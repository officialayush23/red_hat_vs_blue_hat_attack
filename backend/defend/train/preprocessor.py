"""
Single, saved, versioned preprocessor for the tabular models (XGBoost,
LightGBM -- the Autoencoder already carries its own self-contained
prep_spec inside autoencoder.pt, see train_autoencoder.py's
fit_preprocessor()/transform(), so it isn't duplicated here).

Fit once from the same two source files (features.parquet,
attacks_train.parquet) that already, implicitly, produced the frozen
xgboost.json/lightgbm.txt models via defend/train/dataset.py's
load_training_pool(). Fitting this now doesn't change anything about
those already-trained, already-frozen models -- it captures and saves
what was already deterministically true about their training data
(same files, same values), instead of leaving every downstream consumer
to re-derive it independently.

Built 2026-08-30 directly because of two real bugs hit while building
evaluation/run_adversarial_eval.py's first version, which re-derived this
same vocabulary ad hoc, inline, every run: an all-NaN categorical column
(card_type/card_network -- the synthetic attack generator never models
these IEEE-CIS-only fields) crashed XGBoost with an empty-categories
error, and XGBoost hard-errors on a genuinely novel category value
(exactly what Section 8's held-out combinations are designed to contain).
A single saved source of truth removes that whole bug class going
forward, and is a real prerequisite for Task #36 (the live API needs some
deterministic raw-request -> model-input path for the tabular models;
this is it).

This is explicitly NOT how the system adapts to new attack patterns --
that's Section 8's adversarial mutation loop (weakness_log, Task #35's
LLM strategist), a completely different mechanism operating on attack
combinations, not on data schema. This pipeline's job is narrower and
more mundane: make scoring consistent and crash-free, not smarter or
more accurate. See docs/TECHNICAL_SPEC.md Section 5 for where this fits.

Usage (fit + save):
    python backend/defend/train/fit_preprocessor.py

Usage (consume, e.g. from an eval script or the future live API):
    from defend.train.preprocessor import TabularPreprocessor
    prep = TabularPreprocessor.load(MODELS_DIR / "tabular_preprocessor.joblib")
    model_ready_df = prep.transform_tree(raw_df)
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from defend.train.dataset import ALL_FEATURE_COLUMNS, BOOLEAN_FEATURES, CATEGORICAL_FEATURES, NUMERIC_FEATURES


class TabularPreprocessor:
    """cat_vocab: {column_name: sorted list of every value seen in the
    Stage-5 training data for that column}. fitted_from: provenance
    (source files, row counts, fit timestamp) so a re-run of this script
    is auditable, not a silent black box."""

    def __init__(self, cat_vocab: dict, fitted_from: dict):
        self.cat_vocab = cat_vocab
        self.fitted_from = fitted_from

    @classmethod
    def fit(cls, real_df: pd.DataFrame, generated_df: pd.DataFrame, fitted_from: dict) -> "TabularPreprocessor":
        cat_vocab = {}
        for c in CATEGORICAL_FEATURES:
            vals = set()
            if c in real_df.columns:
                vals |= set(real_df[c].dropna().unique().tolist())
            if c in generated_df.columns:
                vals |= set(generated_df[c].dropna().unique().tolist())
            cat_vocab[c] = sorted(vals)
        return cls(cat_vocab=cat_vocab, fitted_from=fitted_from)

    def transform_tree(self, df: pd.DataFrame) -> pd.DataFrame:
        """Model-ready input for XGBoost/LightGBM: float32 numeric/boolean
        with NaN preserved (both models handle missing values natively --
        no imputation), categorical columns masked to the fitted
        vocabulary and cast to pandas 'category' dtype. Masking (rather
        than a plain astype("category")) is what prevents both bugs in
        this module's docstring: it guarantees non-empty categories even
        when this particular df has zero non-null values for a column,
        and it turns a genuinely novel category value into a missing
        value instead of a value XGBoost has never indexed and will
        reject outright."""
        out = pd.DataFrame(index=df.index)
        for c in NUMERIC_FEATURES + BOOLEAN_FEATURES:
            out[c] = pd.to_numeric(df[c], errors="coerce").astype("float32") if c in df.columns else np.float32("nan")
        for c in CATEGORICAL_FEATURES:
            raw = df[c] if c in df.columns else pd.Series([None] * len(df), index=df.index)
            vocab = self.cat_vocab.get(c, [])
            masked = raw.where(raw.isin(vocab)).astype(object) if vocab else pd.Series([None] * len(df), index=df.index)
            out[c] = pd.Categorical(masked, categories=vocab)
        return out[ALL_FEATURE_COLUMNS]

    def save(self, path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"cat_vocab": self.cat_vocab, "fitted_from": self.fitted_from}, path)

    @classmethod
    def load(cls, path) -> "TabularPreprocessor":
        data = joblib.load(Path(path))
        return cls(cat_vocab=data["cat_vocab"], fitted_from=data["fitted_from"])
