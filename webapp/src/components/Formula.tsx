import { useEffect, useRef } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

// KaTeX is bundled locally (no CDN), so the static site stays self contained.
// throwOnError false: a bad expression renders as red source text instead of
// crashing the page. The trust callback enables \htmlData ONLY; formulas use
// it to annotate symbols with data-tip definitions. Tooltips are a single
// shared div appended to document.body and positioned per hover, so they show
// instantly (native title tooltips need a long steady hover) and can never be
// clipped by the formula strip's horizontal scroll container.

let tipEl: HTMLDivElement | null = null;
function tooltipEl(): HTMLDivElement {
  if (!tipEl) {
    tipEl = document.createElement("div");
    tipEl.className = "formula-tip";
    document.body.appendChild(tipEl);
  }
  return tipEl;
}

export function Formula({ tex, block = false }: { tex: string; block?: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);
  const html = katex.renderToString(tex, {
    displayMode: block,
    throwOnError: false,
    strict: false,
    trust: (ctx) => ctx.command === "\\htmlData",
  });

  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    const nodes = root.querySelectorAll<HTMLElement>("[data-tip]");
    const show = (e: Event) => {
      const el = e.currentTarget as HTMLElement;
      const tip = tooltipEl();
      tip.textContent = el.dataset.tip ?? "";
      tip.style.display = "block";
      tip.style.maxWidth = Math.min(320, window.innerWidth - 24) + "px";
      const r = el.getBoundingClientRect();
      const tr = tip.getBoundingClientRect();
      let left = r.left + r.width / 2 - tr.width / 2;
      left = Math.max(8, Math.min(left, window.innerWidth - tr.width - 8));
      let top = r.top - tr.height - 8;
      if (top < 8) top = r.bottom + 8;
      tip.style.left = left + "px";
      tip.style.top = top + "px";
    };
    const hide = () => { tooltipEl().style.display = "none"; };
    nodes.forEach((n) => {
      n.addEventListener("mouseenter", show);
      n.addEventListener("mouseleave", hide);
    });
    return () => {
      nodes.forEach((n) => {
        n.removeEventListener("mouseenter", show);
        n.removeEventListener("mouseleave", hide);
      });
      hide();
    };
  }, [html]);

  return (
    <span
      ref={ref}
      className={block ? "formula-block" : "formula-inline"}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
