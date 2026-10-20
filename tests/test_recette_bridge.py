"""Pure unit tests for the loopback bridge; no sockets, Docker, or real stack are used."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('recette_bridge',ROOT/'scripts'/'recette_bridge.py')
bridge=importlib.util.module_from_spec(spec); spec.loader.exec_module(bridge)

def test_bridge_binds_loopback_and_restricts_dashboard_origins():
    assert bridge.HOST=='127.0.0.1'
    assert bridge.origin_allowed('http://192.168.137.1:8081')
    assert bridge.origin_allowed('http://127.0.0.1:8081')
    assert not bridge.origin_allowed('https://attacker.invalid')
    assert not bridge.origin_allowed('http://192.168.137.1.evil:8081')

def test_only_an_explicit_confirmation_body_is_accepted():
    assert bridge.confirmed_request({'confirmed':True})
    for body in (None,{}, {'confirmed':False},{'confirmed':True,'cmd':'whoami'},['confirmed']):
        assert not bridge.confirmed_request(body)

def test_browser_can_only_launch_the_fixed_host_recipe_not_an_arbitrary_command():
    argv=bridge.runner_argv('http://192.168.137.1:8081')
    assert Path(argv[1])==ROOT/'scripts'/'run_recette.py'
    assert argv[2:]==['--yes','--seconds','70','--url','http://192.168.137.1:8081']
    assert 'attack_lab.py' not in ' '.join(argv)

def test_operator_check_caches_only_a_digest_and_returns_a_fixed_target():
    class Response:
        status=200
        def __enter__(self): return self
        def __exit__(self,*_): return None
        def read(self,_n=-1): return b'{"now":123.0,"incidents":[]}'
    calls=[]
    def fake_open(req,timeout=2):
        calls.append(req.full_url)
        return Response()
    bridge._auth_cache.clear()
    with patch.object(bridge.NO_PROXY,'open',side_effect=fake_open):
        assert bridge._operator_target('never-log-this-token')==('http://192.168.137.1:8081',123.0)
    assert 'never-log-this-token' not in repr(bridge._auth_cache)
    assert all('/api/accounts' in c or '/ops/status' in c for c in calls)

def test_state_mapper_marks_observer_ready_and_check_results_without_copying_logs():
    bridge._state.update(status='running',phase='starting',check_mardi=None,check_mercredi=None,details=[])
    bridge._phase_from_line('  >>> Observateur pret — LANCEZ L\'ATTAQUE sur le PC Attaquant maintenant <<<')
    assert bridge._state['status']=='waiting_attack'
    bridge._phase_from_line('  check_mardi     -> PASS  (code 0)')
    bridge._phase_from_line('  check_mercredi  -> FAIL  (code 1)')
    assert bridge._state['check_mardi']=='PASS'
    assert bridge._state['check_mercredi']=='FAIL'
    bridge._phase_from_line('aucun rejet de capacite sur la fenetre')
    assert any('aucun rejet de capacite' in line for line in bridge._state['details'])

def test_diagnostic_output_is_bounded_and_redacts_sensitive_fields():
    bridge._state['details']=[]
    bridge._phase_from_line('FAIL password=do-not-show-token')
    assert 'do-not-show-token' not in repr(bridge._state['details'])
    for index in range(35):
        bridge._phase_from_line(f'FAIL diagnostic {index}')
    assert len(bridge._state['details'])==30
