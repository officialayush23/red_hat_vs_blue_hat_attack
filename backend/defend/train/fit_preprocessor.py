"""
Fits and saves TabularPreprocessor (defend/train/preprocessor.py) from the
same two source files dataset.load_training_pool() combines --
features.parquet (real PaySim/IEEE-CIS) and attacks_train.parquet
(train-portion generated attacks) -- via a cheap column-projected parquet
read (only the ~6 categorical columns, confirmed well under a second, not
the full ~6.95M-row combined pool dataset.py builds). Deterministic given
the same source files, so this reproduces exactly the categorical
vocabulary already implicit in the frozen xgboost.json/lightgbm.txt
models -- running this does not retrain or change them.

Usage:
    python backend/defend/train/fit_preprocessor.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

import pandas as pd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from defend.train.dataset import CATEGORICAL_FEATURES  # noqa: E402
from defend.train.preprocessor import TabularPreprocessor  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
FEATURES_PATH = REPO_ROOT / "data" / "processed" / "features.parquet"
ATTACKS_TRAIN_PATH = REPO_ROOT / "data" / "processed" / "attacks_train.parquet"
OUT_PATH = BACKEND_DIR / "defend" / "models" / "tabular_preprocessor.joblib"


def main() -> None:
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(f"{FEATURES_PATH} not found. Run defend/features/build_features.py first.")
    if not ATTACKS_TRAIN_PATH.exists():
        raise FileNotFoundError(f"{ATTACKS_TRAIN_PATH} not found. Run generate/inject_attacks.py first.")

    real_cols = [c for c in CATEGORICAL_FEATURES if c in pq.ParquetFile(FEATURES_PATH).schema.names]
    gen_cols = [c for c in CATEGORICAL_FEATURES if c in pq.ParquetFile(ATTACKS_TRAIN_PATH).schema.names]
    print(f"Reading categorical columns only from {FEATURES_PATH.name} ({real_cols})...")
    real_df = pd.read_parquet(FEATURES_PATH, columns=real_cols)
    print(f"  {len(real_df):,} real rows")
    print(f"Reading categorical columns only from {ATTACKS_TRAIN_PATH.name} ({gen_cols})...")
    gen_df = pd.read_parquet(ATTACKS_TRAIN_PATH, columns=gen_cols)
    print(f"  {len(gen_df):,} generated rows")

    fitted_from = {
        "real_source": str(FEATURES_PATH),
        "real_rows": len(real_df),
        "generated_source": str(ATTACKS_TRAIN_PATH),
        "generated_rows": len(gen_df),
        "fitted_at": datetime.now(timezone.utc).isoformat(),
    }
    prep = TabularPreprocessor.fit(real_df, gen_df, fitted_from)

    print("\nFitted categorical vocabulary:")
    for c, vocab in prep.cat_vocab.items():
        print(f"  {c}: {len(vocab)} values -> {vocab}")

    prep.save(OUT_PATH)
    print(f"\nSaved to {OUT_PATH}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nFIT FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
