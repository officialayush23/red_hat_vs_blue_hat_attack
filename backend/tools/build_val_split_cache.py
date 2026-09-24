"""Write backend/seed_data/processed/val_split.parquet -- the validation half
of train_val_split(load_training_pool()) -- so the tabular evaluations can run
on a machine without the 172 MB features.parquet (see dataset.load_val_split).

Run once on the machine that has data/processed/features.parquet, in the main
venv, then commit the file:

    red\\Scripts\\python backend\\tools\\build_val_split_cache.py
    git add backend/seed_data/processed/val_split.parquet

Re-run whenever features.parquet or attacks_train.parquet is rebuilt.
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from defend.train.dataset import (  # noqa: E402
    ALL_FEATURE_COLUMNS, CATEGORICAL_FEATURES, LABEL_COLUMN, load_training_pool, train_val_split,
)

OUT = BACKEND_DIR / "seed_data" / "processed" / "val_split.parquet"


def main() -> int:
    pool = load_training_pool()
    _, X_val, _, y_val = train_val_split(pool)
    del pool
    df = X_val.copy()
    # Category SETS, in order, exactly as the pool built them. LightGBM /
    # XGBoost read pandas categoricals by code, so the reloaded columns must
    # carry the identical category list, not one re-derived from the subset.
    cats = {col: [str(c) for c in X_val[col].cat.categories] for col in CATEGORICAL_FEATURES}
    df[LABEL_COLUMN] = y_val.to_numpy()
    df = df.reset_index(drop=True)[ALL_FEATURE_COLUMNS + [LABEL_COLUMN]]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False, compression="zstd")
    import json
    OUT.with_suffix(".categories.json").write_text(json.dumps(cats, indent=1))
    print(f"Wrote {len(df):,} rows ({int(df[LABEL_COLUMN].sum()):,} fraud) to {OUT} "
          f"({OUT.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
