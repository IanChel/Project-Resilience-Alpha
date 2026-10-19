"""Run inside WSL. Requires age-keygen and sops. Never prints generated secrets."""
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from secret_files import NAMES, harden, report, write_secret
root=Path(__file__).resolve().parents[1]
base=root/'.secrets'
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
