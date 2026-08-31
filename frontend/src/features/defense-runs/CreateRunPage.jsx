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
import { useCreateRun } from "@/hooks/useRuns";
import { ATTACK_CATEGORY_LABEL } from "@/types";
const SCOPE_OPTIONS = Object.entries(ATTACK_CATEGORY_LABEL);
const SCENARIO_COUNTS = [100, 500, 1000, 10000];
export function CreateRunPage() {
  const navigate = useNavigate();
  const createRun = useCreateRun();
  const [scope, setScope] = useState(["transaction", "behavioral", "graph"]);
  const [severity, setSeverity] = useState("adaptive");
  const [scenarioCount, setScenarioCount] = useState(1000);
  const [objective, setObjective] = useState("Harden the fraud defense against adaptive payment fraud.");
  function toggleScope(category) {
    setScope(prev => prev.includes(category) ? prev.filter(c => c !== category) : [...prev, category]);
  }
  async function handleSubmit() {
    const run = await createRun.mutateAsync({
      objective,
      scope,
      severity,
      scenarioCount
    });
    navigate(`/runs/${run.id}/activity`);
  }
  return <div className="mx-auto max-w-2xl space-y-6">
      <PageHeader eyebrow="Red Team" title="Create defense run" description="Choose what the AI Red Team should attack, then let the agentic loop plan, generate, evaluate and adapt." />

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
        <Button size="lg" disabled={scope.length === 0 || createRun.isPending} onClick={handleSubmit}>
          {createRun.isPending ? "Starting…" : "Start Adversarial Evaluation"}
        </Button>
      </div>
    </div>;
}
