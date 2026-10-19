"""Same ledger operations on PostgreSQL (deployment) and SQLite (local tests).
Postgres rows locked in deterministic order; cents are integers; no floats.
"""
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager
from services.common.security import secret
class Conflict(Exception): pass
class Funds(Exception): pass
class Ledger:
    def __init__(self, path=None):
        self.path = path or os.getenv('SQLITE_PATH')
    @contextmanager
    def connection(self):
        if self.path:
            db=sqlite3.connect(self.path,timeout=15)
            db.row_factory=sqlite3.Row
            db.execute('BEGIN IMMEDIATE')
        else:
            import psycopg
            from psycopg.rows import dict_row
            db=psycopg.connect(host=os.getenv('DB_HOST','db'),dbname='payments',user='payments',
                               password=secret('db_password'),row_factory=dict_row,connect_timeout=5)
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback(); raise
        finally: db.close()
    def execute(self,db,sql,args=()):
        return db.execute(sql.replace('?', '%s') if not self.path else sql,args)
    def init(self):
        with self.connection() as db:
            self.execute(db,'CREATE TABLE IF NOT EXISTS accounts (id TEXT PRIMARY KEY, cents BIGINT NOT NULL CHECK(cents>=0))')
            self.execute(db,'CREATE TABLE IF NOT EXISTS transactions (id TEXT PRIMARY KEY, idem TEXT UNIQUE NOT NULL, amount BIGINT NOT NULL CHECK(amount>0), recipient TEXT NOT NULL, created TEXT NOT NULL)')
            for name in ('alice','merchant'):
                self.execute(db,'INSERT INTO accounts(id,cents) VALUES (?,?) ON CONFLICT(id) DO NOTHING',(name,100000))
    def pay(self,amount,recipient,key):
        with self.connection() as db:
            sql='SELECT id,cents FROM accounts ORDER BY id'
            if not self.path: sql+=' FOR UPDATE'
            accounts={r['id']:r['cents'] for r in self.execute(db,sql).fetchall()}
            old=self.execute(db,'SELECT * FROM transactions WHERE idem=?',(key,)).fetchone()
            if old:
                if old['amount']!=amount or old['recipient']!=recipient: raise Conflict()
                return dict(old), True
            if accounts['alice'] < amount: raise Funds()
            self.execute(db,'UPDATE accounts SET cents=cents-? WHERE id=?',(amount,'alice'))
            self.execute(db,'UPDATE accounts SET cents=cents+? WHERE id=?',(amount,recipient))
            txid=str(uuid.uuid4())
            self.execute(db,'INSERT INTO transactions(id,idem,amount,recipient,created) VALUES (?,?,?,?,?)',(txid,key,amount,recipient,datetime.now(timezone.utc).isoformat()))
            return dict(self.execute(db,'SELECT * FROM transactions WHERE id=?',(txid,)).fetchone()), False
    def snapshot(self):
        with self.connection() as db:
            accounts=[dict(x) for x in self.execute(db,'SELECT * FROM accounts ORDER BY id').fetchall()]
            txs=[dict(x) for x in self.execute(db,'SELECT * FROM transactions ORDER BY created DESC,id DESC LIMIT 20').fetchall()]
            return {'accounts':accounts,'transactions':txs,'total_cents':sum(a['cents'] for a in accounts)}
