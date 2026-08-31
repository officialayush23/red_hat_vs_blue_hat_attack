"""
Shared data loading for Stage 5 (Blue Team training). Combines the real
labeled data (defend/features/build_features.py's output) with the
train-portion synthetic attacks (generate/inject_attacks.py's output) into
one training pool, and produces a stratified train/validation split.

This is NOT the adversarial evaluation split from docs/TECHNICAL_SPEC.md
Section 8 -- that's attacks_held_out.parquet, generated from mutation
combinations these models never see here, reserved for
evaluation/run_adversarial_eval.py (Stage 7) after training. The split
here is an ordinary stratified train/validation split of the training
pool, for early stopping and sanity-checking metrics during training
itself.

Real fraud rows from PaySim/IEEE-CIS are included in training as-is --
they're genuine labeled ground truth, not part of our own attack taxonomy,
so there's no combinatorial-holdout basis to exclude any of them.

`is_generated` is tracked but deliberately NEVER included as a model
feature -- every row in the adversarial held-out set is also generated
(is_generated == True), so feeding that flag to the model would let it
"cheat" by learning is_generated -> fraud instead of learning the actual
fraud signal, making the held-out evaluation meaningless.
"""

import gc
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

PROCESSED_DIR = Path(__file__).resolve().parents[3] / "data" / "processed"
FEATURES_PATH = PROCESSED_DIR / "features.parquet"
ATTACKS_TRAIN_PATH = PROCESSED_DIR / "attacks_train.parquet"

NUMERIC_FEATURES = [
    "amount", "log_amount", "hour_of_day", "oldbalance_orig", "newbalance_orig",
    "balance_delta_orig", "orig_balance_wiped", "dest_is_merchant", "dest_balance_delta",
    "identity_match_score", "entity_txn_count_so_far", "time_since_prev_txn_same_entity",
    "is_first_txn_for_entity", "account_age_days", "device_history_count", "relationship_count",
    "hop_count",
    # Graph-topology features (round 4, docs/DATASETS.md) -- real for PaySim
    # (from nameOrig/nameDest) and generated mule_network rows (from that
    # case's own graph); NaN everywhere else (IEEE-CIS, and the three
    # generated families with no real multi-account graph structure). Same
    # "leave null when the row's source has no real graph" convention as
    # every other dataset-specific column above.
    "graph_src_out_degree", "graph_src_unique_out_counterparties", "graph_src_pass_through_ratio",
    "graph_dst_in_degree", "graph_dst_unique_in_counterparties", "graph_dst_pass_through_ratio",
    "graph_in_port",
]
CATEGORICAL_FEATURES = [
    "txn_type", "card_type", "card_network", "product_cd", "source_dataset", "behavior_pattern",
]
# Stored as float (1.0/0.0/NaN) rather than pandas' nullable "boolean" dtype --
# more reliably handled across xgboost/lightgbm/pytorch without extra casting.
BOOLEAN_FEATURES = [
    "device_is_new", "location_is_trusted", "beneficiary_changed",
    "merchant_unusual", "shared_device", "distributed_beneficiaries", "timing_irregular",
]
LABEL_COLUMN = "is_fraud"
ALL_FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES + BOOLEAN_FEATURES


