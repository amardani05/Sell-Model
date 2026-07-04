import { ReactNode, useState } from "react";
import { Bundle, fmt, fmtSigned, fmtPct } from "../lib/data";
import { Plot } from "./Plot";
import { DataTable } from "./DataTable";
import { Term } from "./Term";
import { BacktestSleeve } from "../lib/types";

export function ValidationBacktestView({ meta, validation, backtest }: Bundle) {
  const horizons = meta.horizons_available.map(String);
  const [h, setH] = useState<string>(String(meta.horizon_q));
  const ic = validation.ic[h];
  const dec = validation.deciles[h];

  return (
    <div className="grid">
      <section className="card span-12">
        <div className="row-between">
          <h2>Validation — does the score rank forward relative returns?</h2>
          <div className="seg">
            {horizons.map((hh) => (
              <button key={hh} className={h === hh ? "active" : ""} onClick={() => setH(hh)}>{hh}Q</button>
            ))}
          </div>
        </div>
        <p className="muted">
          Sign convention: <Term id="ic">IC</Term> = minus the <Term id="spearman">Spearman correlation</Term>
          between the score and the forward relative return, so <strong>positive means skill</strong>. The mean
          IC is averaged <Term id="famamacbeth">Fama MacBeth</Term> style with a <Term id="neweywest">Newey
          West</Term> (5 lag) <Term id="tstat">t statistic</Term>. <Term id="walkforward">Walk forward</Term>
          only: features at t use data on or before t, labels use returns in the window after t out to t plus {h}
          quarters.
        </p>
        <div className="metric-row">
          <Metric label={<>Mean <Term id="ic">IC</Term></>} value={fmtSigned(ic?.mean_ic)} good={(ic?.mean_ic ?? 0) > 0} />
          <Metric label={<><Term id="tstat">t statistic</Term> (<Term id="neweywest">NW</Term>)</>} value={fmt(ic?.t_stat)} good={Math.abs(ic?.t_stat ?? 0) > 2} />
          <Metric label={<Term id="ir">IR</Term>} value={fmt(ic?.ir)} />
          <Metric label={<Term id="hitrate">Hit rate</Term>} value={ic ? `${Math.round((ic.hit_rate ?? 0) * 100)}%` : "—"} />
          <Metric label="Periods" value={String(ic?.n_periods ?? 0)} />
        </div>
      </section>

      <section className="card span-7">
        <h3><Term id="ic">IC</Term> time series</h3>
        {ic?.series.length ? (
          <Plot height={300}
            data={[
              { type: "bar", x: ic.series.map((s) => s.date), y: ic.series.map((s) => s.ic),
                marker: { color: ic.series.map((s) => (s.ic >= 0 ? "#2c7a4b" : "#b3001b")) }, name: "IC" },
              { type: "scatter", mode: "lines", x: ic.series.map((s) => s.date),
                y: cumMean(ic.series.map((s) => s.ic)), line: { color: "#1d2733", width: 2 }, name: "cumulative mean" },
            ]}
            layout={{ yaxis: { title: "IC", zeroline: true } }} />
        ) : <Empty />}
      </section>

      <section className="card span-5">
        <h3>Decile <Term id="monotonicity">monotonicity</Term></h3>
        <p className="muted small">Mean forward <Term id="relativereturn">relative return</Term> by sell
          <Term id="decile"> decile</Term>. A good model slopes down (ρ = {fmt(dec?.monotonicity_rho)}): a higher
          sell decile means a worse relative return.</p>
        {dec?.per_decile_mean.length ? (
          <Plot height={300}
            data={[{
              type: "bar",
              x: dec.per_decile_mean.map((d) => `D${d.decile}`),
              y: dec.per_decile_mean.map((d) => d.mean_rel_ret),
              marker: { color: dec.per_decile_mean.map((d) => (d.mean_rel_ret >= 0 ? "#2c7a4b" : "#b3001b")) },
              hovertemplate: "%{x}: %{y:.4f}<extra></extra>",
            }]}
            layout={{ yaxis: { title: "mean fwd relative return", zeroline: true } }} />
        ) : <Empty />}
        <p className="small">Spread (best − worst) = <strong>{fmtSigned(dec?.spread_mean)}</strong> · t = {fmt(dec?.spread_tstat)}</p>
      </section>

      <section className="card span-6">
        <h3><Term id="calibration">Calibration</Term></h3>
        <p className="muted small">Pooled mean realized <Term id="relativereturn">relative return</Term> by score
          quantile (1 = lowest score, 10 = highest sell risk). A well calibrated model steps downward.</p>
        {validation.calibration.length ? (
          <Plot height={280}
            data={[{
              type: "scatter", mode: "markers+lines",
              x: validation.calibration.map((c) => c.score_q),
              y: validation.calibration.map((c) => c.mean_rel_ret),
              marker: { size: 9, color: "#34516b" },
              hovertemplate: "q%{x}: %{y:.4f}<extra></extra>",
            }]}
            layout={{ xaxis: { title: "score quantile (low→high sell-risk)" }, yaxis: { title: "mean rel. return", zeroline: true } }} />
        ) : <Empty />}
      </section>

      <section className="card span-6">
        <h3><Term id="equalweight">Equal weight</Term> baseline vs <Term id="learnedweight">learned weights</Term> (<Term id="oos">OOS</Term>)</h3>
        <DataTable
          rows={validation.model_comparison}
          rowKey={(r) => r.score_col}
          columns={[
            { key: "model", label: "Model" },
            { key: "mean_ic", label: <>Mean <Term id="ic">IC</Term></>, align: "right", render: (r) => fmtSigned(r.mean_ic) },
            { key: "t_stat", label: <Term id="tstat">t</Term>, align: "right", render: (r) => fmt(r.t_stat) },
            { key: "ir", label: <Term id="ir">IR</Term>, align: "right", render: (r) => fmt(r.ir) },
            { key: "hit_rate", label: <Term id="hitrate">Hit</Term>, align: "right", render: (r) => `${Math.round(r.hit_rate * 100)}%` },
          ]}
        />
        <p className="small muted">
          Default scorer = <code>{meta.default_score}</code>. The learned model only becomes the default if it
          <strong> strictly beats</strong> the baseline <Term id="oos">out of sample</Term>, otherwise the
          <Term id="equalweight"> equal weight</Term> baseline stays in charge.
        </p>
      </section>

      <h2 className="span-12 section-head">Backtest — quarterly rebalance, {meta.cost_bps} <Term id="turnover">bps</Term> cost</h2>
      {Object.entries(backtest).map(([key, sleeve]) => (
        <SleeveCard key={key} sleeve={sleeve} benchmark={meta.benchmark} />
      ))}
    </div>
  );
}

