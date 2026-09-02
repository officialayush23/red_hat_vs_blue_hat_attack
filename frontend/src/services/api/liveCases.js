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

// NOTE the key `blocked` is historical and means DETECTED. supabase_results.py
// writes `detected = bool(predicted_fraud == is_fraud)` -- correctness at the
// detector's own calibrated threshold -- which is a different question from
// `decision`, the 0-100 band fusion.py assigns (approve <=30 / review <=60 /
// challenge <=80 / block). They genuinely diverge: 3,797 fraud rows are
// detected=true AND decision='approve', with fused_risk_score 9.35-25.0.
// Calling that "Blocked" claimed the system stopped attacks it in fact let
// through, and put "50.0 REVIEW / Blocked" on the same ticker line.
export const OUTCOME_META = {
  blocked: {
    label: "Detected",
    blurb: "Real attack, correctly identified as fraud by the detector -- see the decision column for what was then done with it",
  },
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
    // fused_risk_score is persisted 0-100 by supabase_results.py -- but it
    // is deliberately NULL for detectors whose score is not a calibrated
    // probability (autoencoder reconstruction error, and the fusion score
    // that includes it). Carried through as null, never coerced to 0: a
    // zero would render as "no risk", the opposite of "not measurable on
    // this scale".
    riskScore: typeof result.fused_risk_score === "number" ? result.fused_risk_score : null,
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
    // The ARTIFACT itself, not a description of it. Left off until
    // 2026-09-02, which meant anything filtering these rows for playable
    // media matched nothing and failed silently -- the panel simply never
    // rendered. CaseEvidence reads exactly these three.
    artifacts: caseRow?.artifacts ?? null,
    mutationParams: caseRow?.mutation_params ?? null,
    transactionSequence: caseRow?.transaction_sequence ?? null,
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
// Same counters, scoped to ONE run.
//
// 2026-09-02: the war room's tiles showed corpus-wide totals on a live run
// page -- 27,576 detected over 30,102 scored -- so a run adding a few hundred
// rows moved them by a fraction of a percent and they read as frozen. "Live"
// has to mean live for everything on the screen, or it means nothing.
//
// Scoped by TIME, not by run id, because no link exists: evaluation_results
// .run_id points at evaluation_runs, whose config carries {model, n_cases}
// and no campaign id, so a defense run cannot be joined to the eval rows it
// produced. Rows written since the run started ARE that run's rows as long as
// one run is in flight -- which is the case here, and the sub-line says so
// rather than pretending to a precision this cannot have. Threading the
// campaign id through supabase_results.py is the real fix; this is the honest
// version that needs no backend deploy.
// The eval runs a defense run produced. Empty for runs that predate
// FRAUDSHIELD_CAMPAIGN_ID (2026-09-02), which is why every caller falls back
// to the time window rather than showing a confident zero.
export async function getEvalRunIds(campaignId) {
  if (!campaignId) return [];
  const { data, error } = await supabase
    .from("evaluation_runs")
    .select("id")
    .eq("config->>campaign_id", campaignId);
  if (error) throw error;
  return (data ?? []).map((r) => r.id);
}

// Real per-case rows for ONE defense run -- the artifacts it actually fed the
// detectors, joined to their cases so the evidence viewer can play them.
export async function listRunCases(campaignId, limit = 60) {
  const runIds = await getEvalRunIds(campaignId);
  if (!runIds.length) return [];
  const { data: results, error } = await supabase
    .from("evaluation_results")
    .select("id,run_id,case_id,model_signals,fused_risk_score,decision,detected,actual_label,evidence,created_at")
    .in("run_id", runIds)
    .order("created_at", { ascending: false })
    .limit(limit);
  if (error) throw error;
  const ids = [...new Set((results ?? []).map((r) => r.case_id))];
  if (!ids.length) return [];
  const { data: cases, error: cErr } = await supabase
    .from("attack_cases")
    .select("id,attack_family,mutation_params,split_portion,is_fraud,artifacts,transaction_sequence,customer_id")
    .in("id", ids);
  if (cErr) throw cErr;
  const byId = Object.fromEntries((cases ?? []).map((c) => [c.id, c]));
  return (results ?? []).map((r) => mapRow(r, byId[r.case_id]));
}

export async function getRunStats(sinceIso, campaignId) {
  if (!sinceIso && !campaignId) return null;
  // Prefer the real join. The time window is the fallback for runs written
  // before evaluation_runs.config carried a campaign_id -- correct only while
  // one run is in flight, which is why it is not the first choice any more.
  const runIds = await getEvalRunIds(campaignId);
  // THE TIME-WINDOW FALLBACK NEEDS AN ACTUAL TIME.
  //
  // campaignId comes straight from the URL, so it is present on the very
  // first render; sinceIso comes from the run row, which has not loaded
  // yet. The guard above passes on campaignId alone, and a run that has
  // not written any evaluation_runs row yet has no runIds -- so this fell
  // through to the time window and issued
  //     ?select=id&created_at=gte.undefined
  // six times per poll, every one a 400. Promise.all then rejected, the
  // query returned no data, and the war room's per-run tiles sat at 0
  // looking like a data problem rather than a malformed request.
  if (!runIds.length && !sinceIso) return null;
  const scopedBy = runIds.length ? "campaign" : "time";
  const countOf = async (build) => {
    const { count, error } = await build();
    if (error) throw error;
    return count ?? 0;
  };
  const base = () => {
    const q = supabase.from("evaluation_results").select("id", { count: "exact", head: true });
    return runIds.length ? q.in("run_id", runIds) : q.gte("created_at", sinceIso);
  };
  const [total, fraudDetected, fraudMissed, fraudBlockedOutright, legitCleared, legitFlagged] =
    await Promise.all([
      countOf(() => base()),
      countOf(() => base().eq("actual_label", "fraud").eq("detected", true)),
      countOf(() => base().eq("actual_label", "fraud").eq("detected", false)),
      countOf(() => base().eq("actual_label", "fraud").eq("decision", "block")),
      countOf(() => base().eq("actual_label", "legit").eq("detected", true)),
      countOf(() => base().eq("actual_label", "legit").eq("detected", false)),
    ]);
  const fraudTotal = fraudDetected + fraudMissed;
  const legitTotal = legitCleared + legitFlagged;
  return {
    scopedBy,
    scoredCases: total,
    fraudDetected,
    fraudBlockedOutright,
    fraudMissed,
    legitCleared,
    falsePositives: legitFlagged,
    detectionPct: fraudTotal ? (fraudDetected / fraudTotal) * 100 : 0,
    blockedPct: fraudTotal ? (fraudBlockedOutright / fraudTotal) * 100 : 0,
    falsePositivePct: legitTotal ? (legitFlagged / legitTotal) * 100 : 0,
  };
}

export async function getCorpusStats() {
  const countOf = async (build) => {
    const { count, error } = await build();
    if (error) throw error;
    return count ?? 0;
  };
  const base = () => supabase.from("evaluation_results").select("id", { count: "exact", head: true });
  // fraudDetected and fraudBlockedOutright are DIFFERENT questions and the UI
  // must not conflate them -- see the OUTCOME_META note above. Both are asked
  // for so the tile can state the detection rate and the block rate together
  // rather than showing one under the other's name.
  const [total, fraudDetected, fraudMissed, fraudBlockedOutright, legitCleared, legitFlagged, cases] =
    await Promise.all([
      countOf(() => base()),
      countOf(() => base().eq("actual_label", "fraud").eq("detected", true)),
      countOf(() => base().eq("actual_label", "fraud").eq("detected", false)),
      countOf(() => base().eq("actual_label", "fraud").eq("decision", "block")),
      countOf(() => base().eq("actual_label", "legit").eq("detected", true)),
      countOf(() => base().eq("actual_label", "legit").eq("detected", false)),
      countOf(() => supabase.from("attack_cases").select("id", { count: "exact", head: true })),
    ]);
  const fraudTotal = fraudDetected + fraudMissed;
  const legitTotal = legitCleared + legitFlagged;
  return {
    scoredCases: total,
    attackCases: cases,
    fraudDetected,
    fraudBlockedOutright,
    fraudMissed,
    legitCleared,
    falsePositives: legitFlagged,
    detectionPct: fraudTotal ? (fraudDetected / fraudTotal) * 100 : 0,
    blockedPct: fraudTotal ? (fraudBlockedOutright / fraudTotal) * 100 : 0,
    falsePositivePct: legitTotal ? (legitFlagged / legitTotal) * 100 : 0,
  };
}
