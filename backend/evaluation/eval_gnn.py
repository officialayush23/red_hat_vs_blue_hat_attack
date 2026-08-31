"""
Section 8 step 4, GNN variant. Independent, local, second verification of
the recall number `notebooks/train_gnn_mule_network.ipynb` reports from
Colab -- run against the SAME real held-out `mule_network` cases (read
locally from `data/generated/attacks/held_out/mule_network/*.json`, the
identical on-disk files the Colab notebook pulled a copy of via Supabase),
using the SAME frozen weights (`backend/defend/models/gnn.pt`). Two
independent runs converging on the same number is real evidence; one
Colab printout alone is not, per this project's evidence-gate discipline
(the same reasoning that made `run_adversarial_eval.py` a second,
mandatory check on the frozen tabular models rather than trusting
Stage-5's training-time validation numbers).

GraphSAGEEncoder/EdgeClassifier and the score_case() feature schema below
MUST stay architecturally/schema identical to the notebook's definitions
-- this script loads the notebook's saved state_dict directly into them.
If the notebook's architecture or feature schema changes, update both
together. As of round 4 (see docs/DATASETS.md), the architecture and
feature schema follow the published methodology for this exact dataset:
Altman, Egressy et al., NeurIPS 2023 (arXiv:2306.16424) established the
IBM AML benchmark and reported GNN baselines (GIN 28.7% F1, PNA 56.8% F1,
graph-features+XGBoost 63.2% F1 -- beating every GNN); Egressy et al.,
AAAI 2024 (arXiv:2306.11586) defined "reverse message passing" (separate
in/out neighbor aggregation, implemented here as DirectionalSAGELayer)
and "port numbering" (both endpoints' timestamp-ordered local
send/receive IDs, implemented as log_out_port/log_in_port edge features),
reporting up to +30% minority-class F1 from these two techniques on this
same money-laundering task.

Only needs the base `torch_geometric` package (pure Python, no CUDA
compilation) -- the optional accelerators (torch-scatter/torch-sparse/
pyg-lib) that are a known Windows install risk are NOT required here:
every case graph is tiny (a handful of nodes), so unaccelerated SAGEConv
is fast enough. If torch_geometric still isn't installed/importable,
this script skips gracefully (same pattern as the autoencoder's
_load_frozen_autoencoder()) rather than crashing the whole eval suite.

Usage:
    pip install torch_geometric --break-system-packages   # one-time, pure Python
    python backend/evaluation/eval_gnn.py
"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import numpy as np  # noqa: E402

from evaluation.metrics import record_result  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
MODELS_DIR = BACKEND_DIR / "defend" / "models"
GNN_PATH = MODELS_DIR / "gnn.pt"
RESULTS_JSON = MODELS_DIR / "metrics.json"
RESULTS_MD = REPO_ROOT / "docs" / "EVALUATION_RESULTS.md"
HELD_OUT_DIR = REPO_ROOT / "data" / "generated" / "attacks" / "held_out" / "mule_network"


def _load_gnn():
    """Returns (score_case_fn, ok). ok=False (with an explanatory print) if
    torch/torch_geometric aren't available or gnn.pt hasn't been placed yet
    -- never raises, so this integrates with identify_weakest()'s existing
    per-model try pattern without special-casing the GNN."""
    if not GNN_PATH.exists():
        print(f"{GNN_PATH} not found -- run notebooks/train_gnn_mule_network.ipynb on Colab "
              f"first and save its gnn.pt here.", file=sys.stderr)
        return None, False
    try:
        import torch
        import torch.nn as nn
        import torch.nn.functional as F
        from torch_geometric.nn import SAGEConv
    except ImportError as exc:
        print(f"torch_geometric not available ({exc}) -- pip install torch_geometric "
              f"--break-system-packages (pure Python, no CUDA compilation needed for "
              f"unaccelerated inference on these small graphs).", file=sys.stderr)
        return None, False

    class DirectionalSAGELayer(nn.Module):
        """Round 4: "reverse message passing" (Egressy et al., AAAI 2024,
        arXiv:2306.11586) -- aggregates a node's in-neighbors and
        out-neighbors with SEPARATE SAGEConv layers, then concatenates,
        instead of only ever seeing predecessors (plain SAGEConv)."""
        def __init__(self, in_dim, out_dim):
            super().__init__()
            assert out_dim % 2 == 0, "out_dim must split evenly across in/out directions"
            self.conv_in = SAGEConv(in_dim, out_dim // 2)
            self.conv_out = SAGEConv(in_dim, out_dim // 2)

        def forward(self, x, edge_index, edge_index_rev):
            h_in = self.conv_in(x, edge_index)
            h_out = self.conv_out(x, edge_index_rev)
            return torch.cat([h_in, h_out], dim=-1)

    class GraphSAGEEncoder(nn.Module):
        def __init__(self, in_dim, hidden_dim=64, out_dim=32, dropout=0.3):
            super().__init__()
            self.layer1 = DirectionalSAGELayer(in_dim, hidden_dim)
            self.layer2 = DirectionalSAGELayer(hidden_dim, out_dim)
            self.dropout = dropout

        def forward(self, x, edge_index, edge_index_rev):
            h = F.relu(self.layer1(x, edge_index, edge_index_rev))
            h = F.dropout(h, p=self.dropout, training=self.training)  # no-op in eval() mode -- kept for state_dict shape parity
            h = self.layer2(h, edge_index, edge_index_rev)
            return h

    class EdgeClassifier(nn.Module):
        def __init__(self, node_emb_dim, edge_attr_dim, hidden_dim=64, dropout=0.3):
            super().__init__()
            self.mlp = nn.Sequential(
                nn.Linear(node_emb_dim * 2 + edge_attr_dim, hidden_dim), nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(hidden_dim, hidden_dim // 2), nn.ReLU(),
                nn.Linear(hidden_dim // 2, 1),
            )

        def forward(self, h_src, h_dst, edge_attr):
            return self.mlp(torch.cat([h_src, h_dst, edge_attr], dim=1)).squeeze(-1)

    ckpt = torch.load(GNN_PATH, map_location="cpu", weights_only=False)
    encoder = GraphSAGEEncoder(in_dim=ckpt["node_in_dim"])
    classifier = EdgeClassifier(node_emb_dim=32, edge_attr_dim=ckpt["edge_attr_dim"])
    encoder.load_state_dict(ckpt["encoder_state_dict"])
    classifier.load_state_dict(ckpt["classifier_state_dict"])
    encoder.eval()
    classifier.eval()
    threshold = ckpt["decision_threshold"]

    # Round 5: the notebook now z-score normalizes node/edge features using
    # TRAIN-period stats before they ever reach the model (see
    # train_gnn_mule_network.ipynb's graph-building cell) -- scoring here
    # MUST apply the identical transform, using the exact stats persisted
    # into this checkpoint, or local numbers won't reflect what the model
    # was actually trained on. Older (pre-round-5) checkpoints won't carry
    # these keys -- degrade gracefully to unnormalized scoring rather than
    # crashing, same as every other "gnn.pt not ready yet" case here.
    _norm_keys = ("node_mean", "node_std", "edge_mean", "edge_std")
    has_norm_stats = all(ckpt.get(k) is not None for k in _norm_keys)
    if has_norm_stats:
        node_mean = np.array(ckpt["node_mean"], dtype=np.float32)
        node_std = np.array(ckpt["node_std"], dtype=np.float32)
        edge_mean = np.array(ckpt["edge_mean"], dtype=np.float32)
        edge_std = np.array(ckpt["edge_std"], dtype=np.float32)
    else:
        print(f"{GNN_PATH} has no round-5 normalization stats (node_mean/std, edge_mean/std) "
              f"-- scoring with raw unnormalized features, matching whichever round trained "
              f"this checkpoint. Re-run the round-5 notebook and replace gnn.pt to pick up "
              f"normalization.", file=sys.stderr)

    def score_case(case: dict) -> float:
        """Round 4 feature schema -- degree + fan-out/fan-in breadth +
        pass-through ratio for nodes; log-amount + cyclic hour +
        velocity/burst + BOTH port numbers for edges; reverse message
        passing in the encoder call. Every value here is read directly
        from ring_gen.py's own real transaction_sequence (zipped 1:1 by
        index with graph['edges']) or computed structurally from the
        case's own real edge order (in_port). Matches
        notebooks/train_gnn_mule_network.ipynb's score_case() exactly;
        keep both in sync."""
        artifacts = case.get("artifacts", case)
        graph = artifacts["graph"]
        seq = case["transaction_sequence"]
        nodes, edges = graph["nodes"], graph["edges"]
        if not edges:
            return 0.0
        assert len(edges) == len(seq), (
            f"graph edges ({len(edges)}) != transaction_sequence rows ({len(seq)}) for case "
            f"{case.get('id', case.get('case_id'))} -- ring_gen.py's edge/row alignment "
            f"assumption doesn't hold here, do not silently misalign real per-edge features."
        )
        local_id = {n: i for i, n in enumerate(nodes)}
        local_src = np.array([local_id[e["source"]] for e in edges])
        local_dst = np.array([local_id[e["target"]] for e in edges])
        local_amount = np.array([e.get("amount", 0.0) for e in edges], dtype=np.float32)

        n_local = len(nodes)
        out_deg = np.bincount(local_src, minlength=n_local).astype(np.float32)
        in_deg = np.bincount(local_dst, minlength=n_local).astype(np.float32)
        out_amt = np.bincount(local_src, weights=local_amount, minlength=n_local).astype(np.float32)
        in_amt = np.bincount(local_dst, weights=local_amount, minlength=n_local).astype(np.float32)

        unique_out_cp = np.zeros(n_local, dtype=np.float32)
        unique_in_cp = np.zeros(n_local, dtype=np.float32)
        for node_i in range(n_local):
            unique_out_cp[node_i] = len(set(local_dst[local_src == node_i].tolist()))
            unique_in_cp[node_i] = len(set(local_src[local_dst == node_i].tolist()))
        pass_through = np.log1p(in_amt) - np.log1p(out_amt)

        x_local = np.stack([
            out_deg, in_deg, np.log1p(out_amt), np.log1p(in_amt),
            np.log1p(np.divide(out_amt, np.maximum(out_deg, 1))),
            unique_out_cp, unique_in_cp, pass_through,
        ], axis=1).astype(np.float32)

        log_amt = np.log1p(local_amount)
        hour = np.array([(row.get("hour_of_day") or 0) for row in seq], dtype=np.float32)
        hour_sin = np.sin(2 * np.pi * hour / 24).astype(np.float32)
        hour_cos = np.cos(2 * np.pi * hour / 24).astype(np.float32)
        time_since_prev = np.array([row.get("time_since_prev_txn_same_entity", -1.0) for row in seq], dtype=np.float32)
        is_first = np.array([row.get("is_first_txn_for_entity", 0) for row in seq], dtype=np.float32)
        out_port = np.array([row.get("entity_txn_count_so_far", 0) for row in seq], dtype=np.float32)

        in_port = np.zeros(len(edges), dtype=np.float32)
        dst_seen = {}
        for i, d in enumerate(local_dst):
            in_port[i] = dst_seen.get(d, 0)
            dst_seen[d] = dst_seen.get(d, 0) + 1

        edge_attr = np.stack([
            log_amt, hour_sin, hour_cos,
            np.log1p(np.maximum(time_since_prev, 0.0)).astype(np.float32),
            is_first,
            np.log1p(out_port).astype(np.float32),
            np.log1p(in_port).astype(np.float32),
        ], axis=1)

        if has_norm_stats:
            x_local = (x_local - node_mean) / node_std
            edge_attr = (edge_attr - edge_mean) / edge_std

        x_t = torch.tensor(x_local)
        edge_index_t = torch.tensor(np.stack([local_src, local_dst]), dtype=torch.long)
        edge_index_t_rev = edge_index_t.flip(0)
        edge_attr_t = torch.tensor(edge_attr)
        with torch.no_grad():
            h = encoder(x_t, edge_index_t, edge_index_t_rev)
            logits = classifier(h[local_src], h[local_dst], edge_attr_t)
            probs = torch.sigmoid(logits).numpy()
        return float(probs.max())

    return (score_case, threshold), True


def _append_results_md(recall: float, n_cases: int, threshold: float) -> None:
    RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_MD, "a") as f:
        f.write(
            f"\n## GNN (Task #33) -- local re-verification of the Colab-trained model\n\n"
            f"- Independent, local re-run of the {n_cases} real held-out mule_network cases, "
            f"using the frozen weights saved from notebooks/train_gnn_mule_network.ipynb.\n"
            f"- recall={recall:.4f} at decision_threshold={threshold:.4f} "
            f"(threshold selected on IBM AML's own held-out split, see the notebook).\n"
            f"- This is a second, independent check against the Colab run's own reported "
            f"number in gnn_metrics_snippet.json -- see docs/DATASETS.md.\n"
        )


def main() -> None:
    result, ok = _load_gnn()
    if not ok:
        print("GNN evaluation skipped -- see message above.")
        return
    score_case, threshold = result

    case_paths = sorted(HELD_OUT_DIR.glob("*.json"))
    if not case_paths:
        raise FileNotFoundError(
            f"No cases under {HELD_OUT_DIR} -- run generate/inject_attacks.py first."
        )
    print(f"Scoring {len(case_paths)} real held-out mule_network cases locally...")

    scores = []
    for p in case_paths:
        case = json.loads(p.read_text())
        scores.append(score_case(case))
    scores = np.array(scores)
    detected = scores >= threshold
    recall = float(detected.mean())  # every held-out mule_network case is fraud by construction

    print(f"Local recall: {recall:.4f} ({int(detected.sum())}/{len(detected)}) at threshold={threshold:.4f}")
    print(f"score distribution: min={scores.min():.4f} median={np.median(scores):.4f} max={scores.max():.4f}")

    record_result(
        RESULTS_JSON, "gnn_adversarial_eval_local_reverify",
        {"recall": recall, "threshold": threshold, "n_cases": len(case_paths)},
        extra={"note": "Local, independent re-run of the Colab-reported gnn_adversarial_eval recall "
                        "-- see docs/DATASETS.md. Compare this number against gnn_adversarial_eval "
                        "(from the Colab notebook) before trusting either one alone."},
    )
    _append_results_md(recall, len(case_paths), threshold)
    print(f"\nDone. Recorded to {RESULTS_JSON} and {RESULTS_MD}.")
    print("Compare this recall against metrics.json's gnn_adversarial_eval (from Colab) -- "
          "they should be close (same cases, same weights); a large gap means investigate "
          "before trusting either number.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nGNN EVAL FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
