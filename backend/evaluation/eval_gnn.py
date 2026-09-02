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

import argparse
import time
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

    def _score_case_reference(case: dict) -> float:
        """REFERENCE IMPLEMENTATION -- correct, and slow. Kept verbatim.

        This is the original per-case scorer. It is no longer what a run
        uses (see score_cases below), but it is not dead code: --verify-fast
        -path scores a sample through BOTH paths and asserts they agree, so
        the fast path has something to be checked against rather than being
        trusted because it looks right.

        Round 4 feature schema -- degree + fan-out/fan-in breadth +
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

    # ---- FAST PATH --------------------------------------------------------
    #
    # 803.8s for 2,580 cases in run_b1b555224c -- 0.31s each, and none of it
    # is the model, which is a 2-layer GraphSAGE plus a small MLP. It was
    # per-case Python overhead, in three places:
    #
    #   1. one file open + json.loads per case
    #   2. `for node_i in range(n_local)` doing a full numpy mask over every
    #      edge, per node, per case -- quadratic in ring size, in Python
    #   3. one unbatched forward pass per case, paying PyTorch dispatch
    #      overhead 2,580 times for graphs of a few dozen edges
    #
    # (2) and (3) are fixed here. Batching is exactly equivalent because the
    # encoder is pure local message passing (SAGEConv) with no batch norm and
    # no global pooling, and the classifier is per-edge: a disjoint union of
    # graphs with offset node indices produces bit-identical embeddings, since
    # no edge crosses between graphs. Dropout is a no-op in eval() mode.
    def _features_for(case: dict):
        """Same features as the reference, computed without per-node loops.
        Returns (x_local, src, dst, edge_attr) or None for an edge-less case."""
        artifacts = case.get("artifacts", case)
        graph = artifacts["graph"]
        seq = case["transaction_sequence"]
        nodes, edges = graph["nodes"], graph["edges"]
        if not edges:
            return None
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

        # Distinct counterparties per node. The reference loops every node and
        # masks every edge; the distinct (src,dst) pairs give both directions
        # in one pass -- each unique pair contributes exactly one counterparty
        # to its src's out-set and one to its dst's in-set, which is the same
        # definition.
        pairs = np.unique(np.stack([local_src, local_dst], axis=1), axis=0)
        unique_out_cp = np.bincount(pairs[:, 0], minlength=n_local).astype(np.float32)
        unique_in_cp = np.bincount(pairs[:, 1], minlength=n_local).astype(np.float32)
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

        # in_port is "how many earlier edges already targeted this dst", in
        # original edge order. The reference keeps a running dict; a stable
        # sort by dst puts each group together in original order, and
        # searchsorted gives each group's first position, so index-minus-
        # group-start is exactly that running count.
        order = np.argsort(local_dst, kind="stable")
        sorted_dst = local_dst[order]
        group_start = np.searchsorted(sorted_dst, sorted_dst, side="left")
        in_port = np.empty(len(edges), dtype=np.float32)
        in_port[order] = (np.arange(len(edges)) - group_start).astype(np.float32)

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
        return x_local, local_src, local_dst, edge_attr

    def score_cases(cases: list, batch_size: int = 256) -> np.ndarray:
        """Scores many cases per forward pass. Same numbers, ~an order of
        magnitude less wall clock."""
        scores = np.zeros(len(cases), dtype=np.float64)
        feats = [_features_for(c) for c in cases]
        # Edge-less cases score 0.0, exactly as the reference returns.
        live = [i for i, f in enumerate(feats) if f is not None]

        for start in range(0, len(live), batch_size):
            chunk = live[start:start + batch_size]
            xs, srcs, dsts, eas, seg = [], [], [], [], []
            offset = 0
            for slot, idx in enumerate(chunk):
                x_local, src, dst, edge_attr = feats[idx]
                xs.append(x_local)
                srcs.append(src + offset)
                dsts.append(dst + offset)
                eas.append(edge_attr)
                seg.append(np.full(len(src), slot, dtype=np.int64))
                offset += x_local.shape[0]

            x_t = torch.tensor(np.concatenate(xs, axis=0))
            src_t = torch.tensor(np.concatenate(srcs), dtype=torch.long)
            dst_t = torch.tensor(np.concatenate(dsts), dtype=torch.long)
            edge_index_t = torch.stack([src_t, dst_t])
            edge_attr_t = torch.tensor(np.concatenate(eas, axis=0))
            with torch.no_grad():
                h = encoder(x_t, edge_index_t, edge_index_t.flip(0))
                logits = classifier(h[src_t], h[dst_t], edge_attr_t)
                probs = torch.sigmoid(logits).numpy()

            seg_all = np.concatenate(seg)
            per_case = np.zeros(len(chunk), dtype=np.float64)
            np.maximum.at(per_case, seg_all, probs)  # same reduction as probs.max()
            for slot, idx in enumerate(chunk):
                scores[idx] = per_case[slot]
        return scores

    return (_score_case_reference, score_cases, threshold), True


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
    parser = argparse.ArgumentParser(description="Local re-verification of the Colab-trained GNN.")
    parser.add_argument("--batch-size", type=int, default=256,
                        help="Cases per forward pass. Higher is faster and uses more memory.")
    parser.add_argument("--verify-fast-path", type=int, default=0, metavar="N",
                        help="Score the first N cases through BOTH the fast and the reference "
                             "implementation and assert they agree. Use after touching either.")
    args = parser.parse_args()

    result, ok = _load_gnn()
    if not ok:
        # EXIT 2, NOT 0. A skipped step is not a passed step.
        #
        # This returned 0, so run_all_evaluations recorded "gnn OK", the
        # orchestrator counted a clean stage, and a machine whose interpreter
        # simply lacks torch_geometric -- or which has no gnn.pt -- produced a
        # run that looked identical to one where the GNN really ran. The
        # 803-second stage and the zero-second one were indistinguishable
        # downstream.
        print("GNN evaluation skipped -- see message above.")
        sys.exit(2)
    score_case_reference, score_cases, threshold = result

    # tools/storage_sync.py drops a `.storage_bundle.json` marker into every
    # directory it manages, so a bare *.json glob picks it up as a phantom entry
    # after a `storage_sync.py pull` -- on Colab, never locally. Same guard
    # synthetic_customers.load_roster() already carries.
    case_paths = sorted(p for p in HELD_OUT_DIR.glob("*.json") if not p.name.startswith("."))
    if not case_paths:
        raise FileNotFoundError(
            f"No cases under {HELD_OUT_DIR} -- run generate/inject_attacks.py first."
        )
    print(f"Scoring {len(case_paths)} real held-out mule_network cases locally...")

    t0 = time.monotonic()
    cases = [json.loads(p.read_text()) for p in case_paths]

    if args.verify_fast_path:
        # The fast path is an optimization, and an optimization that changes a
        # number is a bug wearing a disguise. Prove it on a sample before
        # trusting it on 2,580.
        n = min(args.verify_fast_path, len(cases))
        print(f"Verifying the fast path against the reference on {n} case(s)...")
        fast = score_cases(cases[:n], batch_size=args.batch_size)
        slow = np.array([score_case_reference(c) for c in cases[:n]])
        worst = float(np.max(np.abs(fast - slow))) if n else 0.0
        # float32 accumulation order differs between one graph and a batch, so
        # exact equality is the wrong test; anything above this is a real
        # divergence, not arithmetic noise.
        assert np.allclose(fast, slow, atol=1e-5, rtol=0), (
            f"FAST PATH DISAGREES with the reference (max |diff| = {worst:.3e}). "
            f"Do not record these numbers."
        )
        print(f"  OK -- max |fast - reference| = {worst:.3e} over {n} cases")

    scores = score_cases(cases, batch_size=args.batch_size)
    print(f"Scored {len(scores)} cases in {time.monotonic() - t0:.1f}s "
          f"(batch_size={args.batch_size})")
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
    except SystemExit:
        raise  # the deliberate exit(2) skip signal must not be caught below
    except Exception as exc:
        print(f"\nGNN EVAL FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
