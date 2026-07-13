import { Bundle } from "../lib/data";
import { Term } from "./Term";

const DIRECTION_NOTE: Record<string, string> = {
  Valuation: "rich means red flag (the value premium)",
  Momentum: "low 12 minus 1 momentum and distance below the 52 week high are red flags; the 1 month reversal is kept separately",
  Volatility: "high idiosyncratic volatility, lottery like single day pops (MAX), and high beta are red flags (Ang et al; Bali et al; betting against beta)",
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

        <div className="help-note">
          <strong>Plain language summary.</strong> This tool tries to spot the stocks most likely to lag their
          peers, not the market as a whole. It does that with a short list of traits that decades of market
          research have tied to weaker future returns: paying up for a stock, buying one that has already been
          falling, thin or shrinking profitability, aggressive expansion or share issuance, and earnings that are
          not backed by real cash. Each trait is scored against other companies in the same sector, so we are
          always comparing like with like, and the traits are blended into one number per stock that sorts every
          sector into ten buckets. The rest of this page explains how each piece is built, and just as importantly
          how we check that the ranking was genuinely right in the past rather than lucky. Every underlined term
          has a definition on hover.
        </div>

        <h3>The question</h3>
        <p>
          Rank S&amp;P 600 (SmallCap) and S&amp;P 400 (MidCap) stocks by expected <strong>relative
          underperformance versus their <Term id="gics"> GICS</Term> sector peers</strong> over a forward
          horizon (default {meta.horizon_q}Q). The S&amp;P 400 is unioned in so names that graduated out of the
          600 up into the 400 are still scored.
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
        <div className="help-note">
          <strong>Why these traits and not others.</strong> Each one is a documented market pattern, not a hunch.
          Cheap stocks have tended to beat expensive ones (the value effect), recent winners have tended to keep
          winning over a medium horizon (momentum), profitable and improving companies have tended to beat weak
          ones (the quality effect), companies that expand or issue shares aggressively have tended to disappoint
          (the asset growth and dilution effects), and earnings backed by cash rather than accounting entries have
          tended to persist (the accruals effect). Pointing each trait in its unfavorable direction and averaging
          them is what turns established research into a single sell ranking. We deliberately leave out anything we
          cannot measure honestly from the data on hand, such as analyst estimate revisions, rather than fake it.
        </div>

        <h3>Peer groups and the selection universe</h3>
        <p>
          Every comparison happens inside a <strong>(date, sector, index)</strong> peer group: an S&amp;P 600
          name is z scored, labeled, and deciled against S&amp;P 600 sector peers only, and a 400 graduate
          against 400 peers only. IMA picks from the 600 — the <Term id="selectionuniverse">selection
          universe</Term> — so every validation statistic, backtest, and simulation runs on the 600 alone,
          while the 400 stays scored purely so graduated holdings remain monitorable in the overlay. The
          candidate lists default to 600 with a toggle.
        </p>

        <h3>Scoring grid</h3>
        <p>
          Cross sections are cut <strong>monthly back to 2010</strong> (~200 observation dates). Labels still
          look {meta.horizon_q} quarter(s) ahead, so adjacent months are
          <Term id="overlapping"> overlapping observations</Term> and the <Term id="neweywest">Newey West</Term>
          lag count scales with the overlap — the standard Jegadeesh Titman construction, adopted for
          statistical power. Traded constructions (backtest, Monte Carlo) and quarter over quarter comparisons
          step on the quarter end subset: overlap is a statistics tool, not a tradeable rebalance. The monthly
          grid also guarantees a fresh post earnings cross section every quarter — re-run the pipeline the day
          after prints for IMA's post earnings updates.
        </p>

        <h3>Construction (sequenced to avoid the equal weight versus fitted inconsistency)</h3>
        <ol>
          <li>Compute every factor peer neutrally (z score within GICS sector × index at each date), sign
            aligned to its red flag direction.</li>
          <li><strong><Term id="familybalanced">Family balanced</Term> baseline</strong>: factors are averaged
            within their family first, then across families — four collinear valuation ratios cast ONE vote,
            and the price derived families (Momentum, Volatility) cannot swamp the fundamental ones no matter
            how many price factors exist. A name needs at least 3 populated factors across at least 2 families
            to be scored at all, and the composite is re-standardized within each peer group so thin coverage
            names cannot land in extreme deciles as a data artifact. Then peer neutral
            <Term id="decile"> deciles</Term>. This baseline ships and is validated first.</li>
          <li>Optional <Term id="learnedweight">learned weight</Term> model (ridge, logistic, or gradient boosted
            trees), trained <Term id="walkforward">walk forward</Term> on the selection universe against forward
            relative returns. It becomes the default scorer only if it <strong>beats the baseline
            <Term id="oos"> out of sample</Term></strong> on a paired t test, otherwise the baseline stays
            default. Current default: <code>{meta.default_score}</code>. Fitted then ignored weights are never
            presented.</li>
        </ol>

        <h3>Fundamentals source: SEC EDGAR (free, point in time)</h3>
        <p>
          Fundamental factors are built from the SEC's XBRL <code>companyfacts</code> API: every figure a
          company ever filed, quarterly back to ~2009–2012 for most names, each stamped with its actual
          <strong> filing date</strong> — which becomes the panel's as of date (true
          <Term id="pointintime"> point in time</Term> knowledge instead of a flat reporting lag guess). Values
          are always the <em>first filed</em> number, never a later restatement. Filers that tag the same line
          item under different concepts across the years are merged by an alias map, and year to date cash flow
          figures are differenced into quarters (Q4 = FY − Q3 YTD). No API key is involved; the SEC only
          requires an identifying User-Agent. yfinance remains a per name fallback.
        </p>

        <h3>Torpedo screener (absolute risk)</h3>
        <p>
          The {meta.n_torpedo_features} torpedo risk features are <Term id="zscore">z scored</Term> across the
          <strong> whole universe</strong> at each date (never within sector), sign aligned so higher always
          means more risk, averaged into a composite, then turned into a 0 to 100 universe
          <Term id="percentile"> percentile</Term> and a <Term id="tier">tier</Term> (Stable, Mainstream,
          Elevated). This is the same machinery as the sell model with the sector grouping removed, which is
          exactly what makes it the absolute counterpart.
        </p>

        <h3>Data integrity gate</h3>
        <p>
          Free price feeds occasionally join two different securities under one ticker (a bankruptcy emergence,
          a ticker reuse), which manufactures a fake giant one day "return" that no investor earned. Any single
          day price ratio beyond 4x (or below 0.25x) is flagged as a <Term id="splice">splice artifact</Term>,
          every forward return window spanning that day is <strong>excluded from labels and logged</strong>
          (see the Validation tab), and a backstop drops any window beyond 50x — a pure data error net, set far
          above the largest genuine small cap moonshots (~26x over two quarters in 2020–21), which are
          deliberately <em>kept</em>: deleting real right tail events would erase the model's worst potential
          misses and flatter every statistic. Display statistics
          additionally report <Term id="winsorizedmean">winsorized means</Term> and medians next to plain means,
          because sector relative returns are right skewed and one lottery quarter can otherwise carry an
          average. Rank statistics like the <Term id="ic">IC</Term> are unaffected by winsorization; backtests
          always use raw (gated) returns.
        </p>

        <h3><Term id="coveragera">Coverage eras</Term></h3>
        <p>
          yfinance fundamentals reach back only ~4–5 quarters, so most historical cross sections were scored by
          the two price factors alone while the latest ones use all {meta.n_factors}. Every headline statistic
          is therefore split into a <em>price-only era</em> and a <em>full-factor era</em>: pooling them would
          answer a mixed question, and the split makes it impossible to accidentally present a momentum/reversal
          track record as evidence about the full composite.
        </p>

        <h3>Validation (the whole point)</h3>
        <ul>
          <li><strong>Sector neutral <Term id="ic">IC</Term></strong>: minus the
            <Term id="spearman"> Spearman correlation</Term> between score and forward relative return per cross
            section, averaged <Term id="famamacbeth">Fama MacBeth</Term> with a <Term id="neweywest">Newey
            West</Term> <Term id="tstat">t statistic</Term> whose lag count scales with the label overlap
            (horizon − 1 quarters, floored at one). Mean IC, t, <Term id="ir">IR</Term>, the IC time series,
            an IC-by-year split, and the per era split are all reported.</li>
          <li><strong><Term id="calibration">Calibration</Term>, the Fama MacBeth way</strong>: score buckets are
            cut <em>within each quarter</em>, per bucket outcomes averaged across quarters with
            <Term id="standarderror"> standard errors</Term>, and skew robust companions (median,
            <Term id="winsorizedmean"> winsorized mean</Term>) shown alongside. The
            <Term id="reliability"> reliability curve</Term> reports P(underperform sector) per bucket — the
            score translated into a probability statement.</li>
          <li><strong><Term id="eventstudy">Event study</Term></strong>: the average cumulative sector relative
            return in the 1–4 quarters <em>after</em> a name sits in (or newly enters) the worst decile — the
            most presentation ready read of what a flag has historically meant.</li>
          <li><strong><Term id="decile">Decile</Term> spread</strong> (best minus worst) per period and pooled,
            with a t statistic, plus a <Term id="monotonicity">monotonicity</Term> test across deciles.</li>
          <li><strong>Backtests</strong> (quarterly rebalance, {meta.cost_bps} <Term id="turnover">bps</Term>
            cost, turnover reported): the screen is judged as <em>avoid the worst decile</em> minus
            <em> hold everything</em>, both equal weight — comparing an equal weight portfolio to the cap
            weighted <Term id="benchmark">{meta.benchmark}</Term> would credit the model with the structural
            equal weight effect, so {meta.benchmark} is shown as market context only. Calendar year and market
            regime segments are reported so no single period can quietly carry the result.</li>
          <li><strong><Term id="montecarlo">IMA Monte Carlo</Term></strong>: thousands of random 20 name
            portfolios drawn per rebalance under each screening rule (no screen / drop decile 10 / drop 9–10 /
            top half only), compared as full distributions — the honest way to measure what the screen does for
            a concentrated picker. This replaced the earlier long/short sleeve, which was removed deliberately:
            IMA is long only and a flat bps cost wildly understates real small cap borrow, so its Sharpe invited
            objections rather than evidence.</li>
          <li><strong><Term id="walkforward">Walk forward</Term> only</strong>: features at t use data on or
            before t; labels use returns in the window after t. The learned model is promoted over the equal
            weight baseline only on a <strong>paired</strong> per date IC test (t ≥ 2), never on a point
            estimate.</li>
        </ul>
        <div className="help-note">
          <strong>Why validation is the whole point.</strong> A ranking that looks reasonable can still be
          worthless, so before trusting any name on the list we insist the ranking earned it. The Information
          Coefficient asks whether high scores really came before weak relative returns; the decile spread asks
          whether the best and worst buckets actually separated; the backtest asks whether trading the ranking
          would have paid after costs. The placebo, look ahead, and survivorship checks on the Overview then rule
          out the three most common ways these tests fool you: a score that only looks predictive by accident, a
          feature that secretly peeks at the future, and a universe that quietly drops the losers. Passing all of
          them is what separates a real edge from a good looking chart.
        </div>

        <h3>Per name transparency</h3>
        <p>
          Every ticker on this site is clickable. The drill down shows the full factor decomposition behind the
          name's decile — each factor's raw value, formula, direction aligned sector <Term id="zscore">z
          score</Term>, within sector percentile, and quarter over quarter change — plus a coverage badge (how
          many of the {meta.n_factors} factors are actually populated), the as of date of the fundamentals used,
          the torpedo contrast, and a copyable risks section draft. "Why is this name flagged" should never
          require reading code.
        </p>

        <h3>How this differs from the Piper Sandler Sell Model</h3>
        <p>
          The PSC Sell Model shares this model's architecture — an equal weighted, sector neutral red flag
          count, deciled within sector, decile 10 = most at risk — but the ingredient lists overlap only
          partially. Piper's 14 factors (7 categories × 2) include equity duration, shareholder yield, revenue
          variance, change in days payable, EPS variance, change in receivables, EVA, change in depreciable
          life, and <Term id="sue">SUE</Term> — none of which are carried here — while this model carries
          valuation multiples (P/E, EV/EBITDA, P/S, FCF yield) and explicit quality levels (ROE, ROA, margins)
          that Piper's list does not. The peer groups also differ: Piper ranks within S&amp;P 1500 / Russell
          universe sectors, this model within the S&amp;P 600+400 union. Rank disagreements between the two on a
          specific name are therefore <em>expected</em> and usually explainable by a factor one model carries
          and the other does not — the drill down is the tool for answering exactly that question.
        </p>

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
          <li><strong>EDGAR fundamentals reach back to ~2009–2012, not further.</strong> Pre XBRL cross sections
            carry price factors only; some filers tag line items idiosyncratically (the alias map is maintained,
            not perfect); and names without a CIK fall back to shallow yfinance statements. The coverage era
            split reports exactly which cross sections carry full factor coverage — read it before quoting any
            pooled number.</li>
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
