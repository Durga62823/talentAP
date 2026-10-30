"""Locally trained PII column classifier (no external service, no data leaves the server).

  featurize.py  numeric + text features for one column (aggregates only)
  synth.py      synthetic training corpus (Faker, en_IN); training-time only
  train.py      `python -m app.ml.train` -> artifacts/pii_model.joblib + model_card.json
  model.py      lazy loading, prediction, per-prediction explanations
"""
