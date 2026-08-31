"""
Stage 3 of the training pipeline — feature engineering.

Reads the validated raw PaySim and IEEE-CIS data and produces one combined,
canonical feature table that XGBoost, LightGBM and the Autoencoder all train
from (docs/TECHNICAL_SPEC.md Section 5: "PaySim + IEEE-CIS, engineered
features").

The two datasets don't share raw columns -- PaySim has balances (mobile-money
transfers), IEEE-CIS has card/identity-match columns (card-not-present
e-commerce). Rather than force a fake mapping between them, the canonical
schema below keeps dataset-specific columns and leaves them null for the
dataset that doesn't have that signal. XGBoost/LightGBM handle this natively
(missing-value-aware splits), and it lets the model learn "this came from a
mobile-money flow" vs "this came from a card flow" as signal in its own
right, via `source_dataset`.

Every feature here is grounded in an actual raw column -- nothing is
invented to hit a target count. The five feature groups map directly to the
priority signals named in TECHNICAL_SPEC.md Section 5 (velocity, amount
deviation, time-of-day, device match, account age, merchant trust):

  always-on     : amount, log_amount, hour_of_day
  PaySim-only   : oldbalance_orig, newbalance_orig, balance_delta_orig,
                  orig_balance_wiped, dest_is_merchant, dest_balance_delta,
                  txn_type
  IEEE-CIS-only : card_type, card_network, product_cd, identity_match_score
  velocity      : entity_txn_count_so_far, time_since_prev_txn_same_entity,
                  is_first_txn_for_entity (entity = nameOrig for PaySim,
                  card1 for IEEE-CIS -- the closest available account proxy
                  in each dataset; is_first_txn_for_entity is also the
                  closest defensible proxy for "account age / thin history"
                  that either public dataset actually supports -- neither
                  carries a real account-creation date)
  meta + label  : source_dataset, is_fraud

Graph-derived features (round 4, docs/DATASETS.md): degree, unique
counterparty count, and pass-through ratio for both the sending
(nameOrig) and receiving (nameDest) account, plus a timestamp-ordered
"in_port" rank for the receiving account -- computed from PaySim's own
real nameOrig/nameDest columns (a real transaction graph that was already
being loaded for velocity but never used for graph structure until now).
Column names (graph_src_*/graph_dst_*/graph_in_port) are shared with
generate/inject_attacks.py's per-row features for mule_network cases,
computed the same way from that family's own real generated graph -- see
that module for why the other three generated families (transaction_fraud,
account_takeover, synthetic_identity) get NaN here instead: none of them
have a real multi-account graph structure despite synthetic_identity's
"graph" signal label (that label is a conceptual signal-category tag, not
a real generated graph payload -- verified by reading
artifact_generators/transaction_gen.py directly).
IEEE-CIS gets NaN for all seven columns -- card-not-present transactions
have no destination-account concept, so there is no real graph to derive
these from (same "leave null when the dataset lacks the signal"
convention already used above for balance/card columns).

Usage:
    python backend/defend/features/build_features.py
    python backend/defend/features/build_features.py --sample 300000

--sample N loads only the first N rows of each raw CSV -- fast for local
dev iteration. Velocity features near the sample boundary are approximate
in this mode (an entity's earlier transactions may have been cut off by the
row cap) -- expected, not a bug. Omit --sample for the final canonical run
on the full data.

Every "this dataset doesn't have that column" fill below uses
`np.float32(np.nan)`, never a bare `np.nan` -- a bare Python-float np.nan
scalar assigned to a new pandas column defaults to float64, and
combine_and_save()'s pd.concat([paysim_df, ieee_df]) then promotes that
SAME column to float64 across the ENTIRE combined 6.95M-row output
whenever the other side is float32 (verified directly: concatenating a
float32 column with a float64 one upcasts the combined column, including
the float32 side, to float64). This was traced from a real
`Unable to allocate 1.35 GiB for an array with shape (26, 6953160)` crash
in defend/train/train_xgboost.py -- the crash's actual root cause was
here, not in dataset.py's own (separately real, separately fixed) version
of the same mistake: this file's OWN combine_and_save() step had already
baked 14 needlessly-float64 columns into features.parquet itself (7
pre-existing: oldbalance_orig/newbalance_orig/balance_delta_orig/
orig_balance_wiped/dest_is_merchant/dest_balance_delta/identity_match_score;
7 newly introduced by round 4's graph features), so simply calling
`pd.read_parquet(FEATURES_PATH)` in dataset.py was already materializing
an oversized frame before any of that file's own logic ran. Confirmed via
`pyarrow.parquet.read_schema()` on the real generated file: exactly 14
columns were `double` where they should have been `float`.

Memory notes (this matters on a 16GB laptop -- PaySim alone is 6.36M rows):
  - Velocity features are computed by factorizing the entity column to int32
    codes and lexsorting just (codes, time) with numpy -- never sorting the
    full transaction table. An earlier version called df.sort_values() on
    the whole DataFrame (string columns included) just to get three derived
    columns, which duplicated the entire frame in memory and was the direct
    cause of a `malloc of size 536870912 failed` crash on this exact
    hardware. Fixed.
  - Entity-ID columns (nameOrig/nameDest/card1) are read as plain object
    dtype, not pandas' nullable "string" dtype -- the C parser builds an
    object array first regardless, and casting that to StringDtype
    afterwards briefly holds both arrays in memory at once. Skipping the
    cast avoids that doubling for exactly the columns most likely to be
    large.
  - main() writes each dataset to a temp parquet and frees it (del + close
    over scope) before building the next one, so peak memory is "one
    dataset's DataFrame" rather than "both DataFrames plus the concat",
    then reloads both compact parquet files to combine.
"""

