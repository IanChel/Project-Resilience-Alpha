"""Clean operator traffic, used to record the ML baseline.

Arrival times are RANDOM, not a fixed cycle. Measured on 2026-10-19: with the previous fixed cadence
[0.1,0.4,0.8,0.2] the quote rate was almost constant (standard deviation 0.036, eleven distinct values) and
active_work was binary. A novelty detector trained on that has no variance to learn from: the boundary fits
numerical noise, 62 of 72 training points already scored negative and the holdout gave 100 % false positives,
with no usable `nu` (the sweep jumped 2, 18, 2, 2, 17, 17, 1). Independent clients are classically modelled by
exponential inter-arrival times, which is what this produces. The seed keeps a run reproducible for the report."""
import argparse
import random
import time
import httpx
from lab_client import base_url, validate_url, login
MEAN_INTERVAL_S=0.375      # same average rate as the previous fixed cycle: about 2.7 quotes per second
MIN_INTERVAL_S,MAX_INTERVAL_S=0.05,1.5
p=argparse.ArgumentParser(description=__doc__.splitlines()[0])
p.add_argument('--url',default=base_url()); p.add_argument('--seconds',type=int,default=240)
p.add_argument('--seed',type=int,default=12345,help='0 for a different draw at every run')
a=p.parse_args()
rng=random.Random(a.seed or None)
sent=0
with httpx.Client(trust_env=False,base_url=validate_url(a.url),timeout=5,follow_redirects=False) as c:
    h=login(c,'alice'); end=time.monotonic()+min(a.seconds,600)
    while time.monotonic()<end:
        r=c.post('/api/quotes',headers=h,json={'amount_cents':rng.randrange(50,400,10)}); r.raise_for_status()
        sent+=1
        time.sleep(min(MAX_INTERVAL_S,max(MIN_INTERVAL_S,rng.expovariate(1/MEAN_INTERVAL_S))))
print(f'Clean normal quotation traffic completed: {sent} quotes, seed {a.seed}.')
