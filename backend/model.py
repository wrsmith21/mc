"""Runtime side of the data-science layer: the trained challenger in numpy, and the calibration maps.

scripts/train.py trains with scikit-learn and asserts this module reproduces its probabilities, so production needs
numpy only. Calibration maps raw model scores to the probability of being right, measured on May–Jun 2026.
"""
import json
import math
import re
from functools import lru_cache
from pathlib import Path

import numpy as np

from .store import ROOT

MODEL_DIR = ROOT / "data" / "model"
_TOKEN = re.compile(r"(?u)\b\w\w+\b")
_SPACES = re.compile(r"\s\s+")


def _word_terms(text):
    tokens = _TOKEN.findall(text.lower())
    return tokens + [" ".join(tokens[i:i + 2]) for i in range(len(tokens) - 1)]


def _char_terms(text, lo=3, hi=5):
    out = []
    for w in _SPACES.sub(" ", text.lower()).split():
        w = f" {w} "
        for n in range(lo, hi + 1):
            offset = 0
            out.append(w[offset:offset + n])
            while offset + n < len(w):
                offset += 1
                out.append(w[offset:offset + n])
            if offset == 0:
                break
    return out


def _tfidf(terms, vocab, idf):
    counts = {}
    for t in terms:
        j = vocab.get(t)
        if j is not None:
            counts[j] = counts.get(j, 0) + 1
    vec = {j: c * float(idf[j]) for j, c in counts.items()}
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {j: v / norm for j, v in vec.items()}


class ChallengerModel:
    def __init__(self, path: Path):
        z = np.load(path, allow_pickle=False)
        self.coef, self.intercept = z["coef"].astype(np.float64), z["intercept"].astype(np.float64)
        self.classes = [str(c) for c in z["classes"]]
        self.word_idf, self.char_idf = z["word_idf"], z["char_idf"]
        self.word_vocab = json.loads(str(z["word_vocab"]))
        self.char_vocab = json.loads(str(z["char_vocab"]))
        self.cat = json.loads(str(z["cat_vocab"]))
        self.stats = json.loads(str(z["num_stats"]))
        self.off_char = len(self.word_vocab)
        self.off_cat = self.off_char + len(self.char_vocab)
        self.cat_offsets = [0, len(self.cat["vendor"]), len(self.cat["vendor"]) + len(self.cat["category"])]
        self.off_num = self.off_cat + sum(len(v) for v in self.cat.values())

    def features(self, description, vendor_id, category, entity, amount_usd, unit_usd):
        x = {j: v for j, v in _tfidf(_word_terms(description), self.word_vocab, self.word_idf).items()}
        x.update({self.off_char + j: v for j, v in _tfidf(_char_terms(description), self.char_vocab,
                                                          self.char_idf).items()})
        for off, key, val in zip(self.cat_offsets, ("vendor", "category", "entity"), (vendor_id, category, entity)):
            j = self.cat[key].get(val)
            if j is not None:
                x[self.off_cat + off + j] = 1.0
        nums = [math.log1p(max(amount_usd, 0)), math.log1p(max(unit_usd, 0))]
        for i, v in enumerate(nums):
            x[self.off_num + i] = (v - self.stats["mean"][i]) / self.stats["std"][i]
        return x

    def proba(self, description, vendor_id, category, entity, amount_usd, unit_usd):
        x = self.features(description, vendor_id, category, entity, amount_usd, unit_usd)
        idx = np.fromiter(x.keys(), dtype=np.int64)
        val = np.fromiter(x.values(), dtype=np.float64)
        logits = self.coef[:, idx] @ val + self.intercept
        e = np.exp(logits - logits.max())
        return e / e.sum()

    def explain(self, description, vendor_id, category, entity, amount_usd, unit_usd, account, top=6):
        """Which features pushed this account up: the per-feature contribution to its logit."""
        x = self.features(description, vendor_id, category, entity, amount_usd, unit_usd)
        k = self.classes.index(account)
        names = {}
        inv_w = {v: t for t, v in self.word_vocab.items()}
        inv_c = {v: t for t, v in self.char_vocab.items()}
        contrib = []
        for j, v in x.items():
            c = float(self.coef[k, j] * v)
            if j < self.off_char:
                label = f'word "{inv_w[j]}"'
            elif j < self.off_cat:
                continue  # character n-grams are folded into the word view
            elif j < self.off_num:
                label = "supplier history" if j - self.off_cat < self.cat_offsets[1] else \
                    ("category" if j - self.off_cat < self.cat_offsets[2] else "entity")
            else:
                label = "amount" if j == self.off_num else "unit price"
            names[label] = names.get(label, 0.0) + c
        contrib = sorted(names.items(), key=lambda kv: -abs(kv[1]))[:top]
        return [{"feature": f, "weight": round(w, 3)} for f, w in contrib]


@lru_cache(maxsize=1)
def challenger():
    path = MODEL_DIR / "challenger_weights.npz"
    return ChallengerModel(path) if path.exists() else None


@lru_cache(maxsize=1)
def metrics():
    path = MODEL_DIR / "metrics.json"
    return json.loads(path.read_text()) if path.exists() else None


@lru_cache(maxsize=1)
def _calibration():
    path = MODEL_DIR / "calibration.json"
    return json.loads(path.read_text()) if path.exists() else {}


def calibrate(model_name, raw):
    m = _calibration().get(model_name)
    if not m or not m["x"]:
        return raw
    return float(np.interp(raw, m["x"], m["y"]))


def card():
    path = MODEL_DIR / "model_card.json"
    return json.loads(path.read_text()) if path.exists() else None


def manifest():
    path = MODEL_DIR / "dataset_manifest.json"
    return json.loads(path.read_text()) if path.exists() else []
