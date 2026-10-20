"""Recette orchestrator — HOST side. Prepares the service, starts the observer, then runs the documented
checks, in a strict allowlist of operations. The ATTACK is NEVER launched here: a human launches attack_lab.py
on the ATTACKER PC. This script never runs attack_lab.py.

Sequence (docs/09-RECETTE-RENDU.md):
  1. confirm (attack stopped, no recette running, payment WILL restart)
  2. reset: delete ONLY /state/policy.json in payment (never a volume, a proof or the registry; never down -v)
  3. restart payment, then poll /api/ready for at most 35 s
  4. on failure/timeout: stop, show the error, DO NOT start the observer
  5. when ready: start acceptance.py on the host and print the "observer ready" line
  6. after acceptance: check_mardi.py over the attack window, then check_mercredi.py on that acceptance proof
  7. one distinct result per step: PASS / FAIL / NON VERIFIE, with the return code

Security: every operation is a fixed arg list (never a shell string, never a browser-supplied command/path);
only the whitelisted operations below run; a lock prevents two recettes at once; the observer is always stopped
cleanly; no password/token/key is ever printed. The alice password is handed to acceptance via LAB_PASSWORD_DIR
(a directory of files) so its value never passes through this script's output.
"""
import argparse
from datetime import datetime, timezone
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler
from lab_client import validate_url
ROOT=Path(__file__).resolve().parents[1]
NO_PROXY=build_opener(ProxyHandler({}))
COMPOSE=['docker','compose','-f',str(ROOT/'compose.yaml')]
LOCK=ROOT/'runtime'/'recette.lock'
READY_TIMEOUT_S=35
# The one python snippet the reset runs inside payment: deletes ONLY the containment policy. Fixed, no interpolation.
RESET_SNIPPET="from pathlib import Path; Path('/state/policy.json').unlink(missing_ok=True)"
class Step(Exception):
    def __init__(self,msg): super().__init__(msg); self.msg=msg

def run(argv,timeout=60,**kw):
    """Run a fixed argument LIST (never shell). Returns the CompletedProcess."""
    assert isinstance(argv,list) and all(isinstance(a,str) for a in argv),'operations are fixed arg lists, never strings'
    return subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=timeout,**kw)

# ---- allowlisted operations (each builds a fixed command) --------------------------------------------------
def op_reset_policy():   return COMPOSE+['exec','-T','payment','python','-c',RESET_SNIPPET]
def op_restart_payment():return COMPOSE+['restart','payment']
def op_acceptance(seconds,url):        return [sys.executable,str(ROOT/'scripts'/'acceptance.py'),'--seconds',str(seconds),'--url',url]
def op_check_mardi(last_seconds):      return [sys.executable,str(ROOT/'scripts'/'check_mardi.py'),'--last',f'{last_seconds:g}']
def op_check_mercredi(max_seconds,proof_path=None):
    argv=[sys.executable,str(ROOT/'scripts'/'check_mercredi.py'),'--max-seconds',str(max_seconds)]
    return argv+(['--file',str(proof_path)] if proof_path is not None else [])

def acceptance_proof_names():
    folder=ROOT/'runtime'/'evidence'
    return {p.name for p in folder.glob('acceptance-*.json')} if folder.is_dir() else set()

def find_new_acceptance_proof(before):
    folder=ROOT/'runtime'/'evidence'
    if not folder.is_dir(): return None
    candidates=[p for p in folder.glob('acceptance-*.json') if p.name not in before]
    return max(candidates,key=lambda p:p.stat().st_mtime) if candidates else None

# ---- lock: one recette at a time --------------------------------------------------------------------------
def acquire_lock():
    LOCK.parent.mkdir(parents=True,exist_ok=True)
    if LOCK.exists():
        try: pid=int(LOCK.read_text().strip())
        except (ValueError,OSError): pid=None
        if pid and _pid_alive(pid): raise Step(f'une recette est deja en cours (pid {pid}, {LOCK}). Attendre sa fin ou supprimer le verrou si le processus est mort.')
        LOCK.unlink(missing_ok=True)   # stale lock from a dead process
    LOCK.write_text(str(os.getpid()))
def release_lock():
    try: LOCK.unlink(missing_ok=True)
    except OSError: pass
def _pid_alive(pid):
    try:
        if os.name=='nt':
            out=subprocess.run(['tasklist','/FI',f'PID eq {pid}','/NH'],capture_output=True,text=True,timeout=10).stdout
            return str(pid) in out
        os.kill(pid,0); return True
    except (OSError,subprocess.SubprocessError): return False