import argparse
import gc
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parents[3] / "data" / "processed"

CANONICAL_COLUMNS = [
    # always-on
    "amount", "log_amount", "hour_of_day",
    # PaySim-only
    "oldbalance_orig", "newbalance_orig", "balance_delta_orig",
    "orig_balance_wiped", "dest_is_merchant", "dest_balance_delta", "txn_type",
    # IEEE-CIS-only
    "card_type", "card_network", "product_cd", "identity_match_score",
    # velocity (both, via per-dataset entity proxy)
    "entity_txn_count_so_far", "time_since_prev_txn_same_entity", "is_first_txn_for_entity",
    # graph-derived (PaySim only -- real nameOrig/nameDest graph; NaN for
    # IEEE-CIS, which has no destination-account concept)
    "graph_src_out_degree", "graph_src_unique_out_counterparties", "graph_src_pass_through_ratio",
    "graph_dst_in_degree", "graph_dst_unique_in_counterparties", "graph_dst_pass_through_ratio",
    "graph_in_port",
    # meta + label
    "source_dataset", "is_fraud",
]

CATEGORICAL_COLUMNS = ["txn_type", "card_type", "card_network", "product_cd", "source_dataset"]

# M1,M2,M3,M5-M9 are true/false identity-match flags in IEEE-CIS. M4 is
# excluded deliberately -- it's a 3-way category (M0/M1/M2), not T/F, and
# averaging it in with the boolean ones would silently corrupt the score.
IEEE_MATCH_FLAG_COLUMNS = ["M1", "M2", "M3", "M5", "M6", "M7", "M8", "M9"]


def _entity_velocity(entity: pd.Series, time: pd.Series) -> pd.DataFrame:
    """entity_txn_count_so_far, time_since_prev_txn_same_entity, is_first_txn_for_entity.

    Factorizes `entity` to int32 codes and lexsorts only (codes, time) with
    numpy -- deliberately never sorts (or copies) the full transaction
    DataFrame just to get three small derived columns. See the module
    docstring's "Memory notes" for why this replaced a df.sort_values()
    approach that OOM'd on the full PaySim file.
    """
    codes, _ = pd.factorize(entity.to_numpy(), sort=False)
    codes = codes.astype("int32", copy=False)
    time_arr = time.to_numpy()

    order = np.lexsort((time_arr, codes))  # primary key codes, secondary key time
    codes_sorted = codes[order]
    time_sorted = time_arr[order]

    is_new_entity = np.empty(len(codes_sorted), dtype=bool)
    is_new_entity[0] = True
    is_new_entity[1:] = codes_sorted[1:] != codes_sorted[:-1]

    # Vectorized "cumcount within group": at each entity-boundary, remember
    # the boundary's own index; carry the most recent boundary index forward
    # with a running max (valid because idx is strictly increasing); the
    # in-group position is just idx minus that.
    idx = np.arange(len(codes_sorted))
    run_start = np.maximum.accumulate(np.where(is_new_entity, idx, 0))
    count_so_far_sorted = (idx - run_start).astype("int32")

    time_since_prev_sorted = np.empty(len(time_sorted), dtype="float32")
    time_since_prev_sorted[0] = -1.0
    time_since_prev_sorted[1:] = (time_sorted[1:] - time_sorted[:-1]).astype("float32")
    time_since_prev_sorted[is_new_entity] = -1.0

    # scatter back to original row order
    count_so_far = np.empty_like(count_so_far_sorted)
    count_so_far[order] = count_so_far_sorted
    time_since_prev = np.empty_like(time_since_prev_sorted)
    time_since_prev[order] = time_since_prev_sorted

    return pd.DataFrame(
        {
            "entity_txn_count_so_far": count_so_far,
            "time_since_prev_txn_same_entity": time_since_prev,
            "is_first_txn_for_entity": (time_since_prev < 0).astype("int8"),
        },
        index=entity.index,
    )


