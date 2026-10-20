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
@pytest.mark.parametrize('suite',['chrono.test.js','components.test.js'])
def test_the_frontend_model_tests_pass(suite):
    done=subprocess.run(['node','--test',f'frontend/src/{suite}'],cwd=ROOT,capture_output=True,text=True,timeout=60)
    assert done.returncode==0,done.stdout[-1500:]+done.stderr[-500:]
def test_the_dashboard_shows_a_component_panel_from_independent_probes():
    """Sujet 3.1: observe the components. The dashboard must poll each independently (one down must not hide the
    others) and clear a transient error on success (defect fixed in phase 4)."""
    main=(ROOT/'frontend/src/main.jsx').read_text(encoding='utf-8')
    assert '<Components probes={probes}/>' in main                              # the panel is rendered
    assert 'Promise.all([probe(' in main and 'async function probe(' in main    # independent probes, not one all-or-nothing call
    assert "E(p.ok||o.ok||m.ok?''" in main                                      # a success clears the error banner
    assert 'try{data=await r.json();}catch{data={};}' in main                   # a non-JSON response shows the status, not a parse error
    for endpoint in ('/api/accounts','/ops/status','/ops/ml'): assert endpoint in main

def test_stages_that_share_a_timestamp_are_listed_in_the_order_of_the_chain(tmp_path,monkeypatch):
    # Coarse clocks (about 15 ms on Windows) give `detected` and `accepted` the same value: the order must not depend on the database.
    monkeypatch.setattr(remediator,'STORE',tmp_path/'incidents.sqlite')
    with remediator.connection() as c:
        # A FINISHED incident: the app's lifespan resumes interrupted ones (containing, verifying) and would rewrite their stages.
        c.execute('INSERT INTO incidents VALUES(?,?,?,?,?)',('same','recovered',5.0,5.0,'{}'))
        c.executemany('INSERT INTO stages VALUES(?,?,?)',[('same','recovered',5.0),('same','containing',5.0),('same','accepted',5.0),('same','detected',5.0),('same','mystery',5.0)])
    with TestClient(remediator.app) as client: stages=client.get('/status',headers=OPERATOR()).json()['incidents'][0]['stages']
    assert list(stages)==['detected','accepted','containing','recovered','mystery']
