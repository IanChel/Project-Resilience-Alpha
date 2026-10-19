"""Source addresses behind a flood, for the signed alert.

They are measured at the WAF's OWN peer address: its nginx access log, shipped to Loki by Alloy as
{service="wafaccess"}. They never come from a request header (X-Forwarded-For is client-controlled), so a client
cannot name the address that gets banned. Any problem (no access log, Loki down, unreadable line) gives no
source: the alert then goes out without one, exactly as before. This module never raises and never delays the
alert by more than the short timeout below."""
import ipaddress
import os
import httpx
from services.detector.telemetry import LOKI
# Plain nginx access log (the line starts with the peer address) or a JSON log with a remote_addr field.
QUERY='sum by (ip) (count_over_time({service="wafaccess"} | regexp `(?:^|"remote_addr":")(?P<ip>[0-9a-fA-F:.]+)` [10s]))'
TIMEOUT_S=2
async def loki_get(query):
    async with httpx.AsyncClient(trust_env=False,timeout=TIMEOUT_S) as c:
        r=await c.get(LOKI+'/loki/api/v1/query',params={'query':query}); r.raise_for_status(); return r.json()
def settings(env=None):
    env=os.environ if env is None else env
    return int(env.get('BAN_MIN_REQUESTS') or 50),int(env.get('BAN_MAX_SOURCES') or 3)
async def top_sources(get=loki_get,env=None):
    """Up to BAN_MAX_SOURCES addresses with at least BAN_MIN_REQUESTS requests in the last 10 s, busiest first."""
    try:
        minimum,limit=settings(env)
        data=await get(QUERY)
        if data.get('status')!='success': return []
        found=[]
        for series in data['data']['result']:
            try: found.append((float(series['value'][1]),str(ipaddress.ip_address(series['metric']['ip']))))
            except (KeyError,TypeError,ValueError,IndexError): continue
        return [ip for count,ip in sorted(found,reverse=True) if count>=minimum][:limit]
    except Exception: return []
