// The customer universe -- the 21 real synthetic customers in Supabase's
// synthetic_customers table (generate/synthetic_customers.py), and which
// real attack cases targeted each of them.
//
// Nothing in this app read this table before. It is the missing half of
// the story: the attack library says what was thrown, this says at whom,
// and attack_cases.customer_id is the real join between them
// (generate/inject_attacks.py assigns a customer round-robin per case;
// 6,860 of 19,806 cases currently carry one).

import { supabase } from "@/lib/supabaseClient";

function mapCustomer(row) {
  const meta = row.metadata ?? {};
  const devices = Array.isArray(row.device_history) ? row.device_history : [];
  return {
    id: row.id,
    name: meta.name ?? row.id,
    accountAgeDays: row.account_age_days ?? null,
    relationshipCount: row.relationship_count ?? null,
    trustedBeneficiaries: Array.isArray(meta.trusted_beneficiaries) ? meta.trusted_beneficiaries : [],
    devices: devices.map((d) => ({
      device: d.device ?? "unknown device",
      trusted: d.trusted === true,
      firstSeenDaysAgo: d.first_seen_days_ago ?? null,
    })),
    // Reference assets the media generators registered for this identity --
    // a real registered voice sample is what makes a "clone of this
    // specific customer" attack meaningful rather than generic TTS.
    voiceRef: row.voice_ref ?? null,
    photoRef: row.photo_ref ?? null,
    videoRef: row.video_ref ?? null,
    kycDocumentRef: row.kyc_document_ref ?? null,
    createdAt: row.created_at,
  };
}

// GET /api/customers -- every customer, with the real number of attack
// cases aimed at them, per family.
export async function listCustomers() {
  const { data, error } = await supabase
    .from("synthetic_customers")
    .select("*")
    .order("id");
  if (error) throw error;
  const customers = (data ?? []).map(mapCustomer);

  // Paginated, because PostgREST caps a single response at 1,000 rows
  // regardless of .limit() -- a plain .limit(10000) silently returned the
  // first 1,000 and made 18 of the 21 customers show "0 cases" when they
  // really have hundreds each. Pages until a short page comes back.
  const cases = [];
  const PAGE = 1000;
  for (let from = 0; ; from += PAGE) {
    const { data, error: cErr } = await supabase
      .from("attack_cases")
      .select("id,customer_id,attack_family,split_portion")
      .not("customer_id", "is", null)
      .order("id")
      .range(from, from + PAGE - 1);
    if (cErr) throw cErr;
    cases.push(...(data ?? []));
    if (!data || data.length < PAGE) break;
    if (from > 50_000) break; // hard stop, never spin forever on a growing table
  }

  const byCustomer = {};
  for (const c of cases) {
    const entry = (byCustomer[c.customer_id] ??= { total: 0, families: {} });
    entry.total += 1;
    entry.families[c.attack_family] = (entry.families[c.attack_family] ?? 0) + 1;
  }

  return customers.map((c) => ({
    ...c,
    targeting: byCustomer[c.id] ?? { total: 0, families: {} },
  }));
}

export async function getCustomer(id) {
  if (!id) return null;
  const { data, error } = await supabase.from("synthetic_customers").select("*").eq("id", id).maybeSingle();
  if (error) throw error;
  return data ? mapCustomer(data) : null;
}

