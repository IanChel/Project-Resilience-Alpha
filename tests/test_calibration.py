"""Configurable nu / consecutive, window export and the calibration tool (synthetic data, offline)."""
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import joblib
import numpy as np
import pytest
import yaml
from services.detector import train, window
from services.detector.model import (FEATURES, DEFAULT_CONSECUTIVE, DEFAULT_NU, consecutive_from_env, nu_from_env,
                                     replay_alerts, train_model)
ROOT=Path(__file__).resolve().parents[1]
def load_script():
    spec=importlib.util.spec_from_file_location('calibrate_detector',ROOT/'scripts/calibrate_detector.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m
def normal_rows(n,seed):
    rng=np.random.default_rng(seed)
    return [[float(v) for v in r] for r in np.column_stack([rng.uniform(0.5,2,n),rng.integers(0,2,n),np.zeros(n),np.zeros(n)])]
def attack_rows(n=20,quiet=0):
    return normal_rows(quiet,1)+[[25.0,4.0,12.0,12.0] for _ in range(n)]
def dataset(path,rows,**extra):
    path.write_text(json.dumps({'features':FEATURES,'rows':rows,**extra})); return path

# ---- configuration
def test_defaults_and_valid_values(monkeypatch):
    monkeypatch.delenv('DETECTOR_NU',raising=False); monkeypatch.delenv('DETECTOR_CONSECUTIVE',raising=False)
    assert nu_from_env()==DEFAULT_NU==0.02 and consecutive_from_env()==DEFAULT_CONSECUTIVE==3   # nu calibre le 20/10
    monkeypatch.setenv('DETECTOR_NU','0.08'); monkeypatch.setenv('DETECTOR_CONSECUTIVE','5')
    assert nu_from_env()==0.08 and consecutive_from_env()==5
    monkeypatch.setenv('DETECTOR_NU',''); monkeypatch.setenv('DETECTOR_CONSECUTIVE','')
    assert nu_from_env()==0.02 and consecutive_from_env()==3   # compose passes empty strings when unset -> the default
@pytest.mark.parametrize('raw',['0','-0.1','1.5','abc','nan'])
def test_invalid_nu_is_refused_not_defaulted(monkeypatch,raw):
    monkeypatch.setenv('DETECTOR_NU',raw)
    with pytest.raises(ValueError,match='DETECTOR_NU'): nu_from_env()
@pytest.mark.parametrize('raw',['0','-1','2.5','abc'])
def test_invalid_consecutive_is_refused_not_defaulted(monkeypatch,raw):
    monkeypatch.setenv('DETECTOR_CONSECUTIVE',raw)
    with pytest.raises(ValueError,match='DETECTOR_CONSECUTIVE'): consecutive_from_env()
def test_the_detector_reads_consecutive_at_startup(monkeypatch):
    from services.detector import main as d
    try:
        monkeypatch.setenv('DETECTOR_CONSECUTIVE','5')
        assert importlib.reload(d).CONSECUTIVE==5
        monkeypatch.setenv('DETECTOR_CONSECUTIVE','0')
        with pytest.raises(ValueError): importlib.reload(d)      # fails loudly, no silent fallback
    finally:
        monkeypatch.delenv('DETECTOR_CONSECUTIVE',raising=False); importlib.reload(d)
    assert d.CONSECUTIVE==3
def test_train_uses_nu_flag_then_env_and_records_it(tmp_path,monkeypatch):
    monkeypatch.setenv('MODEL_DIR',str(tmp_path)); dataset(tmp_path/'baseline.json',normal_rows(90,3))
    monkeypatch.delenv('DETECTOR_NU',raising=False)
    train.main([]); assert json.loads((tmp_path/'report.json').read_text())['nu']==0.02   # the calibrated default
    monkeypatch.setenv('DETECTOR_NU','0.08')
    train.main([]); assert json.loads((tmp_path/'report.json').read_text())['nu']==0.08
    assert joblib.load(tmp_path/'model.joblib')[-1].nu==0.08
    train.main(['--nu','0.02']); assert joblib.load(tmp_path/'model.joblib')[-1].nu==0.02   # flag beats env
    for bad in (['--nu','0'],['--nu','2']):
        with pytest.raises(SystemExit): train.main(bad)
def test_compose_keeps_shared_variables_and_adds_the_two_settings():
    env=yaml.safe_load((ROOT/'compose.yaml').read_text())['services']['detector']['environment']
    assert {k:env[k] for k in ('LOG_DIR','STATE_DIR','MODEL_DIR','HOME')}=={'LOG_DIR':'/logs','STATE_DIR':'/state','MODEL_DIR':'/models','HOME':'/tmp'}
    assert env['DETECTOR_NU']=='${DETECTOR_NU:-0.02}' and env['DETECTOR_CONSECUTIVE']=='${DETECTOR_CONSECUTIVE:-3}'
def test_every_variable_of_env_example_is_read_by_compose_or_code():
    names=[l.split('=')[0] for l in (ROOT/'.env.example').read_text().splitlines() if l and not l.startswith('#')]
    compose=(ROOT/'compose.yaml').read_text()
    assert names and all('${'+n in compose for n in names)

# ---- the one counter rule
def test_replay_alerts_matches_the_loop_rule():
    row_hot,row_cold=[5,4,3,3],[5,4,0,0]
    seq=[(-1,row_hot)]*3+[(-1,row_cold)]+[(-1,row_hot)]*2+[(0.5,row_hot)]+[(-1,row_hot)]*3
    assert replay_alerts(seq,3)=={'alerts':2,'first_alert_index':2}   # runs of 3, restarts after an alert, broken by cold/positive
    assert replay_alerts(seq,1)['first_alert_index']==0
    assert replay_alerts(seq,9)=={'alerts':0,'first_alert_index':None}
    assert replay_alerts([(-1,row_cold)]*5,3)['alerts']==0                  # gate: no rejection, no alert
    assert replay_alerts([(-1,row_cold)]*5,3,gated=False)=={'alerts':1,'first_alert_index':2}   # model and N alone

# ---- window export
def test_parse_time():
    assert window.parse_time('1700000000')==1700000000.0
    assert window.parse_time('2026-10-20T14:32:00+02:00')==window.parse_time('2026-10-20T12:32:00Z')
    for bad in ('2026-10-20T14:32:00','yesterday',''):
        with pytest.raises(ValueError): window.parse_time(bad)
def write_journal(tmp_path):
    good=lambda ts,v,row,c=0:{'ts':ts,'service':'detector','event':'inference','score':v,'features':row,'consecutive':c}
    lines=[json.dumps(good(100,0.4,[1,0,0,0])),'not json',json.dumps({'ts':105,'service':'detector','event':'alert_delivered'}),
           json.dumps(good(110,-0.9,[9,4,3,3],1)),json.dumps(good(112,-0.8,[9,4,4,4],2)),json.dumps(good(120,-0.7,[9,4,5,5],3)),
           json.dumps(good(130,0.5,[1,0,0,0])),json.dumps(good(111,'nan',[1,2,3,4])),json.dumps(good(113,-0.5,[1,2,3])),
           json.dumps({'ts':114,'service':'auth','event':'inference','score':-1,'features':[1,2,3,4]})]
    (tmp_path/'detector.jsonl').write_text('\n'.join(lines)+'\n'); return tmp_path
def test_export_keeps_only_valid_inferences_of_the_window(tmp_path):
    log=write_journal(tmp_path); out=tmp_path/'out'/'attack.json'
    assert window.export(105,125,out,log)==3
    data=json.loads(out.read_text())
    assert data['features']==FEATURES and data['rows']==[[9,4,3,3],[9,4,4,4],[9,4,5,5]] and data['timestamps']==[110,112,120]
    assert data['window']=={'start':105,'end':125} and data['scores']==[-0.9,-0.8,-0.7]
    assert not list(out.parent.glob('*.tmp'))
def test_export_refuses_an_empty_window_and_cli_errors_are_clear(tmp_path):
    log=write_journal(tmp_path)
    with pytest.raises(ValueError,match='No inference'): window.export(500,600,tmp_path/'x.json',log)
    with pytest.raises(SystemExit): window.main(['export','--start','200','--end','100','--out',str(tmp_path/'y.json'),'--log-dir',str(log)])
    with pytest.raises(SystemExit,match='no offset'): window.main(['export','--start','2026-10-20T14:00:00','--end','200','--out',str(tmp_path/'y.json'),'--log-dir',str(log)])
    with pytest.raises(SystemExit,match='journal not found'): window.main(['export','--start','1','--end','2','--out',str(tmp_path/'y.json'),'--log-dir',str(tmp_path/'none')])
    window.main(['export','--start','105','--end','125','--out',str(tmp_path/'ok.json'),'--log-dir',str(log)])
    assert (tmp_path/'ok.json').exists()

# ---- calibration tool
def result(nu,n,runs,gated,detected,delay,neg=0.05):
    return {'model':'candidate','nu':nu,'consecutive':n,'n_normal':200,'normal_negative_score_rate':neg,'fp_runs_ungated':runs,
            'fp_alerts_gated':gated,'detected':detected,'delay_s':delay}
def test_choose_prefers_zero_false_run_then_fastest_then_robust():
    m=load_script()
    rows=[result(0.03,1,5,0,True,2),                         # fastest but false runs: rejected
          result(0.03,3,0,0,True,6),result(0.05,2,0,0,True,4,neg=0.09),result(0.01,2,0,0,True,4,neg=0.02),   # tie on delay: lowest negative rate wins
          result(0.03,6,0,0,True,12),                        # too slow
          result(0.08,4,0,0,False,None)]                     # never detects
    best=m.choose(rows,10)
    assert (best['strict']['nu'],best['strict']['consecutive'])==(0.01,2)
    assert best['gate_only']['consecutive']==1               # the gate alone would allow the faster pair
def test_choose_reports_the_conflict_instead_of_deciding():
    m=load_script()
    rows=[result(0.03,1,4,0,True,2),result(0.03,5,0,0,True,14)]
    best=m.choose(rows,10)
    assert best['strict'] is None and best['fastest_zero_false_run']['delay_s']==14 and best['gate_only']['consecutive']==1
    assert m.choose([result(0.03,2,0,0,False,None)],10)=={'strict':None,'gate_only':None,'fastest_zero_false_run':None}
def test_delay_uses_timestamps_and_the_window_start_when_present():
    m=load_script()
    assert m.delay_seconds({'timestamps':None,'window':None},3,2.0)==6.0
    assert m.delay_seconds({'timestamps':[100,102,104,106],'window':None},2,2.0)==4.0
    assert m.delay_seconds({'timestamps':[100,102,104,106],'window':{'start':98}},2,2.0)==6.0
    assert m.delay_seconds({'timestamps':None,'window':None},None,2.0) is None
def run_tool(m,tmp_path,capsys,normal_n=200,attack=None,extra=()):
    base=dataset(tmp_path/'baseline.json',normal_rows(90,3)); atk=dataset(tmp_path/'attack.json',attack or attack_rows())
    args=['--baseline',str(base),'--attack',str(atk),'--out-dir',str(tmp_path/'evidence'),'--nu','0.01,0.03,0.08','--consecutive','1,2,3',*extra]
    if normal_n: args+=['--normal',str(dataset(tmp_path/'normal.json',normal_rows(normal_n,5)))]
    code=m.main(args); return code,capsys.readouterr().out,sorted((tmp_path/'evidence').glob('calibration-*.json'))
def test_tool_measures_writes_only_the_evidence_and_changes_nothing(tmp_path,capsys):
    m=load_script(); before=sorted(p.name for p in tmp_path.iterdir())
    code,out,evidence=run_tool(m,tmp_path,capsys)
    assert len(evidence)==1 and 'Evidence:' in out and ('PROPOSAL' in out)==(code==0)
    data=json.loads(evidence[0].read_text())
    assert len(data['results'])==3*3 and data['conclusive'] is True
    assert {(r['nu'],r['consecutive']) for r in data['results']}=={(nu,n) for nu in (0.01,0.03,0.08) for n in (1,2,3)}
    if data['proposal']:
        p=data['proposal']; assert p['fp_runs_ungated']==0 and p['detected'] and p['delay_s']<=10
    after=sorted(p.name for p in tmp_path.iterdir())
    assert set(after)-set(before)>={'evidence','baseline.json','attack.json','normal.json'} and set(after)-set(before)<={'evidence','baseline.json','attack.json','normal.json'}
    assert not list(tmp_path.rglob('*.joblib')) and not list(tmp_path.rglob('report.json'))
    assert data['inputs']['baseline']['sha256']==hashlib.sha256((tmp_path/'baseline.json').read_bytes()).hexdigest()
def test_short_normal_window_is_flagged_not_conclusive(tmp_path,capsys):
    m=load_script()
    code,out,evidence=run_tool(m,tmp_path,capsys,normal_n=0)       # falls back on the 18-point holdout
    data=json.loads(evidence[0].read_text())
    assert code==1 and data['conclusive'] is False and 'NOT conclusive' in out and any('NOT conclusive' in w for w in data['warnings'])
    assert data['inputs']['normal']['source']=='baseline holdout'
def test_attack_without_rejections_is_called_out(tmp_path,capsys):
    m=load_script()
    code,out,evidence=run_tool(m,tmp_path,capsys,attack=[[25.0,4.0,0.0,0.0]]*20)
    data=json.loads(evidence[0].read_text())
    assert code==1 and any('no capacity rejection' in w for w in data['warnings']) and not any(r['detected'] for r in data['results'])
def test_deployed_model_is_evaluated_as_a_reference_line(tmp_path,capsys):
    m=load_script(); model=tmp_path/'model.joblib'; joblib.dump(train_model(normal_rows(72,3),0.05),model)
    code,out,evidence=run_tool(m,tmp_path,capsys,extra=('--model',str(model)))
    data=json.loads(evidence[0].read_text())
    assert len(data['deployed'])==3 and {r['nu'] for r in data['deployed']}=={0.05} and 'deployed' in out
def test_the_tool_refuses_unusable_inputs(tmp_path,capsys):
    m=load_script()
    short=dataset(tmp_path/'short.json',normal_rows(20,3)); atk=dataset(tmp_path/'attack.json',attack_rows())
    with pytest.raises(SystemExit,match='at least'): m.main(['--baseline',str(short),'--attack',str(atk),'--out-dir',str(tmp_path/'e')])
    wrong=tmp_path/'wrong.json'; wrong.write_text(json.dumps({'features':['x'],'rows':[[1,2,3,4]]}))
    with pytest.raises(SystemExit,match='differ'): m.main(['--baseline',str(wrong),'--attack',str(atk),'--out-dir',str(tmp_path/'e')])
    polluted=normal_rows(90,3); polluted[3][2]=2.0
    with pytest.raises(SystemExit,match='refused'): m.main(['--baseline',str(dataset(tmp_path/'p.json',polluted)),'--attack',str(atk),'--out-dir',str(tmp_path/'e')])
    assert not (tmp_path/'e').exists()                                # nothing written on refusal
