import getpass
import os
from urllib.parse import urlsplit
import httpx
ALLOWED={'127.0.0.1','localhost','192.168.137.1'}
# Published port of the WAF on the Host PC. 8080 is taken there by another service, hence 8081 by default;
# it must match LAB_PORT in .env (compose.yaml). Inside the stack everything still talks to waf:8080.
def lab_port(env=None):
    raw=(env or os.environ).get('LAB_PORT') or '8081'
    try: port=int(raw)
    except ValueError: raise ValueError(f'LAB_PORT must be a port number, got {raw!r}') from None
    if not 1<=port<=65535: raise ValueError(f'LAB_PORT out of range: {port}')
    return port
def base_url(host='127.0.0.1',env=None):
    return f'http://{host}:{lab_port(env)}'
def validate_url(url,env=None):
    p=urlsplit(url); expected=lab_port(env)
    if p.scheme!='http' or p.hostname not in ALLOWED or p.port!=expected or p.path not in ('','/') or p.query or p.fragment or p.username or p.password:
        raise ValueError(f'Only http://192.168.137.1:{expected} or localhost:{expected} is allowed (LAB_PORT)')
    return url.rstrip('/')
def login(client,username):
    r=client.post('/auth/token',json={'username':username,'password':getpass.getpass(username+' lab password: ')})
    r.raise_for_status(); return {'Authorization':'Bearer '+r.json()['access_token']}
