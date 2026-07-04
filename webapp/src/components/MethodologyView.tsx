import { Bundle } from "../lib/data";
import { Term } from "./Term";

const DIRECTION_NOTE: Record<string, string> = {
  Valuation: "rich means red flag (the value premium)",
  Momentum: "low 12 minus 1 momentum is the red flag; the 1 month reversal is kept separately",
  Quality: "low or declining profitability is the red flag (the quality premium)",
  Investment: "high asset growth and net issuance are red flags (the asset growth and dilution effects)",
  "Earnings Quality": "low operating cash flow over net income means high accruals is the red flag (Sloan)",
  Estimates: "downward estimate revisions or low SUE are red flags (gated, never from yfinance)",
};

export function MethodologyView({ meta }: Bundle) {
  const groups = Array.from(new Set(Object.values(meta.factor_groups)));
  const byGroup = (g: string) => Object.entries(meta.factor_groups).filter(([, gg]) => gg === g).map(([f]) => f);

  return (
    <div className="grid">
      <section className="card span-12 prose">
        <h2>Methodology</h2>

        <h3>The question</h3>
        <p>
          Rank S&amp;P 600 stocks by expected <strong>relative underperformance versus their
          <Term id="gics"> GICS</Term> sector peers</strong> over a forward horizon (default {meta.horizon_q}Q).
          The label for every name on every rebalance date is its <Term id="relativereturn">sector relative
          forward return</Term>: the stock return minus the median return of its sector peers over the same
          window. This is a cross sectional return ranking problem, not a risk flag screen and not an event
          classifier.
        </p>

        <h3>Three way contrast (enforced in code and docs)</h3>
        <table className="data-table">
          <thead><tr><th>Model</th><th>Cross section</th><th>Target</th></tr></thead>
          <tbody>
            <tr><td><strong>Relative Sell Model</strong></td><td>within GICS sector (<Term id="sectorneutral">sector neutral</Term>)</td><td>relative forward return (stock minus sector peer median)</td></tr>
            <tr><td><Term id="torpedo">Torpedo screener</Term> (integrated here)</td><td>whole universe</td><td><Term id="absoluterisk">absolute</Term> drawdown or blow up risk</td></tr>
            <tr><td>Earnings event model</td><td>per event</td><td>binary post earnings direction</td></tr>
          </tbody>
        </table>
        <p>
          The torpedo screener is built into this platform as a contrast lens. It shares the same data pipeline
          but ranks each name against the <strong>whole universe</strong> rather than its sector, so the two
          views can be read side by side. See the Torpedo Screener tab and the relative versus absolute scatter.
        </p>

        <h3>Factor taxonomy ({meta.n_factors} active factors)</h3>
        <p>Each factor is a documented cross sectional return predictor. Every raw factor is
          <Term id="winsorize"> winsorized</Term> then <Term id="zscore">z scored</Term>
          <strong> within GICS sector</strong> at each date ({meta.neutralize_method}), and sign flipped to its
          red flag direction so that <em>larger means more expected underperformance</em>.</p>
        <ul>
          {groups.map((g) => (
            <li key={g}><strong>{g}</strong> — {DIRECTION_NOTE[g] ?? ""}: <code>{byGroup(g).join(", ")}</code></li>
          ))}
        </ul>

        <h3>Construction (sequenced to avoid the equal weight versus fitted inconsistency)</h3>
        <ol>
          <li>Compute every factor sector neutrally (z score within GICS sector at each date), sign aligned to
            its red flag direction.</li>
          <li><strong><Term id="equalweight">Equal weight</Term> baseline</strong>: the plain mean of the sector
            neutral factors becomes the composite, then sector neutral <Term id="decile">deciles</Term>. This
            baseline ships and is validated first.</li>
          <li>Optional <Term id="learnedweight">learned weight</Term> model (ridge, logistic, or gradient boosted
            trees), trained <Term id="walkforward">walk forward</Term> against forward relative returns. It
            becomes the default scorer only if it <strong>beats the baseline <Term id="oos">out of
            sample</Term></strong>, otherwise the baseline stays default. Current default:
            <code> {meta.default_score}</code>. Fitted then ignored weights are never presented.</li>
        </ol>

        <h3>Torpedo screener (absolute risk)</h3>
        <p>
          The {meta.n_torpedo_features} torpedo risk features are <Term id="zscore">z scored</Term> across the
          <strong> whole universe</strong> at each date (never within sector), sign aligned so higher always
          means more risk, averaged into a composite, then turned into a 0 to 100 universe
          <Term id="percentile"> percentile</Term> and a <Term id="tier">tier</Term> (Stable, Mainstream,
          Elevated). This is the same machinery as the sell model with the sector grouping removed, which is
          exactly what makes it the absolute counterpart.
        </p>

        <h3>Validation (the whole point)</h3>
        <ul>
          <li><strong>Sector neutral <Term id="ic">IC</Term></strong>: minus the
            <Term id="spearman"> Spearman correlation</Term> between score and forward relative return per cross
            section, averaged <Term id="famamacbeth">Fama MacBeth</Term> with a <Term id="neweywest">Newey
            West</Term> (5 lag) <Term id="tstat">t statistic</Term>. Mean IC, t, <Term id="ir">IR</Term> and the
            IC time series are all reported.</li>
          <li><strong><Term id="decile">Decile</Term> spread</strong> (best minus worst) per period and pooled,
            with a t statistic, plus a <Term id="monotonicity">monotonicity</Term> test across deciles.</li>
          <li><strong>Backtests</strong> (quarterly rebalance, {meta.cost_bps} <Term id="turnover">bps</Term>
            cost, turnover reported): long only avoid the worst sector neutral decile versus
            <Term id="benchmark"> {meta.benchmark}</Term>; and a sector neutral long short (long the best decile,
            short the worst). Reported with <Term id="cagr">CAGR</Term>, volatility,
            <Term id="sharpe"> Sharpe</Term>, <Term id="maxdd">max drawdown</Term> and
            <Term id="hitrate"> hit rate</Term>.</li>
          <li><strong><Term id="walkforward">Walk forward</Term> only</strong>: features at t use data on or
            before t; labels use returns in the window after t.</li>
        </ul>

        <h3>Point in time data and survivorship</h3>
        <p>Universe membership is read from a <Term id="pointintime">point in time</Term> store
          (<code>data/sp600_membership.csv</code>: <code>ticker, company, gics_sector, start_date, end_date,
          delist_note</code>). Forward returns are <Term id="delistingaware">delisting aware</Term>: a name that
          goes to about zero is the strongest underperformer and is carried to its terminal value, never dropped.
          This run carried <strong>{meta.n_delisted_carried}</strong> delisted labels.</p>
        {!meta.membership_point_in_time && (
          <p className="callout warn">⚠ This run uses a <strong>current only</strong> membership snapshot, so
            cross sections before today carry <Term id="survivorship">survivorship bias</Term>. Supply a true
            point in time export for clean history.</p>
        )}

        <h3>Methodology limitations (honest)</h3>
        <ul>
          <li><strong>yfinance fundamental depth (about 4 to 5 quarters).</strong> Valuation, quality, accruals,
            asset growth and issuance factors only populate the most recent cross sections; deep history is
            carried by the price factors (momentum, reversal). The optional FactSet or S&amp;P Global loader is
            the fix and is gated behind <code>.env</code> and config.</li>
          <li><strong>Estimate factors are off unless wired in.</strong> Analyst revisions and
            <Term id="sue"> SUE</Term> cannot be built from yfinance, so they are gated
            (<code>use_estimate_factors = {String(meta.use_estimate_factors)}</code>) and never synthesized from
            price data.</li>
          <li><strong>Small or current only universes give weak IC.</strong> On a small universe with a current
            only membership snapshot the IC can be statistically indistinguishable from zero. That is an honest
            result, not a bug; a full point in time, deep history run is required for a real verdict.</li>
          <li><strong>Source for this build: <code>{meta.source}</code>.</strong> A <code>synthetic</code> source
            is a machinery demonstration with a planted signal, clearly labeled.</li>
        </ul>
      </section>
    </div>
  );
}
