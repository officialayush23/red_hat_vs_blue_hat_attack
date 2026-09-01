import { useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "@/components/shared/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useAttacks, useScenarios } from "@/hooks/useAttacks";
import { ATTACK_FAMILY_BY_ID } from "@/data/attackFamilies.generated";
import { ATTACK_CATEGORY_LABEL } from "@/types";

// Two views over the same real data.
//
// "Named attacks" is the default because the names are how anyone actually
// thinks about these — "QR Quishing", "Fan-Out Mule Network Laundering" —
// and every one of them is a real attack family plus a real mutation
// combination that split_policy.py declares and the generators emit. It
// replaces data/attackCatalog.js, whose 12 named attacks had invented
// severities, variant counts and last-tested dates and matched nothing the
// backend generates. All 12 of those names survive here, now attached to
// real cases, alongside the 15 real combinations that were never named.
//
// "Families" is the taxonomy view: the 7 families themselves.

function pct(v) {
  return v === null || v === undefined ? "—" : `${v.toFixed(1)}%`;
}

function SplitBadge({ split }) {
  const heldOut = split === "held_out";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant="outline"
          className={cn(
            "shrink-0 cursor-help border-transparent text-[10px]",
            heldOut ? "bg-destructive/10 text-destructive" : "bg-muted text-muted-foreground",
          )}
        >
          {heldOut ? "Held-out" : "Train"}
        </Badge>
      </TooltipTrigger>
      <TooltipContent className="max-w-72 text-xs">
        {heldOut
          ? "This combination is reserved from training by split_policy.py — the defense has never learned from this shape, so its score here is a real generalisation test."
          : "This combination is training-allowed: the defense has seen this shape before, so a high detection rate here is expected rather than impressive."}
      </TooltipContent>
    </Tooltip>
  );
}

