from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
def test_no_docker_socket_no_database_publication():
    compose=yaml.safe_load((ROOT/'compose.yaml').read_text())
    assert 'ports' not in compose['services']['db']
    assert 'ports' not in compose['services']['remediator']
    assert 'docker.sock' not in (ROOT/'compose.yaml').read_text()
    assert 'secrets' in compose['services']['payment']
def test_fixed_playbook_has_no_shell_module():
    text=(ROOT/'infra/ansible/contain.yml').read_text()
    assert 'ansible.builtin.shell' not in text
    assert 'ansible.builtin.command' not in text
    assert 'no_log: true' in text

def test_unsafe_lab_urls_refused():
    import importlib.util
    spec=importlib.util.spec_from_file_location('client',ROOT/'scripts/lab_client.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    import pytest
    for url in ['http://example.com:8080','http://192.168.137.2:8080','http://localhost:8080/other','http://user@localhost:8080']:
        with pytest.raises(ValueError): m.validate_url(url)

def load_attack():
    import importlib.util
    spec=importlib.util.spec_from_file_location('attack_lab',ROOT/'scripts/attack_lab.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m
def test_attack_target_stays_inside_lab():
    import pytest
    m=load_attack()
    assert m.resolve_target(m.DEFAULT_TARGET_HOST)=='http://192.168.137.1:8080'
    assert m.resolve_target('192.168.137.20')=='http://192.168.137.20:8080'
    assert m.resolve_target('localhost')=='http://127.0.0.1:8080'
    for bad in ['example.com','8.8.8.8','192.168.1.10','10.0.0.5','192.168.137.1:8080','http://192.168.137.1','']:
        with pytest.raises(ValueError): m.resolve_target(bad)
def test_attack_refuses_without_ack_or_outside_lab(monkeypatch):
    import asyncio,pytest
    m=load_attack()
    def no_prompt(*_): raise AssertionError('scope guard bypassed: reached the password prompt')
    monkeypatch.setattr(m.getpass,'getpass',no_prompt)
    for argv,env in [(['attack_lab.py'],None),
                     (['attack_lab.py','--lab-authorized','--target','8.8.8.8'],None),
                     (['attack_lab.py','--lab-authorized'],'8.8.8.8')]:
        monkeypatch.setattr('sys.argv',argv)
        if env: monkeypatch.setenv('LAB_TARGET',env)
        with pytest.raises(SystemExit) as exc: asyncio.run(m.main())
        assert exc.value.code==2
