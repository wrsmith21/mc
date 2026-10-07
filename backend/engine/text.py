"""TF-IDF similarity over invoice-line descriptions. Inverted index, no external ML dependencies."""
import math
import re
from collections import Counter, defaultdict

STOP = {"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "the", "and",
        "for", "of", "to", "in", "on", "at", "inc", "ltd", "llc", "per", "incl", "x", "with", "by", "a", "an",
        "january", "february", "march", "april", "june", "july", "august", "september", "october", "november",
        "december"}
TOKEN = re.compile(r"[a-z][a-z0-9\-/&]+|[0-9]{3,}[a-z]+[0-9a-z]*")


CODE = re.compile(r"^[a-z]{1,3}[-/]?\d+$")  # matter numbers, reference codes: identifiers, not meaning


def tokens(text: str):
    words = [w.strip("-/") for w in TOKEN.findall(text.lower())]
    words = [w for w in words if w and w not in STOP and not w.isdigit() and not CODE.match(w)]
    return words + [f"{a}_{b}" for a, b in zip(words, words[1:])]


class TfIdfIndex:
    def __init__(self, texts):
        self.n = len(texts)
        df = Counter()
        docs = []
        for t in texts:
            tf = Counter(tokens(t))
            docs.append(tf)
            df.update(tf.keys())
        self.idf = {w: math.log((1 + self.n) / (1 + c)) + 1 for w, c in df.items()}
        self.postings = defaultdict(list)
        self.norms = []
        for i, tf in enumerate(docs):
            weights = {w: (1 + math.log(c)) * self.idf[w] for w, c in tf.items()}
            norm = math.sqrt(sum(v * v for v in weights.values())) or 1.0
            self.norms.append(norm)
            for w, v in weights.items():
                self.postings[w].append((i, v / norm))

    def query_vector(self, text):
        tf = Counter(tokens(text))
        weights = {w: (1 + math.log(c)) * self.idf[w] for w, c in tf.items() if w in self.idf}
        norm = math.sqrt(sum(v * v for v in weights.values())) or 1.0
        return {w: v / norm for w, v in weights.items()}

    def search(self, text, k=50, restrict=None):
        q = self.query_vector(text)
        scores = defaultdict(float)
        for w, qv in q.items():
            for i, dv in self.postings[w]:
                if restrict is None or i in restrict:
                    scores[i] += qv * dv
        return sorted(scores.items(), key=lambda kv: -kv[1])[:k]
