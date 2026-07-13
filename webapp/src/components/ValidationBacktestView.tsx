import { ReactNode, useState } from "react";
import { Bundle, fmt, fmtSigned, fmtPct } from "../lib/data";
import { Plot } from "./Plot";
import { DataTable } from "./DataTable";
import { Term } from "./Term";
import { BacktestSleeve, CalibrationRow, EraICRow, MCTier } from "../lib/types";

const TIER_COLORS: Record<string, string> = {
  full: "#8893a0", ex10: "#1d62a8", ex9_10: "#2c7a4b", top_half: "#6a4aa0",
};

export function ValidationBacktestView({ meta, validation, backtest, mcSim, exclusions, overrides }: Bundle) {
  const horizons = meta.horizons_available.map(String);
  const [h, setH] = useState<string>(String(meta.horizon_q));
  const ic = validation.ic[h];
  const dec = validation.deciles[h];
  const cal = validation.calibration ?? [];
  const evAll = (validation.event_study ?? []).filter((e) => e.cohort === "all");
  const evEnt = (validation.event_study ?? []).filter((e) => e.cohort === "entrant");
  const eras = validation.eras ?? [];
  const eraIC = validation.era_ic ?? [];
  const firstFull = eras.find((e) => e.era === "full-factor")?.date ?? null;

  const sleeves = backtest.sleeves ?? {};
  const holdAll = sleeves["hold_all"];
  const avoid = sleeves["avoid_worst"];
  const bench = sleeves["benchmark"];
  const segYear = backtest.segments?.by_year ?? [];
  const segRegime = backtest.segments?.by_regime ?? [];
  const tiers = mcSim?.tiers ?? {};

  return (
    <div className="grid">
      {/* ================= VALIDATION HEADER ================= */}
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
          West</Term> <Term id="tstat">t statistic</Term> whose lags scale with the label overlap.
          <Term id="walkforward"> Walk forward</Term> only: features at t use data on or before t, labels use
          returns in the window after t out to t plus {h} quarters.
        </p>
        <div className="metric-row">
          <Metric label={<>Mean <Term id="ic">IC</Term></>} value={fmtSigned(ic?.mean_ic)} good={(ic?.mean_ic ?? 0) > 0} />
          <Metric label={<><Term id="tstat">t statistic</Term> (<Term id="neweywest">NW</Term>)</>} value={fmt(ic?.t_stat)} good={Math.abs(ic?.t_stat ?? 0) > 2} />
          <Metric label={<Term id="ir">IR</Term>} value={fmt(ic?.ir)} />
          <Metric label={<Term id="hitrate">Hit rate</Term>} value={ic ? `${Math.round((ic.hit_rate ?? 0) * 100)}%` : "—"} />
          <Metric label="Periods" value={String(ic?.n_periods ?? 0)} />
          <Metric label={<><Term id="splice">Labels excluded</Term></>} value={String(exclusions?.n_labels_excluded ?? 0)} />
        </div>
        {eraIC.length > 0 && (
          <>
            <h3 style={{ marginTop: 6 }}><Term id="coveragera">Coverage eras</Term> — which model does this history actually test?</h3>
            <p className="muted small">
              yfinance fundamentals reach back only ~4–5 quarters, so older cross sections were scored by the two
              price factors alone. Any headline number that pools the eras is answering a mixed question; read
              this split first.
            </p>
            <DataTable<EraICRow>
              rows={eraIC}
              rowKey={(r) => r.era}
              columns={[
                { key: "era", label: "Era", render: (r) => r.era === "price-only"
                    ? <span><b>price-only</b> <span className="muted small">(momentum + reversal)</span></span>
                    : <span><b>full-factor</b> <span className="muted small">(all {meta.n_factors} factors)</span></span> },
                { key: "mean_ic", label: <>Mean <Term id="ic">IC</Term></>, align: "right", render: (r) => fmtSigned(r.mean_ic) },
                { key: "t_stat", label: <Term id="tstat">t</Term>, align: "right", render: (r) => fmt(r.t_stat) },
                { key: "ir", label: <Term id="ir">IR</Term>, align: "right", render: (r) => fmt(r.ir) },
                { key: "n_periods", label: "Quarters", align: "right" },
              ]}
            />
            {(eraIC.find((e) => e.era === "full-factor")?.n_periods ?? 0) < 8 && (
              <p className="callout warn small">
                ⚠ The full factor era spans only
                {" "}{eraIC.find((e) => e.era === "full-factor")?.n_periods ?? 0} scored quarter(s): the 15 factor
                composite is essentially <strong>unproven on real data</strong>. Everything below is machinery you
                can trust and history you should read as a momentum/reversal test until deeper fundamentals land.
              </p>
            )}
          </>
        )}
      </section>

      {/* ================= IC OVER TIME ================= */}
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
            layout={{
              yaxis: { title: "IC", zeroline: true },
              shapes: firstFull ? [{ type: "line", x0: firstFull, x1: firstFull, yref: "paper", y0: 0, y1: 1,
                                     line: { color: "#c98a00", dash: "dot", width: 2 } }] : [],
              annotations: firstFull ? [{ x: firstFull, yref: "paper", y: 1.04, showarrow: false,
                                          text: "fundamentals arrive →", font: { size: 11, color: "#c98a00" } }] : [],
            }} />
        ) : <Empty />}
      </section>

      <section className="card span-5">
        <h3>IC by calendar year <span className="muted small">(each year stands alone)</span></h3>
        {validation.yearly_ic?.length ? (
          <Plot height={300}
            data={[{
              type: "bar",
              x: validation.yearly_ic.map((r) => String(r.year)),
              y: validation.yearly_ic.map((r) => r.mean_ic),
              marker: { color: validation.yearly_ic.map((r) => ((r.mean_ic ?? 0) >= 0 ? "#2c7a4b" : "#b3001b")) },
              hovertemplate: "%{x}: IC %{y:.4f}<extra></extra>",
            }]}
            layout={{ yaxis: { title: "mean IC", zeroline: true } }} />
        ) : <Empty />}
        <p className="muted small">Independent windows: a mean carried by one lucky year shows up here immediately.</p>
      </section>

      {/* ================= CALIBRATION ================= */}
      <section className="card span-6">
        <h3><Term id="calibration">Calibration</Term> — return by score bucket</h3>
        <p className="muted small">
          Buckets are cut <strong>within each quarter</strong>, then averaged across quarters
          (<Term id="famamacbeth">Fama MacBeth</Term>). Error bars are ±2 <Term id="standarderror">standard
          errors</Term>. The <Term id="winsorizedmean">winsorized mean</Term> and median are the skew robust
          reads: relative returns have a long right tail, so a plain mean can be carried by a few lottery
          quarters. A working model steps downward left to right.
        </p>
        {cal.length ? (
          <Plot height={320}
            data={[
              { type: "scatter", mode: "markers", name: "mean ±2SE",
                x: cal.map((c) => c.score_q), y: cal.map((c) => c.mean_rel_ret),
                error_y: { type: "data", array: cal.map((c) => 2 * (c.se ?? 0)), visible: true, color: "#98a7b8" },
                marker: { size: 9, color: "#34516b" } },
              { type: "scatter", mode: "lines+markers", name: "winsorized mean",
                x: cal.map((c) => c.score_q), y: cal.map((c) => c.mean_rel_ret_w),
                line: { color: "#1d62a8", width: 2 }, marker: { size: 5 } },
              { type: "scatter", mode: "lines+markers", name: "median",
                x: cal.map((c) => c.score_q), y: cal.map((c) => c.median_rel_ret),
                line: { color: "#c98a00", width: 2, dash: "dot" }, marker: { size: 5 } },
            ]}
            layout={{ xaxis: { title: "score bucket (1 = best expected → 10 = worst)", dtick: 1 },
                      yaxis: { title: "fwd relative return", zeroline: true } }} />
        ) : <Empty />}
      </section>

      <section className="card span-6">
        <h3><Term id="reliability">Reliability</Term> — P(underperform sector) by bucket</h3>
        <p className="muted small">
          The probability view: for each score bucket, how often did names actually trail their sector median
          over the next {h} quarter(s)? 50% (dashed) is a coin flip because the target is relative to the
          median. A useful sell model pushes the right hand buckets meaningfully above 50%. This chart is the
          honest translation of the score into the language a PM uses.
        </p>
        {cal.length ? (
          <Plot height={320}
            data={[{
              type: "scatter", mode: "lines+markers", name: "P(underperform) ±2SE",
              x: cal.map((c) => c.score_q),
              y: cal.map((c) => c.p_underperform),
              error_y: { type: "data", array: cal.map((c) => 2 * (c.p_underperform_se ?? 0)), visible: true, color: "#d6a5ab" },
              line: { color: "#b3001b", width: 2 }, marker: { size: 7 },
              hovertemplate: "bucket %{x}: %{y:.1%}<extra></extra>",
            }]}
            layout={{
              xaxis: { title: "score bucket (1 = best expected → 10 = worst)", dtick: 1 },
              yaxis: { title: "P(underperform sector median)", tickformat: ".0%" },
              shapes: [{ type: "line", x0: 1, x1: 10, y0: 0.5, y1: 0.5, line: { color: "#888", dash: "dash", width: 1 } }],
            }} />
        ) : <Empty />}
      </section>

      {/* ================= EVENT STUDY + DECILES ================= */}
      <section className="card span-7">
        <h3><Term id="eventstudy">Event study</Term> — what happens after a name is flagged</h3>
        <p className="muted small">
          Cumulative average sector relative return in the quarters after sitting in the worst decile (k = 0 is
          the first quarter after the flag). "New entrants" are names that just fell into decile 10 that
          quarter. This is the deck ready read: <em>"names we flag go on to lag their sector by X% over the
          next N quarters"</em> — provided the curve is negative and its error bars exclude zero.
        </p>
        {evAll.length ? (
          <Plot height={320}
            data={[
              { type: "scatter", mode: "lines+markers", name: `all flagged (n=${evAll[0]?.n ?? 0})`,
                x: evAll.map((e) => e.k + 1), y: evAll.map((e) => e.cum_mean),
                line: { color: "#1d62a8", width: 2 }, marker: { size: 7 },
                error_y: { type: "data", array: evAll.map((e) => 2 * (e.se ?? 0)), visible: true, color: "#9db8d4" } },
              { type: "scatter", mode: "lines+markers", name: `new entrants (n=${evEnt[0]?.n ?? 0})`,
                x: evEnt.map((e) => e.k + 1), y: evEnt.map((e) => e.cum_mean),
                line: { color: "#b3001b", width: 2, dash: "dot" }, marker: { size: 7 },
                error_y: { type: "data", array: evEnt.map((e) => 2 * (e.se ?? 0)), visible: true, color: "#d6a5ab" } },
              { type: "scatter", mode: "lines", name: "all flagged, winsorized",
                x: evAll.map((e) => e.k + 1), y: cumSum(evAll.map((e) => e.mean_rel_ret_w ?? 0)),
                line: { color: "#8fb3d9", width: 1.5, dash: "dash" } },
              { type: "scatter", mode: "lines", name: "new entrants, winsorized",
                x: evEnt.map((e) => e.k + 1), y: cumSum(evEnt.map((e) => e.mean_rel_ret_w ?? 0)),
                line: { color: "#d99aa4", width: 1.5, dash: "dash" } },
            ]}
            layout={{ xaxis: { title: "quarters after flag", dtick: 1 },
                      yaxis: { title: "cumulative mean relative return", zeroline: true, tickformat: ".1%" } }} />
        ) : <Empty />}
        <p className="muted small">
          If the solid (plain mean) and dashed (<Term id="winsorizedmean">winsorized</Term>) curves diverge, the
          flagged bucket's outcome is being carried by a handful of extreme names — decile 10 holds the
          universe's most volatile names, whose <em>mean</em> can rise on lottery winners even when the typical
          flagged name goes nowhere.
        </p>
      </section>

      <section className="card span-5">
        <h3>Decile <Term id="monotonicity">monotonicity</Term></h3>
        <p className="muted small">Forward <Term id="relativereturn">relative return</Term> by sell
          <Term id="decile"> decile</Term> — mean, <Term id="winsorizedmean">winsorized mean</Term>, and median
          (ρ = {fmt(dec?.monotonicity_rho)}; a good model slopes down).</p>
        {dec?.per_decile_mean.length ? (
          <Plot height={320}
            data={[
              { type: "bar", name: "mean",
                x: dec.per_decile_mean.map((d) => `D${d.decile}`),
                y: dec.per_decile_mean.map((d) => d.mean_rel_ret),
                marker: { color: "#98a7b8" } },
              { type: "scatter", mode: "lines+markers", name: "winsorized mean",
                x: dec.per_decile_mean.map((d) => `D${d.decile}`),
                y: dec.per_decile_mean.map((d) => d.mean_rel_ret_w),
                line: { color: "#1d62a8", width: 2 } },
              { type: "scatter", mode: "lines+markers", name: "median",
                x: dec.per_decile_mean.map((d) => `D${d.decile}`),
                y: dec.per_decile_mean.map((d) => d.median_rel_ret),
                line: { color: "#c98a00", width: 2, dash: "dot" } },
            ]}
            layout={{ yaxis: { title: "fwd relative return", zeroline: true } }} />
        ) : <Empty />}
        <p className="small">Spread (best − worst) = <strong>{fmtSigned(dec?.spread_mean)}</strong> · t = {fmt(dec?.spread_tstat)}</p>
      </section>

      {/* ================= MODEL COMPARISON ================= */}
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
          Default scorer = <code>{meta.default_score}</code>. Promotion now requires a <strong>paired</strong>
          {" "}<Term id="tstat">t test</Term> on the per date IC difference
          {validation.promotion
            ? <> — this run: diff {fmtSigned(validation.promotion.mean_diff, 4)}, t = {fmt(validation.promotion.t_stat)}
                over {validation.promotion.n_periods} dates → <strong>{validation.promotion.promote ? "promoted" : "baseline kept"}</strong>.</>
            : <> (learned model not fitted this run).</>}
          {" "}A point estimate edge is noise, not a win.
        </p>
      </section>

      <section className="card span-6">
        <h3>Data integrity gate</h3>
        <p className="muted small">
          Forward return windows spanning a <Term id="splice">splice artifact</Term> (or beyond a 50x error
          net) are excluded from every statistic on this page and logged here — never silently used. One such
          artifact (a bankruptcy emergence spliced into one ticker at +13,000%) previously made calibration
          bucket 4 look like the best performer. Genuine moonshots (GME, MARA in 2020–21) are deliberately
          kept: the skew they cause is handled by the median / winsorized views, not by deletion.
        </p>
        <div className="metric-row">
          <Metric label="Labels excluded" value={String(exclusions?.n_labels_excluded ?? 0)} />
          <Metric label="Tickers affected" value={String(exclusions?.n_tickers ?? 0)} />
          {Object.entries(exclusions?.reasons ?? {}).map(([k, v]) => (
            <Metric key={k} label={k} value={String(v)} />
          ))}
        </div>
        {exclusions?.rows?.length ? (
          <DataTable
            rows={exclusions.rows.slice(0, 8)}
            rowKey={(r, i) => `${r.ticker}-${r.date}-${r.horizon_q}-${i}`}
            columns={[
              { key: "ticker", label: "Ticker" },
              { key: "date", label: "Window start", render: (r) => r.date.slice(0, 10) },
              { key: "horizon_q", label: "h", align: "right" },
              { key: "reason", label: "Reason" },
              { key: "value", label: "Raw value", align: "right", render: (r) => r.value != null ? fmtPct(r.value, 0) : "—" },
            ]}
          />
        ) : <p className="muted small">No exclusions in this run.</p>}
        {(exclusions?.rows?.length ?? 0) > 8 && (
          <p className="muted small">…and {(exclusions?.rows?.length ?? 0) - 8} more in <code>data/exclusions.json</code>.</p>
        )}
      </section>

      {/* ================= OVERRIDE SCOREBOARD ================= */}
      <section className="card span-12">
        <h3>Analyst override scoreboard</h3>
        <p className="muted small">
          Overrides are attributed, expiring annotations filed against the model's view (see the drill down's
          "Add override" and <code>docs/override-layer-design.md</code>). They never change a score. Each quarter
          an overridden name realizes a relative return, we check who was right: the analyst's direction or the
          model's. The clinical vs statistical prediction literature (Meehl 1954; Grove &amp; Meehl 2000) predicts
          the <code>thesis_disagreement</code> bucket will lose to the model — this table finds out.
        </p>
        {(() => {
          const sb = overrides?.scoreboard as any;
          if (!sb || !sb.n_scored_obs) {
            return <p className="muted small">
              {overrides?.active?.length
                ? `${overrides.active.length} active override(s) on file — none has realized a scoreable quarter yet.`
                : "No overrides on file yet. File the first one from any name's drill down panel."}
            </p>;
          }
          return (
            <>
              <div className="metric-row">
                <Metric label="Scored observations" value={String(sb.n_scored_obs)} />
                <Metric label="Analyst hit rate" value={`${Math.round((sb.analyst_hit_rate ?? 0) * 100)}%`}
                  good={(sb.analyst_hit_rate ?? 0) > 0.5} />
                <Metric label="Model hit rate" value={`${Math.round((sb.model_hit_rate ?? 0) * 100)}%`}
                  good={(sb.model_hit_rate ?? 0) > 0.5} />
                <Metric label="Overrides filed" value={String(sb.n_overrides)} />
              </div>
              <DataTable
                rows={sb.by_reason}
                rowKey={(r: any) => r.reason_code}
                columns={[
                  { key: "reason_code", label: "Reason code" },
                  { key: "n_obs", label: "Obs", align: "right" },
                  { key: "analyst_hit_rate", label: "Analyst hit", align: "right",
                    render: (r: any) => `${Math.round(r.analyst_hit_rate * 100)}%` },
                  { key: "avg_rel_ret", label: "Avg rel ret", align: "right",
                    render: (r: any) => fmtPct(r.avg_rel_ret) },
                ]}
              />
            </>
          );
        })()}
      </section>

      {/* ================= BACKTEST ================= */}
      <h2 className="span-12 section-head">Backtest — quarterly rebalance, {meta.cost_bps} <Term id="turnover">bps</Term> cost</h2>
      <div className="help-note span-12">
        <strong>The screen is judged against its own equal weight universe, not the ETF.</strong> An equal weight
        small cap portfolio structurally beats the cap weighted {meta.benchmark}, so comparing "avoid the worst
        decile" to {meta.benchmark} would credit the model with the equal weight effect. The fair test is the
        gap between the two solid lines: everything equal weight, with and without the flagged decile.
        {" "}{meta.benchmark} stays on the chart as market context. History remains survivorship friendly until a
        true point in time membership store is supplied, as flagged on the Overview.
      </div>

      <section className="card span-7">
        <h3>Growth of $1</h3>
        <Plot height={340}
          data={[
            ...(holdAll ? [{ type: "scatter" as const, mode: "lines" as const, name: "hold all (EW universe)",
              x: holdAll.curve.map((c) => c.date), y: holdAll.curve.map((c) => c.strategy),
              line: { color: "#8893a0", width: 2 } }] : []),
            ...(avoid ? [{ type: "scatter" as const, mode: "lines" as const, name: "avoid worst decile",
              x: avoid.curve.map((c) => c.date), y: avoid.curve.map((c) => c.strategy),
              line: { color: "#1d62a8", width: 2.5 } }] : []),
            ...(bench && bench.curve.length ? [{ type: "scatter" as const, mode: "lines" as const, name: meta.benchmark,
              x: bench.curve.map((c) => c.date), y: bench.curve.map((c) => c.strategy),
              line: { color: "#999", width: 1.5, dash: "dot" as const } }] : []),
          ]}
          layout={{ yaxis: { title: "growth of $1" } }} />
      </section>

      <section className="card span-5">
        <h3>Metrics</h3>
        <MetricsTable sleeves={[holdAll, avoid, bench].filter(Boolean) as BacktestSleeve[]} />
        {avoid?.metrics?.excess_cagr_vs_base != null && (
          <div className="help-note">
            <strong>Screen value added</strong> (avoid worst − hold all):
            {" "}<strong>{fmtPct(avoid.metrics.excess_cagr_vs_base as number, 2)}/yr</strong>
            {" "}· <Term id="trackingerror">TE</Term> {fmtPct(avoid.metrics.tracking_error as number)}
            {" "}· IR {fmt(avoid.metrics.ir_vs_base as number)}
            {" "}· hit {avoid.metrics.hit_rate_vs_base != null ? `${Math.round((avoid.metrics.hit_rate_vs_base as number) * 100)}%` : "—"} of quarters
          </div>
        )}
      </section>

      <section className="card span-7">
        <h3>Calendar year segments <span className="muted small">(independent windows)</span></h3>
        {segYear.length ? (
          <DataTable
            rows={segYear}
            rowKey={(r) => String(r.year)}
            columns={[
              { key: "year", label: "Year" },
              { key: "hold_all", label: "Hold all", align: "right", render: (r) => fmtPct(r.hold_all as number | null) },
              { key: "avoid_worst", label: "Avoid worst", align: "right", render: (r) => fmtPct(r.avoid_worst as number | null) },
              { key: "delta", label: "Screen Δ", align: "right", render: (r) => {
                  const d = r.avoid_worst != null && r.hold_all != null ? (r.avoid_worst as number) - (r.hold_all as number) : null;
                  return <span className={d == null ? "" : d >= 0 ? "pos" : "neg"} style={{ fontWeight: 650 }}>{fmtPct(d, 2)}</span>;
                } },
              { key: "benchmark", label: meta.benchmark, align: "right", render: (r) => fmtPct(r.benchmark as number | null) },
              { key: "hold_all_n", label: "Qtrs", align: "right" },
            ]}
          />
        ) : <Empty />}
        <p className="muted small">"Screen Δ" is the year's value added from dropping the flagged decile. A model
          whose whole edge sits in one year is telling you something.</p>
      </section>

      <section className="card span-5">
        <h3>Market regime split</h3>
        {segRegime.length ? (
          <DataTable
            rows={segRegime}
            rowKey={(r) => String(r.regime)}
            columns={[
              { key: "regime", label: "Regime" },
              { key: "n_quarters", label: "Qtrs", align: "right" },
              { key: "hold_all", label: "Hold all (avg q)", align: "right", render: (r) => fmtPct(r.hold_all as number | null) },
              { key: "avoid_worst", label: "Avoid worst (avg q)", align: "right", render: (r) => fmtPct(r.avoid_worst as number | null) },
            ]}
          />
        ) : <Empty />}
        <p className="muted small">A sell screen that only works when the market falls is a different product
          from one that works throughout. Quarters are bucketed by the {meta.benchmark} return's sign.</p>
      </section>

      {/* ================= IMA MONTE CARLO ================= */}
      <h2 className="span-12 section-head"><Term id="montecarlo">IMA simulation</Term> — does the screen help a {mcSim?.n_names ?? 20} name picker?</h2>
      <div className="help-note span-12">
        <strong>Why a distribution and not one backtest.</strong> IMA holds ~{mcSim?.n_names ?? 20} names, and at
        that concentration any single simulated portfolio is decided by luck. So {mcSim?.n_trials ?? 1000} random
        {" "}{mcSim?.n_names ?? 20} name portfolios are drawn per rebalance under each screening rule and the whole
        distributions are compared. If the screen works, the screened distributions shift right and lose their
        left tail. All tiers are drawn on identical quarters, delisting aware, gross of costs (identical turnover
        across tiers, so costs cancel in the comparison).
      </div>

      <section className="card span-7">
        <h3>Distribution of portfolio CAGRs by screening rule</h3>
        {Object.keys(tiers).length ? (
          <Plot height={360}
            data={Object.entries(tiers).map(([key, t]) => ({
              type: "box" as const, name: (t as MCTier).label, y: (t as MCTier).trial_cagrs,
              marker: { color: TIER_COLORS[key] ?? "#888" }, boxpoints: false as const,
            }))}
            layout={{ yaxis: { title: "trial CAGR", tickformat: ".0%" }, showlegend: false, margin: { b: 90 } }} />
        ) : <Empty />}
      </section>

      <section className="card span-5">
        <h3>Simulation summary</h3>
        {Object.keys(tiers).length ? (
          <DataTable
            rows={Object.entries(tiers).map(([key, t]) => ({ key, ...(t as MCTier) }))}
            rowKey={(r) => r.key}
            columns={[
              { key: "label", label: "Rule" },
              { key: "p50", label: "Median CAGR", align: "right", render: (r) => fmtPct(r.cagr.p50) },
              { key: "p5", label: "p5 (bad luck)", align: "right", render: (r) => fmtPct(r.cagr.p5) },
              { key: "p95", label: "p95", align: "right", render: (r) => fmtPct(r.cagr.p95) },
              { key: "pb", label: "P(beat unscreened)", align: "right", render: (r) =>
                  r.prob_beat_full_median != null ? `${Math.round(r.prob_beat_full_median * 100)}%` : "—" },
            ]}
          />
        ) : <Empty />}
        <p className="muted small">
          "P(beat unscreened)" = share of screened trials beating the unscreened median. 50% means the screen
          did nothing; materially above 50% means a random picker was better off inside the screen. The p5
          column is the disaster draw — a good screen protects it most.
        </p>
      </section>
    </div>
  );
}

function MetricsTable({ sleeves }: { sleeves: BacktestSleeve[] }) {
  return (
    <DataTable
      rows={sleeves}
      rowKey={(s) => s.name}
      columns={[
        { key: "name", label: "Sleeve" },
        { key: "cagr", label: <Term id="cagr">CAGR</Term>, align: "right", render: (s) => fmtPct(s.metrics.cagr as number | null) },
        { key: "sharpe", label: <Term id="sharpe">Sharpe</Term>, align: "right", render: (s) => fmt(s.metrics.sharpe as number | null) },
        { key: "max_drawdown", label: <Term id="maxdd">Max DD</Term>, align: "right", render: (s) => fmtPct(s.metrics.max_drawdown as number | null) },
        { key: "vol", label: "Vol", align: "right", render: (s) => fmtPct(s.metrics.vol as number | null) },
        { key: "avg_turnover", label: <Term id="turnover">Turnover</Term>, align: "right", render: (s) => s.metrics.avg_turnover != null ? fmtPct(s.metrics.avg_turnover as number, 0) : "—" },
      ]}
    />
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
function cumSum(xs: number[]): number[] {
  let s = 0; return xs.map((x) => { s += x; return s; });
}
