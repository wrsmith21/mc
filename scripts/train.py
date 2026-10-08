"""Train, back-test and calibrate the coding models on the 18-month history. Everything is measured, nothing assumed.

    uv run python -m scripts.train

Time-based split, no leakage: train Apr 2025 – Apr 2026, calibrate May – Jun 2026, test Jul – Sep 2026.
  champion   the explainable similarity engine (backend/engine/recommend.py), its history cut at the train boundary
  challenger multinomial logistic regression on description words and characters, supplier, category, entity, amount
  blend      the two combined
Writes data/model/: metrics.json, calibration.json, model_card.json, dataset_manifest.json, challenger_weights.npz.
The runtime never imports scikit-learn: the challenger is re-implemented in numpy and checked against it here.
"""
import json
import math
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score

from backend.engine.recommend import Recommender
from backend.model import ChallengerModel
from backend.store import ROOT, get_store

OUT = ROOT / "data" / "model"
TRAIN_END, CALIB_END = "2026-05-01", "2026-07-01"
PREPAID = {"1310", "1320"}
VERSION = "2026.10.07"


def natural(l):
    return l["amortise_to"] if l["gl"] in PREPAID and l["amortise_to"] else l["gl"]


class HistoryView:
    """The store as it looked at a cut-off date: the champion only sees lines it could have learned from."""

    def __init__(self, store, before):
        self.__dict__.update({k: v for k, v in store.__dict__.items()})
        self.lines = [l for l in store.lines if l["invoice_date"] < before]
        self.lines_by_vendor = defaultdict(list)
        for i, l in enumerate(self.lines):
            self.lines_by_vendor[l["vendor_id"]].append(i)


# ---------- champion ----------
def champion_predict(rec, l):
    r = rec.recommend_line(l["vendor_id"], l["description"], l["qty"], l["unit_price"], l["amount_usd"])
    if not r:
        return None
    total = sum(max(a["score"], 0) for a in r["alternatives"]) or 1
    return {"top": r["scored_account"], "conf": r["raw_confidence"], "cc": r["cost_centre"],
            "ranked": [a["account"] for a in r["alternatives"]],
            "share": {a["account"]: max(a["score"], 0) / total for a in r["alternatives"]}}


# ---------- challenger ----------
def features(rows, word, char, vocab, stats, fit=False):
    texts = [r["description"] for r in rows]
    Xw = word.fit_transform(texts) if fit else word.transform(texts)
    Xc = char.fit_transform(texts) if fit else char.transform(texts)
    cats = []
    for r in rows:
        cats.append([vocab["vendor"].get(r["vendor_id"]), vocab["category"].get(r["category"]),
                     vocab["entity"].get(r["entity"])])
    n_cat = len(vocab["vendor"]) + len(vocab["category"]) + len(vocab["entity"])
    offs = [0, len(vocab["vendor"]), len(vocab["vendor"]) + len(vocab["category"])]
    rows_i, cols_i = [], []
    for i, c in enumerate(cats):
        for o, j in zip(offs, c):
            if j is not None:
                rows_i.append(i)
                cols_i.append(o + j)
    Xcat = sparse.csr_matrix((np.ones(len(rows_i)), (rows_i, cols_i)), shape=(len(rows), n_cat))
    num = np.array([[math.log1p(max(r["amount_usd"], 0)), math.log1p(max(r["unit_price"], 0))] for r in rows])
    if fit:
        stats["mean"], stats["std"] = num.mean(axis=0).tolist(), (num.std(axis=0) + 1e-9).tolist()
    num = (num - np.array(stats["mean"])) / np.array(stats["std"])
    return sparse.hstack([Xw, Xc, Xcat, sparse.csr_matrix(num)]).tocsr()


def ece(conf, correct, bins=10):
    conf, correct = np.asarray(conf), np.asarray(correct, dtype=float)
    total, out, curve = len(conf), 0.0, []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        m = (conf >= lo) & ((conf < hi) if b < bins - 1 else (conf <= hi))
        if m.sum():
            gap = abs(conf[m].mean() - correct[m].mean())
            out += gap * m.sum() / total
            curve.append({"bin": f"{lo:.1f}–{hi:.1f}", "confidence": round(float(conf[m].mean()), 3),
                          "accuracy": round(float(correct[m].mean()), 3), "n": int(m.sum())})
    return round(out, 4), curve


def band_threshold(conf, correct, precision):
    """Lowest confidence at which everything at or above it is right at least `precision` of the time."""
    order = np.argsort(-np.asarray(conf))
    c, ok = np.asarray(conf)[order], np.asarray(correct, dtype=float)[order]
    cum = np.cumsum(ok) / np.arange(1, len(ok) + 1)
    best = None
    for i in range(len(c)):
        if cum[i] >= precision and (i + 1 == len(c) or c[i + 1] < c[i]):
            best = float(c[i])
    return round(best, 3) if best is not None else 1.0


