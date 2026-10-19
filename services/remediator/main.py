import asyncio
import hashlib
import hmac
import json
import math
import os
import sqlite3
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
import httpx
from fastapi import FastAPI, HTTPException, Request, Depends
from services.common.security import secret, operator
from services.common.audit import emit
from services.remediator import bans
STORE=Path(os.getenv('STATE_DIR','/state'))/'incidents.sqlite'
# The order of a recovery. Two stages can share a timestamp (coarse clocks), then this order decides, so the
# stages of an incident are always listed in the same order.
STAGE_ORDER=('detected','accepted','containing','verifying','recovered','failed')
lock=asyncio.Lock()
tasks=set()
def connection():
    STORE.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(STORE); c.row_factory=sqlite3.Row
    c.execute('CREATE TABLE IF NOT EXISTS incidents(id TEXT PRIMARY KEY,status TEXT,created REAL,updated REAL,evidence TEXT)')
    # One row per stage reached, so the dashboard can show where the time goes. `evidence` is overwritten at each
    # status; this table is not. A separate table keeps the incidents schema (and its positional inserts) unchanged.
    c.execute('CREATE TABLE IF NOT EXISTS stages(incident_id TEXT,status TEXT,ts REAL,PRIMARY KEY(incident_id,status))')
    return c
def update(incident_id,status,evidence):
    now=time.time()
    with connection() as c:
        c.execute('UPDATE incidents SET status=?,updated=?,evidence=? WHERE id=?',
                  (status,now,json.dumps(evidence),incident_id))
        c.execute('INSERT OR REPLACE INTO stages VALUES(?,?,?)',(incident_id,status,now))
    emit('remediator',status,incident_id=incident_id,**evidence)
async def service_token():
    # The recovery login goes straight to the auth service over the internal network, never through the WAF.
    # Auth rate-limits per peer address and every public client shares the edge's address: through the WAF,
    # a flood of public logins would exhaust the budget this recovery needs. The public path stays limited;
    # only this internal peer has its own budget. The payment proof below still goes through the WAF.
    async with httpx.AsyncClient(trust_env=False,base_url=os.getenv('AUTH_URL','http://auth:8000'),timeout=5) as c:
        r=await c.post('/token',json={'username':'alice','password':secret('alice_password')})
        r.raise_for_status(); return r.json()['access_token']
async def business_verify(incident_id):
    token=await service_token()
    # Verify through WAF and reverse proxy, not just the internal health endpoint.
    async with httpx.AsyncClient(trust_env=False,base_url=os.getenv('PUBLIC_URL','http://waf:8080'),timeout=5) as c:
        headers={'Authorization':'Bearer '+token,'Idempotency-Key':'recovery-'+incident_id}
        for _ in range(15):
            try:
                r=await c.post('/api/payments',headers=headers,json={'amount_cents':1,'recipient':'merchant'})
                r.raise_for_status(); tx=r.json()['transaction']
                r=await c.get('/api/accounts',headers=headers); r.raise_for_status()
                snap=r.json()
                if snap['total_cents']!=200000: raise RuntimeError('Ledger total mismatch')
                if not any(t['id']==tx['id'] for t in snap['transactions']): raise RuntimeError('Committed transaction missing')
                return {'transaction_id':tx['id'],'total_cents':snap['total_cents']}
            except (httpx.HTTPError,RuntimeError): await asyncio.sleep(1)
    raise RuntimeError('End-to-end business verification failed')
def alert_data(incident_id):
    """The signed alert as received (the incident evidence is the alert until the first status update)."""
    with connection() as c: row=c.execute('SELECT evidence FROM incidents WHERE id=?',(incident_id,)).fetchone()
    try: data=json.loads(row['evidence']) if row else {}
    except ValueError: return {}
    return data if isinstance(data,dict) else {}
