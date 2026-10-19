"""Collect a normal-traffic baseline from live Prometheus and Loki into baseline.json.
Run while clean traffic flows (scripts/normal_traffic.py), never during an attack.
Then train: python -m services.detector.train"""
import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from services.detector.model import FEATURES, MIN_BASELINE_SAMPLES
from services.detector.telemetry import sample
def default_path():
    return Path(os.getenv('MODEL_DIR','/models'))/'baseline.json'
async def collect(samples,interval,out):
    rows=[]
    for i in range(samples):
        # An unavailable series raises: no fallback value is ever invented.
        rows.append(await sample())
        print(f'live baseline {i+1}/{samples}',flush=True)
        await asyncio.sleep(interval)
    if any(r[2] or r[3] for r in rows):
        raise ValueError('Baseline contains capacity rejections (overload or attack): nothing written')
    out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_suffix('.tmp')
    tmp.write_text(json.dumps({'features':FEATURES,'rows':rows,'collected_at':time.time()}))
    tmp.replace(out)
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--samples',type=int,default=90,help=f'number of observations (>= {MIN_BASELINE_SAMPLES}, default 90)')
    p.add_argument('--interval',type=float,default=2.0,help='seconds between observations (default 2)')
    p.add_argument('--out',type=Path,default=None,help='output file (default $MODEL_DIR/baseline.json, /models in the container)')
    args=p.parse_args(argv)
    if args.samples<MIN_BASELINE_SAMPLES: p.error(f'--samples must be at least {MIN_BASELINE_SAMPLES} (training needs 60 rows after the 80/20 split)')
    if args.interval<0: p.error('--interval must not be negative')
    out=args.out or default_path()
    try: asyncio.run(collect(args.samples,args.interval,out))
    except (ValueError,RuntimeError) as exc: sys.exit(f'Collection failed: {exc}')
    print(f'Baseline written: {out}')
if __name__=='__main__': main()
