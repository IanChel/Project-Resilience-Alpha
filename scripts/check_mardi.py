"""Preuve du jalon critique de mardi (carte M7) : le pic est MESURE dans Prometheus et le detecteur a produit
anomaly=true sur la meme fenetre. Lecture seule : ne demarre ni ne modifie rien, ne lance pas l'attaque.
On lance l'attaque a la main, puis on demande de verifier ce qui s'est passe :
  python scripts/check_mardi.py --last 120
  python scripts/check_mardi.py --start 2026-10-20T14:32:00+02:00 --end 2026-10-20T14:34:00+02:00
Les heures sont des secondes epoch ou de l'ISO 8601 avec fuseau ; --last est relatif a l'horloge du conteneur.
Tout passe par `docker compose exec` sur le detecteur (GET uniquement). Code de sortie 0 si tout est OK, 1 sinon.
La preuve est ecrite dans runtime/evidence/m7-proof-<UTC>.json, y compris en cas d'echec."""
import argparse
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from check_lundi import Check, as_json, compose, probe
ROOT=Path(__file__).resolve().parents[1]
CLOCK_SKEW_WARN_S=5
HINT_SERIES="Si aucun devis n'a ete emis depuis le demarrage de payment, la serie lab_requests_total{route=\"quotes\"} n'existe pas encore et le detecteur ne peut pas mesurer."
def anomaly_now(compose_file):
    status,body=probe(compose_file,'detector','http://localhost:8000/anomaly')
    if status!=200: raise Check(f'GET /anomaly a repondu {status}')
    data=as_json(body,'/anomaly')
    if not isinstance(data,dict) or 'anomaly' not in data or 'status' not in data: raise Check('/anomaly : reponse inattendue : '+body.strip()[:120])
    return data
def check_model_loaded(ctx):
    data=ctx['now']=anomaly_now(ctx['compose_file'])
    if data['status']=='waiting_for_trained_model': raise Check('aucun modele charge (status waiting_for_trained_model) : collecter la baseline puis entrainer, docs/05-ML-RAG.md')
    if data['status']!='monitoring': raise Check(f'le detecteur ne mesure pas (status {data["status"]}). '+HINT_SERIES)
    return [f'status monitoring, score {data["score"]:.4f}']
def check_at_rest(ctx):
    data=ctx.get('now')
    if data is None: raise Check('/anomaly illisible (voir etape 1)')
    if data['status']!='monitoring': raise Check(f'pas de mesure au repos (status {data["status"]})')
    if data['anomaly']: raise Check(f'anomaly=true au repos (score {data["score"]:.4f}) : attaque encore en cours, ou faux positif ; attendre la fin du trafic ou calibrer (docs/05-ML-RAG.md)')
    return [f'anomaly=false, score {data["score"]:.4f}']
def fetch_report(ctx):
    """One docker exec for both window checks; a failure is remembered so it is not retried."""
    if 'report_error' in ctx: raise ctx['report_error']
    if 'report' not in ctx:
        try:
            out=compose(ctx['compose_file'],'exec','-T','detector','python','-m','services.detector.window','report',*ctx['window_args'])
            ctx['report']=as_json(out.strip(),'rapport de fenetre'); ctx['host_time']=time.time()
        except Check as exc: ctx['report_error']=exc; raise
    return ctx['report']
def check_peak(ctx):
    report=fetch_report(ctx); prom=report['prometheus']
    if 'error' in prom: raise Check('Prometheus injoignable ou requete en echec : '+prom['error'])
    if prom['quote_rate'] is None and prom['active_work'] is None:
        raise Check('Prometheus ne renvoie aucune donnee sur la fenetre (cible payment down, fenetre hors retention de 2 jours, ou fenetre mal placee). '+HINT_SERIES)
    denied=prom['denied_increase']
    if not denied or denied<=0: raise Check("aucun rejet de capacite sur la fenetre : l'attaque n'a pas sature le service, ou la fenetre est mal placee")
    q=(prom['quote_rate'] or {}).get('peak'); a=(prom['active_work'] or {}).get('peak')
    lines=[f'rejets de capacite sur la fenetre : {denied:g}',f'pic quote_rate {q if q is None else round(q,2)}/s, active_work {a}']
    env=report['envelope']
    if not env: return lines+["enveloppe normale indisponible (baseline.json absent) : seuls les rejets ont ete verifies"]
    above=[]
    if q is not None and q>env['quote_rate_max']: above.append(f'quote_rate {q:.2f} > {env["quote_rate_max"]:.2f}')
    if a is not None and a>env['active_work_max']: above.append(f'active_work {a:g} > {env["active_work_max"]:g}')
    if not above: raise Check(f'aucun pic au-dessus de l\'enveloppe normale (quote_rate {q} <= {env["quote_rate_max"]:.2f}, active_work {a} <= {env["active_work_max"]:g})')
    return lines+['au-dessus de l\'enveloppe normale ('+f'{env["n"]} obs.) : '+', '.join(above)]
