"""The control trial ("essai temoin"): remediation is inhibited for incidents during a BOUNDED window, and
only by an authenticated operator. What these tests pin down:
  - the protected mode is unchanged: a normal alert still contains, verifies and recovers;
  - the inhibition applies ONLY while the window holds, and only to the remediator's own response;
  - the window reopens remediation on its own -- deadline, operator, restart -- even
    when something went wrong;
  - an operator session is required to arm it AND to end it;
  - a trial result is never reported as a recovery, and never as a protected PASS.
No attack, no acceptance run, no Docker, no real stack: the containment playbook and the witness transaction
are replaced by fakes, exactly as tests/test_incident_stages.py does.
"""
import asyncio
import hashlib
import hmac
import importlib.util
import json
import sys
import time
import uuid
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import services.remediator.main as remediator
from services.common.security import issue, secret

ROOT = Path(__file__).resolve().parents[1]
OPERATOR = lambda: {'Authorization': 'Bearer ' + issue('alice', 'operator')}
LOADBOT = lambda: {'Authorization': 'Bearer ' + issue('loadbot', 'loadbot')}


def signed(data):
    raw = json.dumps(data).encode()
    return {'content': raw,
            'headers': {'Content-Type': 'application/json',
                        'X-Signature': hmac.new(secret('alert_key').encode(), raw, hashlib.sha256).hexdigest()}}


def alert(**over):
    return {'id': str(uuid.uuid4()), 'issued_at': time.time(), 'score': -0.5, 'features': [9, 4, 5, 5], **over}


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """A remediator whose containment and witness transaction are fakes, and whose trial window starts closed."""
    monkeypatch.setattr(remediator, 'STORE', tmp_path / 'incidents.sqlite')
    contained = []

    class Ansible:
        returncode = 0
        async def communicate(self):
            contained.append(time.time())
            return b'ok', b''

    async def fake_exec(*a, **k):
        return Ansible()

    witnesses = []

    async def fake_verify(iid):
        witnesses.append(iid)
        return {'transaction_id': 'tx-1', 'total_cents': 200000}

    monkeypatch.setattr(remediator.asyncio, 'create_subprocess_exec', fake_exec)
    monkeypatch.setattr(remediator, 'business_verify', fake_verify)
    remediator.trial.update(active=False, until=0.0, armed_at=None, armed_by=None, incident_id=None, closed=None)
    return {'contained': contained, 'witnesses': witnesses}


def wait_final(client, statuses=('recovered', 'failed', 'observed')):
    for _ in range(100):
        body = client.get('/status', headers=OPERATOR()).json()
        if body['incidents'] and body['incidents'][0]['status'] in statuses:
            return body
        time.sleep(0.05)
    raise AssertionError('the incident never reached a final status')


# ---- the protected mode must stay exactly as it was --------------------------------------------------------
def test_the_protected_mode_is_unchanged_containment_witness_and_recovered(lab):
    with TestClient(remediator.app) as client:
        assert client.get('/control-trial', headers=OPERATOR()).json()['active'] is False
        assert client.post('/alerts', **signed(alert())).status_code == 202
        incident = wait_final(client)['incidents'][0]
    assert incident['status'] == 'recovered'
    assert list(incident['stages']) == ['detected', 'accepted', 'containing', 'verifying', 'recovered']
    assert lab['contained'] and lab['witnesses']                      # the playbook ran and the witness was verified
    assert json.loads(incident['evidence'])['total_cents'] == 200000


def test_arming_then_ending_a_trial_leaves_the_protected_mode_intact(lab):
    with TestClient(remediator.app) as client:
        client.post('/control-trial', headers=OPERATOR(), json={'action': 'start', 'confirmed': True, 'seconds': 60})
        assert client.post('/control-trial', headers=OPERATOR(), json={'action': 'stop'}).json()['active'] is False
        assert client.post('/alerts', **signed(alert())).status_code == 202
        incident = wait_final(client)['incidents'][0]
    assert incident['status'] == 'recovered'                           # remediation came back for real
    assert lab['contained'] and lab['witnesses']


