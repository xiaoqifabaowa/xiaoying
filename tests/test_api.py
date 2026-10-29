import json
import time
from fastapi.testclient import TestClient
from enterprise_qa.api import create_app
from enterprise_qa.storage import Store
from enterprise_qa.schemas import RunRequest
from enterprise_qa.knowledge import load_knowledge


def test_conversation_run_trace_and_snapshot(tmp_path):
    with TestClient(create_app(tmp_path/'db.sqlite')) as client:
        cid=client.post('/api/conversations').json()['id']
        response=client.post(f'/api/conversations/{cid}/runs',json={'question':'报销期限多久？','mode':'mock','scenario':'normal'})
        assert response.status_code==202
        rid=response.json()['id']
        for _ in range(100):
            run=client.get(f'/api/runs/{rid}').json()
            if run['result']: break
            time.sleep(.05)
        assert run['result']['status']=='answered'
        version=run['result']['dataset_version']
        doc=client.get(f'/api/documents/D01?dataset_version={version}').json()
        assert '30 天' in doc['content']
        events=client.get(f'/api/runs/{rid}/events?after=1').text
        assert 'event: result' in events
        assert 'id: 1\n' not in events
        trace=client.get(f'/api/runs/{rid}/trace').text
        rows=[json.loads(s) for s in trace.splitlines()]
        assert [e['kind'] for e in rows].count('tool')>=2
        assert client.get(f'/api/conversations/{cid}').json()['runs'][0]['result']
        assert client.get('/api/documents/D01?dataset_version=bad').status_code==404
        assert client.get('/api/runs/missing').status_code==404
        assert client.get('/api/documents?scenario=missing').status_code==422


def test_api_validation_and_secret_not_exposed(tmp_path):
    with TestClient(create_app(tmp_path/'db.sqlite')) as client:
        c=client.post('/api/conversations').json()['id']
        assert client.post(f'/api/conversations/{c}/runs',json={'question':'','mode':'mock'}).status_code==422
        assert client.post(f'/api/conversations/{c}/runs',json={'question':'x','mode':'other'}).status_code==422
        assert client.post(f'/api/conversations/{c}/runs',json={'question':'x','scenario':'missing'}).status_code==422
        assert client.post('/api/conversations/missing/runs',json={'question':'x','mode':'mock'}).status_code==404
        assert 'api_key' not in client.get('/api/health').text


def test_restart_recovers_incomplete_runs_and_preserves_snapshot(tmp_path):
    store=Store(tmp_path/'db.sqlite')
    c=store.new_conversation()
    kb,_=load_knowledge()
    r=store.create_run(c['id'],RunRequest(question='报销期限',mode='mock'),kb)
    store.recover()
    assert store.run(r['id'])['result']['stop_reason']=='SERVER_RESTART'
    assert store.snapshot(kb.version)[0]['content']==kb.documents[0]['content']


def test_duplicate_active_run_is_rejected(tmp_path):
    import sqlite3
    import pytest
    store=Store(tmp_path/'db.sqlite')
    c=store.new_conversation()
    kb,_=load_knowledge()
    request=RunRequest(question='报销期限',mode='mock')
    store.create_run(c['id'],request,kb)
    with pytest.raises(sqlite3.IntegrityError):
        store.create_run(c['id'],request,kb)
