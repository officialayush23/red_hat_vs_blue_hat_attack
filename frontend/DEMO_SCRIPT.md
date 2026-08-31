# FraudShield — 4 minute demo script

Assumes `npm run dev` is already running and the browser is open to the app (`/`). Every click below
uses the sidebar unless noted. Run `DR-024` is the latest/default run everywhere.

### 0:00 – 0:30 — Overview dashboard (`/`)

- Land on the dashboard. Say: *"FraudShield isn't another fraud detector — it's an agentic layer that
  continuously attacks our own defense, finds what it misses, and hardens it automatically."*
- Point at the stat row: detection rate, missed attacks, attack coverage, and **defense improvement**
  (the "+X pts" card) — this is the number that matters: the defense got measurably better this run,
  autonomously.
- Point at the "Weakest category" card: this is what the loop found on its own.

### 0:30 – 1:00 — Live Agent Activity (sidebar → *Live Agent Activity*)

- Say: *"This is the Red Team side — the agentic orchestrator researching, planning, and generating
  attacks in real time."*
- Let a step or two reveal on screen (auto-animates). Point at the agent labels (Threat Research →
  Attack Planner → Attack Generator) — this is a multi-agent pipeline, not a single call to an LLM.

### 1:00 – 1:30 — Attack Library → Attack Detail (sidebar → *Attack Library*, then click any card)

- On the library grid, say: *"Every attack family the Red Team has researched and generated variants
  for, across 8 categories — transaction, behavioral, graph/mule networks, voice, phishing, QR, and
  document forgery."*
- Click into one attack card (e.g. a graph/mule-network one). Point at the **attack chain** visualization
  and the **detection result** card — fused risk score, decision, and the evidence list underneath it.

### 1:30 – 2:15 — Blue Team Evaluation (sidebar → *Evaluation*)

- Say: *"This is the defense side. Every case runs through per-modality models, and their signals get
  fused into one decision."*
- Click through 1–2 cases in the left list. For the selected case, walk top to bottom: **input case** →
  the six model-signal cards (point at one "Triggered" and one "Below threshold") → the **risk fusion**
  card with the final score and BLOCK/REVIEW/ALLOW decision → the "Why this decision" evidence list.
  This is the human-readable explainability layer judges will want to see.

### 2:15 – 2:45 — Weakness Analysis (sidebar → *Weakness Analysis*)

- Say: *"After evaluating thousands of cases, the loop doesn't just report a score — it explains
  *why* the defense is weak in a specific category."*
- Read one "Defense weakness detected" panel's reasons out loud.
- Click **Generate Adaptive Attacks** (top right) to move to the next page.

### 2:45 – 3:20 — Adaptive Mutation (sidebar → *Adaptive Mutation*, or via the button above)

- Say: *"This is the self-hardening step. The mutation engine takes the exact weakness just found and
  re-attacks with harder variants."*
- Point at the trend chart, then scroll through Iteration 1 → 2 → 3: detection rate climbing each time,
  and the "what changed" badges under each iteration (amount pattern, timing, device relationship,
  network structure). Read the closing "detection rose from X% to Y%" summary card.

### 3:20 – 3:45 — Run Results (sidebar → *Run Results*)

- Say: *"Here's the before/after in one view."* Point at the before → after detection numbers and the
  precision/recall/F1/PR-AUC stat row — real evaluation metrics, not just a headline number.

### 3:45 – 4:00 — Reports / Export (sidebar → *Reports / Export*)

- Say: *"Everything the loop found — weaknesses, top missed scenarios, model evidence, recommended
  mitigations — rolls up into one exportable report."* Click **Export Report (JSON)** to show the
  download firing.
- Close with: *"Today this whole pipeline runs on structured mock data with the exact shape our FastAPI
  backend will return — wiring up the real models is a service-layer swap, not a UI rewrite."*

### Optional (if time remains) — Architecture (sidebar → *Architecture*)

- Show the layer chain (Analyst → Dashboard → API → Red Team → Blue Team → Adaptive Feedback) and
  expand one accordion item for technical depth, without dwelling on it — the point is the loop closes
  back on itself.
