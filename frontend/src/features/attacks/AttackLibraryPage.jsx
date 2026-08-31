import { useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "@/components/shared/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { useAttacks } from "@/hooks/useAttacks";
import { ATTACK_CATEGORY_LABEL } from "@/types";

// The 7 real attack families this backend generates and scores, from
// backend/evaluation/split_policy.py via data/attackFamilies.generated.js,
// with live counts and outcomes from Supabase.
//
// This page used to render data/attackCatalog.js: 12 hand-written attacks
// ("Trusted Device + Mule Network", "QR Quishing (Parking / Bill Overlay)",
// "Deepfake Support-Call Impersonation") with invented severities,
// difficulties, variant counts and last-tested dates. None of them
// corresponded to anything the backend has ever generated or evaluated.

function pct(v) {
  return v === null || v === undefined ? "—" : `${v.toFixed(1)}%`;
}

export function AttackLibraryPage() {
  const { data: families, isLoading } = useAttacks();
  const [category, setCategory] = useState("all");

  const filtered = (families ?? []).filter((f) => category === "all" || f.category === category);
  // Only offer tabs for categories that real families actually map to --
  // ATTACK_CATEGORY_LABEL still lists "QR / Quishing", which no family
  // resolves to (qr maps onto document_fraud), so an unfiltered tab list
  // would offer categories that can only ever come up empty.
  const presentCategories = [...new Set((families ?? []).map((f) => f.category))];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Red Team"
        title="Attack library"
        description="The attack families this system really generates and scores — their mutation dimensions, how many cases exist, and what the defense actually did with them."
      />

      <Tabs value={category} onValueChange={(v) => setCategory(v)}>
        <TabsList className="flex-wrap justify-start">
          <TabsTrigger value="all">All</TabsTrigger>
          {presentCategories.map((value) => (
            <TabsTrigger key={value} value={value}>
              {ATTACK_CATEGORY_LABEL[value] ?? value}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-60" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((family) => {
            const s = family.stats ?? {};
            const evaluated = s.evaluated;
            return (
              <Link key={family.id} to={`/attacks/${family.id}`}>
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
                        {s.generatedCases?.toLocaleString() ?? 0} cases generated, none scored yet — no evaluation
                        results for this family have been written to Supabase.
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
          })}
        </div>
      )}
    </div>
  );
}
