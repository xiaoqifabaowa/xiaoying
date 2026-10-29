import argparse
import asyncio
import json
from pathlib import Path
from .config import settings
from .knowledge import load_knowledge
from .models import DeepSeekModel, MockModel
from .agent import Agent


async def run(args):
    kb, spec = load_knowledge(args.scenario)
    model = MockModel() if args.mode == 'mock' else DeepSeekModel(settings())
    history = []
    prelude = None
    if spec.get('history_question'):
        pre_agent = Agent(model, kb, settings(), spec)
        prelude = await pre_agent.run(spec['history_question'])
        history = [{'role': 'user', 'content': spec['history_question']},
                   {'role': 'assistant', 'content': prelude['answer']}]
    agent = Agent(model, kb, settings(), spec)
    question = args.question or spec['question']
    result = await agent.run(question, history)
    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        for name, value in [('input.json', {'question': question, 'history': history, 'scenario': args.scenario, 'mode': args.mode}),
                            ('output.json', result), ('snapshot.json', kb.documents)]:
            (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        (out / 'trace.jsonl').write_text('\n'.join(json.dumps(e, ensure_ascii=False) for e in agent.events)+'\n', encoding='utf-8')
        if prelude:
            (out / 'prelude.json').write_text(json.dumps({'question': spec['history_question'], 'result': prelude,
                'trace': pre_agent.events}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--mode', choices=['mock', 'live'], default='mock')
    p.add_argument('--scenario', default='normal')
    p.add_argument('--question')
    p.add_argument('--output')
    asyncio.run(run(p.parse_args()))


if __name__ == '__main__':
    main()
