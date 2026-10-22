"""Recette runner — HOST side. Prepares the service, starts the observer, then runs the documented
checks, in a strict allowlist of operations. The ATTACK is NEVER launched here: a human launches attack_lab.py
on the ATTACKER PC. This script never runs attack_lab.py.

Two modes, chosen with --mode:
  protected (default) the recette as documented: the remediator answers the alert and the recovery is judged.
  control             an essai temoin: the detector still measures, alerts and journals, but the remediator
                      applies NO containment to incidents during the bounded observation window, so the team can see what the quote load does
                      WITHOUT the automatic response. The window is armed on the remediator with an operator
                      session, is bounded in time, and is ended again in a finally -- including when a step
                      fails. A control trial is NEVER a PASS: it inhibits the very recovery the PASS criteria
                      check, so it is reported under its own status (see control_trial_status).

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
from lab_client import validate_url, password_for
ROOT=Path(__file__).resolve().parents[1]
NO_PROXY=build_opener(ProxyHandler({}))
COMPOSE=['docker','compose','-f',str(ROOT/'compose.yaml')]
LOCK=ROOT/'runtime'/'recette.lock'
READY_TIMEOUT_S=35
# The one python snippet the reset runs inside payment: deletes ONLY the containment policy. Fixed, no interpolation.
RESET_SNIPPET="from pathlib import Path; Path('/state/policy.json').unlink(missing_ok=True)"
MODES=('protected','control')
# The directory of password FILES (never a value in the environment: a value shows up in process listings).
# It is handed to the observer, and read by this script's own operator login when a control trial is armed.
PASSWORD_DIR=ROOT/'.secrets'/'runtime'
def password_env(): return {**os.environ,'LAB_PASSWORD_DIR':str(PASSWORD_DIR)}
# Margin added on top of the observation window when asking for a control trial: it covers the time the
# operator takes to walk to the ATTACKER PC and start the attack, plus the checks. The remediator clamps the
# request again against its own hard bounds, so this value can never widen the window beyond TRIAL_MAX_S.
TRIAL_MARGIN_S=120
TRIAL_MIN_S=5
TRIAL_MAX_S=300
# Outcomes of a CONTROL TRIAL. None of them is PASS: PASS belongs to the protected recette alone.
CONTROL_IMPACT='CONTROL_IMPACT_OBSERVED'
CONTROL_NO_IMPACT='CONTROL_NO_IMPACT'
CONTROL_NOT_INHIBITED='CONTROL_NOT_INHIBITED'
# acceptance.py and check_mercredi.py both verify a RECOVERY. A control trial inhibits it on purpose, so they
# are expected to report FAIL and that FAIL must not be read as a broken lab. Their criteria are NOT changed.
CONTROL_EXPECTED_FAILURES=('acceptance','check_mercredi')
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

def trial_seconds(observation_seconds):
    """The window the launcher asks for, derived from the CURRENT recette duration and clamped to what the
    remediator accepts. Never a caller-chosen, open-ended value."""
    return min(TRIAL_MAX_S,max(TRIAL_MIN_S,int(observation_seconds)+TRIAL_MARGIN_S))

def op_token(url):
    """An operator session for the control-trial window, obtained exactly as the observer does: the password
    comes from LAB_PASSWORD_DIR (a directory of files) and its value never reaches this script's output."""
    body=json.dumps({'username':'alice','password':password_for('alice',password_env())}).encode()
    request=Request(url+'/auth/token',data=body,headers={'Content-Type':'application/json'},method='POST')
    with NO_PROXY.open(request,timeout=8) as response:
        return json.loads(response.read().decode('utf-8'))['access_token']

def trial_call(url,token,payload):
    """One fixed call to the remediator's control-trial window, through the published WAF URL. Returns the
    window state. Only `start` (explicit confirmation, bounded duration) and `stop` exist."""
    request=Request(url+'/ops/control-trial',data=json.dumps(payload).encode(),
                    headers={'Content-Type':'application/json','Authorization':'Bearer '+token},method='POST')
    with NO_PROXY.open(request,timeout=8) as response:
        return json.loads(response.read().decode('utf-8'))

