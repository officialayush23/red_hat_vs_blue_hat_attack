"""
Statistical/structural sanity checks on one generated attack case, run
before it's accepted into an output batch. Fails loudly (raises) rather
than silently writing a malformed case -- same philosophy as
defend/data/validate_raw.py: catch a generation bug here, not three stages
downstream when a model trains on garbage.
"""

from evaluation.split_policy import FAMILIES, SPLIT_PORTIONS

REQUIRED_TOP_LEVEL_KEYS = {
    "case_id", "attack_family", "split_portion", "source_dataset",
    "mutation_params", "resolved_levels", "signals_expected", "transaction_sequence",
}


def validate_case(case: dict) -> None:
    missing = REQUIRED_TOP_LEVEL_KEYS - set(case.keys())
    if missing:
        raise ValueError(f"[{case.get('case_id', '?')}] missing top-level keys: {missing}")

    family = case["attack_family"]
    if family not in FAMILIES:
        raise ValueError(f"[{case['case_id']}] unknown attack_family: {family!r}")

    if case["split_portion"] not in SPLIT_PORTIONS:
        raise ValueError(f"[{case['case_id']}] invalid split_portion: {case['split_portion']!r}")

    known_dims = set(FAMILIES[family]["dimensions"])
    bad_dims = set(case["mutation_params"].keys()) - known_dims
    if bad_dims:
        raise ValueError(f"[{case['case_id']}] mutation_params has dims not declared for {family}: {bad_dims}")

    seq = case["transaction_sequence"]
    if not seq:
        raise ValueError(f"[{case['case_id']}] empty transaction_sequence")

    for i, row in enumerate(seq):
        if row.get("amount") is None or row["amount"] <= 0:
            raise ValueError(f"[{case['case_id']}] row {i}: amount must be positive, got {row.get('amount')}")
        if row.get("is_fraud") != 1:
            raise ValueError(f"[{case['case_id']}] row {i}: is_fraud must be 1 for a generated attack row")
        hour = row.get("hour_of_day")
        if hour is None or not (0 <= hour <= 23):
            raise ValueError(f"[{case['case_id']}] row {i}: hour_of_day out of range: {hour}")
        if row.get("source_dataset") not in ("paysim", "ieee_cis"):
            raise ValueError(f"[{case['case_id']}] row {i}: bad source_dataset: {row.get('source_dataset')}")
        if row.get("entity_txn_count_so_far") != i:
            raise ValueError(
                f"[{case['case_id']}] row {i}: entity_txn_count_so_far should equal position ({i}), "
                f"got {row.get('entity_txn_count_so_far')}"
            )
        if i == 0:
            if row.get("is_first_txn_for_entity") != 1 or row.get("time_since_prev_txn_same_entity") != -1.0:
                raise ValueError(f"[{case['case_id']}] row 0 must be flagged as the entity's first transaction")
        else:
            if row.get("is_first_txn_for_entity") != 0:
                raise ValueError(f"[{case['case_id']}] row {i}: is_first_txn_for_entity must be 0 after row 0")
            gap = row.get("time_since_prev_txn_same_entity")
            if gap is None or gap < 0:
                raise ValueError(f"[{case['case_id']}] row {i}: time_since_prev_txn_same_entity must be >= 0, got {gap}")
