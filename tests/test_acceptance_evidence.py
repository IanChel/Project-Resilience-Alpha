"""scripts/acceptance.py (carte W6): the evidence is usable for the PCA/PRA as written. Never run against a stack here:
the whole lab is simulated (a scripted clock and server)."""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import httpx
import pytest
ROOT=Path(__file__).resolve().parents[1]
def load():
    sys.path.insert(0,str(ROOT/'scripts'))
    spec=importlib.util.spec_from_file_location('acceptance',ROOT/'scripts/acceptance.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m
T0=1_000_000.0
class Lab:
    """A scripted lab. Time only moves when the observer sleeps. The attack starts at t=2: payments are refused from 2 to 8;
    the incident is detected at 2.8, accepted 3.0, contained 3.1, verified 6.9 and recovered 9.3 (stages as the remediator records them)."""
    def __init__(self,outcome='recovered',stages=True,config=True,ml_ok=True,witness=True,ban=None,attack=True):
        self.t=0.0; self.outcome=outcome; self.stages=stages; self.config=config; self.ml_ok=ml_ok; self.witness=witness; self.ban=ban; self.attack=attack; self.requests=[]
    # the clock the script sees
    def clock(self): return SimpleNamespace(monotonic=lambda:self.t,time=lambda:T0+self.t,sleep=self.sleep)
    def sleep(self,seconds): self.t+=seconds
    def incident(self):
        if not self.attack or self.t<3.0: return []
        status='accepted'
        for at,name in ((3.1,'containing'),(6.9,'verifying'),(9.3,self.outcome)):
            if self.t>=at: status=name
        stages={'detected':T0+2.8,'accepted':T0+3.0}
        for at,name in ((3.1,'containing'),(6.9,'verifying'),(9.3,self.outcome)):
            if self.t>=at: stages[name]=T0+at
        evidence={'ban':self.ban} if self.ban else {}
        if status=='recovered' and self.witness: evidence.update(transaction_id='tx-77',total_cents=200000)
        if status=='failed': evidence.update(error_type='RuntimeError',manual_review_required=True)
        inc={'id':'11111111-1111-4111-8111-111111111111','status':status,'created':T0+3.0,'updated':max(stages.values()),'evidence':json.dumps(evidence)}
        if self.stages: inc['stages']=stages
        return [inc]
    def handler(self,request):
        self.requests.append((request.method,request.url.path))
        path=request.url.path
        if path=='/api/payments':
            refused=self.attack and 2.0<=self.t<8.0
            return httpx.Response(503,json={'detail':'Simulated downstream capacity exhausted'}) if refused else httpx.Response(200,json={'transaction':{'id':f'tx-{self.t}'},'replayed':False})
        if path=='/ops/status': return httpx.Response(200,json={'incidents':self.incident() if self.t>0 else [],'now':T0+self.t})
        if path=='/api/accounts': return httpx.Response(200,json={'accounts':[],'transactions':[],'total_cents':200000})
        if path=='/ops/ml':
            if not self.ml_ok: return httpx.Response(502,text='bad gateway')
            return httpx.Response(200,json={'status':'monitoring','features':None,'score':0.1,**({'config':{'consecutive':3,'nu':0.03}} if self.config else {})})
        raise AssertionError('unexpected '+path)
def run(lab,monkeypatch,tmp_path,capsys,seconds=14):
    m=load()
    monkeypatch.setattr(m,'time',lab.clock()); monkeypatch.setattr(m,'login',lambda client,user:{'Authorization':'Bearer NOT-A-SECRET-token'})
    monkeypatch.setattr(m,'httpx',SimpleNamespace(Client=lambda **kw:httpx.Client(transport=httpx.MockTransport(lab.handler),**kw),HTTPError=httpx.HTTPError))
    monkeypatch.setattr(m,'code_version',lambda root=None:{'commit':'abc123','dirty':False}); monkeypatch.chdir(tmp_path)
    code=m.main(['--seconds',str(seconds)])
    files=sorted((tmp_path/'runtime'/'evidence').glob('acceptance-*.json'))
    return code,capsys.readouterr().out,(json.loads(files[-1].read_text()) if files else None)

def test_a_successful_run_carries_everything_the_pca_pra_needs(monkeypatch,tmp_path,capsys):
    code,out,ev=run(Lab(ban={'enabled':True,'eligible':['192.168.137.20'],'applied':['192.168.137.20']}),monkeypatch,tmp_path,capsys)
    s=ev['summary']; i=s['incident']
    assert code==0 and ev['passed'] is True and s['complete'] is True and s['missing']==[]
    assert [(x['name'],x['offset_s']) for x in i['steps']]==[('detected',0.0),('containing',0.3),('verifying',4.1),('recovered',6.5)]   # where the time goes
    assert [x['at'] for x in i['steps']]==[T0+2.8,T0+3.1,T0+6.9,T0+9.3]
    assert i['detection_to_recovered_s']==6.5 and i['within_target'] is True and i['target_s']==60 and i['status']=='recovered'
    assert s['witness']=={'verdict':'validated','transaction_id':'tx-77','total_cents':200000} and s['ledger_total_cents']==200000
    assert s['detector_config']=={'consecutive':3,'nu':0.03}                                  # without it the measurement is not reproducible
    assert s['code_version']=={'commit':'abc123','dirty':False} and s['ban']['applied']==['192.168.137.20']
    assert 'PASS' in out and 'detection -> recovered: 6.5 s' in out and 'complete: True' in out and 'INCOMPLETE' not in out
def test_the_user_visible_outage_is_measured_from_the_first_refusal_to_the_first_success(monkeypatch,tmp_path,capsys):
    _,_,ev=run(Lab(),monkeypatch,tmp_path,capsys); o=ev['summary']['user_visible_outage']
    assert o['first_refused_at']==T0+2.0 and o['first_ok_after_at']==T0+8.0 and o['seconds']==6.0
    # ...which is not the recovery time: the service is usable again after the chain's verifying step, before the witness is proven
    assert o['seconds']!=ev['summary']['incident']['detection_to_recovered_s']
def test_the_raw_observations_and_the_old_fields_are_still_there(monkeypatch,tmp_path,capsys):
    _,_,ev=run(Lab(),monkeypatch,tmp_path,capsys)
    assert {'observations','started_at','before','after','after_status','ledger','passed','summary'}<=set(ev) and len(ev['observations'])>=20
    assert any(o.get('payment_status')==503 for o in ev['observations'])
def test_a_failed_recovery_is_recorded_and_not_called_a_pass(monkeypatch,tmp_path,capsys):
    code,out,ev=run(Lab(outcome='failed'),monkeypatch,tmp_path,capsys)
    s=ev['summary']
    assert code==1 and ev['passed'] is False and 'FAIL' in out
    assert s['witness']['verdict']=='failed' and s['incident']['status']=='failed' and s['incident']['detection_to_recovered_s'] is None
    assert s['complete'] is False and 'witness_transaction_validated' in s['missing'] and 'stage:recovered' in s['missing']
def test_no_attack_means_no_incident_and_incomplete_evidence(monkeypatch,tmp_path,capsys):
    code,out,ev=run(Lab(attack=False),monkeypatch,tmp_path,capsys)
    s=ev['summary']
    assert code==1 and s['incident']['id'] is None and s['witness']['verdict']=='absent' and s['user_visible_outage']['seconds'] is None
    assert {'stage:detected','stage:containing','stage:verifying','stage:recovered','witness_transaction_validated'}<=set(s['missing']) and 'EVIDENCE INCOMPLETE' in out
def test_a_missing_detector_configuration_makes_the_evidence_incomplete_not_the_run_failed(monkeypatch,tmp_path,capsys):
    for lab in (Lab(config=False),Lab(ml_ok=False)):
        code,out,ev=run(lab,monkeypatch,tmp_path,capsys)
        assert code==0 and ev['passed'] is True                                               # the demonstration itself succeeded
        assert ev['summary']['detector_config'] is None and ev['summary']['missing']==['detector_config'] and ev['summary']['complete'] is False
        assert 'EVIDENCE INCOMPLETE, missing: detector_config' in out
def test_an_older_backend_without_stages_says_which_stages_it_cannot_give(monkeypatch,tmp_path,capsys):
    _,_,ev=run(Lab(stages=False),monkeypatch,tmp_path,capsys); s=ev['summary']
    assert ev['passed'] is True and s['incident']['detection_to_recovered_s'] is None and s['complete'] is False
    assert {'stage:detected','stage:containing','stage:verifying','stage:recovered'}<=set(s['missing'])
def test_a_ban_that_was_applied_is_reported_next_to_a_validated_witness(monkeypatch,tmp_path,capsys):
    _,_,ev=run(Lab(ban={'enabled':True,'eligible':['192.168.137.20'],'applied':['192.168.137.20'],'ttl_s':300}),monkeypatch,tmp_path,capsys)
    assert ev['summary']['ban']['applied']==['192.168.137.20'] and ev['summary']['witness']['verdict']=='validated'
def test_the_evidence_holds_no_credential(monkeypatch,tmp_path,capsys):
    _,out,ev=run(Lab(),monkeypatch,tmp_path,capsys)
    text=json.dumps(ev)+out
    assert 'NOT-A-SECRET-token' not in text and 'Bearer' not in text and 'password' not in text.lower()
def test_the_summary_is_a_pure_function_of_what_was_observed():
    m=load(); result={'observations':[{'at':1.0,'payment_status':200,'incidents':[]},{'at':2.0,'payment_status':503,'incidents':[]},{'at':3.0,'payment_status':200,'incidents':[]}],'ledger':{'total_cents':200000}}
    a=m.summarize(result,{'config':{'consecutive':2,'nu':0.05}},None); b=m.summarize(json.loads(json.dumps(result)),{'config':{'consecutive':2,'nu':0.05}},None)
    assert a==b and a['detector_config']=={'consecutive':2,'nu':0.05} and a['code_version'] is None
    assert a['user_visible_outage']['seconds']==1.0
def test_the_script_still_starts_from_a_command_line_without_side_effects_on_import():
    m=load()                                                                                  # importing must not run the observer
    assert callable(m.main) and m.STEPS==('detected','containing','verifying','recovered') and m.TARGET_S==60

def test_the_detector_really_exposes_the_configuration_it_runs_with(tmp_path,monkeypatch):
    import asyncio
    import joblib
    import numpy as np
    from services.detector import main as detector
    from services.detector.model import train_model
    rng=np.random.default_rng(1)
    joblib.dump(train_model(np.column_stack([rng.uniform(0.5,2,100),rng.integers(0,2,100),np.zeros(100),np.zeros(100)]),0.05),tmp_path/'model.joblib')
    monkeypatch.setenv('MODEL_DIR',str(tmp_path)); monkeypatch.setattr(detector,'state',{'status':'waiting_for_trained_model','features':None,'score':None,'config':{'consecutive':detector.CONSECUTIVE,'nu':None}})
    assert detector.state['config']=={'consecutive':3,'nu':None}                       # known before any model is loaded
    async def one_row(): return [1.0,0.0,0.0,0.0]
    async def stop(seconds): raise asyncio.CancelledError()
    monkeypatch.setattr(detector,'sample',one_row); monkeypatch.setattr(detector.asyncio,'sleep',stop); monkeypatch.setattr(detector,'emit',lambda *a,**k:None)
    with pytest.raises(asyncio.CancelledError): asyncio.run(detector.loop())
    assert detector.state['config']=={'consecutive':3,'nu':0.05} and detector.state['status']=='monitoring'
