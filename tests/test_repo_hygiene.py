"""Repository hygiene replayed on every run: what was removed stays removed, and nothing stale is described.
(Monday and Tuesday's fixes must not be quietly undone by a later change.)"""
import re
import shutil
import subprocess
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
def tracked():
    if shutil.which('git') is None or not (ROOT/'.git').exists(): pytest.skip('not a git checkout')
    return subprocess.run(['git','ls-files'],cwd=ROOT,capture_output=True,text=True).stdout.splitlines()

def test_the_dead_scaffold_stays_dead():
    for dead in ('docker-compose.yml','ansible','services/orchestrator','docs/API-CONTRACTS.md','Workshop2026-M2-GX'): assert not (ROOT/dead).exists(),dead
    assert not [f for f in tracked() if f.startswith(('Workshop2026-M2-GX/','ansible/','services/orchestrator/'))]
def test_a_single_compose_file_and_a_single_playbook_directory():
    assert sorted(p.name for p in ROOT.glob('*compose*.y*ml'))==['compose.ban.yaml','compose.yaml']   # compose.ban.yaml is the optional overlay
    assert sorted(p.name for p in ROOT.rglob('contain.yml') if 'node_modules' not in p.parts)==['contain.yml']
def test_nothing_in_the_code_or_docs_describes_what_was_dropped():
    """No orchestrator, no JWT, no IsolationForest, no /pay route, no docker-compose.yml: except as a negation or a documented decision."""
    skip=re.compile(r'^(RAPPORT-|AUDIT-|FIX-|Fix |ETAT-|trello-snapshot|package-lock|tests/)|\.(pdf|png|ico)$')
    pattern=re.compile(r'orchestr\w*|\bJWT\b|isolation ?forest|/pay\b|docker-compose\.yml|ORCHESTRATOR_TOKEN|JWT_SECRET',re.I)
    found=[]
    for name in tracked():
        if skip.search(name): continue
        try: text=(ROOT/name).read_text(encoding='utf-8')
        except (UnicodeDecodeError,OSError): continue
        for number,line in enumerate(text.splitlines(),1):
            for match in pattern.finditer(line): found.append((name,number,match.group(0),line))
    for name,number,term,line in found:
        if term.upper()=='JWT': assert re.search(r"pas un JWT|N'EST PAS un JWT",line),(name,number,line)           # only as a negation
        elif term.lower().replace(' ','')=='isolationforest': assert name=='docs/05-ML-RAG.md',(name,number)       # only in the written decision D-07
        else: pytest.fail(f'{name}:{number} still mentions {term!r}: {line.strip()[:100]}')
def test_dotenv_example_holds_no_secret_and_every_variable_is_read():
    names=[l.split('=')[0] for l in (ROOT/'.env.example').read_text().splitlines() if l and not l.startswith('#')]
    assert names and not [n for n in names if re.search(r'PASSWORD|SECRET|TOKEN|KEY|CREDENTIAL',n,re.I)]
    compose=(ROOT/'compose.yaml').read_text()
    assert all('${'+n in compose for n in names)
def test_the_secret_path_is_ignored_and_no_secret_file_is_tracked():
    assert not [f for f in tracked() if re.search(r'(^|/)\.secrets/|(^|/)\.env$|\.(key|pem|agekey|joblib)$',f)]
    assert '.secrets/' in (ROOT/'.gitignore').read_text().splitlines()
def test_the_repository_is_flat_and_has_no_duplicate_after_removing_the_old_prefix():
    names=[f.removeprefix('Workshop2026-M2-GX/') for f in tracked()]
    assert len(names)==len(set(names))
