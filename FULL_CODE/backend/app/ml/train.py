"""Train, calibrate and evaluate the PII column classifier.

    python -m app.ml.train            # full training (a few minutes)
    python -m app.ml.train --quick    # smaller corpus, for a smoke test

Pipeline
  1. Synthetic corpus (synth.py), column names of the evaluation set excluded.
  2. Name model: TF-IDF character n-grams of "table column" -> logistic regression.
  3. Value model: gradient-boosted trees on the sanitized statistics + the name model's
     out-of-fold class probabilities (stacking), wrapped in isotonic calibration.
  4. Evaluation on a held-out synthetic split AND on the official Saffron Bank columns with
     hand-written labels (app/ml/eval/saffron_labels.csv), alongside the rule engine as a baseline.
Writes artifacts/pii_model.joblib and artifacts/model_card.json."""
from __future__ import annotations

import argparse
import csv
import json
import random
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ..scanner import CATEGORIES, SENSITIVE_LABELS, SENSITIVITY, classify_column
from . import featurize, synth
from .model import ARTIFACT_DIR, CARD_FILE, MODEL_FILE

VERSION = "pii-ml-v1"
SEED = 7
LABELS_CSV = Path(__file__).parent / "eval" / "saffron_labels.csv"
EXTRA_CAVEATS = [
    "Categories with only a few distinct column names can land entirely in training under the name-grouped split "
    "(e.g. ACCOUNT_NUMBER in v1), so their synthetic test score is n/a; check them on the Saffron table instead.",
    "All-digit identifiers are often confused with national IDs (account numbers at ~43% confidence on Saffron); "
    "below the threshold, so they are never applied automatically.",
    "Sparse free-text fields can be flagged from their shape (mostly empty, short notes) as well as their content: "
    "a learned prior that legacy note fields carry PII. The evidence panel shows which applied.",
]


def load_labels() -> list[dict[str, Any]]:
    with LABELS_CSV.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["acceptable"] = {r["label"], *[x for x in r["also_acceptable"].split("|") if x]}
    return rows


def featurize_columns(cols: list[dict[str, Any]]) -> tuple[list[dict[str, float]], list[str], list[str]]:
    numeric, texts, rule_cats = [], [], []
    for c in cols:
        rule = classify_column(c["column"], c["data_type"], c["values"], table=c["table"])
        num, text = featurize.build(c["table"], c["column"], c["data_type"], c["nullable"], c["primary_key"], c["values"], rule)
        numeric.append(num)
        texts.append(text)
        rule_cats.append(rule.category)
    return numeric, texts, rule_cats


def saffron_columns(sample_size: int = 100) -> list[dict[str, Any]]:
    from .. import saffron

    db = saffron.official_file("sql", "sqlite", saffron.SQLITE_TARGET)
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    r = random.Random(SEED)
    cols: list[dict[str, Any]] = []
    for lab in load_labels():
        t = lab["table"]
        info = {row[1]: row for row in con.execute(f'PRAGMA table_info("{t}")')}
        meta = info[lab["column"]]
        n = con.execute(f'SELECT MAX(rowid) FROM "{t}"').fetchone()[0] or 0
        rowids = sorted(r.sample(range(1, n + 1), min(sample_size, n)))
        q = f'SELECT "{lab["column"]}" FROM "{t}" WHERE rowid IN ({",".join("?" * len(rowids))})'
        values = [v[0] for v in con.execute(q, rowids)]
        cols.append({**lab, "data_type": meta[2], "nullable": not meta[3], "primary_key": bool(meta[5]), "values": values})
    con.close()
    return cols


def per_class(y_true: list[str], y_pred: list[str]) -> dict[str, Any]:
    from sklearn.metrics import accuracy_score, f1_score, precision_recall_fscore_support

    labels = sorted(set(y_true) | set(y_pred))
    p, rc, f, s = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "macro_f1": round(float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)), 4),
        "per_class": [{"category": lab, "precision": round(float(a), 3), "recall": round(float(b), 3), "f1": round(float(c), 3), "support": int(d)}
                      for lab, a, b, c, d in zip(labels, p, rc, f, s)],
    }


def binary(sensitive_true: list[bool], sensitive_pred: list[bool]) -> dict[str, float]:
    tp = sum(1 for t, p in zip(sensitive_true, sensitive_pred) if t and p)
    fp = sum(1 for t, p in zip(sensitive_true, sensitive_pred) if not t and p)
    fn = sum(1 for t, p in zip(sensitive_true, sensitive_pred) if t and not p)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
            "missed_sensitive": fn, "false_alarms": fp}


def calibration(conf: np.ndarray, correct: np.ndarray, bins: int = 10) -> dict[str, Any]:
    edges = np.linspace(0, 1, bins + 1)
    out, ece = [], 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.sum():
            acc, avg = float(correct[m].mean()), float(conf[m].mean())
            ece += m.sum() / len(conf) * abs(acc - avg)
            out.append({"bin": f"{lo:.1f}-{hi:.1f}", "count": int(m.sum()), "mean_confidence": round(avg, 3), "accuracy": round(acc, 3)})
    return {"expected_calibration_error": round(ece, 4), "bins": out}


