// Named attack scenarios — the human-recognisable attacks ("Voice Clone IVR
// Takeover", "QR Quishing", "Fan-Out Mule Network Laundering") layered on
// top of the 7 real attack families.
//
// Why this file exists
// --------------------
// data/attackCatalog.js used to list 12 named attacks with invented
// severities, difficulties, variant counts and last-tested dates, backed by
// nothing. Replacing it with the 7 real families from split_policy.py made
// every number real but lost the names, and the names carry the meaning: a
// judge understands "QR Quishing (Parking / Bill Overlay)" instantly and
// has to be walked through "document_fraud {qr_payload: tampered}".
//
// Both are true at once. Every scenario below is a real attack family plus a
// real mutation-parameter combination that backend/evaluation/split_policy.py
// actually declares and the generators actually emit. The name is editorial;
// the `family` and `match` are not. Case counts and detection outcomes are
// computed by matching real attack_cases.mutation_params against `match` --
// so a scenario that the generator has never produced shows zero cases
// rather than a fabricated number.
//
// `match` is a SUBSET of a declared combination: enough dimensions to
// identify it unambiguously within its family, no more. `split` records
// which side of the split policy the combination sits on -- held_out
// scenarios are the ones the defense was never trained against, which is
// where the interesting failures live.
//
// The 12 original names are all preserved (marked `legacyId`). The rest
// exist because split_policy.py declares 27 real combinations in total, and
// naming only 12 of them would leave two thirds of what this system really
// generates unnamed and invisible.

