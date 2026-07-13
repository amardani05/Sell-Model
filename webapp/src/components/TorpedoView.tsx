import { useState } from "react";
import { Bundle, fmt, fmtSigned, decileColor } from "../lib/data";
import { Plot } from "./Plot";
import { DataTable } from "./DataTable";
import { Term } from "./Term";
import { Ticker, UniverseToggle, inUniverse } from "./TickerFlag";
import { TorpedoName } from "../lib/types";

export function TorpedoView({ meta, scores, torpedo }: Bundle) {
  const tierColors = meta.torpedo_tier_colors;
  const [universe, setUniverse] = useState<string>(meta.selection_index ?? "S&P 600");

  // contrast scatter: sell score (x) vs torpedo percentile (y), colored by sector
  const pts = scores.filter((r) => r.score != null && r.torpedo_pct != null
                                   && inUniverse(r.index_name, universe));
  const namesRows = torpedo.names.filter((r) => inUniverse(r.index_name, universe));
  const sectors = Array.from(new Set(pts.map((p) => p.gics_sector))).sort();
  const scoreVals = pts.map((p) => p.score as number).sort((a, b) => a - b);
  const xMid = scoreVals.length ? scoreVals[Math.floor(scoreVals.length / 2)] : 0;

  const traces = sectors.map((s) => {
    const sp = pts.filter((p) => p.gics_sector === s);
    return {
      type: "scatter" as const, mode: "markers" as const, name: s,
      x: sp.map((p) => p.score), y: sp.map((p) => p.torpedo_pct),
      text: sp.map((p) => `${p.ticker}${p.index_name ? " (" + p.index_name + ")" : ""} · ${s}<br>sell decile ${p.decile} · torpedo ${Math.round(p.torpedo_pct ?? 0)}`),
      hovertemplate: "%{text}<extra></extra>",
      marker: { size: 7, color: meta.sector_colors[s] ?? "#888", opacity: 0.8 },
    };
  });

  return (
    <div className="grid">
      <section className="card span-12">
        <div className="row-between">
          <h2>Torpedo screener — the absolute risk view</h2>
          <UniverseToggle value={universe} onChange={setUniverse} counts={meta.index_counts} />
        </div>
        <p>
          The <Term id="torpedo" /> answers the opposite question to the sell model. Instead of ranking a name
          against its sector peers, it ranks every name against the <strong>whole universe</strong> and targets
          <Term id="absoluterisk"><strong> absolute</strong></Term> blow up or drawdown risk. Each of
          the {meta.n_torpedo_features} risk features is <Term id="zscore">z scored</Term> across the entire
          universe (never within sector), sign aligned so higher always means more risk, averaged, then turned
          into a 0 to 100 <Term id="percentile" /> and a <Term id="tier" />.
        </p>
        <div className="help-note">
          Read the two views together. The sell model asks <em>will this lag its sector peers</em>; the torpedo
          asks <em>is this dangerous outright</em>. A cheap defensive name can be a sector relative sell yet a low
          torpedo risk; a whole frothy sector can screen high on the torpedo while its deciles net to neutral.
        </div>
        <div className="help-note">
          <strong>The four corners of the scatter below.</strong> Top right is the danger zone: a name that both
          looks weak against its sector peers and screens as risky against the whole market, the strongest case
          to review. Bottom right is a sector relative sell that is not otherwise fragile, often a fully valued
          but stable business that may simply lag cheaper peers. Top left is an outright risk that is still middle
          of the pack within its own sector, common when an entire sector is stretched. Bottom left is the
          comfortable zone, neither a relative laggard nor an absolute risk. The tiers below (Stable, Mainstream,
          Elevated) are plain language bands on the same absolute risk percentile.
        </div>
        <div className="quad-legend">
          {torpedo.tier_order.map((t) => {
            const c = torpedo.tier_counts.find((x) => x.torpedo_tier === t)?.n ?? 0;
            return <span key={t}><span className="tier-pill" style={{ background: tierColors[t] }}>{t}</span> {c} names</span>;
          })}
        </div>
      </section>

      <section className="card span-12">
        <h3>Relative vs absolute contrast</h3>
        <p className="muted small">
          Horizontal axis: sector neutral sell <Term id="relativereturn">relative risk</Term> score (right = more
          expected underperformance vs peers). Vertical axis: torpedo absolute risk <Term id="percentile" />
          (up = riskier than more of the universe). The <strong>top right</strong> is the double red flag zone:
          names that are both a sector relative sell and an absolute risk. Dashed lines mark the universe median
          sell score and the Elevated torpedo threshold (70).
        </p>
        <Plot height={520}
          data={traces}
          layout={{
            xaxis: { title: "sell relative risk score →", zeroline: false },
            yaxis: { title: "torpedo absolute risk percentile →", range: [0, 100] },
            shapes: [
              { type: "line", x0: xMid, x1: xMid, y0: 0, y1: 100, line: { color: "#aaa", dash: "dash", width: 1 } },
              { type: "line", x0: Math.min(...scoreVals), x1: Math.max(...scoreVals), y0: 70, y1: 70, line: { color: "#aaa", dash: "dash", width: 1 } },
            ],
            annotations: [
              { x: Math.max(...scoreVals), y: 98, xanchor: "right", showarrow: false, text: "double red flag", font: { color: "#b3001b", size: 11 } },
            ],
          }} />
      </section>

      <section className="card span-12">
        <h3>Highest absolute risk names (torpedo percentile, latest cross section)</h3>
        <p className="muted small">
          <Term id="tier" /> and universe <Term id="percentile" /> are absolute. The sell decile column is the
          sector neutral view on the same name, so you can see where the two disagree.
        </p>
        <DataTable<TorpedoName>
          rows={namesRows.slice(0, 30)}
          rowKey={(r) => r.ticker}
          columns={[
            { key: "ticker", label: "Ticker", render: (r) => <Ticker symbol={r.ticker} index={r.index_name} /> },
            { key: "gics_sector", label: "GICS Sector" },
            { key: "torpedo_tier", label: "Tier", render: (r) => (
              <span className="tier-pill" style={{ background: tierColors[r.torpedo_tier ?? ""] ?? "#999" }}>{r.torpedo_tier ?? "—"}</span>
            ) },
            { key: "torpedo_pct", label: "Torpedo pct", align: "right", render: (r) => r.torpedo_pct != null ? Math.round(r.torpedo_pct) : "—" },
            { key: "torpedo_score", label: "Risk z", align: "right", render: (r) => fmtSigned(r.torpedo_score) },
            { key: "decile", label: "Sell decile", align: "right", render: (r) => (
              <span className="decile-pill" style={{ background: decileColor(r.decile) }}>{r.decile ?? "—"}</span>
            ) },
            { key: "short_pct_float", label: "Short % float", align: "right", render: (r) => r.short_pct_float != null ? `${(r.short_pct_float * 100).toFixed(1)}%` : "—" },
          ]}
        />
      </section>
    </div>
  );
}