def load_training_pool() -> pd.DataFrame:
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(f"{FEATURES_PATH} not found. Run defend/features/build_features.py first.")
    if not ATTACKS_TRAIN_PATH.exists():
        raise FileNotFoundError(f"{ATTACKS_TRAIN_PATH} not found. Run generate/inject_attacks.py first.")

    real = pd.read_parquet(FEATURES_PATH)
    generated = pd.read_parquet(ATTACKS_TRAIN_PATH)

    # Bug #4 (round 4, docs/DATASETS.md): the SAME bare-np.nan-defaults-to-
    # float64 anti-pattern already fixed in build_features.py, just missed
    # here. hop_count/account_age_days/device_history_count/relationship_count
    # (NUMERIC_FEATURES) and the 7 BOOLEAN_FEATURES columns don't exist at
    # all in real PaySim/IEEE-CIS data (they're generated-attack-only
    # signals) -- exactly 11 columns missing from `real`, plus
    # behavior_pattern (CATEGORICAL_FEATURES) missing too, confirmed via
    # pyarrow schema check (12 total). Seeding all 12 with a bare `np.nan`
    # made them float64 columns; pandas' BlockManager then consolidated the
    # 11 same-dtype numeric/boolean ones into a single (11, 6953160) --
    # rounds to the reported (12, 6953160) once the 12th (behavior_pattern,
    # object-backed but numpy reports it via the same float64 path when all-
    # NaN) is folded in -- float64 block during the `.copy()` call below,
    # BEFORE the per-frame downcast loop further down ever got a chance to
    # shrink it back to float32. Fix: seed NUMERIC_FEATURES/BOOLEAN_FEATURES
    # directly as float32 so no oversized block is ever materialized;
    # CATEGORICAL_FEATURES columns stay plain NaN (small, single column,
    # later cast to "category" after concat -- never part of a wide numeric
    # block).
    _numeric_or_boolean = set(NUMERIC_FEATURES) | set(BOOLEAN_FEATURES)
    for col in ALL_FEATURE_COLUMNS:
        fill = np.float32(np.nan) if col in _numeric_or_boolean else np.nan
        if col not in real.columns:
            real[col] = fill
        if col not in generated.columns:
            generated[col] = fill

    # Bug #5 (round 4, docs/DATASETS.md): even with every column already
    # float32 on both sides, `pd.concat([real, generated])` still crashed --
    # `Unable to allocate 743. MiB for an array with shape (28, 6953160) and
    # data type float32` -- because pandas' BlockManager had already
    # consolidated 28 of our NUMERIC_FEATURES/BOOLEAN_FEATURES columns (same
    # dtype, set column-by-column in a loop) into ONE wide block inside
    # `real`. concat has to build a brand-new same-shaped destination block
    # for that group in a SINGLE allocation while `real`'s own block (nearly
    # the same size, since generated is only ~1,600 rows next to real's
    # 6.95M) is still alive -- 28 cols x 6,953,160 rows x 4 bytes = 742.7
    # MiB, matching the reported failure exactly. `real["is_generated"] =
    # False` right before it likely also forced the preceding `.copy()` to
    # consolidate, making it worse.
    #
    # Fix: never ask for one allocation that big. Build the pool column by
    # column into a preallocated array per column (~27 MB each, one at a
    # time) instead of asking pandas to concat two wide blocks at once --
    # same "avoid a single oversized transient allocation" discipline as
    # train_autoencoder.py's transform() fix and build_features.py's
    # _entity_velocity fix.
    n_real, n_gen = len(real), len(generated)
    n_pool = n_real + n_gen
    pool_data = {}

    for col in NUMERIC_FEATURES + BOOLEAN_FEATURES:
        arr = np.empty(n_pool, dtype="float32")
        arr[:n_real] = pd.to_numeric(real[col], errors="coerce").to_numpy(dtype="float32")
        arr[n_real:] = pd.to_numeric(generated[col], errors="coerce").to_numpy(dtype="float32")
        pool_data[col] = arr
    gc.collect()

    for col in CATEGORICAL_FEATURES:
        pool_data[col] = pd.concat(
            [real[col], generated[col]], ignore_index=True
        ).astype("category")

    label_arr = np.empty(n_pool, dtype="int8")
    label_arr[:n_real] = pd.to_numeric(real[LABEL_COLUMN], errors="coerce").fillna(0).to_numpy(dtype="int8")
    label_arr[n_real:] = pd.to_numeric(generated[LABEL_COLUMN], errors="coerce").fillna(0).to_numpy(dtype="int8")
    pool_data[LABEL_COLUMN] = label_arr

    pool_data["is_generated"] = np.concatenate(
        [np.zeros(n_real, dtype=bool), np.ones(n_gen, dtype=bool)]
    )

    del real, generated
    gc.collect()

    pool = pd.DataFrame(pool_data)
    del pool_data
    gc.collect()

    return pool


def train_val_split(pool: pd.DataFrame, val_size: float = 0.2, seed: int = 42):
    X = pool[ALL_FEATURE_COLUMNS]
    y = pool[LABEL_COLUMN].astype("int8")
    return train_test_split(X, y, test_size=val_size, random_state=seed, stratify=y)