// Real cases aimed at one customer, each with its latest real score.
export async function getCustomerCases(customerId, limit = 25) {
  if (!customerId) return [];
  // Three targeted reads rather than one recency-ordered read.
  //
  // A customer can have 300+ linked cases, and the most recently generated
  // ones are training-split tabular cases -- which are deliberately never
  // adversarially scored and carry no artifact. Fetching the newest N and
  // sorting afterwards therefore produced 25 rows all reading "not scored"
  // with nothing to look at, on a page whose entire purpose is showing the
  // real artifact. So the interesting slices are asked for by name:
  // media-family cases (they have the invoice / audio / message), held-out
  // cases (they are the ones actually scored), and finally anything else
  // to fill the list out.
  const MEDIA_FAMILIES = ["voice_scam", "document_fraud", "phishing_scam"];
  const columns =
    "id,attack_family,split_portion,mutation_params,artifacts,transaction_sequence,is_fraud,created_at";
  const base = () =>
    supabase.from("attack_cases").select(columns).eq("customer_id", customerId);

  const [media, heldOut, recent] = await Promise.all([
    base().in("attack_family", MEDIA_FAMILIES).limit(limit),
    base().eq("split_portion", "held_out").limit(limit),
    base().order("created_at", { ascending: false }).limit(limit),
  ]);
  const error = media.error || heldOut.error || recent.error;
  if (error) throw error;

  const seen = new Set();
  const cases = [];
  for (const row of [...(media.data ?? []), ...(heldOut.data ?? []), ...(recent.data ?? [])]) {
    if (seen.has(row.id)) continue;
    seen.add(row.id);
    cases.push(row);
  }
  if (!cases.length) return [];

  const ids = cases.map((c) => c.id);
  const { data: results, error: rErr } = await supabase
    .from("evaluation_results")
    .select("case_id,fused_risk_score,decision,detected,actual_label,evidence,model_signals,created_at")
    .in("case_id", ids)
    .order("created_at", { ascending: false });
  if (rErr) throw rErr;
  const latest = {};
  for (const r of results ?? []) if (!latest[r.case_id]) latest[r.case_id] = r;

  const mapped = cases.map((c) => ({
    id: c.id,
    family: c.attack_family,
    splitPortion: c.split_portion,
    mutationParams: c.mutation_params ?? {},
    artifacts: c.artifacts ?? {},
    transactionSequence: Array.isArray(c.transaction_sequence) ? c.transaction_sequence : [],
    isFraud: c.is_fraud,
    // A case carrying a real artifact (an invoice image, a call recording,
    // a message) is the one worth looking at first -- that is the whole
    // point of this view.
    hasArtifact: Object.keys(c.artifacts ?? {}).length > 0,
    result: latest[c.id]
      ? {
          riskScore: typeof latest[c.id].fused_risk_score === "number" ? latest[c.id].fused_risk_score : null,
          decision: latest[c.id].decision,
          detected: latest[c.id].detected === true,
          actualLabel: latest[c.id].actual_label,
          evidence: latest[c.id].evidence ?? [],
          modelSignals: latest[c.id].model_signals ?? [],
        }
      : null,
  }));

  return mapped
    .sort((a, b) => {
      const rank = (x) => (x.result ? 0 : 1) * 2 + (x.hasArtifact ? 0 : 1);
      return rank(a) - rank(b);
    })
    .slice(0, limit);
}

// One case with everything needed to SHOW it: the real artifact (audio,
// invoice image, message text), the real transaction sequence, the real
// mutation parameters, the customer it targeted, and its latest real score.
export async function getCaseEvidence(caseId) {
  if (!caseId) return null;
  const { data: c, error } = await supabase
    .from("attack_cases")
    .select("*")
    .eq("id", caseId)
    .maybeSingle();
  if (error) throw error;
  if (!c) return null;

  const { data: results, error: rErr } = await supabase
    .from("evaluation_results")
    .select("case_id,fused_risk_score,decision,detected,actual_label,evidence,model_signals,created_at,run_id")
    .eq("case_id", caseId)
    .order("created_at", { ascending: false });
  if (rErr) throw rErr;

  const customer = c.customer_id ? await getCustomer(c.customer_id) : null;

  return {
    id: c.id,
    family: c.attack_family,
    splitPortion: c.split_portion,
    sourceDataset: c.source_dataset,
    signalsExpected: c.signals_expected ?? [],
    mutationParams: c.mutation_params ?? {},
    artifacts: c.artifacts ?? {},
    transactionSequence: Array.isArray(c.transaction_sequence) ? c.transaction_sequence : [],
    isFraud: c.is_fraud,
    generatedBy: c.generated_by,
    createdAt: c.created_at,
    customer,
    // Every scored result for this case, newest first -- a case scored by
    // three evidence-gate runs really does have three results, and showing
    // one while implying it is the only one would misrepresent the record.
    results: (results ?? []).map((r) => ({
      runId: r.run_id,
      riskScore: typeof r.fused_risk_score === "number" ? r.fused_risk_score : null,
      decision: r.decision,
      detected: r.detected === true,
      actualLabel: r.actual_label,
      evidence: Array.isArray(r.evidence) ? r.evidence : [],
      modelSignals: Array.isArray(r.model_signals) ? r.model_signals : [],
      scoredAt: r.created_at,
    })),
  };
}