# ---- the inhibition itself ---------------------------------------------------------------------------------
def test_during_a_trial_the_incident_is_journaled_but_never_contained(lab):
    with TestClient(remediator.app) as client:
        armed = client.post('/control-trial', headers=OPERATOR(),
                            json={'action': 'start', 'confirmed': True, 'seconds': 60}).json()
        assert armed['active'] is True and armed['armed_by'] == 'alice'
        assert 0 < armed['remaining_s'] <= 60
        posted = alert(issued_at=time.time() - 1.5)
        assert client.post('/alerts', **signed(posted)).status_code == 202
        incident = wait_final(client)['incidents'][0]
    # The detector's alert is kept with its real detection time: detection and journaling are NOT inhibited.
    assert incident['status'] == 'observed'
    assert list(incident['stages']) == ['detected', 'accepted', 'observed']
    assert incident['stages']['detected'] == posted['issued_at']
    # ...but the remediator's own response never ran.
    assert lab['contained'] == [] and lab['witnesses'] == []
    evidence = json.loads(incident['evidence'])
    assert evidence['mode'] == 'control_trial' and evidence['remediation_applied'] is False
    assert 'ban' not in evidence                                       # no ban was planned, let alone applied


def test_the_trial_covers_multiple_incidents_until_stopped_then_remediation_is_back(lab):
    with TestClient(remediator.app) as client:
        client.post('/control-trial', headers=OPERATOR(), json={'action': 'start', 'confirmed': True, 'seconds': 120})
        assert client.post('/alerts', **signed(alert())).status_code == 202
        first = wait_final(client)['incidents'][0]
        assert first['status'] == 'observed'
        window = client.get('/control-trial', headers=OPERATOR()).json()
        assert window['active'] is True                                # the incident does not end the window
        assert window['observed_incident_id'] == first['id']
        assert client.post('/alerts', **signed(alert())).status_code == 202
        second = wait_final(client)['incidents'][0]
        assert second['status'] == 'observed'                          # incidents inside the window stay unremediated
        assert client.get('/control-trial', headers=OPERATOR()).json()['active'] is True
        stopped = client.post('/control-trial', headers=OPERATOR(), json={'action': 'stop'}).json()
        assert stopped['active'] is False and stopped['closed_reason'] == 'operator_stopped'
        assert client.post('/alerts', **signed(alert())).status_code == 202
        third = wait_final(client)['incidents'][0]
        assert third['status'] == 'recovered'                          # remediation is back after the window
    assert lab['contained'] and lab['witnesses']


def test_an_elapsed_window_is_closed_on_read_and_never_inhibits_again(lab):
    with TestClient(remediator.app) as client:
        client.post('/control-trial', headers=OPERATOR(), json={'action': 'start', 'confirmed': True, 'seconds': 5})
        remediator.trial['until'] = time.time() - 0.001                # the deadline has just passed
        window = client.get('/control-trial', headers=OPERATOR()).json()
        assert window['active'] is False and window['closed_reason'] == 'expired'
        assert window['remaining_s'] is None                           # no countdown is reported for a closed window
        assert client.post('/alerts', **signed(alert())).status_code == 202
        incident = wait_final(client)['incidents'][0]
    assert incident['status'] == 'recovered'
    assert lab['contained']


def test_an_expired_window_cannot_inhibit_even_without_any_reader(lab):
    """The decision point is recover() itself: nothing has to poll the status for the deadline to hold."""
    iid = str(uuid.uuid4())
    with remediator.connection() as c:
        c.execute('INSERT INTO incidents VALUES(?,?,?,?,?)', (iid, 'accepted', time.time(), time.time(), '{}'))
    remediator.trial_open(60, 'alice')
    remediator.trial['until'] = time.time() - 1                        # elapsed, and never read by anyone
    asyncio.run(remediator.recover(iid))
    with remediator.connection() as c:
        assert c.execute('SELECT status FROM incidents WHERE id=?', (iid,)).fetchone()['status'] == 'recovered'
    assert remediator.trial['active'] is False
    assert lab['contained']


