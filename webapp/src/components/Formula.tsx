import katex from "katex";
import "katex/dist/katex.min.css";

// KaTeX is bundled locally (no CDN), so the static site stays self contained.
// throwOnError false: a bad expression renders as red source text instead of
// crashing the page.
export function Formula({ tex, block = false }: { tex: string; block?: boolean }) {
  const html = katex.renderToString(tex, { displayMode: block, throwOnError: false });
  return (
    <span
      className={block ? "formula-block" : "formula-inline"}
      style={block ? { display: "block", margin: "10px 0", overflowX: "auto" } : undefined}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
