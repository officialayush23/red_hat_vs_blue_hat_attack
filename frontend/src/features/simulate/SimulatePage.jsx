import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangleIcon, FlaskConicalIcon, UploadIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { listDetectors, scoreFile, scoreText, HAS_API_BASE } from "@/services/api/jobs";
import { useModelPerformance } from "@/hooks/useEvaluations";
import { cn } from "@/lib/utils";

// SIMULATE YOUR OWN DATA.
//
// The point of this page is that nothing on it is a replay. A visitor hands
// a detector a file it has never seen and watches the same score() the
// evaluation harness calls. What it must never do is let that live demo
// imply more confidence than the detector has earned -- so every result is
// rendered next to the sample size behind that model's headline number,
// pulled from model_registry (the same source the Model Performance page
// reads), not restated here.

function fmtN(n) {
  return n === null || n === undefined ? "—" : n.toLocaleString();
}

const STRENGTH_COPY = {
  strong: "measured on a large sample",
  limited: "indicative — modest sample",
  provisional: "too few samples to generalise from",
  unknown: "no recorded sample size",
};

function EvidenceFootnote({ model }) {
  if (!model) {
    return (
      <p className="text-[11px] text-muted-foreground">
        No evidence-gate run is recorded for this detector, so there is no accuracy to quote alongside
        the score above.
      </p>
    );
  }
  return (
    <p className="text-[11px] text-muted-foreground">
      This detector&apos;s recorded evidence: precision {model.precision.toFixed(3)}, recall{" "}
      {model.recall.toFixed(3)} on <strong>n={fmtN(model.nSamples)}</strong> —{" "}
      {STRENGTH_COPY[model.evidenceStrength] ?? STRENGTH_COPY.unknown}.
    </p>
  );
}

