import { useCallback, useEffect, useRef, useState } from "react";

/**
 * A draggable split between a fluid main column and a fixed-width side panel.
 *
 * Why a CSS custom property instead of React state during the drag:
 * a pointermove fires at display refresh rate, so driving the width through
 * setState re-renders the whole war room -- AttackStream, the agent trace, every
 * card -- 60+ times a second while the user is dragging, on a page that is
 * already streaming live rows from Supabase. Writing the variable straight onto
 * the container element moves the layout without re-rendering a single React
 * component. State is written once, on pointerup, so the value survives
 * re-render and can be persisted.
 *
 * Accessibility is not optional here: the handle is a real
 * role="separator" with aria-orientation/valuenow/valuemin/valuemax, it is
 * focusable, and it can be driven entirely from the keyboard. A split a mouse
 * can move and a keyboard cannot is a split half the users cannot move.
 */

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

export function useResizablePanel({
  storageKey,
  defaultWidth,
  minWidth = 280,
  maxWidth = 720,
  cssVar = "--panel-width",
  // Side the panel sits on. Dragging left must GROW a right-hand panel and
  // SHRINK a left-hand one, so the delta is signed by this.
  side = "right",
}) {
  const containerRef = useRef(null);
  const [width, setWidth] = useState(() => {
    try {
      const stored = Number(localStorage.getItem(storageKey));
      if (Number.isFinite(stored) && stored > 0) return clamp(stored, minWidth, maxWidth);
    } catch {
      // Storage unavailable (private mode, blocked site data). The default is a
      // fine answer -- never let a preference lookup break the layout.
    }
    return defaultWidth;
  });
  const [isDragging, setIsDragging] = useState(false);

  // The live value during a drag. Kept in a ref because pointermove must not
  // re-render; committed to state (and storage) on release.
  const liveWidth = useRef(width);

  const applyWidth = useCallback(
    (next) => {
      liveWidth.current = next;
      containerRef.current?.style.setProperty(cssVar, `${next}px`);
    },
    [cssVar]
  );

  const commitWidth = useCallback(
    (next) => {
      const clamped = clamp(Math.round(next), minWidth, maxWidth);
      applyWidth(clamped);
      setWidth(clamped);
      try {
        localStorage.setItem(storageKey, String(clamped));
      } catch {
        // Best-effort persistence. The panel still resizes for this session.
      }
    },
    [applyWidth, maxWidth, minWidth, storageKey]
  );

  const onPointerDown = useCallback(
    (event) => {
      // Ignore secondary buttons -- a right-click on the handle should open the
      // context menu, not start a drag the user cannot see themselves starting.
      if (event.button !== 0) return;
      event.preventDefault();

      const handle = event.currentTarget;
      // Pointer capture keeps events coming to the handle even when the pointer
      // outruns it, which it will: the pointer moves continuously and layout
      // updates in discrete frames.
      handle.setPointerCapture(event.pointerId);

      const startX = event.clientX;
      const startWidth = liveWidth.current;
      const direction = side === "right" ? -1 : 1;
      setIsDragging(true);

      let frame = 0;
      let pendingX = startX;

      const onMove = (moveEvent) => {
        pendingX = moveEvent.clientX;
        if (frame) return;
        // Coalesce to one layout write per animation frame. Without this a
        // high-polling-rate mouse can fire several pointermove events between
        // paints, and every one of them would force a synchronous reflow.
        frame = requestAnimationFrame(() => {
          frame = 0;
          applyWidth(clamp(startWidth + (pendingX - startX) * direction, minWidth, maxWidth));
        });
      };

      const onUp = () => {
        if (frame) cancelAnimationFrame(frame);
        handle.removeEventListener("pointermove", onMove);
        handle.removeEventListener("pointerup", onUp);
        handle.removeEventListener("pointercancel", onUp);
        try {
          handle.releasePointerCapture(event.pointerId);
        } catch {
          // The pointer can already be gone (device unplugged, tab hidden).
        }
        setIsDragging(false);
        commitWidth(liveWidth.current);
      };

      handle.addEventListener("pointermove", onMove);
      handle.addEventListener("pointerup", onUp);
      // pointercancel fires when the browser takes the pointer away -- a touch
      // becoming a scroll gesture, say. Without this the drag would never end
      // and the width would never be committed.
      handle.addEventListener("pointercancel", onUp);
    },
    [applyWidth, commitWidth, maxWidth, minWidth, side]
  );

  const onKeyDown = useCallback(
    (event) => {
      // Matches the WAI-ARIA window-splitter pattern: arrows nudge, Shift
      // coarsens, Home/End jump to the limits, Enter resets.
      const coarse = event.shiftKey ? 64 : 16;
      const direction = side === "right" ? -1 : 1;
      let next = null;

      if (event.key === "ArrowLeft") next = liveWidth.current + coarse * direction;
      else if (event.key === "ArrowRight") next = liveWidth.current - coarse * direction;
      else if (event.key === "Home") next = side === "right" ? maxWidth : minWidth;
      else if (event.key === "End") next = side === "right" ? minWidth : maxWidth;
      else if (event.key === "Enter" || event.key === " ") next = defaultWidth;

      if (next === null) return;
      event.preventDefault();
      commitWidth(next);
    },
    [commitWidth, defaultWidth, maxWidth, minWidth, side]
  );

  const reset = useCallback(() => commitWidth(defaultWidth), [commitWidth, defaultWidth]);

  // Keep the DOM variable in step with state after any render that did not come
  // from a drag -- first mount, and a reset triggered from elsewhere.
  useEffect(() => {
    containerRef.current?.style.setProperty(cssVar, `${width}px`);
  }, [cssVar, width]);

  // While dragging, the cursor must not flicker as it crosses other elements and
  // text must not select. Set on <body> because the pointer leaves the handle.
  useEffect(() => {
    if (!isDragging) return undefined;
    const { style } = document.body;
    const prevCursor = style.cursor;
    const prevSelect = style.userSelect;
    style.cursor = "col-resize";
    style.userSelect = "none";
    return () => {
      style.cursor = prevCursor;
      style.userSelect = prevSelect;
    };
  }, [isDragging]);

  return {
    width,
    isDragging,
    containerRef,
    reset,
    containerStyle: { [cssVar]: `${width}px` },
    handleProps: {
      role: "separator",
      tabIndex: 0,
      "aria-orientation": "vertical",
      "aria-valuenow": width,
      "aria-valuemin": minWidth,
      "aria-valuemax": maxWidth,
      onPointerDown,
      onKeyDown,
      onDoubleClick: reset,
      "data-dragging": isDragging ? "" : undefined,
    },
  };
}