def check_detection(ctx):
    d=fetch_report(ctx)['detector']
    if d['observations']==0: raise Check('aucune observation journalisee sur la fenetre : detecteur arrete, modele non charge pendant la fenetre, ou fenetre/horloge fausse')
    if d['anomalous']==0: raise Check(f'{d["observations"]} observations mais aucune anormale (score minimal {d["min_score"]:.3f}, compteur max {d["max_consecutive"]}) : le modele ne reconnait pas cette attaque, ou la fenetre ne la couvre pas')
    alerts=f'{d["alerts_delivered"]} (premiere a +{d["first_alert_s"]} s)' if d['alerts_delivered'] else 'aucune (compteur sous le seuil de repetition)'
    return [f'{d["anomalous"]} observation(s) anormale(s) sur {d["observations"]}, premiere a +{d["first_anomalous_s"]} s du debut de fenetre, compteur max {d["max_consecutive"]}','alertes livrees : '+alerts]
def check_evidence(ctx):
    results=ctx['results']; report=ctx.get('report')
    skew=round(ctx['host_time']-report['now'],2) if report and 'host_time' in ctx else None
    stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()); folder=ctx['evidence_dir']
    try:
        folder.mkdir(parents=True,exist_ok=True); path=folder/f'm7-proof-{stamp}.json'
        path.write_text(json.dumps({'created_at':stamp,'created_at_epoch':time.time(),'milestone':'M7',
            'passed':all(r['ok'] for r in results),'window_args':ctx['window_args'],'window':(report or {}).get('window'),
            'checks':results,'anomaly_now':ctx.get('now'),'report':report,'clock_skew_host_minus_container_s':skew,
            'notes':['Prometheus peaks are measured, not read off a screen.','The detector verdict is computed with the rule of the alert counter (is_anomalous).',
                     'Not covered: the demonstration redone in front of the team, and zero false positives on sustained normal traffic (docs/05-ML-RAG.md, Calibration).']},indent=2))
    except OSError as exc: raise Check(f'preuve non ecrite : {exc}')
    lines=[f'preuve ecrite : {path}']
    if skew is not None and abs(skew)>CLOCK_SKEW_WARN_S: lines.append(f'ATTENTION : horloge hote et conteneur decalees de {skew} s ; preferer --last ou des heures en epoch lues dans WSL')
    return lines
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--last',type=float,help='les N dernieres secondes, selon l\'horloge du conteneur')
    p.add_argument('--start'); p.add_argument('--end')
    p.add_argument('--compose-file',type=Path,default=ROOT/'compose.yaml')
    p.add_argument('--evidence-dir',type=Path,default=ROOT/'runtime'/'evidence')
    a=p.parse_args(argv)
    if a.last is not None: window_args=['--last',f'{a.last:g}']
    elif a.start and a.end: window_args=['--start',a.start,'--end',a.end]
    else: p.error('donner --last, ou --start et --end')
    ctx={'compose_file':a.compose_file,'evidence_dir':a.evidence_dir,'window_args':window_args,'results':[]}
    steps=[('Detecteur : un modele entraine est charge (/anomaly)',check_model_loaded),
           ('Detecteur : au repos, /anomaly renvoie anomaly=false',check_at_rest),
           ('Prometheus : le pic d\'attaque est mesure sur la fenetre',check_peak),
           ('Detecteur : anomaly=true produit sur cette meme fenetre',check_detection),
           ('Preuve horodatee ecrite dans runtime/evidence/',check_evidence)]
    passed=0
    for n,(title,fn) in enumerate(steps,1):
        try: detail=fn(ctx); ok,reason=True,None
        except Check as exc: detail,ok,reason=[],False,str(exc)
        except Exception as exc: detail,ok,reason=[],False,f'erreur inattendue {type(exc).__name__}: {exc}'
        passed+=ok
        if n<len(steps): ctx['results'].append({'id':n,'title':title,'ok':ok,'reason':reason,'detail':detail})
        print(f'[{n}/{len(steps)}] {title} ... '+('OK' if ok else f'ECHEC : {reason}'))
        for line in detail: print('      '+line)
    print(f'\n{passed}/{len(steps)} verifications OK : jalon M7 '+('VALIDE (cote technique).' if passed==len(steps) else 'NON valide.'))
    print('Non verifiable par script : la demonstration refaite devant les 6, et zero faux positif sur un trafic normal soutenu (docs/05-ML-RAG.md, Calibration).')
    return 0 if passed==len(steps) else 1
if __name__=='__main__': sys.exit(main())
