"""Real native HTTP + ML score + signed alert + Ansible + business recovery.
SQLite and TEST proxy replace PostgreSQL and WAF. ML training fixture is synthetic.
This does NOT validate Docker, Prometheus, Loki or Ollama.
"""
import asyncio
import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
import httpx
import numpy as np
from services.common.security import secret
from services.detector.model import train_model,score
ROOT=Path(__file__).resolve().parents[1]
def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));return s.getsockname()[1]

def test_native_anomaly_to_ansible_to_verified_transaction(tmp_path):
    ports={name:port() for name in ['auth','payment','remediator','proxy']}
    urls={name:f'http://127.0.0.1:{p}' for name,p in ports.items()}
    base={**os.environ,'PYTHONPATH':str(ROOT),'SQLITE_PATH':str(tmp_path/'payment.sqlite'),
          'PAYMENT_URL':urls['payment'],'AUTH_URL':urls['auth'],'REMEDIATOR_URL':urls['remediator'],
          'PUBLIC_URL':urls['proxy'],'ANSIBLE_LOCAL_TEMP':str(tmp_path/'ansible-tmp')}
    processes=[];logs=[]
    try:
        for name,module in [('auth','services.auth.main'),('payment','services.payment.main'),('remediator','services.remediator.main'),('proxy','tests.native_proxy')]:
            log=(tmp_path/(name+'.log')).open('w');logs.append(log)
            env={**base,'STATE_DIR':str(tmp_path/name)}
            proc=subprocess.Popen([sys.executable,'-m','uvicorn',module+':app','--host','127.0.0.1','--port',str(ports[name]),'--no-access-log'],cwd=ROOT,env=env,stdout=log,stderr=log)
            processes.append(proc)
        with httpx.Client(trust_env=False,timeout=2) as c:
            for name in ports:
                endpoint='/api/ready' if name=='proxy' else '/ready' if name=='payment' else '/health'
                for attempt in range(100):
                    try:
                        if c.get(urls[name]+endpoint).status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(0.1)
                else:raise AssertionError('Native service failed: '+name+' '+(tmp_path/(name+'.log')).read_text())
            operator=c.post(urls['proxy']+'/auth/token',json={'username':'alice','password':secret('alice_password')}).json()['access_token']
            loadbot=c.post(urls['proxy']+'/auth/token',json={'username':'loadbot','password':secret('loadbot_password')}).json()['access_token']
        async def scenario():
            async with httpx.AsyncClient(trust_env=False,base_url=urls['proxy'],timeout=5) as c:
                h={'Authorization':'Bearer '+operator,'Idempotency-Key':str(uuid.uuid4())}
                r=await c.post('/api/payments',headers=h,json={'amount_cents':1,'recipient':'merchant'});assert r.status_code==200
                running=True
                capacity_seen=asyncio.Event()
                async def flood():
                    while running:
                        reply=await c.post('/api/quotes',headers={'Authorization':'Bearer '+loadbot},json={'amount_cents':100})
                        if reply.status_code==503: capacity_seen.set()
                        await asyncio.sleep(0.05)
                started=time.monotonic()
                attackers=[asyncio.create_task(flood()) for _ in range(8)]
                try:
                    # Synchronize on an observed capacity rejection instead of assuming
                    # eight local clients saturate the service within a fixed 150 ms.
                    await asyncio.wait_for(capacity_seen.wait(),timeout=5)
                    # Capacity can briefly clear between quote batches. Keep
                    # observing payment attempts while the bounded workload is
                    # active instead of sampling one instant and flaking.
                    payment_statuses=[]
                    deadline=asyncio.get_running_loop().time()+5
                    while asyncio.get_running_loop().time()<deadline:
                        reply=await c.post('/api/payments',headers={**h,'Idempotency-Key':str(uuid.uuid4())},
                                           json={'amount_cents':1,'recipient':'merchant'})
                        payment_statuses.append(reply.status_code)
                        if reply.status_code==503: break
                        assert reply.status_code==200,payment_statuses
                        await asyncio.sleep(0)
                    assert 503 in payment_statuses,payment_statuses
                    # Actual telemetry from this service; synthetic clean TRAINING fixture only.
                    rng=np.random.default_rng(7)
                    normal=np.column_stack([rng.uniform(0.5,2,80),rng.integers(0,2,80),np.zeros(80),np.zeros(80)])
                    model=train_model(normal)
                    async with httpx.AsyncClient(trust_env=False,) as internal:
                        metrics=(await internal.get(urls['payment']+'/metrics')).text
                        def metric(name):return float(next(line.split()[1] for line in metrics.splitlines() if line.startswith(name+' ')))
                        active=metric('lab_active_work');denied=metric('lab_capacity_denied_total')
                        logs=(Path(os.environ['LOG_DIR'])/'payment.jsonl').read_text()
                        successful=sum(float(line.split()[1]) for line in metrics.splitlines() if line.startswith('lab_requests_total{') and 'route="quotes"' in line and 'status="200"' in line)
                        row=[successful/(time.monotonic()-started),active,denied,float(logs.count('capacity_denied'))]
                        value=score(model,row);assert value<0
                        iid=str(uuid.uuid4());payload=json.dumps({'id':iid,'issued_at':time.time(),'score':value,'features':row}).encode()
                        signature=hmac.new(secret('alert_key').encode(),payload,hashlib.sha256).hexdigest()
                        r=await internal.post(urls['remediator']+'/alerts',content=payload,headers={'Content-Type':'application/json','X-Signature':signature})
                        assert r.status_code==202
                    for _ in range(80):
                        r=await c.get('/ops/status',headers=h);inc=r.json()['incidents'][0]
                        if inc['status'] in ('recovered','failed'):break
                        await asyncio.sleep(0.25)
                    assert inc['status']=='recovered',inc
                    # Flood remains active during the after-transaction check.
                    r=await c.post('/api/payments',headers={**h,'Idempotency-Key':str(uuid.uuid4())},json={'amount_cents':1,'recipient':'merchant'})
                    assert r.status_code==200
                    assert (await c.get('/api/accounts',headers=h)).json()['total_cents']==200000
                finally:
                    running=False
                    await asyncio.gather(*attackers,return_exceptions=True)
        asyncio.run(scenario())
    finally:
        for proc in processes:proc.terminate()
        for proc in processes:
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
        for log in logs:log.close()