async def recover(incident_id):
    async with lock:
        # The ban is decided from the SIGNED alert only (never a request header) and is best effort:
        # whatever happens to it, the containment below goes ahead.
        ban=bans.plan(alert_data(incident_id).get('sources'))
        update(incident_id,'containing',{'action':'enable_quote_admission','ban':ban})
        try:
            playbook=Path(__file__).resolve().parents[2]/'infra'/'ansible'/'contain.yml'
            extra=[]
            try:
                if ban['eligible']:
                    files=bans.merged(bans.config()['dir'],ban['eligible'],ban['ttl_s'])
                    extra=['-e',json.dumps({'ban_ips':ban['eligible'],'ban_list_content':files['list'],'ban_expiry_content':files['expiry']})]
            except Exception as exc:   # best effort: no ban, same containment
                ban={**ban,'eligible':[],'note':f'ban preparation failed: {type(exc).__name__}'}
            proc=await asyncio.create_subprocess_exec(sys.executable,'-m','ansible.cli.playbook','-i','localhost,',
                str(playbook),*extra,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            try: stdout,stderr=await asyncio.wait_for(proc.communicate(),timeout=25)
            except asyncio.TimeoutError:
                proc.kill(); await proc.wait(); raise RuntimeError('Ansible timeout')
            if proc.returncode: raise RuntimeError('Ansible failed; inspect internal console')
            # What was really written, read back from the ban list: not assumed from the plan.
            if ban['eligible']:
                try: ban={**ban,'applied':bans.applied(bans.config()['dir'],ban['eligible'])}
                except Exception as exc: ban={**ban,'applied':[],'note':f'ban read-back failed: {type(exc).__name__}'}
            update(incident_id,'verifying',{'ban':ban})
            proof=await business_verify(incident_id)
            update(incident_id,'recovered',{**proof,'ban':ban})
        except Exception as exc:
            update(incident_id,'failed',{'error_type':type(exc).__name__,'manual_review_required':True,'ban':ban})
async def ban_upkeep():
    """Bans expire: drop them from the ban list once their time is up. Serialised with recoveries by `lock`."""
    while True:
        await asyncio.sleep(15)
        try:
            cfg=bans.config()
            if not cfg['enabled']: continue
            async with lock: removed=bans.prune(cfg['dir'])
            if removed: emit('remediator','ban_expired',removed=removed)
        except Exception as exc: emit('remediator','ban_upkeep_error',error_type=type(exc).__name__)
@asynccontextmanager
async def lifespan(app):
    # On interrupted recovery, resume the same fixed idempotent operation after restart.
    with connection() as c:
        interrupted=[r['id'] for r in c.execute("SELECT id FROM incidents WHERE status IN ('accepted','containing','verifying')")]
    for iid in interrupted:
        task=asyncio.create_task(recover(iid)); tasks.add(task); task.add_done_callback(tasks.discard)
    upkeep=asyncio.create_task(ban_upkeep())
    yield
    upkeep.cancel()
    for task in list(tasks): task.cancel()
    await asyncio.gather(upkeep,*tasks,return_exceptions=True)
app=FastAPI(title='Authorized remediation',lifespan=lifespan)
@app.post('/alerts',status_code=202)
async def alert(request: Request):
    raw=await request.body()
    if len(raw)>4096: raise HTTPException(413,'Alert too large')
    signature=request.headers.get('X-Signature','')
    expected=hmac.new(secret('alert_key').encode(),raw,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature,expected): raise HTTPException(403,'Invalid signature')
    try:
        data=json.loads(raw); iid=str(uuid.UUID(data['id']))
        issued=float(data['issued_at'])
        if not math.isfinite(issued) or abs(time.time()-issued)>30: raise ValueError('stale')
        value=float(data['score']); row=data['features']
        if not math.isfinite(value) or value>=0 or len(row)!=4 or not all(math.isfinite(float(v)) for v in row) or row[2]<=0:
            raise ValueError('evidence')
    except (ValueError,KeyError,TypeError): raise HTTPException(422,'Invalid alert evidence')
    with connection() as c:
        old=c.execute('SELECT status FROM incidents WHERE id=?',(iid,)).fetchone()
        if old: return {'id':iid,'status':old['status'],'duplicate':True}
        busy=c.execute("SELECT id FROM incidents WHERE status IN ('accepted','containing','verifying')").fetchone()
        if busy: return {'id':busy['id'],'status':'already_running'}
        now=time.time()
        c.execute('INSERT INTO incidents VALUES(?,?,?,?,?)',(iid,'accepted',now,now,json.dumps(data)))
        # `detected` is the moment the DETECTOR raised the alert (its signed, freshness-checked issued_at), not the
        # moment this service received it: the chrono starts at the detection.
        c.executemany('INSERT OR REPLACE INTO stages VALUES(?,?,?)',[(iid,'detected',issued),(iid,'accepted',now)])
    task=asyncio.create_task(recover(iid)); tasks.add(task); task.add_done_callback(tasks.discard)
    return {'id':iid,'status':'accepted'}
@app.get('/status')
def status(user=Depends(operator)):
    with connection() as c:
        rows=[dict(r) for r in c.execute('SELECT * FROM incidents ORDER BY created DESC LIMIT 30')]
        reached={}
        for r in c.execute('SELECT incident_id,status,ts FROM stages WHERE incident_id IN (SELECT id FROM incidents ORDER BY created DESC LIMIT 30)'):
            reached.setdefault(r['incident_id'],{})[r['status']]=r['ts']
    for row in rows:
        stages=reached.get(row['id'],{})
        stages.setdefault('detected',row['created']); stages.setdefault(row['status'],row['updated'])   # incidents older than the stage log
        row['stages']=dict(sorted(stages.items(),key=lambda kv:(kv[1],STAGE_ORDER.index(kv[0]) if kv[0] in STAGE_ORDER else len(STAGE_ORDER))))
    # `now` lets the dashboard measure a running incident against the server clock, not the browser's.
    return {'incidents':rows,'now':time.time()}
@app.get('/health')
def health(): return {'status':'alive'}
