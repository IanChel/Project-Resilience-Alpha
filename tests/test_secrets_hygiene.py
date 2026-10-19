"""SOPS (carte W4): decrypted secrets exist in .secrets/runtime/ only, and stay out of git, logs and the archive.
A guard: a later fix must not quietly undo it."""
import re
import shutil
import subprocess
from pathlib import Path
import pytest
import yaml
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[1]
def sources():
    return [p for folder in ('scripts','services') for p in (ROOT/folder).rglob('*.py') if '__pycache__' not in p.parts]
def rel(p): return p.relative_to(ROOT).as_posix()

def test_a_single_helper_writes_secret_values():
    writers={rel(p) for p in sources() if re.search(r"write_text\(\s*value",p.read_text(encoding='utf-8'))}
    assert writers=={'scripts/secret_files.py'}                        # one place writes a secret value, and only one
    helper=(ROOT/'scripts/secret_files.py').read_text(encoding='utf-8')
    assert 'def write_secret(path,value)' in helper                    # the caller supplies the path
    assert not re.search(r"/\s*['\"]\.secrets",helper)                 # ...and builds no path of its own
def test_only_init_and_unseal_write_secrets_and_only_under_runtime():
    callers={rel(p) for p in sources() if 'write_secret(' in p.read_text(encoding='utf-8') and p.name!='secret_files.py'}
    assert callers=={'scripts/init_secrets.py','scripts/unseal.py'}
    for name in callers:   # the destination of every value is built under .secrets/runtime, never anywhere else
        text=(ROOT/name).read_text(encoding='utf-8')
        assert re.search(r"^base\s*=.*'\.secrets'",text,re.M) and "base/'runtime'/name" in text
def test_nothing_else_touches_the_secrets_directory():
    touching={rel(p) for p in sources() if '.secrets' in p.read_text(encoding='utf-8')}
    # init/unseal create it, secret_files documents it, check_lundi reads the Grafana password, package.py excludes it,
    # lab_client only names it as an example: the directory it reads comes from LAB_PASSWORD_DIR, never hard-coded.
    assert touching<={'scripts/init_secrets.py','scripts/unseal.py','scripts/secret_files.py',
                      'scripts/check_lundi.py','scripts/package.py','scripts/lab_client.py'},touching
    assert not re.search(r"/\s*['\"]\.secrets",(ROOT/'scripts/lab_client.py').read_text(encoding='utf-8'))
def test_git_ignores_every_secret_path_and_tracks_none():
    if shutil.which('git') is None or not (ROOT/'.git').exists(): pytest.skip('not a git checkout')
    ignored=subprocess.run(['git','check-ignore','.secrets/runtime/db_password','.secrets/age.key','.secrets/secrets.enc.json','.env'],cwd=ROOT,capture_output=True,text=True)
    assert set(ignored.stdout.split())=={'.secrets/runtime/db_password','.secrets/age.key','.secrets/secrets.enc.json','.env'}
    tracked=subprocess.run(['git','ls-files'],cwd=ROOT,capture_output=True,text=True).stdout.splitlines()
    assert not [f for f in tracked if re.search(r'(^|/)\.secrets/|(^|/)\.env$|\.(key|pem|agekey)$',f)]
def test_compose_mounts_secrets_only_from_the_runtime_directory():
    secrets=yaml.safe_load((ROOT/'compose.yaml').read_text())['secrets']
    assert secrets and all(v['file'].startswith('./.secrets/runtime/') for v in secrets.values())
def test_the_archive_excludes_the_secrets_directory_and_dotenv():
    text=(ROOT/'scripts/package.py').read_text()
    assert "'.secrets'" in re.search(r"excluded=\{[^}]*\}",text).group(0) and "'.env'" not in re.search(r"allowed_files=\{[^}]*\}",text).group(0)
    assert {'.agekey','.joblib','.key','.pyc'}<=set(re.findall(r"'(\.\w+)'",re.search(r"path\.suffix in \{[^}]*\}",text).group(0)))
def test_no_journal_call_carries_a_credential():
    bad=[f'{rel(p)}:{n}' for p in sources() for n,l in enumerate(p.read_text(encoding='utf-8').splitlines(),1)
         if 'emit(' in l and re.search(r'password|token|secret|authorization|api_key',l,re.I) and 'def emit' not in l]
    assert bad==[]

def test_a_login_leaves_no_password_in_any_journal(tmp_path):
    import os
    import services.auth.main as auth
    from services.common.security import secret
    auth.attempts.clear(); wrong='WRONG-password-for-the-journal-test-91'
    with TestClient(auth.app) as client:
        assert client.post('/token',json={'username':'alice','password':wrong}).status_code==401
        assert client.post('/token',json={'username':'alice','password':secret('alice_password')}).status_code==200
    journals=''.join(p.read_text(encoding='utf-8') for p in Path(os.environ['LOG_DIR']).glob('*.jsonl'))
    assert 'login_failed' in journals and 'login_success' in journals                       # the events ARE journaled...
    assert wrong not in journals and secret('alice_password') not in journals                # ...without the credentials
    assert 'access_token' not in journals