function ScoreReadout({ result }) {
  const { score, threshold } = result;
  const pct = Math.max(0, Math.min(1, score)) * 100;
  // The threshold line is drawn, not described, because "0.0056" means
  // nothing to a reader and its POSITION relative to the score means
  // everything. voice_spoof's calibrated operating point really is that
  // small a number.
  const thresholdPct =
    threshold === null || threshold === undefined
      ? null
      : Math.max(0, Math.min(1, threshold)) * 100;
  const above = thresholdPct !== null && pct >= thresholdPct;

  return (
    <div className="space-y-2">
      <div className="flex items-baseline gap-2">
        <span className="cn-font-heading text-3xl font-semibold tabular-nums text-foreground">
          {score.toFixed(4)}
        </span>
        <span className="text-xs text-muted-foreground">in {result.seconds}s</span>
      </div>
      <div className="relative h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full rounded-full", above ? "bg-destructive" : "bg-primary")}
          style={{ width: `${pct}%` }}
        />
        {thresholdPct !== null && (
          <div
            className="absolute inset-y-0 w-0.5 bg-foreground/70"
            style={{ left: `${thresholdPct}%` }}
            title={`calibrated operating point: ${threshold}`}
          />
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        {result.score_means}
        {thresholdPct !== null && (
          <>
            {" "}· the marker is this detector&apos;s calibrated operating point ({threshold.toPrecision(3)}),
            and this score sits <strong>{above ? "above" : "below"}</strong> it.
          </>
        )}
      </p>
      {result.evidence?.length > 0 && (
        <div className="rounded-xl border border-dashed border-border/70 bg-muted/30 px-2.5 py-2">
          <p className="mb-1 text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
            Why — the detector&apos;s own reasoning trace
          </p>
          <ul className="space-y-0.5">
            {result.evidence.map((e) => (
              <li key={e} className="font-mono text-[11px] break-words text-muted-foreground">
                {e}
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-[11px] text-muted-foreground italic">{result.note}</p>
    </div>
  );
}

function DetectorCard({ detector, model }) {
  const [file, setFile] = useState(null);
  const [reference, setReference] = useState(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const isText = detector.input === "text";
  const needsPair = detector.input === "pair";
  const ready = isText ? text.trim().length > 0 : Boolean(file) && (!needsPair || reference);

  async function run() {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const res = isText
        ? await scoreText(detector.id, text)
        : await scoreFile(detector.id, file, reference);
      setResult(res);
    } catch (exc) {
      setError(exc.message || String(exc));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className={cn(!detector.available && "opacity-70")}>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="text-base">{detector.label}</CardTitle>
          <span
            className={cn(
              "rounded-full px-2 py-0.5 text-[10px] font-medium",
              detector.available ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground",
            )}
          >
            {detector.available ? "ready" : "not available here"}
          </span>
        </div>
        <CardDescription>{detector.hint}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {!detector.available ? (
          // The reason is the ACTUAL import error from the server, not a
          // generic message. This deployment really cannot run every
          // detector -- facenet-pytorch pins torch<2.3 while the voice
          // detector's transformers needs torch>=2.5 -- and saying which
          // dependency is missing is more useful, and more honest, than
          // hiding the card.
          <p className="rounded-xl bg-muted/60 px-3 py-2 font-mono text-[11px] break-words text-muted-foreground">
            {detector.unavailable_reason || "unavailable"}
          </p>
        ) : (
          <>
            {isText ? (
              <Textarea
                rows={5}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste an email or SMS here — your own, or one you invent."
              />
            ) : (
              <div className="space-y-2">
                <label className="block text-xs text-muted-foreground">
                  {needsPair ? "Selfie video" : "File"}
                  <input
                    type="file"
                    accept={detector.accepts.join(",")}
                    onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                    className="mt-1 block w-full text-xs file:mr-3 file:rounded-full file:border-0 file:bg-muted file:px-3 file:py-1.5 file:text-xs"
                  />
                </label>
                {needsPair && (
                  <label className="block text-xs text-muted-foreground">
                    Reference photo to compare against
                    <input
                      type="file"
                      accept=".jpg,.jpeg,.png"
                      onChange={(e) => setReference(e.target.files?.[0] ?? null)}
                      className="mt-1 block w-full text-xs file:mr-3 file:rounded-full file:border-0 file:bg-muted file:px-3 file:py-1.5 file:text-xs"
                    />
                  </label>
                )}
                {detector.accepts.length > 0 && (
                  <p className="text-[11px] text-muted-foreground">
                    Accepts {detector.accepts.join(", ")} · up to 25MB
                  </p>
                )}
              </div>
            )}

            <Button size="sm" disabled={!ready || busy} onClick={run}>
              <UploadIcon className="size-4" />
              {busy ? "Scoring…" : "Score it"}
            </Button>

            {error && (
              <p className="rounded-xl bg-destructive/10 px-3 py-2 text-[11px] break-words text-destructive">
                {error}
              </p>
            )}
            {result && <ScoreReadout result={result} />}
          </>
        )}

        <EvidenceFootnote model={model} />
      </CardContent>
    </Card>
  );
}

export function SimulatePage() {
  const { data: detectors, isLoading, error } = useQuery({
    queryKey: ["detectors"],
    queryFn: listDetectors,
    enabled: HAS_API_BASE,
    retry: false,
  });
  const { data: models } = useModelPerformance();
  const modelById = Object.fromEntries((models ?? []).map((m) => [m.id, m]));

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Try it yourself"
        title="Simulate your own data"
        description="Hand a detector something it has never seen and watch it score, in the same code path the evaluation harness uses."
      />

      <Alert>
        <FlaskConicalIcon className="size-4" />
        <AlertTitle>What this proves, and what it does not</AlertTitle>
        <AlertDescription>
          Each detector receives only the artifact — a file or a string. It is never told what family the
          case came from or whether it is fraud, which is what makes the score meaningful rather than
          recited. But one file is one data point: the marker on each bar is that detector&apos;s calibrated
          operating point, and the sample size behind it is printed underneath. A single result here is a
          demonstration, not evidence.
        </AlertDescription>
      </Alert>

      {!HAS_API_BASE ? (
        <EmptyState
          icon={<AlertTriangleIcon className="size-10" />}
          title="This deploy is in replay mode"
          description="Live scoring needs a reachable FastAPI backend. This build has no VITE_API_BASE_URL, so it can read completed runs from Supabase but cannot score anything new."
        />
      ) : isLoading ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : error ? (
        <EmptyState
          icon={<AlertTriangleIcon className="size-10" />}
          title="Couldn't reach the detectors"
          description={error.message}
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {detectors?.map((d) => (
            <DetectorCard key={d.id} detector={d} model={modelById[d.registry_id]} />
          ))}
        </div>
      )}
    </div>
  );
}
