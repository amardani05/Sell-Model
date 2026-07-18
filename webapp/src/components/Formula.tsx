import katex from "katex";
import "katex/dist/katex.min.css";

// KaTeX is bundled locally (no CDN), so the static site stays self contained.
// throwOnError false: a bad expression renders as red source text instead of
// crashing the page. The trust callback enables \htmlData ONLY, which the
// formulas use to annotate symbols; its data-tip attributes are converted to
// native title attributes so every symbol shows a plain language tooltip on
// hover without any positioning code.
export function Formula({ tex, block = false }: { tex: string; block?: boolean }) {
  let html = katex.renderToString(tex, {
    displayMode: block,
    throwOnError: false,
    strict: false,
    trust: (ctx) => ctx.command === "\\htmlData",
  });
  html = html.replace(/data-tip="([^"]*)"/g, 'title="$1" data-tip="$1"');
  return (
    <span
      className={block ? "formula-block" : "formula-inline"}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
