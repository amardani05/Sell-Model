import { ReactNode, useState } from "react";
import { Bundle, fmt, fmtSigned, decileColor } from "../lib/data";
import { Plot } from "./Plot";
import { DataTable } from "./DataTable";
import { Term } from "./Term";
import { Ticker, UniverseToggle, inUniverse } from "./TickerFlag";
import { ScoreRow } from "../lib/types";

const HORIZON_PHRASE: Record<string, string> = {
  "1m": "next month", "1q": "next quarter", "2q": "next 2 quarters", "4q": "next 4 quarters",
};

export function Overview({ meta, scores, validation, exclusions }: Bundle) {
  const horizons = meta.horizons_available.map(String);
  const [h, setH] = useState<string>(meta.horizon ?? `${meta.horizon_q}q`);
  const ic = validation.ic[h];
  const dec = validation.deciles[h];
  const cal = validation.calibration_by_horizon?.[h] ?? validation.calibration ?? [];
  const phrase = HORIZON_PHRASE[h] ?? `next ${meta.horizon_q} quarter(s)`;
  const fullEra = validation.era_ic?.find((e) => e.era === "full factor");
  const priceEra = validation.era_ic?.find((e) => e.era === "price only");
  const [universe, setUniverse] = useState<string>(meta.selection_index ?? "S&P 600");

  const worst = scores
    .filter((r) => r.score !== null && inUniverse(r.index_name, universe))
    .sort((a, b) => (b.score ?? -99) - (a.score ?? -99))
    .slice(0, 12);

  const icSeries = ic?.series ?? [];

  return (
    <div className="grid">
      <section className="card span-12 contrast">
        <div className="row-between">
          <h2>What this model answers</h2>
          <span className="seg-labeled">
            <span className="muted small"><Term id="horizon">Forward horizon</Term></span>
            <span className="seg">
              {horizons.map((hh) => (
                <button key={hh} className={h === hh ? "active" : ""} onClick={() => setH(hh)}>{hh.toUpperCase()}</button>
              ))}
            </span>
          </span>
        </div>
        <p>
          Rank S&amp;P 600 and 400 stocks by expected <strong>relative underperformance versus their <Term id="gics">GICS</Term> sector
          peers</strong> over the {phrase}. The output is a continuous
          <Term id="relativereturn"> relative risk</Term> score and a <Term id="sectorneutral">sector
          neutral</Term> <Term id="decile" /> (1 = best expected relative return, 10 = the sell sleeve).
        </p>
        <div className="contrast-grid">
          <div><span className="pill pill-blue">This model</span> ranks <em>within</em> GICS sector;
            target = stock return <em>minus</em> the sector peer median return.</div>
          <div><span className="pill pill-grey"><Term id="torpedo">Torpedo screener</Term></span> ranks across the
            <em> whole</em> universe; target = <Term id="absoluterisk"><em>absolute</em></Term> drawdown. It now
            lives on its own tab and in the contrast scatter.</div>
          <div><span className="pill pill-grey">Earnings event model</span> is a binary post earnings
            classifier; this has no event window and a continuous return rank label.</div>
        </div>
        <div className="help-note">
          <strong>How the score is built, in plain terms.</strong> For every stock we measure a handful of well
          known warning signs: it looks expensive, it has been lagging, its profits are thin or slipping, it is
          expanding its asset base or share count aggressively, and its earnings are not backed by cash. Each
          signal is compared only against other companies in the same sector, then blended into a single number.
          A high number means the stock looks worse than its sector peers on the very traits that have
          historically come before underperformance. We then sort each sector into ten buckets, called
          <Term id="decile"> deciles</Term>, from the most attractive (1) to the most at risk (10). Decile 10 is
          the sell sleeve.
        </div>
        <div className="help-note">
          <strong>The four tiles below are the model's report card.</strong> They answer one question: over the
          past several years, did a high score actually come before weak returns versus sector peers? A positive
          <Term id="ic"> Information Coefficient</Term> and <Term id="decile">decile</Term> spread, a
          <Term id="hitrate"> hit rate</Term> above one in two, and a <Term id="monotonicity">monotonicity</Term>
          near minus one all point the same way, that the ranking carried real information. Values near zero mean
          the ranking was no better than chance in this sample. Hover any underlined term for its definition.
        </div>
      </section>

      <KPI label={<><Term id="sectorneutral">Sector neutral</Term> <Term id="ic">IC</Term> (h={h.toUpperCase()})</>} value={fmtSigned(ic?.mean_ic)} sub={<>t = {fmt(ic?.t_stat)} · <Term id="ir">IR</Term> {fmt(ic?.ir)}</>} good={(ic?.mean_ic ?? 0) > 0} />
      <KPI label={<><Term id="ic">IC</Term> <Term id="hitrate">hit rate</Term></>} value={ic ? `${Math.round((ic.hit_rate ?? 0) * 100)}%` : "—"} sub={`${ic?.n_periods ?? 0} cross sections`} />
      <KPI label={<><Term id="decile">Decile</Term> spread (best − worst)</>} value={fmtSigned(dec?.spread_mean)} sub={`t = ${fmt(dec?.spread_tstat)}`} good={(dec?.spread_mean ?? 0) > 0} />
      <KPI label={<>Decile <Term id="monotonicity">monotonicity</Term> ρ</>} value={fmt(dec?.monotonicity_rho)} sub="want near −1 (higher sell decile means lower return)" good={(dec?.monotonicity_rho ?? 0) < 0} />

      {(priceEra || fullEra) && (
        <div className="help-note span-12">
          <strong><Term id="coveragera">Coverage eras</Term>, read before quoting any number above.</strong>{" "}
          {priceEra && <>The <em>price only era</em> ({priceEra.n_periods} quarters scored by momentum + reversal
          alone) has IC {fmtSigned(priceEra.mean_ic)} (t = {fmt(priceEra.t_stat)}). </>}
          {fullEra && <>The <em>full factor era</em> (all {meta.n_factors} factors) spans
          {" "}<strong>{fullEra.n_periods} scored quarter(s)</strong>{fullEra.n_periods < 8 && <>, far too few to
          judge the composite; treat the history above as a momentum/reversal test until deeper fundamentals are
          wired in</>}. </>}
          Full split on the Validation tab.
        </div>
      )}

      <section className="card span-6">
        <h3><Term id="reliability">Reliability</Term>: P(underperform sector) by score bucket</h3>
        <p className="muted small">
          The score translated into the language a PM uses: for each bucket, how often names actually trailed
          their sector median over the {phrase}. 50% (dashed) is a coin flip; a working
          model climbs to the right. Full detail, error bars, and the diagnostics gate live on the Validation tab.
        </p>
        {cal.length ? (
          <Plot height={260}
            data={[{
              type: "scatter", mode: "lines+markers", name: "P(underperform)",
              x: cal.map((c) => c.score_q),
              y: cal.map((c) => c.p_underperform),
              line: { color: "#b3001b", width: 2 }, marker: { size: 7 },
              hovertemplate: "bucket %{x}: %{y:.1%}<extra></extra>",
            }]}
            layout={{
              xaxis: { title: "score bucket (1 = best expected → 10 = worst)", dtick: 1 },
              yaxis: { title: "P(underperform)", tickformat: ".0%" },
              shapes: [{ type: "line", x0: 1, x1: 10, y0: 0.5, y1: 0.5, line: { color: "#888", dash: "dash", width: 1 } }],
            }} />
        ) : <p className="muted">No calibration data yet.</p>}
      </section>

      <section className="card span-6">
        <h3><Term id="ic">IC</Term> time series (h={h.toUpperCase()})</h3>
        {icSeries.length ? (
          <Plot height={260}
            data={[{
              type: "bar", x: icSeries.map((s) => s.date), y: icSeries.map((s) => s.ic),
              marker: { color: icSeries.map((s) => (s.ic >= 0 ? "#2c7a4b" : "#b3001b")) },
              name: "per period IC",
            }]}
            layout={{ yaxis: { title: "Spearman IC", zeroline: true }, xaxis: { title: "" } }} />
        ) : <p className="muted">No IC series (insufficient labeled cross sections).</p>}
      </section>

      <section className="card span-12">
        <div className="row-between">
          <h3>Top sell candidates: highest <Term id="relativereturn">relative risk</Term> score (latest cross section)</h3>
          <UniverseToggle value={universe} onChange={setUniverse} counts={meta.index_counts} />
        </div>
        <p className="muted small">
          Defaults to the <Term id="selectionuniverse">selection universe</Term> (S&amp;P 600), the names IMA
          actually picks from. S&amp;P 400 graduates are scored against 400 peers for monitoring only.
        </p>
        <DataTable<ScoreRow>
          rows={worst}
          rowKey={(r) => r.ticker}
          columns={[
            { key: "sell_rank", label: "#", render: (r) => r.sell_rank ?? "—" },
            { key: "ticker", label: "Ticker", render: (r) => <Ticker symbol={r.ticker} index={r.index_name} /> },
            { key: "gics_sector", label: "GICS Sector" },
            { key: "decile", label: "Decile", align: "right", render: (r) => (
              <span className="decile-pill" style={{ background: decileColor(r.decile) }}>{r.decile ?? "—"}</span>
            ) },
            { key: "score", label: "Score", align: "right", render: (r) => fmtSigned(r.score) },
            { key: "n_factors_used", label: "Factors", align: "right" },
          ]}
        />
      </section>
    </div>
  );
}

function KPI({ label, value, sub, good }: { label: ReactNode; value: string; sub?: ReactNode; good?: boolean }) {
  return (
    <div className="card kpi span-3">
      <span className="kpi-label">{label}</span>
      <span className={"kpi-value" + (good === undefined ? "" : good ? " pos" : " neg")}>{value}</span>
      {sub && <span className="kpi-sub">{sub}</span>}
    </div>
  );
}
