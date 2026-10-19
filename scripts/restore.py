import argparse
import hashlib
import subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('backup',type=Path);p.add_argument('--confirm-lab-restore',action='store_true');a=p.parse_args()
if not a.confirm_lab_restore:p.error('Restoration replaces lab database content; pass --confirm-lab-restore')
path=a.backup.resolve()
if not path.is_file():p.error('Backup not found')
checksum=path.with_suffix('.sha256')
if not checksum.is_file() or checksum.read_text().strip()!=hashlib.sha256(path.read_bytes()).hexdigest():p.error('Backup hash invalid or absent')
subprocess.run(['docker','compose','stop','payment'],cwd=root,check=True)
with path.open('rb') as f:
    subprocess.run(['docker','compose','exec','-T','db','pg_restore','-U','payments','-d','payments','--clean','--if-exists','--exit-on-error'],cwd=root,stdin=f,check=True)
subprocess.run(['docker','compose','start','payment'],cwd=root,check=True)
print('Restore command completed. Verify readiness AND a committed transaction before declaring recovery.')
