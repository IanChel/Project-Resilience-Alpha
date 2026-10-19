"""Temporary source ban (carte W1): the address comes from the signed alert, internal addresses are never
banned, a replay changes nothing, and the witness transaction still succeeds while a ban is active."""
import asyncio
import hashlib
import hmac
import ipaddress
import json
import os
import time
import uuid
from pathlib import Path
import httpx
import pytest
import yaml
from fastapi.testclient import TestClient
import services.auth.main as auth
import services.remediator.main as remediator
from services.common.security import secret
from services.detector import sources
from services.detector.main import build_alert
from services.remediator import bans
ROOT=Path(__file__).resolve().parents[1]
ATTACKER='192.168.137.20'; HOST='192.168.137.1'
def cfg(**env): return bans.config({'BAN_ENABLED':'1','BAN_DIR':'/unused',**env})

# ---- what may be banned
def test_only_a_lab_address_that_is_not_the_host_can_be_banned():
    c=cfg()
    assert bans.check(ATTACKER,c)==(ATTACKER,None)
    assert bans.check(' 192.168.137.20 ',c)==(ATTACKER,None)
    assert bans.check('::ffff:192.168.137.20',c)==(ATTACKER,None)                  # mapped form of an eligible address
    for value,why in [(HOST,'protected address'),('192.168.137.0','network or broadcast address'),('192.168.137.255','network or broadcast address'),
                      ('172.18.0.5','outside the lab network'),('10.1.2.3','outside the lab network'),('8.8.8.8','outside the lab network'),
                      ('::1','outside the lab network'),('::ffff:172.18.0.5','outside the lab network'),
                      ('1.2.3.4, 192.168.137.20','not an IP address'),('192.168.137.20/24','not an IP address'),('','not an IP address'),
                      (None,'not a string'),(5,'not a string'),(['192.168.137.20'],'not a string')]:
        assert bans.check(value,c)==(None,why),value
def test_no_internal_address_is_ever_eligible():
    c=cfg(); internal=[]
    for net,step in (('172.16.0.0/12',1237),('10.0.0.0/8',7919),('127.0.0.0/8',60013),('169.254.0.0/16',97),('192.168.65.0/24',1),('100.64.0.0/10',4421)):
        n=ipaddress.ip_network(net); internal+=[str(n[i]) for i in range(0,n.num_addresses,step)]
    internal+=['192.168.137.1','::1','fe80::1','fd00::5']
    assert len(internal)>1000 and all(bans.check(a,c)[0] is None for a in internal)
def test_plan_keeps_eligible_addresses_and_explains_every_exclusion():
    p=bans.plan([ATTACKER,HOST,'172.18.0.5','junk',ATTACKER],cfg())
    assert p['eligible']==[ATTACKER] and p['enabled'] is True and p['ttl_s']==300
    assert {(e['ip'],e['reason']) for e in p['excluded']}=={(HOST,'protected address'),('172.18.0.5','outside the lab network'),('junk','not an IP address')}
def test_plan_caps_the_number_of_bans_per_alert():
    many=[f'192.168.137.{n}' for n in range(20,30)]
    p=bans.plan(many,cfg(BAN_MAX_SOURCES='3'))
    assert p['eligible']==many[:3] and len(p['excluded'])==7 and all(e['reason']=='over the per-alert limit' for e in p['excluded'])
def test_plan_never_raises_and_disabled_means_no_ban():
    off=bans.plan([ATTACKER],bans.config({}))
    assert off['eligible']==[] and off['enabled'] is False and 'disabled' in off['note']
    for bad in (None,'192.168.137.20',{'ip':ATTACKER},42,[[]],[{'x':1}]): assert bans.plan(bad,cfg())['eligible']==[]
def test_a_broken_ban_configuration_means_no_ban_not_a_crash(monkeypatch):
    monkeypatch.setenv('BAN_ENABLED','1'); monkeypatch.setenv('BAN_NETWORKS','not-a-network')
    p=bans.plan([ATTACKER]); assert p['eligible']==[] and 'configuration invalid' in p['note']
    monkeypatch.setenv('BAN_NETWORKS','192.168.137.0/24'); monkeypatch.setenv('BAN_TTL_SECONDS','soon')
    assert 'configuration invalid' in bans.plan([ATTACKER])['note']

