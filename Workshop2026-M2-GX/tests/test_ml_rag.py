import numpy as np
import pytest
from services.detector.model import train_model,score
from services.rag.retrieval import Corpus

def baseline():
    rng=np.random.default_rng(42)
    return np.column_stack([rng.uniform(0.5,2,100),rng.integers(0,2,100),np.zeros(100),np.zeros(100)])
def test_ml_novelty_detection_on_synthetic_unit_fixture():
    model=train_model(baseline())
    attack=score(model,[20,4,30,30])
    assert attack<0
    assert score(model,[1,0,0,0])>attack

def test_refuse_poisoned_or_short_baseline():
    rows=baseline();rows[5,2]=1
    with pytest.raises(ValueError): train_model(rows)
    with pytest.raises(ValueError): train_model(baseline()[:10])
    with pytest.raises(ValueError): score(train_model(baseline()),[float('nan'),0,0,0])

def test_document_retrieval_is_grounded(tmp_path):
    (tmp_path/'restore.md').write_text('La reprise du paiement exige une transaction confirmée et un registre cohérent. '*20)
    (tmp_path/'other.md').write_text('La couleur du tableau de bord est bleue. '*20)
    hits=Corpus(tmp_path).retrieve('Comment vérifier la reprise du paiement ?')
    assert hits[0]['source']=='restore.md'
    assert 'transaction' in hits[0]['text']
