"""The five OpenAPI contracts (auth, detector, payment, rag, remediator) still describe the code: routes, declared status
codes, and the BODY of real responses validated against the spec's schemas."""
import hashlib
import hmac
import json
import time
import uuid
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
import services.auth.main as auth
import services.remediator.main as remediator
from services.common.security import issue, secret
from tests.test_rag_service import rag            # noqa: F401  (fixture: the real RAG app, Ollama pointed at a closed port)
ROOT=Path(__file__).resolve().parents[1]
SPECS={n:json.loads((ROOT/'docs'/'openapi'/f'{n}.json').read_text(encoding='utf-8')) for n in ('auth','detector','payment','rag','remediator')}
OP=lambda:{'Authorization':'Bearer '+issue('alice','operator')}
LB=lambda:{'Authorization':'Bearer '+issue('loadbot','loadbot')}
def deref(node,spec):
    if isinstance(node,dict):
        if '$ref' in node:
            target=spec
            for part in node['$ref'].lstrip('#/').split('/'): target=target[part]
            return deref(target,spec)
        return {k:deref(v,spec) for k,v in node.items()}
    return [deref(v,spec) for v in node] if isinstance(node,list) else node
class Seen:
    def __init__(self): self.calls=[]
    def check(self,name,method,path,response):
        spec=SPECS[name]; operation=spec['paths'].get(path,{}).get(method.lower())
        assert operation is not None,f'{name}: {method} {path} is not in the spec'
        declared=deref(operation['responses'],spec); code=str(response.status_code)
        assert code in declared,f'{name}: {method} {path} -> {code} is not declared ({sorted(declared)}) body={response.text[:120]}'
        content=declared[code].get('content')
        if content:
            kind=response.headers.get('content-type','').split(';')[0]
            assert kind in content,f'{name}: {method} {path} -> {code} answers {kind}, the spec says {sorted(content)}'
            if kind=='application/json':
                errors=sorted(Draft202012Validator(content[kind]['schema']).iter_errors(response.json()),key=lambda e:list(e.path))
                assert not errors,f'{name}: {method} {path} -> {code} body does not match the spec: '+'; '.join(f'{"/".join(map(str,e.path)) or "(root)"}: {e.message}' for e in errors[:4])+f' | body={response.text[:200]}'
        self.calls.append((name,method.upper(),path,response.status_code)); return response
@pytest.fixture
def seen(): return Seen()

def test_auth(seen):
    auth.attempts.clear()
    with TestClient(auth.app) as c:
        seen.check('auth','get','/health',c.get('/health'))
        seen.check('auth','post','/token',c.post('/token',json={'username':'alice','password':secret('alice_password')}))
        seen.check('auth','post','/token',c.post('/token',json={'username':'alice','password':'wrong'}))
        seen.check('auth','post','/token',c.post('/token',json={'username':'alice'}))
        for _ in range(35): last=c.post('/token',json={'username':'alice','password':'wrong'})
        seen.check('auth','post','/token',last)
    assert {s for *_,s in seen.calls}=={200,401,422,429}
def test_payment(seen,payment):
    body={'amount_cents':12,'recipient':'merchant'}; key={'Idempotency-Key':'conformance-key-1'}
    with TestClient(payment.app) as c:
        for path in ('/health','/ready','/metrics'): seen.check('payment','get',path,c.get(path))
        seen.check('payment','get','/accounts',c.get('/accounts',headers=OP())); seen.check('payment','get','/accounts',c.get('/accounts')); seen.check('payment','get','/accounts',c.get('/accounts',headers=LB()))
        seen.check('payment','post','/payments',c.post('/payments',headers={**OP(),**key},json=body))
        seen.check('payment','post','/payments',c.post('/payments',headers={**OP(),**key},json={**body,'amount_cents':13}))
        seen.check('payment','post','/payments',c.post('/payments',headers={**OP(),**key},json={**body,'amount_cents':0}))
        seen.check('payment','post','/payments',c.post('/payments',json=body)); seen.check('payment','post','/payments',c.post('/payments',headers={**LB(),**key},json=body))
        payment.active=4                                                                             # all four capacity slots taken
        seen.check('payment','post','/payments',c.post('/payments',headers={**OP(),'Idempotency-Key':'conformance-key-2'},json=body))
        seen.check('payment','post','/quotes',c.post('/quotes',headers=LB(),json={'amount_cents':100})); payment.active=0
        seen.check('payment','post','/quotes',c.post('/quotes',headers=LB(),json={'amount_cents':100})); seen.check('payment','post','/quotes',c.post('/quotes',json={'amount_cents':100}))
        seen.check('payment','post','/control/contain',c.post('/control/contain'))
        seen.check('payment','post','/control/contain',c.post('/control/contain',headers={'X-Control-Key':secret('control_key')}))
        time.sleep(1.05); c.post('/quotes',headers=LB(),json={'amount_cents':100})
        seen.check('payment','post','/quotes',c.post('/quotes',headers=LB(),json={'amount_cents':100}))     # contained: second quote within a second
    assert {s for *_,s in seen.calls}>={200,401,403,409,422,429,503}
def signed(data):
    raw=json.dumps(data).encode(); return {'content':raw,'headers':{'Content-Type':'application/json','X-Signature':hmac.new(secret('alert_key').encode(),raw,hashlib.sha256).hexdigest()}}
