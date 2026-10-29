import asyncio
import time
from datetime import datetime, timezone
from typing import TypedDict, Any
from langgraph.graph import StateGraph, END
from pydantic import ValidationError
from .schemas import SearchArgs, ReadArgs, Answer
from .models import ModelFailure
from .evidence import validate_answer


class State(TypedDict):
    question: str
    history: list
    evidence: dict
    observations: list
    steps: int
    tools: int
    decision: Any
    result: Any


class Agent:
    def __init__(self, model, knowledge, config, spec=None, emit=None):
        self.model, self.knowledge, self.config = model, knowledge, config
        self.spec, self.emit = spec or {}, emit
        self.events = []
        self.step_limit = min(config.max_steps, self.spec.get('max_steps', config.max_steps))
        graph = StateGraph(State)
        graph.add_node('decide', self.decide)
        graph.add_node('execute', self.execute)
        graph.set_entry_point('decide')
        graph.add_conditional_edges('decide', lambda s: 'end' if s.get('result') else 'execute',
                                    {'end': END, 'execute': 'execute'})
        graph.add_conditional_edges('execute', lambda s: 'end' if s.get('result') else 'decide',
                                    {'end': END, 'decide': 'decide'})
        self.graph = graph.compile()

    def event(self, kind, **data):
        event = {'sequence': len(self.events) + 1, 'timestamp': datetime.now(timezone.utc).isoformat(),
                 'kind': kind, 'mode': self.model.mode, 'model': self.config.model if self.model.mode == 'live' else 'scripted-mock',
                 'dataset_version': self.knowledge.version, **data}
        self.events.append(event)
        if self.emit:
            self.emit(event)

    def stop(self, state, status, code, message):
        state['result'] = Answer(status=status, answer=message,
            knowledge_gaps=['本次任务未完成，请参考已有证据和执行记录。'], stop_reason=code).model_dump()
        return state

    async def decide(self, state):
        if state['steps'] >= self.step_limit or state['tools'] >= self.config.max_tools:
            return self.stop(state, 'incomplete', 'BUDGET_EXHAUSTED', '执行预算已耗尽，任务未完成。')
        state['steps'] += 1
        start = time.monotonic()
        try:
            d = await self.model.decide({'question': state['question'], 'history': state['history'],
                'evidence': state['evidence'], 'observations': state['observations'],
                'remaining_decisions': self.step_limit - state['steps'],
                'remaining_tools': self.config.max_tools - state['tools']})
            state['decision'] = d
            self.event('decision', step=state['steps'], action=d.action, arguments=d.arguments,
                       reason=d.reason, duration_ms=round((time.monotonic()-start)*1000),
                       remaining_steps=self.step_limit-state['steps'], remaining_tools=self.config.max_tools-state['tools'],
                       provider=getattr(self.model, 'last_metadata', None))
        except ModelFailure as exc:
            self.event('model_error', code=exc.code)
            return self.stop(state, 'failed', exc.code, '真实模型调用失败；未自动切换为 Mock。请检查配置或主动选择离线演示。')
        except (ValueError, ValidationError, TypeError):
            state['decision'] = None
            observation = {'action': 'validation', 'output': {'ok': False, 'error': {'code': 'INVALID_MODEL_OUTPUT',
                'message': '动作格式不合法，请按 JSON Schema 修正。'}}}
            state['observations'].append(observation)
            self.event('validation', **observation)
        return state

    async def execute(self, state):
        d = state.get('decision')
        if not d:
            return state
        if d.action in ('finish', 'ask_user'):
            errors = ['终止动作必须包含 result。'] if d.result is None else validate_answer(
                d.result, state['evidence'], any(o['action'] == 'search_documents' for o in state['observations']))
            if d.action == 'ask_user' and d.result and not d.result.clarification:
                errors.append('ask_user 必须提供 clarification。')
            if not errors and d.result:
                if state['steps'] >= self.step_limit:
                    return self.stop(state, 'incomplete', 'BUDGET_EXHAUSTED', '预算不足以完成证据审核，任务未完成。')
                state['steps'] += 1
                try:
                    audit = await self.model.audit(state['question'], state['history'], d.result.model_dump(), state['evidence'], state['observations'])
                    self.event('audit', step=state['steps'], provider=getattr(self.model, 'last_metadata', None), **audit)
                    if not audit['supported']:
                        errors.extend(audit['issues'] or ['结论未通过证据语义审核。'])
                except ModelFailure as exc:
                    self.event('model_error', code=exc.code)
                    return self.stop(state, 'incomplete', 'AUDIT_UNAVAILABLE', '证据审核服务不可用，未发布候选答案。')
                except (ValueError, TypeError, KeyError):
                    errors.append('证据审核输出无效，不能发布候选答案。')
            if errors:
                output = {'ok': False, 'error': {'code': 'EVIDENCE_VALIDATION', 'message': errors}}
                state['observations'].append({'action': 'validate_answer', 'output': output})
                self.event('validation', output=output)
            else:
                state['result'] = d.result.model_dump()
            return state
        state['tools'] += 1
        start = time.monotonic()
        try:
            if d.action == 'search_documents':
                args = SearchArgs.model_validate(d.arguments)
                if self.spec.get('fault') == 'search_always':
                    raise OSError('injected')
                output = await asyncio.wait_for(asyncio.to_thread(self.knowledge.search, **args.model_dump()), self.config.tool_timeout)
            else:
                args = ReadArgs.model_validate(d.arguments)
                if self.spec.get('fault') == 'read_always':
                    raise OSError('injected')
                output = await asyncio.wait_for(asyncio.to_thread(self.knowledge.read, **args.model_dump()), self.config.tool_timeout)
                if output.get('ok'):
                    state['evidence'][args.doc_id] = output['document']
        except ValidationError:
            output = {'ok': False, 'error': {'code': 'INVALID_TOOL_ARGUMENTS', 'message': '请修正工具参数。', 'retryable': False}}
        except TimeoutError:
            output = {'ok': False, 'error': {'code': 'TOOL_TIMEOUT', 'message': '工具执行超时。', 'retryable': True}}
        except Exception:
            output = {'ok': False, 'error': {'code': 'TOOL_UNAVAILABLE', 'message': '工具暂时不可用。', 'retryable': True}}
        state['observations'].append({'action': d.action, 'arguments': d.arguments, 'output': output})
        summary = (f"命中 {len(output['hits'])} 份文档" if 'hits' in output else
                   f"已读取 {output['document']['doc_id']}" if 'document' in output else output.get('error', {}).get('code'))
        self.event('tool', action=d.action, arguments=d.arguments, output=output, summary=summary,
                   duration_ms=round((time.monotonic()-start)*1000))
        return state

    async def run(self, question, history=None):
        state = State(question=question, history=history or [], evidence={}, observations=[],
                      steps=0, tools=0, decision=None, result=None)
        self.event('started', question=question, limits={'steps': self.step_limit, 'tools': self.config.max_tools,
                   'timeout_seconds': self.config.run_timeout})
        try:
            async with asyncio.timeout(self.config.run_timeout):
                # Keep latest state, including evidence, if the outer timeout cancels execution.
                async for update in self.graph.astream(state, {'recursion_limit': self.step_limit*3+5}, stream_mode='values'):
                    state = update
        except TimeoutError:
            self.stop(state, 'incomplete', 'RUN_TIMEOUT', '运行时间已达到上限，任务未完成。')
        except Exception:
            self.stop(state, 'failed', 'INTERNAL_ERROR', '运行异常，任务未完成。')
        result = {**state['result'], 'mode': self.model.mode, 'dataset_version': self.knowledge.version,
                  'steps': state['steps'], 'tool_calls': state['tools'],
                  'evidence': list(state['evidence'].values())}
        self.event('completed', status=result['status'], stop_reason=result['stop_reason'])
        return result
