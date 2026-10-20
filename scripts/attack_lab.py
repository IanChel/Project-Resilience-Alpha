"""Bounded HTTP application-capacity exercise. No scanning, exploit or external target."""
import argparse
import asyncio
from datetime import datetime, timezone
import getpass
import hashlib
import ipaddress
import json
import os
import sys
import time
import uuid
from collections import Counter
from pathlib import Path
import httpx
def loadbot_password():
    """Interactive by default: a human launches the exercise. For an automated local dry-run of the recovery
    chain, LAB_PASSWORD_DIR names a directory with one file per account (like .secrets/runtime) -- a directory
    of files, never the value in a variable, which would show in process listings. This script stays standalone
    (copied alone to the attacker PC), so it does not import lab_client; the few lines are duplicated on purpose."""
    folder=os.environ.get('LAB_PASSWORD_DIR')
    if not folder: return getpass.getpass('loadbot lab password (from your team): ')
    path=Path(folder)/'loadbot_password'
    if not path.is_file(): raise SystemExit(f'LAB_PASSWORD_DIR is set but {path} does not exist')
    value=path.read_text(encoding='utf-8').strip()
    if not value: raise SystemExit(f'{path} is empty')
    return value
# Default = Host PC on the Windows hotspot RESILIENCE-G2 (see docs/04-ATTAQUE.md).
DEFAULT_TARGET_HOST='192.168.137.1'
LAB_NETWORK=ipaddress.ip_network('192.168.137.0/24')
PORT=int(os.environ.get('LAB_PORT') or 8081)   # published port of the WAF; 8080 is taken on the Host PC
def resolve_target(value):
    """Lab-scope guard. The target stays configurable, but only as a literal IP of the
    hotspot subnet (or loopback). No hostname, no campus range, no Internet address."""
    host='127.0.0.1' if value=='localhost' else value
    try: ip=ipaddress.ip_address(host)
    except ValueError: raise ValueError('Target must be a literal IP address, not a hostname: '+repr(value))
    if not (ip in LAB_NETWORK or ip.is_loopback):
        raise ValueError(f'Target outside the lab network {LAB_NETWORK} and loopback: refused')
    return f'http://{host}:{PORT}'
async def main():
    p=argparse.ArgumentParser(); p.add_argument('--lab-authorized',action='store_true'); p.add_argument('--seconds',type=int,default=30)
    p.add_argument('--target',default=os.environ.get('LAB_TARGET',DEFAULT_TARGET_HOST),
                   help=f'Lab host IP inside {LAB_NETWORK} or loopback (env LAB_TARGET, default {DEFAULT_TARGET_HOST}); port is fixed to {PORT}')
    p.add_argument('--output',type=Path,help='JSON results path (default: attack-results-<UTC timestamp>.json in the current directory)')
    args=p.parse_args()
    if not args.lab_authorized: p.error('Explicit laboratory scope acknowledgement required: --lab-authorized')
    if not 5<=args.seconds<=35: p.error('Duration must be between 5 and 35 seconds')
    try: target=resolve_target(args.target)
    except ValueError as exc: p.error(str(exc))
    password=loadbot_password()
    counts=Counter(); pending=set(); sent=0
    async with httpx.AsyncClient(trust_env=False,base_url=target,timeout=2,follow_redirects=False,limits=httpx.Limits(max_connections=12)) as c:
        r=await c.post('/auth/token',json={'username':'loadbot','password':password}); r.raise_for_status()
        headers={'Authorization':'Bearer '+r.json()['access_token']}
        async def one():
            try:
                r=await c.post('/api/quotes',headers=headers,json={'amount_cents':100})
                counts[str(r.status_code)]+=1
            except httpx.HTTPError: counts['network_error']+=1
        print(f'LAB ONLY: {target}; at most 20 requests/s, 12 concurrent, 700 total.')
        run_id=str(uuid.uuid4())
        started_at_epoch=time.time()
        started_at_utc=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
        started_monotonic=time.monotonic()
        end=started_monotonic+args.seconds
        while time.monotonic()<end and sent<700:
            if len(pending)<12:
                task=asyncio.create_task(one()); pending.add(task); task.add_done_callback(pending.discard); sent+=1
            await asyncio.sleep(0.05)
        await asyncio.gather(*pending)
        ended_at_epoch=time.time()
        ended_at_utc=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    result={
        'schema_version':1,
        'run_id':run_id,
        'started_at_utc':started_at_utc,
        'ended_at_utc':ended_at_utc,
        'started_at_epoch':started_at_epoch,
        'ended_at_epoch':ended_at_epoch,
        'duration_requested_s':args.seconds,
        'duration_actual_s':round(ended_at_epoch-started_at_epoch,3),
        'target':target,
        'endpoint':'POST /api/quotes',
        'account':'loadbot',
        'requests_scheduled':sent,
        'results_by_status_or_error':dict(sorted(counts.items())),
        'http_responses_total':sum(counts[code] for code in counts if code.isdigit()),
        'network_errors':counts['network_error'],
        'results_total':sum(counts.values()),
        'limits':{'requests_per_second':20,'concurrent':12,'total_requests':700},
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'python_version':sys.version.split()[0],
        'credentials_or_tokens_recorded':False,
    }
    output=args.output or Path('attack-results-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json')
    try:
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    except OSError as exc:
        raise SystemExit(f'Attack finished, but results JSON could not be written to {output}: {exc}')
    print(dict(counts))
    print('429 after containment is expected; the workload remains active until its planned end.')
    print(f'Results JSON: {output.resolve()}')
if __name__=='__main__': asyncio.run(main())
