"""GET /anomaly and GET /health (published as /ops/ml) read the same detector state."""
import re
from pathlib import Path
import numpy as np
from fastapi.testclient import TestClient
from services.detector import main as d
from services.detector.model import FEATURES, is_anomalous, score, train_model
ROOT=Path(__file__).resolve().parents[1]
def model():
    rng=np.random.default_rng(42)
    return train_model(np.column_stack([rng.uniform(0.5,2,100),rng.integers(0,2,100),np.zeros(100),np.zeros(100)]))
def monitoring(m,row): return {'status':'monitoring','features':dict(zip(FEATURES,row)),'score':score(m,row)}
def read_both(monkeypatch,state):
    monkeypatch.setattr(d,'state',state)
    c=TestClient(d.app)   # no `with`: the lifespan, and its Prometheus polling loop, is never started
    return c.get('/health').json(),c.get('/anomaly').json()

def test_no_model_is_false_and_says_why(monkeypatch):
    state={'status':'waiting_for_trained_model','features':None,'score':None}
    ops,an=read_both(monkeypatch,state)
    assert ops==state                                    # /ops/ml unchanged
    assert an=={'anomaly':False,'score':None,'status':'waiting_for_trained_model'}
def test_normal_traffic_is_false(monkeypatch):
    m=model(); state=monitoring(m,[1,0,0,0])
    ops,an=read_both(monkeypatch,state)
    assert ops==state
    assert an=={'anomaly':False,'score':state['score'],'status':'monitoring'} and state['score']>0
def test_attack_is_true_with_the_same_score(monkeypatch):
    m=model(); state=monitoring(m,[20,4,30,30])
    ops,an=read_both(monkeypatch,state)
    assert ops==state
    assert an=={'anomaly':True,'score':ops['score'],'status':'monitoring'} and an['score']<0
def test_novelty_without_capacity_rejections_is_not_an_anomaly(monkeypatch):
    m=model(); state=monitoring(m,[20,4,0,0])           # unusual load, nothing rejected
    ops,an=read_both(monkeypatch,state)
    assert an['score']<0 and an['anomaly'] is False     # same gate as the alert counter
def test_collection_error_never_reports_a_stale_score(monkeypatch):
    m=model(); state={**monitoring(m,[20,4,30,30]),'status':'telemetry_or_delivery_error'}
    ops,an=read_both(monkeypatch,state)
    assert ops['score']<0                                # /ops/ml keeps its raw state
    assert an=={'anomaly':False,'score':None,'status':'telemetry_or_delivery_error'}
def test_verdict_is_the_alert_rule_for_every_state(monkeypatch):
    m=model()
    for row in ([1,0,0,0],[20,4,0,0],[20,4,30,30],[0.5,1,5,0],[3,2,0,4]):
        ops,an=read_both(monkeypatch,monitoring(m,row))
        assert an['anomaly']==is_anomalous(ops['score'],list(ops['features'].values()))
def test_the_alert_loop_does_not_keep_its_own_copy_of_the_rule():
    text=(ROOT/'services/detector/main.py').read_text()
    # The loop and /anomaly go through the shared rule: no inline score test, no hard-coded repetition count.
    assert 'next_consecutive(consecutive,value,row)' in text and 'alert_due(consecutive,CONSECUTIVE)' in text
    assert not re.search(r'value\s*<\s*0',text) and not re.search(r'consecutive\s*>=\s*\d',text)