function ScenarioCard({ s }) {
  const family = ATTACK_FAMILY_BY_ID[s.family];
  const evaluated = s.detectionRate !== null;
  return (
    <Link to={`/attacks/${s.family}`}>
      <Card className="h-full transition-shadow hover:shadow-md">
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="text-sm leading-snug">{s.name}</CardTitle>
            <SplitBadge split={s.split} />
          </div>
          <p className="text-xs text-muted-foreground">
            {family?.label ?? s.family} · {ATTACK_CATEGORY_LABEL[family?.category] ?? family?.category}
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="line-clamp-3 text-xs text-muted-foreground">{s.description}</p>

          <div className="flex flex-wrap gap-1">
            {Object.entries(s.match).map(([k, v]) => (
              <Badge key={k} variant="outline" className="border-border font-mono text-[10px] font-normal">
                {k}={String(v)}
              </Badge>
            ))}
          </div>

          {evaluated ? (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Detection rate</span>
                <span className="font-medium text-foreground tabular-nums">{pct(s.detectionRate)}</span>
              </div>
              <Progress value={s.detectionRate} className="h-1.5" />
              <p className="text-[11px] text-muted-foreground">
                {s.blocked} blocked · {s.missed} missed
                <span className="text-muted-foreground/70"> (of {s.scoredInSample} scored in sample)</span>
              </p>
            </div>
          ) : (
            <p className="rounded-xl bg-muted px-2.5 py-1.5 text-[11px] text-muted-foreground">
              {s.generatedCases === 0
                ? "No cases generated for this combination yet."
                : s.split === "train"
                  ? `${s.generatedCases.toLocaleString()} cases generated, not adversarially scored — run_adversarial_eval.py evaluates held-out combinations only, since scoring a shape the model trained on measures memorisation, not detection.`
                  : `${s.generatedCases.toLocaleString()} cases generated, none scored yet.`}
            </p>
          )}

          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
            <span className="tabular-nums">{s.generatedCases.toLocaleString()} real cases</span>
            {s.avgRiskScore !== null && <span className="tabular-nums">avg risk {s.avgRiskScore.toFixed(1)}</span>}
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function FamilyCard({ family }) {
  const s = family.stats ?? {};
  const evaluated = s.evaluated;
  return (
    <Link to={`/attacks/${family.id}`}>
      <Card className="h-full transition-shadow hover:shadow-md">
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="text-sm leading-snug">{family.label}</CardTitle>
            <Badge
              variant="outline"
              className={cn(
                "shrink-0 border-transparent",
                evaluated ? "bg-primary/10 text-primary" : "bg-amber-500/10 text-amber-600 dark:text-amber-400",
              )}
            >
              {evaluated ? "Evaluated" : "Not evaluated"}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            {ATTACK_CATEGORY_LABEL[family.category] ?? family.category}
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="line-clamp-3 text-xs text-muted-foreground">{family.description}</p>
          {evaluated ? (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Detection rate</span>
                <span className="font-medium text-foreground tabular-nums">{pct(s.detectionRate)}</span>
              </div>
              <Progress value={s.detectionRate ?? 0} className="h-1.5" />
              <p className="text-[11px] text-muted-foreground">
                {s.blocked.toLocaleString()} blocked · {s.missed.toLocaleString()} missed
                {s.falsePositives ? ` · ${s.falsePositives.toLocaleString()} false positives` : ""}
              </p>
            </div>
          ) : (
            <p className="rounded-xl bg-amber-500/10 px-2.5 py-1.5 text-[11px] text-amber-700 dark:text-amber-300">
              {s.generatedCases?.toLocaleString() ?? 0} cases generated, none scored yet — no evaluation results for
              this family have been written to Supabase.
            </p>
          )}
          <div className="flex flex-wrap gap-1">
            {(family.detectors ?? []).slice(0, 3).map((d) => (
              <Badge key={d} variant="outline" className="border-border text-[10px] font-normal">
                {d}
              </Badge>
            ))}
          </div>
          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
            <span className="tabular-nums">{(s.generatedCases ?? 0).toLocaleString()} cases</span>
            <span>{family.dimensions.length} mutation dimensions</span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

export function AttackLibraryPage() {
  const { data: families, isLoading: familiesLoading } = useAttacks();
  const { data: scenarios, isLoading: scenariosLoading } = useScenarios();
  const [view, setView] = useState("scenarios");
  const [category, setCategory] = useState("all");

  const presentCategories = [...new Set((families ?? []).map((f) => f.category))];
  const categoryOf = (familyId) => ATTACK_FAMILY_BY_ID[familyId]?.category;

  const visibleScenarios = (scenarios ?? []).filter(
    (s) => category === "all" || categoryOf(s.family) === category,
  );
  const visibleFamilies = (families ?? []).filter((f) => category === "all" || f.category === category);
  const isLoading = view === "scenarios" ? scenariosLoading : familiesLoading;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Red Team"
        title="Attack library"
        description="Every named attack is a real attack family plus a real mutation-parameter combination from split_policy.py — with the real number of cases generated for it and what the defense actually did with them."
      />

      <div className="flex flex-wrap items-center gap-3">
        <Tabs value={view} onValueChange={setView}>
          <TabsList>
            <TabsTrigger value="scenarios">Named attacks ({scenarios?.length ?? 27})</TabsTrigger>
            <TabsTrigger value="families">Families ({families?.length ?? 7})</TabsTrigger>
          </TabsList>
        </Tabs>
        <Tabs value={category} onValueChange={setCategory}>
          <TabsList className="flex-wrap justify-start">
            <TabsTrigger value="all">All</TabsTrigger>
            {presentCategories.map((value) => (
              <TabsTrigger key={value} value={value}>
                {ATTACK_CATEGORY_LABEL[value] ?? value}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-60" />
          ))}
        </div>
      ) : view === "scenarios" ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visibleScenarios.map((s) => (
            <ScenarioCard key={s.id} s={s} />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visibleFamilies.map((f) => (
            <FamilyCard key={f.id} family={f} />
          ))}
        </div>
      )}
    </div>
  );
}
