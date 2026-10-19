import asyncio
import httpx
import pytest
from fastapi.testclient import TestClient
from services.common.security import issue,secret

def headers(role='operator'):
    return {'Authorization':'Bearer '+issue('alice' if role=='operator' else 'loadbot',role),'Idempotency-Key':'demo-request-123'}
def test_auth_required(payment):
    with TestClient(payment.app) as c:
        assert c.get('/accounts').status_code==401
        assert c.get('/accounts',headers=headers('loadbot')).status_code==403
        assert c.post('/control/contain').status_code==403
@pytest.mark.parametrize('amount',[0,-1,1.2,'100',True,100001])
def test_invalid_amounts(payment,amount):
    with TestClient(payment.app) as c:
        assert c.post('/payments',headers=headers(),json={'amount_cents':amount,'recipient':'merchant'}).status_code==422

def test_transaction_replay(payment):
    with TestClient(payment.app) as c:
        body={'amount_cents':12,'recipient':'merchant'}
        first=c.post('/payments',headers=headers(),json=body)
        replay=c.post('/payments',headers=headers(),json=body)
        assert first.status_code==replay.status_code==200
        assert first.json()['transaction']['id']==replay.json()['transaction']['id']
        assert replay.json()['replayed']

def test_overload_then_targeted_recovery(payment):
    async def run():
        async with httpx.AsyncClient(trust_env=False,transport=httpx.ASGITransport(app=payment.app),base_url='http://lab') as c:
            tasks=[asyncio.create_task(c.post('/quotes',headers=headers('loadbot'),json={'amount_cents':100})) for _ in range(4)]
            await asyncio.sleep(0.02)
            r=await c.post('/payments',headers=headers(),json={'amount_cents':1,'recipient':'merchant'})
            assert r.status_code==503
            await asyncio.gather(*tasks)
            r=await c.post('/control/contain',headers={'X-Control-Key':secret('control_key')});assert r.json()['changed']
            assert not (await c.post('/control/contain',headers={'X-Control-Key':secret('control_key')})).json()['changed']
            tasks=[asyncio.create_task(c.post('/quotes',headers=headers('loadbot'),json={'amount_cents':100})) for _ in range(12)]
            await asyncio.sleep(0.02)
            r=await c.post('/payments',headers=headers(),json={'amount_cents':1,'recipient':'merchant'});assert r.status_code==200
            assert sum(x.status_code==429 for x in await asyncio.gather(*tasks))>=11
            assert (await c.get('/accounts',headers=headers())).json()['total_cents']==200000
    asyncio.run(run())

def test_login_and_role_separation(lab_env):
    from services.auth.main import app,attempts
    attempts.clear()
    with TestClient(app) as c:
        assert c.post('/token',json={'username':'alice','password':'bad'}).status_code==401
        assert c.post('/token',json={'username':'alice','password':secret('alice_password')}).status_code==200

def test_forged_and_expired_token(payment):
    with TestClient(payment.app) as c:
        forged=issue('alice','operator')+'x'
        assert c.get('/accounts',headers={'Authorization':'Bearer '+forged}).status_code==401
        expired=issue('alice','operator',now=1)
        assert c.get('/accounts',headers={'Authorization':'Bearer '+expired}).status_code==401
