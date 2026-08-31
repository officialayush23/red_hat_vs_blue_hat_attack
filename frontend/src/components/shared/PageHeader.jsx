export function PageHeader({
  eyebrow,
  title,
  description,
  actions
}) {
  return <div className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between">
      <div className="space-y-1">
        {eyebrow ? <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{eyebrow}</p> : null}
        <h1 className="cn-font-heading text-2xl font-semibold text-foreground">{title}</h1>
        {description ? <p className="max-w-2xl text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>;
}