def summarise(name, rows, top, top3, conf_raw, conf_cal, cc_pred, bands):
    y = [natural(r) for r in rows]
    ok = [t == yy for t, yy in zip(top, y)]
    fast, review = bands
    banded = {"fast_track": [], "review": [], "manual": []}
    for c, o in zip(conf_cal, ok):
        banded["fast_track" if c >= fast else "review" if c >= review else "manual"].append(o)
    by_cat = defaultdict(list)
    for r, o in zip(rows, ok):
        by_cat[r["category"]].append(o)
    confusion = Counter((yy, t) for t, yy in zip(top, y) if t != yy).most_common(10)
    miscoded = [i for i, r in enumerate(rows) if r["posted_gl"] != r["gl"]]
    raw_ece, _ = ece(conf_raw, ok)
    cal_ece, curve = ece(conf_cal, ok)
    return {
        "model": name, "test_lines": len(rows),
        "first_time_right": round(float(np.mean(ok)), 4),
        "top3": round(float(np.mean([yy in t3 for yy, t3 in zip(y, top3)])), 4),
        "macro_f1": round(float(f1_score(y, top, average="macro", zero_division=0)), 4),
        "cost_centre_accuracy": round(float(np.mean([p == r["cc"] for p, r in zip(cc_pred, rows)])), 4)
        if cc_pred else None,
        "ece_raw": raw_ece, "ece_calibrated": cal_ece, "reliability": curve,
        "bands": {b: {"share": round(len(v) / len(ok), 4), "accuracy": round(float(np.mean(v)), 4) if v else None,
                      "lines": len(v)} for b, v in banded.items()},
        "by_category": sorted([{"category": k, "lines": len(v), "accuracy": round(float(np.mean(v)), 4)}
                               for k, v in by_cat.items()], key=lambda x: -x["lines"]),
        "confusions": [{"actual": a, "predicted": p, "lines": n} for (a, p), n in confusion],
        "reclasses_avoided": {"historic_miscodes_in_test": len(miscoded),
                              "model_predicts_corrected_account": sum(1 for i in miscoded if ok[i])},
    }


