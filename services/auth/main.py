import hashlib
import hmac
import secrets
import smtplib
import ssl
import time
from collections import defaultdict, deque
from email.message import EmailMessage
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from services.common.security import secret, issue
from services.common.audit import emit
from services.auth.passwords import verify_password

app = FastAPI(title='RESILIENCE authentication')
attempts = defaultdict(deque)
operator_challenges = {}

class Login(BaseModel):
    username: str = Field(max_length=32)
    password: str = Field(max_length=128)

class OperatorLogin(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

class OperatorCode(BaseModel):
    challenge_id: str = Field(min_length=32, max_length=64)
    code: str = Field(pattern=r'^\d{6}$')

def check_budget(key, limit=30):
    queue = attempts[key]
    now = time.monotonic()
    while queue and queue[0] < now-60:
        queue.popleft()
    if len(queue) >= limit:
        raise HTTPException(429, 'Login rate exceeded')
    queue.append(now)

def send_operator_code(recipient, code):
    message = EmailMessage()
    message['Subject'] = 'Votre code de connexion Resilience Alpha'
    message['From'] = recipient
    message['To'] = recipient
    message.set_content(f'Votre code de vérification Resilience Alpha est : {code}\n\nIl expire dans 5 minutes. Si vous n’êtes pas à l’origine de cette demande, ignorez ce message.')
    context = ssl.create_default_context()
    with smtplib.SMTP('smtp.gmail.com', 587, timeout=15) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(recipient, secret('gmail_app_password', minimum_length=16))
        smtp.send_message(message)

def code_digest(challenge_id, code):
    key = secret('session_key').encode()
    return hmac.new(key, f'{challenge_id}:{code}'.encode(), hashlib.sha256).hexdigest()

@app.get('/health')
def health():
    return {'status':'ok'}

@app.post('/token')
def token(body: Login, request: Request):
    # This legacy endpoint is retained for the Alice/loadbot lab scripts and internal automation.
    check_budget(request.client.host)
    if body.username not in ('alice','loadbot'):
        raise HTTPException(401,'Bad credentials')
    if not hmac.compare_digest(body.password, secret(body.username+'_password')):
        emit('auth','login_failed',user=body.username)
        raise HTTPException(401,'Bad credentials')
    role = 'operator' if body.username=='alice' else 'loadbot'
    emit('auth','login_success',user=body.username)
    return {'access_token':issue(body.username,role),'token_type':'bearer'}

@app.post('/operator/challenge')
def operator_challenge(body: OperatorLogin, request: Request):
    check_budget('operator:'+request.client.host, limit=10)
    expected_email = secret('operator_email', minimum_length=3).strip().casefold()
    password_hash = secret('operator_password_hash')
    if not hmac.compare_digest(body.email.strip().casefold(), expected_email) or not verify_password(body.password, password_hash):
        emit('auth','operator_login_failed')
        raise HTTPException(401, 'Bad credentials')
    now = time.monotonic()
    for key, value in list(operator_challenges.items()):
        if value['expires'] <= now:
            operator_challenges.pop(key, None)
    if len(operator_challenges) >= 1000:
        raise HTTPException(503, 'Too many pending verification requests')
    challenge_id = secrets.token_urlsafe(32)
    code = f'{secrets.randbelow(1_000_000):06d}'
    operator_challenges[challenge_id] = {'digest':code_digest(challenge_id, code), 'expires':now+300, 'attempts':0}
    try:
        send_operator_code(expected_email, code)
    except (OSError, smtplib.SMTPException, ssl.SSLError) as exc:
        operator_challenges.pop(challenge_id, None)
        emit('auth','operator_email_failed',error_type=type(exc).__name__)
        raise HTTPException(503, 'Could not send verification email') from None
    emit('auth','operator_code_sent')
    return {'challenge_id':challenge_id,'message':'Verification code sent'}

@app.post('/operator/verify')
def operator_verify(body: OperatorCode):
    challenge = operator_challenges.get(body.challenge_id)
    if not challenge or challenge['expires'] <= time.monotonic():
        operator_challenges.pop(body.challenge_id, None)
        raise HTTPException(401, 'Invalid or expired verification code')
    challenge['attempts'] += 1
    valid = hmac.compare_digest(challenge['digest'], code_digest(body.challenge_id, body.code))
    if not valid:
        if challenge['attempts'] >= 5:
            operator_challenges.pop(body.challenge_id, None)
        emit('auth','operator_code_failed')
        raise HTTPException(401, 'Invalid or expired verification code')
    operator_challenges.pop(body.challenge_id, None)
    emit('auth','operator_login_success',user='alice')
    return {'access_token':issue('alice','operator'),'token_type':'bearer'}
