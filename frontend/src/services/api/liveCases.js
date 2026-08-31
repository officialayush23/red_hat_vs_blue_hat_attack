// Real per-case scored evidence, straight out of Supabase -- this is what
// feeds the war-room attack animation.
//
// Every row here was written by backend/evaluation/supabase_results.py
// during a real evidence-gate run: `evaluation_results` holds the real
// per-case model signals, fused risk score, decision and correctness
// (14,020 rows as of 2026-08-31), and `attack_cases` holds the real
// generated case it scored (13,926 rows across all 7 attack families,
// written by backend/db/backfill_attack_cases.py).
//
// Nothing in this module is generated, seeded or randomised. It replaces
// services/api/evaluations.js's listEvaluationCases(), which called
// mockStore.js's getEvaluationCases() -- a seeded-random fabricator that
// invented attack names, model signals and risk scores wholesale.

import { supabase } from "@/lib/supabaseClient";

// Real family ids (backend/evaluation/split_policy.py's FAMILIES) mapped
// to the frontend's scope-category keys -- the exact same mapping
// backend/orchestration/agent_runner.py uses (FAMILY_TO_CATEGORY), kept
// identical on purpose so a category shown here means the same thing a
// category shown on the weakness cards does.
export const FAMILY_TO_CATEGORY = {
  transaction_fraud: "transaction",
  account_takeover: "account-takeover",
  synthetic_identity: "transaction",
  mule_network: "graph",
  voice_scam: "voice",
  document_fraud: "document",
  phishing_scam: "text",
};

export const FAMILY_LABEL = {
  transaction_fraud: "Transaction fraud",
  account_takeover: "Account takeover",
  synthetic_identity: "Synthetic identity",
  mule_network: "Mule-network laundering",
  voice_scam: "Voice-clone impersonation",
  document_fraud: "Document / invoice fraud",
  phishing_scam: "Phishing (text / GenAI)",
};

// Bonafide (genuinely legitimate) samples are scored by the same harness
// but are NOT attack cases, so they have no attack_cases row. Their real
// family is unambiguous from the case_id prefix the generators write
// (e.g. "phishing_bonafide_003", "voice_bonafide_012") -- read, not guessed.
const BONAFIDE_PREFIX_TO_FAMILY = {
  phishing_bonafide: "phishing_scam",
  voice_bonafide: "voice_scam",
  document_bonafide: "document_fraud",
  video_kyc_bonafide: "document_fraud",
};

function familyFromCaseId(caseId) {
  if (!caseId) return null;
  for (const [prefix, family] of Object.entries(BONAFIDE_PREFIX_TO_FAMILY)) {
    if (caseId.startsWith(prefix)) return family;
  }
  // Attack case ids are "<family>_<hash>" (backfill_attack_cases.py).
  const match = Object.keys(FAMILY_LABEL).find((f) => caseId.startsWith(f));
  return match ?? null;
}

// The four real outcomes of a scored case. `detected` in
// evaluation_results means "the harness got this case RIGHT" -- for a
// fraud case that's a block, for a legitimate case that's letting it
// through. Collapsing those two into one colour (as the old canvas did)
// hides the single most important number in the whole system: the false
// positives. So they are four distinct outcomes here.
export function outcomeOf(row) {
  const isFraud = row.actualLabel === "fraud";
  if (isFraud) return row.detected ? "blocked" : "missed";
  return row.detected ? "cleared" : "false_positive";
}

export const OUTCOME_META = {
  blocked: { label: "Blocked", blurb: "Real attack, correctly stopped at the Blue Team boundary" },
  missed: { label: "Missed", blurb: "Real attack that slipped past every detector and reached the system" },
  cleared: { label: "Cleared", blurb: "Legitimate traffic, correctly allowed through" },
  false_positive: { label: "False positive", blurb: "Legitimate traffic wrongly blocked -- real customer friction" },
};

function mapRow(result, caseRow) {
  const family =
    caseRow?.attack_family ?? familyFromCaseId(result.case_id) ?? "transaction_fraud";
  const signals = Array.isArray(result.model_signals) ? result.model_signals : [];
  const row = {
    id: result.id,
    caseId: result.case_id,
    runId: result.run_id,
    family,
    familyLabel: FAMILY_LABEL[family] ?? family,
    category: FAMILY_TO_CATEGORY[family] ?? "transaction",
    // fused_risk_score is persisted 0-100 by supabase_results.py.
    riskScore: typeof result.fused_risk_score === "number" ? result.fused_risk_score : 0,
    decision: result.decision,
    detected: result.detected === true,
    actualLabel: result.actual_label,
    evidence: Array.isArray(result.evidence) ? result.evidence : [],
    // Each signal is the real {model, score} the detector emitted.
    modelSignals: signals.map((s) => ({
      model: s.model ?? "unknown",
      score: typeof s.score === "number" ? s.score : null,
    })),
    splitPortion: caseRow?.split_portion ?? null,
    sourceDataset: caseRow?.source_dataset ?? null,
    createdAt: result.created_at,
  };
  row.outcome = outcomeOf(row);
  return row;
}

