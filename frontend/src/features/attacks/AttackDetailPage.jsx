import { useParams, Link } from "react-router-dom";
import { ChevronLeftIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { SeverityBadge, AttackStatusBadge, DifficultyBadge, DecisionBadge } from "@/components/shared/badges";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbSeparator, BreadcrumbPage } from "@/components/ui/breadcrumb";
import { useAttack, useRepresentativeCase } from "@/hooks/useAttacks";
import { AttackChainFlow } from "@/features/attacks/AttackChainFlow";
import { ATTACK_CATEGORY_LABEL, MODALITY_LABEL } from "@/types";
export function AttackDetailPage() {
  const {
    attackId = ""
  } = useParams();
  const {
    data: attack,
    isLoading
  } = useAttack(attackId);
  const {
    data: evalCase
  } = useRepresentativeCase(attackId);
  if (isLoading || !attack) {
    return <Skeleton className="h-96 w-full" />;
  }
  const triggered = evalCase?.modelSignals.filter(s => s.triggered) ?? [];
  const missed = evalCase?.modelSignals.filter(s => !s.triggered) ?? [];
  return <div className="space-y-6">
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link to="/attacks">Attack library</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{attack.name}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <PageHeader eyebrow={ATTACK_CATEGORY_LABEL[attack.category]} title={attack.name} description={attack.description} actions={<Button asChild variant="ghost" size="sm">
            <Link to="/attacks">
              <ChevronLeftIcon className="size-4" />
              Back to library
            </Link>
          </Button>} />

      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={attack.severity} />
        <AttackStatusBadge status={attack.status} />
        <DifficultyBadge difficulty={attack.difficulty} />
        {attack.modalities.map(m => <Badge key={m} variant="outline" className="border-border text-muted-foreground">
            {MODALITY_LABEL[m]}
          </Badge>)}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Attack chain</CardTitle>
          <CardDescription>How this attack progresses from initial access to cash-out</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <AttackChainFlow steps={attack.attackChain} />
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Detection result</CardTitle>
            <CardDescription>Representative case from the latest evaluation run</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {evalCase ? <>
                <div className="flex items-center justify-between rounded-2xl bg-muted/60 px-4 py-3">
                  <div>
                    <p className="text-xs text-muted-foreground">Fused risk score</p>
                    <p className="cn-font-heading text-2xl font-semibold tabular-nums">
                      {(evalCase.fusedRiskScore * 100).toFixed(0)}%
                    </p>
                  </div>
                  <DecisionBadge decision={evalCase.decision} />
                </div>
                <div className="space-y-1.5">
                  <p className="text-xs font-medium text-muted-foreground uppercase">Evidence</p>
                  <ul className="space-y-1 text-sm text-foreground">
                    {evalCase.evidence.map(e => <li key={e} className="flex gap-2">
                        <span className="text-muted-foreground">·</span>
                        {e}
                      </li>)}
                  </ul>
                </div>
              </> : <Skeleton className="h-32 w-full" />}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Detection rate</CardTitle>
            <CardDescription>{attack.variants} generated variants</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Overall</span>
                <span className="font-medium text-foreground tabular-nums">{attack.detectionRate}%</span>
              </div>
              <Progress value={attack.detectionRate} />
            </div>
            <p className="text-xs text-muted-foreground">
              Last tested {new Date(attack.lastTested).toLocaleString()}
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Models triggered</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {triggered.map(s => <div key={s.model} className="flex items-center justify-between text-sm">
                <span className="text-foreground">{s.model}</span>
                <span className="tabular-nums text-primary">{(s.score * 100).toFixed(0)}%</span>
              </div>)}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Models missed / weak signal</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {missed.length === 0 ? <p className="text-sm text-muted-foreground">Every model signal triggered for this case.</p> : missed.map(s => <div key={s.model} className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">{s.model}</span>
                  <span className="tabular-nums text-muted-foreground">{(s.score * 100).toFixed(0)}%</span>
                </div>)}
          </CardContent>
        </Card>
      </div>
    </div>;
}
