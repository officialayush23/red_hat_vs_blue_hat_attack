// GENERATED FILE -- DO NOT EDIT BY HAND.
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

export const ATTACK_FAMILIES = [
  {
    "id": "transaction_fraud",
    "label": "Transaction fraud",
    "category": "transaction",
    "description": "Fraudulent card/account transactions mutated along amount, velocity, merchant category and time of day.",
    "detectors": [
      "XGBoost",
      "LightGBM",
      "Autoencoder",
      "fusion"
    ],
    "metricsKey": "fusion_adversarial_eval",
    "sourceDataset": "ieee_cis",
    "generator": "generate/generate_tabular_attacks via inject_attacks.py",
    "dimensions": [
      "amount",
      "velocity",
      "merchant_category",
      "time_of_day"
    ],
    "trainingAllowed": [
      {
        "amount": "low",
        "velocity": "high"
      },
      {
        "amount": "high",
        "velocity": "low"
      },
      {
        "merchant_category": "mismatch"
      }
    ],
    "heldOutOnly": [
      {
        "amount": "mid",
        "velocity": "moderate",
        "merchant_category": "new",
        "time_of_day": "off_hours"
      }
    ]
  },
  {
    "id": "account_takeover",
    "label": "Account takeover",
    "category": "account-takeover",
    "description": "A real customer's account driven from a new device/location, with beneficiary changes and velocity shifts.",
    "detectors": [
      "XGBoost",
      "LightGBM",
      "Autoencoder",
      "fusion",
      "behavioral_adjustment"
    ],
    "metricsKey": "fusion_adversarial_eval",
    "sourceDataset": "ieee_cis",
    "generator": "generate/inject_attacks.py + artifact_generators/transaction_gen.py",
    "dimensions": [
      "device",
      "location",
      "beneficiary_change",
      "velocity"
    ],
    "trainingAllowed": [
      {
        "device": "new",
        "location": "new"
      },
      {
        "beneficiary_change": true,
        "velocity": "high"
      }
    ],
    "heldOutOnly": [
      {
        "device": "new",
        "location": "trusted",
        "velocity": "gradual_ramp"
      }
    ]
  },
  {
    "id": "synthetic_identity",
    "label": "Synthetic identity",
    "category": "transaction",
    "description": "A fabricated identity built up over time -- thin account age, limited device history, behaviour that ramps from normal to abnormal.",
    "detectors": [
      "XGBoost",
      "LightGBM",
      "Autoencoder",
      "fusion"
    ],
    "metricsKey": "fusion_adversarial_eval",
    "sourceDataset": "ieee_cis",
    "generator": "generate/inject_attacks.py",
    "dimensions": [
      "account_age",
      "device_history",
      "behavior_pattern",
      "relationship_count"
    ],
    "trainingAllowed": [
      {
        "account_age": "low",
        "device_history": "limited",
        "behavior_pattern": "normal_then_abnormal"
      }
    ],
    "heldOutOnly": [
      {
        "account_age": "low",
        "device_history": "limited",
        "behavior_pattern": "gradual_ramp_relationship_building"
      }
    ]
  },
  {
    "id": "mule_network",
    "label": "Mule-network laundering",
    "category": "graph",
    "description": "Funds hopped through a ring of mule accounts, varying hop count, device sharing, timing gaps and cash-out shape.",
    "detectors": [
      "GraphSAGE (GNN)",
      "fusion"
    ],
    "metricsKey": "gnn_colab_round5_reported",
    "sourceDataset": "ibm_aml + ring_gen.py",
    "generator": "generate/artifact_generators/ring_gen.py",
    "dimensions": [
      "hop_count",
      "shared_device",
      "timing_gaps",
      "cash_out",
      "beneficiaries"
    ],
    "trainingAllowed": [
      {
        "hop_count": "2_3",
        "timing_gaps": "short",
        "shared_device": true
      }
    ],
    "heldOutOnly": [
      {
        "hop_count": "4_plus",
        "timing_gaps": "long_irregular",
        "shared_device": false,
        "beneficiaries": "distributed"
      }
    ]
  },
  {
    "id": "voice_scam",
    "label": "Voice-clone impersonation",
    "category": "voice",
    "description": "Cloned or synthetic voice delivering a scam script, varying script type, urgency and whether it clones a specific registered customer.",
    "detectors": [
      "wav2vec2 voice-spoof detector"
    ],
    "metricsKey": "voice_spoof_detector",
    "sourceDataset": "librispeech (bonafide) + Chatterbox clones",
    "generator": "generate/generate_voice_attacks.py",
    "dimensions": [
      "script_type",
      "urgency",
      "voice_characteristics"
    ],
    "trainingAllowed": [
      {
        "script_type": "bank_manager_verification",
        "urgency": "high"
      },
      {
        "script_type": "kyc_reverification",
        "urgency": "high"
      }
    ],
    "heldOutOnly": [
      {
        "script_type": "family_emergency",
        "urgency": "low",
        "voice_characteristics": "cloned_customer"
      }
    ]
  },
  {
    "id": "document_fraud",
    "label": "Document / invoice fraud",
    "category": "document",
    "description": "Tampered invoices where printed fields and the QR-encoded ground truth disagree -- amount, beneficiary, invoice number, bank account, or the QR itself.",
    "detectors": [
      "PaddleOCR-VL + QR cross-check"
    ],
    "metricsKey": "document_consistency_detector",
    "sourceDataset": "self-generated invoices",
    "generator": "generate/generate_document_attacks.py",
    "dimensions": [
      "amount",
      "beneficiary",
      "qr_payload",
      "invoice_number",
      "bank_account"
    ],
    "trainingAllowed": [
      {
        "amount": "tampered"
      },
      {
        "beneficiary": "tampered"
      },
      {
        "qr_payload": "tampered"
      },
      {
        "invoice_number": "tampered"
      },
      {
        "bank_account": "tampered"
      }
    ],
    "heldOutOnly": [
      {
        "amount": "tampered",
        "beneficiary": "tampered",
        "qr_payload": "tampered"
      },
      {
        "bank_account": "tampered",
        "qr_payload": "tampered"
      }
    ]
  },
  {
    "id": "phishing_scam",
    "label": "Phishing (text / GenAI)",
    "category": "text",
    "description": "Scam SMS and email varying urgency, impersonation target, channel and language -- including code-mixed Hinglish designed to slip past English-only filters.",
    "detectors": [
      "TF-IDF + LogisticRegression phishing classifier"
    ],
    "metricsKey": "phishing_classifier_evidence_gate",
    "sourceDataset": "difraud (sms + email)",
    "generator": "generate/generate_phishing_attacks.py",
    "dimensions": [
      "urgency",
      "impersonation_target",
      "channel",
      "language"
    ],
    "trainingAllowed": [
      {
        "urgency": "high",
        "impersonation_target": "bank_otp",
        "channel": "sms"
      },
      {
        "urgency": "high",
        "impersonation_target": "delivery",
        "channel": "sms"
      },
      {
        "urgency": "high",
        "impersonation_target": "tax_refund",
        "channel": "email"
      },
      {
        "urgency": "high",
        "impersonation_target": "tech_support",
        "channel": "email"
      }
    ],
    "heldOutOnly": [
      {
        "urgency": "low",
        "impersonation_target": "employer_hr",
        "channel": "email",
        "language": "english"
      },
      {
        "urgency": "high",
        "impersonation_target": "lottery_prize",
        "channel": "sms",
        "language": "hinglish"
      }
    ]
  }
];

export const ATTACK_FAMILY_BY_ID = Object.fromEntries(
  ATTACK_FAMILIES.map((f) => [f.id, f]),
);

export function getFamily(id) {
  return ATTACK_FAMILY_BY_ID[id] ?? null;
}
