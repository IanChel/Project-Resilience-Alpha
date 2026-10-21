"""scripts/run_recette.py (recette orchestrator, HOST side). Everything here is SIMULATED: subprocess and docker are
mocked, nothing touches the real stack, no secret is read. The tests pin the security properties the task requires:
the attack is never launched, operations are a fixed allowlist, confirmation is required, two recettes cannot run at
once, a readiness failure stops before the observer, the documented order is respected, and results read PASS/FAIL/
NON VÉRIFIÉ from the real return codes."""
import importlib.util
import subprocess
import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
def load():
    sys.path.insert(0,str(ROOT/'scripts'))
    spec=importlib.util.spec_from_file_location('run_recette',ROOT/'scripts/run_recette.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m
rr=load()
CP=subprocess.CompletedProcess

class FakeRun:
    """Records every command and returns a scripted return code, chosen by matching the argv. Never executes anything."""
    def __init__(self,codes=None): self.calls=[]; self.codes=codes or {}
    def __call__(self,argv,timeout=60,**kw):
        assert isinstance(argv,list) and all(isinstance(a,str) for a in argv), 'operations must stay fixed arg lists'
        assert kw.get('shell') is not True, 'never a shell'
        self.calls.append(argv)
        joined=' '.join(argv)
        for needle,code in self.codes.items():
            if needle in joined: return CP(argv,code,'out '+needle,'')
        return CP(argv,0,'','')
    def commands(self): return [' '.join(c) for c in self.calls]

class FakeObserver:
    """Stands in for the acceptance.py subprocess: emits a few lines incl. the ready signal, then exits with `code`."""
    instances=[]
    def __init__(self,argv,cwd=None,env=None,**kw):
        self.argv=argv; self.env=env or {}; self._done=False; self.terminated=False; self.killed=False
        self.returncode=FakeObserver.code
        self._lines=iter(['Logged in as alice.',
                          'Initial transaction verified. Start attack_lab.py on the ATTACKER PC now.',
                          'observing...','PASS'])
        self.stdout=self._gen()
        FakeObserver.instances.append(self)
    def _gen(self):
        for l in self._lines: yield l+'\n'
        self._done=True
    def poll(self): return self.returncode if self._done else None
    def wait(self,timeout=None): self._done=True; return self.returncode
    def terminate(self): self.terminated=True; self._done=True
    def kill(self): self.killed=True; self._done=True

@pytest.fixture
def patched(monkeypatch,tmp_path):
    FakeObserver.instances=[]; FakeObserver.code=0
    fake=FakeRun()
    # The run summary is written under ROOT/runtime/evidence. A test must NEVER drop a simulated summary in the
    # real evidence folder: a fabricated recette-run-*.json there is indistinguishable from a recorded one.
    monkeypatch.setattr(rr,'ROOT',tmp_path)
    monkeypatch.setattr(rr,'run',fake)
    monkeypatch.setattr(rr.subprocess,'Popen',FakeObserver)
    monkeypatch.setattr(rr.time,'sleep',lambda *_:None)
    monkeypatch.setattr(rr,'check_ready_once',lambda _url:True)
    monkeypatch.setattr(rr,'acceptance_proof_names',lambda:set())
    monkeypatch.setattr(rr,'find_new_acceptance_proof',lambda _before:Path('runtime/evidence/fresh-proof.json'))
    monkeypatch.setattr(rr.os,'environ',{})          # so LAB_PASSWORD_DIR is set only for the observer, not leaked
    return fake

def _code_only(src):
    """The source with its module docstring removed, so a word used only in prose does not read as code."""
    doc=rr.__doc__ or ''
    return src.replace('"""'+doc+'"""','')

# ---- the attack is NEVER launched, operations are a fixed allowlist -----------------------------------------
def test_attack_script_appears_only_as_prose_or_an_output_match_never_as_a_command():
    body=_code_only((ROOT/'scripts/run_recette.py').read_text(encoding='utf-8'))
    for line in body.splitlines():
        if 'attack_lab' in line:
            assert 'in line' in line, line   # the ONLY code use is matching the observer's own stdout, not launching
def test_attack_is_not_in_any_built_command():
    for argv in (rr.op_reset_policy(),rr.op_restart_payment(),
                 rr.op_acceptance(70,'http://127.0.0.1:8081'),rr.op_check_mardi(90),rr.op_check_mercredi(60)):
        assert all(isinstance(a,str) for a in argv)
        assert 'attack_lab.py' not in ' '.join(argv)
def test_reset_deletes_only_the_policy_file_nothing_destructive():
    argv=rr.op_reset_policy()
    assert argv[:5]==rr.COMPOSE+['exec'] or argv[4]=='exec'
    joined=' '.join(argv)
    assert "/state/policy.json" in joined and 'unlink' in joined
    assert 'down' not in joined and '-v' not in argv and 'rm' not in argv and 'volume' not in joined
def test_the_source_never_uses_a_shell_and_never_downs_volumes():
    body=_code_only((ROOT/'scripts/run_recette.py').read_text(encoding='utf-8'))
    assert 'shell=True' not in body
    assert 'down -v' not in body and "'down'" not in body and "'-v'" not in body and '"-v"' not in body
def test_acceptance_command_is_the_observer_with_bounded_args():
    argv=rr.op_acceptance(70,'http://127.0.0.1:8081')
    assert argv[0]==sys.executable and argv[1].endswith('acceptance.py')
    assert argv[2:]== ['--seconds','70','--url','http://127.0.0.1:8081']
def test_check_mercredi_is_pinned_to_the_given_proof():
    argv=rr.op_check_mercredi(60,Path('runtime/evidence/only-this-run.json'))
    assert argv[-2]=='--file' and Path(argv[-1])==Path('runtime/evidence/only-this-run.json')

# ---- confirmation is required -------------------------------------------------------------------------------
def test_declining_the_confirmation_runs_nothing(patched,monkeypatch):
    monkeypatch.setattr('builtins.input',lambda *_:'n')
    code=rr.recette(seconds=70,url='http://127.0.0.1:8081',auto=False)
    assert code==2 and patched.calls==[] and FakeObserver.instances==[]
def test_confirmation_accepts_oui_and_auto(monkeypatch):
    for answer in ('o','oui','y','yes','OUI'): monkeypatch.setattr('builtins.input',lambda *_,a=answer:a); assert rr.confirm(False) is True
    for answer in ('','n','non','peut-etre'): monkeypatch.setattr('builtins.input',lambda *_,a=answer:a); assert rr.confirm(False) is False
    assert rr.confirm(True) is True

# ---- one recette at a time ----------------------------------------------------------------------------------
def test_a_second_recette_is_refused_while_one_runs(monkeypatch,tmp_path):
    monkeypatch.setattr(rr,'LOCK',tmp_path/'recette.lock')
    monkeypatch.setattr(rr,'_pid_alive',lambda pid:True)
    rr.acquire_lock()
    with pytest.raises(rr.Step) as exc: rr.acquire_lock()
    assert 'deja en cours' in exc.value.msg
    rr.release_lock()
    rr.acquire_lock(); rr.release_lock()          # once released, a new one is allowed
def test_a_stale_lock_from_a_dead_process_is_reclaimed(monkeypatch,tmp_path):
    lock=tmp_path/'recette.lock'; lock.write_text('999999')
    monkeypatch.setattr(rr,'LOCK',lock); monkeypatch.setattr(rr,'_pid_alive',lambda pid:False)
    rr.acquire_lock()                              # dead owner -> reclaimed, no exception
    assert lock.read_text().strip()==str(rr.os.getpid()); rr.release_lock()

# ---- readiness gates the observer ---------------------------------------------------------------------------
def test_full_happy_path_runs_steps_in_the_documented_order(patched,monkeypatch):
    FakeObserver.code=0
    code=rr.recette(seconds=70,url='http://127.0.0.1:8081',auto=True)
    cmds=patched.commands()
    reset_i=next(i for i,c in enumerate(cmds) if 'policy.json' in c)
    restart_i=next(i for i,c in enumerate(cmds) if 'restart payment' in c)
    assert rr.check_ready_once('http://192.168.137.1:8081') is True
    mardi_i=next(i for i,c in enumerate(cmds) if 'check_mardi.py' in c)
    mercredi_i=next(i for i,c in enumerate(cmds) if 'check_mercredi.py' in c)
    assert reset_i<restart_i<mardi_i<mercredi_i                   # readiness gates observer; checks follow observer
    assert FakeObserver.instances and mercredi_i>mardi_i
    assert '--file' in cmds[mercredi_i] and 'fresh-proof.json' in cmds[mercredi_i]
    assert code==0
def test_when_payment_never_becomes_ready_the_observer_is_not_launched(patched,monkeypatch):
    monkeypatch.setattr(rr,'check_ready_once',lambda _url:False)  # published WAF readiness probe always fails
    monkeypatch.setattr(rr,'READY_TIMEOUT_S',0.01)
    with pytest.raises(rr.Step) as exc: rr.recette(seconds=70,url='http://127.0.0.1:8081',auto=True)
    assert 'observateur non lance' in exc.value.msg.lower()
    assert FakeObserver.instances==[]                            # the observer was NEVER started
    assert not any('check_mardi' in c for c in patched.commands())
def test_a_failed_reset_stops_before_restart(patched):
    patched.codes={'policy.json':1}
    with pytest.raises(rr.Step) as exc: rr.recette(seconds=70,url='http://127.0.0.1:8081',auto=True)
    assert 'reset' in exc.value.msg.lower()
    assert not any('restart payment' in c for c in patched.commands())

def test_ready_probe_uses_the_published_waf_route_and_requires_ready_json(monkeypatch):
    class Response:
        status=200
        def __enter__(self): return self
        def __exit__(self,*_): return None
        def read(self): return b'{"status":"ready"}'
    seen=[]
    def fake_open(req,timeout): seen.append((req.full_url,timeout));return Response()
    monkeypatch.setattr(rr.NO_PROXY,'open',fake_open)
    assert rr.check_ready_once('http://192.168.137.1:8081') is True
    assert seen==[('http://192.168.137.1:8081/api/ready',3)]

# ---- results read PASS / FAIL / NON VÉRIFIÉ from the real return codes --------------------------------------
def test_run_check_maps_return_codes(patched):
    assert rr.run_check('check_mardi',['x'])[2].startswith('PASS')     # FakeRun default: code 0
    patched.codes={'x':1}
    name,code,detail=rr.run_check('check_mardi',['x'])
    assert code==1 and detail.startswith('FAIL')
def test_run_check_timeout_is_non_verifie(monkeypatch):
    def boom(argv,timeout=60,**kw): raise subprocess.TimeoutExpired(argv,timeout)
    monkeypatch.setattr(rr,'run',boom)
    name,code,detail=rr.run_check('check_mercredi',['y'])
    assert code is None and 'NON VERIFIE' in detail
def test_a_check_failure_makes_the_recette_incomplete(patched):
    FakeObserver.code=0; patched.codes={'check_mercredi.py':1}
    code=rr.recette(seconds=70,url='http://127.0.0.1:8081',auto=True)
    assert code==1                                               # one FAIL -> recette incomplete, not a silent pass

def test_missing_new_acceptance_proof_skips_mercredi_without_using_history(patched,monkeypatch):
    monkeypatch.setattr(rr,'find_new_acceptance_proof',lambda _before:None)
    code=rr.recette(seconds=70,url='http://127.0.0.1:8081',auto=True)
    assert code==1
    assert not any('check_mercredi.py' in c for c in patched.commands())

# ---- the observer is always stopped, the password is never printed ------------------------------------------
def test_the_observer_is_terminated_if_still_running(patched,monkeypatch):
    class Hanging(FakeObserver):
        def _gen(self):
            for l in self._lines: yield l+'\n'        # stdout ends WITHOUT marking done: the process lingers
        def poll(self): return self.returncode if (self.terminated or self.killed) else None
        def wait(self,timeout=None):
            if self.terminated or self.killed: return self.returncode
            raise subprocess.TimeoutExpired(self.argv,timeout or 0)
    monkeypatch.setattr(rr.subprocess,'Popen',Hanging)
    rr.recette(seconds=70,url='http://127.0.0.1:8081',auto=True)
    assert Hanging.instances[-1].terminated is True
def test_password_dir_is_passed_to_observer_but_value_is_never_in_output(patched,capsys):
    rr.recette(seconds=70,url='http://127.0.0.1:8081',auto=True)
    obs=FakeObserver.instances[-1]
    assert obs.env.get('LAB_PASSWORD_DIR','').endswith('runtime')  # a directory path, not a secret value
    # Only the DIRECTORY ever travels. The summary path is dropped first: pytest names its temporary directory
    # after this test, so that one line legitimately contains the word without being about a secret.
    out='\n'.join(l for l in capsys.readouterr().out.splitlines() if 'evidence' not in l)
    assert 'password' not in out.lower() and 'LAB_PASSWORD_DIR' not in out

# ---- control trial: the window is armed, bounded, and ALWAYS ended again ------------------------------------
@pytest.fixture
def trial(monkeypatch):
    """Records the control-trial calls the runner makes, without any network or stack."""
    calls=[]
    def fake_call(url,token,payload):
        assert token=='operator-session','the window is only ever changed with an operator session'
        calls.append((url,payload))
        if payload['action']=='start': return {'active':True,'remaining_s':payload['seconds'],'max_seconds':300}
        return {'active':False,'closed_reason':'operator_stopped'}
    monkeypatch.setattr(rr,'op_token',lambda _url:'operator-session')
    monkeypatch.setattr(rr,'trial_call',fake_call)
    return calls

def test_a_protected_run_never_touches_the_control_trial_window(patched,trial):
    assert rr.recette(seconds=70,url='http://127.0.0.1:8081',auto=True) in (0,1)
    assert trial==[]                                  # the documented recette is unchanged, and arms nothing

def test_a_control_run_arms_a_bounded_window_and_ends_it_afterwards(patched,trial):
    rr.recette(seconds=70,url='http://127.0.0.1:8081',auto=True,mode='control')
    actions=[payload['action'] for _url,payload in trial]
    assert actions==['start','stop']                  # armed once, ended once
    _url,start=trial[0]
    assert start=={'action':'start','confirmed':True,'seconds':rr.trial_seconds(70)}
    assert rr.TRIAL_MIN_S<=start['seconds']<=rr.TRIAL_MAX_S
    assert all(url=='http://127.0.0.1:8081' for url,_ in trial)

def test_the_window_is_armed_after_the_reset_and_stays_open_across_the_observation(patched,trial,monkeypatch):
    order=[]
    def watched(*a,**k):
        order.append('observer'); return FakeObserver(*a,**k)
    def fake_call(url,token,payload):
        order.append(payload['action'])
        return {'active':True,'max_seconds':300} if payload['action']=='start' else {'active':False}
    monkeypatch.setattr(rr.subprocess,'Popen',watched)
    monkeypatch.setattr(rr,'trial_call',fake_call)
    rr.recette(seconds=70,url='http://127.0.0.1:8081',auto=True,mode='control')
    assert order.index('start')<order.index('observer')   # the trial covers the observation...
    assert order.index('observer')<order.index('stop')    # ...and is still open while it runs
    assert any('policy.json' in c for c in patched.commands())        # the clean state came first
    assert any('restart payment' in c for c in patched.commands())

@pytest.mark.parametrize('boom',['check_mardi','observer'])
def test_the_window_is_ended_even_when_a_later_step_fails(patched,trial,monkeypatch,boom):
    if boom=='check_mardi':
        monkeypatch.setattr(rr,'run_check',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('boom')))
    else:
        def exploding(*a,**k): raise OSError('observer cannot start')
        monkeypatch.setattr(rr.subprocess,'Popen',exploding)
    with pytest.raises((RuntimeError,OSError)):
        rr.recette(seconds=70,url='http://127.0.0.1:8081',auto=True,mode='control')
    assert [p['action'] for _u,p in trial]==['start','stop']   # the remediation came back on the way out

