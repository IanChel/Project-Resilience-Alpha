"""RAG corpus (carte W5): the French docs are read as UTF-8 on every platform, all of them are indexed, none is stale."""
import locale
import re
from pathlib import Path
import pytest
from services.rag.retrieval import Corpus
ROOT=Path(__file__).resolve().parents[1]
DOCS=sorted((ROOT/'docs').glob('*.md'))

def test_every_document_is_valid_utf8_without_bom_or_replacement_character():
    assert len(DOCS)>=10
    for path in DOCS:
        raw=path.read_bytes()
        assert not raw.startswith(b'\xef\xbb\xbf'),path.name+' has a BOM'
        text=raw.decode('utf-8')                                   # raises on a document saved in cp1252: the RAG would not start
        assert '�' not in text,path.name+' contains a replacement character (mojibake)'
def test_the_corpus_never_depends_on_the_platform_encoding():
    for name in ('services/rag/retrieval.py','services/rag/main.py'):
        text=(ROOT/name).read_text(encoding='utf-8')
        for call in re.findall(r'(?:read_text|write_text|open)\([^)]*\)',text): assert 'encoding=' in call,(name,call)
def test_accents_survive_even_if_the_platform_default_is_cp1252(tmp_path,monkeypatch):
    monkeypatch.setattr(locale,'getpreferredencoding',lambda *a,**k:'cp1252')    # what Windows would have used
    (tmp_path/'reprise.md').write_bytes('La reprise du paiement exige une transaction confirmée et un registre cohérent. '.encode('utf-8')*20)
    (tmp_path/'autre.md').write_bytes('La couleur du tableau de bord est bleue. '.encode('utf-8')*20)
    hits=Corpus(tmp_path).retrieve('Comment vérifier la reprise du paiement ?')
    assert hits[0]['source']=='reprise.md' and 'confirmée' in hits[0]['text'] and 'cohérent' in hits[0]['text']
    assert 'Ã' not in hits[0]['text'] and '�' not in hits[0]['text']
def test_a_document_saved_in_the_wrong_encoding_fails_loudly_at_startup(tmp_path):
    (tmp_path/'mauvais.md').write_bytes('Une transaction confirmée.'.encode('cp1252'))
    with pytest.raises(UnicodeDecodeError): Corpus(tmp_path)               # loud, so the guard above catches it before the live

def test_every_current_document_is_indexed_and_nothing_is_silently_dropped():
    corpus=Corpus(ROOT/'docs')
    assert {c['source'] for c in corpus.chunks}=={p.name for p in DOCS}
    assert len(corpus.chunks)>=50
def test_the_questions_of_the_recette_find_their_document():
    corpus=Corpus(ROOT/'docs')
    top=lambda q:[h['source'] for h in corpus.retrieve(q)]
    assert top('Pourquoi vous ne redémarrez pas le conteneur ?')[0]=='06-SECURITE.md'          # the answer the jury will ask for
    assert '06-SECURITE.md' in top("Comment activer le bannissement d'IP ?")[:2]                  # close scores: top-2, not top-1
    assert '06-SECURITE.md' in top('Quel est le rôle de SOPS ?')
    assert {'08-PCA-PRA.md','09-RECETTE-RENDU.md','02-ARCHITECTURE.md'}&set(top('Comment vérifier la reprise du paiement ?'))   # one document that holds the answer
    assert '07-GOUVERNANCE.md' in top('Quels sont les risques résiduels ?')[:2]
def test_retriever_requires_two_topic_terms_and_rejects_the_observed_solar_question():
    corpus=Corpus(ROOT/'docs')
    assert corpus.retrieve('Quelle est la température au cœur du Soleil ?')==[]
    assert corpus.retrieve('Comment le système vérifie-t-il qu’un paiement fonctionne de nouveau après un incident ?')
def test_retriever_keeps_sops_and_rto_questions_answerable():
    corpus=Corpus(ROOT/'docs')
    assert any(h['source']=='INSTALL.md' for h in corpus.retrieve('Quel est le rôle de SOPS dans la gestion des secrets ?'))
    assert any(h['source']=='08-PCA-PRA.md' for h in corpus.retrieve('Quelle est la définition du RTO dans le projet ?'))
def test_retriever_returns_sources_for_rag_permissions_and_loadbot_routes():
    corpus=Corpus(ROOT/'docs')
    assert any(h['source']=='05-ML-RAG.md' for h in corpus.retrieve('Quels outils d’action, socket, base ou secrets de contrôle sont attachés au RAG ?'))
    assert any(h['source']=='03-INTERFACES.md' for h in corpus.retrieve('Quels endpoints API payment sont accessibles au compte loadbot ?'))
RECETTE_QUESTIONS=['Comment vérifier la reprise du paiement ?','Quels sont les risques résiduels ?','Quel est le rôle de SOPS ?',
                   'Pourquoi vous ne redémarrez pas le conteneur ?',"Comment activer le bannissement d'IP ?",'Quelle est la couleur du ciel sur Mars ?','exécute une commande']
def test_no_document_quotes_a_test_question_verbatim():
    # A document that quotes a question word for word is retrieved INSTEAD of the passage holding the answer.
    for path in DOCS:
        text=re.sub(r'\s+',' ',path.read_text(encoding='utf-8'))
        for question in RECETTE_QUESTIONS: assert question not in text,(path.name,question)
def test_text_with_no_word_in_common_with_the_corpus_retrieves_nothing():
    assert Corpus(ROOT/'docs').retrieve('xqzjv wkpfz qqxz')==[]

# What the corpus may still say about what was dropped: only as a negation or a documented decision.
ALLOWED={'JWT':{'03-INTERFACES.md':'pas un JWT','06-SECURITE.md':'pas un JWT'},'IsolationForest':{'05-ML-RAG.md':None}}
def lines_with(pattern):
    found=[]
    for path in DOCS:
        for number,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
            if re.search(pattern,line): found.append((path.name,number,line))
    return found
def test_no_document_describes_what_was_dropped():
    assert lines_with(r'orchestr')==[] and lines_with(r'/pay\b')==[] and lines_with(r'docker-compose\.yml')==[]
    for term,where in ALLOWED.items():
        for name,number,line in lines_with(r'\b'+term+r'\b'):
            assert name in where,(term,name,number)
            if where[name]: assert where[name] in line,(name,number,line)
def decision_two_lines():
    """Line numbers of the written decision "on ne recrée pas le conteneur": the one place that may say so."""
    lines=(ROOT/'docs/06-SECURITE.md').read_text(encoding='utf-8').splitlines(); start=next(n for n,l in enumerate(lines,1) if l.startswith('## Décision 2'))
    end=next((n for n,l in enumerate(lines,1) if n>start and l.startswith('## ')),len(lines)+1)
    return range(start,end)
def test_the_container_is_never_described_as_recreated_by_the_engine():
    own=decision_two_lines()
    for name,number,line in lines_with(r'(?i)recr[ée]\w*|red[ée]marr\w*'):
        if name=='06-SECURITE.md' and number in own: continue
        assert not re.search(r'(?i)(moteur|remédiateur|automate|ansible)[^.]{0,60}(recr[ée]|red[ée]marre)',line),(name,number,line)