# ---- the files: idempotent, expiring
def test_replaying_a_ban_changes_nothing(tmp_path):
    first=bans.merged(tmp_path,[ATTACKER],300,now=1000); bans.write(tmp_path,first)
    again=bans.merged(tmp_path,[ATTACKER],300,now=1200)            # replayed later, ban still active
    assert again==first and first['list']==f'{ATTACKER}\n' and first['expiry']==f'{ATTACKER} 1300\n'   # same content: the expiry is kept
    bans.write(tmp_path,again); assert bans.read_list(tmp_path)=={ATTACKER}
def test_bans_merge_and_expire(tmp_path):
    bans.write(tmp_path,bans.merged(tmp_path,['192.168.137.20'],300,now=1000))
    bans.write(tmp_path,bans.merged(tmp_path,['192.168.137.21'],300,now=1100))
    assert bans.read_list(tmp_path)=={'192.168.137.20','192.168.137.21'}
    assert bans.prune(tmp_path,now=1250)==[] and bans.prune(tmp_path,now=1350)==['192.168.137.20']   # 20 expired at 1300, 21 at 1400
    assert bans.read_list(tmp_path)=={'192.168.137.21'} and bans.prune(tmp_path,now=1500)==['192.168.137.21'] and bans.read_list(tmp_path)==set()
    assert (tmp_path/bans.LIST).read_text()=='' and not list(tmp_path.glob('*.tmp'))
def test_prune_writes_nothing_when_nothing_expired(tmp_path):
    bans.write(tmp_path,bans.merged(tmp_path,[ATTACKER],300,now=1000)); before=(tmp_path/bans.LIST).stat().st_mtime_ns
    assert bans.prune(tmp_path,now=1100)==[] and (tmp_path/bans.LIST).stat().st_mtime_ns==before     # no spurious WAF reload
def test_malformed_expiry_lines_are_ignored_and_applied_is_read_back(tmp_path):
    (tmp_path/bans.EXPIRY).write_text(f'garbage\n{ATTACKER} 9999999999\nnot-an-ip 5\n{HOST} soon\n')
    assert bans.read_expiry(tmp_path)=={ATTACKER:9999999999.0}
    bans.write(tmp_path,bans.merged(tmp_path,[],0,now=1)); assert bans.applied(tmp_path,[ATTACKER,'192.168.137.99'])==[ATTACKER]

# ---- the remediator: the address comes from the signed alert, never from a header
def signed(data):
    raw=json.dumps(data).encode()
    return {'content':raw,'headers':{'Content-Type':'application/json','X-Signature':hmac.new(secret('alert_key').encode(),raw,hashlib.sha256).hexdigest()}}
class FakeAnsible:
    """Stands for ansible-playbook: does what the two `copy` tasks of contain.yml do, from the extra vars."""
    returncode=0
    def __init__(self,args,write=True): self.args=args; self.write=write
    async def communicate(self):
        if '-e' in self.args and self.write:
            extra=json.loads(self.args[self.args.index('-e')+1]); folder=Path(os.environ['BAN_DIR'])
            (folder/'ban.expiry').write_text(extra['ban_expiry_content']); (folder/'ban.list').write_text(extra['ban_list_content'])
        return b'ok',b''
@pytest.fixture
def lab(tmp_path,monkeypatch):
    monkeypatch.setattr(remediator,'STORE',tmp_path/'incidents.sqlite')
    monkeypatch.setenv('BAN_ENABLED','1'); monkeypatch.setenv('BAN_DIR',str(tmp_path/'bans')); (tmp_path/'bans').mkdir()
    calls=[]
    async def fake_exec(*args,**kw): calls.append(list(args)); return FakeAnsible(list(args),write=getattr(fake_exec,'write',True))
    async def fake_verify(iid): return {'transaction_id':'tx-1','total_cents':200000}
    monkeypatch.setattr(remediator.asyncio,'create_subprocess_exec',fake_exec); monkeypatch.setattr(remediator,'business_verify',fake_verify)
    return SimpleLab(tmp_path,calls,fake_exec)
