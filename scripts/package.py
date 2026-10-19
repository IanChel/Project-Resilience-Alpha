"""Allowlist packaging: private keys, runtime secrets, models and dependencies excluded."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--group',default='X');p.add_argument('--output',default=str(root.parent));a=p.parse_args()
if not a.group.isalnum(): p.error('Group must contain letters or digits only')
name='Workshop2026-M2-G'+a.group
output=Path(a.output);output.mkdir(parents=True,exist_ok=True)
allowed_dirs={'services','frontend','infra','scripts','tests','docs','evidence'}
allowed_files={'README.md','compose.yaml','Dockerfile','Dockerfile.rag','.dockerignore','.gitignore','pytest.ini','requirements.txt','requirements-dev.txt','requirements-rag.txt'}
excluded={'node_modules','dist','__pycache__','.pytest_cache','.git','.secrets','.venv'}
files=[]
for path in sorted(root.rglob('*')):
    if not path.is_file(): continue
    rel=path.relative_to(root)
    if any(x in excluded for x in rel.parts): continue
    if not (rel.parts[0] in allowed_dirs or str(rel) in allowed_files): continue
    if path.suffix in {'.agekey','.joblib','.key','.pyc'}: continue
    files.append((path,rel))
manifest={str(rel):hashlib.sha256(path.read_bytes()).hexdigest() for path,rel in files}
archive=output/(name+'-Code.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for path,rel in files:z.write(path,str(Path(name)/rel))
    z.writestr(name+'/MANIFEST-SHA256.json',json.dumps(manifest,indent=2))
print(archive)
