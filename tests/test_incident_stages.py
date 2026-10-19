"""The dashboard chrono reads recorded stages: /ops/status must carry real, ordered timestamps."""
import asyncio
import hashlib
import hmac
import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import services.remediator.main as remediator
from services.common.security import issue, secret
ROOT=Path(__file__).resolve().parents[1]
def signed(data):
    raw=json.dumps(data).encode()
    return {'content':raw,'headers':{'Content-Type':'application/json','X-Signature':hmac.new(secret('alert_key').encode(),raw,hashlib.sha256).hexdigest()}}
@pytest.fixture
def flow(tmp_path,monkeypatch):
    monkeypatch.setattr(remediator,'STORE',tmp_path/'incidents.sqlite')
    class Ansible:
        returncode=0
        async def communicate(self): await asyncio.sleep(0.05); return b'ok',b''
    async def fake_exec(*a,**k): return Ansible()
    outcome={'fail':False}
    async def fake_verify(iid):
        await asyncio.sleep(0.05)
        if outcome['fail']: raise RuntimeError('witness transaction refused')
        return {'transaction_id':'tx-1','total_cents':200000}
    monkeypatch.setattr(remediator.asyncio,'create_subprocess_exec',fake_exec); monkeypatch.setattr(remediator,'business_verify',fake_verify)
    return outcome
def alert(issued_at): return {'id':str(uuid.uuid4()),'issued_at':issued_at,'score':-0.5,'features':[9,4,5,5]}
def wait_final(client,operator):
    for _ in range(80):
        body=client.get('/status',headers=operator).json()
        if body['incidents'][0]['status'] in ('recovered','failed'): return body
        time.sleep(0.05)
    raise AssertionError('recovery did not finish')
OPERATOR=lambda:{'Authorization':'Bearer '+issue('alice','operator')}

def test_a_recovery_records_every_stage_in_order_from_the_detector_alert_time(flow):
    detected=time.time()-2.0                                         # the detector raised the alert 2 s before it was received
    with TestClient(remediator.app) as client:
        assert client.post('/alerts',**signed(alert(detected))).status_code==202
        body=wait_final(client,OPERATOR())
    incident=body['incidents'][0]; stages=incident['stages']
    assert incident['status']=='recovered' and list(stages)==['detected','accepted','containing','verifying','recovered']
    assert stages['detected']==detected                              # exactly the signed issued_at, not the reception time
    times=list(stages.values()); assert times==sorted(times) and times[1]-times[0]>=1.9
    assert stages['recovered']-stages['detected']>=2.1               # the chrono includes the time before the remediator heard of it
    assert incident['updated']==stages['recovered'] and body['now']>=stages['recovered'] and abs(body['now']-time.time())<5
    json.dumps(body)
def test_a_failed_recovery_stops_at_failed_and_never_claims_recovered(flow):
    flow['fail']=True
    with TestClient(remediator.app) as client:
        assert client.post('/alerts',**signed(alert(time.time()))).status_code==202
        incident=wait_final(client,OPERATOR())['incidents'][0]
    assert incident['status']=='failed' and 'recovered' not in incident['stages']
    assert list(incident['stages'])==['detected','accepted','containing','verifying','failed']
    assert json.loads(incident['evidence'])['manual_review_required'] is True
def test_an_incident_older_than_the_stage_log_still_reports_sane_stages(tmp_path,monkeypatch):
    monkeypatch.setattr(remediator,'STORE',tmp_path/'incidents.sqlite')
    with remediator.connection() as c: c.execute('INSERT INTO incidents VALUES(?,?,?,?,?)',('old-incident','recovered',100.0,112.5,'{}'))
    with TestClient(remediator.app) as client: incident=client.get('/status',headers=OPERATOR()).json()['incidents'][0]
    assert incident['stages']=={'detected':100.0,'recovered':112.5}
def test_the_incidents_table_is_unchanged_and_stages_need_the_operator_role(tmp_path,monkeypatch):
    monkeypatch.setattr(remediator,'STORE',tmp_path/'incidents.sqlite')
    with remediator.connection() as c:
        assert [r[1] for r in c.execute('PRAGMA table_info(incidents)')]==['id','status','created','updated','evidence']   # positional inserts keep working
        assert [r[1] for r in c.execute('PRAGMA table_info(stages)')]==['incident_id','status','ts']
    with TestClient(remediator.app) as client:
        assert client.get('/status').status_code==401
        assert client.get('/status',headers={'Authorization':'Bearer '+issue('loadbot','loadbot')}).status_code==403
def test_the_stage_log_is_per_incident_and_replacing_a_stage_is_idempotent(tmp_path,monkeypatch):
    monkeypatch.setattr(remediator,'STORE',tmp_path/'incidents.sqlite')
    for iid in ('a','b'):
        with remediator.connection() as c: c.execute('INSERT INTO incidents VALUES(?,?,?,?,?)',(iid,'accepted',1.0,1.0,'{}'))
        remediator.update(iid,'containing',{}); remediator.update(iid,'containing',{})        # replayed after a restart
    with remediator.connection() as c:
        assert c.execute('SELECT COUNT(*) FROM stages WHERE status=?',('containing',)).fetchone()[0]==2

@pytest.mark.skipif(shutil.which('node') is None,reason='node is not installed')
def test_the_chrono_model_tests_pass():
    done=subprocess.run(['node','--test','frontend/src/chrono.test.js'],cwd=ROOT,capture_output=True,text=True,timeout=60)
    assert done.returncode==0,done.stdout[-1500:]+done.stderr[-500:]