class SimpleLab:
    def __init__(self,tmp,calls,fake): self.tmp=tmp; self.calls=calls; self.fake=fake
    def incident(self,alert):
        iid=str(uuid.uuid4())
        with remediator.connection() as c: c.execute('INSERT INTO incidents VALUES(?,?,?,?,?)',(iid,'accepted',time.time(),time.time(),json.dumps(alert)))
        return iid
    def run(self,alert):
        iid=self.incident(alert); asyncio.run(remediator.recover(iid))
        with remediator.connection() as c: row=dict(c.execute('SELECT * FROM incidents WHERE id=?',(iid,)).fetchone())
        return row['status'],json.loads(row['evidence'])
def alert(sources_):
    return {'id':str(uuid.uuid4()),'issued_at':time.time(),'score':-0.5,'features':[9,4,5,5],'sources':sources_}
def extra_vars(call): return json.loads(call[call.index('-e')+1])
def test_the_ban_comes_from_the_signed_alert_only(lab):
    status,ev=lab.run(alert([ATTACKER,HOST,'172.18.0.5']))
    assert status=='recovered' and ev['transaction_id']=='tx-1'
    assert extra_vars(lab.calls[0])['ban_ips']==[ATTACKER]                               # the host and the internal address are not in it
    assert ev['ban']['eligible']==[ATTACKER] and ev['ban']['applied']==[ATTACKER] and len(ev['ban']['excluded'])==2
    assert bans.read_list(lab.tmp/'bans')=={ATTACKER}
def test_no_source_in_the_alert_means_no_ban_and_the_same_containment(lab):
    status,ev=lab.run({k:v for k,v in alert([]).items() if k!='sources'})
    assert status=='recovered' and '-e' not in lab.calls[0] and ev['ban']['eligible']==[] and 'applied' not in ev['ban']
def test_a_header_cannot_name_an_address_to_ban(lab):
    from services.common.security import issue
    spoofed={'X-Forwarded-For':ATTACKER,'X-Real-IP':ATTACKER,'Forwarded':f'for={ATTACKER}','X-Client-IP':ATTACKER}
    body=alert([])                                                                       # a real, signed alert that names NO source
    with TestClient(remediator.app) as client:
        reply=client.post('/alerts',**{**signed(body),'headers':{**signed(body)['headers'],**spoofed}})
        assert reply.status_code==202
        operator={'Authorization':'Bearer '+issue('alice','operator')}
        for _ in range(50):                                                              # let the real recovery finish
            incident=client.get('/status',headers=operator).json()['incidents'][0]
            if incident['status'] in ('recovered','failed'): break
            time.sleep(0.1)
    assert incident['status']=='recovered'
    assert '-e' not in lab.calls[0]                                                      # nothing was passed to the playbook to ban
    assert json.loads(incident['evidence'])['ban']['eligible']==[] and bans.read_list(lab.tmp/'bans')==set()
def test_a_replayed_ban_gives_the_same_playbook_input(lab):
    lab.run(alert([ATTACKER])); time.sleep(0.01); lab.run(alert([ATTACKER]))
    first,second=(extra_vars(c) for c in lab.calls)
    assert first['ban_list_content']==second['ban_list_content'] and first['ban_expiry_content']==second['ban_expiry_content']   # copy is then a no-op
def test_the_ban_never_breaks_the_containment(lab,monkeypatch):
    monkeypatch.setattr(bans,'merged',lambda *a,**k:(_ for _ in ()).throw(OSError('ban directory unreadable')))
    status,ev=lab.run(alert([ATTACKER]))
    assert status=='recovered' and '-e' not in lab.calls[0] and ev['ban']['eligible']==[] and 'ban preparation failed' in ev['ban']['note']
    monkeypatch.undo()
def test_a_ban_that_was_not_written_is_reported_as_not_applied(lab):
    lab.fake.write=False                                                                  # ansible "succeeds" but nothing reaches the file
    status,ev=lab.run(alert([ATTACKER]))
    assert status=='recovered' and ev['ban']['eligible']==[ATTACKER] and ev['ban']['applied']==[]
def test_broken_ban_configuration_still_contains(lab,monkeypatch):
    monkeypatch.setenv('BAN_NETWORKS','nonsense')
    status,ev=lab.run(alert([ATTACKER]))
    assert status=='recovered' and '-e' not in lab.calls[0] and ev['ban']['eligible']==[]
