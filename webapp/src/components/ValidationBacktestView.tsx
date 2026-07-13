import { ReactNode, useState } from "react";
import { Bundle, fmt, fmtSigned, fmtPct } from "../lib/data";
import { Plot } from "./Plot";
import { DataTable } from "./DataTable";
import { Term } from "./Term";
import { BacktestSleeve, CalibrationRow, EraICRow, HorizonICRow, MCTier } from "../lib/types";

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
  const firstFull = eras.find((e) => e.era === "full factor")?.date ?? null;

  // roadmap 1.5: IC decay curves (per family IC at each label horizon)
  const termStructure = validation.horizon_term_structure ?? [];
  const tsHorizons = Array.from(new Map(termStructure.map((r) => [r.horizon, r.months])).entries())
    .sort((a, b) => a[1] - b[1]).map(([hz]) => hz);
  const tsFamSeries = Array.from(new Set(termStructure.filter((r) => r.kind !== "factor").map((r) => r.series)));
  const tsFactorSeries = Array.from(new Set(termStructure.filter((r) => r.kind === "factor").map((r) => r.series)));
  const tsCell = new Map(termStructure.map((r) => [`${r.series}|${r.horizon}`, r]));
  const defaultComposite = meta.default_score === "score_ml" ? "Composite (learned)" : "Composite (equal weight)";
  const tsColumns = [
    { key: "series", label: "Series", render: (r: { series: string }) =>
        r.series === defaultComposite ? <strong>{r.series} ★</strong> : <>{r.series}</> },
    ...tsHorizons.map((hz) => ({
      key: hz, label: hz, align: "right" as const,
      render: (r: { series: string }) => icCell(tsCell.get(`${r.series}|${hz}`)),
    })),
  ];

  // roadmap 1.6: IC weighted family blend diagnostics
  const icwW = validation.icw_weights ?? [];
  const icwFams = Array.from(new Set(icwW.map((r) => r.family)));
  const icwPaired = validation.icw_paired;

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
          <h2>Validation: does the score rank forward relative returns?</h2>
          <span className="seg-labeled">
            <span className="muted small"><Term id="horizon">Forward horizon</Term></span>
            <span className="seg">
              {horizons.map((hh) => (
                <button key={hh} className={h === hh ? "active" : ""} onClick={() => setH(hh)}>{hh}Q</button>
              ))}
            </span>
          </span>
        </div>
        <p className="muted">
          Every statistic on this page describes the <Term id="selectionuniverse">selection universe</Term>
          {" "}({meta.selection_index ?? "S&P 600"}) on a <strong>monthly scoring grid</strong>
          {" "}({meta.n_cross_sections} <Term id="overlapping">overlapping cross sections</Term>
          {meta.n_quarterly_cross_sections ? <>; traded sleeves step on the {meta.n_quarterly_cross_sections} quarter ends</> : null}).
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
            <h3 style={{ marginTop: 6 }}><Term id="coveragera">Coverage eras</Term>: which model does this history actually test?</h3>
            <p className="muted small">
              Cross sections before XBRL fundamentals become available (~2009 to 2012 via SEC EDGAR) are scored by
              the price factors alone. Any headline number that pools the eras is answering a mixed question;
              read this split first.
            </p>
            <DataTable<EraICRow>
              rows={eraIC}
              rowKey={(r) => r.era}
              columns={[
                { key: "era", label: "Era", render: (r) => r.era === "price only"
                    ? <span><b>price only</b> <span className="muted small">(momentum + reversal)</span></span>
                    : <span><b>full factor</b> <span className="muted small">(all {meta.n_factors} factors)</span></span> },
                { key: "mean_ic", label: <>Mean <Term id="ic">IC</Term></>, align: "right", render: (r) => fmtSigned(r.mean_ic) },
                { key: "t_stat", label: <Term id="tstat">t</Term>, align: "right", render: (r) => fmt(r.t_stat) },
                { key: "ir", label: <Term id="ir">IR</Term>, align: "right", render: (r) => fmt(r.ir) },
                { key: "n_periods", label: "Quarters", align: "right" },
              ]}
            />
            {(eraIC.find((e) => e.era === "full factor")?.n_periods ?? 0) < 8 && (
              <p className="callout warn small">
                ⚠ The full factor era spans only
                {" "}{eraIC.find((e) => e.era === "full factor")?.n_periods ?? 0} scored quarter(s): the 15 factor
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

      {/* ================= WHAT BROKE, AND WHEN ================= */}
      <section className="card span-7">
        <h3>What broke, and when: rolling one year IC per factor family</h3>
        <p className="muted small">
          The composite can net to zero while its families are strongly nonzero in <em>opposite</em> directions.
          Each line is one family's sub score used alone, rolling twelve month mean IC: above zero = that
          family's red flags predicted underperformance in that regime; below zero = they pointed the wrong way.
          This is the diagnostic behind the headline: which ingredient failed, and in which market.
        </p>
        {validation.family_ic_rolling?.length ? (
          <Plot height={340}
            data={Object.keys(validation.family_ic_rolling[0] ?? {})
              .filter((k) => k !== "date")
              .map((fam) => ({
                type: "scatter" as const, mode: "lines" as const, name: fam,
                x: validation.family_ic_rolling.map((r) => r.date as string),
                y: validation.family_ic_rolling.map((r) => r[fam] as number | null),
                line: { width: 2 },
              }))}
            layout={{ yaxis: { title: "rolling 12m mean IC", zeroline: true },
                      legend: { orientation: "h", y: -0.22 } }} />
        ) : <Empty />}
      </section>

      <section className="card span-5">
        <h3>Stress windows: named disasters, judged separately</h3>
        <p className="muted small">
          A sell model that only works in calm tape is a different product. Rows are flags raised
          {" "}<em>during</em> each episode, judged on their forward window. COVID is two rows on purpose: the
          crash and the junk rally that followed are opposite regimes for a red flag model.
        </p>
        {validation.stress_windows?.length ? (
          <DataTable
            rows={validation.stress_windows}
            rowKey={(r) => r.window}
            columns={[
              { key: "window", label: "Episode", render: (r) => (
                <span title={`${r.start} to ${r.end}`}>{r.window}</span>
              ) },
              { key: "mean_ic", label: "IC", align: "right", render: (r) => (
                <span className={(r.mean_ic ?? 0) >= 0 ? "pos" : "neg"} style={{ fontWeight: 650 }}>{fmtSigned(r.mean_ic, 3)}</span>
              ) },
              { key: "spread_mean", label: "Spread", align: "right", render: (r) => fmtSigned(r.spread_mean, 3) },
              { key: "bench_return", label: meta.benchmark, align: "right", render: (r) => fmtPct(r.bench_return, 0) },
              { key: "n_periods", label: "Obs", align: "right" },
            ]}
          />
        ) : <Empty />}
        <p className="muted small">
          IC &gt; 0 with the benchmark falling = the screen protected when it mattered. IC &lt; 0 in a rally =
          flagged names led the bounce (the lottery effect in regime form).
        </p>
      </section>

      {/* ================= HORIZON TERM STRUCTURE ================= */}
      <section className="card span-7">
        <h3>IC term structure: how fast does each family pay?</h3>
        <p className="muted small">
          Each line is one family's sub score tested on its own against forward relative returns at four label
          horizons (1M, 1Q, 2Q, 4Q). Documented anomalies differ in <em>speed</em>: short term reversal pays
          within a month and is gone (Jegadeesh 1990), while value, quality and accruals build over two to four
          quarters (Sloan's accruals result is an annual effect). A family that is negative at 1Q but positive
          further out is mis timed, not broken, and a candidate for a slower label or a separate slow sleeve. A
          family negative at every horizon is genuinely inverted in this sample. Error bars are ±2
          {" "}<Term id="standarderror">standard errors</Term> (<Term id="neweywest">Newey West</Term>; lags
          scale with each label's overlap on the monthly grid).
        </p>
        {termStructure.length ? (
          <Plot height={360}
            data={tsFamSeries.map((name) => {
              const rows = tsHorizons.map((hz) => tsCell.get(`${name}|${hz}`) ?? null);
              const isComposite = name.startsWith("Composite");
              const isDefault = name === defaultComposite;
              return {
                type: "scatter" as const, mode: "lines+markers" as const, name,
                x: tsHorizons, y: rows.map((r) => r?.mean_ic ?? null),
                error_y: { type: "data" as const, array: rows.map((r) => 2 * (r?.se ?? 0)),
                           visible: true, thickness: 1 },
                line: isDefault ? { color: "#1d2733", width: 3.5 }
                  : isComposite ? { color: "#8893a0", width: 1.5, dash: "dot" as const }
                  : { width: 2 },
                marker: { size: 6 },
                text: rows.map((r) => (r ? `t ${fmt(r.t_stat, 1)} · n ${r.n_periods}` : "")),
                hovertemplate: "%{x}: IC %{y:.4f}<br>%{text}<extra>" + name + "</extra>",
              };
            })}
            layout={{ xaxis: { title: "label horizon", type: "category" },
                      yaxis: { title: "mean IC", zeroline: true },
                      legend: { orientation: "h", y: -0.25 } }} />
        ) : <Empty />}
      </section>

      <section className="card span-5">
        <h3>Term structure table</h3>
        {termStructure.length ? (
          <>
            <DataTable
              rows={tsFamSeries.map((s) => ({ series: s }))}
              rowKey={(r) => r.series}
              columns={tsColumns}
            />
            <details style={{ marginTop: 8 }}>
              <summary className="muted small">Per factor detail ({tsFactorSeries.length} factors)</summary>
              <DataTable
                rows={tsFactorSeries.map((s) => ({ series: s }))}
                rowKey={(r) => r.series}
                columns={tsColumns}
              />
            </details>
          </>
        ) : <Empty />}
        <p className="muted small">
          Read <strong>shapes, not stars</strong>: {tsFamSeries.length + tsFactorSeries.length} series across
          {" "}{tsHorizons.length} horizons is 100+ <Term id="tstat">t statistics</Term>, so a few clear t = 2
          by luck alone (Harvey, Liu and Zhu 2016). A bigger IC at a slower horizon also does not mean the
          model should trade slower: IR ≈ IC × √breadth (Grinold and Kahn), and a 1M signal makes about 12
          independent bets a year versus about 1 at 4Q. The 4Q column spans only ~15 independent windows:
          directional evidence with wide bands. ★ marks the default scorer.
        </p>
      </section>

      {/* ================= CALIBRATION ================= */}
      <section className="card span-6">
        <h3><Term id="calibration">Calibration</Term>: return by score bucket</h3>
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
        <h3><Term id="reliability">Reliability</Term>: P(underperform sector) by bucket</h3>
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
        <h3><Term id="eventstudy">Event study</Term>: what happens after a name is flagged</h3>
        <p className="muted small">
          Cumulative average sector relative return in the quarters after sitting in the worst decile (k = 0 is
          the first quarter after the flag). "New entrants" are names that just fell into decile 10 that
          quarter. This is the deck ready read: <em>"names we flag go on to lag their sector by X% over the
          next N quarters"</em>, provided the curve is negative and its error bars exclude zero.
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
          flagged bucket's outcome is being carried by a handful of extreme names: decile 10 holds the
          universe's most volatile names, whose <em>mean</em> can rise on lottery winners even when the typical
          flagged name goes nowhere.
        </p>
      </section>

      <section className="card span-5">
        <h3>Decile <Term id="monotonicity">monotonicity</Term></h3>
        <p className="muted small">Forward <Term id="relativereturn">relative return</Term> by sell
          <Term id="decile"> decile</Term>: mean, <Term id="winsorizedmean">winsorized mean</Term>, and median
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
            ? <>. This run: diff {fmtSigned(validation.promotion.mean_diff, 4)}, t = {fmt(validation.promotion.t_stat)}
                over {validation.promotion.n_periods} dates → <strong>{validation.promotion.promote ? "promoted" : "baseline kept"}</strong>.</>
            : <> (learned model not fitted this run).</>}
          {" "}A point estimate edge is noise, not a win.
        </p>
      </section>

      <section className="card span-6">
        <h3>Data integrity gate</h3>
        <p className="muted small">
          Forward return windows spanning a <Term id="splice">splice artifact</Term> (or beyond a 50x error
          net) are excluded from every statistic on this page and logged here, never silently used. One such
          artifact (a bankruptcy emergence spliced into one ticker at +13,000%) previously made calibration
          bucket 4 look like the best performer. Genuine moonshots (GME, MARA in 2020 to 2021) are deliberately
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

      {/* ================= IC WEIGHTED BLEND ================= */}
      <section className="card span-12">
        <h3>IC weighted family blend: the transparent middle ground</h3>
        <p className="muted small">
          The third scorer in the comparison above. Family weights at each date are proportional to the
          family's trailing mean <Term id="ic">IC</Term> over the last {validation.icw_params?.window ?? 36}
          {" "}realized cross sections, then shrunk halfway back toward equal weight, because family IC
          estimates are noisy and only half the weight should follow the evidence (the shrinkage idea is
          James Stein; the reference on combining signals is Grinold and Kahn chapter 10). A family whose
          trailing IC is negative is muted to zero, never inverted: learning to bet <em>against</em> a family
          is extra freedom deliberately left to the learned model. Strictly point in time: a cross section's
          IC enters the window only after its forward label has fully realized, and until
          {" "}{validation.icw_params?.min_realized ?? 12} realized ICs exist the blend stays equal weight.
        </p>
        {icwPaired && (
          <p className="small">
            Paired per date IC tests: <strong>blend minus equal weight</strong>
            {" "}{fmtSigned(icwPaired.icw_vs_equal_weight?.mean_diff, 4)} (t = {fmt(icwPaired.icw_vs_equal_weight?.t_stat)});
            {" "}<strong>learned minus blend</strong>
            {" "}{fmtSigned(icwPaired.learned_vs_icw?.mean_diff, 4)} (t = {fmt(icwPaired.learned_vs_icw?.t_stat)}).
            The default score decision remains learned vs baseline; this section is evidence for a PM call,
            never a silent switch.
          </p>
        )}
        {icwW.length ? (
          <Plot height={300}
            data={icwFams.map((fam) => {
              const rows = icwW.filter((r) => r.family === fam);
              return {
                type: "scatter" as const, mode: "lines" as const, name: fam,
                x: rows.map((r) => r.date), y: rows.map((r) => r.weight),
                line: { width: 2 },
                hovertemplate: "%{x}: %{y:.3f}<extra>" + fam + "</extra>",
              };
            })}
            layout={{
              yaxis: { title: "family weight", rangemode: "tozero" },
              legend: { orientation: "h", y: -0.25 },
              shapes: icwFams.length ? [{ type: "line", xref: "paper", x0: 0, x1: 1,
                y0: 1 / icwFams.length, y1: 1 / icwFams.length,
                line: { color: "#888", dash: "dash", width: 1 } }] : [],
              annotations: icwFams.length ? [{ xref: "paper", x: 0.01, y: 1 / icwFams.length,
                yanchor: "bottom", text: "equal weight", showarrow: false,
                font: { size: 11, color: "#888" } }] : [],
            }} />
        ) : <Empty />}
        <p className="muted small">
          Reading the chart: lines above the dashed reference are families the blend currently trusts more
          than equal weight; lines pinned at zero are families whose trailing IC is negative (for this
          history, expect quality and accruals there, and valuation above the line, matching the term
          structure verdict). Weights move slowly because the window is three years of realized labels.
        </p>
      </section>

      {/* ================= OVERRIDE SCOREBOARD ================= */}
      <section className="card span-12">
        <h3>Analyst override scoreboard</h3>
        <p className="muted small">
          Overrides are attributed, expiring annotations filed against the model's view (see the drill down's
          "Add override" and <code>docs/override-layer-design.md</code>). They never change a score. Each quarter
          an overridden name realizes a relative return, we check who was right: the analyst's direction or the
          model's. The clinical vs statistical prediction literature (Meehl 1954; Grove &amp; Meehl 2000) predicts
          the <code>thesis_disagreement</code> bucket will lose to the model; this table finds out.
        </p>
        {(() => {
          const sb = overrides?.scoreboard as any;
          if (!sb || !sb.n_scored_obs) {
            return <p className="muted small">
              {overrides?.active?.length
                ? `${overrides.active.length} active override(s) on file; none has realized a scoreable quarter yet.`
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
      <h2 className="span-12 section-head">Backtest: quarterly rebalance, {meta.cost_bps} <Term id="turnover">bps</Term> cost</h2>
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
      <h2 className="span-12 section-head"><Term id="montecarlo">IMA simulation</Term>: does the screen help a {mcSim?.n_names ?? 20} name picker?</h2>
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
          column is the disaster draw; a good screen protects it most.
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

function icCell(r: HorizonICRow | null | undefined): ReactNode {
  if (!r || r.mean_ic == null) return <span className="muted">—</span>;
  return (
    <span>
      <span className={r.mean_ic >= 0 ? "pos" : "neg"} style={{ fontWeight: 650 }}>{fmtSigned(r.mean_ic, 3)}</span>{" "}
      <span className="muted small">t {fmt(r.t_stat, 1)}</span>
    </span>
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