def arm_trial(url,token,seconds):
    return trial_call(url,token,{'action':'start','confirmed':True,'seconds':seconds})
def end_trial(url,token):
    return trial_call(url,token,{'action':'stop'})

def end_control_trial(url,token,previous=None,quiet=False):
    """End the trial and report the window as the SERVICE sees it. Safe to call twice: `stop` on a window that
    is already closed just returns its state. A failure is announced, never swallowed -- the remediator still
    closes the window on its own deadline, so remediation comes back
    even if this host process dies here."""
    if token is None: return previous
    try:
        state=end_trial(url,token)
        if not quiet: print('  Remediation reactivee (fenetre : %s)'%(state.get('closed_reason') or 'deja fermee'),flush=True)
        return state
    except (OSError,TimeoutError,ValueError,KeyError,json.JSONDecodeError) as exc:
        print('  ATTENTION : fin d\'essai temoin non confirmee (%s). La remediation revient a l\'echeance de '
              'la fenetre (au plus %gs) ou au redemarrage du remediateur.'%(type(exc).__name__,TRIAL_MAX_S),flush=True)
        return {**(previous or {}),'closed_confirmed':False,'close_error':type(exc).__name__}

def new_tally():
    return {'probes':0,'payment_200':0,'payment_503':0,'first_refused_at':None,'incident_status':{}}

def tally_observation(line,tally):
    """Count what the observer's OWN probe rows report, as they stream past: the user-visible impact and the
    last status of each incident it saw. Nothing is read back from a proof file for this."""
    if '"payment_status"' not in line and '"incidents"' not in line: return tally
    try: row=json.loads(line)
    except ValueError: return tally
    if not isinstance(row,dict): return tally
    status=row.get('payment_status')
    if status is not None:
        tally['probes']+=1
        if status==503:
            tally['payment_503']+=1
            if tally['first_refused_at'] is None: tally['first_refused_at']=row.get('at')
        elif status==200: tally['payment_200']+=1
    for incident in row.get('incidents') or []:
        if isinstance(incident,dict) and incident.get('id'):
            tally['incident_status'][incident['id']]=incident.get('status')
    return tally

def tally_summary(tally):
    """The observed impact, as counts only: no transaction, no identity, nothing invented."""
    tally=tally or new_tally()
    return {'probes':tally['probes'],'payment_refused_503':tally['payment_503'],
            'payment_served_200':tally['payment_200'],'first_refused_at':tally['first_refused_at'],
            'incident_statuses':sorted({s for s in tally['incident_status'].values() if s}),
            'note':'Paiements fictifs refuses pendant la fenetre = impact de la charge SANS remediation. '
                   'Ce n est pas une reprise.'}

def control_trial_status(results,tally):
    """The outcome of a CONTROL TRIAL, deliberately distinct from the protected recette's PASS/FAIL.

    The PASS criteria of acceptance.py, check_mardi.py and check_mercredi.py are untouched. acceptance and
    check_mercredi verify a RECOVERY, which this mode inhibits on purpose: their FAIL is expected here and is
    listed in `expected_failures`. What the trial is actually asked to show is read from its own two signals:
      - the remediation really did NOT apply (no incident went past `observed`), else the premise broke and
        the run is reported CONTROL_NOT_INHIBITED instead of being quietly accepted;
      - the quote load really had an effect: capacity rejections measured by check_mardi, or fictitious
        payments refused (503) under the observer's own probe.
    A refused payment is the IMPACT of the load without remediation; it is never a successful recovery.
    """
    remediated=sorted({s for s in (tally.get('incident_status') or {}).values()
                       if s in ('containing','verifying','recovered')})
    if remediated: return CONTROL_NOT_INHIBITED
    by_name={name:code for name,code,_ in results}
    if by_name.get('check_mardi')==0 or tally.get('payment_503',0)>0: return CONTROL_IMPACT
    return CONTROL_NO_IMPACT

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
def confirm(auto,mode='protected'):
    print('RECETTE — avant de lancer, confirmez :')
    print('  - l\'attaque precedente est ARRETEE sur le PC Attaquant ;')
    print('  - aucune autre recette n\'est en cours ;')
    print('  - le service `payment` VA REDEMARRER (le confinement est leve, le registre est conserve).')
    if mode=='control':
        print('  ESSAI TEMOIN SANS REMEDIATION :')
        print('  - le detecteur continue de mesurer, d\'alerter et de journaliser ;')
        print('  - le remediateur n\'appliquera AUCUN confinement aux incidents pendant la fenetre bornee ;')
        print('  - WAF, MFA, limitation des essais de connexion et autres defenses restent ACTIFS ;')
        print('  - la remediation est reactivee a la fin de l\'essai, a l\'echeance, ou si ce lanceur echoue ;')
        print('  - ce n\'est pas une recette protegee : aucun resultat ne sera marque PASS.')
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

