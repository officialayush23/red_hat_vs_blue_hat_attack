import { ArrowRightIcon, RefreshCwIcon, ShieldAlertIcon, ShieldCheckIcon, SwordsIcon, TargetIcon } from "lucide-react"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { useOnboarding } from "@/lib/onboarding"

const LOOP_STEPS = [
  { label: "Discover", detail: "Red Team researches plausible fraud strategies" },
  { label: "Attack", detail: "Red Team generates a controlled attack scenario" },
  { label: "Evaluate", detail: "Blue Team scores it — caught, or missed?" },
  { label: "Adapt", detail: "Missed attacks become harder tests, automatically" },
]

export function OnboardingDialog() {
  const { isOpen, close } = useOnboarding()

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && close()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl" showCloseButton={false}>
        <DialogHeader>
          <Badge variant="outline" className="mb-1 w-fit border-transparent bg-primary/10 text-primary">
            Welcome
          </Badge>
          <DialogTitle className="text-xl">What is FraudShield?</DialogTitle>
          <DialogDescription>
            FraudShield isn't another fraud detector — it's an AI attacker and an AI defender, locked in a
            continuous loop, so real weaknesses get found before real attackers find them.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-2 rounded-2xl border border-destructive/20 bg-destructive/5 p-4">
            <div className="flex items-center gap-2">
              <div className="flex size-8 items-center justify-center rounded-xl bg-destructive/15 text-destructive">
                <ShieldAlertIcon className="size-4" />
              </div>
              <p className="font-medium text-foreground">Red Team</p>
            </div>
            <p className="text-sm text-muted-foreground">
              The attacker simulator. It asks: <span className="text-foreground">"How can I break the defense?"</span>{" "}
              — and builds a realistic fraud scenario to try it.
            </p>
          </div>
          <div className="space-y-2 rounded-2xl border border-primary/20 bg-primary/5 p-4">
            <div className="flex items-center gap-2">
              <div className="flex size-8 items-center justify-center rounded-xl bg-primary/15 text-primary">
                <ShieldCheckIcon className="size-4" />
              </div>
              <p className="font-medium text-foreground">Blue Team</p>
            </div>
            <p className="text-sm text-muted-foreground">
              The defender. It asks: <span className="text-foreground">"Can I catch it?"</span> — scoring every
              case and explaining its decision.
            </p>
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">What's happening</p>
          <div className="flex flex-wrap items-center gap-1.5">
            {LOOP_STEPS.map((step, i) => (
              <span key={step.label} className="flex items-center gap-1.5">
                <span className="rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-foreground" title={step.detail}>
                  {step.label}
                </span>
                {i < LOOP_STEPS.length - 1 ? (
                  <ArrowRightIcon className="size-3 shrink-0 text-muted-foreground/50" />
                ) : (
                  <RefreshCwIcon className="size-3 shrink-0 text-primary/70" />
                )}
              </span>
            ))}
          </div>
          <p className="text-sm text-muted-foreground">
            Every missed attack becomes intelligence for the next, harder one — automatically, without a human
            in the loop.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex items-start gap-2.5">
            <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-xl bg-muted text-muted-foreground">
              <TargetIcon className="size-3.5" />
            </div>
            <div>
              <p className="text-sm font-medium text-foreground">End goal</p>
              <p className="text-sm text-muted-foreground">A fraud defense that measurably gets stronger every run.</p>
            </div>
          </div>
          <div className="flex items-start gap-2.5">
            <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-xl bg-muted text-muted-foreground">
              <SwordsIcon className="size-3.5" />
            </div>
            <div>
              <p className="text-sm font-medium text-foreground">Why it's worth it</p>
              <p className="text-sm text-muted-foreground">Find weaknesses before attackers do — with evidence, not guesswork.</p>
            </div>
          </div>
        </div>

        <DialogFooter>
          <p className="mr-auto self-center text-xs text-muted-foreground">
            Reopen this anytime from the <span className="font-medium text-foreground">?</span> icon in the top bar.
          </p>
          <Button onClick={close}>Got it, let's go</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
