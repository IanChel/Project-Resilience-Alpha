"""Bounded HTTP application-capacity exercise. No scanning, exploit or external target."""
import argparse
import asyncio
import getpass
import ipaddress
import os
import time
from collections import Counter
import httpx
# Default = Host PC on the Windows hotspot RESILIENCE-G2 (see docs/04-ATTAQUE.md).
DEFAULT_TARGET_HOST='192.168.137.1'
LAB_NETWORK=ipaddress.ip_network('192.168.137.0/24')
PORT=8080
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
    args=p.parse_args()
    if not args.lab_authorized: p.error('Explicit laboratory scope acknowledgement required: --lab-authorized')
    if not 5<=args.seconds<=35: p.error('Duration must be between 5 and 35 seconds')
    try: target=resolve_target(args.target)
    except ValueError as exc: p.error(str(exc))
    password=getpass.getpass('loadbot lab password (from your team): ')
    counts=Counter(); pending=set(); end=time.monotonic()+args.seconds
    async with httpx.AsyncClient(trust_env=False,base_url=target,timeout=2,follow_redirects=False,limits=httpx.Limits(max_connections=12)) as c:
        r=await c.post('/auth/token',json={'username':'loadbot','password':password}); r.raise_for_status()
        headers={'Authorization':'Bearer '+r.json()['access_token']}
        async def one():
            try:
                r=await c.post('/api/quotes',headers=headers,json={'amount_cents':100})
                counts[str(r.status_code)]+=1
            except httpx.HTTPError: counts['network_error']+=1
        sent=0
        print(f'LAB ONLY: {target}; at most 20 requests/s, 12 concurrent, 700 total.')
        while time.monotonic()<end and sent<700:
            if len(pending)<12:
                task=asyncio.create_task(one()); pending.add(task); task.add_done_callback(pending.discard); sent+=1
            await asyncio.sleep(0.05)
        await asyncio.gather(*pending)
    print(dict(counts))
    print('429 after containment is expected; the workload remains active until its planned end.')
if __name__=='__main__': asyncio.run(main())