def is_no_incident_observation(results):
    """Recognize a completed quiet observation, distinct from an attack-recovery failure.

    Require all three independent signals from the attack-oriented checks: acceptance found no
    recoverable incident, M7 saw no capacity rejections and no anomalous detector observations,
    and the recovery check found no incident. Any unrelated failure remains a real FAIL.
    """
    by_name={name:(code,detail.casefold()) for name,code,detail in results}
    acceptance=by_name.get('acceptance')
    mardi=by_name.get('check_mardi')
    mercredi=by_name.get('check_mercredi')
    if not acceptance or not mardi or not mercredi:
        return False
    return (
        acceptance[0] != 0
        and mardi[0] != 0
        and "aucun rejet de capacite sur la fenetre" in mardi[1]
        and re.search(r"\d+ observations mais aucune anormale", mardi[1]) is not None
        and mercredi[0] != 0
        and "aucun incident observe" in mercredi[1]
    )

def _safe_result_lines(detail):
    """Keep short check output for the run record, redacting likely credential values."""
    lines=[]
    for line in detail.splitlines()[-20:]:
        line=re.sub(r'(?i)\b(password|token|secret|authorization)\b\s*[:=]\s*[^\s,;]+',r'\1=[REDACTED]',line)
        line=line.replace(str(ROOT/'.secrets'),'[secret-path]')
        lines.append(line[:500])
    return lines

def write_recipe_result(started_epoch,url,prep,results,proof=None,mode='protected',tally=None,trial=None):
    """Write a new, non-secret summary for this recipe; never overwrite acceptance/M7 evidence.
    The MODE and, for a control trial, the observed impact are recorded, so the two kinds of run can never be
    confused when the summaries are read back."""
    ended_epoch=time.time()
    tests=[]
    for name,code,detail in results:
        if name=='acceptance': verdict='PASS' if code==0 else ('NON VERIFIE' if code is None else 'FAIL')
        else: verdict='PASS' if code==0 else ('NON VERIFIE' if code is None else 'FAIL')
        lines=detail.splitlines()
        tests.append({'name':name,'verdict':verdict,'exit_code':code,
                      'summary':lines[0] if lines else verdict,'details':_safe_result_lines(detail)})
    prep_ok=bool(prep) and all(item.get('verdict')=='PASS' for item in prep)
    if mode=='control':
        # Judged on the trial's own signals, and NEVER a PASS: the criteria of the three check scripts are
        # untouched, so the two that verify a recovery report an expected FAIL here.
        overall=control_trial_status(results,tally or new_tally()) if prep_ok else 'FAIL'
    else:
        all_pass=prep_ok and all(t['verdict']=='PASS' for t in tests)
        quiet_observation=is_no_incident_observation(results)
        overall='PASS' if all_pass else ('NO_INCIDENT' if quiet_observation else 'FAIL')
    report={'schema_version':1,'run_id':str(uuid.uuid4()),
            'started_at_utc':datetime.fromtimestamp(started_epoch,timezone.utc).isoformat().replace('+00:00','Z'),
            'ended_at_utc':datetime.fromtimestamp(ended_epoch,timezone.utc).isoformat().replace('+00:00','Z'),
            'started_at_epoch':started_epoch,'ended_at_epoch':ended_epoch,
            'duration_s':round(ended_epoch-started_epoch,3),'target':url,
            'attack_launched_by_runner':False,'status':overall,
            'mode':mode,'remediation_inhibited':mode=='control',
            'control_trial':trial if mode=='control' else None,
            'observed_impact':tally_summary(tally) if mode=='control' else None,
            'expected_failures':list(CONTROL_EXPECTED_FAILURES) if mode=='control' else [],
            'preparation':prep,'checks':tests,
            'acceptance_evidence_file':proof.name if proof else None}
    folder=ROOT/'runtime'/'evidence'
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/f"recette-run-{int(started_epoch)}-{report['run_id'][:8]}.json"
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    os.replace(temp,path)
    # Machine-readable final marker lets the loopback dashboard display final results reliably.
    marker={'status':overall,'mode':mode,
            'acceptance':next((t['verdict'] for t in tests if t['name']=='acceptance'),None),
            'check_mardi':next((t['verdict'] for t in tests if t['name']=='check_mardi'),None),
            'check_mercredi':next((t['verdict'] for t in tests if t['name']=='check_mercredi'),None),
            'result_file':path.name}
    print('RECETTE_RESULT_JSON '+json.dumps(marker,separators=(',',':')),flush=True)
    print(f'Récapitulatif JSON écrit : {path}',flush=True)
    return path

