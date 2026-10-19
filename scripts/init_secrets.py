"""Run inside WSL. Requires age-keygen and sops. Never prints generated secrets."""
import json
import os
import secrets
import shutil
import subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
base=root/'.secrets'
if not all(shutil.which(x) for x in ('age-keygen','sops')):
    raise SystemExit('Install age and sops in WSL before generating secrets. See docs/INSTALL.md')
if base.exists(): raise SystemExit('.secrets already exists: use unseal.py, do not overwrite keys')
os.umask(0o077)
base.mkdir()
subprocess.run(['age-keygen','-o',str(base/'age.key')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
pub=subprocess.check_output(['age-keygen','-y',str(base/'age.key')],text=True).strip()
data={name:secrets.token_urlsafe(32) for name in ['db_password','session_key','control_key','alert_key','alice_password','loadbot_password','grafana_password']}
result=subprocess.run(['sops','--encrypt','--age',pub,'--input-type','json','--output-type','json','/dev/stdin'],input=json.dumps(data),capture_output=True,text=True,check=True)
(base/'secrets.enc.json').write_text(result.stdout)
(base/'runtime').mkdir()
for name,value in data.items(): (base/'runtime'/name).write_text(value+'\n')
# Compose bind-mounted secrets must be readable by non-root container users.
# Parent remains 0700 on WSL; the selected files are mounted into authorized containers only.
for path in (base/'runtime').iterdir(): path.chmod(0o444)
print('Encrypted secrets and runtime mounts generated. Keep age.key offline and out of Git/ZIP.')