# ---- the sequence ------------------------------------------------------------------------------------------
def confirm(auto):
    print('RECETTE — avant de lancer, confirmez :')
    print('  - l\'attaque precedente est ARRETEE sur le PC Attaquant ;')
    print('  - aucune autre recette n\'est en cours ;')
    print('  - le service `payment` VA REDEMARRER (le confinement est leve, le registre est conserve).')
    if auto: print('  [--yes] confirmation implicite.'); return True
    try: answer=input('Continuer ? [o/N] ').strip().lower()
    except EOFError: answer=''
    return answer in ('o','oui','y','yes')

def wait_ready(url,verbose=True):
    deadline=time.monotonic()+READY_TIMEOUT_S
    while time.monotonic()<deadline:
        if check_ready_once(url): return True
        if verbose: print('  payment pas encore pret...',flush=True)
        time.sleep(2)
    return False

def check_ready_once(url):
    """End-to-end readiness through the same published WAF URL acceptance will use."""
    try:
        with NO_PROXY.open(Request(url+'/api/ready',headers={'Accept':'application/json'}),timeout=3) as response:
            body=json.loads(response.read().decode('utf-8'))
            return response.status==200 and body.get('status')=='ready'
    except (HTTPError,URLError,TimeoutError,ValueError,json.JSONDecodeError):
        return False

def run_check(name,argv):
    """Run a check script; return (label, code, tail-of-output). A missing prerequisite reads as NON VERIFIE."""
    try: done=run(argv,timeout=180)
    except subprocess.TimeoutExpired: return (name,None,'NON VERIFIE : le controle n\'a pas rendu de resultat (timeout).')
    out=(done.stdout or '')+(done.stderr or '')
    verdict='PASS' if done.returncode==0 else 'FAIL'
    return (name,done.returncode,verdict+'\n'+_tail(out,20))
def _tail(text,n): return '\n'.join(('    '+l) for l in text.strip().splitlines()[-n:])

def _safe_result_lines(detail):
    """Keep short check output for the run record, redacting likely credential values."""
    lines=[]
    for line in detail.splitlines()[-20:]:
        line=re.sub(r'(?i)\b(password|token|secret|authorization)\b\s*[:=]\s*[^\s,;]+',r'\1=[REDACTED]',line)
        line=line.replace(str(ROOT/'.secrets'),'[secret-path]')
        lines.append(line[:500])
    return lines

def write_recipe_result(started_epoch,url,prep,results,proof=None):
    """Write a new, non-secret summary for this recipe; never overwrite acceptance/M7 evidence."""
    ended_epoch=time.time()
    tests=[]
    for name,code,detail in results:
        if name=='acceptance': verdict='PASS' if code==0 else ('NON VERIFIE' if code is None else 'FAIL')
        else: verdict='PASS' if code==0 else ('NON VERIFIE' if code is None else 'FAIL')
        lines=detail.splitlines()
        tests.append({'name':name,'verdict':verdict,'exit_code':code,
                      'summary':lines[0] if lines else verdict,'details':_safe_result_lines(detail)})
    overall='PASS' if prep and all(item.get('verdict')=='PASS' for item in prep) and all(t['verdict']=='PASS' for t in tests) else 'FAIL'
    report={'schema_version':1,'run_id':str(uuid.uuid4()),
            'started_at_utc':datetime.fromtimestamp(started_epoch,timezone.utc).isoformat().replace('+00:00','Z'),
            'ended_at_utc':datetime.fromtimestamp(ended_epoch,timezone.utc).isoformat().replace('+00:00','Z'),
            'started_at_epoch':started_epoch,'ended_at_epoch':ended_epoch,
            'duration_s':round(ended_epoch-started_epoch,3),'target':url,
            'attack_launched_by_runner':False,'status':overall,
            'preparation':prep,'checks':tests,
            'acceptance_evidence_file':proof.name if proof else None}
    folder=ROOT/'runtime'/'evidence'
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/f"recette-run-{int(started_epoch)}-{report['run_id'][:8]}.json"
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    os.replace(temp,path)
    # Machine-readable final marker lets the loopback dashboard display final results reliably.
    marker={'status':overall,'acceptance':next((t['verdict'] for t in tests if t['name']=='acceptance'),None),
            'check_mardi':next((t['verdict'] for t in tests if t['name']=='check_mardi'),None),
            'check_mercredi':next((t['verdict'] for t in tests if t['name']=='check_mercredi'),None),
            'result_file':path.name}
    print('RECETTE_RESULT_JSON '+json.dumps(marker,separators=(',',':')),flush=True)
    print(f'Récapitulatif JSON écrit : {path}',flush=True)
    return path

