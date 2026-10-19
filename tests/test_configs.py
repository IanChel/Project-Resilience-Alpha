import re
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

def load_client():
    import importlib.util
    spec=importlib.util.spec_from_file_location('client',ROOT/'scripts/lab_client.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m
def test_unsafe_lab_urls_refused():
    m=load_client()
    import pytest
    for url in ['http://example.com:8081','http://192.168.137.2:8081','http://localhost:8081/other','http://user@localhost:8081',
                'http://localhost:8080']:                                   # the old port is now refused too
        with pytest.raises(ValueError): m.validate_url(url)
    assert m.validate_url('http://192.168.137.1:8081')=='http://192.168.137.1:8081'
    assert m.base_url()=='http://127.0.0.1:8081' and m.lab_port()==8081      # published port, not the 8080 inside the stack
def test_the_published_port_follows_lab_port():
    import pytest
    m=load_client()
    assert m.lab_port({'LAB_PORT':'9090'})==9090 and m.base_url('192.168.137.1',{'LAB_PORT':'9090'})=='http://192.168.137.1:9090'
    assert m.validate_url('http://127.0.0.1:9090',{'LAB_PORT':'9090'})=='http://127.0.0.1:9090'
    with pytest.raises(ValueError): m.validate_url('http://127.0.0.1:8081',{'LAB_PORT':'9090'})
    for bad in ('0','70000','abc','-1','80.5'):
        with pytest.raises(ValueError): m.lab_port({'LAB_PORT':bad})
    assert m.lab_port({'LAB_PORT':''})==8081 and m.lab_port({})==8081   # compose passes an empty string when the variable is unset

def load_attack():
    import importlib.util
    spec=importlib.util.spec_from_file_location('attack_lab',ROOT/'scripts/attack_lab.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m
def test_attack_target_stays_inside_lab():
    import pytest
    m=load_attack()
    assert m.resolve_target(m.DEFAULT_TARGET_HOST)=='http://192.168.137.1:8081'
    assert m.resolve_target('192.168.137.20')=='http://192.168.137.20:8081'
    assert m.resolve_target('localhost')=='http://127.0.0.1:8081'
    for bad in ['example.com','8.8.8.8','192.168.1.10','10.0.0.5','192.168.137.1:8081','http://192.168.137.1','']:
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

def compose_services():
    return yaml.safe_load((ROOT/'compose.yaml').read_text())['services']
def test_ansible_can_write_its_temp_dir_in_the_remediator():
    """Ansible resolves ~ from the passwd database (/home/app), not $HOME, and / is read-only: without these
    variables every module fails with "Failed to create temporary directory", so every incident would end in
    manual_review_required. `ansible-playbook --syntax-check` passes even when this is broken."""
    env=compose_services()['remediator']['environment']
    for key in ('ANSIBLE_LOCAL_TEMP','ANSIBLE_REMOTE_TEMP','ANSIBLE_HOME'):
        assert env.get(key,'').startswith('/tmp/'),f'{key} must live under the writable tmpfs: {env.get(key)!r}'
    tmpfs=' '.join(compose_services()['remediator'].get('tmpfs') or [])
    assert '/tmp' in tmpfs and 'rw' in tmpfs                                  # the only writable path in the container
    for key in ('LOG_DIR','STATE_DIR','HOME'): assert key in env,f'{key} lost when the x-app environment was overridden'
def test_a_published_port_requires_a_non_internal_network():
    """A container attached only to an `internal: true` network cannot publish a port: Docker accepts the
    declaration and never establishes the binding. Grafana hit exactly this."""
    compose=yaml.safe_load((ROOT/'compose.yaml').read_text())
    internal={name for name,net in compose['networks'].items() if (net or {}).get('internal')}
    for name,service in compose['services'].items():
        if not service.get('ports'): continue
        attached=set(service.get('networks') or [])
        assert attached-internal,f'{name} publishes {service["ports"]} but is only on internal networks {sorted(attached)}'

def test_the_password_can_come_from_a_directory_for_automation(tmp_path):
    """Needed for Thursday's repeated runs and run-demo.sh: getpass reads the console on Windows, so a script
    cannot feed it through stdin. The default stays interactive."""
    import pytest
    m=load_client()
    (tmp_path/'alice_password').write_text('motdepasse-de-test' + chr(10), encoding='utf-8')
    assert m.password_for('alice',{'LAB_PASSWORD_DIR':str(tmp_path)})=='motdepasse-de-test'   # trailing newline stripped
    with pytest.raises(ValueError,match='does not exist'): m.password_for('loadbot',{'LAB_PASSWORD_DIR':str(tmp_path)})
    (tmp_path/'loadbot_password').write_text('   ' + chr(10), encoding='utf-8')
    with pytest.raises(ValueError,match='empty'): m.password_for('loadbot',{'LAB_PASSWORD_DIR':str(tmp_path)})
    asked=[]
    m.getpass.getpass=lambda prompt='': asked.append(prompt) or 'tape-a-la-main'
    assert m.password_for('alice',{})=='tape-a-la-main' and asked      # nothing set: still interactive
def test_the_password_value_never_travels_through_the_environment():
    text=(ROOT/'scripts/lab_client.py').read_text(encoding='utf-8')
    assert "env.get('LAB_PASSWORD_DIR')" in text                        # a directory of files...
    assert not re.search(r"get\(['\"]LAB_PASSWORD['\"]\)",text)         # ...never the value itself
    assert 'read_text' in text and 'password' not in text.split('def login')[1].split('json=')[0].lower()
