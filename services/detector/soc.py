"""Minimal integrated SOC: time-window rules on central logs, plus one correlation. Not a full SIEM.

Two kinds of signal:
 - isolated RULES: a count over a window (failed logins, capacity pressure, an alert delivered, WAF activity);
 - a CORRELATION that follows ONE incident across services through its incident_id: the detector's alert, then the
   remediator's stages. It says whether the chain went through, and flags the two silent failures a count cannot
   see: an alert that was never handled, and a recovery that never finished."""
import json
import time
import uuid
import httpx
from services.detector.telemetry import LOKI
RULES={
 'repeated_failed_logins': ('sum(count_over_time({service="auth",event="login_failed"}[1m]))',5),
 'capacity_pressure': ('sum(count_over_time({service="payment",event="capacity_denied"}[30s]))',3),
 'ml_alert_delivered': ('sum(count_over_time({service="detector",event="alert_delivered"}[1m]))',1),
 'waf_audit_activity': ('sum(count_over_time({service="waf"}[1m]))',1),
}
ORDER=('alert_delivered','containing','verifying','recovered')   # the chain of a recovery, in order
FINAL=('recovered','failed')
NOT_HANDLED_S=15   # alert delivered, remediator silent for this long: the alert was lost or ignored
STUCK_S=90         # recovery started, no final state for this long: stuck
WINDOW_S=900       # how far back incidents are looked for
MAX_INCIDENTS=3
def chain(incident_id,events,now):
    """The state of one incident from (timestamp, event) pairs. Pure: the same events give the same verdict."""
    first={}
    for ts,name in sorted(events): first.setdefault(name,ts)
    final=next((n for n in FINAL if n in first),None)
    path=[n for n in ORDER if n in first]+(['failed'] if 'failed' in first else [])
    times=[first[n] for n in path]
    signal={'rule':'incident_correlation','incident_id':incident_id,'count':1,'window':f'{WINDOW_S//60}m','seen':path,
            'seconds':round(first[final]-first['alert_delivered'],2) if final and 'alert_delivered' in first else None}
    if 'alert_delivered' not in first: return {**signal,'state':'no_alert','missing':['alert_delivered']}
    if final=='failed': return {**signal,'state':'failed','missing':[]}               # manual review requested by the remediator itself
    if final=='recovered':
        missing=[n for n in ORDER if n not in first]
        if missing: return {**signal,'state':'chain_gap','missing':missing}           # recovered without the stages before it
        if times!=sorted(times): return {**signal,'state':'out_of_order','missing':[]}
        return {**signal,'state':'recovered','missing':[]}
    if 'containing' not in first:
        late=now-first['alert_delivered']>NOT_HANDLED_S
        return {**signal,'state':'alert_not_handled' if late else 'alert_pending','missing':['containing']}
    late=now-first['containing']>STUCK_S
    return {**signal,'state':'stuck' if late else 'in_progress','missing':[n for n in ORDER[2:] if n not in first]}
def changed(signal,memory):
    """True when a correlation signal has a new state: the SOC journals transitions, not the same state every cycle."""
    key=signal['incident_id']; state=signal['state']
    if memory.get(key)==state: return False
    memory[key]=state
    if len(memory)>50:
        for old in list(memory)[:len(memory)-50]: del memory[old]
    return True
async def lines(c,query,now):
    r=await c.get(LOKI+'/loki/api/v1/query_range',params={'query':query,'start':int((now-WINDOW_S)*1e9),'end':int(now*1e9),'limit':200,'direction':'backward'})
    r.raise_for_status(); data=r.json()
    if data.get('status')!='success': raise RuntimeError('SOC query failed')
    return [line for stream in data['data']['result'] for _,line in stream['values']]
def parse(line):
    try: record=json.loads(line)
    except ValueError: return None
    return record if isinstance(record,dict) and isinstance(record.get('ts'),(int,float)) and isinstance(record.get('event'),str) else None
async def correlations(c,now=None):
    """Follow the latest incidents: the detector's alert, then every remediator stage carrying the same id."""
    now=time.time() if now is None else now
    alerts=[r for r in map(parse,await lines(c,'{service="detector",event="alert_delivered"}',now)) if r]
    found=[]
    for record in sorted(alerts,key=lambda r:r['ts'],reverse=True):
        try: iid=str(uuid.UUID(str(record.get('incident_id'))))     # validated: it goes into a log query
        except ValueError: continue
        if iid not in [i for i,_ in found]: found.append((iid,record['ts']))
        if len(found)==MAX_INCIDENTS: break
    out=[]
    for iid,alerted in found:
        stages=[r for r in map(parse,await lines(c,'{service="remediator"} |= "%s"'%iid,now)) if r and r.get('incident_id')==iid]
        out.append(chain(iid,[(alerted,'alert_delivered')]+[(r['ts'],r['event']) for r in stages],now))
    return out
async def signals(correlate=True):
    out=[]
    async with httpx.AsyncClient(trust_env=False,timeout=5) as c:
        for name,(query,threshold) in RULES.items():
            r=await c.get(LOKI+'/loki/api/v1/query',params={'query':query});r.raise_for_status()
            data=r.json()
            if data.get('status')!='success': raise RuntimeError('SOC query failed')
            rows=data['data']['result']; count=float(rows[0]['value'][1]) if rows else 0
            if count>=threshold:out.append({'rule':name,'count':count,'window':'30s or 1m; see rule'})
        if correlate:
            # A failing correlation must not hide the rule signals above: it is reported, not raised.
            try: out+=await correlations(c)
            except Exception as exc: out.append({'rule':'incident_correlation','count':0,'window':f'{WINDOW_S//60}m','state':'unavailable','error':type(exc).__name__})
    return out
