import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def encode(value):
    return json.dumps(value, ensure_ascii=False)


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, title TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY, documents TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, conversation_id TEXT, question TEXT,
              mode TEXT, scenario TEXT, dataset_version TEXT, status TEXT, result TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS events(run_id TEXT, sequence INTEGER, payload TEXT,
              PRIMARY KEY(run_id, sequence));
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_run ON runs(conversation_id)
              WHERE status IN ('queued', 'running');
            ''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def new_conversation(self):
        c = {'id': str(uuid.uuid4()), 'title': '新会话', 'created_at': datetime.now(timezone.utc).isoformat()}
        with self.connect() as db:
            db.execute('INSERT INTO conversations VALUES (:id,:title,:created_at)', c)
        return c

    def list_conversations(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM conversations ORDER BY created_at DESC')]

    def conversation(self, cid):
        with self.connect() as db:
            row = db.execute('SELECT * FROM conversations WHERE id=?', (cid,)).fetchone()
            if row is None:
                return None
            runs = [self.decode_run(r) for r in db.execute('SELECT * FROM runs WHERE conversation_id=? ORDER BY created_at', (cid,))]
            return {**dict(row), 'runs': runs}

    def decode_run(self, row):
        value = dict(row)
        value['result'] = json.loads(value['result']) if value['result'] else None
        return value

    def create_run(self, cid, req, knowledge):
        rid = str(uuid.uuid4())
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT id FROM conversations WHERE id=?', (cid,)).fetchone():
                raise KeyError(cid)
            db.execute('INSERT OR IGNORE INTO snapshots VALUES (?,?)', (knowledge.version, encode(knowledge.documents)))
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?)',
                (rid, cid, req.question, req.mode, req.scenario, knowledge.version, 'queued', None,
                 datetime.now(timezone.utc).isoformat()))
            db.execute("UPDATE conversations SET title=? WHERE id=? AND title='新会话'", (req.question[:35], cid))
        return self.run(rid)

    def run(self, rid):
        with self.connect() as db:
            r = db.execute('SELECT * FROM runs WHERE id=?', (rid,)).fetchone()
            return self.decode_run(r) if r else None

    def event(self, rid, event):
        with self.connect() as db:
            db.execute('INSERT INTO events VALUES (?,?,?)', (rid, event['sequence'], encode(event)))

    def events(self, rid, after=0):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT payload FROM events WHERE run_id=? AND sequence>? ORDER BY sequence', (rid, after))]

    def set_status(self, rid, status, result=None):
        with self.connect() as db:
            db.execute('UPDATE runs SET status=?, result=? WHERE id=?', (status, encode(result) if result else None, rid))

    def snapshot(self, version):
        with self.connect() as db:
            row = db.execute('SELECT documents FROM snapshots WHERE id=?', (version,)).fetchone()
            return json.loads(row[0]) if row else None

    def recover(self):
        # Single-process local service: interrupted jobs cannot silently remain running after restart.
        with self.connect() as db:
            rows = list(db.execute("SELECT id,mode,dataset_version FROM runs WHERE status IN ('queued','running')"))
            for row in rows:
                result = {'run_id': row['id'], 'mode': row['mode'], 'dataset_version': row['dataset_version'],
                    'status': 'incomplete', 'answer': '服务重启中断了此次运行，请重新提问。',
                    'stop_reason': 'SERVER_RESTART', 'citations': [], 'claims': [], 'conflicts': [],
                    'knowledge_gaps': ['运行未完成'], 'clarification': None, 'evidence': []}
                db.execute('UPDATE runs SET status=?,result=? WHERE id=?', ('incomplete', encode(result), row['id']))
