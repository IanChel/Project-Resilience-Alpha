"""services.detector.window report : what the detector saw and what Prometheus measured over a window."""
import json
import time
import pytest
from services.detector import window
def inference(ts,score,row,consecutive=0):
    return {'ts':ts,'service':'detector','event':'inference','score':score,'features':row,'consecutive':consecutive}
def journal(tmp_path,*extra):
    lines=[inference(100,0.4,[1,0,0,0]),                                   # before the window
           inference(110,0.3,[1,1,0,0]),                                   # normal
           inference(112,-0.9,[9,4,0,0]),                                  # novelty but no rejection: not anomalous
           inference(114,-0.9,[9,4,3,3],1),inference(116,-0.8,[9,4,4,4],2),inference(118,-0.7,[9,4,5,5],3),
           {'ts':118.5,'service':'detector','event':'alert_delivered','incident_id':'abc'},
           {'ts':119,'service':'auth','event':'alert_delivered','incident_id':'other-service'},
           inference(130,0.5,[1,0,0,0]),*extra]                            # after the window
    (tmp_path/'detector.jsonl').write_text('\n'.join(json.dumps(l) for l in lines)+'\nnot json\n'); return tmp_path
def matrix(*values): return {'status':'success','data':{'result':[{'values':[[i,str(v)] for i,v in enumerate(values)]}]}}
def vector(v): return {'status':'success','data':{'result':[{'value':[0,str(v)]}] if v is not None else []}}
def fake_prometheus(rate,active,denied,calls=None):
    def get(path,params):
        if calls is not None: calls.append((path,params))
        if path.endswith('/query'): return vector(denied)
        return matrix(*rate) if 'lab_requests_total' in params['query'] else matrix(*active)
    return get

def test_summarize_counts_anomalies_with_the_alert_rule():
    inferences=[{'ts':110,'score':0.3,'row':[1,1,0,0],'consecutive':0},{'ts':112,'score':-0.9,'row':[9,4,0,0],'consecutive':0},
                {'ts':114,'score':-0.9,'row':[9,4,3,3],'consecutive':1},{'ts':118,'score':-0.7,'row':[9,4,5,5],'consecutive':3}]
    s=window.summarize(inferences,[{'ts':118.5,'incident_id':'abc'}],start=108)
    assert s=={'observations':4,'anomalous':2,'first_anomalous_s':6.0,'min_score':-0.9,'max_consecutive':3,'alerts_delivered':1,'first_alert_s':10.5}
    assert window.summarize([],[],0)=={'observations':0,'anomalous':0,'first_anomalous_s':None,'min_score':None,'max_consecutive':0,'alerts_delivered':0,'first_alert_s':None}
def test_alerts_are_read_from_the_detector_journal_only(tmp_path):
    assert window.read_alerts(105,125,journal(tmp_path))==[{'ts':118.5,'incident_id':'abc'}]
    assert window.read_alerts(120,125,tmp_path)==[]
def test_prometheus_peaks_denials_and_ignored_nan():
    calls=[]; got=window.prometheus_summary(1000,1120,fake_prometheus([0.5,6.5,'NaN',3],[1,4,4],118.0,calls))
    assert got=={'quote_rate':{'peak':6.5,'samples':3},'active_work':{'peak':4.0,'samples':3},'denied_increase':118.0}
    instant=[p for path,p in calls if path.endswith('/query')][0]
    assert 'increase(lab_capacity_denied_total[120s])' in instant['query'] and instant['time']==1120   # the whole window, evaluated at its end
def test_prometheus_without_data_or_unreachable_is_explicit():
    assert window.prometheus_summary(0,60,fake_prometheus([],[],None))=={'quote_rate':None,'active_work':None,'denied_increase':None}
    def down(path,params): raise ConnectionError('prometheus:9090 unreachable')
    assert window.prometheus_summary(0,60,down)=={'error':'ConnectionError: prometheus:9090 unreachable'}
    assert 'error' in window.prometheus_summary(0,60,lambda p,q:{'status':'error'})
def test_baseline_envelope(tmp_path):
    assert window.baseline_envelope(tmp_path) is None                       # no baseline: no envelope, no crash
    (tmp_path/'baseline.json').write_text(json.dumps({'rows':[[1.2,0,0,0],[2.5,1,0,0],[0.4,1,0,0]]}))
    assert window.baseline_envelope(tmp_path)=={'quote_rate_max':2.5,'active_work_max':1,'n':3}
def test_report_assembles_the_window(tmp_path):
    log=journal(tmp_path); (tmp_path/'baseline.json').write_text(json.dumps({'rows':[[1.2,0,0,0],[2.5,1,0,0]]}))
    report=window.build_report(105,125,log_dir=log,model_dir=tmp_path,get=fake_prometheus([1,6],[1,4],50.0))
    assert report['window']=={'start':105,'end':125,'length_s':20}
    assert report['detector']['observations']==5 and report['detector']['anomalous']==3 and report['detector']['alerts_delivered']==1
    assert report['prometheus']['denied_increase']==50.0 and report['envelope']['active_work_max']==1
    assert abs(report['now']-time.time())<5
    json.dumps(report)                                                       # serializable as is
def test_cli_report_last_start_end_and_errors(tmp_path,monkeypatch,capsys):
    log=journal(tmp_path)
    monkeypatch.setattr(window,'prometheus_summary',lambda s,e,get=None:{'quote_rate':None,'active_work':None,'denied_increase':None})
    window.main(['report','--start','105','--end','125','--log-dir',str(log)])
    assert json.loads(capsys.readouterr().out)['detector']['anomalous']==3
    window.main(['report','--last','60','--log-dir',str(log)])
    out=json.loads(capsys.readouterr().out); assert out['window']['length_s']==60 and out['detector']['observations']==0   # relative to NOW: the fixture is old
    for bad in (['report','--log-dir',str(log)],['report','--last','-5','--log-dir',str(log)],['report','--start','9','--end','3','--log-dir',str(log)]):
        with pytest.raises(SystemExit) as exc: window.main(bad)
        assert exc.value.code==2
    with pytest.raises(SystemExit,match='journal not found'): window.main(['report','--last','60','--log-dir',str(tmp_path/'none')])
def test_report_is_read_only(tmp_path,monkeypatch):
    log=journal(tmp_path); snapshot=lambda:{p.name:p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}   # conftest also creates a secrets/ folder here
    before=snapshot()
    monkeypatch.setattr(window,'prometheus_summary',lambda s,e,get=None:{})
    window.build_report(105,125,log_dir=log,model_dir=tmp_path)
    assert snapshot()==before and set(before)=={'detector.jsonl'}
