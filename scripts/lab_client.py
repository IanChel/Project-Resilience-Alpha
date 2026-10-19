import getpass
from urllib.parse import urlsplit
import httpx
ALLOWED={'127.0.0.1','localhost','192.168.137.1'}
def validate_url(url):
    p=urlsplit(url)
    if p.scheme!='http' or p.hostname not in ALLOWED or p.port!=8080 or p.path not in ('','/') or p.query or p.fragment or p.username or p.password:
        raise ValueError('Only http://192.168.137.1:8080 or localhost:8080 is allowed')
    return url.rstrip('/')
def login(client,username):
    r=client.post('/auth/token',json={'username':username,'password':getpass.getpass(username+' lab password: ')})
    r.raise_for_status(); return {'Authorization':'Bearer '+r.json()['access_token']}
