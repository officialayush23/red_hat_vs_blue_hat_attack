"""
Red Team artifact generator for the three non-graph Phase 1 attack families:
transaction_fraud, account_takeover, synthetic_identity.

Deterministic, seeded, and grounded in the real legitimate-transaction
distribution via generate/mutation_engine.py's resolved spec -- no LLM
involvement anywhere in this file (docs/TECHNICAL_SPEC.md Principles 3/4).

Each call to generate_case() produces one attack CASE: a short sequence of
transaction rows in (roughly) the canonical feature schema from
defend/features/build_features.py, plus generated-only columns for signals
the two real public datasets don't carry (device/location/beneficiary for
account takeover; account age/relationship count for synthetic identity).
Those extra columns are NaN on every real-data row and populated only on
generated attack rows -- same "leave it null for the dataset that doesn't
have the signal" pattern build_features.py already uses between PaySim and
IEEE-CIS.

The returned dict IS the persistent artifact for Principle 8 -- it gets
written verbatim to a JSON file by generate/inject_attacks.py.
"""

import math
import uuid

# Mirrors merchant_category resolution: our own design choice for what a
# "merchant category mismatch" looks like in each dataset's own vocabulary,
# not an asserted external fact about either dataset.
PAYSIM_NORMAL_TYPES = ["PAYMENT", "CASH_OUT", "CASH_IN", "DEBIT"]
IEEE_NORMAL_PRODUCTS = ["W", "R", "H", "S"]


def _empty_canonical_row() -> dict:
    return {
        "amount": None, "log_amount": None, "hour_of_day": None,
        "oldbalance_orig": None, "newbalance_orig": None, "balance_delta_orig": None,
        "orig_balance_wiped": None, "dest_is_merchant": None, "dest_balance_delta": None, "txn_type": None,
        "card_type": None, "card_network": None, "product_cd": None, "identity_match_score": None,
        "entity_txn_count_so_far": None, "time_since_prev_txn_same_entity": None, "is_first_txn_for_entity": None,
        "source_dataset": None, "is_fraud": 1,
    }


def _apply_merchant_signal(row: dict, source_dataset: str, unusual: bool, rng) -> None:
    if source_dataset == "paysim":
        row["txn_type"] = "TRANSFER" if unusual else rng.choice(PAYSIM_NORMAL_TYPES)
        row["dest_is_merchant"] = 0 if unusual else 1
    else:
        row["product_cd"] = "C" if unusual else rng.choice(IEEE_NORMAL_PRODUCTS)
        row["identity_match_score"] = round(rng.uniform(0.0, 0.3), 4) if unusual else round(rng.uniform(0.6, 1.0), 4)


def _advance_hour(hour: int, gap: float, source_dataset: str) -> int:
    hours_elapsed = gap if source_dataset == "paysim" else gap / 3600.0
    return int(round(hour + hours_elapsed)) % 24


def _build_sequence(spec: dict, n: int, rng, amount_schedule) -> list[dict]:
    """Shared per-family scaffolding: n rows, timestamps advanced by sampled
    gaps from spec["gap_range"], amounts driven by amount_schedule(i, spec, rng).
    """
    source_dataset = spec["source_dataset"]
    lo, hi = spec["gap_range"]
    hour = rng.randint(*spec.get("hour_range", (0, 23)))

    rows = []
    for i in range(n):
        row = _empty_canonical_row()
        row["source_dataset"] = source_dataset
        amount = amount_schedule(i, spec, rng)
        row["amount"] = round(amount, 2)
        row["log_amount"] = round(math.log1p(amount), 4)

        if i == 0:
            row["time_since_prev_txn_same_entity"] = -1.0
            row["is_first_txn_for_entity"] = 1
        else:
            gap = round(rng.uniform(lo, hi), 2)
            row["time_since_prev_txn_same_entity"] = gap
            row["is_first_txn_for_entity"] = 0
            hour = _advance_hour(hour, gap, source_dataset)
        row["hour_of_day"] = hour
        row["entity_txn_count_so_far"] = i
        rows.append(row)
    return rows


