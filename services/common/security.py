"""Lab-only signed session tokens. No external identity provider or banking data."""
import base64
import binascii
import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from fastapi import Header, HTTPException

def secret(name):
    path = Path(os.getenv('SECRETS_DIR', '/run/secrets')) / name
    value = path.read_text().strip()
    if len(value) < 24:
        raise RuntimeError(f'Secret too short: {name}')
    return value

def b64(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')

def issue(user, role, now=None):
    payload = b64(json.dumps({'sub': user, 'role': role, 'exp': int(now or time.time())+3600,
                              'aud': 'resilience-lab'}, sort_keys=True).encode())
    return payload+'.'+b64(hmac.new(secret('session_key').encode(), payload.encode(), hashlib.sha256).digest())

def verify(token, now=None):
    try:
        payload, signature = token.split('.')
        expected = b64(hmac.new(secret('session_key').encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError('signature')
        data = json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
        if data['exp'] <= (now or time.time()) or data['aud'] != 'resilience-lab':
            raise ValueError('expired')
        if data['sub'] not in ('alice', 'loadbot') or data['role'] not in ('operator','loadbot'):
            raise ValueError('identity')
        return data
    except (ValueError, KeyError, TypeError, binascii.Error, UnicodeDecodeError):
        raise HTTPException(401, 'Invalid or expired session')

def identity(authorization: str = Header(default='')):
    if not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Bearer session required')
    return verify(authorization[7:])

def operator(authorization: str = Header(default='')):
    user = identity(authorization)
    if user['role'] != 'operator':
        raise HTTPException(403, 'Operator required')
    return user

def require_internal(value, name):
    if not hmac.compare_digest(value or '', secret(name)):
        raise HTTPException(403, 'Internal authorization required')
