import { FileTextIcon, ImageIcon, MailIcon, TableIcon, UserIcon, Volume2Icon } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

// Shows the ACTUAL artifact behind a case, not a description of it.
//
// Every media artifact this project generates was already uploaded to
// Supabase Storage's public `attack-artifacts` bucket by the generators,
// and attack_cases.artifacts carries the real URL -- verified live:
// a document_fraud invoice returns 200 image/png (75,775 bytes) and a
// voice_scam clip returns 200 audio/wav (130,924 bytes). Nothing in this
// app played or displayed any of it. So a reviewer could read that the
// system detects tampered invoices, and never see one.
//
// Per family:
//   document_fraud  -> the tampered invoice image itself
//   voice_scam      -> the generated audio, playable
//   phishing_scam   -> the real message: sender, subject, body
//   tabular         -> the real transaction sequence that was scored

function ParamChips({ params }) {
  const resolved = params?.resolved_levels ?? params ?? {};
  const entries = Object.entries(resolved).filter(([k]) => k !== "extra_fields" && k !== "resolved_levels");
  if (!entries.length) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([k, v]) => (
        <Badge key={k} variant="outline" className="border-border font-mono text-[10px] font-normal">
          {k}={String(v)}
        </Badge>
      ))}
    </div>
  );
}