def recette(seconds,url,auto,mode='protected'):
    try: url=validate_url(url)
    except ValueError as exc: raise Step('URL refusee : '+str(exc)) from None
    if mode not in MODES: raise Step('mode inconnu : '+str(mode))
    if not confirm(auto,mode): print('Annule.'); return 2
    started_epoch=time.time()
    prep=[]
    results=[]
    tally=new_tally()
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
    return _observe_and_check(seconds,url,mode,prep,results,tally,started_epoch)

def _observe_and_check(seconds,url,mode,prep,results,tally,started_epoch):
    """Steps 4 and 5, plus the whole life of a control-trial window: armed here, and ended here in a finally
    so no path out of this function can leave the remediation inhibited."""
    trial=None; token=None; closed=False
    try:
        # The clean state above is the reset the protected recette already uses; the window is armed only once
        # the service answers /api/ready, so the trial covers the observation and not the preparation.
        if mode=='control':
            print('\n[essai temoin] Inhibition de la remediation automatique pendant la fenetre bornee')
            window=trial_seconds(seconds)
            try:
                token=op_token(url)
                trial=arm_trial(url,token,window)
            except (OSError,TimeoutError,ValueError,KeyError,json.JSONDecodeError) as exc:
                raise Step('essai temoin impossible a armer (%s) : la remediation reste ACTIVE et '
                           'l\'observateur n\'a PAS ete lance.'%type(exc).__name__) from None
            if not trial.get('active'):
                raise Step('le remediateur n\'a pas arme l\'essai temoin : la remediation reste ACTIVE.')
            prep.append({'name':'control_trial_armed','verdict':'PASS','exit_code':0,
                         'window_s':window,'max_seconds':trial.get('max_seconds')})
            print('  OK : remediation inhibee pour %gs au plus (plafond du service : %gs)'
                  %(window,trial.get('max_seconds') or 0),flush=True)
        # 4. observer + the operator launches the attack by hand
        print('\n[4/5] Lancement de l\'observateur (acceptance.py) sur le PC Hote')
        env=password_env()   # the directory, not the value; acceptance reads the file itself
        started=time.monotonic()
        proofs_before=acceptance_proof_names()
        obs=subprocess.Popen(op_acceptance(seconds,url),cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
        code=None
        try:
            for line in obs.stdout:
                line=line.rstrip()
                tally_observation(line,tally)   # the impact and the incident statuses, from the observer's own rows
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
        if mode=='control':
            # Remediation comes back BEFORE the verdict is written, so the summary records how the window closed.
            trial=end_control_trial(url,token,trial); closed=True
        print('\n===== RESULTATS =====')
        for name,code,detail in results:
            print(f'  {name:14} -> {detail.splitlines()[0]}  (code {code})')
            for extra in detail.splitlines()[1:]: print('      '+extra.strip())
        if mode=='control':
            outcome=report_control_trial(results,tally)
            write_recipe_result(started_epoch,url,prep,results,proof,mode=mode,tally=tally,trial=trial)
            return 0 if outcome in (CONTROL_IMPACT,CONTROL_NO_IMPACT) else 1
        ok=all(code==0 for _,code,_ in results)
        quiet_observation=is_no_incident_observation(results)
        if ok:
            print('\nRecette VALIDE (cote technique).')
        elif quiet_observation:
            print('\nObservation terminée : aucun incident détecté. La reprise après attaque n’a pas été testée.')
        else:
            print('\nRecette INCOMPLETE — voir les FAIL ci-dessus')
        write_recipe_result(started_epoch,url,prep,results,proof,mode=mode)
        # A quiet observation completed as intended; it is not a PASS for the attack/recovery recipe.
        return 0 if ok or quiet_observation else 1
    finally:
        # Whatever happened above -- a failed step, Ctrl+C, a crash -- the remediation is turned back on here.
        if mode=='control' and not closed: end_control_trial(url,token,trial,quiet=True)

def report_control_trial(results,tally):
    """Print the control-trial verdict in words that cannot be mistaken for a protected recette's PASS."""
    outcome=control_trial_status(results,tally)
    print('\nMODE : ESSAI TEMOIN SANS REMEDIATION — aucun resultat n\'est marque PASS.')
    print('  Attendu dans ce mode : %s en FAIL. Ces controles verifient une REPRISE, volontairement'%(' et '.join(CONTROL_EXPECTED_FAILURES)))
    print('  inhibee ici ; leurs criteres ne sont pas modifies.')
    print('  Impact observe : %d paiement(s) fictif(s) refuse(s) (503) sur %d sondes, %d servi(s).'
          %(tally['payment_503'],tally['probes'],tally['payment_200']))
    statuses=sorted({s for s in tally['incident_status'].values() if s})
    print('  Statuts d\'incident vus par l\'observateur : %s'%(', '.join(statuses) if statuses else 'aucun incident'))
    if outcome==CONTROL_IMPACT:
        print('  RESULTAT : CONTROL_IMPACT_OBSERVED — la charge de devis (/api/quotes) a EU un effet mesurable')
        print('             sans remediation. C\'est l\'impact constate, PAS une reprise reussie.')
    elif outcome==CONTROL_NO_IMPACT:
        print('  RESULTAT : CONTROL_NO_IMPACT — aucun effet mesure : ni rejet de capacite sur la fenetre, ni')
        print('             paiement fictif refuse. La charge n\'a rien prouve cette fois.')
    else:
        print('  RESULTAT : CONTROL_NOT_INHIBITED — essai INVALIDE : la remediation s\'est appliquee malgre')
        print('             l\'essai temoin (statuts %s). A refaire.'%', '.join(statuses))
    return outcome

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--seconds',type=int,default=70,help='duree d\'observation (5..120)')
    p.add_argument('--url',default='http://192.168.137.1:8081',help='URL du WAF hote a observer (adresse du laboratoire ; localhost est aussi accepte)')
    p.add_argument('--yes',action='store_true',help='sauter la confirmation interactive')
    p.add_argument('--mode',choices=MODES,default='protected',
                   help='protected (defaut) : recette avec remediation automatique. '
                        'control : essai temoin SANS remediation automatique, borne dans le temps.')
    a=p.parse_args(argv)
    if not 5<=a.seconds<=120: p.error('--seconds doit etre entre 5 et 120')
    try: acquire_lock()
    except Step as exc: print('ECHEC : '+exc.msg); return 1
    def _sig(*_): raise KeyboardInterrupt
    signal.signal(signal.SIGINT,_sig)
    try: return recette(a.seconds,a.url,a.yes,a.mode)
    except Step as exc: print('ECHEC : '+exc.msg); return 1
    except KeyboardInterrupt: print('\nInterrompu — observateur arrete, aucune preuve fabriquee.'); return 130
    finally: release_lock()
if __name__=='__main__': sys.exit(main())