def _graph_topology_features(orig: pd.Series, dest: pd.Series, amount: pd.Series, time: pd.Series) -> pd.DataFrame:
    """graph_src_out_degree, graph_src_unique_out_counterparties, graph_src_pass_through_ratio,
    graph_dst_in_degree, graph_dst_unique_in_counterparties, graph_dst_pass_through_ratio, graph_in_port.

    Built from PaySim's own real nameOrig/nameDest columns -- a real
    transaction graph, not a fabricated one (docs/DATASETS.md's round-4
    entry). Account-level aggregates (degree, counterparty diversity, total
    flow) are computed once via groupby -- never a full-frame sort -- then
    mapped back onto each row by account id, mirroring the memory-conscious
    approach _entity_velocity already uses for velocity features.

    pass_through_ratio(account) = min(total_in, total_out) / max(total_in,
    total_out) when the account has both inbound and outbound transactions,
    else 0.0. This is our own derived ratio (not an asserted external fact):
    it is close to 1.0 for a classic layering/mule account (money flows
    through in roughly the amount it flows out) and 0.0 for a pure source
    or pure sink account. Same formula validated for the round-4 GNN's node
    features (docs/DATASETS.md), reused here for consistency.

    graph_in_port reuses _entity_velocity's cumulative-count logic with
    nameDest as the "entity" -- the destination account's timestamp-ordered
    rank among the transactions it has received so far, i.e. the tabular
    equivalent of the GNN's in_port feature (Egressy et al. AAAI 2024,
    arXiv:2306.11586).
    """
    out_agg = pd.DataFrame({"amount": amount.to_numpy()}, index=orig.to_numpy())
    out_agg = out_agg.groupby(level=0)["amount"].agg(["count", "sum"])
    out_agg.columns = ["out_degree", "total_out_amount"]
    out_unique = pd.Series(dest.to_numpy(), index=orig.to_numpy()).groupby(level=0).nunique()
    out_unique.name = "unique_out_counterparties"

    in_agg = pd.DataFrame({"amount": amount.to_numpy()}, index=dest.to_numpy())
    in_agg = in_agg.groupby(level=0)["amount"].agg(["count", "sum"])
    in_agg.columns = ["in_degree", "total_in_amount"]
    in_unique = pd.Series(orig.to_numpy(), index=dest.to_numpy()).groupby(level=0).nunique()
    in_unique.name = "unique_in_counterparties"

    acct = out_agg.join(out_unique, how="outer").join(in_agg, how="outer").join(in_unique, how="outer")
    acct = acct.fillna(0.0)
    has_both = (acct["out_degree"] > 0) & (acct["in_degree"] > 0)
    denom = np.maximum(acct["total_in_amount"], acct["total_out_amount"]).clip(lower=1e-6)
    acct["pass_through_ratio"] = np.where(
        has_both, np.minimum(acct["total_in_amount"], acct["total_out_amount"]) / denom, 0.0,
    )

    dest_velocity = _entity_velocity(dest, time)

    result = pd.DataFrame(index=orig.index)
    result["graph_src_out_degree"] = orig.map(acct["out_degree"]).astype("float32")
    result["graph_src_unique_out_counterparties"] = orig.map(acct["unique_out_counterparties"]).astype("float32")
    result["graph_src_pass_through_ratio"] = orig.map(acct["pass_through_ratio"]).astype("float32")
    result["graph_dst_in_degree"] = dest.map(acct["in_degree"]).astype("float32")
    result["graph_dst_unique_in_counterparties"] = dest.map(acct["unique_in_counterparties"]).astype("float32")
    result["graph_dst_pass_through_ratio"] = dest.map(acct["pass_through_ratio"]).astype("float32")
    result["graph_in_port"] = dest_velocity["entity_txn_count_so_far"].astype("float32")
    return result


