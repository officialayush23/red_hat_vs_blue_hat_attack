import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CalendarIcon, MicIcon, SmartphoneIcon, UsersIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { CaseEvidence } from "@/components/shared/CaseEvidence";
import { EmptyState } from "@/components/shared/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useCaseEvidence, useCustomerCases, useCustomers } from "@/hooks/useCustomers";
import { FAMILY_LABEL } from "@/services/api/liveCases";

// The customer universe: the real synthetic_customers rows this system
// generates attacks against, and, for any one of them, the real cases that
// targeted them with the actual artifact attached.
//
// This table has held 21 real rows since 2026-08-30 and nothing in the app
// read it. It is the "at whom" half of the story -- the attack library
// covers "what was thrown", and attack_cases.customer_id is the real join.

function CustomerCard({ c, selected, onSelect }) {
  const families = Object.entries(c.targeting.families).sort((a, b) => b[1] - a[1]);
  return (
    <button
      type="button"
      onClick={() => onSelect(c.id)}
      className={cn(
        "w-full rounded-2xl border px-3 py-2.5 text-left transition-colors",
        selected ? "border-primary/40 bg-primary/5" : "border-transparent hover:bg-muted",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{c.name}</p>
          <p className="font-mono text-[10px] text-muted-foreground">{c.id}</p>
        </div>
        <Badge variant="outline" className="shrink-0 border-border text-[10px] tabular-nums">
          {c.targeting.total} cases
        </Badge>
      </div>
      <div className="mt-1.5 flex flex-wrap gap-1">
        {families.slice(0, 3).map(([f, n]) => (
          <Badge key={f} variant="outline" className="border-border text-[9px] font-normal">
            {FAMILY_LABEL[f] ?? f} {n}
          </Badge>
        ))}
      </div>
    </button>
  );
}

export function CustomerUniversePage() {
  const [params, setParams] = useSearchParams();
  const { data: customers, isLoading } = useCustomers();
  const focus = params.get("focus");
  const selectedId = focus ?? customers?.[0]?.id ?? null;
  const selected = (customers ?? []).find((c) => c.id === selectedId) ?? null;

  const { data: cases } = useCustomerCases(selectedId, 25);
  const [caseId, setCaseId] = useState(null);
  const activeCaseId = caseId && cases?.some((c) => c.id === caseId) ? caseId : cases?.[0]?.id ?? null;
  const { data: evidence } = useCaseEvidence(activeCaseId);

  function select(id) {
    setParams(id ? { focus: id } : {}, { replace: true });
    setCaseId(null);
  }

  const totalTargeted = (customers ?? []).reduce((s, c) => s + c.targeting.total, 0);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Customer Universe"
        title="Who the attacks were aimed at"
        description="The real synthetic customers this system generates attacks against — their devices, account age and trusted beneficiaries — and, for each, the real cases that targeted them with the actual generated artifact attached."
      />

      {isLoading ? (
        <Skeleton className="h-96 w-full" />
      ) : !customers?.length ? (
        <EmptyState
          icon={<UsersIcon className="size-10" />}
          title="No customers in the universe yet"
          description="generate/synthetic_customers.py writes these rows. Run it, then backfill_attack_cases so cases link to them."
        />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ["Customers", customers.length.toLocaleString()],
              ["Cases linked to a customer", totalTargeted.toLocaleString()],
              ["Registered voice samples", customers.filter((c) => c.voiceRef).length],
              ["Trusted beneficiaries", customers.reduce((s, c) => s + c.trustedBeneficiaries.length, 0)],
            ].map(([label, value]) => (
              <div key={label} className="rounded-2xl border px-3 py-2.5">
                <p className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">{label}</p>
                <p className="cn-font-heading text-xl font-semibold tabular-nums">{value}</p>
              </div>
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
            <Card className="min-w-0">
              <CardHeader>
                <CardTitle className="text-sm">The universe</CardTitle>
                <CardDescription>{customers.length} real identities</CardDescription>
              </CardHeader>
              <CardContent className="px-2">
                <ScrollArea className="h-[560px] pr-2">
                  <div className="space-y-1">
                    {customers.map((c) => (
                      <CustomerCard key={c.id} c={c} selected={c.id === selectedId} onSelect={select} />
                    ))}
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>

            <div className="min-w-0 space-y-4">
              {selected && (
                <Card>
                  <CardHeader>
                    <CardTitle>{selected.name}</CardTitle>
                    <CardDescription className="font-mono text-[11px]">{selected.id}</CardDescription>
                  </CardHeader>
                  <CardContent className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-2">
                      <p className="flex items-center gap-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                        <CalendarIcon className="size-3.5" /> Account
                      </p>
                      <p className="text-sm">
                        {selected.accountAgeDays ?? "—"} days old · {selected.relationshipCount ?? 0} relationships
                      </p>
                      {selected.trustedBeneficiaries.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {selected.trustedBeneficiaries.map((b) => (
                            <Badge key={b} variant="outline" className="border-border text-[10px] font-normal">
                              {b}
                            </Badge>
                          ))}
                        </div>
                      )}
                      {selected.voiceRef && (
                        <p className="flex items-start gap-1.5 font-mono text-[10px] break-all text-muted-foreground">
                          <MicIcon className="mt-0.5 size-3 shrink-0" /> {selected.voiceRef}
                        </p>
                      )}
                    </div>
                    <div className="space-y-2">
                      <p className="flex items-center gap-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                        <SmartphoneIcon className="size-3.5" /> Device history
                      </p>
                      {selected.devices.length === 0 ? (
                        <p className="text-sm text-muted-foreground">No devices recorded.</p>
                      ) : (
                        <ul className="space-y-1 text-sm">
                          {selected.devices.map((d) => (
                            <li key={d.device} className="flex items-center justify-between gap-2">
                              <span>{d.device}</span>
                              <span className="flex items-center gap-2 text-xs text-muted-foreground">
                                {d.firstSeenDaysAgo !== null && <span>{d.firstSeenDaysAgo}d ago</span>}
                                <Badge
                                  variant="outline"
                                  className={cn(
                                    "border-transparent text-[10px]",
                                    d.trusted ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground",
                                  )}
                                >
                                  {d.trusted ? "trusted" : "unknown"}
                                </Badge>
                              </span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </CardContent>
                </Card>
              )}

              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Attacks aimed at this customer</CardTitle>
                  <CardDescription>
                    {cases?.length
                      ? `${cases.length} most recent real cases — pick one to see the actual artifact`
                      : "No cases link to this customer yet."}
                  </CardDescription>
                </CardHeader>
                <CardContent className="px-2">
                  <ScrollArea className="max-h-56">
                    <div className="space-y-1">
                      {(cases ?? []).map((c) => (
                        <button
                          key={c.id}
                          type="button"
                          onClick={() => setCaseId(c.id)}
                          className={cn(
                            "flex w-full items-center gap-3 rounded-xl px-2.5 py-1.5 text-left text-xs transition-colors",
                            c.id === activeCaseId ? "bg-primary/5" : "hover:bg-muted",
                          )}
                        >
                          <span className="w-44 shrink-0 truncate font-mono text-[10px] text-muted-foreground">{c.id}</span>
                          <span className="min-w-0 flex-1 truncate">{FAMILY_LABEL[c.family] ?? c.family}</span>
                          <span className="shrink-0 text-muted-foreground">{c.splitPortion}</span>
                          <span
                            className={cn(
                              "w-24 shrink-0 text-right font-medium",
                              c.result?.actualLabel === "fraud" && c.result?.detected && "text-emerald-600 dark:text-emerald-400",
                              c.result?.actualLabel === "fraud" && c.result?.detected === false && "text-destructive",
                            )}
                          >
                            {!c.result
                              ? "not scored"
                              : c.result.actualLabel === "fraud"
                                ? c.result.detected ? "Blocked" : "Missed"
                                : c.result.detected ? "Cleared" : "False positive"}
                          </span>
                        </button>
                      ))}
                    </div>
                  </ScrollArea>
                </CardContent>
              </Card>

              {evidence && <CaseEvidence evidence={evidence} />}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