def test_remediator(seen,tmp_path,monkeypatch):
    monkeypatch.setattr(remediator,'STORE',tmp_path/'incidents.sqlite')
    async def no_recovery(iid): return None
    monkeypatch.setattr(remediator,'recover',no_recovery)
    alert=lambda **o:{'id':str(uuid.uuid4()),'issued_at':time.time(),'score':-0.4,'features':[9,4,5,5],'sources':['192.168.137.20'],**o}
    first=alert()
    with TestClient(remediator.app) as c:
        seen.check('remediator','get','/health',c.get('/health'))
        seen.check('remediator','get','/status',c.get('/status',headers=OP()))                       # empty list, with `now`
        seen.check('remediator','post','/alerts',c.post('/alerts',**signed(first)))                   # accepted
        seen.check('remediator','post','/alerts',c.post('/alerts',**signed(first)))                   # duplicate
        seen.check('remediator','post','/alerts',c.post('/alerts',**signed(alert())))                 # already_running
        seen.check('remediator','post','/alerts',c.post('/alerts',content=b'{}',headers={'X-Signature':'0'*64}))
        seen.check('remediator','post','/alerts',c.post('/alerts',**signed(alert(issued_at=time.time()-100))))
        seen.check('remediator','post','/alerts',c.post('/alerts',content=b'x'*5000,headers={'X-Signature':'0'*64}))
        remediator.update(first['id'],'containing',{'action':'enable_quote_admission','ban':{'enabled':True,'eligible':['192.168.137.20'],'excluded':[],'ttl_s':300}})
        remediator.update(first['id'],'verifying',{'ban':{'enabled':True}}); remediator.update(first['id'],'recovered',{'transaction_id':'tx-1','total_cents':200000,'ban':{'enabled':False}})
        reply=seen.check('remediator','get','/status',c.get('/status',headers=OP()))                  # an incident with its stages
        assert list(reply.json()['incidents'][0]['stages'])[:2]==['detected','accepted']
        seen.check('remediator','get','/status',c.get('/status')); seen.check('remediator','get','/status',c.get('/status',headers=LB()))
    assert {s for *_,s in seen.calls}>={200,202,401,403,413,422}
def test_detector(seen,monkeypatch):
    from services.detector import main as detector
    states=[{'status':'waiting_for_trained_model','features':None,'score':None,'config':{'consecutive':3,'nu':None}},
            {'status':'monitoring','features':{'quote_rate':9.0,'active_work':4.0,'capacity_denied_10s':5.0,'denial_logs_10s':5.0},'score':-0.4,'config':{'consecutive':3,'nu':0.03},
             'soc_signals':[{'rule':'capacity_pressure','count':9.0,'window':'30s'},{'rule':'incident_correlation','incident_id':str(uuid.uuid4()),'count':1,'window':'15m','state':'recovered',
                                                                                  'seen':['alert_delivered','containing','verifying','recovered'],'missing':[],'seconds':14.2}],'soc_error':'ConnectError'},
            {'status':'telemetry_or_delivery_error','features':None,'score':None,'config':{'consecutive':3,'nu':0.03}}]
    for state in states:
        monkeypatch.setattr(detector,'state',state)
        c=TestClient(detector.app)
        seen.check('detector','get','/health',c.get('/health')); seen.check('detector','get','/anomaly',c.get('/anomaly'))
def test_rag(seen,rag,monkeypatch):                                                                  # noqa: F811
    from tests.test_rag_service import Chain
    with TestClient(rag.app) as c:
        seen.check('rag','get','/health',c.get('/health'))
        seen.check('rag','post','/ask',c.post('/ask',json={'question':'xqzjv wkpfz qqxz'},headers=OP()))   # abstains
        monkeypatch.setattr(rag,'chain',Chain(result='Réponse.')); seen.check('rag','post','/ask',c.post('/ask',json={'question':'Pourquoi vous ne redémarrez pas le conteneur ?'},headers=OP()))
        seen.check('rag','post','/ask',c.post('/ask',json={'question':'une question'})); seen.check('rag','post','/ask',c.post('/ask',json={'question':'une question'},headers=LB()))
        seen.check('rag','post','/ask',c.post('/ask',json={'question':'ab'},headers=OP()))
        monkeypatch.setattr(rag,'chain',Chain(error=RuntimeError('model not pulled'))); seen.check('rag','post','/ask',c.post('/ask',json={'question':'Pourquoi vous ne redémarrez pas le conteneur ?'},headers=OP()))
        monkeypatch.setattr(rag,'lock',type('L',(),{'locked':lambda self:True})()); seen.check('rag','post','/ask',c.post('/ask',json={'question':'une question'},headers=OP()))
    assert {s for *_,s in seen.calls}>={200,401,403,422,429,503}

@pytest.mark.parametrize('name,module',[('auth','services.auth.main'),('payment','services.payment.main'),('remediator','services.remediator.main'),('detector','services.detector.main')])
def test_every_route_of_the_code_is_in_the_spec_and_the_other_way_round(name,module):
    import importlib
    live=importlib.import_module(module).app.openapi()
    routes=lambda s:{(p,m.upper()) for p,ops in s['paths'].items() for m in ops if m in ('get','post','put','delete','patch')}
    assert routes(SPECS[name])==routes(live)
def test_the_rag_routes_match_its_spec(rag):                                                          # noqa: F811
    live=rag.app.openapi(); routes=lambda s:{(p,m.upper()) for p,ops in s['paths'].items() for m in ops if m in ('get','post')}
    assert routes(SPECS['rag'])==routes(live)
@pytest.mark.parametrize('name',sorted(SPECS))
def test_every_spec_is_valid_openapi_with_resolvable_references(name):
    spec=SPECS[name]; assert spec['openapi'].startswith('3.1')
    deref(spec,spec)                                                                                  # raises KeyError on a dangling $ref
    for path,operations in spec['paths'].items():
        for method,operation in operations.items(): assert operation['responses'] and operation.get('operationId'),(name,path,method)
