import argparse
import time
import httpx
from lab_client import base_url, validate_url, login
p=argparse.ArgumentParser(); p.add_argument('--url',default=base_url()); p.add_argument('--seconds',type=int,default=240)
a=p.parse_args()
with httpx.Client(trust_env=False,base_url=validate_url(a.url),timeout=5,follow_redirects=False) as c:
    h=login(c,'alice'); end=time.monotonic()+min(a.seconds,600); i=0
    while time.monotonic()<end:
        r=c.post('/api/quotes',headers=h,json={'amount_cents':100+(i%4)*50}); r.raise_for_status()
        time.sleep([0.1,0.4,0.8,0.2][i%4]); i+=1
print('Clean normal quotation traffic completed.')
