"""scripts/check_lundi.py : logique et lecture seule, avec docker et HTTP simules."""
import importlib.util
import json
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PASSWORD='unit-test-grafana-secret-value'
def load():
    spec=importlib.util.spec_from_file_location('check_lundi',ROOT/'scripts/check_lundi.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m
ROWS=[{'Service':s,'State':'running','Health':'healthy' if s in ('db','payment') else ''} for s in ('db','payment','prometheus','grafana','loki')]+[{'Service':'init','State':'exited','ExitCode':0}]
HEALTH='200\n{"status":"alive"}\n'
METRICS='200\n# HELP x\nlab_active_work 0.0\nlab_capacity_denied_total 0.0\nlab_contained 0.0\nlab_duration_seconds_bucket{route="quotes",le="1.0"} 0.0\n'
TARGETS=json.dumps({'data':{'activeTargets':[{'labels':{'job':'payment'},'health':'up','scrapeUrl':'http://payment:8000/metrics','lastError':''}]}})
GF_HEALTH=(200,'{"database":"ok"}')
GF_DS=(200,'{"status":"OK","message":"Successfully queried the Prometheus API."}')
def run(m,monkeypatch,tmp_path,capsys,password=PASSWORD,ps=None,health=HEALTH,metrics=METRICS,targets=TARGETS,gf_health=GF_HEALTH,gf_ds=GF_DS):
    calls=[]
    def compose(f,*args):
        calls.append(args)
        if args[0]=='ps': return ps if ps is not None else json.dumps(ROWS)
        out={'payment':health if args[-1].endswith('/health') else metrics,'prometheus':targets}[args[2]]
        if isinstance(out,Exception): raise out
        return out
    def http(url,headers=None):
        return gf_health if url.endswith('/api/health') else gf_ds
    monkeypatch.setattr(m,'compose',compose); monkeypatch.setattr(m,'http',http)
    monkeypatch.setattr(m,'ROOT',tmp_path)  # never read a real .secrets during tests
    if password: monkeypatch.setenv('GRAFANA_PASSWORD',password)
    else: monkeypatch.delenv('GRAFANA_PASSWORD',raising=False)
    code=m.main([])
    out=capsys.readouterr().out
    assert PASSWORD not in out  # the admin password is never printed
    return code,out,calls

def test_healthy_stack_exits_zero_and_only_reads(monkeypatch,tmp_path,capsys):
    m=load()
    code,out,calls=run(m,monkeypatch,tmp_path,capsys)
    assert code==0 and '5/5 verifications OK' in out and 'ECHEC' not in out
    assert {c[0] for c in calls}<={'ps','exec'}   # no up/down/restart/stop...
def test_ndjson_output_of_compose_ps_is_understood(monkeypatch,tmp_path,capsys):
    m=load()
    code,out,_=run(m,monkeypatch,tmp_path,capsys,ps='\n'.join(json.dumps(r) for r in ROWS))
    assert code==0 and '5/5' in out
def test_stack_down_fails_loudly_on_every_step(monkeypatch,tmp_path,capsys):
    m=load()
    code,out,_=run(m,monkeypatch,tmp_path,capsys,ps='',health=m.Check('docker compose exec a echoue : service payment is not running'),
                   metrics=m.Check('docker compose exec a echoue : service payment is not running'),
                   targets=m.Check('docker compose exec a echoue : service prometheus is not running'),gf_health=(0,''))
    assert code==1 and out.count('ECHEC')>=4
    for name in ('db','payment','prometheus','grafana','loki'): assert name+' absent' in out
def test_container_not_running_or_unhealthy(monkeypatch,tmp_path,capsys):
    m=load()
    rows=[dict(r) for r in ROWS]; rows[1].update(State='exited',ExitCode=1); rows[0]['Health']='unhealthy'
    code,out,_=run(m,monkeypatch,tmp_path,capsys,ps=json.dumps(rows))
    assert code==1 and 'payment : etat exited (code 1)' in out and 'db : healthcheck unhealthy' in out
def test_health_not_200_or_not_json(monkeypatch,tmp_path,capsys):
    m=load()
    code,out,_=run(m,monkeypatch,tmp_path,capsys,health='503\n{"detail":"down"}\n')
    assert code==1 and 'GET /health a repondu 503' in out
    code,out,_=run(m,monkeypatch,tmp_path,capsys,health='200\n<html>\n')
    assert code==1 and 'non JSON' in out
def test_metrics_without_application_series(monkeypatch,tmp_path,capsys):
    m=load()
    code,out,_=run(m,monkeypatch,tmp_path,capsys,metrics='200\n# HELP x\npython_gc_objects_collected_total 1.0\n')
    assert code==1 and 'series applicatives absentes : lab_active_work' in out
def test_prometheus_target_down_or_missing(monkeypatch,tmp_path,capsys):
    m=load()
    down=json.dumps({'data':{'activeTargets':[{'labels':{'job':'payment'},'health':'down','scrapeUrl':'http://payment:8000/metrics','lastError':'connection refused'}]}})
    code,out,_=run(m,monkeypatch,tmp_path,capsys,targets=down)
    assert code==1 and 'cible non scrapee' in out and 'connection refused' in out
    code,out,_=run(m,monkeypatch,tmp_path,capsys,targets=json.dumps({'data':{'activeTargets':[]}}))
    assert code==1 and "aucune cible 'payment'" in out
def test_grafana_failures_have_a_reason(monkeypatch,tmp_path,capsys):
    m=load()
    code,out,_=run(m,monkeypatch,tmp_path,capsys,gf_ds=(200,'{"status":"ERROR","message":"dial tcp prometheus:9090: connection refused"}'))
    assert code==1 and 'datasource' in out and 'connection refused' in out
    code,out,_=run(m,monkeypatch,tmp_path,capsys,gf_ds=(401,'{"message":"Invalid username or password"}'))
    assert code==1 and 'authentification admin refusee' in out
    code,out,_=run(m,monkeypatch,tmp_path,capsys,gf_ds=(404,'{"message":"Data source not found"}'))
    assert code==1 and 'absente' in out
    code,out,_=run(m,monkeypatch,tmp_path,capsys,password=None)
    assert code==1 and 'mot de passe admin Grafana introuvable' in out
def test_grafana_password_read_from_the_secrets_file(monkeypatch,tmp_path,capsys):
    m=load()
    (tmp_path/'.secrets'/'runtime').mkdir(parents=True)
    (tmp_path/'.secrets'/'runtime'/'grafana_password').write_text(PASSWORD+'\n')
    code,out,_=run(m,monkeypatch,tmp_path,capsys,password=None)
    assert code==0
def test_script_source_contains_no_state_changing_operation():
    text=(ROOT/'scripts/check_lundi.py').read_text()
    assert not re.search(r"\b(POST|PUT|DELETE|PATCH)\b|[(,]\s*data=|method=",text)  # GET only, no request body
    subcommands=re.findall(r"compose\(compose_file,\s*'([\w-]+)'",text)
    assert len(subcommands)>=3 and set(subcommands)<={'ps','exec'}   # never up/down/restart/stop...
