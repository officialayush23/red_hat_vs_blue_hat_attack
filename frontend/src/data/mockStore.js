import { ATTACK_CATALOG } from "@/data/attackCatalog";
import { daysAgoIso, mulberry32, pick, seededInt } from "@/data/seed";
const rand = mulberry32(20260829);
const SCOPES = [["transaction", "behavioral", "graph"], ["voice", "text", "qr"], ["document", "account-takeover", "graph"], ["transaction", "graph", "account-takeover"], ["behavioral", "voice", "text", "qr", "document"]];
const OBJECTIVES = ["Harden the fraud defense against adaptive payment fraud.", "Stress-test mule-network detection ahead of the festive payment surge.", "Validate resilience against GenAI voice-clone social engineering.", "Probe phishing + quishing coverage across the SMS and QR channels.", "Re-baseline account-takeover detection after the last credential leak."];
function buildRun(index, id) {
  const scope = SCOPES[index % SCOPES.length];
  const attacksTested = [10000, 5000, 1000, 10000, 500][index % 5];
  const before = 88 + seededInt(rand, 0, 4);
  const after = Math.min(99.4, before + 3 + seededInt(rand, 2, 6));
  const missed = Math.max(0, Math.round(attacksTested * (100 - after) / 100));
  const caught = attacksTested - missed;
  const fp = seededInt(rand, 12, 90);
  const status = index === 0 ? "completed" : index === 4 ? "running" : "completed";
  return {
    id,
    objective: OBJECTIVES[index % OBJECTIVES.length],
    scope,
    severity: index % 4 === 3 ? "adaptive" : ["low", "medium", "high", "adaptive"][index % 4],
    scenarioCount: attacksTested,
    status,
    createdAt: daysAgoIso(index * 2 + 1, seededInt(rand, 0, 12)),
    completedAt: status === "completed" ? daysAgoIso(index * 2, seededInt(rand, 0, 6)) : undefined,
    currentIteration: status === "running" ? 2 : 3,
    totalIterations: 3,
    attacksTested,
    attacksCaught: caught,
    attacksMissed: missed,
    falsePositives: fp,
    detectionRateBefore: Number(before.toFixed(1)),
    detectionRateAfter: Number(after.toFixed(1)),
    weakestCategory: pick(rand, scope),
    improvementPct: Number((after - before).toFixed(1)),
    precision: Number((0.9 + rand() * 0.06).toFixed(3)),
    recall: Number((after / 100).toFixed(3)),
    f1: Number((0.9 + rand() * 0.05).toFixed(3)),
    prAuc: Number((0.93 + rand() * 0.05).toFixed(3)),
    attackCoveragePct: Number((82 + seededInt(rand, 0, 14)).toFixed(1))
  };
}
export const RUNS = [buildRun(0, "DR-024"), buildRun(1, "DR-023"), buildRun(2, "DR-022"), buildRun(3, "DR-021"), buildRun(4, "DR-020")];
export const LATEST_RUN = RUNS[0];
const AGENT_STEP_TEMPLATES = [{
  agent: "orchestrator",
  label: "Orchestrator Agent",
  detail: r => `Goal received: "${r.objective}"`,
  observation: r => `New defense run requested — objective: "${r.objective}"`,
  decision: () => "Decompose the goal and delegate discovery to the Threat Research Agent",
  tool: () => "—",
  action: r => `Initialize run across ${r.scope.length} scope categories`,
  result: r => `Run scope locked: ${r.scope.join(", ")}`,
  next: () => "Hand off to Threat Research Agent"
}, {
  agent: "threat-research",
  label: "Threat Research Agent",
  detail: r => `Identified relevant attack families across ${r.scope.length} scopes`,
  observation: () => "No current-run coverage on file for this scope yet",
  decision: () => "Pull candidate attack families from the taxonomy for this scope",
  tool: () => "Attack taxonomy · prior-run weaknesses",
  action: r => `Search attack families across ${r.scope.join(", ")}`,
  result: () => "Candidate attack families shortlisted and ranked by expected fragility",
  next: () => "Hand off to Attack Planner Agent"
}, {
  agent: "attack-planner",
  label: "Attack Planner Agent",
  detail: () => "Selected high-risk scenarios and prioritized by expected fragility",
  observation: () => "Multiple candidate attack families available",
  decision: () => "Prioritize the scenarios most likely to expose an undetected weakness",
  tool: () => "Attack Planner",
  action: () => "Select scenarios and set generation parameters (severity, variant count)",
  result: () => "Attack plan finalized",
  next: () => "Hand off to Attack Generator"
}, {
  agent: "attack-generator",
  label: "Attack Generator",
  detail: r => `Generated ${r.scenarioCount.toLocaleString()} adversarial cases (CTGAN / TimeGAN)`,
  observation: () => "Attack plan approved by the orchestrator",
  decision: () => "Synthesize adversarial cases at the requested scale",
  tool: () => "CTGAN · TimeGAN · programmatic mutation",
  action: r => `Generate ${r.scenarioCount.toLocaleString()} adversarial cases`,
  result: r => `${r.scenarioCount.toLocaleString()} scenarios created`,
  next: () => "Send scenarios to the Blue Team"
}, {
  agent: "blue-team",
  label: "Blue Team",
  detail: () => "Evaluating defense across transaction, behavioral, graph, voice, text and document models",
  observation: () => "New batch of adversarial scenarios received",
  decision: () => "Score every scenario across all specialist detection models",
  tool: () => "XGBoost · Transformer · GraphSAGE-GAT · DistilBERT · Wav2Vec2 · OCR",
  action: () => "Evaluate transaction, behavioral, graph, voice, text and document signals",
  result: r => `${r.attacksCaught.toLocaleString()} caught · ${r.attacksMissed.toLocaleString()} missed`,
  next: () => "Hand off to Evaluation Agent"
}, {
  agent: "evaluation",
  label: "Evaluation Agent",
  detail: r => `Found weakness in ${r.weakestCategory.replace("-", " ")} scenarios`,
  observation: r => `Detection rate is lowest on ${r.weakestCategory.replace("-", " ")} scenarios`,
  decision: () => "Flag this as the run's primary weakness",
  tool: () => "Evaluation Agent — precision / recall / FPR / FNR / attack coverage",
  action: () => "Compare detected vs. missed cases and extract the common pattern",
  result: r => `Weakness identified: ${r.weakestCategory.replace("-", " ")}`,
  next: () => "Hand off to Adaptation Agent"
}, {
  agent: "mutation-engine",
  label: "Adaptation Agent",
  detail: () => "Generating harder variants targeting the discovered weakness",
  observation: () => "Weakness confirmed: a gradual, low-signal pattern the models underweight",
  decision: () => "Generate a harder follow-up scenario that specifically targets this blind spot",
  tool: () => "Mutation Engine",
  action: () => "Vary timing, amount and relationship structure",
  result: () => "Harder follow-up scenario created",
  next: () => "Loop back to Attack Generator for re-test"
}];
export function getAgentSteps(runId) {
  const run = RUNS.find(r => r.id === runId) ?? LATEST_RUN;
  const doneCount = run.status === "running" ? 5 : run.status === "queued" ? 0 : AGENT_STEP_TEMPLATES.length;
  return AGENT_STEP_TEMPLATES.map((tpl, i) => ({
    id: `${runId}-step-${i}`,
    runId,
    agent: tpl.agent,
    label: tpl.label,
    detail: tpl.detail(run),
    observation: tpl.observation(run),
    decision: tpl.decision(run),
    tool: tpl.tool(run),
    action: tpl.action(run),
    result: tpl.result(run),
    next: tpl.next(run),
    status: i < doneCount ? "done" : i === doneCount ? "running" : "pending",
    timestamp: daysAgoIso(0, AGENT_STEP_TEMPLATES.length - i)
  }));
}
function modelSignalsFor(attackId) {
  const attack = ATTACK_CATALOG.find(a => a.id === attackId) ?? ATTACK_CATALOG[0];
  const base = [{
    model: "XGBoost — Transaction",
    modality: "transaction",
    score: Number((0.4 + rand() * 0.5).toFixed(2)),
    triggered: true,
    note: "Amount/velocity pattern deviates from account baseline"
  }, {
    model: "Transformer — Behavioral Sequence",
    modality: "behavioral",
    score: Number((0.4 + rand() * 0.5).toFixed(2)),
    triggered: true,
    note: "Session/navigation sequence diverges from historical profile"
  }, {
    model: "GraphSAGE — Mule Network",
    modality: "graph",
    score: Number((0.3 + rand() * 0.6).toFixed(2)),
    triggered: true,
    note: "Beneficiary sits within 2 hops of known mule cluster"
  }, {
    model: "DistilBERT — Phishing / Text",
    modality: "text",
    score: Number((0.05 + rand() * 0.2).toFixed(2)),
    triggered: false,
    note: "No phishing-indicative language in associated messages"
  }, {
    model: "Autoencoder — Anomaly",
    modality: "anomaly",
    score: Number((0.4 + rand() * 0.5).toFixed(2)),
    triggered: true,
    note: "Reconstruction error above the 98th percentile band"
  }];
  if (attack.modalities.includes("voice")) {
    base.push({
      model: "Wav2Vec2 — Voice Spoof",
      modality: "voice",
      score: Number((0.3 + rand() * 0.6).toFixed(2)),
      triggered: true,
      note: "Spectral artifacts consistent with synthetic voice generation"
    });
  }
  if (attack.modalities.includes("document")) {
    base.push({
      model: "OCR / Document Verification",
      modality: "document",
      score: Number((0.2 + rand() * 0.6).toFixed(2)),
      triggered: rand() > 0.4,
      note: "Font/metadata inconsistency detected against template baseline"
    });
  }
  return base;
}
function fuseRisk(signals) {
  const weighted = signals.reduce((acc, s) => acc + s.score * (s.triggered ? 1.1 : 0.6), 0);
  return Math.min(0.99, Number((weighted / signals.length / 1.15).toFixed(2)));
}
export function getCaseForAttack(attackId) {
  const attack = ATTACK_CATALOG.find(a => a.id === attackId) ?? ATTACK_CATALOG[0];
  const signals = modelSignalsFor(attack.id);
  const fused = fuseRisk(signals);
  const decision = fused >= 0.75 ? "block" : fused >= 0.45 ? "review" : "allow";
  return {
    id: `${attack.id}-representative-case`,
    runId: LATEST_RUN.id,
    attackFamilyId: attack.id,
    attackName: attack.name,
    modelSignals: signals,
    fusedRiskScore: fused,
    decision,
    evidence: [`${signals.filter(s => s.triggered).length} of ${signals.length} model signals triggered above threshold`, signals.find(s => s.modality === "graph") ? "Beneficiary graph distance to known mule cluster: 2 hops" : "No graph-relationship signal available for this case", `Fused risk score ${(fused * 100).toFixed(0)}% → ${decision.toUpperCase()}`],
    actualLabel: "fraud",
    detected: decision !== "allow"
  };
}
export function getEvaluationCases(runId, limit = 12) {
  const cases = [];
  for (let i = 0; i < limit; i++) {
    const attack = pick(rand, ATTACK_CATALOG);
    const signals = modelSignalsFor(attack.id);
    const fused = fuseRisk(signals);
    const decision = fused >= 0.75 ? "block" : fused >= 0.45 ? "review" : "allow";
    const detected = decision !== "allow";
    cases.push({
      id: `${runId}-case-${i}`,
      runId,
      attackFamilyId: attack.id,
      attackName: attack.name,
      modelSignals: signals,
      fusedRiskScore: fused,
      decision,
      evidence: [`${signals.filter(s => s.triggered).length} of ${signals.length} model signals triggered above threshold`, signals.find(s => s.modality === "graph") ? "Beneficiary graph distance to known mule cluster: 2 hops" : "No graph-relationship signal available for this case", `Fused risk score ${(fused * 100).toFixed(0)}% → ${decision.toUpperCase()}`],
      actualLabel: rand() > 0.12 ? "fraud" : "legitimate",
      detected
    });
  }
  return cases;
}
const WEAKNESS_TEMPLATES = {
  graph: {
    label: "Mule-network attacks",
    reasons: ["Device appears trusted from prior sessions", "Individual transaction amounts appear normal", "Behavioral deviation accrues gradually across many small transfers", "Graph relationship to the mule cluster is weakly represented at 2+ hops"]
  },
  transaction: {
    label: "Low-value probing cascades",
    reasons: ["Each probing transaction sits under the static rule threshold", "Merchant-category rotation dilutes velocity signals", "Model has limited training coverage on sub-threshold sequences"]
  },
  behavioral: {
    label: "Synthetic behavioral drift",
    reasons: ["Baseline re-calibrates gradually, absorbing the attacker's drift", "Device fingerprint stays constant, suppressing anomaly signals", "Drift rate falls below the model's sensitivity window"]
  },
  voice: {
    label: "Voice-clone impersonation",
    reasons: ["Clone quality exceeds the spoof detector's training distribution", "IVR fallback flow has weaker verification than the primary channel", "Urgency framing suppresses manual review escalation"]
  },
  text: {
    label: "GenAI phishing variants",
    reasons: ["Personalized lures avoid known template signatures", "Look-alike domains rotate faster than the blocklist updates"]
  },
  qr: {
    label: "QR quishing overlays",
    reasons: ["Overlay QR content is visually indistinguishable from the source", "Payment redirect happens outside any monitored digital channel"]
  },
  document: {
    label: "Forged invoices / documents",
    reasons: ["GenAI-edited fields pass basic OCR consistency checks", "Metadata normalization removes typical forgery fingerprints"]
  },
  "account-takeover": {
    label: "Credential-stuffing takeover",
    reasons: ["Low-and-slow login attempts stay under rate-limit thresholds", "Beneficiary change immediately follows a 'legitimate' login, diluting risk"]
  }
};
export function getWeaknesses(runId) {
  const run = RUNS.find(r => r.id === runId) ?? LATEST_RUN;
  return run.scope.map((category, i) => {
    const tpl = WEAKNESS_TEMPLATES[category];
    const detectionRate = 82 + seededInt(rand, 0, 12) - i;
    return {
      id: `${runId}-weak-${category}`,
      runId,
      category,
      label: tpl.label,
      detectionRate,
      missRate: Number((100 - detectionRate).toFixed(1)),
      reasons: tpl.reasons,
      recommendedAction: "Generate harder variants targeting this weakness",
      severity: i === 0 ? "high" : "medium"
    };
  });
}
export function getMutationIterations(runId) {
  const run = RUNS.find(r => r.id === runId) ?? LATEST_RUN;
  const weak = WEAKNESS_TEMPLATES[run.weakestCategory];
  const start = run.detectionRateBefore;
  const end = run.detectionRateAfter;
  const mid = Number((start + (end - start) * 0.55).toFixed(1));
  return [{
    iteration: 1,
    detectionRate: start,
    weakness: weak.label,
    changes: ["Baseline attack set", "Static severity mix"]
  }, {
    iteration: 2,
    detectionRate: mid,
    weakness: `${weak.label} — refined`,
    changes: ["Amount pattern mutated", "Timing distribution shifted", "Device-trust relationship varied"]
  }, {
    iteration: 3,
    detectionRate: end,
    weakness: `${weak.label} — hardened`,
    changes: ["Network structure re-shaped", "Escalation curve smoothed", "Cross-modal correlation added"]
  }];
}
export function getDefenseMetricSeries(runId) {
  return getMutationIterations(runId).map((it, i) => ({
    iteration: it.iteration,
    label: `Iteration ${it.iteration}`,
    detectionRate: it.detectionRate,
    precision: Number((0.88 + i * 0.02 + rand() * 0.01).toFixed(3)),
    recall: Number((it.detectionRate / 100).toFixed(3)),
    f1: Number((0.88 + i * 0.02 + rand() * 0.01).toFixed(3)),
    prAuc: Number((0.9 + i * 0.02 + rand() * 0.01).toFixed(3)),
    falsePositiveRate: Number((1.4 - i * 0.3).toFixed(2))
  }));
}
export const MODEL_PERFORMANCE = [{
  name: "XGBoost — Transaction",
  modality: "transaction",
  precision: 0.95,
  recall: 0.94,
  f1: 0.945,
  detectionRate: 96
}, {
  name: "Transformer — Behavioral",
  modality: "behavioral",
  precision: 0.91,
  recall: 0.89,
  f1: 0.9,
  detectionRate: 91
}, {
  name: "GraphSAGE — Graph/Mule",
  modality: "graph",
  precision: 0.88,
  recall: 0.85,
  f1: 0.865,
  detectionRate: 89
}, {
  name: "Autoencoder — Anomaly",
  modality: "anomaly",
  precision: 0.9,
  recall: 0.92,
  f1: 0.91,
  detectionRate: 93
}, {
  name: "DistilBERT — Phishing/Text",
  modality: "text",
  precision: 0.97,
  recall: 0.95,
  f1: 0.96,
  detectionRate: 96
}, {
  name: "Wav2Vec2 — Voice Spoof",
  modality: "voice",
  precision: 0.89,
  recall: 0.86,
  f1: 0.875,
  detectionRate: 87
}, {
  name: "OCR / Document Verification",
  modality: "document",
  precision: 0.92,
  recall: 0.88,
  f1: 0.9,
  detectionRate: 90
}];
export function getReport(runId) {
  const run = RUNS.find(r => r.id === runId) ?? LATEST_RUN;
  const weaknesses = getWeaknesses(runId);
  return {
    runId: run.id,
    generatedAt: run.completedAt ?? run.createdAt,
    objective: run.objective,
    attackCoveragePct: run.attackCoveragePct,
    performance: {
      detectionRateBefore: run.detectionRateBefore,
      detectionRateAfter: run.detectionRateAfter,
      precision: run.precision,
      recall: run.recall,
      f1: run.f1,
      prAuc: run.prAuc,
      falsePositiveRate: Number((run.falsePositives / run.attacksTested * 100).toFixed(2))
    },
    weaknesses,
    topMissedScenarios: weaknesses.map(w => ({
      name: w.label,
      category: w.category,
      missRate: w.missRate
    })),
    modelEvidence: MODEL_PERFORMANCE,
    recommendedMitigations: ["Add graph-distance features at 3+ hops for mule-cluster proximity", "Lower the sub-threshold aggregation window for probing-pattern detection", "Retrain behavioral baseline with slower re-calibration decay", "Expand voice spoof training data with the latest clone-model family"],
    iterationImprovement: getDefenseMetricSeries(runId)
  };
}
