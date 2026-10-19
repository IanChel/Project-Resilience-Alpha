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
from services.detector.model import score, FEATURES, is_anomalous, next_consecutive, alert_due, consecutive_from_env
from services.detector.telemetry import sample
from services.detector.soc import signals, changed
from services.detector.sources import top_sources
# Observations in a row before an alert. Read once at startup (DETECTOR_CONSECUTIVE, default 3);
# an invalid value stops the service instead of silently falling back.
CONSECUTIVE=consecutive_from_env()
# `config` makes a measurement reproducible: what the detector ran with (nu is the loaded model's, None until one loads).
state={'status':'waiting_for_trained_model','features':None,'score':None,'config':{'consecutive':CONSECUTIVE,'nu':None}}
def build_alert(value,row,sources):
    """The signed alert body. `sources` are the busiest peer addresses seen by the WAF (possibly none)."""
    return json.dumps({'id':str(uuid.uuid4()),'issued_at':time.time(),'score':value,'features':row,'sources':sources},sort_keys=True).encode()
async def soc_loop():
    memory={}   # last state seen per incident: a correlation is journaled when it changes, not every cycle
    while True:
        try:
            state['soc_signals']=await signals()
            for signal in state['soc_signals']:
                if signal['rule']!='incident_correlation' or changed(signal,memory): emit('soc','security_signal',**signal)
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
                    state['config']={'consecutive':CONSECUTIVE,'nu':float(getattr(model[-1],'nu',None) or 0) or None}
                row=await sample(); value=score(model,row)
                state.update(status='monitoring',features=dict(zip(FEATURES,row)),score=value)
                consecutive=next_consecutive(consecutive,value,row)
                emit('detector','inference',score=value,features=row,consecutive=consecutive)
                if alert_due(consecutive,CONSECUTIVE) and time.time()-last_alert>30:
                    payload=build_alert(value,row,await top_sources())
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
    emit('detector','config',consecutive_required=CONSECUTIVE)
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
