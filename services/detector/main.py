import asyncio
import hashlib
import hmac
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
import httpx
import joblib
from fastapi import FastAPI
from services.common.security import secret
from services.common.audit import emit
from services.detector.model import score, FEATURES, is_anomalous
from services.detector.telemetry import sample
from services.detector.soc import signals
state={'status':'waiting_for_trained_model','features':None,'score':None}
async def soc_loop():
    while True:
        try:
            state['soc_signals']=await signals()
            for signal in state['soc_signals']: emit('soc','security_signal',**signal)
        except Exception as exc:
            state['soc_error']=type(exc).__name__
        await asyncio.sleep(10)

async def loop():
    model=None; stamp=None; consecutive=0; last_alert=0
    path=Path(os.getenv('MODEL_DIR','/models'))/'model.joblib'
    while True:
        try:
            if not path.exists():
                state['status']='waiting_for_trained_model'
            else:
                if path.stat().st_mtime!=stamp:
                    # Only trusted local training artifact; never accept uploaded pickle/joblib.
                    model=joblib.load(path); stamp=path.stat().st_mtime
                row=await sample(); value=score(model,row)
                state.update(status='monitoring',features=dict(zip(FEATURES,row)),score=value)
                consecutive=consecutive+1 if is_anomalous(value,row) else 0
                emit('detector','inference',score=value,features=row,consecutive=consecutive)
                if consecutive>=3 and time.time()-last_alert>30:
                    payload=json.dumps({'id':str(uuid.uuid4()),'issued_at':time.time(),
                                        'score':value,'features':row},sort_keys=True).encode()
                    signature=hmac.new(secret('alert_key').encode(),payload,hashlib.sha256).hexdigest()
                    async with httpx.AsyncClient(trust_env=False,timeout=8) as c:
                        r=await c.post('http://remediator:8000/alerts',content=payload,
                                       headers={'Content-Type':'application/json','X-Signature':signature})
                        r.raise_for_status()
                    last_alert=time.time(); consecutive=0
                    emit('detector','alert_delivered',incident_id=json.loads(payload)['id'])
        except Exception as exc:
            consecutive=0; state['status']='telemetry_or_delivery_error'
            emit('detector','error',error_type=type(exc).__name__)
        await asyncio.sleep(2)
@asynccontextmanager
async def lifespan(app):
    tasks=[asyncio.create_task(loop()),asyncio.create_task(soc_loop())]
    yield
    for task in tasks: task.cancel()
    await asyncio.gather(*tasks,return_exceptions=True)
app=FastAPI(title='ML detector',lifespan=lifespan)
def snapshot():
    """The single reading point of the detector state: /health (published as /ops/ml) and /anomaly both read it."""
    return state
def verdict(s):
    # Only a live measurement counts. Without a model, or after a collection error, the verdict is
    # false AND status says why; the stale score of an earlier cycle is not returned as current.
    measured=s['status']=='monitoring' and s['score'] is not None and s['features'] is not None
    return {'anomaly':bool(measured and is_anomalous(s['score'],[s['features'][f] for f in FEATURES])),
            'score':s['score'] if measured else None,'status':s['status']}
@app.get('/health')
def health(): return snapshot()
@app.get('/anomaly')
def anomaly(): return verdict(snapshot())
