"""Read the detector's own observation journal (LOG_DIR/detector.jsonl) over a time window.
Every scored observation is journaled as an `inference` event (score, the 4 features, alert counter),
so the data of an attack can be exported afterwards, exactly as the detector saw it.
  python -m services.detector.window export --start <time> --end <time> --out <file>
Times: epoch seconds, or ISO 8601 with an explicit offset (2026-10-20T14:32:00+02:00 or ...Z)."""
import argparse
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from services.detector.model import FEATURES
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
def read_inferences(start,end,log_dir=None):
    """Valid `inference` events with start <= ts <= end, in time order. Malformed lines are skipped."""
    path=journal(log_dir)
    if not path.is_file(): raise FileNotFoundError(f'Detector journal not found: {path}')
    found=[]
    for line in path.read_text(encoding='utf-8',errors='replace').splitlines():
        try: e=json.loads(line)
        except ValueError: continue
        if not isinstance(e,dict) or e.get('service')!='detector' or e.get('event')!='inference': continue
        ts,row,value=e.get('ts'),e.get('features'),e.get('score')
        try:
            if not (start<=ts<=end) or len(row)!=len(FEATURES): continue
            if not all(math.isfinite(float(v)) for v in [value,*row]): continue
        except (TypeError,ValueError): continue
        found.append({'ts':float(ts),'score':float(value),'row':[float(v) for v in row],'consecutive':e.get('consecutive')})
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
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub=p.add_subparsers(dest='command',required=True)
    e=sub.add_parser('export',help='write the observations of a window as a dataset file (same format as baseline.json)')
    e.add_argument('--start',required=True); e.add_argument('--end',required=True)
    e.add_argument('--out',type=Path,required=True,help='output file, e.g. /models/attack.json in the container')
    e.add_argument('--log-dir',default=None,help='default $LOG_DIR, /logs in the container')
    args=p.parse_args(argv)
    try:
        start,end=parse_time(args.start),parse_time(args.end)
        if end<=start: p.error('--end must be after --start')
        count=export(start,end,args.out,args.log_dir)
    except (ValueError,FileNotFoundError) as exc: sys.exit(f'Export failed: {exc}')
    print(f'{count} observations written: {args.out}')
if __name__=='__main__': main()
