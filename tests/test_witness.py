"""The witness transaction (carte W3): what makes a recovery PROVEN rather than assumed. Confirmed, not rewritten."""
import asyncio
from types import SimpleNamespace
import httpx
import pytest
import services.remediator.main as remediator
RealClient=httpx.AsyncClient
class Stack:
    """Canned auth + WAF. Records every request so the tests can see what the witness really sends."""
    def __init__(self,total=200000,listed=True,pay_status=200):
        self.total=total; self.listed=listed; self.pay_status=pay_status; self.seen=[]
    def handler(self,request):
        self.seen.append((request.method,request.url.host,request.url.path,dict(request.headers),request.content))
        if request.url.host=='auth': return httpx.Response(200,json={'access_token':'t','token_type':'bearer'})
        if request.url.path=='/api/payments':
            if self.pay_status!=200: return httpx.Response(self.pay_status,json={'detail':'Simulated downstream capacity exhausted'})
            return httpx.Response(200,json={'transaction':{'id':'tx-42'},'replayed':False})
        if request.url.path=='/api/accounts':
            return httpx.Response(200,json={'total_cents':self.total,'transactions':[{'id':'tx-42'}] if self.listed else [{'id':'someone-else'}]})
        raise AssertionError('unexpected '+request.url.path)
@pytest.fixture
def witness(monkeypatch):
    monkeypatch.setenv('PUBLIC_URL','http://waf:8080'); monkeypatch.setenv('AUTH_URL','http://auth:8000')
    async def no_wait(seconds): return None
    monkeypatch.setattr(remediator.asyncio,'sleep',no_wait)                              # skip the one-second retries
    def install(stack):
        monkeypatch.setattr(remediator,'httpx',SimpleNamespace(AsyncClient=lambda **kw:RealClient(transport=httpx.MockTransport(stack.handler),**kw),HTTPError=httpx.HTTPError))
        return stack
    return install

def test_the_witness_pays_one_cent_through_the_waf_with_a_per_incident_idempotency_key(witness):
    stack=witness(Stack())
    proof=asyncio.run(remediator.business_verify('inc-1'))
    assert proof=={'transaction_id':'tx-42','total_cents':200000}
    pay=[s for s in stack.seen if s[2]=='/api/payments'][0]
    assert pay[0]=='POST' and pay[1]=='waf'                                              # the public path, not the internal health endpoint
    assert pay[3]['idempotency-key']=='recovery-inc-1' and b'"amount_cents":1' in pay[4].replace(b' ',b'')
    assert pay[3]['authorization']=='Bearer t'
def test_the_same_incident_replays_with_the_same_key_so_a_retry_never_pays_twice(witness):
    stack=witness(Stack())
    asyncio.run(remediator.business_verify('inc-2')); asyncio.run(remediator.business_verify('inc-2'))
    keys={s[3]['idempotency-key'] for s in stack.seen if s[2]=='/api/payments'}
    assert keys=={'recovery-inc-2'}
def test_a_wrong_ledger_total_is_not_a_recovery(witness):
    witness(Stack(total=199999))
    with pytest.raises(RuntimeError,match='End-to-end business verification failed'): asyncio.run(remediator.business_verify('inc-3'))
def test_a_transaction_missing_from_the_ledger_is_not_a_recovery(witness):
    witness(Stack(listed=False))
    with pytest.raises(RuntimeError,match='End-to-end business verification failed'): asyncio.run(remediator.business_verify('inc-4'))
def test_a_payment_still_refused_is_not_a_recovery(witness):
    stack=witness(Stack(pay_status=503))
    with pytest.raises(RuntimeError,match='End-to-end business verification failed'): asyncio.run(remediator.business_verify('inc-5'))
    assert len([s for s in stack.seen if s[2]=='/api/payments'])==15                     # bounded retries, no open-ended loop
def test_the_witness_never_asks_the_waf_to_log_in(witness):
    stack=witness(Stack()); asyncio.run(remediator.business_verify('inc-6'))
    assert [s[2] for s in stack.seen if s[1]=='waf']==['/api/payments','/api/accounts']  # login goes over the internal path (mardi, M1)
