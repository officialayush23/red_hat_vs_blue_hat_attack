"""
Emits frontend/src/data/attackFamilies.generated.js from the real
evaluation/split_policy.py FAMILIES dict.

Why generate instead of hand-writing the frontend copy: the frontend used
to ship data/attackCatalog.js, a hand-written catalogue of 12 invented
attacks ("Trusted Device + Mule Network", "QR Quishing (Parking / Bill
Overlay)") that did not correspond to this system's 7 real attack families
at all -- the Attack Library page was showing attacks the backend has
never generated or scored. Transcribing FAMILIES into JS by hand would
just move that drift risk one step later, so this script transcribes it
mechanically and the output carries a DO-NOT-EDIT banner.

Everything structural (family ids, mutation dimensions, the exact
training-allowed and held-out-only combinations) comes straight from
split_policy.py. FAMILY_META below is the only hand-written part: display
labels, the scope category each family maps to (identical to
orchestration/agent_runner.py's FAMILY_TO_CATEGORY), which real detector
scores it, and the metrics.json key holding its real evidence-gate
numbers. No severities, no invented narrative copy -- severity is derived
at render time from the family's real measured recall instead.

Run:  python tools/export_attack_taxonomy.py
"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from evaluation.split_policy import FAMILIES  # noqa: E402

OUT = BACKEND_DIR.parent / "frontend" / "src" / "data" / "attackFamilies.generated.js"

# The only hand-written table here. Every value is a fact about this
# codebase, checkable by opening the file it names.
FAMILY_META = {
    "transaction_fraud": {
        "label": "Transaction fraud",
        "category": "transaction",
        "description": "Fraudulent card/account transactions mutated along amount, velocity, merchant category and time of day.",
        "detectors": ["XGBoost", "LightGBM", "Autoencoder", "fusion"],
        "metricsKey": "fusion_adversarial_eval",
        "sourceDataset": "ieee_cis",
        "generator": "generate/generate_tabular_attacks via inject_attacks.py",
    },
    "account_takeover": {
        "label": "Account takeover",
        "category": "account-takeover",
        "description": "A real customer's account driven from a new device/location, with beneficiary changes and velocity shifts.",
        "detectors": ["XGBoost", "LightGBM", "Autoencoder", "fusion", "behavioral_adjustment"],
        "metricsKey": "fusion_adversarial_eval",
        "sourceDataset": "ieee_cis",
        "generator": "generate/inject_attacks.py + artifact_generators/transaction_gen.py",
    },
    "synthetic_identity": {
        "label": "Synthetic identity",
        "category": "transaction",
        "description": "A fabricated identity built up over time -- thin account age, limited device history, behaviour that ramps from normal to abnormal.",
        "detectors": ["XGBoost", "LightGBM", "Autoencoder", "fusion"],
        "metricsKey": "fusion_adversarial_eval",
        "sourceDataset": "ieee_cis",
        "generator": "generate/inject_attacks.py",
    },
    "mule_network": {
        "label": "Mule-network laundering",
        "category": "graph",
        "description": "Funds hopped through a ring of mule accounts, varying hop count, device sharing, timing gaps and cash-out shape.",
        "detectors": ["GraphSAGE (GNN)", "fusion"],
        "metricsKey": "gnn_colab_round5_reported",
        "sourceDataset": "ibm_aml + ring_gen.py",
        "generator": "generate/artifact_generators/ring_gen.py",
    },
    "voice_scam": {
        "label": "Voice-clone impersonation",
        "category": "voice",
        "description": "Cloned or synthetic voice delivering a scam script, varying script type, urgency and whether it clones a specific registered customer.",
        "detectors": ["wav2vec2 voice-spoof detector"],
        "metricsKey": "voice_spoof_detector",
        "sourceDataset": "librispeech (bonafide) + Chatterbox clones",
        "generator": "generate/generate_voice_attacks.py",
    },
    "document_fraud": {
        "label": "Document / invoice fraud",
        "category": "document",
        "description": "Tampered invoices where printed fields and the QR-encoded ground truth disagree -- amount, beneficiary, invoice number, bank account, or the QR itself.",
        "detectors": ["PaddleOCR-VL + QR cross-check"],
        "metricsKey": "document_consistency_detector",
        "sourceDataset": "self-generated invoices",
        "generator": "generate/generate_document_attacks.py",
    },
    "phishing_scam": {
        "label": "Phishing (text / GenAI)",
        "category": "text",
        "description": "Scam SMS and email varying urgency, impersonation target, channel and language -- including code-mixed Hinglish designed to slip past English-only filters.",
        "detectors": ["TF-IDF + LogisticRegression phishing classifier"],
        "metricsKey": "phishing_classifier_evidence_gate",
        "sourceDataset": "difraud (sms + email)",
        "generator": "generate/generate_phishing_attacks.py",
    },
}


def build() -> str:
    families = []
    for family, spec in FAMILIES.items():
        meta = FAMILY_META.get(family)
        if meta is None:
            raise SystemExit(
                f"split_policy.FAMILIES has {family!r} but FAMILY_META here does not. "
                "Add it rather than letting the frontend silently drop a real family."
            )
        families.append({
            "id": family,
            **meta,
            "dimensions": spec["dimensions"],
            "trainingAllowed": spec["training_allowed"],
            "heldOutOnly": spec["held_out_only"],
        })

    body = json.dumps(families, indent=2)
    return f"""// GENERATED FILE -- DO NOT EDIT BY HAND.
//
// Written by backend/tools/export_attack_taxonomy.py from
// backend/evaluation/split_policy.py's FAMILIES dict, which is this
// project's single source of truth for which mutation-parameter
// combinations are training-allowed vs. held-out-only per attack family
// (docs/TECHNICAL_SPEC.md Section 4a).
//
// Re-run `python tools/export_attack_taxonomy.py` from backend/ after any
// change to FAMILIES. Counts, recall and example cases are NOT in here --
// those are read live from Supabase (services/api/attacks.js), because
// they change every time a real run happens.

export const ATTACK_FAMILIES = {body};

export const ATTACK_FAMILY_BY_ID = Object.fromEntries(
  ATTACK_FAMILIES.map((f) => [f.id, f]),
);

export function getFamily(id) {{
  return ATTACK_FAMILY_BY_ID[id] ?? null;
}}
"""


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding="utf-8")
    print(f"Wrote {OUT} ({len(FAMILIES)} families)")
