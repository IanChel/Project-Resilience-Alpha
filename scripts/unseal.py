import json
import os
import subprocess
from pathlib import Path
base=Path(__file__).resolve().parents[1]/'.secrets'
env={**os.environ,'SOPS_AGE_KEY_FILE':str(base/'age.key')}
result=subprocess.run(['sops','--decrypt',str(base/'secrets.enc.json')],env=env,capture_output=True,text=True,check=True)
data=json.loads(result.stdout)
(base/'runtime').mkdir(mode=0o700,exist_ok=True)
for name,value in data.items():
    if name not in {'db_password','session_key','control_key','alert_key','alice_password','loadbot_password','grafana_password'}:
        raise SystemExit('Unexpected secret name')
    path=base/'runtime'/name
    if path.exists(): path.chmod(0o600)
    path.write_text(value+'\n'); path.chmod(0o444)
print('Runtime secrets restored; values were not logged.')