def test_bans_are_off_unless_enabled(lab,monkeypatch):
    monkeypatch.delenv('BAN_ENABLED')
    status,ev=lab.run(alert([ATTACKER]))
    assert status=='recovered' and '-e' not in lab.calls[0] and ev['ban']['enabled'] is False

# ---- detector -> alert
def test_the_alert_carries_the_sources_and_the_remediator_accepts_it(lab,monkeypatch):
    body=json.loads(build_alert(-0.4,[9.0,4.0,5.0,5.0],[ATTACKER]))
    assert body['sources']==[ATTACKER] and set(body)=={'id','issued_at','score','features','sources'}
    started=[]
    async def no_recover(iid): started.append(iid)
    monkeypatch.setattr(remediator,'recover',no_recover)
    with TestClient(remediator.app) as client:
        assert client.post('/alerts',**signed(body)).status_code==202
        assert client.post('/alerts',**signed({**body,'id':str(uuid.uuid4()),'sources':[ATTACKER]*3000})).status_code==413    # the size cap still holds
    assert remediator.alert_data(started[0])['sources']==[ATTACKER]
def loki(*series):
    async def get(query): return {'status':'success','data':{'result':[{'metric':{'ip':ip},'value':[0,str(n)]} for ip,n in series]}}
    return get
def test_top_sources_are_the_busiest_peers_above_the_threshold():
    run=lambda *s,env=None:asyncio.run(sources.top_sources(loki(*s),env or {}))
    assert run((ATTACKER,200),('192.168.137.30',120),('192.168.137.31',60),('192.168.137.32',10),('192.168.137.33',90))==[ATTACKER,'192.168.137.30','192.168.137.33']
    assert run((ATTACKER,49))==[] and run((ATTACKER,50))==[ATTACKER]
    assert run((ATTACKER,200),('192.168.137.30',120),env={'BAN_MAX_SOURCES':'1'})==[ATTACKER]
    assert run((ATTACKER,40),env={'BAN_MIN_REQUESTS':'30'})==[ATTACKER]
def test_top_sources_gives_nothing_on_any_problem():
    async def down(q): raise httpx.ConnectError('loki unreachable')
    async def bad_status(q): return {'status':'error'}
    async def junk(q): return {'status':'success','data':{'result':[{'metric':{'ip':'not-an-ip'},'value':[0,'99']},{'metric':{},'value':[0,'99']},{'value':[0,'x']},{'metric':{'ip':ATTACKER},'value':[0,'99']}]}}
    assert asyncio.run(sources.top_sources(down,{}))==[] and asyncio.run(sources.top_sources(bad_status,{}))==[]
    assert asyncio.run(sources.top_sources(junk,{}))==[ATTACKER]                         # one bad series does not hide a good one
    assert asyncio.run(sources.top_sources(loki((ATTACKER,99)),{'BAN_MAX_SOURCES':'many'}))==[]
def test_sources_are_read_from_the_waf_peer_not_from_a_header():
    assert '{service="wafaccess"}' in sources.QUERY and 'forwarded' not in sources.QUERY.lower() and 'x-real' not in sources.QUERY.lower()
    alloy=(ROOT/'infra/alloy/config.alloy').read_text()
    assert '/waflogs/access.log' in alloy and 'service = "wafaccess"' in alloy

# ---- the witness transaction while a ban is active
class Waf(httpx.AsyncBaseTransport):
    """In-memory WAF: refuses banned peers with a 403, forwards the rest to the real apps. 'auth' is the internal path."""
    def __init__(self,payment,peer,ban_dir): self.payment=payment; self.peer=peer; self.ban_dir=ban_dir
    async def handle_async_request(self,request):
        if request.url.host=='waf':
            if self.peer in bans.read_list(self.ban_dir): return httpx.Response(403,json={'detail':'RESILIENCE temporary source ban'},request=request)
            app,path={'/api/payments':(self.payment.app,'/payments'),'/api/accounts':(self.payment.app,'/accounts')}[request.url.path]
        else: app,path=auth.app,request.url.path
        forwarded=httpx.Request(request.method,request.url.copy_with(path=path),headers=request.headers,content=request.content)
        return await httpx.ASGITransport(app=app,client=(self.peer,40000)).handle_async_request(forwarded)