def train(quick: bool = False) -> dict[str, Any]:
    import joblib
    import sklearn
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.inspection import permutation_importance
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import confusion_matrix
    from sklearn.model_selection import GroupKFold, GroupShuffleSplit, cross_val_predict
    from sklearn.pipeline import make_pipeline

    t0 = time.time()
    labels = load_labels()
    corpus = synth.generate(n_per_category=80 if quick else 260, n_none=500 if quick else 1800, seed=SEED,
                            exclude_names={lab["column"] for lab in labels})
    print(f"synthetic corpus: {len(corpus)} columns")
    numeric, texts, rule_cats = featurize_columns(corpus)
    y = np.array([c["label"] for c in corpus])
    feats = sorted({k for row in numeric for k in row})
    X_num = np.array([[row.get(f, 0.0) for f in feats] for row in numeric], dtype=float)
    texts_arr = np.array(texts)
    groups = np.array([c["base_name"] for c in corpus])
    # Split by column name: test columns use names never seen in training, so the synthetic
    # score measures generalisation to new schemas rather than memorised names.
    idx_tr, idx_te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED).split(X_num, y, groups))
    print(f"featurized in {time.time() - t0:.0f}s; train {len(idx_tr)} / test {len(idx_te)}")

    classes = sorted(set(y))
    name_model = make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True),
        LogisticRegression(C=4.0, max_iter=3000, class_weight="balanced"),
    )
    # Out-of-fold name probabilities so the value model never sees leaked name predictions.
    folds = list(GroupKFold(n_splits=5).split(idx_tr, y[idx_tr], groups[idx_tr]))
    oof = cross_val_predict(name_model, texts_arr[idx_tr], y[idx_tr], cv=folds, method="predict_proba")
    name_model.fit(texts_arr[idx_tr], y[idx_tr])
    assert list(name_model.classes_) == classes

    # Balanced class weights: NONE columns outnumber each sensitive category ~7:1, and an unsure
    # model should not default to "not sensitive" in a security tool.
    base = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.08, max_leaf_nodes=31, l2_regularization=1.0,
                                          class_weight="balanced", random_state=SEED)
    model = CalibratedClassifierCV(base, method="isotonic", cv=folds)
    model.fit(np.hstack([X_num[idx_tr], oof]), y[idx_tr])
    print(f"trained in {time.time() - t0:.0f}s")

    def predict(num: np.ndarray, txt: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        p = model.predict_proba(np.hstack([num, name_model.predict_proba(txt)]))
        return np.array(model.classes_)[p.argmax(1)], p.max(1)

    # ---- held-out synthetic split
    pred_te, conf_te = predict(X_num[idx_te], texts_arr[idx_te])
    synthetic = per_class(list(y[idx_te]), list(pred_te))
    synthetic["calibration"] = calibration(conf_te, pred_te == y[idx_te])
    synthetic["confusion_matrix"] = {"labels": classes, "matrix": confusion_matrix(y[idx_te], pred_te, labels=classes).tolist()}
    # Same unseen-name columns through the deterministic rule engine, for a like-for-like baseline.
    rules_te = [rule_cats[i] for i in idx_te]

    def sens(cats: Any) -> list[bool]:
        return [SENSITIVITY[c] in SENSITIVE_LABELS for c in cats]

    synthetic["ml_sensitive_detection"] = binary(sens(y[idx_te]), sens(pred_te))
    synthetic["rules"] = {"accuracy": round(float(np.mean(np.array(rules_te) == y[idx_te])), 4),
                          "sensitive_detection": binary(sens(y[idx_te]), sens(rules_te))}

    # ---- official Saffron columns (never used for training)
    sf = saffron_columns()
    sf_num, sf_txt, sf_rule = featurize_columns(sf)
    sf_X = np.array([[row.get(f, 0.0) for f in feats] for row in sf_num], dtype=float)
    sf_pred, sf_conf = predict(sf_X, np.array(sf_txt))
    rows, ml_ok, rule_ok = [], [], []
    for c, p, conf, rule in zip(sf, sf_pred, sf_conf, sf_rule):
        ml_ok.append(p in c["acceptable"])
        rule_ok.append(rule in c["acceptable"])
        rows.append({"table": c["table"], "column": c["column"], "label": c["label"], "acceptable": sorted(c["acceptable"]),
                     "ml": str(p), "ml_confidence": round(float(conf), 3), "rule": rule, "ml_correct": ml_ok[-1], "rule_correct": rule_ok[-1]})
    sens_true = [SENSITIVITY[c["label"]] in SENSITIVE_LABELS for c in sf]
    saffron_eval = {
        "columns": len(sf),
        "ml": {"accuracy": round(sum(ml_ok) / len(sf), 4), "sensitive_detection": binary(sens_true, [SENSITIVITY[p] in SENSITIVE_LABELS for p in sf_pred])},
        "rules": {"accuracy": round(sum(rule_ok) / len(sf), 4), "sensitive_detection": binary(sens_true, [SENSITIVITY[p] in SENSITIVE_LABELS for p in sf_rule])},
        "combined_upgrade_only": None,
        "columns_detail": rows,
    }
    # What the app actually does: rule result, raised (never lowered) by a confident ML verdict.
    rank = {"PUBLIC": 0, "INTERNAL": 1, "PII_MEDIUM": 3, "FINANCIAL_CONFIDENTIAL": 3, "PII_HIGH": 4}
    comb = [p if conf >= 0.8 and rank[SENSITIVITY[p]] > rank[SENSITIVITY[r]] else r for p, conf, r in zip(sf_pred, sf_conf, sf_rule)]
    saffron_eval["combined_upgrade_only"] = {
        "accuracy": round(sum(1 for c, p in zip(sf, comb) if p in c["acceptable"]) / len(sf), 4),
        "sensitive_detection": binary(sens_true, [SENSITIVITY[p] in SENSITIVE_LABELS for p in comb]),
    }

    # ---- global importance (permutation on the synthetic test split, grouped name features)
    sub = idx_te[: min(len(idx_te), 600)]
    X_sub = np.hstack([X_num[sub], name_model.predict_proba(texts_arr[sub])])
    imp = permutation_importance(model, X_sub, y[sub], n_repeats=3, random_state=SEED, scoring="accuracy")
    names = feats + [f"name:{c}" for c in classes]
    grouped: dict[str, float] = {}
    for n, v in zip(names, imp.importances_mean):
        key = "column name (character n-grams)" if n.startswith("name:") else n
        grouped[key] = grouped.get(key, 0.0) + float(v)
    importance = [{"feature": k, "importance": round(v, 4)} for k, v in sorted(grouped.items(), key=lambda kv: -kv[1])[:15]]

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    full_name_p = name_model.predict_proba(texts_arr[idx_tr])
    bundle = {
        "version": VERSION, "sklearn_version": sklearn.__version__, "classes": list(model.classes_),
        "numeric_features": feats, "medians": np.median(X_num[idx_tr], axis=0).tolist(),
        "class_prior": full_name_p.mean(axis=0).tolist(), "name_model": name_model, "model": model,
    }
    joblib.dump(bundle, ARTIFACT_DIR / MODEL_FILE, compress=3)
    card = {
        "version": VERSION,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sklearn_version": sklearn.__version__,
        "seed": SEED,
        "algorithm": "Stacked: TF-IDF char n-gram logistic regression on column names -> gradient-boosted trees on sanitized "
                     "value statistics + name probabilities, isotonic-calibrated (5-fold).",
        "training_data": {"source": "fully synthetic (Faker en_IN / en_US); no real or official data",
                          "columns": int(len(idx_tr)), "per_class": {c: int((y[idx_tr] == c).sum()) for c in classes},
                          "excluded_names": "exact column names of the evaluation set",
                          "test_split": "grouped by column name: synthetic test names never appear in training"},
        "categories": [c for c in CATEGORIES if c in classes],
        "synthetic_test": synthetic,
        "saffron_evaluation": saffron_eval,
        "feature_importance": importance,
        "decision_rule": "upgrade-only: applied only when more sensitive than the current classification, confidence >= threshold, "
                         "and no human review exists",
        "caveats": [
            "Saffron labels were hand-written by the team (app/ml/eval/saffron_labels.csv); ambiguous columns accept several categories.",
            "The synthetic test uses unseen column names but the same value generators as training, so it is still optimistic.",
            "The rule engine was hand-tuned on the Saffron dataset, so its Saffron score is an upper bound, not a fair comparison.",
            "Scans sample random rows, so predictions for sparse columns can vary between scans.",
            "Confidence is calibrated on synthetic data; calibration on real schemas is not guaranteed.",
            *EXTRA_CAVEATS,
        ],
        "training_seconds": round(time.time() - t0, 1),
    }
    (ARTIFACT_DIR / CARD_FILE).write_text(json.dumps(card, indent=2), encoding="utf-8")
    return card


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quick", action="store_true")
    card = train(quick=ap.parse_args().quick)
    s, e = card["synthetic_test"], card["saffron_evaluation"]
    print(f"\nsynthetic test: accuracy {s['accuracy']}  macro-F1 {s['macro_f1']}  ECE {s['calibration']['expected_calibration_error']}")
    print(f"  ML    sensitive {s['ml_sensitive_detection']}")
    print(f"  rules accuracy {s['rules']['accuracy']}  sensitive {s['rules']['sensitive_detection']}")
    for k in ("ml", "rules", "combined_upgrade_only"):
        d = e[k]
        print(f"saffron {k:22s} accuracy {d['accuracy']}  sensitive P/R/F1 {d['sensitive_detection']['precision']}/"
              f"{d['sensitive_detection']['recall']}/{d['sensitive_detection']['f1']}  missed {d['sensitive_detection']['missed_sensitive']}")
    print("ML wrong on:", [f"{r['table']}.{r['column']} -> {r['ml']} ({r['ml_confidence']})" for r in e["columns_detail"] if not r["ml_correct"]])
    print("rules wrong on:", [f"{r['table']}.{r['column']} -> {r['rule']}" for r in e["columns_detail"] if not r["rule_correct"]])


if __name__ == "__main__":
    main()
