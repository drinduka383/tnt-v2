"""A single-process worker with durable, monotonic SQLite run states."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
import json
import os
import sqlite3
import time
import uuid
from src.contracts import AnalysisError

TERMINAL = {'succeeded', 'insufficient_evidence', 'failed', 'cancelled'}

class Cancelled(Exception):
    pass

class RunService:
    def __init__(self, root, pipeline, background=True):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = (self.root / '.worker.lock').open('a+b')
        self.lock.seek(0)
        if self.lock.read(1) == b'':
            self.lock.write(b'1')
            self.lock.flush()
        self.lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            raise RuntimeError('Another worker owns this data directory') from None
        self.db = self.root / 'runs.sqlite3'
        self.pipeline = pipeline
        self.executor = ThreadPoolExecutor(max_workers=1) if background else None
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, key TEXT UNIQUE, spec TEXT NOT NULL, status TEXT NOT NULL, stage TEXT, result TEXT, error TEXT, created REAL NOT NULL, updated REAL NOT NULL)')
            # Single waitress process owns this store; interrupted work is never reported as success.
            db.execute("UPDATE runs SET status='failed', error=?, updated=? WHERE status IN ('accepted','running')",
                       (json.dumps({'code': 'interrupted', 'message': 'Server restarted. Submit a new run.'}), time.time()))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, identifier):
        with self.connect() as db:
            row = db.execute('SELECT * FROM runs WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise AnalysisError('Run not found.', 404, 'not_found')
        record = dict(row)
        for key in ('spec', 'result', 'error'):
            record[key] = json.loads(record[key]) if record[key] else None
        record.pop('key')
        record['spec']['model'].pop('path', None)
        return record

    def recent(self):
        with self.connect() as db:
            rows = db.execute('SELECT id,spec,status,result,created FROM runs ORDER BY created DESC LIMIT 10').fetchall()
        records = []
        for row in rows:
            spec = json.loads(row['spec'])
            result = json.loads(row['result']) if row['result'] else None
            records.append({'id':row['id'], 'target':spec['target'], 'evidence':spec['evidence'],
                            'status':row['status'], 'has_evidence':bool(result and (result.get('evidence_status') == 'ready' or result.get('processed_json') or any(item.get('status') == 'scored' for item in result.get('candidates',[])))),
                            'created':row['created']})
        return records

    def create(self, spec, key=None, upload=None):
        encoded = json.dumps(spec, sort_keys=True, allow_nan=False)
        now, identifier = time.time(), uuid.uuid4().hex
        directory = self.root / identifier
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if key:
                previous = db.execute('SELECT id, spec FROM runs WHERE key=?', (key,)).fetchone()
                if previous:
                    if previous['spec'] != encoded:
                        raise AnalysisError('Idempotency key belongs to different inputs.', 409, 'idempotency_conflict')
                    return self.get(previous['id'])
            pending = db.execute("SELECT count(*) FROM runs WHERE status IN ('accepted','running')").fetchone()[0]
            if pending >= 16:
                raise AnalysisError('Analysis queue is full. Retry later.', 429, 'queue_full')
            directory.mkdir()
            if upload is not None:
                (directory / 'observation.fits').write_bytes(upload)
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?)',
                       (identifier, key, encoded, 'accepted', 'queued', None, None, now, now))
        if self.executor:
            self.executor.submit(self.execute, identifier)
        return self.get(identifier)

    def stage(self, identifier, name):
        with self.connect() as db:
            changed = db.execute("UPDATE runs SET stage=?, updated=? WHERE id=? AND status='running'", (name, time.time(), identifier)).rowcount
        if not changed:
            raise Cancelled()

    def finish(self, identifier, status, result=None, error=None):
        if status not in TERMINAL:
            raise ValueError('Invalid terminal state')
        with self.connect() as db:
            return bool(db.execute("UPDATE runs SET status=?, result=?, error=?, updated=? WHERE id=? AND status='running'",
                        (status, json.dumps(result, allow_nan=False), json.dumps(error), time.time(), identifier)).rowcount)

    def execute(self, identifier):
        with self.connect() as db:
            if not db.execute("UPDATE runs SET status='running', updated=? WHERE id=? AND status='accepted'", (time.time(), identifier)).rowcount:
                return
            spec = json.loads(db.execute('SELECT spec FROM runs WHERE id=?', (identifier,)).fetchone()[0])
        try:
            status, result = self.pipeline(spec, self.root / identifier, lambda name: self.stage(identifier, name))
            self.finish(identifier, status, result=result)
        except Cancelled:
            pass
        except AnalysisError as error:
            status = 'insufficient_evidence' if error.code in ('insufficient_evidence', 'no_observation') else 'failed'
            self.finish(identifier, status, error={'code': error.code, 'message': str(error)})
        except Exception:
            import logging
            logging.exception('Analysis run failed: %s', identifier)
            self.finish(identifier, 'failed', error={'code': 'internal_error', 'message': 'Analysis failed. See the server log.'})

    def cancel(self, identifier):
        self.get(identifier)
        with self.connect() as db:
            db.execute("UPDATE runs SET status='cancelled', updated=? WHERE id=? AND status IN ('accepted','running')", (time.time(), identifier))
        return self.get(identifier)

    def close(self):
        if self.executor:
            self.executor.shutdown(wait=True, cancel_futures=True)
        if not self.lock.closed:
            if os.name == 'nt':
                import msvcrt
                self.lock.seek(0)
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_UNLCK, 1)
            self.lock.close()
