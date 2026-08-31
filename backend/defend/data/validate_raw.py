"""
Stage 2 of the training pipeline — validate raw data before feature
engineering ever touches it.

This fails loudly (non-zero exit code) the moment the raw data doesn't match
what the rest of the pipeline expects, instead of letting a schema mismatch
or a corrupted download silently produce garbage features three steps
downstream.

Usage:
    python backend/defend/data/validate_raw.py
"""

import sys
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw"

PAYSIM_EXPECTED_COLUMNS = {
    "step", "type", "amount", "nameOrig", "oldbalanceOrg", "newbalanceOrig",
    "nameDest", "oldbalanceDest", "newbalanceDest", "isFraud", "isFlaggedFraud",
}

IEEE_TRANSACTION_EXPECTED_COLUMNS = {
    "TransactionID", "isFraud", "TransactionDT", "TransactionAmt",
    "ProductCD", "card1", "card4", "card6",
}

MAX_NULL_RATE = 0.6  # columns nullier than this get flagged, not auto-failed
# IEEE-CIS's identity/behavioral columns (id_*, V*) are legitimately very
# sparse by design -- this is a heads-up, not a failure condition.


def _report_nulls(df: pd.DataFrame, name: str) -> None:
    null_rates = df.isnull().mean().sort_values(ascending=False)
    bad = null_rates[null_rates > MAX_NULL_RATE]
    if len(bad):
        print(f"[{name}] {len(bad)} columns are >{MAX_NULL_RATE:.0%} null "
              f"(expected for IEEE-CIS's optional columns -- worth a glance, not a failure):")
        print(bad.head(10).to_string())


def _report_balance(df: pd.DataFrame, label_col: str, name: str) -> None:
    rate = df[label_col].mean()
    print(f"[{name}] fraud rate in sample: {rate:.4%} ({int(df[label_col].sum()):,} / {len(df):,} rows)")
    if rate == 0 or rate == 1:
        raise ValueError(f"[{name}] label column '{label_col}' has no variation in this sample -- check the file.")


def validate_paysim() -> None:
    path = RAW_DIR / "paysim"
    csvs = list(path.glob("*.csv"))
    if not csvs:
        raise FileNotFoundError(f"No PaySim CSV found in {path}. Run acquire.py first.")
    df = pd.read_csv(csvs[0], nrows=200_000)  # sample -- fast schema check, not a full load
    missing = PAYSIM_EXPECTED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"[PaySim] missing expected columns: {missing}")
    _report_nulls(df, "PaySim")
    _report_balance(df, "isFraud", "PaySim")
    print(f"[PaySim] OK -- schema matches, {df.shape[1]} columns, file: {csvs[0].name}")


def validate_ieee_cis() -> None:
    path = RAW_DIR / "ieee_cis"
    # Specifically "train_transaction*" -- the zip also contains test_transaction.csv,
    # which is the unlabeled competition test set and has no isFraud column. A looser
    # "*transaction*.csv" glob can match that one first (glob order isn't guaranteed
    # alphabetical-safe here) and fail validation on a missing column that was never
    # actually missing from the right file.
    txn_files = list(path.glob("train_transaction*.csv"))
    if not txn_files:
        raise FileNotFoundError(f"No IEEE-CIS train_transaction CSV found in {path}. Run acquire.py first.")
    df = pd.read_csv(txn_files[0], nrows=200_000)
    missing = IEEE_TRANSACTION_EXPECTED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"[IEEE-CIS] missing expected columns: {missing}")
    _report_nulls(df, "IEEE-CIS")
    _report_balance(df, "isFraud", "IEEE-CIS")
    print(f"[IEEE-CIS] OK -- schema matches, {df.shape[1]} columns, file: {txn_files[0].name}")


if __name__ == "__main__":
    try:
        validate_paysim()
        print()
        validate_ieee_cis()
    except Exception as exc:
        print(f"\nVALIDATION FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
    print("\nAll raw data validated successfully. Next: feature engineering (coming next turn).")
