import asyncio
import hashlib
import hmac
import json
import time
import uuid
from fastapi.testclient import TestClient
from services.common.security import secret

def signed(data):
    raw=json.dumps(data).encode()
    return {'content':raw,'headers':{'Content-Type':'application/json','X-Signature':hmac.new(secret('alert_key').encode(),raw,hashlib.sha256).hexdigest()}}
def test_signed_alert_dedup_and_replay_protection(tmp_path,monkeypatch):
    import services.remediator.main as r
    monkeypatch.setattr(r,'STORE',tmp_path/'incidents.sqlite')
    calls=[]
    async def recover(iid): calls.append(iid)
    monkeypatch.setattr(r,'recover',recover)
    with TestClient(r.app) as c:
        assert c.post('/alerts',json={}).status_code==403
        data={'id':str(uuid.uuid4()),'issued_at':time.time(),'score':-0.2,'features':[20,4,10,10]}
        assert c.post('/alerts',**signed(data)).status_code==202
        assert c.post('/alerts',**signed(data)).json()['duplicate']
        stale={**data,'id':str(uuid.uuid4()),'issued_at':time.time()-100}
        assert c.post('/alerts',**signed(stale)).status_code==422
        invalid={**data,'score':float('nan')}
        assert c.post('/alerts',**signed(invalid)).status_code==422
    assert calls==[data['id']]

def test_no_recovery_claim_when_business_verification_fails(tmp_path,monkeypatch):
    import services.remediator.main as r
    monkeypatch.setattr(r,'STORE',tmp_path/'incidents.sqlite')
    iid=str(uuid.uuid4())
    with r.connection() as c: c.execute('INSERT INTO incidents VALUES(?,?,?,?,?)',(iid,'accepted',time.time(),time.time(),'{}'))
    class Process:
        returncode=0
        async def communicate(self): return b'ok',b''
    async def fake_process(*args,**kwargs): return Process()
    async def failed_verification(iid): raise RuntimeError('Business transaction still fails')
    monkeypatch.setattr(r.asyncio,'create_subprocess_exec',fake_process)
    monkeypatch.setattr(r,'business_verify',failed_verification)
    asyncio.run(r.recover(iid))
    with r.connection() as c: assert c.execute('SELECT status FROM incidents').fetchone()['status']=='failed'
