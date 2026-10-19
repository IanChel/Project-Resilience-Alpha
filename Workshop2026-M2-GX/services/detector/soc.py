"""Minimal integrated SOC: time-window rules on central logs, not a full SIEM."""
import httpx
from services.detector.telemetry import LOKI
RULES={
 'repeated_failed_logins': ('sum(count_over_time({service="auth",event="login_failed"}[1m]))',5),
 'capacity_pressure': ('sum(count_over_time({service="payment",event="capacity_denied"}[30s]))',3),
 'ml_alert_delivered': ('sum(count_over_time({service="detector",event="alert_delivered"}[1m]))',1),
 'waf_audit_activity': ('sum(count_over_time({service="waf"}[1m]))',1),
}
async def signals():
    out=[]
    async with httpx.AsyncClient(trust_env=False,timeout=5) as c:
        for name,(query,threshold) in RULES.items():
            r=await c.get(LOKI+'/loki/api/v1/query',params={'query':query});r.raise_for_status()
            data=r.json()
            if data.get('status')!='success': raise RuntimeError('SOC query failed')
            rows=data['data']['result']; count=float(rows[0]['value'][1]) if rows else 0
            if count>=threshold:out.append({'rule':name,'count':count,'window':'30s or 1m; see rule'})
    return out