function SleeveCard({ sleeve, benchmark }: { sleeve: BacktestSleeve; benchmark: string }) {
  const m = sleeve.metrics;
  const hasBench = sleeve.curve.some((c) => c.benchmark != null);
  return (
    <section className="card span-6">
      <h3>{sleeve.name}</h3>
      <div className="metric-row">
        <Metric label={<Term id="cagr">CAGR</Term>} value={fmtPct(m.cagr)} good={(m.cagr ?? 0) > 0} />
        <Metric label={<Term id="sharpe">Sharpe</Term>} value={fmt(m.sharpe)} good={(m.sharpe ?? 0) > 0} />
        <Metric label={<Term id="maxdd">Max DD</Term>} value={fmtPct(m.max_drawdown)} />
        <Metric label="Vol" value={fmtPct(m.vol)} />
        <Metric label={<Term id="turnover">Turnover</Term>} value={fmtPct(m.avg_turnover, 0)} />
      </div>
      <Plot height={280}
        data={[
          { type: "scatter", mode: "lines", x: sleeve.curve.map((c) => c.date),
            y: sleeve.curve.map((c) => c.strategy), line: { color: "#1d62a8", width: 2 }, name: "strategy" },
          ...(hasBench ? [{
            type: "scatter" as const, mode: "lines" as const, x: sleeve.curve.map((c) => c.date),
            y: sleeve.curve.map((c) => c.benchmark), line: { color: "#999", width: 1.5, dash: "dot" as const }, name: benchmark,
          }] : []),
        ]}
        layout={{ yaxis: { title: "growth of $1" } }} />
    </section>
  );
}

function Metric({ label, value, good }: { label: ReactNode; value: string; good?: boolean }) {
  return (
    <div className="metric">
      <span className="metric-label">{label}</span>
      <span className={"metric-value" + (good === undefined ? "" : good ? " pos" : " neg")}>{value}</span>
    </div>
  );
}
const Empty = () => <p className="muted">No data for this horizon (insufficient labeled cross sections).</p>;
function cumMean(xs: number[]): number[] {
  let s = 0; return xs.map((x, i) => { s += x; return s / (i + 1); });
}
