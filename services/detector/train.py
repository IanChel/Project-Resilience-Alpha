"""Train the detector on a baseline file written by services.detector.collect_baseline.
Run on a clean normal-traffic baseline, never during the attack."""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
import joblib
from services.detector.model import train_model, FEATURES, MIN_BASELINE_SAMPLES, score
def main(argv=None):
    folder=Path(os.getenv('MODEL_DIR','/models'))
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--baseline',type=Path,default=folder/'baseline.json',
                   help='baseline file to read (default $MODEL_DIR/baseline.json, /models in the container)')
    path=p.parse_args(argv).baseline
    if not path.is_file(): sys.exit(f'Baseline not found: {path}. Collect it first: python -m services.detector.collect_baseline')
    raw=path.read_bytes()
    data=json.loads(raw)
    if data.get('features')!=FEATURES: sys.exit(f'Baseline features {data.get("features")} do not match the detector {FEATURES}: collect it again')
    rows=data['rows']
    if len(rows)<MIN_BASELINE_SAMPLES: sys.exit(f'Baseline has {len(rows)} observations, at least {MIN_BASELINE_SAMPLES} required')
    cut=int(len(rows)*0.8)
    try: model=train_model(rows[:cut])
    except ValueError as exc: sys.exit(f'Training refused: {exc}')
    holdout=[score(model,r) for r in rows[cut:]]
    folder.mkdir(parents=True,exist_ok=True)
    report={'source':'baseline file '+str(path)+' (live Prometheus and Loki at collection; normal traffic only)',
            'collected_at':data.get('collected_at'),'n_train':cut,'n_holdout':len(rows)-cut,
            'holdout_false_positive_fraction':sum(s<0 for s in holdout)/len(holdout),
            'sha256_dataset':hashlib.sha256(raw).hexdigest(),
            'attack_recall':'NOT MEASURED: run scripts/acceptance.py',
            'created_at':time.time()}
    joblib.dump(model,folder/'model.tmp')
    (folder/'model.tmp').replace(folder/'model.joblib')
    (folder/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
if __name__=='__main__': main()
