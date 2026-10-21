"""Writing secret files, portably.

The repository lives on a Windows drive and docs/INSTALL.md says to work from WSL, so the secrets land on
/mnt/c (DrvFs). There, POSIX modes cannot be applied: chmod raises `Operation not permitted` unless WSL
metadata is enabled. Hardening is therefore BEST EFFORT: it is applied where the filesystem supports it, and
where it does not the caller is told plainly rather than the run crashing after the keys are already written.
What protects the secrets on Windows is the NTFS permissions of the user profile, the fact that `.secrets/` is
git-ignored and excluded from the delivery archive (see docs/06-SECURITE.md)."""
import os
from pathlib import Path
NAMES={'db_password','session_key','control_key','alert_key','alice_password','loadbot_password','grafana_password',
       'operator_email','operator_password_hash','gmail_app_password'}
def harden(path,mode):
    """chmod if the filesystem allows it. Returns True when the mode was really applied."""
    try: os.chmod(path,mode)
    except (PermissionError,NotImplementedError,OSError): return False
    return True
def write_secret(path,value):
    """Write one secret, replacing a read-only file if there is one. Returns True if the mode was applied."""
    path=Path(path)
    if path.exists(): harden(path,0o600)
    path.write_text(value+'\n',encoding='utf-8')
    return harden(path,0o444)
def report(folder,applied):
    """One honest line about the state of the permissions."""
    if applied: return f'Permissions restreintes appliquees sur {folder}.'
    return (f'ATTENTION : permissions POSIX non applicables sur {folder} (volume Windows monte dans WSL).\n'
            f'  Les fichiers restent lisibles par votre compte Windows. Protection effective : profil NTFS,\n'
            f"  .secrets/ ignore par git et exclu de l'archive. Ne jamais copier ce dossier ailleurs.")
