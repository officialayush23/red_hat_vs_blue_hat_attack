"""
Red Team artifact generator for the mule_network attack family --
self-generated fraud-ring graphs via networkx (docs/TECHNICAL_SPEC.md
Section 3: "no external dataset dependency, full control over topology").

Deterministic and seeded, same as artifact_generators/transaction_gen.py --
no LLM involvement. Mule-network transfers are modeled in PaySim's
mobile-money vocabulary specifically (multi-hop TRANSFER/CASH_OUT chains
are what that dataset's schema represents) rather than IEEE-CIS's
card-not-present schema, which has no natural multi-hop transfer concept.

Each case is one ring: a networkx DiGraph of hop_count edges (a fan-out to
several beneficiaries on the final hop when the combination calls for
"distributed beneficiaries"), amounts decaying slightly per hop (layering --
each intermediate mule skims or forwards a slightly reduced amount), and
inter-hop timing drawn from the resolved gap range (irregular/jittered when
the combination's timing_gaps is "long_irregular").

The graph itself (nodes + edges + attributes) is kept in the returned
artifact alongside the flattened transaction_sequence -- the edge list is
what Phase 3's GNN will eventually train on; the flattened rows are what
Phase 1's XGBoost/LightGBM get graph-derived features from in the meantime
(docs/TECHNICAL_SPEC.md Section 10, Phase 1: "graph-derived features into
XGBoost/LightGBM rather than a trained GNN yet").
"""

import uuid

import networkx as nx


def _empty_canonical_row() -> dict:
    return {
        "amount": None, "log_amount": None, "hour_of_day": None,
        "oldbalance_orig": None, "newbalance_orig": None, "balance_delta_orig": None,
        "orig_balance_wiped": None, "dest_is_merchant": None, "dest_balance_delta": None, "txn_type": None,
        "card_type": None, "card_network": None, "product_cd": None, "identity_match_score": None,
        "entity_txn_count_so_far": None, "time_since_prev_txn_same_entity": None, "is_first_txn_for_entity": None,
        "source_dataset": "paysim", "is_fraud": 1,
    }


def generate_case(split_portion: str, spec: dict, rng, customer: dict | None = None) -> dict:
    import math

    # customer (2026-08-31, Phase 2.5): threads customer_id onto the case for
    # identity-family linkage (inject_attacks.py assigns one per case,
    # round-robin over generate/synthetic_customers.py's roster) -- optional,
    # no behavioral country/channel derivation here (unlike account_takeover
    # in transaction_gen.py): a mule ring's signal is its graph topology, not
    # a deviation from one customer's own normal transacting pattern.
    customer_id = customer["id"] if customer else None

    ring_id = uuid.uuid4().hex[:10]
    hop_count = rng.randint(*spec["hop_count_range"])
    distributed = spec["distributed_beneficiaries"]
    shared_device = spec["shared_device"]
    irregular = spec["timing_irregular"]
    gap_lo, gap_hi = spec["gap_range"]
    amount_lo, amount_hi = spec["amount_range"]

    n_final_hops = rng.randint(2, 3) if distributed else 1
    # Chain of `hop_count` edges needs hop_count+1 relay nodes when the chain
    # runs straight through; when it fans out at the end, the chain itself is
    # hop_count-1 edges / hop_count relay nodes, and the fan-out targets are
    # separate destination nodes (added below).
    relay_count = hop_count if distributed else hop_count + 1
    node_ids = [f"MULE_{ring_id}_{i}" for i in range(relay_count)]
    if distributed:
        node_ids += [f"MULE_{ring_id}_dest{i}" for i in range(n_final_hops)]

    graph = nx.DiGraph()
    graph.add_nodes_from(node_ids)

    start_amount = rng.uniform(amount_hi * 0.6, amount_hi)
    decay = rng.uniform(0.92, 0.98)  # each hop keeps 92-98% of the previous amount

    rows = []
    hour = rng.randint(0, 23)
    amount = start_amount
    for hop in range(hop_count - (1 if distributed else 0)):
        src, dst = node_ids[hop], node_ids[hop + 1]
        graph.add_edge(src, dst, amount=round(amount, 2), hop=hop)

        row = _empty_canonical_row()
        row["amount"] = round(amount, 2)
        row["log_amount"] = round(math.log1p(amount), 4)
        row["txn_type"] = "TRANSFER"
        row["dest_is_merchant"] = 0
        row["entity_txn_count_so_far"] = hop
        if hop == 0:
            row["time_since_prev_txn_same_entity"] = -1.0
            row["is_first_txn_for_entity"] = 1
        else:
            gap = rng.uniform(gap_lo, gap_hi)
            if irregular:
                gap *= rng.choice([1.0, 1.0, 3.5])  # occasional long stall -- "irregular"
            row["time_since_prev_txn_same_entity"] = round(gap, 2)
            row["is_first_txn_for_entity"] = 0
            hour = int(round(hour + gap)) % 24  # paysim gap unit is hours, matches build_features
        row["hour_of_day"] = hour
        rows.append(row)
        amount *= decay

    if distributed:
        # Final hop fans out from the last relay node to several distinct
        # beneficiaries -- the evasive shape from the held-out combination
        # (no single obvious cash-out endpoint to flag).
        relay = node_ids[hop_count - 1]
        split_amount = amount / n_final_hops
        for i in range(n_final_hops):
            dst = f"MULE_{ring_id}_dest{i}"
            graph.add_edge(relay, dst, amount=round(split_amount, 2), hop=hop_count - 1 + i)
            row = _empty_canonical_row()
            row["amount"] = round(split_amount, 2)
            row["log_amount"] = round(math.log1p(max(split_amount, 0.01)), 4)
            row["txn_type"] = "CASH_OUT" if spec["cash_out"] else "TRANSFER"
            row["dest_is_merchant"] = 0
            row["entity_txn_count_so_far"] = hop_count - 1 + i
            gap = rng.uniform(gap_lo, gap_hi)
            row["time_since_prev_txn_same_entity"] = round(gap, 2)
            row["is_first_txn_for_entity"] = 0
            hour = int(round(hour + gap)) % 24
            row["hour_of_day"] = hour
            rows.append(row)
    else:
        rows[-1]["txn_type"] = "CASH_OUT" if spec["cash_out"] else "TRANSFER"

    return {
        "case_id": f"mule_network_{ring_id}",
        "attack_family": "mule_network",
        "split_portion": split_portion,
        "source_dataset": "paysim",
        "mutation_params": spec["raw_combo"],
        "resolved_levels": spec["resolved_levels"],
        "signals_expected": ["graph", "transaction"],
        "customer_id": customer_id,  # Phase 2.5 (2026-08-31): real linkage, was always None before this
        "extra_fields": {
            "ring_id": ring_id,
            "hop_count": hop_count,
            "shared_device": shared_device,
            "distributed_beneficiaries": distributed,
            "timing_irregular": irregular,
        },
        "graph": {
            "nodes": list(graph.nodes),
            "edges": [{"source": u, "target": v, **d} for u, v, d in graph.edges(data=True)],
        },
        "transaction_sequence": rows,
    }
