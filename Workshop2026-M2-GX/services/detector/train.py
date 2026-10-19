"""Run during a clean normal-traffic session, never during the attack."""
import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
import joblib
from services.detector.model import train_model, FEATURES, score
from services.detector.telemetry import sample
async def main():
    rows=[]
    for i in range(90):
        rows.append(await sample())
        print(f'live baseline {i+1}/90',flush=True)
        await asyncio.sleep(2)
    cut=72
    model=train_model(rows[:cut])
    holdout=[score(model,r) for r in rows[cut:]]
    folder=Path(os.getenv('MODEL_DIR','/models')); folder.mkdir(parents=True,exist_ok=True)
    dataset=json.dumps({'features':FEATURES,'rows':rows,'collected_at':time.time()})
    (folder/'baseline.json').write_text(dataset)
    report={'source':'live Prometheus and Loki; normal traffic only','n_train':cut,'n_holdout':18,
            'holdout_false_positive_fraction':sum(s<0 for s in holdout)/len(holdout),
            'sha256_dataset':hashlib.sha256(dataset.encode()).hexdigest(),
            'attack_recall':'NOT MEASURED: run scripts/acceptance.py',
            'created_at':time.time()}
    joblib.dump(model,folder/'model.tmp')
    (folder/'model.tmp').replace(folder/'model.joblib')
    (folder/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
if __name__=='__main__': asyncio.run(main())
