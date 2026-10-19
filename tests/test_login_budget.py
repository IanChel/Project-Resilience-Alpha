"""The recovery verification must not depend on the public login budget.
Auth rate-limits logins per peer address; behind WAF and edge every public client shares one address."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
import httpx
import pytest
import yaml
import services.auth.main as auth
import services.remediator.main as remediator
from services.common.security import secret
ROOT=Path(__file__).resolve().parents[1]
RealClient=httpx.AsyncClient
EDGE=('172.20.0.5',40000)         # what auth sees for ANY public client (WAF -> edge -> auth)
REMEDIATOR=('172.20.0.9',40001)   # what auth sees for the remediator container
class Network(httpx.AsyncBaseTransport):
    """In-memory stand-in for the compose network. 'waf' is the public path (rewritten like
    infra/nginx/default.conf, peer = edge); 'auth' is the internal path (peer = remediator)."""
    def __init__(self,payment): self.payment=payment
    async def handle_async_request(self,request):
        if request.url.host=='waf':
            app,path={'/auth/token':(auth.app,'/token'),'/api/payments':(self.payment.app,'/payments'),
                      '/api/accounts':(self.payment.app,'/accounts')}[request.url.path]; peer=EDGE
        elif request.url.host=='auth': app,path,peer=auth.app,request.url.path,REMEDIATOR
        else: raise AssertionError('unexpected host '+request.url.host)
        forwarded=httpx.Request(request.method,request.url.copy_with(path=path),headers=request.headers,content=request.content)
        return await httpx.ASGITransport(app=app,client=peer).handle_async_request(forwarded)
@pytest.fixture
def network(payment,monkeypatch):
    auth.attempts.clear()
    monkeypatch.setenv('PUBLIC_URL','http://waf:8080'); monkeypatch.setenv('AUTH_URL','http://auth:8000')
    net=Network(payment)
    monkeypatch.setattr(remediator,'httpx',SimpleNamespace(AsyncClient=lambda **kw:RealClient(transport=net,**kw),HTTPError=httpx.HTTPError))
    return net
async def exhaust_public_budget(net):
    async with RealClient(transport=net,base_url='http://waf:8080') as public:
        codes=[(await public.post('/auth/token',json={'username':'alice','password':'wrong'})).status_code for _ in range(35)]
        assert 401 in codes and 429 in codes                       # the rate limit is still doing its job
        locked=await public.post('/auth/token',json={'username':'alice','password':secret('alice_password')})
        assert locked.status_code==429                             # even the right password is refused publicly

def test_verification_succeeds_while_the_public_login_budget_is_exhausted(network):
    async def run():
        await exhaust_public_budget(network)
        proof=await remediator.business_verify('budget-test')
        assert proof['total_cents']==200000 and proof['transaction_id']
    asyncio.run(run())
def test_this_harness_does_reproduce_the_old_coupling(network,monkeypatch):
    async def coupled_token():                                     # the previous behaviour: login through the WAF
        async with remediator.httpx.AsyncClient(base_url='http://waf:8080') as c:
            r=await c.post('/auth/token',json={'username':'alice','password':secret('alice_password')})
            r.raise_for_status(); return r.json()['access_token']
    monkeypatch.setattr(remediator,'service_token',coupled_token)
    async def run():
        await exhaust_public_budget(network)
        with pytest.raises(httpx.HTTPStatusError) as exc: await remediator.business_verify('budget-test')
        assert exc.value.response.status_code==429
    asyncio.run(run())
def test_the_internal_path_exists_and_is_not_published():
    compose=yaml.safe_load((ROOT/'compose.yaml').read_text())
    internal={n for n,v in compose['networks'].items() if v.get('internal')}
    shared=set(compose['services']['remediator']['networks'])&set(compose['services']['auth']['networks'])
    assert shared&internal                                          # same internal network: no need to go through the WAF
    assert 'ports' not in compose['services']['auth'] and 'ports' not in compose['services']['remediator']
def test_the_recovery_login_never_names_the_public_route():
    text=(ROOT/'services/remediator/main.py').read_text()
    body=text[text.index('async def service_token'):text.index('async def business_verify')]
    assert "os.getenv('AUTH_URL'" in body and '/auth/token' not in body