// GET /api/evaluations/cases?limit= -- the most recently scored real
// cases, newest first, joined to their attack_cases row for family and
// split. Two queries rather than a PostgREST embed because
// evaluation_results.case_id has no FK to attack_cases (bonafide samples
// deliberately have no attack_cases row), so an embed would silently drop
// every legitimate-traffic case and with it every false positive.
export async function listScoredCases(limit = 60) {
  const { data: results, error } = await supabase
    .from("evaluation_results")
    .select("id,run_id,case_id,model_signals,fused_risk_score,decision,detected,actual_label,evidence,created_at")
    .order("created_at", { ascending: false })
    .limit(limit);
  if (error) throw error;
  if (!results?.length) return [];

  const caseIds = [...new Set(results.map((r) => r.case_id).filter(Boolean))];
  let byId = {};
  if (caseIds.length) {
    const { data: cases, error: caseError } = await supabase
      .from("attack_cases")
      .select("id,attack_family,split_portion,source_dataset")
      .in("id", caseIds);
    if (caseError) throw caseError;
    byId = Object.fromEntries((cases ?? []).map((c) => [c.id, c]));
  }
  return results.map((r) => mapRow(r, byId[r.case_id]));
}

// A family-balanced sample, so the war-room lanes show every modality
// this system actually covers rather than whichever family happened to be
// scored most recently (evaluation_results is written per eval script, so
// the newest N rows are usually all one family). Still 100% real rows --
// this only changes WHICH real rows are read, never their content.
export async function listScoredCasesByFamily(perFamily = 8) {
  const families = Object.keys(FAMILY_LABEL);
  const batches = await Promise.all(
    families.map(async (family) => {
      const { data: cases, error } = await supabase
        .from("attack_cases")
        .select("id,attack_family,split_portion,source_dataset")
        .eq("attack_family", family)
        .limit(perFamily * 6);
      if (error) throw error;
      if (!cases?.length) return [];
      const ids = cases.map((c) => c.id);
      const { data: results, error: rErr } = await supabase
        .from("evaluation_results")
        .select("id,run_id,case_id,model_signals,fused_risk_score,decision,detected,actual_label,evidence,created_at")
        .in("case_id", ids)
        .order("created_at", { ascending: false })
        .limit(perFamily);
      if (rErr) throw rErr;
      const byId = Object.fromEntries(cases.map((c) => [c.id, c]));
      return (results ?? []).map((r) => mapRow(r, byId[r.case_id]));
    }),
  );
  return batches.flat();
}

// Real aggregate counters over the scored corpus -- computed by asking
// Postgres for exact counts (head:true, count:"exact"), never by counting
// a page of rows in the browser and extrapolating.
export async function getCorpusStats() {
  const countOf = async (build) => {
    const { count, error } = await build();
    if (error) throw error;
    return count ?? 0;
  };
  const base = () => supabase.from("evaluation_results").select("id", { count: "exact", head: true });
  const [total, fraudBlocked, fraudMissed, legitCleared, legitFlagged, cases] = await Promise.all([
    countOf(() => base()),
    countOf(() => base().eq("actual_label", "fraud").eq("detected", true)),
    countOf(() => base().eq("actual_label", "fraud").eq("detected", false)),
    countOf(() => base().eq("actual_label", "legit").eq("detected", true)),
    countOf(() => base().eq("actual_label", "legit").eq("detected", false)),
    countOf(() => supabase.from("attack_cases").select("id", { count: "exact", head: true })),
  ]);
  const fraudTotal = fraudBlocked + fraudMissed;
  const legitTotal = legitCleared + legitFlagged;
  return {
    scoredCases: total,
    attackCases: cases,
    fraudBlocked,
    fraudMissed,
    legitCleared,
    falsePositives: legitFlagged,
    recallPct: fraudTotal ? (fraudBlocked / fraudTotal) * 100 : 0,
    falsePositivePct: legitTotal ? (legitFlagged / legitTotal) * 100 : 0,
  };
}
