import { Bundle, fmt, fmtSigned } from "../lib/data";
import { Plot } from "./Plot";
import { DataTable } from "./DataTable";
import { Term } from "./Term";
import { FactorICRow } from "../lib/types";

const GROUP_COLOR: Record<string, string> = {
  Valuation: "#4e79a7", Momentum: "#f28e2b", Volatility: "#17becf", Quality: "#59a14f",
  Investment: "#b07aa1", "Earnings Quality": "#e15759", Estimates: "#9c755f", Other: "#999",
};

export function FactorICView({ factorIC }: Bundle) {
  const rows = [...factorIC.factors].sort((a, b) => (b.mean_ic ?? -9) - (a.mean_ic ?? -9));
  const thin = rows.filter((r) => r.n_periods < 8).length;

  return (
    <div className="grid">
      <section className="card span-12">
        <h2>Per factor <Term id="ic">Information Coefficient</Term> (h={factorIC.horizon_q}Q)</h2>
        {thin > 0 && (
          <p className="callout warn small">
            ⚠ {thin} of {rows.length} factors have fewer than 8 scored quarters (yfinance fundamentals only reach
            back ~4–5 quarters), so their ICs here are anecdotes, not evidence — check the Periods column before
            reading anything into a bar. The price factors (momentum, reversal) carry the long history.
          </p>
        )}
        <p className="muted">
          Each bar is one direction aligned, <Term id="sectorneutral">sector neutral</Term> factor used
          <em> alone</em> as a score. A positive <Term id="ic">IC</Term> means the factor's documented red flag
          direction (for example rich <Term id="pe">valuation</Term>, low <Term id="momentum">momentum</Term>,
          high <Term id="accruals">accruals</Term>) actually predicts sector relative underperformance. Bars are
          colored by factor family; the whisker is one standard error.
        </p>
        <div className="help-note">
          <strong>What a factor is, and what this chart proves.</strong> A factor is a single measurable trait,
          for example how expensive a stock is or how much its share count grew over the past year. The model
          bets that each trait, pointed in its historically unfavorable direction, comes before weaker returns.
          This chart tests each trait on its own. A bar to the right of zero means that trait, by itself, leaned
          correctly toward the names that went on to underperform their peers; bars near zero added little in this
          sample. The blended sell score is simply the average of all these traits, so families that lean
          positive here are the ones carrying the signal, while families near zero are along for diversification
          rather than punch. A single strong factor is fragile; agreement across several families is what makes
          the combined ranking sturdier than any one input.
        </div>
        <Plot height={Math.max(320, rows.length * 26)}
          data={[{
            type: "bar", orientation: "h",
            x: rows.map((r) => r.mean_ic ?? 0).reverse(),
            y: rows.map((r) => r.factor).reverse(),
            marker: { color: rows.map((r) => GROUP_COLOR[r.group] ?? "#999").reverse() },
            error_x: { type: "data", array: rows.map((r) => (r.t_stat ? Math.abs((r.mean_ic ?? 0) / r.t_stat) : 0)).reverse(), visible: true, color: "#aaa" },
            hovertemplate: "%{y}: IC %{x:.4f}<extra></extra>",
          }]}
          layout={{ xaxis: { title: "mean IC (Fama MacBeth)", zeroline: true }, yaxis: { automargin: true } }} />
      </section>

      <section className="card span-12">
        <h3>Factor table</h3>
        <DataTable<FactorICRow>
          rows={rows}
          rowKey={(r) => r.factor}
          columns={[
            { key: "factor", label: "Factor" },
            { key: "group", label: "Family", render: (r) => (
              <span className="group-pill" style={{ background: GROUP_COLOR[r.group] ?? "#999" }}>{r.group}</span>
            ) },
            { key: "mean_ic", label: <>Mean <Term id="ic">IC</Term></>, align: "right", render: (r) => fmtSigned(r.mean_ic) },
            { key: "t_stat", label: <><Term id="tstat">t</Term> (<Term id="neweywest">NW</Term>)</>, align: "right", render: (r) => fmt(r.t_stat) },
            { key: "ir", label: <Term id="ir">IR</Term>, align: "right", render: (r) => fmt(r.ir) },
            { key: "hit_rate", label: <Term id="hitrate">Hit</Term>, align: "right", render: (r) => r.hit_rate != null ? `${Math.round(r.hit_rate * 100)}%` : "—" },
            { key: "n_periods", label: "Periods", align: "right" },
          ]}
        />
      </section>
    </div>
  );
}
