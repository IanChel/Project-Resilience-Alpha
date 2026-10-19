"""Read the detector's own observation journal (LOG_DIR/detector.jsonl) over a time window.
Every scored observation is journaled as an `inference` event (score, the 4 features, alert counter),
so what happened during an attack can be read back afterwards, exactly as the detector saw it.
  python -m services.detector.window export --start <time> --end <time> --out <file>
  python -m services.detector.window report (--start <time> --end <time> | --last <seconds>)
`export` writes the observations as a dataset (calibration); `report` prints a JSON summary of the window
(Prometheus peaks, anomalous observations, alerts) used by scripts/check_mardi.py. Read-only.
Times: epoch seconds, or ISO 8601 with an explicit offset (2026-10-20T14:32:00+02:00 or ...Z)."""
import argparse
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from services.detector.model import FEATURES, is_anomalous
from services.detector.telemetry import PROM, QUERIES
def parse_time(text):
    try: return float(text)
    except ValueError: pass
    try: moment=datetime.fromisoformat(str(text).replace('Z','+00:00'))
    except ValueError: raise ValueError(f'Unreadable time {text!r}: use epoch seconds or ISO 8601 such as 2026-10-20T14:32:00+02:00') from None
    # The host and the container are not in the same time zone: a naive time would silently shift the window.
    if moment.tzinfo is None: raise ValueError(f'Time {text!r} has no offset: add Z or +HH:MM (or give epoch seconds)')
    return moment.timestamp()
def journal(log_dir=None):
    return Path(log_dir or os.getenv('LOG_DIR','/logs'))/'detector.jsonl'
def read_events(log_dir=None):
    """Every well-formed detector event of the journal. Malformed lines are skipped."""
    path=journal(log_dir)
    if not path.is_file(): raise FileNotFoundError(f'Detector journal not found: {path}')
    for line in path.read_text(encoding='utf-8',errors='replace').splitlines():
        try: e=json.loads(line)
        except ValueError: continue
        if isinstance(e,dict) and e.get('service')=='detector': yield e
def read_inferences(start,end,log_dir=None):
    """Valid `inference` events with start <= ts <= end, in time order."""
    found=[]
    for e in read_events(log_dir):
        if e.get('event')!='inference': continue
        ts,row,value=e.get('ts'),e.get('features'),e.get('score')
        try:
            if not (start<=ts<=end) or len(row)!=len(FEATURES): continue
            if not all(math.isfinite(float(v)) for v in [value,*row]): continue
        except (TypeError,ValueError): continue
        found.append({'ts':float(ts),'score':float(value),'row':[float(v) for v in row],'consecutive':e.get('consecutive')})
    return sorted(found,key=lambda x:x['ts'])
def read_alerts(start,end,log_dir=None):
    """`alert_delivered` events inside the window: an alert reached the remediator."""
    found=[]
    for e in read_events(log_dir):
        try:
            if e.get('event')=='alert_delivered' and start<=e['ts']<=end: found.append({'ts':float(e['ts']),'incident_id':e.get('incident_id')})
        except (KeyError,TypeError,ValueError): continue
    return sorted(found,key=lambda x:x['ts'])
def export(start,end,out,log_dir=None):
    events=read_inferences(start,end,log_dir)
    if not events:
        raise ValueError('No inference journaled in this window: detector stopped, no model loaded (status waiting_for_trained_model), or wrong window/clock')
    out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_suffix('.tmp')
    tmp.write_text(json.dumps({'features':FEATURES,'rows':[e['row'] for e in events],'timestamps':[e['ts'] for e in events],
                               'scores':[e['score'] for e in events],'window':{'start':start,'end':end},
                               'source':'detector.jsonl','collected_at':time.time()}))
    tmp.replace(out)
    return len(events)
