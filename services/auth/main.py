import hmac
import time
from collections import defaultdict, deque
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from services.common.security import secret, issue
from services.common.audit import emit
app = FastAPI(title='RESILIENCE authentication')
attempts = defaultdict(deque)
class Login(BaseModel):
    username: str = Field(max_length=32)
    password: str = Field(max_length=128)
@app.get('/health')
def health():
    return {'status':'ok'}
@app.post('/token')
def token(body: Login, request: Request):
    # Bounded login budget. Proxy supplies no trusted arbitrary identity headers.
    key = request.client.host
    queue = attempts[key]
    now = time.monotonic()
    while queue and queue[0] < now-60: queue.popleft()
    if len(queue) >= 30: raise HTTPException(429, 'Login rate exceeded')
    queue.append(now)
    if body.username not in ('alice','loadbot'):
        raise HTTPException(401,'Bad credentials')
    if not hmac.compare_digest(body.password, secret(body.username+'_password')):
        emit('auth','login_failed',user=body.username)
        raise HTTPException(401,'Bad credentials')
    role = 'operator' if body.username=='alice' else 'loadbot'
    emit('auth','login_success',user=body.username)
    return {'access_token':issue(body.username,role),'token_type':'bearer'}
