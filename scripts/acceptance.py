"""Host-side observer; the attack MUST be started on the second PC.
The evidence it writes (runtime/evidence/acceptance-<epoch>.json) is meant to be quoted in the PCA/PRA: besides the
raw observations it carries a `summary` (the stage timestamps, detection -> recovered time, witness verdict, ban,
user-visible outage), the detector configuration the run used (without it a measurement cannot be reproduced) and
the code version. `complete` and `missing` say whether the evidence can be used as it is."""
import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
import httpx
from lab_client import validate_url, login
STEPS=('detected','containing','verifying','recovered')   # alert, remediation started, healthcheck OK, witness transaction validated
TARGET_S=60
ROOT=Path(__file__).resolve().parents[1]
def code_version(root=ROOT):
    """Commit and whether the working tree differs from it, best effort (None when git is unavailable)."""
    try:
        commit=subprocess.run(['git','rev-parse','HEAD'],cwd=root,capture_output=True,text=True,timeout=10,check=True).stdout.strip()
        dirty=bool(subprocess.run(['git','status','--porcelain'],cwd=root,capture_output=True,text=True,timeout=10,check=True).stdout.strip())
        return {'commit':commit,'dirty':dirty}
    except (OSError,subprocess.SubprocessError): return None
def evidence_of(incident):
    try: value=json.loads(incident.get('evidence') or '{}')
    except ValueError: return {}
    return value if isinstance(value,dict) else {}
def summarize(result,ml_state,version):
    """What a reader of the PCA/PRA needs, from the raw observations. Pure: no network, no clock."""
    observed=result['observations']; latest={}
    for row in observed:
        for incident in row.get('incidents',[]): latest[incident['id']]=incident            # last snapshot of each new incident
    incident=min(latest.values(),key=lambda i:i['created']) if latest else None             # the one this attack caused
    stages=(incident or {}).get('stages') or {}; start=stages.get('detected')
    steps=[{'name':name,'at':stages.get(name),'offset_s':round(stages[name]-start,2) if name in stages and start is not None else None} for name in STEPS]
    total=round(stages['recovered']-start,2) if 'recovered' in stages and start is not None else None
    evidence=evidence_of(incident) if incident else {}
    verdict={'recovered':'validated','failed':'failed'}.get((incident or {}).get('status'),'absent')
    first_refused=next((r['at'] for r in observed if r.get('payment_status')==503),None)
    first_ok_after=next((r['at'] for r in observed if first_refused is not None and r['at']>first_refused and r.get('payment_status')==200),None)
    config=(ml_state or {}).get('config')
    ledger_total=(result.get('ledger') or {}).get('total_cents')
    missing=[f'stage:{s["name"]}' for s in steps if s['at'] is None]
    if verdict!='validated': missing.append('witness_transaction_validated')
    if not isinstance(config,dict) or config.get('consecutive') is None or config.get('nu') is None: missing.append('detector_config')
    if ledger_total is None: missing.append('ledger_total')
    return {'incident':{'id':(incident or {}).get('id'),'status':(incident or {}).get('status'),'steps':steps,'detection_to_recovered_s':total,
                        'within_target':None if total is None else total<TARGET_S,'target_s':TARGET_S},
            'witness':{'verdict':verdict,'transaction_id':evidence.get('transaction_id'),'total_cents':evidence.get('total_cents')},
            'ban':evidence.get('ban'),
            'user_visible_outage':{'first_refused_at':first_refused,'first_ok_after_at':first_ok_after,
                                   'seconds':round(first_ok_after-first_refused,2) if first_ok_after is not None else None,
                                   'note':'seen by this observer, one probe every 0.5 s'},
            'ledger_total_cents':ledger_total,'detector_config':config,'code_version':version,
            'complete':not missing,'missing':missing}
def verdict_of(result):
    observed=result['observations']
    failures=[r['at'] for r in observed if r.get('payment_status')==503]
    recovered=[i for row in observed for i in row.get('incidents',[]) if i['status']=='recovered']
    return bool(failures and any(i['created']>=result['started_at'] and i['updated']>=min(failures) for i in recovered) and result['after_status']==200 and result['ledger']['total_cents']==200000)
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0]); p.add_argument('--url',default='http://127.0.0.1:8080'); p.add_argument('--seconds',type=int,default=55)
    a=p.parse_args(argv); result={'observations':[],'started_at':time.time()}; ml_state=None
    with httpx.Client(trust_env=False,base_url=validate_url(a.url),timeout=3,follow_redirects=False) as c:
        h=login(c,'alice')
        r=c.post('/api/payments',headers={**h,'Idempotency-Key':str(uuid.uuid4())},json={'amount_cents':1,'recipient':'merchant'})
        r.raise_for_status(); result['before']=r.json()
        old=c.get('/ops/status',headers=h); old.raise_for_status(); existing={x['id'] for x in old.json()['incidents']}
        print('Initial transaction verified. Start attack_lab.py on the ATTACKER PC now.',flush=True)
        end=time.monotonic()+min(a.seconds,120)
        while time.monotonic()<end:
            row={'at':time.time()}
            try:
                r=c.post('/api/payments',headers={**h,'Idempotency-Key':str(uuid.uuid4())},json={'amount_cents':1,'recipient':'merchant'})
                row['payment_status']=r.status_code
                r=c.get('/ops/status',headers=h); r.raise_for_status()
                row['incidents']=[i for i in r.json()['incidents'] if i['id'] not in existing]
            except httpx.HTTPError as exc: row['network_error']=type(exc).__name__
            result['observations'].append(row); print(json.dumps(row),flush=True); time.sleep(0.5)
        r=c.post('/api/payments',headers={**h,'Idempotency-Key':str(uuid.uuid4())},json={'amount_cents':1,'recipient':'merchant'})
        result['after_status']=r.status_code
        result['after']=r.json()
        r=c.get('/api/accounts',headers=h); r.raise_for_status(); result['ledger']=r.json()
        try:   # the detector configuration of THIS run: without it a measurement is not reproducible
            r=c.get('/ops/ml',headers=h); r.raise_for_status(); ml_state=r.json()
        except (httpx.HTTPError,ValueError): ml_state=None      # unreadable: the evidence says so (detector_config missing), the run is not lost
    result['passed']=verdict_of(result)
    result['summary']=summarize(result,ml_state,code_version())
    folder=Path('runtime/evidence'); folder.mkdir(parents=True,exist_ok=True)
    path=folder/('acceptance-'+str(int(time.time()))+'.json'); path.write_text(json.dumps(result,indent=2))
    s=result['summary']; i=s['incident']
    print('PASS' if result['passed'] else 'FAIL: inspect evidence; do not claim a successful demonstration')
    print(f'detection -> recovered: {i["detection_to_recovered_s"]} s | witness: {s["witness"]["verdict"]} | detector config: {s["detector_config"]} | complete: {s["complete"]}')
    if not s['complete']: print('EVIDENCE INCOMPLETE, missing: '+', '.join(s['missing']))
    print(path)
    return 0 if result['passed'] else 1
if __name__=='__main__': sys.exit(main())
