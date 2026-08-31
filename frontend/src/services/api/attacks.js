// Real attack-taxonomy reads. Nothing in this module is invented.
//
// Structure (families, mutation dimensions, which combinations are
// training-allowed vs. held-out-only) comes from
// data/attackFamilies.generated.js, which backend/tools/export_attack_taxonomy.py
// writes mechanically from backend/evaluation/split_policy.py's FAMILIES --
// this project's single source of truth for the split policy.
//
// Volume and outcome numbers come from Supabase: real generated cases in
// attack_cases, real scored results in evaluation_results.
//
// What this replaces: data/attackCatalog.js, a hand-written list of 12
// invented attacks ("Trusted Device + Mule Network", "QR Quishing
// (Parking / Bill Overlay)", "Deepfake Support-Call Impersonation") that
// matched none of the 7 families this backend actually generates and
// scores, wrapped in mockStore.js fabricators for the case detail. A judge
// clicking Attack Library was being shown attacks that do not exist.

import { supabase } from "@/lib/supabaseClient";
import { ATTACK_FAMILIES, getFamily } from "@/data/attackFamilies.generated";

// evaluation_results.case_id is "<family>_<hash>" for attack cases and
// "<family-ish>_bonafide_<n>" for legitimate samples (both written by the
// generators). Filtering on that prefix is how a family's real results are
// found: evaluation_results has no attack_family column and no FK to
// attack_cases, because bonafide samples deliberately have no case row.
function prefixFilter(family) {
  // PostgREST `like` uses * for %. Underscores in the family id are left
  // as-is: they are single-character wildcards in SQL LIKE, which can only
  // match the literal underscore that is actually there, since no two
  // family ids differ by one character in those positions.
  return `${family}*`;
}

async function countWhere(build) {
  const { count, error } = await build();
  if (error) throw error;
  return count ?? 0;
}

// Real per-family volume + outcome counters.
//
// NOTE ON UNITS, which matters for honesty: evaluation_results holds one
// row per (case, evaluation run) pair, so a case scored by three separate
// evidence-gate runs contributes three rows. These counters are therefore
// SCORED RESULTS, not distinct cases -- verified directly against the
// live table (case synthetic_identity_001321f3577e appears more than
// once). `generatedCases` below is the distinct-case number, from
// attack_cases. The UI must not label a result count as a case count.
export async function getFamilyStats(family) {
  const results = () =>
    supabase.from("evaluation_results").select("id", { count: "exact", head: true })
      .like("case_id", prefixFilter(family));
  const cases = () =>
    supabase.from("attack_cases").select("id", { count: "exact", head: true })
      .eq("attack_family", family);

  const [generatedCases, trainCases, heldOutCases, scoredResults, blocked, missed, falsePositives, cleared] =
    await Promise.all([
      countWhere(cases),
      countWhere(() => cases().eq("split_portion", "train")),
      countWhere(() => cases().eq("split_portion", "held_out")),
      countWhere(results),
      countWhere(() => results().eq("actual_label", "fraud").is("detected", true)),
      countWhere(() => results().eq("actual_label", "fraud").is("detected", false)),
      countWhere(() => results().eq("actual_label", "legit").is("detected", false)),
      countWhere(() => results().eq("actual_label", "legit").is("detected", true)),
    ]);

  const fraudResults = blocked + missed;
  const legitResults = cleared + falsePositives;
  return {
    family,
    generatedCases,
    trainCases,
    heldOutCases,
    scoredResults,
    blocked,
    missed,
    cleared,
    falsePositives,
    // Detection rate over every recorded fraud result for this family.
    // Null (not zero) when nothing has been scored yet -- document_fraud
    // is in exactly that state: 120 real generated cases, 0 scored
    // results, because its Colab evidence-gate run was never merged back.
    detectionRate: fraudResults ? (blocked / fraudResults) * 100 : null,
    falsePositiveRate: legitResults ? (falsePositives / legitResults) * 100 : null,
    evaluated: fraudResults > 0,
  };
}

// GET /api/attacks — the 7 real families with their real numbers attached.
export async function listAttacks() {
  const stats = await Promise.all(ATTACK_FAMILIES.map((f) => getFamilyStats(f.id)));
  const byFamily = Object.fromEntries(stats.map((s) => [s.family, s]));
  return ATTACK_FAMILIES.map((f) => ({ ...f, stats: byFamily[f.id] }));
}

// GET /api/attacks/:id
export async function getAttack(id) {
  const family = getFamily(id);
  if (!family) return null;
  return { ...family, stats: await getFamilyStats(id) };
}

