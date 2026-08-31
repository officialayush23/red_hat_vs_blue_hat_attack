import { ArrowRightIcon } from "lucide-react";
export function AttackChainFlow({
  steps
}) {
  return <div className="flex flex-wrap items-stretch gap-2">
      {steps.map((step, i) => <div key={step} className="flex items-center gap-2">
          <div className="flex min-w-36 flex-col justify-center rounded-2xl border bg-card px-3.5 py-2.5">
            <span className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
              Step {i + 1}
            </span>
            <span className="text-sm font-medium text-foreground">{step}</span>
          </div>
          {i < steps.length - 1 && <ArrowRightIcon className="size-4 shrink-0 text-muted-foreground/60" />}
        </div>)}
    </div>;
}
