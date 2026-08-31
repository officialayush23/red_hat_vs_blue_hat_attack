import { useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "@/components/shared/PageHeader";
import { SeverityBadge, AttackStatusBadge, DifficultyBadge } from "@/components/shared/badges";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAttacks } from "@/hooks/useAttacks";
import { ATTACK_CATEGORY_LABEL } from "@/types";
export function AttackLibraryPage() {
  const {
    data: attacks,
    isLoading
  } = useAttacks();
  const [category, setCategory] = useState("all");
  const filtered = attacks?.filter(a => category === "all" || a.category === category);
  return <div className="space-y-6">
      <PageHeader eyebrow="Red Team" title="Attack library" description="Every attack family the Red Team has researched, generated and tested against the fraud defense." />

      <Tabs value={category} onValueChange={v => setCategory(v)}>
        <TabsList className="flex-wrap justify-start">
          <TabsTrigger value="all">All</TabsTrigger>
          {Object.entries(ATTACK_CATEGORY_LABEL).map(([value, label]) => <TabsTrigger key={value} value={value}>
              {label}
            </TabsTrigger>)}
        </TabsList>
      </Tabs>

      {isLoading ? <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({
        length: 6
      }).map((_, i) => <Skeleton key={i} className="h-52" />)}
        </div> : <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered?.map(attack => <Link key={attack.id} to={`/attacks/${attack.id}`}>
              <Card className="h-full transition-shadow hover:shadow-md">
                <CardHeader>
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-sm leading-snug">{attack.name}</CardTitle>
                    <SeverityBadge severity={attack.severity} className="shrink-0" />
                  </div>
                  <p className="text-xs text-muted-foreground">{ATTACK_CATEGORY_LABEL[attack.category]}</p>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="line-clamp-2 text-xs text-muted-foreground">{attack.description}</p>
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>Detection rate</span>
                      <span className="font-medium text-foreground tabular-nums">{attack.detectionRate}%</span>
                    </div>
                    <Progress value={attack.detectionRate} className="h-1.5" />
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <AttackStatusBadge status={attack.status} />
                    <DifficultyBadge difficulty={attack.difficulty} />
                  </div>
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>{attack.variants} variants</span>
                    <span>Tested {new Date(attack.lastTested).toLocaleDateString()}</span>
                  </div>
                </CardContent>
              </Card>
            </Link>)}
        </div>}
    </div>;
}
