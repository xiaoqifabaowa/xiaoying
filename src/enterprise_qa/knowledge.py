import hashlib
import json
import logging
import re
from pathlib import Path
import jieba
from rank_bm25 import BM25Okapi
from .config import ROOT

jieba.setLogLevel(logging.ERROR)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def tokens(text):
    text = text.lower()
    words = [w for w in jieba.lcut(text) if re.search(r'[\w\u4e00-\u9fff]', w)]
    chars = re.sub(r'\s+', '', text)
    return words + [chars[i:i+2] for i in range(len(chars)-1)]


class Knowledge:
    def __init__(self, documents):
        self.documents = []
        ids = set()
        for source in documents:
            d = dict(source)
            if d['doc_id'] in ids:
                raise ValueError('duplicate document ID')
            ids.add(d['doc_id'])
            d['content_hash'] = fingerprint(d['content'])
            chunks = []
            for match in re.finditer(r'[^\n]+', d['content']):
                chunks.append({'chunk_id': f"{d['doc_id']}:{len(chunks)+1}",
                    'text': match.group(), 'start': match.start(), 'end': match.end()})
            d['chunks'] = chunks
            self.documents.append(d)
        self.version = fingerprint(self.documents)[:16]
        self.by_id = {d['doc_id']: d for d in self.documents}
        self.corpus = [tokens(d['title'] + ' ' + d['content']) for d in self.documents]
        self.bm25 = BM25Okapi(self.corpus) if self.corpus else None

    def search(self, query, top_k=5):
        qt = tokens(query)
        scores = self.bm25.get_scores(qt) if self.bm25 else []
        ranked = []
        for i, d in enumerate(self.documents):
            overlap = len(set(qt) & set(self.corpus[i]))
            if overlap < min(2, max(1, len(set(qt)))):
                continue
            # Lexical overlap keeps very small corpora usable when BM25 IDF is zero/negative.
            score = max(float(scores[i]), 0) + overlap / max(len(set(qt)), 1)
            ranked.append({'doc_id': d['doc_id'], 'title': d['title'],
                'version_date': d['version_date'], 'scope': d.get('scope'),
                'score': round(score, 4), 'snippet': d['content'][:220]})
        ranked.sort(key=lambda d: (-d['score'], d['doc_id']))
        return {'ok': True, 'query': query, 'dataset_version': self.version,
                'retrieval_mode': 'bm25+character_bigrams', 'hits': ranked[:top_k]}

    def read(self, doc_id):
        if doc_id not in self.by_id:
            return {'ok': False, 'error': {'code': 'DOCUMENT_NOT_FOUND',
                'message': '指定文档不存在', 'retryable': False}}
        return {'ok': True, 'dataset_version': self.version, 'document': self.by_id[doc_id]}


def scenarios():
    return json.loads((ROOT / 'data/scenarios.json').read_text(encoding='utf-8'))


def load_knowledge(scenario='normal'):
    spec = next((s for s in scenarios() if s['id'] == scenario), None)
    if spec is None:
        raise ValueError('unknown scenario')
    docs = json.loads((ROOT / 'data/documents.json').read_text(encoding='utf-8'))
    selected = [dict(d) for d in docs if d['doc_id'] in spec['documents']]
    for d in selected:
        if d['doc_id'] in spec.get('overrides', {}):
            d.update(spec['overrides'][d['doc_id']])
    return Knowledge(selected), spec
