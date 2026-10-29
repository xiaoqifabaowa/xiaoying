"""Record actual executions, then evaluate bounded assertions (not a semantic proof)."""
import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from contextlib import redirect_stdout
import io
from enterprise_qa.cli import run
from enterprise_qa.knowledge import scenarios
from enterprise_qa.evidence import validate_answer
from enterprise_qa.schemas import Answer


def assess(spec, output, trace):
    checks = {'expected_status': output['status']==spec['expected'],
        'correct_mode': output['mode'] in ['live','mock'],
        'bounded_steps': output['steps']<=spec.get('max_steps',8),
        'bounded_tools': output['tool_calls']<=10,
        'trace_completed': bool(trace) and trace[-1]['kind']=='completed'}
    answer=Answer.model_validate({k:v for k,v in output.items() if k in Answer.model_fields})
    checks['quote_integrity']=not validate_answer(answer,{d['doc_id']:d for d in output['evidence']},True)
    if spec['id'] in ['normal','paraphrase','changed']:
        expected='45' if spec['id']=='changed' else '30'
        checks['expected_fact']=expected in output['answer']
        checks['expected_document']=any(c['doc_id']=='D01' for c in output['citations'])
    if spec['id']=='conflict':
        checks['both_documents']={'D01','D02'} <= {c['doc_id'] for c in output['citations']}
        checks['both_values']='30' in output['answer'] and '15' in output['answer']
        checks['requests_clarification']=bool(output['clarification'])
    if spec['id']=='context':
        checks['materials_answer']='发票' in output['answer'] and '审批' in output['answer']
    if spec['id'] in ['search_failure','read_failure']:
        checks['observed_failure']=any(e['kind']=='tool' and not e['output'].get('ok') for e in trace)
        checks['not_hidden_by_budget']=output['stop_reason'] not in ['BUDGET_EXHAUSTED', 'RUN_TIMEOUT', 'INTERNAL_ERROR']
    if spec['id']=='budget': checks['explicit_budget']=output['stop_reason']=='BUDGET_EXHAUSTED'
    return checks


async def main(args):
    root=Path('examples')/args.mode
    root.mkdir(parents=True,exist_ok=True)
    rows=[]
    for spec in scenarios():
        out=root/spec['id']
        if args.force or not (out/'output.json').exists():
            with redirect_stdout(io.StringIO()):
                await run(SimpleNamespace(mode=args.mode,scenario=spec['id'],question=None,output=str(out)))
        output=json.loads((out/'output.json').read_text(encoding='utf-8'))
        trace=[json.loads(s) for s in (out/'trace.jsonl').read_text(encoding='utf-8').splitlines()]
        checks=assess(spec,output,trace)
        row={'scenario':spec['id'],'expected':spec['expected'],'actual':output['status'],
             'passed':all(checks.values()),'checks':checks,
             'path':[e['action'] for e in trace if e['kind']=='decision'],'artifact':str(out).replace('\\','/')}
        rows.append(row)
        print(f"{args.mode} {spec['id']}: {row['actual']} {'PASS' if row['passed'] else 'FAIL'}",flush=True)
    report={'created_at':datetime.now(timezone.utc).isoformat(),'mode':args.mode,
        'boundary':'自动断言只覆盖列出的条件；语义正确性仍需查看原文与人工核验。Mock 不证明真实模型决策。',
        'passed':sum(r['passed'] for r in rows),'total':len(rows),'results':rows}
    (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if report['passed'] != report['total']: raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--mode',choices=['live','mock'],default='mock')
    p.add_argument('--force',action='store_true',help='重新运行已有材料；live 模式会调用付费接口。')
    asyncio.run(main(p.parse_args()))