def build_paysim_features(sample: int | None) -> pd.DataFrame:
    path = RAW_DIR / "paysim"
    csvs = list(path.glob("*.csv"))
    if not csvs:
        raise FileNotFoundError(f"No PaySim CSV found in {path}. Run acquire.py first.")

    dtypes = {
        "step": "int32", "type": "category", "amount": "float32",
        # nameOrig/nameDest: deliberately plain object, not "string" -- see
        # module docstring's Memory notes.
        "oldbalanceOrg": "float32", "newbalanceOrig": "float32",
        "oldbalanceDest": "float32", "newbalanceDest": "float32",
        "isFraud": "int8",
    }
    read_kwargs = {"dtype": dtypes, "usecols": list(dtypes.keys()) + ["nameOrig", "nameDest"]}
    if sample:
        read_kwargs["nrows"] = sample
    df = pd.read_csv(csvs[0], **read_kwargs)

    velocity = _entity_velocity(df["nameOrig"], df["step"])

    out = pd.DataFrame(index=df.index)
    out["amount"] = df["amount"]
    out["log_amount"] = np.log1p(df["amount"])
    out["hour_of_day"] = (df["step"] % 24).astype("int8")

    out["oldbalance_orig"] = df["oldbalanceOrg"]
    out["newbalance_orig"] = df["newbalanceOrig"]
    out["balance_delta_orig"] = df["oldbalanceOrg"] - df["newbalanceOrig"] - df["amount"]
    out["orig_balance_wiped"] = ((df["newbalanceOrig"] == 0) & (df["oldbalanceOrg"] > 0)).astype("int8")
    out["dest_is_merchant"] = df["nameDest"].astype(str).str.startswith("M").astype("int8")
    out["dest_balance_delta"] = df["newbalanceDest"] - df["oldbalanceDest"] - df["amount"]
    out["txn_type"] = df["type"].astype(str)

    out["card_type"] = np.nan
    out["card_network"] = np.nan
    out["product_cd"] = np.nan
    out["identity_match_score"] = np.float32(np.nan)

    out["entity_txn_count_so_far"] = velocity["entity_txn_count_so_far"]
    out["time_since_prev_txn_same_entity"] = velocity["time_since_prev_txn_same_entity"]
    out["is_first_txn_for_entity"] = velocity["is_first_txn_for_entity"]

    graph_feats = _graph_topology_features(df["nameOrig"], df["nameDest"], df["amount"], df["step"])
    for col in graph_feats.columns:
        out[col] = graph_feats[col]

    out["source_dataset"] = "paysim"
    out["is_fraud"] = df["isFraud"].astype("int8")

    del df, velocity, graph_feats
    gc.collect()
    return out


