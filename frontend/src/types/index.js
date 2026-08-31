// FraudShield domain types.
// These mirror the shape the future FastAPI backend is expected to return —
// the mock service layer in src/services/api produces exactly this shape,
// so swapping mocks for real HTTP calls later should not require UI changes.

export const ATTACK_CATEGORY_LABEL = {
  transaction: "Transaction",
  behavioral: "Behavioral",
  graph: "Graph / Mule Network",
  voice: "Voice Impersonation",
  text: "Phishing / SMS",
  qr: "QR / Quishing",
  document: "Invoice / Document",
  "account-takeover": "Account Takeover"
};
export const MODALITY_LABEL = {
  transaction: "Transaction Model",
  behavioral: "Behavioral Model",
  graph: "Graph Model",
  voice: "Voice Model",
  text: "Text / NLP Model",
  anomaly: "Anomaly Model",
  document: "Document / OCR Model",
  identity: "Identity / Face Model"
};
