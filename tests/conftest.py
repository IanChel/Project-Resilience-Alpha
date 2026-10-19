import pytest
@pytest.fixture(autouse=True)
def lab_env(tmp_path,monkeypatch):
    secrets=tmp_path/'secrets'; secrets.mkdir()
    for name in ['session_key','alice_password','loadbot_password','control_key','alert_key','db_password']:
        (secrets/name).write_text(name+'_'+'test-only-'*4)
    monkeypatch.setenv('SECRETS_DIR',str(secrets))
    monkeypatch.setenv('LOG_DIR',str(tmp_path/'logs'))
    return secrets
@pytest.fixture
def payment(tmp_path,monkeypatch):
    import services.payment.main as p
    from services.payment.db import Ledger
    monkeypatch.setattr(p,'ledger',Ledger(str(tmp_path/'ledger.sqlite')))
    monkeypatch.setattr(p,'policy_path',tmp_path/'state'/'policy.json')
    monkeypatch.setattr(p,'contained',False)
    monkeypatch.setattr(p,'active',0)
    p.last_quote.clear(); p.ledger.init()
    return p