def build_ieee_features(sample: int | None) -> pd.DataFrame:
    path = RAW_DIR / "ieee_cis"
    txn_files = list(path.glob("train_transaction*.csv"))
    if not txn_files:
        raise FileNotFoundError(f"No IEEE-CIS train_transaction CSV found in {path}. Run acquire.py first.")

    dtype_map = {
        "TransactionID": "int32", "isFraud": "int8", "TransactionDT": "int32",
        "TransactionAmt": "float32", "ProductCD": "category",
        # card1: deliberately plain object, not "string" -- see module
        # docstring's Memory notes.
        "card4": "category", "card6": "category",
    }
    needed = list(dtype_map.keys()) + ["card1"] + IEEE_MATCH_FLAG_COLUMNS
    read_kwargs = {"usecols": needed, "dtype": dtype_map}
    if sample:
        read_kwargs["nrows"] = sample
    df = pd.read_csv(txn_files[0], **read_kwargs)

    velocity = _entity_velocity(df["card1"], df["TransactionDT"])

    out = pd.DataFrame(index=df.index)
    out["amount"] = df["TransactionAmt"]
    out["log_amount"] = np.log1p(df["TransactionAmt"])
    # TransactionDT is seconds since an arbitrary reference point, not a real
    # clock timestamp -- day-of-week isn't derivable, but hour-of-day within
    # the implied 24h cycle is (the standard convention used across IEEE-CIS
    # fraud-detection kernels).
    out["hour_of_day"] = ((df["TransactionDT"] // 3600) % 24).astype("int8")

    out["oldbalance_orig"] = np.float32(np.nan)
    out["newbalance_orig"] = np.float32(np.nan)
    out["balance_delta_orig"] = np.float32(np.nan)
    out["orig_balance_wiped"] = np.float32(np.nan)
    out["dest_is_merchant"] = np.float32(np.nan)
    out["dest_balance_delta"] = np.float32(np.nan)
    out["txn_type"] = np.nan

    out["card_type"] = df["card6"].astype(str)
    out["card_network"] = df["card4"].astype(str)
    out["product_cd"] = df["ProductCD"].astype(str)
    match_flags = df[IEEE_MATCH_FLAG_COLUMNS].replace({"T": 1, "F": 0}).apply(pd.to_numeric, errors="coerce")
    out["identity_match_score"] = match_flags.mean(axis=1, skipna=True).astype("float32")

    out["entity_txn_count_so_far"] = velocity["entity_txn_count_so_far"]
    out["time_since_prev_txn_same_entity"] = velocity["time_since_prev_txn_same_entity"]
    out["is_first_txn_for_entity"] = velocity["is_first_txn_for_entity"]

    # No destination-account concept in IEEE-CIS (card-not-present) -- no real
    # graph to derive these from, so left null (see module docstring).
    out["graph_src_out_degree"] = np.float32(np.nan)
    out["graph_src_unique_out_counterparties"] = np.float32(np.nan)
    out["graph_src_pass_through_ratio"] = np.float32(np.nan)
    out["graph_dst_in_degree"] = np.float32(np.nan)
    out["graph_dst_unique_in_counterparties"] = np.float32(np.nan)
    out["graph_dst_pass_through_ratio"] = np.float32(np.nan)
    out["graph_in_port"] = np.float32(np.nan)

    out["source_dataset"] = "ieee_cis"
    out["is_fraud"] = df["isFraud"].astype("int8")

    del df, velocity, match_flags
    gc.collect()
    return out


def combine_and_save(paysim_df: pd.DataFrame, ieee_df: pd.DataFrame):
    combined = pd.concat([paysim_df, ieee_df], ignore_index=True, sort=False)
    combined = combined[CANONICAL_COLUMNS]
    for col in CATEGORICAL_COLUMNS:
        combined[col] = combined[col].astype("category")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "features.parquet"
    combined.to_parquet(out_path, index=False)

    manifest = {
        "canonical_columns": CANONICAL_COLUMNS,
        "categorical_columns": CATEGORICAL_COLUMNS,
        "row_count": int(len(combined)),
        "row_count_by_source": {k: int(v) for k, v in combined["source_dataset"].value_counts().items()},
        "fraud_rate_overall": float(combined["is_fraud"].mean()),
        "fraud_rate_by_source": {
            k: float(v) for k, v in combined.groupby("source_dataset", observed=True)["is_fraud"].mean().items()
        },
        "null_rate_by_column": {k: float(v) for k, v in combined.isnull().mean().round(4).items()},
    }
    manifest_path = PROCESSED_DIR / "feature_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return combined, out_path, manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--sample", type=int, default=None,
        help="Load only the first N rows of each raw CSV (fast local iteration). "
             "Omit for the full dataset (final canonical run).",
    )
    args = parser.parse_args()

    if args.sample:
        print(
            f"Sampling mode: first {args.sample:,} rows per dataset. Velocity features "
            "near the sample boundary are approximate -- expected in this mode."
        )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    paysim_tmp = PROCESSED_DIR / "_paysim_features.parquet"
    ieee_tmp = PROCESSED_DIR / "_ieee_features.parquet"

    print("Building PaySim features...")
    paysim_df = build_paysim_features(args.sample)
    n_paysim = len(paysim_df)
    print(f"  {n_paysim:,} rows")
    paysim_df.to_parquet(paysim_tmp, index=False)
    del paysim_df
    gc.collect()

    print("Building IEEE-CIS features...")
    ieee_df = build_ieee_features(args.sample)
    n_ieee = len(ieee_df)
    print(f"  {n_ieee:,} rows")
    ieee_df.to_parquet(ieee_tmp, index=False)
    del ieee_df
    gc.collect()

    print("Combining and saving...")
    paysim_df = pd.read_parquet(paysim_tmp)
    ieee_df = pd.read_parquet(ieee_tmp)
    combined, out_path, manifest_path = combine_and_save(paysim_df, ieee_df)
    paysim_tmp.unlink(missing_ok=True)
    ieee_tmp.unlink(missing_ok=True)

    print(f"\nWrote {len(combined):,} rows x {combined.shape[1]} columns to {out_path}")
    print(f"Manifest: {manifest_path}")
    print(f"Overall fraud rate: {combined['is_fraud'].mean():.4%}")
    print("\nDone. Next: synthetic attack injection (Stage 4, coming next turn).")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nFEATURE BUILD FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
