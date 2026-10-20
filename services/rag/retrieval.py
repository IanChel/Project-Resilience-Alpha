from pathlib import Path
import re
import unicodedata
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# The cosine threshold alone accepts documents that merely mention one related
# word (for example, “astronomy” next to “temperature”). Keep it as a broad
# candidate threshold, then require two distinct, non-generic query terms in
# the same passage (one exact uppercase acronym is sufficient for short
# technical questions). The offline evaluation script records the trade-off.
MIN_COSINE = 0.08
MIN_SHARED_QUERY_TERMS = 2
_STOP_WORDS = frozenset('''
 a au aux avec ce ces dans de des du elle en et eux il je la le les leur lui ma
 mais me meme mes moi mon ne nos notre nous on ou par pas pour qu que quelle
 quelles quel quels qui sa sans se ses son sont sous sur ta te tes toi ton tous
 tout tu un une vos votre vous y comment pourquoi quand combien est sont peut
 doivent doit faut faire fait fonctionne utiliser utilise donne donnez indique
 explique expliquer verifier verifie systeme projet service services
 principal principaux principale principales role
'''.split())

def query_terms(text):
    """Return normalized content words used for the evidence-overlap gate."""
    folded=''.join(ch for ch in unicodedata.normalize('NFKD',text.lower())
                   if not unicodedata.combining(ch))
    terms={term for term in re.findall(r'[a-z0-9]+',folded)
           if len(term)>=3 and term not in _STOP_WORDS and not term.isdigit()}
    # Preserve short, explicit acronyms such as IP; they are often the only
    # strong topic word in a concise technical question.
    terms.update(term.lower() for term in re.findall(r'(?<![A-Za-z0-9])[A-Z][A-Z0-9]{1,}(?![A-Za-z0-9])',text))
    return terms

def shared_query_terms(question, passage):
    return len(query_terms(question) & query_terms(passage))

class Corpus:
    def __init__(self,folder):
        self.chunks=[]
        for path in sorted(Path(folder).glob('*.md')):
            text=path.read_text(encoding='utf-8')
            for i in range(0,len(text),1200):
                self.chunks.append({'source':path.name,'chunk':i//1200,'text':text[i:i+1500]})
        if not self.chunks: raise ValueError('No technical documentation available')
        self.vectorizer=TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),max_features=30000)
        self.matrix=self.vectorizer.fit_transform([c['text'] for c in self.chunks])
    def retrieve(self,question,k=3,min_shared_terms=MIN_SHARED_QUERY_TERMS):
        terms=query_terms(question)
        explicit_acronym=bool(re.search(r'(?<![A-Za-z0-9])[A-Z][A-Z0-9]{1,}(?![A-Za-z0-9])',question))
        required=1 if min_shared_terms and explicit_acronym else min_shared_terms
        if len(terms)<required: return []
        scores=cosine_similarity(self.vectorizer.transform([question]),self.matrix)[0]
        hits=[]
        for i in scores.argsort()[::-1]:
            if scores[i] <= MIN_COSINE: break
            chunk=self.chunks[i]
            overlap=len(terms & query_terms(chunk['text']))
            if overlap < required: continue
            hits.append({**chunk,'similarity':float(scores[i]),'matched_terms':overlap})
            if len(hits)>=k: break
        return hits
