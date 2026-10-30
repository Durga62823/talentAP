"""Inference for the locally trained PII column classifier.

The artifact (artifacts/pii_model.joblib) is produced by `python -m app.ml.train`. It runs fully
in-process: no network, no API key. If the file is missing or was trained with an incompatible
scikit-learn version, the model reports itself unavailable and the scan continues on rules."""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ..scanner import SENSITIVITY

log = logging.getLogger("sentinelmask.ml")

ARTIFACT_DIR = Path(__file__).parent / "artifacts"
MODEL_FILE = "pii_model.joblib"
CARD_FILE = "model_card.json"

FEATURE_LABELS = {
    "credit_card_luhn_match_ratio": "card numbers passing Luhn", "pan_match_ratio": "PAN format", "aadhaar_format_match_ratio": "Aadhaar format",
    "aadhaar_checksum_valid_match_ratio": "Aadhaar Verhoeff checksum", "ssn_format_match_ratio": "SSN format", "passport_in_match_ratio": "passport format",
    "email_match_ratio": "email format", "phone_match_ratio": "phone format", "upi_handle_match_ratio": "UPI handle format",
    "iban_checksum_valid_match_ratio": "IBAN checksum", "ifsc_match_ratio": "IFSC format", "date_match_ratio": "date values",
    "person_name_shape_match_ratio": "person-name shape", "address_shape_match_ratio": "address shape", "decimal_amount_match_ratio": "decimal amounts",
    "birth_year_ratio": "dates with adult birth years", "recent_year_ratio": "recent dates", "score_range_ratio": "integers in 300-900",
    "free_text_with_embedded_entities_ratio": "free text with embedded identifiers", "unique_ratio": "uniqueness",
    "average_length": "average length", "maximum_length": "maximum length", "numeric_ratio": "all-digit values",
    "alphabetic_ratio": "alphabetic values", "contains_space_ratio": "values with spaces", "low_cardinality": "few distinct values",
    "numeric_mean_log": "magnitude of numbers", "uppercase_char_ratio": "uppercase characters", "digit_char_ratio": "digit characters",
    "null_or_empty_ratio": "share of empty values", "distinct_count_log": "number of distinct values (log10)",
    "minimum_length": "minimum length", "integer_value_ratio": "whole numbers", "numeric_value_ratio": "numeric values",
    "percent_range_ratio": "values that look like percentages", "nullable": "nullable column", "primary_key": "primary key",
}


@dataclass
class MlVerdict:
    category: str
    sensitivity: str
    confidence: float
    top: list[dict[str, Any]] = field(default_factory=list)       # top-3 classes with probabilities
    reasons: list[dict[str, Any]] = field(default_factory=list)   # top evidence for the predicted class


