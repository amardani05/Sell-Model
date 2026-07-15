import { useMemo, useState } from "react";
import { Bundle, fmtSigned, decileColor } from "../lib/data";
import { DataTable } from "./DataTable";
import { Term } from "./Term";
import { Ticker } from "./TickerFlag";
import { ScoreRow } from "../lib/types";
import { factorLabel } from "../lib/factorMeta";

// Default long only sleeve overlaid out of the box; user can paste their own.
const SAMPLE = [
  "TDS", "PRDO", "MCRI", "CVCO", "UNFI", "CRGY", "AX", "PFBC", "ENVA", "NEOG",
  "KRYS", "FSS", "GTES", "MYRG", "DOCN", "KLIC", "VIAV", "CE", "CTRE", "AVA",
].join(", ");

export function PortfolioOverlayView({ meta, scores, drilldown, transitions, overrides }: Bundle) {
  const activeOv = overrides?.active ?? [];
  const ovFor = (tk: string) => activeOv.filter((o) => o.ticker === tk);
  const [text, setText] = useState(SAMPLE);
  const [copied, setCopied] = useState(false);
  const byTicker = useMemo(() => {
    const m = new Map<string, ScoreRow>();
    scores.forEach((r) => m.set(r.ticker.toUpperCase(), r));
    return m;
  }, [scores]);

  const tickers = text.split(/[\s,]+/).map((t) => t.trim().toUpperCase()).filter(Boolean);
  const held = tickers.map((t) => byTicker.get(t)).filter(Boolean) as ScoreRow[];
  const missing = tickers.filter((t) => !byTicker.has(t));
  const n = 10;

  const dd = drilldown.names;
  const topFlags = (tk: string, k = 2): { f: string; z: number }[] => {
    const d = dd[tk];
    if (!d) return [];
    return Object.entries(d.factors)
      .filter(([, v]) => v && v.z != null && (v.z as number) > 0.5)
      .map(([f, v]) => ({ f, z: v!.z as number }))
      .sort((a, b) => b.z - a.z)
      .slice(0, k);
  };
  const qoq = (tk: string): number | null => {
    const d = dd[tk];
    return d && d.decile != null && d.prev_decile != null ? d.decile - d.prev_decile : null;
  };
  const isNew = (tk: string): boolean => {
    const d = dd[tk];
    return !!d && (d.decile ?? 0) >= n - 1 && (d.prev_decile == null || (d.prev_decile ?? 0) < n - 1);
  };
  const isDouble = (r: ScoreRow): boolean =>
    (r.decile ?? 0) >= n - 1 && r.torpedo_tier === "Elevated";

  const inWorst = held.filter((r) => r.decile === n);
  const flagged = held.filter((r) => (r.decile ?? 0) >= n - 1);
  const newlyFlagged = held.filter((r) => isNew(r.ticker));
  const doubles = held.filter(isDouble);
  const meanDecile = held.length ? held.reduce((a, r) => a + (r.decile ?? 0), 0) / held.length : 0;

  const sortedHeld = [...held].sort((a, b) => (b.score ?? -99) - (a.score ?? -99));

  const copyReview = async () => {
    const rows = sortedHeld.map((r) => {
      const dq = qoq(r.ticker);
      const flags = topFlags(r.ticker).map((f) => `${factorLabel(f.f)} +${f.z.toFixed(1)}σ`).join("; ") || "—";
      const badges = [r.decile === n ? "REVIEW" : "", isNew(r.ticker) ? "NEW" : "", isDouble(r) ? "DOUBLE FLAG" : ""].filter(Boolean).join(" ");
      return `| ${r.ticker} | ${r.gics_sector} | ${r.decile ?? "—"} | ${dq == null ? "—" : dq > 0 ? `+${dq}` : dq} | ${flags} | ${r.torpedo_tier ?? "—"} | ${badges} |`;
    });
    const md = [
      `# Holdings risk review: ${drilldown.as_of} (Relative Sell Model)`,
      ``,
      `${held.length} matched · ${inWorst.length} in decile 10 · ${newlyFlagged.length} newly flagged (9 or 10) · ${doubles.length} double flagged · mean decile ${meanDecile.toFixed(1)}/10`,
      ``,
      `| Ticker | Sector | Decile | QoQ Δ | Top quantitative flags | Torpedo | Badges |`,
      `|---|---|---|---|---|---|---|`,
      ...rows,
      ``,
      `Decile 10 = worst expected sector relative return over the ${meta.horizon_phrase ?? `next ${meta.horizon_q}Q`}. Flags are sector neutral z scores; see the model dashboard for full per name decompositions. Screen output is evidence for review, not a trade instruction.`,
    ].join("\n");
    try { await navigator.clipboard.writeText(md); setCopied(true); setTimeout(() => setCopied(false), 1600); }
    catch { /* clipboard unavailable */ }
  };

  const matrix = transitions?.row_prob ?? [];

  return (
    <div className="grid">
      <section className="card span-12">
        <h2>Portfolio overlay: where do my holdings sit on the sell model?</h2>
        <p className="muted">
          Paste your long only sleeve (tickers, any separator). Each holding is matched to its
          <Term id="sectorneutral"> sector neutral</Term> <Term id="decile">decile</Term> and
          <Term id="relativereturn"> relative risk</Term> score from the latest cross section
          ({drilldown.as_of}). <strong>Click any ticker for the full factor decomposition and a copyable risks
          section draft.</strong>
        </p>
        <div className="help-note">
          <strong>How IMA should read this.</strong> A holding in decile 9 or 10 is a prompt to underwrite the thesis again, not an
          automatic sell: the model expects it to lag its sector peers over the {meta.horizon_phrase ?? `next ${meta.horizon_q} quarter(s)`},
          and the burden shifts to the thesis to explain why the flags are wrong or already priced. The
          <em> QoQ Δ</em> column shows decile movement since last quarter; deterioration is often more
          informative than level. <em>Double flag</em> means the name is both a sector relative sell (decile ≥ 9)
          and an Elevated absolute risk on the <Term id="torpedo">torpedo screener</Term>, the strongest prompt
          this platform produces.
        </div>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} spellCheck={false} />
        <div className="overlay-summary">
          <span><strong>{held.length}</strong> matched</span>
          <span className={inWorst.length ? "neg" : "pos"}><strong>{inWorst.length}</strong> in worst decile</span>
          <span className={newlyFlagged.length ? "neg" : ""}><strong>{newlyFlagged.length}</strong> newly flagged (9 or 10)</span>
          <span className={doubles.length ? "neg" : ""}><strong>{doubles.length}</strong> double flagged</span>
          <span>mean decile <strong>{meanDecile.toFixed(1)}</strong> / {n}</span>
          {missing.length > 0 && <span className="muted">not in universe: {missing.join(", ")}</span>}
        </div>
      </section>

      <section className="card span-12">
        <div className="row-between">
          <h3>Holdings risk review <span className="muted small">(quarterly meeting table)</span></h3>
          <button className="copy-btn" onClick={copyReview}>{copied ? "Copied ✓" : "Copy as markdown"}</button>
        </div>
        <DataTable<ScoreRow>
          rows={sortedHeld}
          rowKey={(r) => r.ticker}
          columns={[
            { key: "ticker", label: "Ticker", render: (r) => <Ticker symbol={r.ticker} index={r.index_name} /> },
            { key: "gics_sector", label: "GICS Sector" },
            { key: "decile", label: "Decile", align: "right", render: (r) => (
              <span className="decile-pill" style={{ background: decileColor(r.decile, n) }}>{r.decile ?? "—"}</span>
            ) },
            { key: "qoq", label: "QoQ Δ", align: "right", render: (r) => {
                const d = qoq(r.ticker);
                if (d == null) return <span className="muted">—</span>;
                return <span className={d > 0 ? "neg" : d < 0 ? "pos" : "muted"} style={{ fontWeight: 650 }}>
                  {d > 0 ? `▲ +${d}` : d < 0 ? `▼ ${d}` : "="}</span>;
              } },
            { key: "flags", label: "Top quantitative flags", render: (r) => {
                const fl = topFlags(r.ticker);
                return fl.length
                  ? <span className="mini-flags">{fl.map((f) => <span key={f.f}><b>{factorLabel(f.f)}</b> +{f.z.toFixed(1)}σ&nbsp;&nbsp;</span>)}</span>
                  : <span className="muted small">no factor above +0.5σ</span>;
              } },
            { key: "torpedo_tier", label: "Torpedo", render: (r) => r.torpedo_tier
                ? <span className="tier-pill" style={{ background: meta.torpedo_tier_colors[r.torpedo_tier] ?? "#999" }}>{r.torpedo_tier}</span>
                : "—" },
            { key: "score", label: "Score", align: "right", render: (r) => fmtSigned(r.score) },
            { key: "flag", label: "", render: (r) => (
              <span>
                {r.decile === n && <span className="flag-chip" style={{ background: "#b3001b" }}>REVIEW</span>}
                {isNew(r.ticker) && <span className="flag-chip new">NEW</span>}
                {isDouble(r) && <span className="flag-chip double">DOUBLE</span>}
                {ovFor(r.ticker).map((o, i) => (
                  <span key={i} className={"flag-chip " + (o.direction === "less_risky" ? "ov-less" : "ov-more")}
                    title={`Analyst override (${o.analyst}): ${o.direction} · ${o.reason_code}. ${o.note}`}>⚑</span>
                ))}
              </span>
            ) },
          ]}
        />
        <p className="muted small">
          NEW = entered decile 9 or 10 this quarter (was better last quarter). DOUBLE = decile ≥ 9 <em>and</em>
          {" "}Elevated torpedo tier. Click a ticker for its factor waterfall and risks section draft.
        </p>
      </section>

      <section className="card span-6">
        <h3>Universe flag churn this quarter</h3>
        <p className="muted small">
          Names entering deciles 9 or 10 between {transitions?.prev_date ?? "—"} and {transitions?.latest_date ?? "—"}
          {" "}across the whole universe: the screen's fresh output, worth a first look before they become
          consensus problems.
        </p>
        {transitions?.new_flagged?.length ? (
          <DataTable
            rows={transitions.new_flagged.slice(0, 15)}
            rowKey={(r) => r.ticker}
            columns={[
              { key: "ticker", label: "Ticker", render: (r) => <Ticker symbol={r.ticker} /> },
              { key: "sector", label: "Sector" },
              { key: "prev_decile", label: "Was", align: "right", render: (r) => r.prev_decile ?? "new" },
              { key: "decile", label: "Now", align: "right", render: (r) => (
                <span className="decile-pill" style={{ background: decileColor(r.decile, n) }}>{r.decile}</span>
              ) },
            ]}
          />
        ) : <p className="muted small">No churn data (needs at least two cross sections).</p>}
        {(transitions?.new_flagged?.length ?? 0) > 15 && (
          <p className="muted small">…and {(transitions?.new_flagged?.length ?? 0) - 15} more.</p>
        )}
      </section>

      <section className="card span-6">
        <h3><Term id="transitionmatrix">Decile transition matrix</Term>: how sticky is a flag?</h3>
        <p className="muted small">
          Row = decile this quarter, column = decile next quarter, cell = historical probability
          ({transitions?.n_date_pairs ?? 0} quarter pairs). Read row 10: the mass staying in 9 or 10 is the
          persistence of the sell flag; mass jumping back to 1 to 5 is how often a flag melts on its own.
        </p>
        {matrix.length ? (
          <div className="table-wrap">
            <table className="data-table" style={{ fontSize: 12 }}>
              <thead>
                <tr><th>from \ to</th>{matrix.map((_, j) => <th key={j} style={{ textAlign: "right" }}>D{j + 1}</th>)}</tr>
              </thead>
              <tbody>
                {matrix.map((row, i) => (
                  <tr key={i}>
                    <td><b>D{i + 1}</b></td>
                    {row.map((p, j) => (
                      <td key={j} style={{
                        textAlign: "right",
                        background: `rgba(29, 98, 168, ${Math.min(0.85, p * 1.8)})`,
                        color: p > 0.25 ? "#fff" : "inherit",
                      }}>{Math.round(p * 100)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="muted small">Needs at least two cross sections.</p>}
      </section>
    </div>
  );
}
