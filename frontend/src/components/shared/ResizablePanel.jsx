import { cn } from "@/lib/utils";

/**
 * The visible grab affordance. The hit area is deliberately wider than the
 * 1px rule it draws -- a 1px drag target is a target most people miss -- so the
 * element is 9px wide with the line centred inside it via a pseudo-element.
 */
export function ResizeHandle({ className, label = "Resize panel", ...props }) {
  return (
    <div
      aria-label={label}
      title="Drag to resize · double-click to reset · arrow keys when focused"
      className={cn(
        "group relative z-10 hidden w-2.5 shrink-0 cursor-col-resize touch-none select-none xl:block",
        "focus-visible:outline-none",
        className
      )}
      {...props}
    >
      <span
        aria-hidden="true"
        className={cn(
          "pointer-events-none absolute inset-y-0 left-1/2 w-px -translate-x-1/2 rounded-full",
          "bg-border transition-colors duration-150",
          "group-hover:bg-primary/60 group-focus-visible:bg-primary",
          "group-data-[dragging]:bg-primary"
        )}
      />
      <span
        aria-hidden="true"
        className={cn(
          "pointer-events-none absolute top-1/2 left-1/2 h-8 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full",
          "bg-border/0 transition-colors duration-150",
          "group-hover:bg-primary/40 group-focus-visible:bg-primary/70",
          "group-data-[dragging]:bg-primary"
        )}
      />
    </div>
  );
}
