import hashlib
import subprocess
import time
from pathlib import Path
root=Path(__file__).resolve().parents[1];folder=root/'runtime'/'backups';folder.mkdir(parents=True,exist_ok=True)
path=folder/('payments-'+str(int(time.time()))+'.dump')
try:
    with path.open('wb') as f:
        subprocess.run(['docker','compose','exec','-T','db','pg_dump','-U','payments','-d','payments','-Fc'],cwd=root,stdout=f,check=True)
except Exception:
    path.unlink(missing_ok=True);raise
(path.with_suffix('.sha256')).write_text(hashlib.sha256(path.read_bytes()).hexdigest())
print(path)