export const ATTACK_SCENARIOS = [
  // ---- transaction_fraud -------------------------------------------------
  {
    id: "low-value-probing",
    legacyId: "atk-low-value-probing",
    name: "Low-Value Probing Cascade",
    family: "transaction_fraud",
    split: "train",
    match: { amount: "low", velocity: "high" },
    description:
      "Many small transactions in quick succession, each individually under a static rule threshold, probing for what gets through.",
  },
  {
    id: "high-value-slow-drain",
    name: "High-Value Slow Drain",
    family: "transaction_fraud",
    split: "train",
    match: { amount: "high", velocity: "low" },
    description:
      "The inverse shape: few transactions, large amounts, paced slowly enough that velocity signals never accumulate.",
  },
  {
    id: "merchant-category-mismatch",
    name: "Merchant-Category Mismatch",
    family: "transaction_fraud",
    split: "train",
    match: { merchant_category: "mismatch" },
    description:
      "Spend at merchant categories inconsistent with the customer's established pattern.",
  },
  {
    id: "anomalous-timing-burst",
    legacyId: "atk-anomalous-timing-burst",
    name: "Off-Hours Timing Burst",
    family: "transaction_fraud",
    split: "held_out",
    match: { time_of_day: "off_hours", merchant_category: "new" },
    description:
      "The held-out evasion: mid amounts, moderate velocity, a new merchant category, off-hours — every dimension individually unremarkable, only the combination is not.",
  },

  // ---- account_takeover --------------------------------------------------
  {
    id: "ato-credential-stuffing",
    legacyId: "atk-ato-credential-stuffing",
    name: "Credential-Stuffing Account Takeover",
    family: "account_takeover",
    split: "train",
    match: { device: "new", location: "new" },
    description:
      "The classic loud takeover: unfamiliar device, unfamiliar location, immediately after a credential compromise.",
  },
  {
    id: "beneficiary-change-burst",
    name: "Beneficiary Swap + Burst Transfer",
    family: "account_takeover",
    split: "train",
    match: { beneficiary_change: true, velocity: "high" },
    description:
      "A new payee added, then drained fast — the payout leg of most successful takeovers.",
  },
  {
    id: "synthetic-behavior-drift",
    legacyId: "atk-synthetic-behavior-drift",
    name: "Synthetic Behavioral Drift (trusted device)",
    family: "account_takeover",
    split: "held_out",
    match: { device: "new", location: "trusted", velocity: "gradual_ramp" },
    description:
      "The held-out evasion: a new device from a location the customer already trusts, ramping gradually so the behavioural baseline re-calibrates around the attacker instead of flagging them.",
  },

  // ---- synthetic_identity ------------------------------------------------
  {
    id: "synthetic-identity-onboarding",
    legacyId: "atk-synthetic-identity-onboarding",
    name: "Synthetic Identity Onboarding",
    family: "synthetic_identity",
    split: "train",
    match: { account_age: "low", behavior_pattern: "normal_then_abnormal" },
    description:
      "A fabricated identity that onboards cleanly, behaves normally, then turns — thin account age and limited device history throughout.",
  },
  {
    id: "synthetic-identity-relationship-building",
    name: "Relationship-Building Synthetic Identity",
    family: "synthetic_identity",
    split: "held_out",
    match: { behavior_pattern: "gradual_ramp_relationship_building" },
    description:
      "The held-out evasion: the same fabricated identity, but it builds real-looking relationships first and ramps slowly, so there is no turn to detect.",
  },

  // ---- mule_network ------------------------------------------------------
  {
    id: "mule-trusted-device",
    legacyId: "atk-mule-trusted-device",
    name: "Trusted Device + Mule Network",
    family: "mule_network",
    split: "train",
    match: { hop_count: "2_3", shared_device: true },
    description:
      "A short mule chain where accounts share a device — the shared device is the strongest graph signal available.",
  },
  {
    id: "graph-fanout-mule",
    legacyId: "atk-graph-fanout-mule",
    name: "Fan-Out Mule Network Laundering",
    family: "mule_network",
    split: "held_out",
    match: { hop_count: "4_plus", beneficiaries: "distributed" },
    description:
      "The held-out evasion: four or more hops, no shared device, long irregular timing gaps, distributed beneficiaries — every structural giveaway removed.",
  },

  // ---- voice_scam --------------------------------------------------------
  {
    id: "voice-clone-ivr",
    legacyId: "atk-voice-clone-ivr",
    name: "Voice Clone IVR Takeover",
    family: "voice_scam",
    split: "train",
    match: { script_type: "bank_manager_verification" },
    description:
      "A cloned voice posing as a bank officer running a high-urgency verification script.",
  },
  {
    id: "voice-kyc-reverification",
    name: "KYC Re-verification Voice Scam",
    family: "voice_scam",
    split: "train",
    match: { script_type: "kyc_reverification" },
    description:
      "The compliance pretext: an urgent call claiming the customer's KYC must be re-verified now.",
  },
  {
    id: "deepfake-support-call",
    legacyId: "atk-deepfake-support-call",
    name: "Deepfake Family-Emergency Call",
    family: "voice_scam",
    split: "held_out",
    match: { script_type: "family_emergency", voice_characteristics: "cloned_customer" },
    description:
      "The held-out evasion: a clone of a specific registered customer's own voice, low urgency, framed as a family emergency — written to read as legitimate rather than alarming.",
  },

  // ---- document_fraud ----------------------------------------------------
  {
    id: "invoice-amount-tamper",
    legacyId: "atk-invoice-doc-fraud",
    name: "GenAI Invoice / Amount Forgery",
    family: "document_fraud",
    split: "train",
    match: { amount: "tampered" },
    description:
      "The printed invoice amount is edited while the QR keeps the original value — the classic forged-invoice pattern.",
  },
  {
    id: "invoice-beneficiary-tamper",
    name: "Beneficiary Substitution",
    family: "document_fraud",
    split: "train",
    match: { beneficiary: "tampered" },
    description: "The payee name on the face of the invoice is replaced; the QR still encodes the real one.",
  },
  {
    id: "quishing-poster",
    legacyId: "atk-quishing-poster",
    name: "QR Quishing (Parking / Bill Overlay)",
    family: "document_fraud",
    split: "train",
    match: { qr_payload: "tampered" },
    description:
      "The QR itself is swapped for a different, still well-formed invoice while everything printed stays internally consistent — the overlay-sticker attack.",
  },
  {
    id: "invoice-number-tamper",
    name: "Invoice-Number Tampering",
    family: "document_fraud",
    split: "train",
    match: { invoice_number: "tampered" },
    description: "The invoice reference is altered, breaking reconciliation against the real record.",
  },
  {
    id: "bank-account-tamper",
    name: "Payment Redirection (bank account)",
    family: "document_fraud",
    split: "train",
    match: { bank_account: "tampered" },
    description: "The printed bank account is replaced — payment redirection fraud, the highest-value document attack.",
  },
  {
    id: "multi-field-tamper",
    name: "Multi-Field Simultaneous Tampering",
    family: "document_fraud",
    split: "held_out",
    match: { amount: "tampered", beneficiary: "tampered", qr_payload: "tampered" },
    description:
      "The held-out evasion: amount, beneficiary and QR all altered together so no single cross-check disagrees.",
  },
  {
    id: "bank-account-qr-tamper",
    name: "Payment Redirection + QR Swap",
    family: "document_fraud",
    split: "held_out",
    match: { bank_account: "tampered", qr_payload: "tampered" },
    description:
      "The held-out evasion: both the bank account and the QR that would reveal it are swapped, while amounts and names stay untouched — only a bank-account-level cross-check catches this.",
  },

  // ---- phishing_scam -----------------------------------------------------
  {
    id: "genai-phishing-sms",
    legacyId: "atk-genai-phishing-sms",
    name: "GenAI Phishing / Smishing Wave (bank OTP)",
    family: "phishing_scam",
    split: "train",
    match: { impersonation_target: "bank_otp", channel: "sms" },
    description: "High-urgency SMS impersonating the bank to harvest a one-time passcode.",
  },
  {
    id: "delivery-sms",
    name: "Delivery-Notification Smishing",
    family: "phishing_scam",
    split: "train",
    match: { impersonation_target: "delivery", channel: "sms" },
    description: "The parcel-redelivery pretext — the highest-volume real smishing shape.",
  },
  {
    id: "tax-refund-email",
    name: "Tax-Refund Phishing",
    family: "phishing_scam",
    split: "train",
    match: { impersonation_target: "tax_refund", channel: "email" },
    description: "Email impersonating a tax authority promising a refund.",
  },
  {
    id: "tech-support-email",
    name: "Tech-Support Phishing",
    family: "phishing_scam",
    split: "train",
    match: { impersonation_target: "tech_support", channel: "email" },
    description: "Email impersonating IT or a software vendor to obtain credentials or remote access.",
  },
  {
    id: "employer-hr-lowurgency",
    name: "Employer / HR Low-Urgency Phish",
    family: "phishing_scam",
    split: "held_out",
    match: { impersonation_target: "employer_hr", urgency: "low" },
    description:
      "The held-out evasion: a novel impersonation target with deliberately calm wording, written to read as a routine internal email rather than an alarm.",
  },
  {
    id: "hinglish-lottery",
    name: "Code-Mixed Hinglish Lottery Scam",
    family: "phishing_scam",
    split: "held_out",
    match: { language: "hinglish" },
    description:
      "The held-out evasion: code-mixed Hindi/English text designed to slip past English-only keyword and classifier filters.",
  },
];

export const SCENARIOS_BY_FAMILY = ATTACK_SCENARIOS.reduce((acc, s) => {
  (acc[s.family] ??= []).push(s);
  return acc;
}, {});

export function getScenario(id) {
  return ATTACK_SCENARIOS.find((s) => s.id === id || s.legacyId === id) ?? null;
}

// True when every dimension this scenario constrains has the matching value
// in the case's real, fully-resolved mutation parameters.
export function scenarioMatches(scenario, resolvedParams) {
  if (!resolvedParams) return false;
  return Object.entries(scenario.match).every(
    ([k, v]) => String(resolvedParams[k]) === String(v),
  );
}
