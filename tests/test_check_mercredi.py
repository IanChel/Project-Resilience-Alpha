"""scripts/check_mercredi.py (carte W7): judges the last acceptance evidence. Evidence is produced by the REAL acceptance.py
against the simulated lab of test_acceptance_evidence, so the two scripts are tested against each other."""
import importlib.util
import json
import re
from pathlib import Path
from tests.test_acceptance_evidence import Lab,run as run_acceptance
ROOT=Path(__file__).resolve().parents[1]
BAN={'enabled':True,'requested':['192.168.137.20'],'eligible':['192.168.137.20'],'excluded':[],'ttl_s':300,'applied':['192.168.137.20']}
def load():
    spec=importlib.util.spec_from_file_location('check_mercredi',ROOT/'scripts/check_mercredi.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.head=lambda:'abc123'                                                                   # deterministic: no git in the unit tests
    return m
def produce(monkeypatch,tmp_path,capsys,lab,subdir=None):
    where=tmp_path if subdir is None else tmp_path/subdir
    where.mkdir(exist_ok=True)
    run_acceptance(lab,monkeypatch,where,capsys); capsys.readouterr()
    return where/'runtime'/'evidence'
def judge(folder,capsys,*args,m=None):
    m=m or load(); code=m.main(['--evidence-dir',str(folder),*args]); return code,capsys.readouterr().out
def rewrite(folder,edit):
    path=next(folder.glob('acceptance-*.json')); data=json.loads(path.read_text()); edit(data); path.write_text(json.dumps(data))
def verdicts(out): return [line.split('...')[1].strip().split(' ')[0] for line in out.splitlines() if line.startswith('[')]

def test_a_complete_run_with_a_ban_validates_the_milestone(monkeypatch,tmp_path,capsys):
    folder=produce(monkeypatch,tmp_path,capsys,Lab(ban=BAN)); code,out=judge(folder,capsys)
    assert code==0 and '5/5 verifications OK' in out and 'jalon W7 VALIDE' in out and 'ECHEC' not in out
    assert '6.5 s de la detection' in out and 'consecutive=3, nu=0.03' in out and 'ban pose sur 192.168.137.20' in out and 'transaction temoin tx-77 validee' in out
def test_the_disabled_ban_overlay_is_not_a_failure(monkeypatch,tmp_path,capsys):
    # The real remediator always writes a ban dict; off by default. The optional overlay being off must NOT fail W7.
    folder=produce(monkeypatch,tmp_path,capsys,Lab(ban={'enabled':False,'eligible':[],'excluded':[],'note':'bans disabled (BAN_ENABLED not set)'}))
    code,out=judge(folder,capsys)
    assert code==0 and '5/5 verifications OK' in out and 'jalon W7 VALIDE' in out
    assert verdicts(out)==['OK','OK','OK','OK','OK'] and 'N/A : bannissement optionnel non active' in out
def test_missing_ban_information_is_a_failure(monkeypatch,tmp_path,capsys):
    folder=produce(monkeypatch,tmp_path,capsys,Lab(ban=BAN))
    rewrite(folder,lambda d:d['summary'].__setitem__('ban',None)); code,out=judge(folder,capsys)
    assert code==1 and 'aucune information de ban' in out
def test_a_ban_that_is_ON_but_broken_has_its_own_reason(monkeypatch,tmp_path,capsys):
    folder=produce(monkeypatch,tmp_path,capsys,Lab(ban=BAN))
    cases=[({'enabled':True,'eligible':[],'excluded':[{'ip':'172.18.0.1','reason':'outside the lab network'}]},"WAF n'a pas vu l'adresse du PC Attaquant"),
           ({'enabled':True,'eligible':['192.168.137.20'],'excluded':[],'applied':[]},'ban non pose')]
    for ban,needle in cases:
        rewrite(folder,lambda d,ban=ban:d['summary'].__setitem__('ban',ban)); code,out=judge(folder,capsys)
        assert code==1 and needle in out,needle
def test_a_ban_with_a_witness_that_failed_is_not_a_success(monkeypatch,tmp_path,capsys):
    folder=produce(monkeypatch,tmp_path,capsys,Lab(ban=BAN))
    rewrite(folder,lambda d:d['summary']['witness'].__setitem__('verdict','failed')); code,out=judge(folder,capsys)
    assert code==1 and 'le ban a pu bloquer la verification' in out and 'transaction temoin' in out
def test_over_sixty_seconds_is_a_failure_that_shows_where_the_time_went(monkeypatch,tmp_path,capsys):
    folder=produce(monkeypatch,tmp_path,capsys,Lab(ban=BAN))
    def slow(d):
        steps=d['summary']['incident']['steps']; base=steps[0]['at']
        for s,off in zip(steps,(0,0.5,20.0,71.3)): s['at']=base+off; s['offset_s']=off
        d['summary']['incident']['detection_to_recovered_s']=71.3; d['summary']['incident']['within_target']=False
    rewrite(folder,slow); code,out=judge(folder,capsys)
    assert code==1 and '71.3 s, la cible est sous 60 s' in out and 'verifying +20.0 s' in out and 'recovered +71.3 s' in out
def test_the_target_can_be_tightened_for_thursday(monkeypatch,tmp_path,capsys):
    folder=produce(monkeypatch,tmp_path,capsys,Lab(ban=BAN))
    assert judge(folder,capsys,'--max-seconds','60')[0]==0
    code,out=judge(folder,capsys,'--max-seconds','5'); assert code==1 and '6.5 s, la cible est sous 5 s' in out
def test_an_announced_total_that_does_not_match_the_stages_is_not_trusted(monkeypatch,tmp_path,capsys):
    folder=produce(monkeypatch,tmp_path,capsys,Lab(ban=BAN))
    rewrite(folder,lambda d:d['summary']['incident'].__setitem__('detection_to_recovered_s',3.0)); code,out=judge(folder,capsys)
    assert code==1 and 'incoherence : le total annonce (3.0 s) differe des etapes (6.5 s)' in out
def test_stage_times_in_the_wrong_order_are_not_trusted(monkeypatch,tmp_path,capsys):
    folder=produce(monkeypatch,tmp_path,capsys,Lab(ban=BAN),subdir='disordered')
    rewrite(folder,lambda d:d['summary']['incident']['steps'][1].__setitem__('at',d['summary']['incident']['steps'][0]['at']-5))
    code,out=judge(folder,capsys); assert code==1 and 'dans le desordre' in out
def test_missing_stage_times_are_reported_not_crashed_on(monkeypatch,tmp_path,capsys):
    folder=produce(monkeypatch,tmp_path,capsys,Lab(ban=BAN))
    rewrite(folder,lambda d:d['summary']['incident']['steps'][2].__setitem__('at',None)); code,out=judge(folder,capsys)
    assert code==1 and 'etapes absentes : verifying' in out and 'horodatages d\'etapes absents' in out and 'erreur inattendue' not in out
def test_a_failed_recovery_or_a_human_request_is_an_intervention(monkeypatch,tmp_path,capsys):
    folder=produce(monkeypatch,tmp_path,capsys,Lab(outcome='failed',ban=BAN)); code,out=judge(folder,capsys)
    assert code==1 and 'en failed : la reprise a echoue' in out and 'manual_review_required (un humain est demande)' in out and 'passed=false' in out
def test_an_incident_without_a_detection_looks_hand_made(monkeypatch,tmp_path,capsys):
    folder=produce(monkeypatch,tmp_path,capsys,Lab(ban=BAN))
    def hand_made(d):
        for row in d['observations']:
            for i in row.get('incidents',[]): i['stages']={k:v for k,v in i['stages'].items() if k!='detected'}
    rewrite(folder,hand_made); code,out=judge(folder,capsys)
    assert code==1 and 'sans detection (cree a la main ?)' in out
def test_a_run_with_no_incident_proves_nothing(monkeypatch,tmp_path,capsys):
    folder=produce(monkeypatch,tmp_path,capsys,Lab(attack=False)); code,out=judge(folder,capsys)
    assert code==1 and 'etapes absentes : detected, containing, verifying, recovered' in out and 'aucun incident observe' in out
def test_a_missing_detector_configuration_is_reported(monkeypatch,tmp_path,capsys):
    folder=produce(monkeypatch,tmp_path,capsys,Lab(ban=BAN,config=False)); code,out=judge(folder,capsys)
    assert code==1 and 'configuration du detecteur absente' in out and '4/5' in out
def test_an_invalid_detector_configuration_is_reported(monkeypatch,tmp_path,capsys):
    for n,bad in enumerate(({'consecutive':0,'nu':0.03},{'consecutive':3,'nu':None},{'consecutive':3,'nu':1.5},{'consecutive':'3','nu':0.03})):
        folder=produce(monkeypatch,tmp_path,capsys,Lab(ban=BAN),subdir=f'invalid{n}')
        rewrite(folder,lambda d,bad=bad:d['summary'].__setitem__('detector_config',bad))
        assert 'configuration incomplete ou invalide' in judge(folder,capsys)[1],bad
def test_an_evidence_from_an_older_acceptance_is_refused_with_the_fix(tmp_path,capsys):
    folder=tmp_path/'e'; folder.mkdir(); (folder/'acceptance-1700000000.json').write_text(json.dumps({'observations':[],'passed':True}))
    code,out=judge(folder,capsys)
    assert code==1 and out.count('ECHEC')==5 and 'preuve sans bloc `summary`' in out and 'la refaire avec le script a jour' in out
def test_no_evidence_at_all_says_how_to_produce_one(tmp_path,capsys):
    code,out=judge(tmp_path/'nothing',capsys)
    assert code==1 and out.count('ECHEC')==5 and 'aucune preuve acceptance-*.json' in out and 'python scripts/acceptance.py' in out
def test_the_latest_proof_is_chosen_by_the_epoch_in_its_name(tmp_path,capsys):
    m=load(); folder=tmp_path/'e'; folder.mkdir()
    for epoch in (1700000500,1700000200,1700000900): (folder/f'acceptance-{epoch}.json').write_text('{}')
    (folder/'acceptance-notes.json').write_text('{}'); (folder/'other.json').write_text('{}')
    assert m.latest(folder).name=='acceptance-1700000900.json'
    explicit=folder/'acceptance-1700000200.json'; code,out=judge(folder,capsys,'--file',str(explicit),m=m)
    assert code==1 and str(explicit) not in out and 'preuve sans bloc `summary`' in out    # the named file was read, and refused for what it contains
def test_a_proof_from_another_commit_or_a_dirty_tree_is_flagged(monkeypatch,tmp_path,capsys):
    folder=produce(monkeypatch,tmp_path,capsys,Lab(ban=BAN))
    rewrite(folder,lambda d:d['summary'].__setitem__('code_version',{'commit':'ffff0000aaaa','dirty':True})); code,out=judge(folder,capsys)
    assert code==0 and 'preuve produite avec le commit ffff0000, le depot est a abc123' in out and 'modifications non commitees' in out
def test_it_reads_only_and_never_starts_anything(monkeypatch,tmp_path,capsys):
    folder=produce(monkeypatch,tmp_path,capsys,Lab(ban=BAN)); before={p.name:p.read_bytes() for p in folder.iterdir()}
    judge(folder,capsys); assert {p.name:p.read_bytes() for p in folder.iterdir()}==before
    text=(ROOT/'scripts/check_mercredi.py').read_text()
    assert not re.search(r'write_text|write_bytes|mkdir|\bopen\(|httpx|requests|docker|\bPOST\b',text)   # it only reads, and never talks to the lab
    assert re.findall(r'subprocess\.run\(\[([^\]]*)\]',text)==["'git','rev-parse','HEAD'"]              # the single command it may run