def _make_case(family: str, split_portion: str, spec: dict, transaction_sequence: list[dict], extra: dict,
                customer_id: str | None = None) -> dict:
    return {
        "case_id": f"{family}_{uuid.uuid4().hex[:12]}",
        "attack_family": family,
        "split_portion": split_portion,
        "source_dataset": spec["source_dataset"],
        "mutation_params": spec["raw_combo"],
        "resolved_levels": spec["resolved_levels"],
        "signals_expected": _SIGNALS_EXPECTED[family],
        "customer_id": customer_id,  # Phase 2.5 (2026-08-31): real linkage, was always None before this
        "extra_fields": extra,
        "transaction_sequence": transaction_sequence,
    }


def _behavioral_country_channel(spec: dict, customer: dict | None, rng) -> tuple:
    """account_takeover-specific: derives a country/channel for THIS case
    from the assigned customer's own behavior_baseline (generate/
    synthetic_customers.py's _generate_behavior_baseline()), driven by the
    same device_is_new/location_is_trusted signal already chosen for this
    case -- one coherent story per case, not three independently-rolled
    dice. device_is_new=True and location_is_trusted=False both push
    toward this transaction landing OUTSIDE the customer's normal_*
    ranges (sampled from occasional_*, still a plausible value, not an
    exotic one -- see synthetic_customers.py's own module docstring on why
    'occasional' ranges exist at all: a customer who never travels/never
    uses a new device would make deviation detection trivially easy).
    Returns (country, channel) -- (None, None) if no customer was assigned
    (customer_id stays optional; older/ungenerated rosters still work,
    just without this signal)."""
    if customer is None:
        return None, None
    baseline = customer.get("metadata", {}).get("behavior_baseline")
    if not baseline:
        return None, None

    if not spec.get("location_is_trusted", True):
        country = rng.choice(baseline["occasional_countries"])
    else:
        country = rng.choice(baseline["normal_countries"])

    if spec.get("device_is_new", False):
        channel = rng.choice(baseline["occasional_channels"])
    else:
        channel = rng.choice(baseline["normal_channels"])

    return country, channel


_SIGNALS_EXPECTED = {
    "transaction_fraud": ["transaction"],
    "account_takeover": ["transaction", "behavioral", "device"],
    "synthetic_identity": ["behavioral", "device", "graph"],
}


def _generate_transaction_fraud(split_portion: str, spec: dict, rng, customer: dict | None = None) -> dict:
    n = spec["n_transactions"]
    lo, hi = spec["amount_range"]

    def amount_schedule(i, spec, rng):
        return rng.uniform(lo, hi)

    rows = _build_sequence(spec, n, rng, amount_schedule)
    for row in rows:
        _apply_merchant_signal(row, spec["source_dataset"], spec["merchant_unusual"], rng)
    customer_id = customer["id"] if customer else None
    return _make_case("transaction_fraud", split_portion, spec, rows, {"merchant_unusual": spec["merchant_unusual"]},
                       customer_id=customer_id)