def test_a_restart_always_comes_back_with_remediation_enabled(lab):
    """The window is deliberately never written to disk, so it cannot survive the process."""
    source = (ROOT / 'services/remediator/main.py').read_text(encoding='utf-8')
    body = source.split('trial={')[1].split('def in_flight')[0]
    for persistence in ('write_text', 'write(', 'sqlite', 'INSERT', 'UPDATE', 'STORE', 'connection('):
        assert persistence not in body, f'the trial window must not be persisted: {persistence}'
    remediator.trial_open(300, 'alice')
    with TestClient(remediator.app) as client:                          # a fresh app, as after a restart
        remediator.trial.update(active=False, until=0.0, closed=None)   # what a new process starts from
        assert client.get('/control-trial', headers=OPERATOR()).json()['active'] is False
        assert client.post('/alerts', **signed(alert())).status_code == 202
        assert wait_final(client)['incidents'][0]['status'] == 'recovered'


def test_an_interrupted_trial_incident_is_terminal_and_is_not_resumed_as_a_recovery(lab):
    """`observed` is terminal: the lifespan resume must not pick it up and remediate it after the fact."""
    with remediator.connection() as c:
        c.execute('INSERT INTO incidents VALUES(?,?,?,?,?)', ('obs', 'observed', 1.0, 2.0, '{}'))
    with TestClient(remediator.app) as client:
        time.sleep(0.2)
        incident = client.get('/status', headers=OPERATOR()).json()['incidents'][0]
    assert incident['status'] == 'observed'
    assert lab['contained'] == [] and lab['witnesses'] == []


# ---- who may arm and end a trial ---------------------------------------------------------------------------
@pytest.mark.parametrize('payload', [{'action': 'start', 'confirmed': True, 'seconds': 60}, {'action': 'stop'}])
def test_only_an_authenticated_operator_can_start_or_stop_a_trial(lab, payload):
    with TestClient(remediator.app) as client:
        assert client.post('/control-trial', json=payload).status_code == 401
        assert client.post('/control-trial', headers=LOADBOT(), json=payload).status_code == 403
        assert client.get('/control-trial').status_code == 401
        assert client.get('/control-trial', headers=LOADBOT()).status_code == 403
        assert remediator.trial['active'] is False                      # nothing was armed by a refused caller


@pytest.mark.parametrize('payload,reason', [
    ({'action': 'start', 'seconds': 60}, 'no confirmation at all'),
    ({'action': 'start', 'confirmed': False, 'seconds': 60}, 'confirmation refused'),
    ({'action': 'start', 'confirmed': 'yes', 'seconds': 60}, 'confirmation is not a true boolean'),
    ({'action': 'start', 'confirmed': True}, 'no duration'),
    ({'action': 'start', 'confirmed': True, 'seconds': 0}, 'duration below the floor'),
    ({'action': 'start', 'confirmed': True, 'seconds': 301}, 'duration above the cap'),
    ({'action': 'start', 'confirmed': True, 'seconds': 86400}, 'a whole day'),
    ({'action': 'start', 'confirmed': True, 'seconds': 'soixante'}, 'duration is not a number'),
    ({'action': 'disable_security', 'confirmed': True}, 'an action that does not exist'),
    ({'confirmed': True, 'seconds': 60}, 'no action'),
    ({}, 'nothing'),
])
def test_a_trial_cannot_be_armed_without_an_explicit_bounded_request(lab, payload, reason):
    with TestClient(remediator.app) as client:
        assert client.post('/control-trial', headers=OPERATOR(), json=payload).status_code == 422, reason
        assert remediator.trial['active'] is False, reason
        # ...and the remediation still works.
        assert client.post('/alerts', **signed(alert())).status_code == 202
        assert wait_final(client)['incidents'][0]['status'] == 'recovered'


def test_the_window_is_never_an_open_ended_switch(lab):
    assert remediator.TRIAL_MAX_S <= 300
    with TestClient(remediator.app) as client:
        state = client.post('/control-trial', headers=OPERATOR(),
                            json={'action': 'start', 'confirmed': True, 'seconds': remediator.TRIAL_MAX_S}).json()
        assert state['max_seconds'] == remediator.TRIAL_MAX_S
        assert state['remaining_s'] <= remediator.TRIAL_MAX_S
        # A second arming cannot extend an already running remediation...
        assert client.post('/alerts', **signed(alert())).status_code == 202
        wait_final(client)
        assert client.get('/control-trial', headers=OPERATOR()).json()['active'] is True
        assert client.post('/control-trial', headers=OPERATOR(), json={'action': 'stop'}).json()['active'] is False


