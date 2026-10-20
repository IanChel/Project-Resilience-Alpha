"""Preuve du jalon de mercredi (carte W7) : la boucle complete tourne sans humain en moins de 60 secondes.
Lecture seule : ne demarre ni ne modifie rien, ne lance ni attaque ni observateur. Il lit la DERNIERE preuve ecrite par
`python scripts/acceptance.py` dans runtime/evidence/ et la juge. Code de sortie 0 si tout est OK, 1 sinon.
  python scripts/check_mercredi.py                      # derniere preuve, cible 60 s
  python scripts/check_mercredi.py --max-seconds 45     # la cible de jeudi
  python scripts/check_mercredi.py --file runtime/evidence/acceptance-1760900000.json"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STEPS=('detected','containing','verifying','recovered')
CAUSAL=('detected','accepted','containing','verifying','recovered')
class Check(Exception): pass
def latest(folder):
    """The newest acceptance-<epoch>.json, by the epoch in its name (not by file date, which a copy changes)."""
    found=[(int(m.group(1)),p) for p in Path(folder).glob('acceptance-*.json') for m in [re.fullmatch(r'acceptance-(\d+)\.json',p.name)] if m]
    if not found: raise Check(f'aucune preuve acceptance-*.json dans {folder} : lancer `python scripts/acceptance.py` pendant une attaque')
    return max(found)[1]
def load(path):
    try: evidence=json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError) as exc: raise Check(f'preuve illisible ({path}) : {exc}')
    if not isinstance(evidence,dict) or not isinstance(evidence.get('summary'),dict):
        raise Check("preuve sans bloc `summary` : produite par une ancienne version d'acceptance.py ; la refaire avec le script a jour")
    return evidence
def incidents(evidence):
    """Last snapshot of every incident the observer saw during the run."""
    seen={}
    for row in evidence.get('observations',[]):
        for incident in row.get('incidents',[]): seen[incident['id']]=incident
    return list(seen.values())
def check_loop(evidence,ctx):
    inc=evidence['summary']['incident']; steps={s['name']:s['at'] for s in inc['steps']}
    missing=[n for n in STEPS if steps.get(n) is None]
    if missing: raise Check('etapes absentes : '+', '.join(missing)+'. La boucle ne va pas de la detection a la transaction temoin.')
    if inc.get('status')!='recovered': raise Check(f'statut final {inc.get("status")!r}, attendu recovered')
    w=evidence['summary']['witness']
    if w.get('verdict')!='validated': raise Check(f'transaction temoin {w.get("verdict")!r}, attendue validated')
    return [f'detection, remediation lancee, healthcheck OK, transaction temoin {w.get("transaction_id")} validee (total du registre {w.get("total_cents")})']
def check_time(evidence,ctx):
    inc=evidence['summary']['incident']; total=inc.get('detection_to_recovered_s'); steps=inc['steps']
    if total is None: raise Check('temps detection -> service retabli absent de la preuve')
    at=[s['at'] for s in steps]
    if None in at: raise Check("horodatages d'etapes absents (voir l'etape 1) : le temps ne peut pas etre recalcule")
    if at!=sorted(at): raise Check('horodatages des etapes dans le desordre : '+', '.join(f'{s["name"]}={s["at"]}' for s in steps))
    recomputed=round(at[-1]-at[0],2)
    if abs(recomputed-total)>0.05: raise Check(f'incoherence : le total annonce ({total} s) differe des etapes ({recomputed} s)')
    limit=ctx['max_seconds']
    if not total<limit: raise Check(f'{total} s, la cible est sous {limit:g} s. Ou passe le temps : '+', '.join(f'{s["name"]} +{s["offset_s"]} s' for s in steps))
    lines=[f'{total} s de la detection a la transaction temoin (cible sous {limit:g} s) : '+', '.join(f'{s["name"]} +{s["offset_s"]} s' for s in steps)]
    if limit>45 and total>=45: lines.append('au-dessus de 45 s : la cible de jeudi est plus stricte')
    return lines
def check_no_human(evidence,ctx):
    problems=[]
    if evidence.get('passed') is not True: problems.append("l'observateur n'a pas juge l'execution reussie (passed=false)")
    seen=incidents(evidence)
    if not seen: problems.append("aucun incident observe : rien ne prouve que la reprise a ete declenchee par le systeme")
    for incident in seen:
        try: body=json.loads(incident.get('evidence') or '{}')
        except ValueError: body={}
        if incident.get('status')=='failed': problems.append(f'incident {incident["id"][:8]} en failed : la reprise a echoue')
        if isinstance(body,dict) and body.get('manual_review_required'): problems.append(f'incident {incident["id"][:8]} : manual_review_required (un humain est demande)')
        stages=incident.get('stages') or {}
        order=[stages[n] for n in CAUSAL if n in stages]
        if 'detected' not in stages or order!=sorted(order): problems.append(f'incident {incident["id"][:8]} : etapes hors ordre causal ou sans detection (cree a la main ?)')
    if problems: raise Check('; '.join(problems))
    return [f'{len(seen)} incident(s), aucun failed ni manual_review_required, detection avant prise en charge, observateur : passed']
def check_ban(evidence,ctx):
    # The IP ban is an OPTIONAL overlay (compose.ban.yaml, docs/06-SECURITE.md, decision 1). When it is off, the
    # autonomous loop is validated without it, so this step passes with a loud N/A rather than failing the milestone.
    # When it is on, it must really have been posted and the witness must still have succeeded.
    s=evidence['summary']; ban=s.get('ban'); w=s.get('witness') or {}
    if not isinstance(ban,dict): raise Check("aucune information de ban dans la preuve : le remediateur n'a rien consigne")
    if not ban.get('enabled'):
        return ['N/A : bannissement optionnel non active (compose.ban.yaml). La boucle est validee sans lui.',
                '  Pour la demo AVEC ban, relancer avec la surcouche et revalider cette etape (docs/06-SECURITE.md, decision 1).']
    if not ban.get('eligible'): raise Check("ban active mais aucune adresse eligible : le WAF n'a pas vu l'adresse du PC Attaquant, ou elle est exclue ("+'; '.join(f'{e["ip"]}: {e["reason"]}' for e in ban.get('excluded',[]))+') ; voir docs/06-SECURITE.md, decision 1')
    if not ban.get('applied'): raise Check(f'adresse eligible {ban["eligible"]} mais absente du fichier de ban apres le playbook : ban non pose')
    if w.get('verdict')!='validated': raise Check('ban pose mais transaction temoin non validee : le ban a pu bloquer la verification')
    return [f'ban pose sur {", ".join(ban["applied"])} (duree {ban.get("ttl_s")} s) ET transaction temoin validee']
def check_config(evidence,ctx):
    config=evidence['summary'].get('detector_config')
    if not isinstance(config,dict): raise Check("configuration du detecteur absente : sans elle la mesure n'est pas reproductible (/ops/ml illisible pendant l'execution ?)")
    c,nu=config.get('consecutive'),config.get('nu')
    if not isinstance(c,int) or c<1 or not isinstance(nu,(int,float)) or not 0<nu<=1: raise Check(f'configuration incomplete ou invalide : {config}')
    return [f'consecutive={c}, nu={nu:g}']
STEPS_LIST=[('La boucle est allee de la detection a la transaction temoin',check_loop),('Detection -> service retabli sous la cible',check_time),
            ('Aucune intervention humaine dans la trace',check_no_human),('Ban d\'IP (si active) pose ET transaction temoin validee',check_ban),
            ('Configuration du detecteur consignee',check_config)]
def head():
    try: return subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,timeout=10,check=True).stdout.strip()
    except (OSError,subprocess.SubprocessError): return None
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--evidence-dir',type=Path,default=ROOT/'runtime'/'evidence'); p.add_argument('--file',type=Path)
    p.add_argument('--max-seconds',type=float,default=60.0,help='cible detection -> service retabli (60 mercredi, 45 jeudi)')
    a=p.parse_args(argv); ctx={'max_seconds':a.max_seconds}
    try: path=a.file or latest(a.evidence_dir); evidence=load(path); source_error=None
    except Check as exc: path=a.file; evidence=None; source_error=str(exc)
    if evidence is not None:
        age=time.time()-path.stat().st_mtime if path.exists() else None
        print(f'Preuve lue : {path}'+(f' (ecrite il y a {age/60:.0f} min)' if age is not None else ''))
        version=(evidence['summary'].get('code_version') or {}); now=head()
        if version.get('commit') and now and version['commit']!=now: print(f'ATTENTION : preuve produite avec le commit {version["commit"][:8]}, le depot est a {now[:8]}')
        if version.get('dirty'): print('ATTENTION : la preuve a ete produite avec des modifications non commitees')
    passed=0
    for n,(title,fn) in enumerate(STEPS_LIST,1):
        try:
            if source_error: raise Check(source_error)
            detail=fn(evidence,ctx); ok,reason=True,None
        except Check as exc: detail,ok,reason=[],False,str(exc)
        except Exception as exc: detail,ok,reason=[],False,f'erreur inattendue {type(exc).__name__}: {exc}'
        passed+=ok; print(f'[{n}/{len(STEPS_LIST)}] {title} ... '+('OK' if ok else f'ECHEC : {reason}'))
        for line in detail: print('      '+line)
    print(f'\n{passed}/{len(STEPS_LIST)} verifications OK : jalon W7 '+('VALIDE (cote technique).' if passed==len(STEPS_LIST) else 'NON valide.'))
    print("Non verifiable par script : que PERSONNE n'a touche le clavier pendant l'execution, et la repetabilite (5 executions de suite : jeudi).")
    return 0 if passed==len(STEPS_LIST) else 1
if __name__=='__main__': sys.exit(main())
