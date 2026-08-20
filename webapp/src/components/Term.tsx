import { CSSProperties, ReactNode, SyntheticEvent, useCallback, useState } from "react";
import { GLOSSARY } from "../lib/glossary";

// Inline hoverable definition. <Term id="ic" /> renders the glossary label with
// a dotted underline and shows the definition on hover; pass children to change
// the visible text while keeping the same definition.
//
// Positioning is computed on hover rather than left to CSS. The tooltip used to
// be absolutely positioned inside its parent, so any scrolling or clipping
// ancestor cut it off: the drill down panel (overflow-y: auto) sliced the top
// off every definition in its metric row, and terms near the right edge ran off
// the panel. Fixed positioning escapes every clipping context, and the trigger
// rect decides which way to open so the box always lands on screen.
const TIP_WIDTH = 300;
const MARGIN = 10;
const GAP = 8;

export function Term({ id, children }: { id: keyof typeof GLOSSARY | string; children?: ReactNode }) {
  const entry = GLOSSARY[id as string];
  const [style, setStyle] = useState<CSSProperties>({});

  // Measure the trigger from the event itself. A ref would be the obvious
  // choice, but under the automatic JSX runtime a ref passed in the props
  // object is handed through as an ordinary prop and never binds, so it read
  // back null and the tooltip silently kept its clipped CSS position.
  const place = useCallback((e: SyntheticEvent<HTMLSpanElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const width = Math.min(TIP_WIDTH, vw - 2 * MARGIN);
    // clamp horizontally so the box never runs past either edge
    const left = Math.min(Math.max(MARGIN, r.left), vw - width - MARGIN);
    // open downward from the top half of the screen, upward from the bottom
    // half: whichever side has room, without needing the tooltip's height
    const openDown = r.top < vh / 2;
    setStyle({
      position: "fixed",
      left,
      width,
      maxHeight: openDown ? vh - r.bottom - GAP - MARGIN : r.top - GAP - MARGIN,
      overflowY: "auto",
      zIndex: 200,
      // clear the opposite edge explicitly: the stylesheet sets bottom, and
      // leaving both set would stretch the box between them
      ...(openDown
        ? { top: r.bottom + GAP, bottom: "auto" as const }
        : { bottom: vh - r.top + GAP, top: "auto" as const }),
    });
  }, []);

  if (!entry) return <>{children ?? id}</>;
  return (
    <span className="term" tabIndex={0}
          onMouseEnter={place} onFocus={place}>
      {children ?? entry.label}
      <span className="term-tip" role="tooltip" style={style}>
        <strong>{entry.label}</strong>
        {entry.def}
      </span>
    </span>
  );
}
