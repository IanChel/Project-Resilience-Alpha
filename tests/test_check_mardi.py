"""scripts/check_mardi.py : the M7 proof, with docker simulated. Each failure cause must point at its own reason."""
import copy
import importlib.util
import json
import re
import sys
import time
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
def load():
    sys.path.insert(0,str(ROOT/'scripts'))
    spec=importlib.util.spec_from_file_location('check_mardi',ROOT/'scripts/check_mardi.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m
REST={'anomaly':False,'score':0.31,'status':'monitoring'}
def report(**over):
    base={'window':{'start':1000.0,'end':1120.0,'length_s':120.0},'now':time.time(),
          'prometheus':{'quote_rate':{'peak':6.5,'samples':60},'active_work':{'peak':4.0,'samples':60},'denied_increase':120.0},
          'envelope':{'quote_rate_max':2.0,'active_work_max':1.0,'n':90},
          'detector':{'observations':58,'anomalous':20,'first_anomalous_s':4.1,'min_score':-1.9,'max_consecutive':3,'alerts_delivered':1,'first_alert_s':8.3}}
    for k,v in over.items(): base[k]={**base[k],**v} if isinstance(v,dict) and isinstance(base.get(k),dict) else v
    return base
def run(m,monkeypatch,tmp_path,capsys,now=REST,rep=None,exec_error=None,argv=('--last','120'),evidence=None):
    calls=[]
    def fake_probe(compose_file,service,url):
        calls.append(('probe',service,url)); return 200,json.dumps(now)
    def fake_compose(compose_file,*args):
        calls.append(args)
        if exec_error: raise m.Check(exec_error)
        return json.dumps(rep if rep is not None else report())+'\n'
    monkeypatch.setattr(m,'probe',fake_probe); monkeypatch.setattr(m,'compose',fake_compose)
    folder=evidence or tmp_path/'evidence'
    code=m.main([*argv,'--evidence-dir',str(folder)])
    proofs=sorted(folder.glob('m7-proof-*.json')) if folder.is_dir() else []
    return code,capsys.readouterr().out,calls,(json.loads(proofs[-1].read_text()) if proofs else None)

def test_everything_ok_exits_zero_and_writes_a_timestamped_proof(monkeypatch,tmp_path,capsys):
    m=load(); code,out,calls,proof=run(m,monkeypatch,tmp_path,capsys)
    assert code==0 and '5/5 verifications OK' in out and 'ECHEC' not in out and 'jalon M7 VALIDE' in out
    assert proof['passed'] is True and proof['milestone']=='M7' and re.fullmatch(r'\d{8}T\d{6}Z',proof['created_at'])
    assert [c['ok'] for c in proof['checks']]==[True]*4 and proof['report']['detector']['anomalous']==20 and proof['anomaly_now']==REST
    assert proof['window_args']==['--last','120'] and abs(proof['clock_skew_host_minus_container_s'])<5
    assert 'au-dessus de l\'enveloppe normale' in out and 'alertes livrees : 1' in out
def test_it_only_reads_and_asks_for_the_window_it_was_given(monkeypatch,tmp_path,capsys):
    m=load(); _,_,calls,_=run(m,monkeypatch,tmp_path,capsys,argv=('--start','2026-10-20T14:32:00+02:00','--end','2026-10-20T14:34:00+02:00'))
    execs=[c for c in calls if c[0]=='exec']
    assert len(execs)==1
    assert execs[0][-5:]==('report','--start','2026-10-20T14:32:00+02:00','--end','2026-10-20T14:34:00+02:00')
    assert {c[0] for c in calls}<={'probe','exec'}                          # never up/down/restart/stop
    text=(ROOT/'scripts/check_mardi.py').read_text()
    assert set(re.findall(r"compose\(ctx\['compose_file'\],\s*'([\w-]+)'",text))=={'exec'}
    assert not re.search(r"\b(POST|PUT|DELETE|PATCH)\b|[(,]\s*data=",text)
def test_window_is_required(monkeypatch,tmp_path,capsys):
    m=load()
    for argv in ([],['--start','1'],['--end','2']):
        with pytest.raises(SystemExit) as exc: m.main([*argv,'--evidence-dir',str(tmp_path)])
        assert exc.value.code==2
def test_no_model_is_reported_as_such(monkeypatch,tmp_path,capsys):
    m=load(); code,out,_,proof=run(m,monkeypatch,tmp_path,capsys,now={'anomaly':False,'score':None,'status':'waiting_for_trained_model'})
    assert code==1 and 'aucun modele charge (status waiting_for_trained_model)' in out and proof['passed'] is False
    assert [c['ok'] for c in proof['checks']][0] is False
def test_telemetry_error_points_at_the_missing_quote_series(monkeypatch,tmp_path,capsys):
    m=load(); code,out,_,_=run(m,monkeypatch,tmp_path,capsys,now={'anomaly':False,'score':None,'status':'telemetry_or_delivery_error'})
    assert code==1 and 'le detecteur ne mesure pas (status telemetry_or_delivery_error)' in out and 'lab_requests_total' in out
def test_anomaly_true_at_rest_fails_only_the_rest_check(monkeypatch,tmp_path,capsys):
    m=load(); code,out,_,proof=run(m,monkeypatch,tmp_path,capsys,now={'anomaly':True,'score':-0.8,'status':'monitoring'})
    assert code==1 and 'anomaly=true au repos' in out and [c['ok'] for c in proof['checks']]==[True,False,True,True]
@pytest.mark.parametrize('over,needle',[
    ({'prometheus':{'error':'ConnectError: prometheus unreachable'}},'Prometheus injoignable'),
    ({'prometheus':{'quote_rate':None,'active_work':None}},'aucune donnee sur la fenetre'),
    ({'prometheus':{'denied_increase':0.0}},'aucun rejet de capacite'),
    ({'prometheus':{'denied_increase':None}},'aucun rejet de capacite'),
    ({'prometheus':{'quote_rate':{'peak':1.5,'samples':9},'active_work':{'peak':1.0,'samples':9}}},"aucun pic au-dessus de l'enveloppe normale")])
def test_peak_failures_have_their_own_reason(monkeypatch,tmp_path,capsys,over,needle):
    m=load(); code,out,_,proof=run(m,monkeypatch,tmp_path,capsys,rep=report(**over))
    assert code==1 and needle in out and [c['ok'] for c in proof['checks']]==[True,True,False,True]
def test_without_a_baseline_envelope_only_rejections_are_checked(monkeypatch,tmp_path,capsys):
    m=load(); code,out,_,_=run(m,monkeypatch,tmp_path,capsys,rep=report(envelope=None))
    assert code==0 and 'enveloppe normale indisponible' in out
def test_a_peak_on_active_work_alone_is_enough(monkeypatch,tmp_path,capsys):
    m=load(); code,out,_,_=run(m,monkeypatch,tmp_path,capsys,rep=report(prometheus={'quote_rate':{'peak':1.0,'samples':9}}))
    assert code==0 and 'active_work 4 > 1' in out
@pytest.mark.parametrize('over,needle',[
    ({'observations':0,'anomalous':0},'aucune observation journalisee'),
    ({'anomalous':0,'min_score':-0.4},'aucune anormale (score minimal -0.400')])
def test_detection_failures_have_their_own_reason(monkeypatch,tmp_path,capsys,over,needle):
    m=load(); code,out,_,proof=run(m,monkeypatch,tmp_path,capsys,rep=report(detector=over))
    assert code==1 and needle in out and [c['ok'] for c in proof['checks']]==[True,True,True,False]
def test_no_alert_is_informative_not_a_failure(monkeypatch,tmp_path,capsys):
    m=load(); code,out,_,_=run(m,monkeypatch,tmp_path,capsys,rep=report(detector={'alerts_delivered':0,'first_alert_s':None}))
    assert code==0 and 'aucune (compteur sous le seuil de repetition)' in out
def test_container_down_fails_both_window_checks_once_and_still_writes_the_proof(monkeypatch,tmp_path,capsys):
    m=load(); code,out,calls,proof=run(m,monkeypatch,tmp_path,capsys,exec_error='docker compose exec a echoue : service detector is not running')
    assert code==1 and out.count('service detector is not running')==2
    assert len([c for c in calls if c[0]=='exec'])==1                      # remembered, not retried
    assert proof['passed'] is False and proof['report'] is None
def test_clock_skew_is_called_out(monkeypatch,tmp_path,capsys):
    m=load(); code,out,_,proof=run(m,monkeypatch,tmp_path,capsys,rep=report(now=time.time()-90))
    assert code==0 and 'ATTENTION : horloge hote et conteneur decalees' in out and proof['clock_skew_host_minus_container_s']>60
def test_unwritable_evidence_fails_the_last_step(monkeypatch,tmp_path,capsys):
    m=load(); blocker=tmp_path/'evidence'; blocker.write_text('a file, not a folder')
    code,out,_,_=run(m,monkeypatch,tmp_path,capsys,evidence=blocker)
    assert code==1 and 'preuve non ecrite' in out and '4/5 verifications OK' in out
def test_the_proof_contains_no_secret(monkeypatch,tmp_path,capsys):
    m=load(); _,_,_,proof=run(m,monkeypatch,tmp_path,capsys)
    assert not re.search(r'password|secret|token|key',json.dumps(proof),re.I)
