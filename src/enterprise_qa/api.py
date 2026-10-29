import asyncio
import json
import sqlite3
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Header
from fastapi.responses import StreamingResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from .config import ROOT, settings
from .storage import Store
from .schemas import RunRequest
from .knowledge import load_knowledge, scenarios
from .models import DeepSeekModel, MockModel
from .agent import Agent


def create_app(db_path=None):
    store = Store(db_path or ROOT / 'runtime/app.sqlite3')
    tasks = set()

    @asynccontextmanager
    async def lifespan(app):
        store.recover()
        yield
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title='知据 · 企业知识问答 Agent', version='0.1.0', lifespan=lifespan)
    app.state.store = store

    @app.get('/api/health')
    def health():
        cfg = settings()
        return {'status': 'ok', 'model': cfg.model, 'live_configured': bool(cfg.api_key),
                'mock_boundary': '离线 Mock 只验证流程，不证明真实模型决策效果。'}

    @app.get('/api/scenarios')
    def get_scenarios():
        return scenarios()

    @app.post('/api/conversations', status_code=201)
    def new_conversation():
        return store.new_conversation()

    @app.get('/api/conversations')
    def conversations():
        return store.list_conversations()

    @app.get('/api/conversations/{cid}')
    def conversation(cid: str):
        result = store.conversation(cid)
        if result is None:
            raise HTTPException(404, '会话不存在')
        return result

    async def execute_run(run, knowledge, spec, history):
        rid = run['id']
        store.set_status(rid, 'running')
        model = DeepSeekModel(settings()) if run['mode'] == 'live' else MockModel()
        agent = Agent(model, knowledge, settings(), spec, emit=lambda e: store.event(rid, e))
        result = await agent.run(run['question'], history)
        result.update(run_id=rid, trace_id=rid)
        store.set_status(rid, result['status'], result)

    @app.post('/api/conversations/{cid}/runs', status_code=202)
    async def create_run(cid: str, req: RunRequest):
        try:
            knowledge, spec = load_knowledge(req.scenario)
        except ValueError:
            raise HTTPException(422, '未知评审场景')
        previous = store.conversation(cid)
        if previous is None:
            raise HTTPException(404, '会话不存在')
        history = []
        for r in previous['runs'][-6:]:
            if r['result']:
                history.extend([{'role': 'user', 'content': r['question']},
                                {'role': 'assistant', 'content': r['result']['answer']}])
        try:
            run = store.create_run(cid, req, knowledge)
        except sqlite3.IntegrityError:
            raise HTTPException(409, '当前会话已有任务运行，请等待完成。')
        task = asyncio.create_task(execute_run(run, knowledge, spec, history))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return run

    @app.get('/api/runs/{rid}')
    def get_run(rid: str):
        result = store.run(rid)
        if result is None:
            raise HTTPException(404, '运行不存在')
        return result

    @app.get('/api/runs/{rid}/trace')
    def trace(rid: str):
        get_run(rid)
        data = '\n'.join(json.dumps(e, ensure_ascii=False) for e in store.events(rid)) + '\n'
        return Response(data, media_type='application/x-ndjson',
            headers={'Content-Disposition': f'attachment; filename="trace-{rid}.jsonl"'})

    @app.get('/api/runs/{rid}/events')
    async def events(rid: str, after: int = Query(default=0, ge=0), last_event_id: str | None = Header(default=None)):
        get_run(rid)
        cursor = max(after, int(last_event_id) if last_event_id and last_event_id.isdigit() else 0)
        async def stream():
            nonlocal cursor
            while True:
                for e in store.events(rid, cursor):
                    cursor = e['sequence']
                    yield f"id: {cursor}\ndata: {json.dumps(e, ensure_ascii=False)}\n\n"
                run = store.run(rid)
                if run['result'] is not None:
                    yield f"event: result\ndata: {json.dumps(run, ensure_ascii=False)}\n\n"
                    break
                yield ': heartbeat\n\n'
                await asyncio.sleep(0.35)
        return StreamingResponse(stream(), media_type='text/event-stream',
                                 headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    @app.get('/api/documents')
    def documents(scenario: str = 'normal'):
        try:
            kb, _ = load_knowledge(scenario)
        except ValueError:
            raise HTTPException(422, '未知场景')
        return {'dataset_version': kb.version, 'documents': kb.documents}

    @app.get('/api/documents/{doc_id}')
    def document(doc_id: str, dataset_version: str | None = None, scenario: str = 'normal'):
        if dataset_version:
            docs = store.snapshot(dataset_version)
        else:
            try:
                docs = load_knowledge(scenario)[0].documents
            except ValueError:
                raise HTTPException(422, '未知场景')
        d = next((d for d in docs or [] if d['doc_id'] == doc_id), None)
        if d is None:
            raise HTTPException(404, '指定版本文档不存在')
        return d

    dist = ROOT / 'frontend/dist'
    if dist.exists():
        app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')
        @app.get('/')
        def index():
            return FileResponse(dist / 'index.html')
    return app


app = create_app()
