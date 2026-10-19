"""Temporary source bans: what may be banned, and the ban list / expiry files the WAF reads.

The address to ban comes ONLY from the signed alert, where the detector measured it at the WAF's own peer
address. It never comes from a request header: a client that controls X-Forwarded-For could otherwise get any
address banned, including the proxy's, which would cut the whole service.

Safety nets, in order:
 1. only addresses inside BAN_NETWORKS (default: the lab hotspot subnet) can be banned, so internal Docker
    addresses, loopback and the campus are out by construction. The witness transaction leaves from the
    remediator container, which is never in that subnet;
 2. BAN_NEVER (default: the Host PC, which also runs the observer) is never banned;
 3. at most BAN_MAX_SOURCES addresses per alert;
 4. every ban expires (BAN_TTL_SECONDS); an active ban keeps its expiry, so replaying a ban changes nothing;
 5. best effort: a failure here must never fail the containment (see infra/ansible/contain.yml)."""
import ipaddress
import os
import time
from pathlib import Path
LIST='ban.list'       # one address per line: read by the WAF (ModSecurity @ipMatchFromFile)
EXPIRY='ban.expiry'   # "<address> <epoch>" per line: read by the upkeep, never by the WAF
def _networks(text):
    return [ipaddress.ip_network(part.strip(),strict=False) for part in text.split(',') if part.strip()]
def config(env=None):
    env=os.environ if env is None else env
    return {'enabled':env.get('BAN_ENABLED','').strip().lower() in ('1','true','yes'),'dir':Path(env.get('BAN_DIR') or '/bans'),
            'networks':_networks(env.get('BAN_NETWORKS') or '192.168.137.0/24'),'never':_networks(env.get('BAN_NEVER') or '192.168.137.1'),
            'ttl':int(env.get('BAN_TTL_SECONDS') or 300),'max':int(env.get('BAN_MAX_SOURCES') or 3)}
def check(value,cfg):
    """(address, None) if it may be banned, else (None, reason)."""
    if not isinstance(value,str): return None,'not a string'
    try: ip=ipaddress.ip_address(value.strip())
    except ValueError: return None,'not an IP address'
    if ip.version==6 and ip.ipv4_mapped: ip=ip.ipv4_mapped
    inside=[n for n in cfg['networks'] if n.version==ip.version and ip in n]
    if not inside: return None,'outside the lab network'
    if any(n.version==ip.version and ip in n for n in cfg['never']): return None,'protected address'
    if ip.version==4 and any(ip in (n.network_address,n.broadcast_address) for n in inside): return None,'network or broadcast address'
    return str(ip),None
def plan(sources,cfg=None):
    """What to ban for one alert. Never raises: any problem means "no ban", and says why."""
    try: cfg=cfg or config()
    except (ValueError,TypeError) as exc: return {'enabled':False,'requested':[],'eligible':[],'excluded':[],'note':f'ban configuration invalid: {exc}'}
    requested=sources[:20] if isinstance(sources,list) else []
    eligible=[]; excluded=[]
    for value in requested:
        address,reason=check(value,cfg)
        if address is None: excluded.append({'ip':str(value)[:64],'reason':reason})
        elif address not in eligible: eligible.append(address)
    for address in eligible[cfg['max']:]: excluded.append({'ip':address,'reason':'over the per-alert limit'})
    eligible=eligible[:cfg['max']]
    result={'enabled':cfg['enabled'],'requested':[str(v)[:64] for v in requested],'eligible':eligible if cfg['enabled'] else [],'excluded':excluded,'ttl_s':cfg['ttl']}
    if not cfg['enabled']: result['note']='bans disabled (BAN_ENABLED not set)'
    return result
def read_expiry(directory):
    """{address: expiry epoch} from the expiry file. Malformed lines are ignored."""
    found={}
    try: lines=(Path(directory)/EXPIRY).read_text(encoding='utf-8').splitlines()
    except OSError: return found
    for line in lines:
        parts=line.split()
        try:
            if len(parts)==2: found[str(ipaddress.ip_address(parts[0]))]=float(parts[1])
        except ValueError: continue
    return found
def merged(directory,new,ttl,now=None):
    """The full content of both files after adding `new`. Pure function of its inputs: expired bans are dropped,
    an active ban keeps its expiry, so the same call twice gives the same content (idempotent)."""
    now=time.time() if now is None else now
    current={ip:int(exp) for ip,exp in read_expiry(directory).items() if exp>now}
    for ip in new: current.setdefault(ip,int(now+ttl))
    return {'list':''.join(f'{ip}\n' for ip in sorted(current)),'expiry':''.join(f'{ip} {exp}\n' for ip,exp in sorted(current.items())),'active':sorted(current)}
def write(directory,content):
    """Atomic writes, expiry first: the WAF only ever reads the list."""
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    for name,text in ((EXPIRY,content['expiry']),(LIST,content['list'])):
        tmp=directory/(name+'.tmp'); tmp.write_text(text,encoding='utf-8'); tmp.replace(directory/name)
def read_list(directory):
    try: return {line.strip() for line in (Path(directory)/LIST).read_text(encoding='utf-8').splitlines() if line.strip()}
    except OSError: return set()
def prune(directory,now=None):
    """Drop expired bans from both files; returns the addresses removed. Writes only when something changed."""
    now=time.time() if now is None else now
    before=set(read_expiry(directory))|read_list(directory); content=merged(directory,[],0,now)
    removed=sorted(before-set(content['active']))
    if removed: write(directory,content)
    return removed
def applied(directory,addresses):
    """Which of `addresses` are really in the ban list now (proof read back from the file, not assumed)."""
    present=read_list(directory); return [a for a in addresses if a in present]
