from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
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
    def retrieve(self,question,k=3):
        scores=cosine_similarity(self.vectorizer.transform([question]),self.matrix)[0]
        return [{**self.chunks[i],'similarity':float(scores[i])} for i in scores.argsort()[::-1][:k] if scores[i]>0.08]
