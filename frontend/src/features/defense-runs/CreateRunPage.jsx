import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { useCreateRun, useRuns } from "@/hooks/useRuns";
import { useApiMode } from "@/hooks/useApiMode";
import { useDataStatus, useHydrate } from "@/hooks/useDataStatus";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { DatabaseIcon, LoaderCircleIcon, RadioIcon, TriangleAlertIcon } from "lucide-react";
import { ATTACK_CATEGORY_LABEL } from "@/types";
const SCOPE_OPTIONS = Object.entries(ATTACK_CATEGORY_LABEL);
const SCENARIO_COUNTS = [100, 500, 1000, 10000];
export function CreateRunPage() {
  const navigate = useNavigate();
  const createRun = useCreateRun();
  const api = useApiMode();
  const { data: runs } = useRuns();
  const { data: dataStatus } = useDataStatus(api.live);
  const hydrate = useHydrate();
  // The Railway image is built from the repo and data/generated/ is
  // gitignored, so a fresh container has no cases to attack. That is no
  // longer a reason to block Start: agent_runner.py pulls the bundles its
  // scope needs from Supabase Storage as a real, reported first stage of
  // the run itself. This flag only decides whether to warn that the run
  // will take a few extra minutes.
  const hasData = dataStatus ? dataStatus.canRunPipeline : true;
  const canStart = api.live;
  const [scope, setScope] = useState(["transaction", "behavioral", "graph"]);
  const [severity, setSeverity] = useState("adaptive");
  const [scenarioCount, setScenarioCount] = useState(1000);
  const [objective, setObjective] = useState("Harden the fraud defense against adaptive payment fraud.");
  // Reuse by default: ~25.7k real cases are already stored, and scoring the
  // same population every run is what makes a detection-rate delta mean the
  // DEFENSE changed rather than the attacks having changed underneath it.
  const [caseSource, setCaseSource] = useState("reuse");
  const [difficulty, setDifficulty] = useState("held_out");
  function toggleScope(category) {
    setScope(prev => prev.includes(category) ? prev.filter(c => c !== category) : [...prev, category]);
  }
  // The most recent run that actually finished — what "replay" opens when
  // this build has no backend to launch a new one against.
  const latestCompleted = (runs ?? []).find(r => r.status === "completed") ?? (runs ?? [])[0];

  async function handleSubmit() {
    const run = await createRun.mutateAsync({
      objective,
      scope,
      severity,
      scenarioCount,
      caseSource,
      difficulty
    });
    // Straight into the war room: the attack stream is the screen, not a
    // page you navigate to afterwards.
    navigate(`/runs/${run.id}/live`);
  }
  return <div className="mx-auto max-w-2xl space-y-6">
      <PageHeader eyebrow="Red Team" title="Create defense run" description="Choose what the AI Red Team should attack, then let the agentic loop plan, generate, evaluate and adapt." />

      {api.isFetched && !api.live && (
        <Alert>
          <TriangleAlertIcon className="size-4" />
          <AlertTitle>Replay mode — no backend reachable from this build</AlertTitle>
          <AlertDescription className="space-y-2">
            <p>
              Starting a run launches <code className="font-mono text-xs">orchestration/agent_runner.py</code> as a
              real local process over the local model and data files, so it needs a reachable FastAPI backend
              {api.apiBase ? <> (currently configured: <code className="font-mono text-xs">{api.apiBase}</code>, {api.reason})</> : <> (no <code className="font-mono text-xs">VITE_API_BASE_URL</code> was baked into this build)</>}.
              Everything else on this site is real, completed evidence read straight from Supabase.
            </p>
            {latestCompleted && (
              <Button variant="outline" size="sm" onClick={() => navigate(`/runs/${latestCompleted.id}/live`)}>
                Open the last real run in the war room
              </Button>
            )}
          </AlertDescription>
        </Alert>
      )}

      {api.live && hasData && (
        <Alert>
          <RadioIcon className="size-4" />
          <AlertTitle>Backend live</AlertTitle>
          <AlertDescription>
            Connected to <code className="font-mono text-xs">{api.apiBase}</code>
            {dataStatus ? <> · {dataStatus.totalFiles.toLocaleString()} generated case files on that instance</> : null}.
            Starting a run will launch a real 7-stage agent pipeline against this project&apos;s actual generators and
            detectors.
          </AlertDescription>
        </Alert>
      )}

      {api.live && !hasData && (
        <Alert>
          <DatabaseIcon className="size-4" />
          <AlertTitle>This backend will fetch its data first</AlertTitle>
          <AlertDescription className="space-y-2">
            <p>
              <code className="font-mono text-xs">{api.apiBase}</code> is reachable and healthy, but its
              <code className="mx-1 font-mono text-xs">data/generated/</code> directory is empty — the container image
              is built from the repo, and that directory is gitignored (236&nbsp;MB of regenerable cases, audio and
              invoices).
            </p>
            <p>
              You can still start a run. Its first stage pulls the bundles this scope actually needs from Supabase
              Storage and reports doing so in the live trace — a transaction-only run fetches ~2&nbsp;MB, a
              voice run ~120&nbsp;MB. Expect the first run on a cold instance to take a few extra minutes.
            </p>
            <p className="text-muted-foreground">
              Optional: warm the instance now so the run itself starts clean.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" onClick={() => hydrate.mutate({})} disabled={hydrate.isPending}>
                {hydrate.isPending ? (
                  <>
                    <LoaderCircleIcon className="size-4 animate-spin" /> Hydrating…
                  </>
                ) : (
                  <>Pre-warm now (optional)</>
                )}
              </Button>
              {latestCompleted && (
                <Button variant="outline" size="sm" onClick={() => navigate(`/runs/${latestCompleted.id}/live`)}>
                  Open the last real run instead
                </Button>
              )}
            </div>
            {hydrate.isError && (
              <p className="font-mono text-xs break-words text-destructive">
                {hydrate.error?.message ?? String(hydrate.error)}
              </p>
            )}
            {hydrate.data && (
              <pre className="max-h-40 overflow-auto rounded-xl bg-muted/60 p-2 font-mono text-[10px] whitespace-pre-wrap">
                {hydrate.data.log_tail || hydrate.data.stderr_tail || hydrate.data.status}
              </pre>
            )}
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Attack scope</CardTitle>
          <CardDescription>Which modalities should the Red Team target this run?</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {SCOPE_OPTIONS.map(([value, label]) => <label key={value} className="group flex items-center gap-2.5 rounded-2xl border border-transparent px-3 py-2.5 text-sm hover:bg-muted">
                <Checkbox checked={scope.includes(value)} onCheckedChange={() => toggleScope(value)} />
                <span>{label}</span>
              </label>)}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Severity &amp; scale</CardTitle>
          <CardDescription>Adaptive severity lets the Mutation Engine escalate difficulty automatically.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5 sm:grid-cols-2">
          <div className="space-y-2">
            <Label>Severity</Label>
            <Select value={severity} onValueChange={v => setSeverity(v)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="low">Low</SelectItem>
                <SelectItem value="medium">Medium</SelectItem>
                <SelectItem value="high">High</SelectItem>
                <SelectItem value="adaptive">Adaptive</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Number of scenarios</Label>
            <Select value={String(scenarioCount)} onValueChange={v => setScenarioCount(Number(v))}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SCENARIO_COUNTS.map(n => <SelectItem key={n} value={String(n)}>
                    {n.toLocaleString()}
                  </SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Cases &amp; difficulty</CardTitle>
          <CardDescription>
            What this run attacks with. Difficulty is not a slider on top of the data — it selects which region
            of the real split policy (backend/evaluation/split_policy.py) the run draws from.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5 sm:grid-cols-2">
          <div className="space-y-2">
            <Label>Cases</Label>
            <Select value={caseSource} onValueChange={(v) => setCaseSource(v)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="reuse">Reuse the stored corpus</SelectItem>
                <SelectItem value="generate">Generate fresh attacks</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {caseSource === "reuse"
                ? "Scores cases already generated and stored. Faster, and comparable across runs because every run scores the same population."
                : "Runs the Red Team generators first. Slower, and each run scores a different population — a detection-rate change then reflects both the defense and the new attacks."}
            </p>
          </div>
          <div className="space-y-2">
            <Label>Difficulty</Label>
            <Select value={difficulty} onValueChange={(v) => setDifficulty(v)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="held_out">Hard — held-out-only combinations</SelectItem>
                <SelectItem value="mixed">Mixed — both regions</SelectItem>
                <SelectItem value="training">Easier — training-allowed combinations</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {difficulty === "held_out"
                ? "Mutation combinations the frozen models have never seen. This is the region that supports a \u201cdetects novel fraud\u201d claim."
                : difficulty === "training"
                  ? "Combinations the models were fitted against. Expect high detection — this measures fit, not novelty."
                  : "Both regions together. The headline number then averages a seen and an unseen population."}
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Objective</CardTitle>
          <CardDescription>Tell the Orchestrator Agent what "hardened" should mean for this run.</CardDescription>
        </CardHeader>
        <CardContent>
          <Textarea value={objective} onChange={e => setObjective(e.target.value)} rows={3} />
        </CardContent>
      </Card>

      <Separator />

      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {scope.length} scope{scope.length === 1 ? "" : "s"} selected · {scenarioCount.toLocaleString()} scenarios
        </p>
        <Button size="lg" disabled={scope.length === 0 || createRun.isPending || !canStart} onClick={handleSubmit}>
          {createRun.isPending ? "Starting…" : "Start Adversarial Evaluation"}
        </Button>
      </div>

      {createRun.isError && (
        <Alert variant="destructive">
          <TriangleAlertIcon className="size-4" />
          <AlertTitle>The run did not start</AlertTitle>
          <AlertDescription className="font-mono text-xs break-words">
            {createRun.error?.message ?? String(createRun.error)}
          </AlertDescription>
        </Alert>
      )}
    </div>;
}