def recette(seconds,url,auto):
    try: url=validate_url(url)
    except ValueError as exc: raise Step('URL refusee : '+str(exc)) from None
    if not confirm(auto): print('Annule.'); return 2
    started_epoch=time.time()
    prep=[]
    results=[]
    print('\n[1/5] Reset : suppression de /state/policy.json (uniquement)')
    r=run(op_reset_policy(),timeout=30)
    if r.returncode!=0: raise Step('reset impossible : '+_tail((r.stderr or r.stdout),4).strip())
    prep.append({'name':'reset_policy','verdict':'PASS','exit_code':0})
    print('  OK : confinement leve')
    print('[2/5] Redemarrage de payment')
    restart=run(op_restart_payment(),timeout=60)
    if restart.returncode!=0: raise Step('redemarrage de payment en echec')
    prep.append({'name':'restart_payment','verdict':'PASS','exit_code':restart.returncode})
    print('[3/5] Attente de /api/ready (max %ds)'%READY_TIMEOUT_S)
    if not wait_ready(url): raise Step('WAF/payment ne repond pas /api/ready apres %ds : recette interrompue, observateur NON lance.'%READY_TIMEOUT_S)
    prep.append({'name':'waf_payment_ready','verdict':'PASS','exit_code':0})
    print('  OK : payment repond /ready')
    # 4. observer + the operator launches the attack by hand
    print('\n[4/5] Lancement de l\'observateur (acceptance.py) sur le PC Hote')
    env={**os.environ,'LAB_PASSWORD_DIR':str(ROOT/'.secrets'/'runtime')}   # value never printed; acceptance reads it
    started=time.monotonic()
    proofs_before=acceptance_proof_names()
    obs=subprocess.Popen(op_acceptance(seconds,url),cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
    code=None
    try:
        for line in obs.stdout:
            line=line.rstrip()
            if 'Start attack_lab.py' in line:   # the observer's ready signal (matched in its output, never launched here)
                print('\n  >>> Observateur pret — LANCEZ L\'ATTAQUE sur le PC Attaquant maintenant <<<\n',flush=True)
            elif '"incidents"' not in line:
                print('  [acceptance] '+line,flush=True)
        try: code=obs.wait(timeout=10)
        except subprocess.TimeoutExpired: code=None
    finally:
        if obs.poll() is None:   # stdout closed but the process lingers: always stop the observer cleanly
            obs.terminate()
            try: code=obs.wait(timeout=10)
            except subprocess.TimeoutExpired: obs.kill(); code=obs.wait()
        if code is None: code=obs.poll()
    results.append(('acceptance',code,'PASS' if code==0 else 'FAIL'))
    print('  acceptance : %s (code %s)'%('PASS' if code==0 else 'FAIL',code))
    # 5. checks, in the documented order and window
    print('\n[5/5] Controles')
    elapsed=time.monotonic()-started
    results.append(run_check('check_mardi',op_check_mardi(min(600,elapsed+40))))   # window covering the just-finished attack
    proof=find_new_acceptance_proof(proofs_before)
    if proof:
        results.append(run_check('check_mercredi',op_check_mercredi(60,proof)))
    else:
        results.append(('check_mercredi',None,'NON VERIFIE : acceptance n\'a produit aucune nouvelle preuve ; aucune preuve historique n\'a ete utilisee.'))
    print('\n===== RESULTATS =====')
    for name,code,detail in results:
        print(f'  {name:14} -> {detail.splitlines()[0]}  (code {code})')
        for extra in detail.splitlines()[1:]: print('      '+extra.strip())
    ok=all(code==0 for _,code,_ in results)
    print('\nRecette %s.'%('VALIDE (cote technique)' if ok else 'INCOMPLETE — voir les FAIL ci-dessus'))
    write_recipe_result(started_epoch,url,prep,results,proof)
    return 0 if ok else 1

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--seconds',type=int,default=70,help='duree d\'observation (5..120)')
    p.add_argument('--url',default='http://192.168.137.1:8081',help='URL du WAF hote a observer (adresse du laboratoire ; localhost est aussi accepte)')
    p.add_argument('--yes',action='store_true',help='sauter la confirmation interactive')
    a=p.parse_args(argv)
    if not 5<=a.seconds<=120: p.error('--seconds doit etre entre 5 et 120')
    try: acquire_lock()
    except Step as exc: print('ECHEC : '+exc.msg); return 1
    def _sig(*_): raise KeyboardInterrupt
    signal.signal(signal.SIGINT,_sig)
    try: return recette(a.seconds,a.url,a.yes)
    except Step as exc: print('ECHEC : '+exc.msg); return 1
    except KeyboardInterrupt: print('\nInterrompu — observateur arrete, aucune preuve fabriquee.'); return 130
    finally: release_lock()
if __name__=='__main__': sys.exit(main())