function ArtifactBody({ family, artifacts, transactionSequence }) {
  const a = artifacts ?? {};

  if (a.image_url) {
    return (
      <div className="space-y-2">
        <p className="flex items-center gap-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
          <ImageIcon className="size-3.5" /> The tampered document
        </p>
        <a href={a.image_url} target="_blank" rel="noreferrer" className="block">
          <img
            src={a.image_url}
            alt="Generated invoice for this case"
            loading="lazy"
            className="max-h-[520px] w-full rounded-2xl border object-contain"
          />
        </a>
        <p className="font-mono text-[10px] break-all text-muted-foreground">{a.image_url}</p>
      </div>
    );
  }

  if (a.audio_url) {
    return (
      <div className="space-y-2">
        <p className="flex items-center gap-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
          <Volume2Icon className="size-3.5" /> The generated call audio
        </p>
        <audio controls preload="none" src={a.audio_url} className="w-full">
          Your browser cannot play this audio. <a href={a.audio_url}>Download it</a>.
        </audio>
        {a.transcript ? (
          <p className="rounded-2xl border bg-muted/40 px-3 py-2 text-sm whitespace-pre-wrap">{a.transcript}</p>
        ) : null}
        <p className="font-mono text-[10px] break-all text-muted-foreground">{a.audio_url}</p>
      </div>
    );
  }

  if (a.video_url) {
    return (
      <div className="space-y-2">
        <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">The submitted KYC video</p>
        <video controls preload="none" src={a.video_url} className="max-h-[480px] w-full rounded-2xl border" />
        <p className="font-mono text-[10px] break-all text-muted-foreground">{a.video_url}</p>
      </div>
    );
  }

  if (a.body || a.subject || a.sender) {
    return (
      <div className="space-y-2">
        <p className="flex items-center gap-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
          <MailIcon className="size-3.5" /> The message as it was sent
        </p>
        <div className="overflow-hidden rounded-2xl border">
          <div className="space-y-0.5 border-b bg-muted/40 px-4 py-2.5 text-xs">
            {a.sender && (
              <p><span className="text-muted-foreground">From: </span><span className="font-medium">{a.sender}</span></p>
            )}
            {a.subject && (
              <p><span className="text-muted-foreground">Subject: </span><span className="font-medium">{a.subject}</span></p>
            )}
            {a.channel && (
              <p><span className="text-muted-foreground">Channel: </span><span className="uppercase">{a.channel}</span></p>
            )}
          </div>
          <p className="px-4 py-3 text-sm whitespace-pre-wrap">{a.body}</p>
          {a.url && (
            <p className="border-t px-4 py-2 font-mono text-xs break-all text-destructive">
              Link in message: {a.url}
            </p>
          )}
        </div>
      </div>
    );
  }

  if (transactionSequence?.length) {
    const cols = [...new Set(transactionSequence.flatMap((t) => Object.keys(t)))]
      .filter((c) => transactionSequence.some((t) => t[c] !== null && t[c] !== undefined))
      .slice(0, 8);
    return (
      <div className="space-y-2">
        <p className="flex items-center gap-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
          <TableIcon className="size-3.5" /> The transaction sequence that was scored
        </p>
        <div className="overflow-x-auto rounded-2xl border">
          <Table>
            <TableHeader>
              <TableRow>
                {cols.map((c) => (
                  <TableHead key={c} className="font-mono text-[10px]">{c}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {transactionSequence.map((t, i) => (
                <TableRow key={i}>
                  {cols.map((c) => (
                    <TableCell key={c} className="font-mono text-[11px] tabular-nums">
                      {t[c] === null || t[c] === undefined ? "—" : String(t[c])}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
    );
  }

  return (
    <p className="rounded-2xl border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
      This case has no stored artifact. {family === "mule_network"
        ? "Mule-network cases are graph structures rather than a single file — the ring is expressed in the transaction rows."
        : "Its generator did not register one."}
    </p>
  );
}

export function CaseEvidence({ evidence, compact = false }) {
  if (!evidence) return null;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <CardTitle className="flex items-center gap-2 text-sm">
                <FileTextIcon className="size-4 shrink-0" />
                Evidence
              </CardTitle>
              <CardDescription className="font-mono text-[11px] break-all">{evidence.id}</CardDescription>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge variant="outline" className="border-border text-[10px]">
                {evidence.splitPortion ?? "—"}
              </Badge>
              <Badge
                variant="outline"
                className={cn(
                  "border-transparent text-[10px]",
                  evidence.isFraud ? "bg-destructive/10 text-destructive" : "bg-muted text-muted-foreground",
                )}
              >
                ground truth: {evidence.isFraud ? "fraud" : "legitimate"}
              </Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <ArtifactBody
            family={evidence.family}
            artifacts={evidence.artifacts}
            transactionSequence={evidence.transactionSequence}
          />

          <div className="space-y-1.5">
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
              Mutation parameters that produced it
            </p>
            <ParamChips params={evidence.mutationParams} />
          </div>

          {evidence.customer && (
            <div className="space-y-1.5">
              <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Targeted customer</p>
              <Link
                to={`/customers?focus=${evidence.customer.id}`}
                className="flex items-center gap-2 rounded-2xl border px-3 py-2 text-sm hover:bg-muted"
              >
                <UserIcon className="size-4 text-muted-foreground" />
                <span className="font-medium">{evidence.customer.name}</span>
                <span className="font-mono text-[11px] text-muted-foreground">{evidence.customer.id}</span>
                <span className="ml-auto text-xs text-muted-foreground">
                  {evidence.customer.accountAgeDays ?? "—"} days old ·{" "}
                  {evidence.customer.devices.length} device(s)
                </span>
              </Link>
            </div>
          )}
        </CardContent>
      </Card>

      {!compact && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">What the defense did with it</CardTitle>
            <CardDescription>
              {evidence.results.length === 0
                ? "This case has never been scored."
                : `${evidence.results.length} real scored result(s) — one per evaluation run that included this case.`}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {evidence.results.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Generated but not evaluated. No score is shown because none exists.
              </p>
            ) : (
              evidence.results.map((r, i) => (
                <div key={`${r.runId}-${i}`} className={cn("space-y-2 rounded-2xl border px-3 py-2.5", i > 0 && "opacity-70")}>
                  <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                    <span className="font-medium">
                      {r.riskScore === null ? "risk not on the 0–100 scale" : `${r.riskScore.toFixed(1)} / 100`}
                      <span className="ml-2 text-xs text-muted-foreground uppercase">{r.decision}</span>
                    </span>
                    <Badge
                      variant="outline"
                      className={cn(
                        "border-transparent text-[10px]",
                        r.actualLabel === "fraud" && r.detected && "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
                        r.actualLabel === "fraud" && !r.detected && "bg-destructive/10 text-destructive",
                        r.actualLabel !== "fraud" && !r.detected && "bg-amber-500/10 text-amber-600 dark:text-amber-400",
                        r.actualLabel !== "fraud" && r.detected && "bg-muted text-muted-foreground",
                      )}
                    >
                      {r.actualLabel === "fraud"
                        ? r.detected ? "Blocked" : "Missed"
                        : r.detected ? "Cleared" : "False positive"}
                    </Badge>
                  </div>
                  {r.modelSignals.length > 0 && (
                    <div className="flex flex-wrap gap-2 text-[11px]">
                      {r.modelSignals.map((s) => (
                        <span key={s.model} className="rounded-lg bg-muted px-2 py-0.5 font-mono">
                          {s.model} {typeof s.score === "number" ? s.score.toFixed(4) : "—"}
                        </span>
                      ))}
                    </div>
                  )}
                  {r.evidence.length > 0 && (
                    <ul className="space-y-0.5 font-mono text-[10px] text-muted-foreground">
                      {r.evidence.map((e) => (
                        <li key={e} className="break-words">· {e}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ))
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