def test_a_trial_is_refused_while_a_remediation_is_in_flight(lab, monkeypatch):
    slow = asyncio.Event()

    async def hanging_verify(iid):
        await asyncio.wait_for(slow.wait(), timeout=10)
        return {'transaction_id': 'tx-1', 'total_cents': 200000}

    monkeypatch.setattr(remediator, 'business_verify', hanging_verify)
    with TestClient(remediator.app) as client:
        assert client.post('/alerts', **signed(alert())).status_code == 202
        for _ in range(100):                                            # wait until it is really in flight
            rows = client.get('/status', headers=OPERATOR()).json()['incidents']
            if rows and rows[0]['status'] in ('containing', 'verifying'):
                break
            time.sleep(0.05)
        refused = client.post('/control-trial', headers=OPERATOR(),
                              json={'action': 'start', 'confirmed': True, 'seconds': 60})
        assert refused.status_code == 409                                # never inhibit a recovery halfway
        assert remediator.trial['active'] is False
        slow.set()
        assert wait_final(client)['incidents'][0]['status'] == 'recovered'


def test_an_oversized_control_request_is_refused_before_anything_is_armed(lab):
    with TestClient(remediator.app) as client:
        reply = client.post('/control-trial', headers=OPERATOR(), content=b'{"action":"start"' + b' ' * 600 + b'}')
        assert reply.status_code == 413
        assert remediator.trial['active'] is False


@pytest.mark.parametrize('raw', [b'{"action":"start","confirmed":true,"seconds":1e999}',   # parses to +inf
                                 b'{"action":"start","confirmed":true,"seconds":-1e999}',
                                 b'{"action":"start","confirmed":true,"seconds":NaN}',
                                 b'not json at all', b'[]', b'"start"', b''])
def test_a_duration_that_is_not_a_finite_bounded_number_is_refused(lab, raw):
    with TestClient(remediator.app) as client:
        reply = client.post('/control-trial', content=raw,
                            headers={**OPERATOR(), 'Content-Type': 'application/json'})
        assert reply.status_code == 422, raw
        assert remediator.trial['active'] is False, raw


# ---- what the window publishes -----------------------------------------------------------------------------
def test_the_window_is_published_on_every_status_poll_and_carries_no_secret(lab):
    with TestClient(remediator.app) as client:
        client.post('/control-trial', headers=OPERATOR(), json={'action': 'start', 'confirmed': True, 'seconds': 90})
        body = client.get('/status', headers=OPERATOR()).json()
        window = body['control_trial']
        assert window['active'] is True and window['armed_by'] == 'alice'
        assert set(window) == {'active', 'remaining_s', 'armed_at', 'armed_by', 'min_seconds', 'max_seconds',
                               'observed_incident_id', 'closed_reason'}
        text = json.dumps(body)
        for forbidden in (secret('alert_key'), secret('session_key'), secret('alice_password')):
            assert forbidden not in text
        for word in ('password', 'token', 'secret', 'Bearer'):
            assert word not in text


def test_arming_and_closing_are_journaled(lab, monkeypatch):
    events = []
    monkeypatch.setattr(remediator, 'emit', lambda service, action, **fields: events.append((action, fields)))
    remediator.trial_open(60, 'alice')
    remediator.trial_close('operator_stopped')
    assert remediator.trial_close('operator_stopped') is False          # closing twice journals once
    actions = [action for action, _ in events]
    assert actions == ['control_trial_armed', 'control_trial_closed']
    assert events[0][1]['armed_by'] == 'alice' and events[0][1]['seconds'] == 60
    assert events[1][1]['reason'] == 'operator_stopped'


# ---- the host launcher's reading of a trial ----------------------------------------------------------------
def load(name):
    sys.path.insert(0, str(ROOT / 'scripts'))          # the host scripts import lab_client as a sibling
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load('run_recette')
bridge = load('recette_bridge')


def result(**over):
    base = {'acceptance': 1, 'check_mardi': 0, 'check_mercredi': 1}
    base.update(over)
    return [(name, code, 'PASS' if code == 0 else 'FAIL') for name, code in base.items()]


