"""SIEM (carte W4): the SOC follows one incident across services, not only isolated counts."""
import asyncio
import json
import re
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
import httpx
import pytest
import services.detector.main as detector
import services.remediator.main as remediator
from services.detector import soc
ROOT=Path(__file__).resolve().parents[1]
IID=str(uuid.uuid4())
def ev(*pairs): return [(ts,name) for ts,name in pairs]
def state(events,now=1000.0,iid=IID): return soc.chain(iid,events,now)

# ---- the verdict on one incident
def test_a_complete_recovery_is_recognised_and_timed_from_the_alert():
    s=state(ev((100.0,'alert_delivered'),(100.4,'containing'),(106.8,'verifying'),(114.2,'recovered')))
    assert s['state']=='recovered' and s['missing']==[] and s['seconds']==14.2 and s['seen']==['alert_delivered','containing','verifying','recovered']
    assert s['rule']=='incident_correlation' and s['incident_id']==IID and s['count']==1
def test_the_chain_is_judged_by_event_time_not_arrival_order():
    shuffled=ev((114.2,'recovered'),(100.0,'alert_delivered'),(106.8,'verifying'),(100.4,'containing'))
    assert state(shuffled)['state']=='recovered'
def test_a_failed_recovery_is_flagged_for_review():
    s=state(ev((100.0,'alert_delivered'),(100.4,'containing'),(104.0,'verifying'),(110.0,'failed')))
    assert s['state']=='failed' and s['seconds']==10.0 and s['seen'][-1]=='failed'
def test_an_alert_nobody_handled_is_the_silent_failure_a_count_cannot_see():
    assert state(ev((100.0,'alert_delivered')),now=105)['state']=='alert_pending'          # the remediator still has time
    lost=state(ev((100.0,'alert_delivered')),now=120)
    assert lost['state']=='alert_not_handled' and lost['missing']==['containing'] and lost['seconds'] is None
def test_a_recovery_that_never_finishes_is_stuck():
    started=ev((100.0,'alert_delivered'),(100.4,'containing'))
    assert state(started,now=150)['state']=='in_progress'
    stuck=state(started,now=200)
    assert stuck['state']=='stuck' and stuck['missing']==['verifying','recovered']
    assert state(started+ev((105.0,'verifying')),now=200)['missing']==['recovered']
def test_a_recovery_with_missing_or_misordered_stages_is_not_trusted():
    gap=state(ev((100.0,'alert_delivered'),(100.4,'containing'),(114.2,'recovered')))
    assert gap['state']=='chain_gap' and gap['missing']==['verifying']
    assert state(ev((100.0,'alert_delivered'),(110.0,'containing'),(105.0,'verifying'),(114.0,'recovered')))['state']=='out_of_order'
def test_stages_without_an_alert_are_reported():
    s=state(ev((100.4,'containing'),(114.2,'recovered')))
    assert s['state']=='no_alert' and s['missing']==['alert_delivered'] and s['seconds'] is None
def test_the_verdict_is_deterministic_and_serializable():
    events=ev((100.0,'alert_delivered'),(100.4,'containing'),(106.8,'verifying'),(114.2,'recovered'))
    assert state(events)==state(list(reversed(events))) and json.dumps(state(events))

# ---- the SOC journals transitions, not every cycle
def test_a_state_is_journaled_once_and_again_only_when_it_changes():
    memory={}; a={'incident_id':'i1','state':'in_progress'}
    assert soc.changed(a,memory) is True and soc.changed(a,memory) is False
    assert soc.changed({**a,'state':'recovered'},memory) is True and soc.changed({**a,'state':'recovered'},memory) is False
    assert soc.changed({'incident_id':'i2','state':'recovered'},memory) is True
    for n in range(80): soc.changed({'incident_id':f'x{n}','state':'s'},memory)
    assert len(memory)<=50
def test_the_loop_emits_a_correlation_once_but_every_rule_signal(monkeypatch):
    cycles=[0]; emitted=[]
    corr={'rule':'incident_correlation','incident_id':'i1','state':'in_progress','count':1,'window':'15m'}
    rule={'rule':'capacity_pressure','count':9,'window':'30s'}
    async def fake_signals(): return [rule,corr]
    async def fake_sleep(seconds):
        cycles[0]+=1
        if cycles[0]>=3: raise asyncio.CancelledError()
    monkeypatch.setattr(detector,'signals',fake_signals); monkeypatch.setattr(detector.asyncio,'sleep',fake_sleep)
    monkeypatch.setattr(detector,'emit',lambda service,event,**f:emitted.append(f['rule']))
    with pytest.raises(asyncio.CancelledError): asyncio.run(detector.soc_loop())
    assert emitted.count('capacity_pressure')==3 and emitted.count('incident_correlation')==1

# ---- against Loki (simulated)
class Reply:
    def __init__(self,payload): self.payload=payload
    def raise_for_status(self): pass
    def json(self): return self.payload
def stream(*lines): return {'status':'success','data':{'result':[{'values':[[str(int(l['ts']*1e9)),json.dumps(l)] for l in lines]}]}}
class FakeLoki:
    def __init__(self,alerts,stages,rule_count=0,fail_range=False): self.alerts=alerts; self.stages=stages; self.rule_count=rule_count; self.fail_range=fail_range; self.queries=[]
    async def __aenter__(self): return self
    async def __aexit__(self,*a): return False
    async def get(self,url,params=None):
        q=params['query']; self.queries.append(q)
        if url.endswith('/query'): return Reply({'status':'success','data':{'result':[{'value':[0,str(self.rule_count)]}] if self.rule_count else []}})
        if self.fail_range: raise httpx.ConnectError('loki unreachable')
        if 'alert_delivered' in q: return Reply(stream(*self.alerts))
        iid=q.split('"')[-2]; return Reply(stream(*[s for s in self.stages if s.get('incident_id')==iid]))
