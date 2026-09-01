import { Link, useParams } from "react-router-dom";
import { ChevronLeftIcon, ShieldAlertIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { DecisionBadge } from "@/components/shared/badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState } from "@/components/shared/EmptyState";
import { cn } from "@/lib/utils";
import { useAttack, useAttackCases, useGeneratedCombinations, useRepresentativeCase } from "@/hooks/useAttacks";
import { ATTACK_CATEGORY_LABEL } from "@/types";

// One real attack family: its real mutation dimensions and split policy
// (backend/evaluation/split_policy.py), the combinations the generator
// actually emitted, and real scored cases from Supabase.
//
// The previous version of this page rendered an invented "attack chain"
// (initial access -> cash-out narrative steps), a fabricated severity /
// difficulty / variant count, and a mockStore-generated "representative
// case" whose model signals and risk score were seeded random numbers.
// None of that had a backend behind it.

function ComboChips({ combo }) {
  const entries = Object.entries(combo ?? {});
  if (!entries.length) return <span className="text-xs text-muted-foreground">defaults only</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {entries.map(([k, v]) => (
        <Badge key={k} variant="outline" className="border-border font-mono text-[10px] font-normal">
          {k}={String(v)}
        </Badge>
      ))}
    </span>
  );
}

export function AttackDetailPage() {
  const { attackId = "" } = useParams();
  const { data: family, isLoading } = useAttack(attackId);
  const { data: representative } = useRepresentativeCase(attackId);
  const { data: cases } = useAttackCases(attackId, 10);
  const { data: combos } = useGeneratedCombinations(attackId);

  if (isLoading) return <Skeleton className="h-96 w-full" />;

  if (!family) {
    return (
      <EmptyState
        icon={<ShieldAlertIcon className="size-10" />}
        title="Attack family not found"
        description="This id isn't one of the attack families in backend/evaluation/split_policy.py."
        action={
          <Button asChild variant="outline">
            <Link to="/attacks">Back to attack library</Link>
          </Button>
        }
      />
    );
  }

  const s = family.stats ?? {};
  const result = representative?.result;

  return (
    <div className="space-y-6">
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link to="/attacks">Attack library</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{family.label}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <PageHeader
        eyebrow={ATTACK_CATEGORY_LABEL[family.category] ?? family.category}
        title={family.label}
        description={family.description}
        actions={
          <Button asChild variant="ghost" size="sm">
            <Link to="/attacks">
              <ChevronLeftIcon className="size-4" />
              Back to library
            </Link>
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" className="border-border font-mono text-[11px] font-normal">{family.id}</Badge>
        {(family.detectors ?? []).map((d) => (
          <Badge key={d} variant="outline" className="border-border text-muted-foreground">{d}</Badge>
        ))}
        <Badge variant="outline" className="border-border text-muted-foreground">source: {family.sourceDataset}</Badge>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Generated cases</CardTitle>
            <CardDescription>attack_cases in Supabase</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="cn-font-heading text-2xl font-semibold tabular-nums">
              {(s.generatedCases ?? 0).toLocaleString()}
            </p>
            <p className="text-xs text-muted-foreground">
              {(s.trainCases ?? 0).toLocaleString()} train · {(s.heldOutCases ?? 0).toLocaleString()} held-out
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Detection rate</CardTitle>
            <CardDescription>
              {s.evaluated
                ? `over ${(s.blocked + s.missed).toLocaleString()} scored fraud results`
                : "no scored results yet"}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {s.evaluated ? (
              <>
                <p className="cn-font-heading text-2xl font-semibold tabular-nums">
                  {s.detectionRate.toFixed(1)}%
                </p>
                <Progress value={s.detectionRate} />
                <p className="text-xs text-muted-foreground">
                  {s.blocked.toLocaleString()} blocked · {s.missed.toLocaleString()} missed
                </p>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                This family has generated cases but no rows in <code className="font-mono text-xs">evaluation_results</code>,
                so there is no detection rate to report. Nothing is estimated in its place.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">False positives</CardTitle>
            <CardDescription>on legitimate samples</CardDescription>
          </CardHeader>
          <CardContent>
            <p
              className={cn(
                "cn-font-heading text-2xl font-semibold tabular-nums",
                (s.falsePositiveRate ?? 0) >= 10 && "text-amber-600 dark:text-amber-400",
              )}
            >
              {s.falsePositiveRate === null || s.falsePositiveRate === undefined
                ? "—"
                : `${s.falsePositiveRate.toFixed(1)}%`}
            </p>
            <p className="text-xs text-muted-foreground">
              {(s.falsePositives ?? 0).toLocaleString()} of {((s.falsePositives ?? 0) + (s.cleared ?? 0)).toLocaleString()} legitimate results
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Split policy</CardTitle>
          <CardDescription>
            Transcribed from backend/evaluation/split_policy.py — which mutation-parameter combinations the
            generator may use for training data, and which are reserved so the defense is scored on shapes it
            never learned from. Dimensions: {family.dimensions.join(", ")}.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Training-allowed</p>
            {family.trainingAllowed.map((c, i) => (
              <div key={i} className="rounded-xl border px-3 py-2"><ComboChips combo={c} /></div>
            ))}
          </div>
          <div className="space-y-2">
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Held-out only</p>
            {family.heldOutOnly.map((c, i) => (
              <div key={i} className="rounded-xl border border-destructive/30 bg-destructive/5 px-3 py-2">
                <ComboChips combo={c} />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {combos?.length ? (
        <Card>
          <CardHeader>
            <CardTitle>Combinations actually generated</CardTitle>
            <CardDescription>
              What the generator really emitted, counted from real attack_cases.mutation_params — the empirical
              counterpart to the policy above.
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Combination</TableHead>
                  <TableHead className="text-right">Train</TableHead>
                  <TableHead className="text-right">Held-out</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {combos.slice(0, 12).map((c, i) => (
                  <TableRow key={i}>
                    <TableCell><ComboChips combo={c.combo} /></TableCell>
                    <TableCell className="text-right tabular-nums">{c.train}</TableCell>
                    <TableCell className="text-right tabular-nums">{c.heldOut}</TableCell>
                    <TableCell className="text-right font-medium tabular-nums">{c.total}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Most instructive real case</CardTitle>
            <CardDescription>
              A real miss where one exists — an attack that got through teaches more than one that was stopped —
              otherwise the highest-risk real block.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {!representative ? (
              <p className="text-sm text-muted-foreground">No cases for this family yet.</p>
            ) : !result ? (
              <p className="text-sm text-muted-foreground">
                Case <code className="font-mono text-xs">{representative.id}</code> was generated but never scored —
                this family has no evaluation results.
              </p>
            ) : (
              <>
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-muted/60 px-4 py-3">
                  <div>
                    <p className="font-mono text-[10px] break-all text-muted-foreground">{representative.id}</p>
                    <p className="text-xs text-muted-foreground">Fused risk score</p>
                    <p className="cn-font-heading text-2xl font-semibold tabular-nums">
                      {result.riskScore === null ? "n/a" : `${result.riskScore.toFixed(1)} / 100`}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1.5">
                    <DecisionBadge decision={result.decision} />
                    <Badge
                      variant="outline"
                      className={cn(
                        "border-transparent",
                        result.detected ? "bg-primary/10 text-primary" : "bg-destructive/10 text-destructive",
                      )}
                    >
                      {result.actualLabel === "fraud"
                        ? result.detected ? "Blocked" : "Missed"
                        : result.detected ? "Cleared" : "False positive"}
                    </Badge>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Mutation parameters</p>
                  <ComboChips combo={representative.mutationParams?.resolved_levels ?? representative.mutationParams} />
                </div>

                {result.evidence.length > 0 && (
                  <div className="space-y-1.5">
                    <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Evidence</p>
                    <ul className="space-y-1 text-sm">
                      {result.evidence.map((e) => (
                        <li key={e} className="flex gap-2 font-mono text-xs">
                          <span className="text-muted-foreground">·</span>
                          {e}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Model signals</CardTitle>
            <CardDescription>real per-detector scores on that case</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {result?.modelSignals?.length ? (
              result.modelSignals.map((sig) => (
                <div key={sig.model} className="flex items-center justify-between text-sm">
                  <span className="text-foreground">{sig.model}</span>
                  <span className="tabular-nums">{sig.score === null ? "—" : sig.score.toFixed(3)}</span>
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">No model signals recorded for this case.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent real cases</CardTitle>
          <CardDescription>Newest generated cases for this family, with their latest score where one exists</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Case</TableHead>
                <TableHead>Split</TableHead>
                <TableHead className="text-right">Risk</TableHead>
                <TableHead>Decision</TableHead>
                <TableHead>Outcome</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(cases ?? []).map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="font-mono text-[11px] break-all">{c.id}</TableCell>
                  <TableCell className="text-muted-foreground">{c.splitPortion ?? "—"}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {c.result && c.result.riskScore !== null ? c.result.riskScore.toFixed(1) : "—"}
                  </TableCell>
                  <TableCell className="text-muted-foreground uppercase">{c.result?.decision ?? "—"}</TableCell>
                  <TableCell
                    className={cn(
                      "font-medium",
                      c.result?.detected === false && c.result?.actualLabel === "fraud" && "text-destructive",
                      c.result?.detected === true && c.result?.actualLabel === "fraud" && "text-primary",
                    )}
                  >
                    {!c.result
                      ? "not scored"
                      : c.result.actualLabel === "fraud"
                        ? c.result.detected ? "Blocked" : "Missed"
                        : c.result.detected ? "Cleared" : "False positive"}
                  </TableCell>
                </TableRow>
              ))}
              {!cases?.length && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-sm text-muted-foreground">
                    No generated cases for this family.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
