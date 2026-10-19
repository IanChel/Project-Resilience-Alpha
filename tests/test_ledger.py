from concurrent.futures import ThreadPoolExecutor
import pytest
from services.payment.db import Ledger,Conflict,Funds
@pytest.fixture
def ledger(tmp_path):
    l=Ledger(str(tmp_path/'ledger.sqlite'));l.init();return l
def test_atomic_transfer_and_conservation(ledger):
    tx,replay=ledger.pay(123,'merchant','sample-key-1')
    s=ledger.snapshot();assert s['total_cents']==200000
    assert s['accounts'][0]['cents']==99877
    assert not replay
    assert tx['amount']==123
def test_concurrent_idempotency_prevents_double_debit(ledger):
    with ThreadPoolExecutor(max_workers=8) as pool:
        out=list(pool.map(lambda _:ledger.pay(100,'merchant','same-request-key'),range(40)))
    assert len({x[0]['id'] for x in out})==1
    assert sum(not x[1] for x in out)==1
    assert ledger.snapshot()['accounts'][0]['cents']==99900
def test_idempotency_payload_mismatch(ledger):
    ledger.pay(100,'merchant','same-key')
    with pytest.raises(Conflict):ledger.pay(101,'merchant','same-key')
    assert ledger.snapshot()['accounts'][0]['cents']==99900
def test_no_partial_debit_on_insufficient_funds(ledger):
    with pytest.raises(Funds):ledger.pay(100001,'merchant','new-key')
    assert len(ledger.snapshot()['transactions'])==0
    assert ledger.snapshot()['total_cents']==200000
