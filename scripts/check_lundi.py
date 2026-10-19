"""Verification du jalon de lundi (cartes L3 et L7) sur une stack DEJA demarree.
Lecture seule : ne demarre, n'arrete et ne modifie rien. Code de sortie 0 si tout est OK, 1 sinon.
payment et prometheus ne publient aucun port sur l'hote : ils sont interroges avec
`docker compose exec` (GET uniquement). Grafana est joint sur 127.0.0.1:3000."""
import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EXPECTED=('db','payment','prometheus','grafana','loki')
REQUIRED_SERIES=('lab_active_work','lab_capacity_denied_total','lab_contained')
# Runs inside a container: prints the HTTP status, then the body. A non-2xx raises (exit 1).
PROBE='import sys,urllib.request as u\nr=u.urlopen(sys.argv[1],timeout=5)\nprint(r.status);print(r.read().decode())'
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never use a system proxy
class Check(Exception): pass
def compose(compose_file,*args):
    try: p=subprocess.run(['docker','compose','-f',str(compose_file),*args],cwd=ROOT,capture_output=True,text=True,timeout=30)
    except FileNotFoundError: raise Check('commande docker introuvable (lancer depuis WSL ou Docker Desktop)')
    except subprocess.TimeoutExpired: raise Check('docker compose ne repond pas (30 s)')
    if p.returncode:
        lines=[l for l in p.stderr.strip().splitlines() if l.strip()]
        raise Check('docker compose '+args[0]+' a echoue : '+(lines[-1][:200] if lines else 'code '+str(p.returncode)))
    return p.stdout
def http(url,headers=None):
    try:
        with OPENER.open(urllib.request.Request(url,headers=headers or {}),timeout=5) as r: return r.status,r.read().decode()
    except urllib.error.HTTPError as exc: return exc.code,exc.read().decode(errors='replace')
    except (urllib.error.URLError,OSError) as exc: raise Check(f'{url} injoignable : {getattr(exc,"reason",exc)}')
def as_json(text,what):
    try: return json.loads(text)
    except ValueError: raise Check(what+' : reponse non JSON : '+text.strip()[:120])
def probe(compose_file,service,url):
    out=compose(compose_file,'exec','-T',service,'python','-c',PROBE,url).split('\n',1)
    return int(out[0]),out[1] if len(out)>1 else ''
def check_containers(compose_file):
    text=compose(compose_file,'ps','--all','--format','json').strip()
    try: rows=json.loads(text) if text.startswith('[') else [json.loads(l) for l in text.splitlines() if l.strip()]
    except ValueError: raise Check('sortie de docker compose ps illisible : '+text[:120])
    by={r.get('Service'):r for r in rows}; problems=[]; detail=[]
    for name in EXPECTED:
        r=by.get(name)
        if not r: problems.append(f'{name} absent (docker compose up -d lance ?)'); continue
        state,health=r.get('State'),r.get('Health') or ''
        if state!='running': problems.append(f'{name} : etat {state} (code {r.get("ExitCode")})')
        elif health in ('unhealthy','starting'): problems.append(f'{name} : healthcheck {health}')
        else: detail.append(f'{name} : running'+(f' ({health})' if health else ''))
    if problems: raise Check('; '.join(problems))
    return detail
def check_health(compose_file):
    status,body=probe(compose_file,'payment','http://localhost:8000/health')
    if status!=200: raise Check(f'GET /health a repondu {status}')
    as_json(body,'/health')
    return ['payment GET /health -> 200 '+body.strip()]
def check_metrics(compose_file):
    status,body=probe(compose_file,'payment','http://localhost:8000/metrics')
    if status!=200: raise Check(f'GET /metrics a repondu {status}')
    names={l.split('{')[0].split(' ')[0] for l in body.splitlines() if l and not l.startswith('#')}
    missing=[s for s in REQUIRED_SERIES if s not in names]
    if missing: raise Check('series applicatives absentes : '+', '.join(missing))
    return [f'{len([n for n in names if n.startswith("lab_")])} noms de series lab_* exposes (dont '+', '.join(REQUIRED_SERIES)+')']
