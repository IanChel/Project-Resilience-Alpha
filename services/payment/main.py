import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from services.common.security import identity, operator, require_internal
from services.common.audit import emit
from services.payment.db import Ledger, Conflict, Funds
ledger=Ledger()
REQUESTS=Counter('lab_requests_total','Business responses',['route','status'])
DURATION=Histogram('lab_duration_seconds','Business request time',['route'])
ACTIVE=Gauge('lab_active_work','Occupied simulated downstream connection slots')
DENIED=Counter('lab_capacity_denied_total','Requests rejected because capacity is exhausted')
CONTAINED=Gauge('lab_contained','Targeted quote protection enabled')
active=0
last_quote={}
policy_path=Path(os.getenv('STATE_DIR','/state'))/'policy.json'
contained=False
@asynccontextmanager
async def lifespan(app):
    global contained
    ledger.init()
    if policy_path.exists(): contained=json.loads(policy_path.read_text())['contained']
    CONTAINED.set(int(contained))
    yield
app=FastAPI(title='Fictitious payment API',lifespan=lifespan)
class Payment(BaseModel):
    amount_cents: int = Field(strict=True,ge=1,le=100000)
    recipient: str = Field(pattern='^merchant$')
class Quote(BaseModel):
    amount_cents: int = Field(strict=True,ge=1,le=100000)
async def acquire(route):
    global active
    if active>=4:
        DENIED.inc(); REQUESTS.labels(route,'503').inc()
        emit('payment','capacity_denied',route=route)
        raise HTTPException(503,'Simulated downstream capacity exhausted')
    active+=1; ACTIVE.set(active)
def release():
    global active
    active-=1; ACTIVE.set(active)
@app.get('/health')
def health():
    return {'status':'alive'}
@app.get('/ready')
def ready():
    ledger.snapshot()
    return {'status':'ready'}
@app.get('/metrics')
def metrics():
    return Response(generate_latest(),media_type=CONTENT_TYPE_LATEST)
@app.get('/accounts')
def accounts(user=Depends(operator)):
    return ledger.snapshot()
@app.post('/payments')
async def pay(body: Payment, idempotency_key: str = Header(min_length=8,max_length=80),user=Depends(operator)):
    await acquire('payments')
    start=time.monotonic()
    try:
        await asyncio.sleep(0.08)  # Simulated downstream payment latency, shared capacity.
        try:
            tx,replayed=await asyncio.to_thread(ledger.pay,body.amount_cents,body.recipient,idempotency_key)
        except Conflict: raise HTTPException(409,'Idempotency key reused with different payload')
        except Funds: raise HTTPException(409,'Insufficient fictitious balance')
        REQUESTS.labels('payments','200').inc()
        emit('payment','transaction_success',transaction_id=tx['id'],replayed=replayed)
        return {'transaction':tx,'replayed':replayed}
    finally:
        DURATION.labels('payments').observe(time.monotonic()-start); release()
@app.post('/quotes')
async def quote(body: Quote,user=Depends(identity)):
    now=time.monotonic()
    if contained and now-last_quote.get(user['sub'],-100)<1:
        REQUESTS.labels('quotes','429').inc()
        raise HTTPException(429,'Containment: one quote per identity per second')
    last_quote[user['sub']]=now
    await acquire('quotes')
    start=time.monotonic()
    try:
        # Deliberate LAB design flaw: slow quotation shares payment capacity.
        # No CPU/memory stress on Windows; bounded application concurrency only.
        await asyncio.sleep(0.6)
        REQUESTS.labels('quotes','200').inc()
        return {'amount_cents':body.amount_cents,'fee_cents':1}
    finally:
        DURATION.labels('quotes').observe(time.monotonic()-start); release()
@app.post('/control/contain')
def contain(x_control_key: str = Header(default='')):
    global contained
    require_internal(x_control_key,'control_key')
    changed=not contained
    contained=True; CONTAINED.set(1)
    policy_path.parent.mkdir(parents=True,exist_ok=True)
    tmp=policy_path.with_suffix('.tmp'); tmp.write_text(json.dumps({'contained':True})); tmp.replace(policy_path)
    emit('payment','containment_enabled',changed=changed)
    return {'contained':True,'changed':changed}