def tally(**over):
    return {**runner.new_tally(), **over}


def test_a_control_trial_is_never_a_pass_whatever_the_checks_say():
    # Even if every check somehow passed, a control trial has no PASS: PASS belongs to the protected recette.
    for results in (result(), result(acceptance=0, check_mercredi=0), result(check_mardi=1)):
        assert runner.control_trial_status(results, tally(payment_503=3)) != 'PASS'
    assert 'PASS' not in {runner.CONTROL_IMPACT, runner.CONTROL_NO_IMPACT, runner.CONTROL_NOT_INHIBITED}


def test_the_expected_failures_are_the_checks_that_verify_a_recovery():
    assert runner.CONTROL_EXPECTED_FAILURES == ('acceptance', 'check_mercredi')
    assert 'check_mardi' not in runner.CONTROL_EXPECTED_FAILURES       # M7 measures the load: it should pass


def test_capacity_rejections_or_refused_payments_read_as_an_observed_impact():
    assert runner.control_trial_status(result(check_mardi=0), tally()) == runner.CONTROL_IMPACT
    assert runner.control_trial_status(result(check_mardi=1), tally(payment_503=2)) == runner.CONTROL_IMPACT
    # Nothing measured at all: nothing is claimed.
    assert runner.control_trial_status(result(check_mardi=1), tally(payment_200=40)) == runner.CONTROL_NO_IMPACT


def test_a_trial_whose_remediation_actually_ran_is_reported_invalid_not_accepted():
    for applied in ('containing', 'verifying', 'recovered'):
        status = runner.control_trial_status(result(check_mardi=0), tally(payment_503=5,
                                                                         incident_status={'i': applied}))
        assert status == runner.CONTROL_NOT_INHIBITED, applied
    # `observed` is the status a trial is supposed to produce, and `detected` never reached the response.
    for fine in ('observed', 'detected', 'accepted', 'failed'):
        assert runner.control_trial_status(result(check_mardi=0),
                                           tally(payment_503=5, incident_status={'i': fine})) == runner.CONTROL_IMPACT


def test_the_observer_rows_are_tallied_without_reading_any_proof_file():
    counted = runner.new_tally()
    runner.tally_observation('{"at": 10.0, "payment_status": 200, "incidents": []}', counted)
    runner.tally_observation('{"at": 11.0, "payment_status": 503, "incidents": [{"id": "abc", "status": "detected"}]}', counted)
    runner.tally_observation('{"at": 12.0, "payment_status": 503, "incidents": [{"id": "abc", "status": "observed"}]}', counted)
    runner.tally_observation('not json at all', counted)
    runner.tally_observation('{"at": 13.0, "network_error": "ReadTimeout"}', counted)
    runner.tally_observation('[1,2,3]', counted)
    assert counted['probes'] == 3 and counted['payment_200'] == 1 and counted['payment_503'] == 2
    assert counted['first_refused_at'] == 11.0
    assert counted['incident_status'] == {'abc': 'observed'}            # the LAST snapshot of each incident wins