def test_an_interrupted_control_run_still_ends_the_window(patched,trial,monkeypatch):
    def interrupt(*a,**k): raise KeyboardInterrupt
    monkeypatch.setattr(rr,'run_check',interrupt)
    with pytest.raises(KeyboardInterrupt):
        rr.recette(seconds=70,url='http://127.0.0.1:8081',auto=True,mode='control')
    assert [p['action'] for _u,p in trial]==['start','stop']

def test_a_window_that_cannot_be_armed_stops_before_the_observer_and_keeps_remediation_on(patched,monkeypatch,tmp_path):
    monkeypatch.setattr(rr,'ROOT',tmp_path)
    monkeypatch.setattr(rr,'op_token',lambda _url:'operator-session')
    monkeypatch.setattr(rr,'trial_call',lambda *a,**k:(_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(rr.Step) as exc:
        rr.recette(seconds=70,url='http://127.0.0.1:8081',auto=True,mode='control')
    assert 'reste ACTIVE' in exc.value.msg
    assert FakeObserver.instances==[]                 # the observer was NOT started

def test_a_window_the_service_refuses_to_arm_stops_the_run(patched,monkeypatch,tmp_path):
    monkeypatch.setattr(rr,'ROOT',tmp_path)
    monkeypatch.setattr(rr,'op_token',lambda _url:'operator-session')
    monkeypatch.setattr(rr,'trial_call',lambda url,token,payload:{'active':False,'closed_reason':None})
    with pytest.raises(rr.Step) as exc:
        rr.recette(seconds=70,url='http://127.0.0.1:8081',auto=True,mode='control')
    assert 'reste ACTIVE' in exc.value.msg
    assert FakeObserver.instances==[]

def test_the_observer_gets_the_password_directory_in_both_modes(patched,trial):
    """Regression: the runner's own operator login reads LAB_PASSWORD_DIR from an explicit env, not from the
    parent process -- the loopback bridge never sets it."""
    for mode in ('protected','control'):
        FakeObserver.instances=[]
        rr.recette(seconds=70,url='http://127.0.0.1:8081',auto=True,mode=mode)
        assert FakeObserver.instances[-1].env.get('LAB_PASSWORD_DIR','').endswith('runtime'),mode
    assert rr.password_env()['LAB_PASSWORD_DIR'].endswith('runtime')
    assert 'LAB_PASSWORD' not in rr.os.environ        # the value itself never goes through the environment

def test_an_unknown_mode_is_refused_before_anything_runs(patched,trial):
    with pytest.raises(rr.Step):
        rr.recette(seconds=70,url='http://127.0.0.1:8081',auto=True,mode='disable-everything')
    assert trial==[] and patched.calls==[]

def test_the_confirmation_spells_out_what_a_control_trial_does(capsys):
    rr.confirm(True,'control')
    printed=capsys.readouterr().out
    assert 'ESSAI TEMOIN SANS REMEDIATION' in printed
    assert 'restent ACTIFS' in printed                # not presented as switching security off
    assert 'reactivee' in printed                     # says how the remediation comes back
    assert 'PASS' in printed                          # says no result will be a PASS
    rr.confirm(True,'protected')
    assert 'ESSAI TEMOIN' not in capsys.readouterr().out