def alert(iid,ts): return {'ts':ts,'service':'detector','event':'alert_delivered','incident_id':iid}
def stage(iid,ts,name): return {'ts':ts,'service':'remediator','event':name,'incident_id':iid}
def test_correlations_follow_each_incident_through_the_services():
    a,b=str(uuid.uuid4()),str(uuid.uuid4()); now=1000.0
    loki=FakeLoki([alert(a,100.0),alert(b,990.0)],[stage(a,100.4,'containing'),stage(a,106.8,'verifying'),stage(a,114.2,'recovered'),stage(b,990.5,'containing')])
    result={s['incident_id']:s for s in asyncio.run(soc.correlations(loki,now))}
    assert result[a]['state']=='recovered' and result[a]['seconds']==14.2
    assert result[b]['state']=='in_progress' and result[b]['missing']==['verifying','recovered']
def test_only_validated_ids_reach_a_log_query():
    evil='x" or {service=~".+"} |= "'
    loki=FakeLoki([alert(evil,100.0),{'ts':101.0,'service':'detector','event':'alert_delivered'},alert(IID,102.0)],[])
    out=asyncio.run(soc.correlations(loki,1000.0))
    assert [s['incident_id'] for s in out]==[IID]
    assert all(evil not in q for q in loki.queries) and any(IID in q for q in loki.queries)
def test_at_most_three_incidents_are_followed():
    ids=[str(uuid.uuid4()) for _ in range(6)]
    out=asyncio.run(soc.correlations(FakeLoki([alert(i,100.0+n) for n,i in enumerate(ids)],[]),1000.0))
    assert [s['incident_id'] for s in out]==ids[::-1][:3]                                  # the latest three, newest first
def test_a_failing_correlation_does_not_hide_the_rule_signals(monkeypatch):
    monkeypatch.setattr(soc,'httpx',SimpleNamespace(AsyncClient=lambda **kw:FakeLoki([],[],rule_count=7,fail_range=True)))
    out=asyncio.run(soc.signals())
    assert {s['rule'] for s in out}=={'repeated_failed_logins','capacity_pressure','ml_alert_delivered','waf_audit_activity','incident_correlation'}
    assert [s for s in out if s['rule']=='incident_correlation'][0]['state']=='unavailable'
    rules=asyncio.run(soc.signals(correlate=False))
    assert {s['rule'] for s in rules}=={'repeated_failed_logins','capacity_pressure','ml_alert_delivered','waf_audit_activity'}   # unchanged without correlation

# ---- the SOC expects exactly what the services emit
def test_the_events_the_soc_expects_are_the_ones_the_services_really_emit(tmp_path,monkeypatch):
    monkeypatch.setattr(remediator,'STORE',tmp_path/'incidents.sqlite'); captured=[]
    class Ansible:
        returncode=0
        async def communicate(self): return b'ok',b''
    async def fake_exec(*a,**k): return Ansible()
    async def fake_verify(i): return {'transaction_id':'tx','total_cents':200000}
    monkeypatch.setattr(remediator.asyncio,'create_subprocess_exec',fake_exec); monkeypatch.setattr(remediator,'business_verify',fake_verify)
    monkeypatch.setattr(remediator,'emit',lambda service,event,**f:captured.append((service,event,f.get('incident_id'))))
    iid=str(uuid.uuid4())
    with remediator.connection() as c: c.execute('INSERT INTO incidents VALUES(?,?,?,?,?)',(iid,'accepted',1.0,1.0,'{}'))
    asyncio.run(remediator.recover(iid))
    assert [e for s,e,i in captured if i==iid]==['containing','verifying','recovered'] and all(s=='remediator' for s,e,i in captured)
    source=(ROOT/'services/detector/main.py').read_text()
    assert "emit('detector','alert_delivered',incident_id=" in source                      # the alert event carries the same id
    events=[(100.0,'alert_delivered')]+[(100.0+n,e) for n,(s,e,i) in enumerate(captured,1)]
    assert soc.chain(iid,events,1000.0)['state']=='recovered'

def test_the_dashboard_knows_every_state_the_correlation_can_produce():
    labels=set(re.findall(r"^\s{2}(\w+):\{text:",(ROOT/'frontend/src/chrono.js').read_text(encoding='utf-8'),re.M))
    scenarios=[ev((100.0,'alert_delivered'),(100.4,'containing'),(106.8,'verifying'),(114.2,'recovered')),ev((100.0,'alert_delivered'),(110.0,'failed')),
               ev((100.0,'alert_delivered'),(100.4,'containing')),ev((100.0,'alert_delivered')),ev((100.4,'containing'),(114.2,'recovered')),
               ev((100.0,'alert_delivered'),(100.4,'containing'),(114.2,'recovered')),ev((100.0,'alert_delivered'),(110.0,'containing'),(105.0,'verifying'),(114.0,'recovered'))]
    produced={soc.chain(IID,s,now)['state'] for s in scenarios for now in (101.0,120.0,300.0)}|{'unavailable'}
    assert produced<=labels,produced-labels                    # nothing the SOC can say is left without a screen label
    assert labels<=produced|{'unavailable'},labels-produced     # and no label for a state that does not exist
