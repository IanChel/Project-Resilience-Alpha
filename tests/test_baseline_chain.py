"""collect_baseline -> baseline.json -> train -> model.joblib, offline (sampler faked)."""
import json
import joblib
import numpy as np
import pytest
from services.detector import collect_baseline, train
from services.detector.model import FEATURES, score

def normal_rows(n=90):
    rng=np.random.default_rng(3)
    return [[float(v) for v in r] for r in np.column_stack([rng.uniform(0.5,2,n),rng.integers(0,2,n),np.zeros(n),np.zeros(n)])]
def fake_sample(monkeypatch,rows):
    it=iter(rows)
    async def sample(): return next(it)
    monkeypatch.setattr(collect_baseline,'sample',sample)

def test_collect_then_train_writes_the_files_the_detector_reads(tmp_path,monkeypatch):
    monkeypatch.setenv('MODEL_DIR',str(tmp_path))
    fake_sample(monkeypatch,normal_rows())
    collect_baseline.main(['--interval','0'])
    data=json.loads((tmp_path/'baseline.json').read_text())
    assert data['features']==FEATURES and len(data['rows'])==90
    train.main([])
    # detector/main.py loads exactly MODEL_DIR/model.joblib
    model=joblib.load(tmp_path/'model.joblib')
    report=json.loads((tmp_path/'report.json').read_text())
    assert (report['n_train'],report['n_holdout'])==(72,18)
    assert report['holdout_false_positive_fraction']<=0.5
    assert score(model,[20,4,30,30])<0<score(model,[1,0,0,0])
    assert not list(tmp_path.glob('*.tmp'))

def test_collect_refuses_to_write_a_polluted_baseline(tmp_path,monkeypatch):
    monkeypatch.setenv('MODEL_DIR',str(tmp_path))
    rows=normal_rows(); rows[40][2]=3.0
    fake_sample(monkeypatch,rows)
    with pytest.raises(SystemExit): collect_baseline.main(['--interval','0'])
    assert not (tmp_path/'baseline.json').exists()

def test_collect_refuses_too_few_samples(tmp_path,monkeypatch):
    monkeypatch.setenv('MODEL_DIR',str(tmp_path))
    with pytest.raises(SystemExit) as exc: collect_baseline.main(['--samples','10'])
    assert exc.value.code==2

def test_train_refuses_missing_stale_or_polluted_baseline(tmp_path,monkeypatch):
    monkeypatch.setenv('MODEL_DIR',str(tmp_path))
    with pytest.raises(SystemExit): train.main([])
    path=tmp_path/'baseline.json'
    path.write_text(json.dumps({'features':['other'],'rows':normal_rows()}))
    with pytest.raises(SystemExit): train.main([])
    rows=normal_rows(); rows[10][3]=2.0
    path.write_text(json.dumps({'features':FEATURES,'rows':rows}))
    with pytest.raises(SystemExit): train.main([])
    assert not (tmp_path/'model.joblib').exists()

def test_train_accepts_an_explicit_baseline_path(tmp_path,monkeypatch):
    monkeypatch.setenv('MODEL_DIR',str(tmp_path/'models'))
    other=tmp_path/'elsewhere.json'
    other.write_text(json.dumps({'features':FEATURES,'rows':normal_rows()}))
    train.main(['--baseline',str(other)])
    assert (tmp_path/'models'/'model.joblib').exists()