REMEDIATOR_IP='172.20.0.9'
@pytest.fixture
def waf(payment,tmp_path,monkeypatch):
    auth.attempts.clear(); folder=tmp_path/'bans'; folder.mkdir()
    monkeypatch.setenv('PUBLIC_URL','http://waf:8080'); monkeypatch.setenv('AUTH_URL','http://auth:8000')
    real=httpx.AsyncClient
    monkeypatch.setattr(remediator,'httpx',type('H',(),{'AsyncClient':staticmethod(lambda **kw:real(transport=Waf(payment,REMEDIATOR_IP,folder),**kw)),'HTTPError':httpx.HTTPError}))
    return payment,folder,real
def test_the_witness_transaction_succeeds_while_a_ban_is_active(waf):
    payment,folder,real=waf
    bans.write(folder,bans.merged(folder,[ATTACKER],300))                                # the attacker is banned
    async def run():
        async with real(transport=Waf(payment,ATTACKER,folder),base_url='http://waf:8080') as attacker:
            assert (await attacker.get('/api/accounts')).status_code==403                # the ban is really enforced by this WAF
        proof=await remediator.business_verify('ban-active')                             # the witness leaves from the remediator container
        assert proof['total_cents']==200000
    asyncio.run(run())
def test_banning_the_remediator_address_would_fail_the_witness_which_is_why_it_is_refused(waf,monkeypatch):
    payment,folder,real=waf
    async def no_wait(seconds): return None
    monkeypatch.setattr(remediator.asyncio,'sleep',no_wait)                              # skip the 15 one-second retries
    assert bans.plan([REMEDIATOR_IP],cfg())['eligible']==[]                              # no alert can ever make the plan include it
    bans.write(folder,bans.merged(folder,[REMEDIATOR_IP],300))                           # forced by hand: the hazard the plan prevents
    with pytest.raises(RuntimeError): asyncio.run(remediator.business_verify('ban-on-remediator'))

# ---- the playbook
def test_the_playbook_contains_first_and_bans_best_effort():
    play=yaml.safe_load((ROOT/'infra/ansible/contain.yml').read_text())[0]; tasks=play['tasks']; names=[t['name'] for t in tasks]
    assert names==['Enable the quotation admission policy','Temporary source ban','Verify the database readiness endpoint']   # containment first
    ban=tasks[1]
    assert ban['when']=='ban_ips | default([]) | length > 0' and 'rescue' in ban and ban['rescue'][0].get('ansible.builtin.debug')
    writes=ban['block']
    assert [list(t)[1] for t in writes]==['ansible.builtin.copy','ansible.builtin.copy']                                   # idempotent by checksum
    assert [t['ansible.builtin.copy']['dest'] for t in writes]==['{{ ban_dir }}/ban.expiry','{{ ban_dir }}/ban.list']      # expiry first, the WAF reads the list
    assert [t['ansible.builtin.copy']['content'] for t in writes]==['{{ ban_expiry_content }}','{{ ban_list_content }}']
    text=(ROOT/'infra/ansible/contain.yml').read_text()
    assert 'ansible.builtin.shell' not in text and 'ansible.builtin.command' not in text and 'no_log: true' in text
    assert not any(w in text.lower() for w in ('forwarded','http_x','headers.x','lookup(\'ansible.builtin.url'))        # no address from a request
def test_the_overlay_is_optional_and_does_not_widen_the_remediator():
    assert 'bans' not in (ROOT/'compose.yaml').read_text()                                                               # the base stack is untouched
    over=yaml.safe_load((ROOT/'compose.ban.yaml').read_text())['services']
    assert 'docker.sock' not in (ROOT/'compose.ban.yaml').read_text()
    assert over['waf-reload']['cap_add']==['KILL'] and over['waf-reload']['cap_drop']==['ALL'] and over['waf-reload']['network_mode']=='none'
    assert over['waf']['volumes'][0]=='bans:/bans:ro' and over['remediator']['environment']['BAN_ENABLED']=='1'
    assert 'REMOTE_ADDR' in (ROOT/'infra/waf/ra-ban.conf').read_text() and 'ipMatchFromFile /bans/ban.list' in (ROOT/'infra/waf/ra-ban.conf').read_text()
    assert 'compose.ban.yaml' in (ROOT/'scripts/package.py').read_text()