def summarize(inferences,alerts,start):
    """What the detector saw in the window. `anomalous` uses the same rule as the alert counter and GET /anomaly."""
    anomalous=[e for e in inferences if is_anomalous(e['score'],e['row'])]
    seen=[e['consecutive'] for e in inferences if isinstance(e['consecutive'],int)]
    return {'observations':len(inferences),'anomalous':len(anomalous),
            'first_anomalous_s':round(anomalous[0]['ts']-start,2) if anomalous else None,
            'min_score':min((e['score'] for e in inferences),default=None),'max_consecutive':max(seen,default=0),
            'alerts_delivered':len(alerts),'first_alert_s':round(alerts[0]['ts']-start,2) if alerts else None}
def baseline_envelope(model_dir=None):
    """Highest quote_rate and active_work of the clean baseline: the normal envelope an attack must exceed."""
    path=Path(model_dir or os.getenv('MODEL_DIR','/models'))/'baseline.json'
    try: rows=json.loads(path.read_text())['rows']
    except (OSError,ValueError,KeyError): return None
    return {'quote_rate_max':max(r[0] for r in rows),'active_work_max':max(r[1] for r in rows),'n':len(rows)} if rows else None
def http_get(path,params):
    import httpx
    with httpx.Client(trust_env=False,timeout=5) as c:
        r=c.get(PROM+path,params=params); r.raise_for_status(); return r.json()
def peak(get,query,start,end):
    data=get('/api/v1/query_range',{'query':query,'start':start,'end':end,'step':2})
    if data.get('status')!='success': raise RuntimeError('Prometheus query failed')
    values=[float(v) for series in data['data']['result'] for _,v in series['values'] if math.isfinite(float(v))]
    return {'peak':max(values),'samples':len(values)} if values else None
def prometheus_summary(start,end,get=http_get):
    """Peaks over the window of the detector's own inputs (quote rate, active work) and the rejections counted."""
    try:
        data=get('/api/v1/query',{'query':f'sum(increase(lab_capacity_denied_total[{max(int(end-start),1)}s]))','time':end})
        result=data['data']['result']
        return {'quote_rate':peak(get,QUERIES[0],start,end),'active_work':peak(get,QUERIES[1],start,end),
                'denied_increase':float(result[0]['value'][1]) if result else None}
    except Exception as exc: return {'error':f'{type(exc).__name__}: {exc}'}
def build_report(start,end,log_dir=None,model_dir=None,get=http_get):
    return {'window':{'start':start,'end':end,'length_s':round(end-start,2)},'now':time.time(),
            'prometheus':prometheus_summary(start,end,get),'envelope':baseline_envelope(model_dir),
            'detector':summarize(read_inferences(start,end,log_dir),read_alerts(start,end,log_dir),start)}
def window_bounds(p,args):
    if args.last is not None:
        if args.last<=0: p.error('--last must be positive')
        now=time.time(); return now-args.last,now
    if not (args.start and args.end): p.error('give --start and --end, or --last')
    start,end=parse_time(args.start),parse_time(args.end)
    if end<=start: p.error('--end must be after --start')
    return start,end
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub=p.add_subparsers(dest='command',required=True)
    e=sub.add_parser('export',help='write the observations of a window as a dataset file (same format as baseline.json)')
    e.add_argument('--start',required=True); e.add_argument('--end',required=True)
    e.add_argument('--out',type=Path,required=True,help='output file, e.g. /models/attack.json in the container')
    r=sub.add_parser('report',help='print a JSON summary of a window (read-only)')
    r.add_argument('--start'); r.add_argument('--end'); r.add_argument('--last',type=float,help='the last N seconds, by the container clock')
    for s in (e,r): s.add_argument('--log-dir',default=None,help='default $LOG_DIR, /logs in the container')
    args=p.parse_args(argv)
    try:
        start,end=window_bounds(p,args) if args.command=='report' else (parse_time(args.start),parse_time(args.end))
        if args.command=='export':
            if end<=start: p.error('--end must be after --start')
            print(f'{export(start,end,args.out,args.log_dir)} observations written: {args.out}')
        else: print(json.dumps(build_report(start,end,args.log_dir)))
    except (ValueError,FileNotFoundError) as exc: sys.exit(f'{args.command.capitalize()} failed: {exc}')
if __name__=='__main__': main()