def test_the_summary_records_the_mode_and_the_impact_without_inventing_one(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    prep = [{'name': 'reset_policy', 'verdict': 'PASS', 'exit_code': 0}]
    counted = tally(probes=20, payment_503=4, payment_200=16, first_refused_at=5.0,
                    incident_status={'i': 'observed'})
    path = runner.write_recipe_result(time.time(), 'http://127.0.0.1:8081', prep, result(check_mardi=0),
                                      mode='control', tally=counted,
                                      trial={'active': False, 'closed_reason': 'operator_stopped'})
    report = json.loads(path.read_text(encoding='utf-8'))
    assert report['mode'] == 'control' and report['remediation_inhibited'] is True
    assert report['status'] == runner.CONTROL_IMPACT and report['status'] != 'PASS'
    assert report['expected_failures'] == ['acceptance', 'check_mercredi']
    assert report['observed_impact']['payment_refused_503'] == 4
    assert report['observed_impact']['incident_statuses'] == ['observed']
    assert 'reprise' not in report['observed_impact']['note'].lower().replace('pas une reprise', '')
    assert report['control_trial']['closed_reason'] == 'operator_stopped'
    assert report['attack_launched_by_runner'] is False


def test_a_protected_summary_keeps_its_own_shape_and_can_still_be_a_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    prep = [{'name': 'reset_policy', 'verdict': 'PASS', 'exit_code': 0}]
    path = runner.write_recipe_result(time.time(), 'http://127.0.0.1:8081', prep,
                                      result(acceptance=0, check_mardi=0, check_mercredi=0))
    report = json.loads(path.read_text(encoding='utf-8'))
    assert report['status'] == 'PASS'
    assert report['mode'] == 'protected' and report['remediation_inhibited'] is False
    assert report['control_trial'] is None and report['observed_impact'] is None
    assert report['expected_failures'] == []


def test_a_failed_preparation_is_a_plain_failure_in_either_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    for mode in ('protected', 'control'):
        path = runner.write_recipe_result(time.time(), 'http://127.0.0.1:8081', [], result(), mode=mode,
                                          tally=tally(payment_503=9))
        assert json.loads(path.read_text(encoding='utf-8'))['status'] == 'FAIL', mode


def test_the_window_the_launcher_asks_for_is_derived_and_clamped():
    assert runner.trial_seconds(70) == 70 + runner.TRIAL_MARGIN_S
    assert runner.trial_seconds(5) == 5 + runner.TRIAL_MARGIN_S
    assert runner.trial_seconds(10_000) == runner.TRIAL_MAX_S          # never beyond what the service accepts
    assert runner.trial_seconds(0) >= runner.TRIAL_MIN_S
    assert runner.TRIAL_MAX_S == 300                                   # the same cap the remediator enforces
    assert runner.TRIAL_MAX_S == remediator.TRIAL_MAX_S


def test_the_trial_is_always_ended_even_when_the_call_fails(monkeypatch, capsys):
    monkeypatch.setattr(runner, 'end_trial', lambda url, token: (_ for _ in ()).throw(TimeoutError()))
    state = runner.end_control_trial('http://127.0.0.1:8081', 'a-token', {'active': True})
    assert state['closed_confirmed'] is False and state['close_error'] == 'TimeoutError'
    printed = capsys.readouterr().out
    assert 'ATTENTION' in printed and 'echeance' in printed            # the operator is told how it comes back
    assert runner.end_control_trial('http://127.0.0.1:8081', None, {'active': True}) == {'active': True}


def test_the_runner_asks_for_the_trial_with_an_explicit_confirmation_and_never_a_shell():
    source = (ROOT / 'scripts/run_recette.py').read_text(encoding='utf-8')
    assert "{'action':'start','confirmed':True,'seconds':seconds}" in source
    assert "{'action':'stop'}" in source
    assert "'/ops/control-trial'" in source                            # the published operator route, nothing else
    assert 'shell=True' not in source and 'os.system' not in source
    # The attack is never launched from here. The only remaining mention is the observer's ready signal being
    # MATCHED in its output, never a command. (Same reading as tests/test_run_recette.py.)
    code = source.replace('"""' + (runner.__doc__ or '') + '"""', '')
    for line in code.splitlines():
        if 'attack_lab' in line:
            assert 'in line' in line, line


# ---- the bridge offers the two modes and nothing more ------------------------------------------------------
def test_the_browser_can_ask_for_exactly_two_modes():
    assert bridge.requested_mode({'confirmed': True}) == 'protected'
    assert bridge.requested_mode({'confirmed': True, 'mode': 'protected'}) == 'protected'
    assert bridge.requested_mode({'confirmed': True, 'mode': 'control'}) == 'control'
    for refused in ({}, None, {'mode': 'control'}, {'confirmed': False, 'mode': 'control'},
                    {'confirmed': True, 'mode': 'whatever'}, {'confirmed': True, 'mode': None},
                    {'confirmed': True, 'mode': 'control', 'cmd': 'whoami'},
                    {'confirmed': True, 'seconds': 86400}, ['confirmed'], 'control'):
        assert bridge.requested_mode(refused) is None, refused


def test_the_mode_only_ever_adds_two_fixed_arguments():
    protected = bridge.runner_argv('http://192.168.137.1:8081')
    control = bridge.runner_argv('http://192.168.137.1:8081', 'control')
    assert protected[2:] == ['--yes', '--seconds', '70', '--url', 'http://192.168.137.1:8081']
    assert control == protected + ['--mode', 'control']
    assert bridge.runner_argv('http://192.168.137.1:8081', 'anything-else') == protected
    for argv in (protected, control):
        assert Path(argv[1]) == ROOT / 'scripts' / 'run_recette.py'
        assert 'attack_lab.py' not in ' '.join(argv)


def test_the_bridge_keeps_the_runners_own_control_verdict_instead_of_the_exit_code():
    for outcome, expected in (('CONTROL_IMPACT_OBSERVED', 'control_impact'),
                              ('CONTROL_NO_IMPACT', 'control_no_impact'),
                              ('CONTROL_NOT_INHIBITED', 'control_not_inhibited'),
                              ('NO_INCIDENT', 'no_incident'),
                              ('PASS', 'complete')):
        bridge._state.update(status='running', phase='starting', mode='control')
        bridge._phase_from_line('RECETTE_RESULT_JSON ' + json.dumps(
            {'status': outcome, 'mode': 'control', 'result_file': 'recette-run-1-abcd.json'}))
        assert bridge._state['status'] == expected, outcome
        assert bridge._state['mode'] == 'control'
        assert expected in bridge.RUNNER_DECLARED or expected == 'complete'
    bridge._state.update(status='running', phase='starting', mode=None)
    bridge._phase_from_line('RECETTE_RESULT_JSON ' + json.dumps({'status': 'something-new'}))
    assert bridge._state['status'] == 'failed'                          # an unknown outcome is never a success


def test_the_bridge_reports_the_arming_phase():
    bridge._state.update(status='running', phase='starting')
    bridge._phase_from_line('[essai temoin] Inhibition de la remediation automatique pendant la fenetre bornee')
    assert bridge._state['phase'] == 'arming_trial'


# ---- the trial inhibits the remediator's response and NOTHING else -----------------------------------------
def test_the_trial_touches_no_other_defence():
    """WAF, operator login (e-mail + password + code), the attempt budget and the containment control itself
    are untouched: the only thing a trial changes is whether the remediator answers incidents during its window."""
    window = (ROOT / 'services/remediator/main.py').read_text(encoding='utf-8')
    window = window.split('trial={')[1].split('def in_flight')[0]
    for untouched in ('/control/contain', 'control_key', 'httpx', 'auth', 'attempts', 'nginx', 'waf'):
        assert untouched not in window, f'a control trial must not reach {untouched}'
    # The inhibited branch of recover() does exactly two things and calls nothing else. Comments are dropped
    # first: the branch explains in prose what it does NOT do, and that prose must not read as code.
    branch = (ROOT / 'services/remediator/main.py').read_text(encoding='utf-8')
    branch = branch.split('if trial_active():')[1].split('        # The ban is decided')[0]
    code = '\n'.join(line for line in branch.splitlines() if not line.lstrip().startswith('#'))
    assert 'trial_close(' not in code and "update(incident_id,'observed'" in code
    for forbidden in ('create_subprocess_exec', 'business_verify', 'bans.', 'contain('):
        assert forbidden not in code, f'the inhibited branch must not call {forbidden}'


def test_the_other_services_are_not_aware_of_the_trial_at_all():
    """Nothing was added to payment, detector or auth: the detector keeps detecting, the WAF keeps filtering."""
    for service in ('payment/main.py', 'detector/main.py', 'auth/main.py'):
        text = (ROOT / 'services' / service).read_text(encoding='utf-8')
        for word in ('control_trial', 'trial_active', 'control-trial', 'essai temoin'):
            assert word not in text, f'{service} must not know about the control trial ({word})'


def test_the_published_surface_adds_exactly_one_operator_route():
    waf = (ROOT / 'infra/nginx/default.conf').read_text(encoding='utf-8')
    assert waf.count('/ops/control-trial') == 1
    assert 'limit_except GET POST { deny all; }' in waf                 # no other verb reaches the remediator
    remediator_routes = [line for line in waf.splitlines() if 'remediator:8000' in line]
    assert len(remediator_routes) == 2                                  # /ops/status and /ops/control-trial, nothing else
    assert 'down -v' not in waf