def check_scrape(compose_file):
    out=compose(compose_file,'exec','-T','prometheus','wget','-qO-','http://localhost:9090/api/v1/targets')
    targets=[t for t in as_json(out,'Prometheus /api/v1/targets')['data']['activeTargets'] if t['labels'].get('job')=='payment']
    if not targets: raise Check("aucune cible 'payment' dans Prometheus (infra/prometheus/prometheus.yml)")
    down=[f'{t["scrapeUrl"]} : {t["health"]} {t.get("lastError","")}'.strip() for t in targets if t['health']!='up']
    if down: raise Check('cible non scrapee : '+'; '.join(down))
    return [f'cible payment up ({t["scrapeUrl"]})' for t in targets]
def grafana_password():
    value=os.environ.get('GRAFANA_PASSWORD')
    path=ROOT/'.secrets'/'runtime'/'grafana_password'
    if not value and path.is_file(): value=path.read_text().strip()
    if not value: raise Check('mot de passe admin Grafana introuvable (variable GRAFANA_PASSWORD ou .secrets/runtime/grafana_password)')
    return value
def check_grafana(base,uid):
    status,body=http(base+'/api/health')
    if status!=200: raise Check(f'GET /api/health a repondu {status}')
    token=base64.b64encode(('admin:'+grafana_password()).encode()).decode()
    status,body=http(f'{base}/api/datasources/uid/{uid}/health',{'Authorization':'Basic '+token})
    if status==401: raise Check('authentification admin refusee (mot de passe different de celui du conteneur ?)')
    if status==404: raise Check(f"datasource '{uid}' absente (infra/grafana/provisioning/datasources/local.yml)")
    data=as_json(body,'datasource')
    if status!=200 or data.get('status')!='OK': raise Check(f"datasource '{uid}' injoignable : "+str(data.get('message',body))[:200])
    return ['Grafana repond (/api/health 200)',f"datasource '{uid}' joignable : "+str(data.get('message',''))[:100]]
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--compose-file',type=Path,default=ROOT/'compose.yaml')
    p.add_argument('--grafana-url',default='http://127.0.0.1:3000')
    p.add_argument('--datasource-uid',default='prometheus',help='uid provisionne de la datasource Prometheus')
    a=p.parse_args(argv); f=a.compose_file; base=a.grafana_url.rstrip('/')
    steps=[('Conteneurs Up ('+', '.join(EXPECTED)+')',lambda:check_containers(f)),
           ('payment : GET /health',lambda:check_health(f)),
           ('payment : GET /metrics (series applicatives)',lambda:check_metrics(f)),
           ('Prometheus : cible payment scrapee (up)',lambda:check_scrape(f)),
           ('Grafana : repond et datasource Prometheus joignable',lambda:check_grafana(base,a.datasource_uid))]
    passed=0
    for n,(title,fn) in enumerate(steps,1):
        try: detail=fn()
        except Check as exc: print(f'[{n}/{len(steps)}] {title} ... ECHEC : {exc}'); continue
        except Exception as exc: print(f'[{n}/{len(steps)}] {title} ... ECHEC : erreur inattendue {type(exc).__name__}: {exc}'); continue
        passed+=1; print(f'[{n}/{len(steps)}] {title} ... OK')
        for line in detail: print('      '+line)
    print(f'\n{passed}/{len(steps)} verifications OK : jalon de lundi '+('VALIDE (cote technique).' if passed==len(steps) else 'NON valide.'))
    print('Non verifiable par script : les 4 contrats valides par les 6 (docs/openapi/, docs/03-INTERFACES.md) et le Kanban.')
    return 0 if passed==len(steps) else 1
if __name__=='__main__': sys.exit(main())