def main():
    t0 = time.time()
    s = get_store()
    lines = [l for l in s.lines if l["amount_usd"] > 0]
    for l in lines:
        l["category"] = l.get("category") or s.vendors[l["vendor_id"]]["category"]
    train = [l for l in lines if l["invoice_date"] < TRAIN_END]
    calib = [l for l in lines if TRAIN_END <= l["invoice_date"] < CALIB_END]
    test = [l for l in lines if l["invoice_date"] >= CALIB_END]
    print(f"lines: train {len(train):,} · calibrate {len(calib):,} · test {len(test):,}")

    # champion, history cut at the train boundary
    rec = Recommender(HistoryView(s, TRAIN_END))
    champ = {"calib": [champion_predict(rec, l) for l in calib], "test": [champion_predict(rec, l) for l in test]}
    print(f"champion scored in {time.time() - t0:.0f}s")

    # challenger
    word = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2, lowercase=True)
    char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, lowercase=True)
    vocab = {"vendor": {v: i for i, v in enumerate(sorted({l["vendor_id"] for l in train}))},
             "category": {v: i for i, v in enumerate(sorted({l["category"] for l in train}))},
             "entity": {v: i for i, v in enumerate(sorted({l["entity"] for l in train}))}}
    stats = {}
    Xtr = features(train, word, char, vocab, stats, fit=True)
    ytr = [natural(l) for l in train]
    clf = LogisticRegression(C=8.0, max_iter=400)
    clf.fit(Xtr, ytr)
    cc_clf = LogisticRegression(C=4.0, max_iter=300).fit(Xtr, [l["cc"] for l in train])
    classes = list(clf.classes_)
    P = {k: clf.predict_proba(features(rows, word, char, vocab, stats)) for k, rows in (("calib", calib), ("test", test))}
    cc_test = cc_clf.predict(features(test, word, char, vocab, stats)).tolist()
    print(f"challenger trained on {Xtr.shape[1]:,} features in {time.time() - t0:.0f}s")

    def chall(k):
        return [{"top": classes[int(np.argmax(p))], "conf": float(np.max(p)),
                 "ranked": [classes[j] for j in np.argsort(-p)[:3]], "proba": p} for p in P[k]]

    def blend(k):
        out = []
        for c, h in zip(champ[k], chall(k)):
            score = {a: 0.5 * h["proba"][classes.index(a)] if a in classes else 0.0 for a in classes}
            if c:
                for a, sh in c["share"].items():
                    score[a] = score.get(a, 0.0) + 0.5 * sh
            ranked = sorted(score, key=lambda a: -score[a])
            out.append({"top": ranked[0], "conf": float(score[ranked[0]]), "ranked": ranked[:3]})
        return out

    preds = {"champion": champ, "challenger": {k: chall(k) for k in ("calib", "test")},
             "blend": {k: blend(k) for k in ("calib", "test")}}
    calibration, results = {}, {}
    for name, pr in preds.items():
        cal_rows = [(p["conf"] if p else 0.0, (p["top"] if p else None) == natural(l)) for p, l in zip(pr["calib"], calib)]
        iso = IsotonicRegression(y_min=0.0, y_max=0.99, out_of_bounds="clip")
        iso.fit([c for c, _ in cal_rows], [float(o) for _, o in cal_rows])
        calibration[name] = {"x": [round(float(x), 6) for x in iso.X_thresholds_],
                             "y": [round(float(y), 6) for y in iso.y_thresholds_]}
        raw = [p["conf"] if p else 0.0 for p in pr["test"]]
        cal = iso.predict(raw).tolist()
        top = [p["top"] if p else None for p in pr["test"]]
        ok = [t == natural(l) for t, l in zip(top, test)]
        bands = (band_threshold(cal, ok, 0.98), band_threshold(cal, ok, 0.80))
        cc = [p["cc"] if p else None for p in pr["test"]] if name == "champion" else (cc_test if name == "challenger" else None)
        results[name] = summarise(name, test, top, [p["ranked"] if p else [] for p in pr["test"]], raw, cal, cc, bands)
        results[name]["proposed_bands"] = {"fast_track": bands[0], "review": bands[1]}
        print(f"{name:10} first-time-right {results[name]['first_time_right']:.1%} · top-3 {results[name]['top3']:.1%} "
              f"· ECE {results[name]['ece_raw']:.3f} → {results[name]['ece_calibrated']:.3f} · bands {bands}")

    production = max(results, key=lambda m: (round(results[m]["first_time_right"], 3), -results[m]["ece_calibrated"]))

    # learning loop: the champion's history refreshed monthly with confirmed coding vs frozen at the train cut
    months = sorted({l["invoice_date"][:7] for l in test})
    loop = []
    for m in months:
        rows = [l for l in test if l["invoice_date"][:7] == m]
        fresh = Recommender(HistoryView(s, f"{m}-01"))
        frozen_ok = [((champion_predict(rec, l) or {}).get("top")) == natural(l) for l in rows]
        fresh_ok = [((champion_predict(fresh, l) or {}).get("top")) == natural(l) for l in rows]
        loop.append({"month": m, "lines": len(rows), "frozen": round(float(np.mean(frozen_ok)), 4),
                     "with_corrections": round(float(np.mean(fresh_ok)), 4)})

    # export the challenger for numpy inference and prove it matches scikit-learn
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        OUT / "challenger_weights.npz", coef=clf.coef_.astype(np.float32), intercept=clf.intercept_.astype(np.float32),
        classes=np.array(classes), word_idf=word.idf_.astype(np.float32), char_idf=char.idf_.astype(np.float32),
        word_vocab=np.array(json.dumps({k: int(v) for k, v in word.vocabulary_.items()})),
        char_vocab=np.array(json.dumps({k: int(v) for k, v in char.vocabulary_.items()})),
        cat_vocab=np.array(json.dumps(vocab)), num_stats=np.array(json.dumps(stats)))
    runtime = ChallengerModel(OUT / "challenger_weights.npz")
    sample = test[:400]
    diff = max(float(np.max(np.abs(runtime.proba(l["description"], l["vendor_id"], l["category"], l["entity"],
                                                 l["amount_usd"], l["unit_price"]) - p)))
               for l, p in zip(sample, P["test"][:400]))
    assert diff < 1e-4, f"numpy inference drifted from scikit-learn by {diff}"
    print(f"numpy inference matches scikit-learn (max |Δp| {diff:.2e})")

    # anomaly sweep, scored against the generator's ground truth (planted and historic miscodes)
    from backend.engine.anomaly import AnomalyLayer
    truth = json.loads((ROOT / "data" / "seed" / "_truth.json").read_text())
    layer = AnomalyLayer(s, Recommender(s))
    ap = layer.scan_ap_ledger()
    open_miscodes = {m["invoice_id"] for m in truth["miscoded_lines"] if not m["reclassified"]}
    window = {i["invoice_id"] for i in s.history if i["invoice_date"] >= "2026-04-01"}
    target = open_miscodes & window
    hits = sum(1 for f in ap["flags"] if f["invoice_id"] in target)
    jr = layer.scan_journals()
    planted = set(truth["journal_planted"].values())
    jr_hits = {f["je_id"] for f in jr["flags"]} & planted
    cash = layer.scan_cash()
    anomaly = {"ap_ledger": {"flags": len(ap["flags"]), "true_miscodes_flagged": hits,
                             "precision": round(hits / max(1, len(ap["flags"])), 3),
                             "recall": round(hits / max(1, len(target)), 3), "open_miscodes_in_window": len(target)},
               "journals": {"flags": len(jr["flags"]), "planted": len(planted), "planted_found": len(jr_hits),
                            "lines_scanned": jr["lines_scanned"]},
               "cash": {"flags": len(cash["flags"]), "receipts_scanned": cash["lines_scanned"],
                        "planted": len(truth["cash_planted"])}}
    print(f"anomaly sweep: AP precision {anomaly['ap_ledger']['precision']:.0%} recall "
          f"{anomaly['ap_ledger']['recall']:.0%} · journals {len(jr_hits)}/{len(planted)} planted found")

    split = {"train": [train[0]["invoice_date"][:7] if train else None, "2026-04"], "calibrate": ["2026-05", "2026-06"],
             "test": ["2026-07", "2026-09"]}
    metrics = {"version": VERSION, "trained_at": date.today().isoformat(), "production_model": production,
               "split": split, "lines": {"train": len(train), "calibrate": len(calib), "test": len(test)},
               "models": results, "learning_loop": loop, "anomaly": anomaly,
               "features": {"challenger": int(Xtr.shape[1]), "word_ngrams": len(word.vocabulary_),
                            "char_ngrams": len(char.vocabulary_), "suppliers": len(vocab["vendor"])},
               "note": "Measured on synthetic data. Not a product accuracy claim."}
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=1))
    (OUT / "calibration.json").write_text(json.dumps(calibration))
    prod = results[production]
    (OUT / "model_card.json").write_text(json.dumps({
        "name": "Non-PO GL coding recommender", "version": VERSION, "production_model": production,
        "intended_use": "Recommend GL account and cost centre for non-PO invoice lines, with evidence, for a person "
                        "to accept or override. Also used by the anomaly sweep to spot miscoded lines.",
        "out_of_scope": ["Deciding capitalisation (Fixed Asset Accounting decides)", "Approving or paying invoices",
                         "PO-backed invoices (matched, not coded)", "T&E (Concur) and intercompany"],
        "training_data": f"{len(train):,} coded invoice lines, Apr 2025 – Apr 2026, {len(vocab['vendor'])} suppliers, "
                         f"final (post-reclass) coding as the label.",
        "evaluation": f"Time-based hold-out Jul – Sep 2026 ({len(test):,} lines): first-time-right "
                      f"{prod['first_time_right']:.1%}, top-3 {prod['top3']:.1%}, calibration error "
                      f"{prod['ece_calibrated']:.3f} after isotonic calibration on May – Jun 2026.",
        "limitations": ["New suppliers with no history fall back to category-level evidence and lower confidence",
                        "Free-text descriptions that do not say what was bought need a person",
                        "Synthetic data: real accuracy is established by back-testing on the client's history"],
        "monitoring": {"override_rate_alert": 0.08, "psi_alert": 0.2,
                       "retrain_trigger": "Override rate above 8% for two consecutive weeks, or confidence PSI above "
                                          "0.2 week on week; otherwise quarterly"},
        "owner": "GBSC Finance Automation CoE (model owner) · Controllership (accounting policy owner)",
        "approval": "Pending model risk review before production use",
        "data_use": "Trained only on the client's own coded history inside its tenant. No client data is used to "
                    "train third-party models."}, indent=1))

    manifest = []
    for name, rows, dated, used in [
            ("invoice_history", s.history, "invoice_date", "Coding & treatment, price, risk, duplicate check"),
            ("purchase_orders", s.pos, "created_date", "Supplier & validity (open-PO match)"),
            ("vendors", list(s.vendors.values()), "created_date", "Supplier & validity, risk"),
            ("people", list(s.people.values()), None, "Approval & receipt"),
            ("journals_sep26", s.journals, "accounting_date", "Anomaly sweep, cut-off"),
            ("cash_receipts_20261014", s.receipts, None, "Anomaly sweep (cash)"),
            ("ar_open_items", s.ar_items, None, "Anomaly sweep (cash)"),
            ("intake_queue", s.intake, "received_at", "Intake")]:
        dates = sorted(r[dated][:10] for r in rows if dated and r.get(dated)) if dated else []
        manifest.append({"dataset": name, "rows": len(rows), "from": dates[0] if dates else None,
                         "to": dates[-1] if dates else None, "used_by": used})
    manifest.insert(1, {"dataset": "coded invoice lines", "rows": len(s.lines), "from": lines[0]["invoice_date"],
                        "to": max(l["invoice_date"] for l in lines), "used_by": "Model training and evidence"})
    (OUT / "dataset_manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"production model: {production} · wrote {OUT} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
