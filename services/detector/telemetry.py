import os
import httpx
from services.detector.model import FEATURES
PROM=os.getenv('PROM_URL','http://prometheus:9090')
LOKI=os.getenv('LOKI_URL','http://loki:3100')
QUERIES=[
 'sum(rate(lab_requests_total{route="quotes",status="200"}[10s]))',
 'sum(lab_active_work)',
 'sum(increase(lab_capacity_denied_total[10s]))',
]
async def sample():
    values=[]
    async with httpx.AsyncClient(trust_env=False,timeout=5) as c:
        for q in QUERIES:
            r=await c.get(PROM+'/api/v1/query',params={'query':q}); r.raise_for_status()
            data=r.json()
            if data.get('status')!='success': raise RuntimeError('Prometheus query failed')
            result=data['data']['result']
            # Empty series during startup is unavailable evidence, not a zero measurement.
            if not result: raise RuntimeError('Prometheus series not ready: '+q)
            values.append(float(result[0]['value'][1]))
        query='sum(count_over_time({service="payment"} |= "capacity_denied" [10s]))'
        r=await c.get(LOKI+'/loki/api/v1/query',params={'query':query}); r.raise_for_status()
        data=r.json()
        if data.get('status')!='success': raise RuntimeError('Loki query failed')
        result=data['data']['result']
        values.append(float(result[0]['value'][1]) if result else 0.0)
    return values
