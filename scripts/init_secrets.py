"""Run inside WSL. Requires age-keygen and sops. Never prints generated secrets."""
import json
import getpass
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from secret_files import NAMES, harden, report, write_secret
root=Path(__file__).resolve().parents[1]
base=root/'.secrets'
def configure_operator():
    """Add operator login and Gmail SMTP credentials to the SOPS store without displaying them."""
    if not all(shutil.which(x) for x in ('age-keygen','sops')):
        raise SystemExit('Install age and sops in WSL before configuring operator login.')
    encrypted=base/'secrets.enc.json'
    age_key=base/'age.key'
    if not encrypted.is_file() or not age_key.is_file():
        raise SystemExit('Existing .secrets/secrets.enc.json and .secrets/age.key are required.')
    email=input('Adresse e-mail opérateur (destinataire et expéditeur Gmail) : ').strip()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email):
        raise SystemExit('Adresse e-mail invalide.')
    password=getpass.getpass('Nouveau mot de passe opérateur (12 caractères minimum) : ')
    if len(password)<12 or len(password)>128:
        raise SystemExit('Le mot de passe opérateur doit contenir entre 12 et 128 caractères.')
    confirmation=getpass.getpass('Confirmer le mot de passe opérateur : ')
    if password!=confirmation:
        raise SystemExit('Les mots de passe opérateur ne correspondent pas.')
    app_password=''.join(getpass.getpass('Mot de passe d’application Gmail (sans espaces) : ').split())
    if len(app_password)!=16:
        raise SystemExit('Le mot de passe d’application Gmail doit contenir 16 caractères.')
    env={**os.environ,'SOPS_AGE_KEY_FILE':str(age_key)}
    result=subprocess.run(['sops','--decrypt',str(encrypted)],env=env,capture_output=True,text=True,check=True)
    data=json.loads(result.stdout)
    operator_names={'operator_email','operator_password_hash','gmail_app_password'}
    if not isinstance(data,dict) or not (NAMES-operator_names).issubset(data) or not all(isinstance(v,str) for v in data.values()):
        raise SystemExit('Le fichier SOPS n’a pas le schéma de secrets attendu; aucun changement écrit.')
    pub=subprocess.check_output(['age-keygen','-y',str(age_key)],text=True).strip()
    # Import late so a bad input or missing existing SOPS file never changes runtime state.
    sys.path.insert(0,str(root))
    from services.auth.passwords import hash_password
    data.update(operator_email=email,operator_password_hash=hash_password(password),gmail_app_password=app_password)
    encrypted_result=subprocess.run(['sops','--encrypt','--age',pub,'--input-type','json','--output-type','json','/dev/stdin'],
                                    input=json.dumps(data),capture_output=True,text=True,check=True)
    (base/'runtime').mkdir(mode=0o700,exist_ok=True)
    encrypted.write_text(encrypted_result.stdout,encoding='utf-8')
    results=[write_secret(base/'runtime'/name,data[name]) for name in ('operator_email','operator_password_hash','gmail_app_password')]
    applied=all(results)
    print('Operator login and Gmail SMTP credentials saved to the SOPS store and runtime mounts; values were not logged.')
    print(report(base,applied))
if '--configure-operator' in sys.argv:
    configure_operator()
    raise SystemExit(0)
if not all(shutil.which(x) for x in ('age-keygen','sops')):
    raise SystemExit('Install age and sops in WSL before generating secrets. See docs/INSTALL.md')
if base.exists(): raise SystemExit('.secrets already exists: use unseal.py, do not overwrite keys')
os.umask(0o077)
base.mkdir()
subprocess.run(['age-keygen','-o',str(base/'age.key')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
pub=subprocess.check_output(['age-keygen','-y',str(base/'age.key')],text=True).strip()
data={name:secrets.token_urlsafe(32) for name in sorted(NAMES)}
result=subprocess.run(['sops','--encrypt','--age',pub,'--input-type','json','--output-type','json','/dev/stdin'],input=json.dumps(data),capture_output=True,text=True,check=True)
(base/'secrets.enc.json').write_text(result.stdout)
(base/'runtime').mkdir()
# Compose bind-mounted secrets must be readable by non-root container users.
# Hardening is best effort: on a Windows volume mounted in WSL, POSIX modes cannot be applied (secret_files).
applied=all([write_secret(base/'runtime'/name,value) for name,value in data.items()])
applied=harden(base/'age.key',0o400) and applied
print('Encrypted secrets and runtime mounts generated. Keep age.key offline and out of Git/ZIP.')
print(report(base,applied))
