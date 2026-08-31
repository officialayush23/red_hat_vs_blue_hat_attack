"""
Single source of truth for which mutation-parameter combinations are
train-allowed vs. held-out-only, per attack family.

This is docs/TECHNICAL_SPEC.md Section 4a, transcribed as data rather than
prose -- the mutation engine and the adversarial evaluation harness both
import FAMILIES from here, so there is exactly one place that can drift out
of sync with the frozen spec.

Each combo is a partial dict: only the dimensions it constrains are keys.
Unset dimensions fall back to the family's DEFAULT_PARAMS in
generate/mutation_engine.py. This mirrors the spec's own phrasing --
e.g. transaction fraud's third training-allowed combo is just "standard
merchant mismatch," not a full specification of every dimension.

Phase 1 scope: transaction_fraud, account_takeover, synthetic_identity,
mule_network (mule via self-generated networkx rings, per
docs/TECHNICAL_SPEC.md Section 10).

Phase 2 adds voice_scam (2026-08-30) and document_fraud (2026-08-30) here --
phishing follows the same pattern and is not in FAMILIES yet.
"""

FAMILIES = {
    "transaction_fraud": {
        "dimensions": ["amount", "velocity", "merchant_category", "time_of_day"],
        "training_allowed": [
            {"amount": "low", "velocity": "high"},
            {"amount": "high", "velocity": "low"},
            {"merchant_category": "mismatch"},
        ],
        "held_out_only": [
            {"amount": "mid", "velocity": "moderate", "merchant_category": "new", "time_of_day": "off_hours"},
        ],
    },
    "account_takeover": {
        "dimensions": ["device", "location", "beneficiary_change", "velocity"],
        "training_allowed": [
            {"device": "new", "location": "new"},
            {"beneficiary_change": True, "velocity": "high"},
        ],
        "held_out_only": [
            {"device": "new", "location": "trusted", "velocity": "gradual_ramp"},
        ],
    },
    "synthetic_identity": {
        "dimensions": ["account_age", "device_history", "behavior_pattern", "relationship_count"],
        "training_allowed": [
            {"account_age": "low", "device_history": "limited", "behavior_pattern": "normal_then_abnormal"},
        ],
        "held_out_only": [
            {"account_age": "low", "device_history": "limited", "behavior_pattern": "gradual_ramp_relationship_building"},
        ],
    },
    "mule_network": {
        # "beneficiaries" isn't in Section 4a's "Mutation dimensions" column
        # header, but the held-out combo it lists explicitly names
        # "distributed beneficiaries" as part of the evasive shape -- declared
        # here so it's a recognized dimension rather than an undeclared one.
        "dimensions": ["hop_count", "shared_device", "timing_gaps", "cash_out", "beneficiaries"],
        "training_allowed": [
            {"hop_count": "2_3", "timing_gaps": "short", "shared_device": True},
        ],
        "held_out_only": [
            {"hop_count": "4_plus", "timing_gaps": "long_irregular", "shared_device": False, "beneficiaries": "distributed"},
        ],
    },
    "voice_scam": {
        # Section 4a: "Cloned/synthetic voice, scam script." Mutation
        # dimensions per the spec table: script type, urgency, voice
        # characteristics. voice_characteristics captures whether the
        # generated audio is a straight TTS read (no specific target
        # identity) or a clone of a specific synthetic customer's own
        # registered reference voice (true impersonation, Section 4b-i) --
        # wired to real synthetic_customers rows as of 2026-08-30
        # (generate/synthetic_customers.py).
        "dimensions": ["script_type", "urgency", "voice_characteristics"],
        "training_allowed": [
            {"script_type": "bank_manager_verification", "urgency": "high"},
            {"script_type": "kyc_reverification", "urgency": "high"},
        ],
        "held_out_only": [
            # Novel framing designed to read as legitimate rather than
            # alarming -- the evasive combination per Section 4a.
            {"script_type": "family_emergency", "urgency": "low", "voice_characteristics": "cloned_customer"},
        ],
    },
    "document_fraud": {
        # Section 4a: "Tampered invoice or QR payload." Five mutation
        # dimensions -- amount, beneficiary, QR payload, invoice number,
        # and bank_account (2026-08-30 addition: payment-redirection /
        # "bank-account replacement" fraud, a real documented pattern) --
        # each independently either "consistent" (printed value matches
        # the QR-encoded ground truth) or "tampered".
        # generate/artifact_generators/document_gen.py resolves what
        # "tampered" concretely means per-dimension: for amount/
        # beneficiary/invoice_number/bank_account, the PRINTED field is
        # edited while the QR keeps the original value (forged-invoice
        # pattern); for qr_payload, the QR itself is swapped for a
        # wholesale different (still well-formed) invoice while everything
        # printed stays internally consistent (QR-swap fraud) -- two
        # distinct real-world tampering mechanisms that both surface as
        # the same observable: printed-vs-QR mismatch.
        "dimensions": ["amount", "beneficiary", "qr_payload", "invoice_number", "bank_account"],
        "training_allowed": [
            # Single-field tampering, per spec -- one combo per dimension so
            # get_combination's uniform choice covers each field equally.
            {"amount": "tampered"},
            {"beneficiary": "tampered"},
            {"qr_payload": "tampered"},
            {"invoice_number": "tampered"},
            {"bank_account": "tampered"},
        ],
        "held_out_only": [
            # "multi-field simultaneous tampering (amount + beneficiary + QR
            # together)" -- Section 4a's own explicit held-out example,
            # transcribed directly rather than invented.
            {"amount": "tampered", "beneficiary": "tampered", "qr_payload": "tampered"},
            # Payment-redirection evasion: swap both the bank account AND
            # the QR that would otherwise reveal it -- the printed/QR
            # amount and identity fields stay untouched, so this combo is
            # NOT caught by an amount- or name-level sanity check, only by
            # the bank_account cross-check specifically.
            {"bank_account": "tampered", "qr_payload": "tampered"},
        ],
    },
    "phishing_scam": {
        # Section 4a: "Scam SMS/email/WhatsApp message." Mutation
        # dimensions: urgency, impersonation_target, channel, language.
        # channel maps directly onto difraud/difraud's own "sms" and
        # "phishing" (email) domains -- the classifier
        # (train_phishing_classifier.py) trains on real difraud rows for
        # exactly these two channels, so held-out evaluation exercises the
        # same channel shapes it learned from, not a third unseen one.
        "dimensions": ["urgency", "impersonation_target", "channel", "language"],
        "training_allowed": [
            {"urgency": "high", "impersonation_target": "bank_otp", "channel": "sms"},
            {"urgency": "high", "impersonation_target": "delivery", "channel": "sms"},
            {"urgency": "high", "impersonation_target": "tax_refund", "channel": "email"},
            {"urgency": "high", "impersonation_target": "tech_support", "channel": "email"},
        ],
        "held_out_only": [
            # "novel impersonation target + low-urgency wording (designed
            # to read as legitimate)" -- Section 4a's own explicit
            # held-out example, transcribed directly.
            {"urgency": "low", "impersonation_target": "employer_hr", "channel": "email", "language": "english"},
            # Second evasion axis, not in the spec's prose example but a
            # real documented pattern: code-mixed Hindi/English text
            # bypassing English-only keyword/classifier filters.
            {"urgency": "high", "impersonation_target": "lottery_prize", "channel": "sms", "language": "hinglish"},
        ],
    },
}

SPLIT_PORTIONS = ("train", "held_out")


def list_families() -> list[str]:
    return list(FAMILIES.keys())


def get_combination(family: str, split_portion: str, rng) -> dict:
    """One combo, chosen uniformly at random from the family's allowed list
    for this split_portion. `rng` is a random.Random instance -- caller
    controls the seed, so a run is fully reproducible.
    """
    if family not in FAMILIES:
        raise KeyError(f"Unknown attack family: {family!r}. Known: {list_families()}")
    if split_portion not in SPLIT_PORTIONS:
        raise ValueError(f"split_portion must be one of {SPLIT_PORTIONS}, got {split_portion!r}")

    key = "training_allowed" if split_portion == "train" else "held_out_only"
    combos = FAMILIES[family][key]
    return dict(rng.choice(combos))  # copy -- caller may mutate