// GET /api/attacks/:id/combinations — the mutation-parameter combinations
// that were ACTUALLY generated for this family, with how many real cases
// each produced. This is the empirical counterpart to the family's
// declared trainingAllowed/heldOutOnly lists: it shows what the generator
// really emitted, not only what the policy permits.
export async function getGeneratedCombinations(family, sampleSize = 1000) {
  const { data, error } = await supabase
    .from("attack_cases")
    .select("mutation_params,split_portion")
    .eq("attack_family", family)
    .limit(sampleSize);
  if (error) throw error;

  const buckets = new Map();
  for (const row of data ?? []) {
    const params = row.mutation_params ?? {};
    // resolved_levels is the generator's own record of the fully-resolved
    // combination (declared combo + family defaults) -- prefer it when
    // present, since that is what was really rendered into the case.
    const combo = params.resolved_levels ?? params;
    const key = JSON.stringify(
      Object.fromEntries(
        Object.entries(combo)
          .filter(([k]) => k !== "extra_fields" && k !== "resolved_levels")
          .sort(([a], [b]) => a.localeCompare(b)),
      ),
    );
    if (!buckets.has(key)) buckets.set(key, { combo: JSON.parse(key), train: 0, heldOut: 0, total: 0 });
    const b = buckets.get(key);
    b.total += 1;
    if (row.split_portion === "held_out") b.heldOut += 1;
    else b.train += 1;
  }
  return [...buckets.values()].sort((a, b) => b.total - a.total);
}

// GET /api/attacks/:id/cases — real generated cases for this family, each
// paired with its real scored result where one exists. A case with no
// result is returned with result:null rather than being hidden: "generated
// but never evaluated" is real, important information (it is the entire
// story for document_fraud right now).
export async function getAttackCases(family, limit = 12) {
  const { data: cases, error } = await supabase
    .from("attack_cases")
    .select("id,attack_family,mutation_params,split_portion,signals_expected,source_dataset,is_fraud,customer_id,created_at")
    .eq("attack_family", family)
    .order("created_at", { ascending: false })
    .limit(limit);
  if (error) throw error;
  if (!cases?.length) return [];

  const ids = cases.map((c) => c.id);
  const { data: results, error: rErr } = await supabase
    .from("evaluation_results")
    .select("case_id,model_signals,fused_risk_score,decision,detected,actual_label,evidence,created_at")
    .in("case_id", ids)
    .order("created_at", { ascending: false });
  if (rErr) throw rErr;

  // Newest result per case (the query is already newest-first).
  const latest = {};
  for (const r of results ?? []) if (!latest[r.case_id]) latest[r.case_id] = r;

  return cases.map((c) => {
    const r = latest[c.id] ?? null;
    return {
      id: c.id,
      family: c.attack_family,
      mutationParams: c.mutation_params ?? {},
      splitPortion: c.split_portion,
      signalsExpected: c.signals_expected ?? [],
      sourceDataset: c.source_dataset,
      isFraud: c.is_fraud,
      customerId: c.customer_id,
      createdAt: c.created_at,
      result: r
        ? {
            modelSignals: Array.isArray(r.model_signals) ? r.model_signals : [],
            riskScore: r.fused_risk_score ?? 0,
            decision: r.decision,
            detected: r.detected === true,
            actualLabel: r.actual_label,
            evidence: Array.isArray(r.evidence) ? r.evidence : [],
            scoredAt: r.created_at,
          }
        : null,
    };
  });
}

// GET /api/attacks/:id/representative-case — the highest-signal real case
// this family has: prefer a real MISS (a held-out attack that got through,
// the most instructive case there is), else the highest-risk real block.
export async function getRepresentativeCase(family) {
  const cases = await getAttackCases(family, 40);
  const scored = cases.filter((c) => c.result);
  if (!scored.length) return cases[0] ?? null;
  const miss = scored.find((c) => c.result.actualLabel === "fraud" && !c.result.detected);
  if (miss) return miss;
  return scored.sort((a, b) => b.result.riskScore - a.result.riskScore)[0];
}

// Real per-category totals for the dashboard breakdown chart, aggregated
// from the same real family stats (categories are the frontend scope keys;
// two families map onto "transaction", so they sum).
export async function getCategoryBreakdown() {
  const families = await listAttacks();
  const byCategory = new Map();
  for (const f of families) {
    const entry = byCategory.get(f.category) ?? {
      category: f.category,
      generatedCases: 0,
      blocked: 0,
      missed: 0,
      falsePositives: 0,
      families: [],
    };
    entry.generatedCases += f.stats.generatedCases;
    entry.blocked += f.stats.blocked;
    entry.missed += f.stats.missed;
    entry.falsePositives += f.stats.falsePositives;
    entry.families.push(f.label);
    byCategory.set(f.category, entry);
  }
  return [...byCategory.values()].map((e) => ({
    ...e,
    detectionRate: e.blocked + e.missed ? (e.blocked / (e.blocked + e.missed)) * 100 : null,
  }));
}
