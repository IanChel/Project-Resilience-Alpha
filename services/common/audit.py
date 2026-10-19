"""JSON audit trail without credentials, request bodies or token headers."""
import json
import os
import time
from pathlib import Path

def emit(service, event, **fields):
    record = {'ts':time.time(), 'service':service, 'event':event, **fields}
    line = json.dumps(record, separators=(',',':'))
    print(line, flush=True)
    folder = Path(os.getenv('LOG_DIR','/logs'))
    folder.mkdir(parents=True,exist_ok=True)
    with (folder / (service+'.jsonl')).open('a') as f:
        f.write(line+'\n')
