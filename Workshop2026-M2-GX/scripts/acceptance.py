"""Host-side observer; the attack MUST be started on the second PC."""
import argparse
import json
import time
import uuid
from pathlib import Path
import httpx
from lab_client import validate_url, login
p=argparse.ArgumentParser(); p.add_argument('--url',default='http://127.0.0.1:8080'); p.add_argument('--seconds',type=int,default=55)
a=p.parse_args(); result={'observations':[],'started_at':time.time()}
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
observed=result['observations']
failures=[r['at'] for r in observed if r.get('payment_status')==503]
recovered=[i for row in observed for i in row.get('incidents',[]) if i['status']=='recovered']
result['passed']=bool(failures and any(i['created']>=result['started_at'] and i['updated']>=min(failures) for i in recovered) and result['after_status']==200 and result['ledger']['total_cents']==200000)
folder=Path('runtime/evidence'); folder.mkdir(parents=True,exist_ok=True)
path=folder/('acceptance-'+str(int(time.time()))+'.json'); path.write_text(json.dumps(result,indent=2))
print('PASS' if result['passed'] else 'FAIL: inspect evidence; do not claim a successful demonstration')
print(path)
raise SystemExit(0 if result['passed'] else 1)