def _generate_account_takeover(split_portion: str, spec: dict, rng, customer: dict | None = None) -> dict:
    n = spec["n_transactions"]
    lo, hi = spec["amount_range"]

    def amount_schedule(i, spec, rng):
        # escalating drain after the takeover -- later transactions pull more
        frac = (i + 1) / n
        return lo + (hi - lo) * (frac ** 1.5)

    if spec["gradual_ramp"]:
        # Evasive combination: start with long gaps (looks normal), shrink
        # toward short gaps by the end -- a naive fixed-threshold velocity
        # rule catches an abrupt spike but not a ramp.
        base_lo, base_hi = spec["gap_range"]
        gaps = [base_hi - (base_hi - base_lo) * (i / max(n - 1, 1)) for i in range(n)]
        rows = []
        hour = rng.randint(0, 23)
        source_dataset = spec["source_dataset"]
        for i in range(n):
            row = _empty_canonical_row()
            row["source_dataset"] = source_dataset
            amount = amount_schedule(i, spec, rng)
            row["amount"] = round(amount, 2)
            row["log_amount"] = round(math.log1p(amount), 4)
            if i == 0:
                row["time_since_prev_txn_same_entity"] = -1.0
                row["is_first_txn_for_entity"] = 1
            else:
                gap = round(gaps[i], 2)
                row["time_since_prev_txn_same_entity"] = gap
                row["is_first_txn_for_entity"] = 0
                hour = _advance_hour(hour, gap, source_dataset)
            row["hour_of_day"] = hour
            row["entity_txn_count_so_far"] = i
            rows.append(row)
    else:
        rows = _build_sequence(spec, n, rng, amount_schedule)

    for row in rows:
        _apply_merchant_signal(row, spec["source_dataset"], False, rng)

    country, channel = _behavioral_country_channel(spec, customer, rng)
    extra = {
        "device_is_new": spec["device_is_new"],
        "location_is_trusted": spec["location_is_trusted"],
        "beneficiary_changed": spec["beneficiary_changed"],
        # 2026-08-31 (Phase 2.5): the fields defend/fusion.py's behavioral_adjustment()
        # actually compares against the customer's behavior_baseline -- None on every
        # case generated before this change, and whenever no customer was assigned.
        "country": country,
        "channel": channel,
    }
    return _make_case("account_takeover", split_portion, spec, rows, extra,
                       customer_id=customer["id"] if customer else None)


def _generate_synthetic_identity(split_portion: str, spec: dict, rng, customer: dict | None = None) -> dict:
    n = spec["n_transactions"]
    lo, hi = spec["amount_range"]
    slow_burn = "relationship_building" in str(spec["behavior_pattern"])

    if slow_burn:
        def amount_schedule(i, spec, rng):
            frac = i / max(n - 1, 1)
            return lo + (hi - lo) * frac  # gradual ramp, no obvious spike
    else:
        def amount_schedule(i, spec, rng):
            if i < n - 1:
                return rng.uniform(lo, lo + (hi - lo) * 0.2)  # small "normal" activity
            return rng.uniform(hi * 0.8, hi * 1.5)  # then one abnormal spike

    rows = _build_sequence(spec, n, rng, amount_schedule)
    for row in rows:
        _apply_merchant_signal(row, spec["source_dataset"], False, rng)

    lo_age, hi_age = spec["account_age_days_range"]
    lo_dev, hi_dev = spec["device_history_count_range"]
    lo_rel, hi_rel = spec["relationship_count_range"]
    extra = {
        "account_age_days": rng.randint(lo_age, hi_age),
        "device_history_count": rng.randint(lo_dev, hi_dev),
        "relationship_count": rng.randint(lo_rel, hi_rel),
        "behavior_pattern": spec["behavior_pattern"],
    }
    return _make_case("synthetic_identity", split_portion, spec, rows, extra,
                       customer_id=customer["id"] if customer else None)


_GENERATORS = {
    "transaction_fraud": _generate_transaction_fraud,
    "account_takeover": _generate_account_takeover,
    "synthetic_identity": _generate_synthetic_identity,
}


def generate_case(family: str, split_portion: str, spec: dict, rng, customer: dict | None = None) -> dict:
    """customer (2026-08-31, Phase 2.5): an optional entry from generate/
    synthetic_customers.py's roster (inject_attacks.py assigns one per
    case, round-robin). Threads customer_id onto every case regardless of
    family; account_takeover additionally derives country/channel from the
    customer's own behavior_baseline (see _behavioral_country_channel) --
    that's the specific data defend/fusion.py's behavioral_adjustment()
    needs and has never had until now. Optional and defaults to None so
    this function's existing callers (and any case generated without a
    customer) keep working unchanged."""
    if family not in _GENERATORS:
        raise KeyError(f"transaction_gen has no generator for family {family!r}")
    return _GENERATORS[family](split_portion, spec, rng, customer)
