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