class PiiModel:
    def __init__(self, bundle: dict[str, Any]):
        self.version: str = bundle["version"]
        self.classes: list[str] = [str(c) for c in bundle["classes"]]
        self.numeric_features: list[str] = list(bundle["numeric_features"])
        self.medians = np.asarray(bundle["medians"], dtype=float)
        self.name_model = bundle["name_model"]
        self.model = bundle["model"]
        self.class_prior = np.asarray(bundle["class_prior"], dtype=float)

    def _num_matrix(self, rows: list[dict[str, float]]) -> np.ndarray:
        return np.array([[r.get(f, m) for f, m in zip(self.numeric_features, self.medians)] for r in rows], dtype=float)

    def _proba(self, num: np.ndarray, name_p: np.ndarray) -> np.ndarray:
        return self.model.predict_proba(np.hstack([num, name_p]))

    def predict(self, rows: list[tuple[dict[str, float], str]], explain: bool = True) -> list[MlVerdict]:
        if not rows:
            return []
        num = self._num_matrix([r[0] for r in rows])
        name_p = self.name_model.predict_proba([r[1] for r in rows])
        probs = self._proba(num, name_p)
        ks = probs.argmax(1)
        reasons = self._explain_all(num, name_p, ks, probs, [r[1] for r in rows]) if explain else [[] for _ in rows]
        out: list[MlVerdict] = []
        for i, p in enumerate(probs):
            k = int(ks[i])
            cat = self.classes[k]
            top = [{"category": self.classes[j], "probability": round(float(p[j]), 3)} for j in np.argsort(-p)[:3]]
            out.append(MlVerdict(cat, SENSITIVITY[cat], round(float(p[k]), 3), top, reasons[i]))
        return out

    def _explain_all(self, num: np.ndarray, name_p: np.ndarray, ks: np.ndarray, probs: np.ndarray, texts: list[str]) -> list[list[dict[str, Any]]]:
        """Occlusion: reset one feature (or the whole name signal) to its typical training value and
        measure how much the predicted class's probability drops. Positive = supports the prediction.
        All perturbations of all columns go through the model in a single batch (one call has a
        large fixed cost: 5 calibrated sub-models)."""
        cand_num, cand_name, owners = [], [], []
        for i in range(len(num)):
            changed = [j for j in range(num.shape[1]) if num[i, j] != self.medians[j]]
            for j in changed:
                v = num[i].copy()
                v[j] = self.medians[j]
                cand_num.append(v)
                cand_name.append(name_p[i])
                owners.append((i, j))
            cand_num.append(num[i])
            cand_name.append(self.class_prior)  # name signal removed
            owners.append((i, -1))
        p_all = self._proba(np.array(cand_num), np.array(cand_name))
        effects: list[list[tuple[str, float, float | None]]] = [[] for _ in range(len(num))]
        for (i, j), p in zip(owners, p_all):
            delta = float(probs[i, ks[i]] - p[ks[i]])
            if j < 0:
                effects[i].append(("__column_name__", delta, None))
            else:
                effects[i].append((self.numeric_features[j], delta, float(num[i, j])))
        return [self._reasons(e, texts[i]) for i, e in enumerate(effects)]

    def _reasons(self, effects: list[tuple[str, float, float | None]], text: str) -> list[dict[str, Any]]:
        effects.sort(key=lambda e: -e[1])
        reasons = []
        for feat, delta, value in effects[:3]:
            if delta <= 0.01:
                break
            if feat == "__column_name__":
                label = f"column name \"{text.split(' ', 1)[-1]}\""
            else:
                label = f"{FEATURE_LABELS.get(feat, feat.replace('_', ' '))} = {round(value, 2)}"
            reasons.append({"feature": feat, "evidence": label, "impact": round(delta, 3)})
        return reasons


_lock = threading.Lock()
_model: PiiModel | None = None
_loaded = False
_error = ""


def model_path() -> Path:
    return Path(os.environ.get("SENTINEL_ML_MODEL") or ARTIFACT_DIR / MODEL_FILE)


def get_model() -> PiiModel | None:
    """Load once; None (with a logged reason) if the artifact is missing or incompatible."""
    global _model, _loaded, _error
    with _lock:
        if _loaded:
            return _model
        _loaded = True
        path = model_path()
        if not path.exists():
            _error = "model artifact not found; run `python -m app.ml.train`"
            log.warning("ML model unavailable: %s", _error)
            return None
        try:
            import joblib
            import sklearn

            bundle = joblib.load(path)
            if bundle.get("sklearn_version") != sklearn.__version__:
                _error = f"trained with scikit-learn {bundle.get('sklearn_version')}, running {sklearn.__version__}; retrain"
                log.warning("ML model unavailable: %s", _error)
                return None
            _model = PiiModel(bundle)
        except Exception as exc:  # noqa: BLE001
            _error = f"could not load model ({type(exc).__name__})"
            log.warning("ML model unavailable: %s", _error)
            _model = None
        return _model


def reset_model() -> None:
    """Test hook / after retraining."""
    global _model, _loaded, _error
    with _lock:
        _model, _loaded, _error = None, False, ""


def model_error() -> str:
    get_model()
    return _error


def model_card() -> dict[str, Any] | None:
    path = model_path().with_name(CARD_FILE)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def min_confidence() -> float:
    return float(os.environ.get("SENTINEL_ML_MIN_CONFIDENCE", 0.8))
