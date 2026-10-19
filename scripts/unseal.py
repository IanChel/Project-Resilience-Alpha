import json
import os
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from secret_files import NAMES, report, write_secret
base=Path(__file__).resolve().parents[1]/'.secrets'
env={**os.environ,'SOPS_AGE_KEY_FILE':str(base/'age.key')}
result=subprocess.run(['sops','--decrypt',str(base/'secrets.enc.json')],env=env,capture_output=True,text=True,check=True)
data=json.loads(result.stdout)
(base/'runtime').mkdir(mode=0o700,exist_ok=True)
applied=True
for name,value in data.items():
    if name not in NAMES: raise SystemExit('Unexpected secret name')
    applied=write_secret(base/'runtime'/name,value) and applied
print('Runtime secrets restored; values were not logged.')
print(report(base,applied))
