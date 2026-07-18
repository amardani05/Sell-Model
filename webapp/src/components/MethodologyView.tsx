import { Bundle } from "../lib/data";
import { Term } from "./Term";

const DIRECTION_NOTE: Record<string, string> = {
  Valuation: "rich means red flag (the value premium)",
  Momentum: "low 12 minus 1 momentum and distance below the 52 week high are red flags; the 1 month reversal is kept separately",
  Volatility: "high idiosyncratic volatility, lottery like single day pops (MAX), and high beta are red flags (Ang et al; Bali et al; betting against beta)",
  Quality: "low or declining profitability is the red flag (the quality premium)",
  Investment: "high asset growth and net issuance are red flags (the asset growth and dilution effects)",
  "Earnings Quality": "low operating cash flow over net income means high accruals is the red flag (Sloan)",
  "Short Activity": "a high or rising share of daily volume sold short is the red flag (informed shorting flow, Boehmer Jones Zhang 2008; FINRA Reg SHO daily files, so history begins Oct 2018 and this is flow, not short interest positions)",
  "Insider Activity": "net insider selling is the red flag: open market Form 4 purchases predict returns, strongest in small caps (Lakonishok and Lee 2001). The SEC posts each quarter's transaction data set a week or two after quarter end, so the newest cross sections can briefly lag",
  "Earnings Surprise": "a weak market reaction to the latest earnings 8-K is the red flag: bad surprises keep drifting (Bernard and Thomas 1989). This is the price based SUE proxy while estimate feeds stay gated off",
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
          horizon (headline {meta.horizon_label ?? `${meta.horizon_q}Q`}, switchable at run time; traded sleeves always rebalance quarterly). The S&amp;P 400 is unioned in so names that graduated out of the
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

        <h3>Read this first: five ideas carry everything below</h3>
        <div className="help-note">
          <p>
            <strong>1. Average versus median.</strong> The average adds everything up and divides; the
            <strong> median</strong> is the middle value once everything is sorted. Small cap returns have a
            long right tail (occasional 10x moonshots), and a single moonshot can drag an average far away
            from what the typical stock did. That is why this model grades stocks against their sector's
            median, and why charts here often show medians next to means.
          </p>
          <p>
            <strong>2. Standard deviation.</strong> The typical gap between individual values and their group
            average, in the same units as the data. If sector P/E ratios average 20 with a standard deviation
            of 5, then a P/E of 25 is one typical gap above average (ordinary), while a P/E of 35 is three
            gaps above (genuinely unusual).
          </p>
          <p>
            <strong>3. The <Term id="zscore">z score</Term>.</strong> One number that answers "how unusual is
            this value among its peers": the value, minus the peer average, divided by the peer standard
            deviation. A z of 0 is perfectly typical, +1 is notable, +2 is unusual, and the sign tells the
            direction. z scores let us compare apples to oranges: a P/E and a profit margin become the same
            currency, "peer gaps."
          </p>
          <p>
            <strong>4. <Term id="percentile">Percentile</Term> and <Term id="decile">decile</Term>.</strong>{" "}
            A percentile says what share of the group sits below you: percentile 88 means higher than 88% of
            peers. Sort a group and cut it into ten equal stacks, and each stack is a decile: decile 1 is the
            bottom tenth of the sort, decile 10 the top tenth.
          </p>
          <p>
            <strong>5. <Term id="oos">Out of sample</Term>.</strong> Every performance number on this site
            comes from predictions made BEFORE the answer existed, then graded once returns realized, the way
            a weather forecast is judged. Nothing is graded on data the model was allowed to study first.
          </p>
        </div>

        <h3>From raw data to a sell decile, one stock at a time</h3>
        <p className="muted small">
          The walkthrough follows one fictional name, ACME, an S&amp;P 600 industrial supplier, through the
          entire pipeline. Every step below is what the code actually does, in order.
        </p>
        <ol>
          <li>
            <strong>Collect what was knowable, when it was knowable.</strong> Daily prices and volumes back to
            2010; quarterly financial statements as they were FIRST filed with the SEC (stamped with the
            filing date, so ACME's March quarter only informs the model from its May filing date onward);
            FINRA's daily short sale volume file; insider Form 4 filings; earnings announcement dates from
            8-K filings. No revised or restated numbers, no information used before its public date.
          </li>
          <li>
            <strong>Measure the warning signs (the factors).</strong> From that raw data, {meta.n_factors}
            {" "}measurements per stock per month, each one a warning sign the academic literature documented
            as predicting weak returns BEFORE we ever touched the data. Example: ACME trades at $50 with $2
            of trailing earnings per share, so its P/E is 25. Other factors measure momentum, volatility,
            profitability, asset growth, accruals, shorting activity, insider selling, and the market's
            reaction to the latest earnings print.
          </li>
          <li>
            <strong>Compare within the sector only (<Term id="sectorneutral">sector neutral</Term>).</strong>{" "}
            A software company always looks expensive next to a bank; comparing raw P/Es mostly ranks
            industries, not companies. So ACME's P/E of 25 is compared only against other S&amp;P 600
            Industrials on the same date, never against the whole market, and S&amp;P 600 names are never
            compared against S&amp;P 400 names.
          </li>
          <li>
            <strong>Turn each comparison into a z score.</strong> Suppose S&amp;P 600 Industrials average a
            P/E of 20 with a standard deviation of 5. ACME's z is (25 − 20) ÷ 5 = +1.0: one typical gap
            richer than its average peer. Before computing this, the wildest 2% of values on each side are
            clipped in ("winsorized") so one broken or freak number cannot distort the sector's average and
            standard deviation. This repeats for all {meta.n_factors} factors, every stock, every month.
          </li>
          <li>
            <strong>Point every signal the same way.</strong> Each z score is multiplied by +1 or −1 so that
            after alignment, a BIGGER number always means MORE expected underperformance. High P/E is already
            a red flag, so it keeps its sign; high profitability is good, so its z is flipped. Only after
            this step does averaging signals make sense.
          </li>
          <li>
            <strong>One vote per family, not per factor.</strong> The four valuation ratios are near copies
            of one another; letting each vote would quadruple count one idea. So factors are first averaged
            within their family (Valuation, Momentum, Volatility, Quality, Investment, Earnings Quality,
            Short Activity, Insider Activity, Earnings Surprise), and the families are then combined. A stock
            must have at least 3 factors across at least 2 families or it is not scored at all; missing data
            is never guessed.
          </li>
          <li>
            <strong>Weight the families.</strong> The simple baseline gives every family an equal vote. The
            {" "}<Term id="learnedweight">learned model</Term>, which currently holds the default, instead
            lets a <Term id="ridge">ridge regression</Term> choose the weights: refit every month using only
            history available at that moment, allowed to give a family a negative weight where its
            documented red flag has been paying the wrong way in this market. It holds the default only
            because it beat the equal weight baseline <Term id="oos">out of sample</Term> under the
            pre registered promotion rule; its full evidence file, including its refit by refit weights and
            the overfit checks, lives on the Validation tab.
          </li>
          <li>
            <strong>Cut the deciles.</strong> ACME's final score is standardized once more within its peer
            group (so names scored on 4 families are comparable with names scored on 9), then every sector's
            names are RANKED by score and split into ten equal stacks per sector per date.
            <Term id="decile"> Decile</Term> 1 holds the tenth of each sector that looks best, decile 10 the
            tenth that looks worst: the sell sleeve. Because the cut happens inside each sector, decile 10
            always contains roughly the worst tenth of EVERY sector; the model cannot dump an entire cheap
            industry into it. If ACME's aligned score puts it in the riskiest tenth of Industrials that
            month, ACME is a decile 10 name regardless of how any other sector looks.
          </li>
          <li>
            <strong>Grade it later.</strong> The score's job is to predict the
            {" "}<Term id="relativereturn">sector relative forward return</Term>: ACME's total return over
            the {meta.horizon_phrase ?? "forward window"}, minus the MEDIAN return of its sector peers over
            the same window. If ACME returns +4% while the median Industrial returns +10%, ACME
            underperformed by 6 points even though it went up. A name that stops trading is graded at −100%
            rather than dropped, so failures cannot vanish from the record. Every validation chart is this
            grading, done out of sample, across ~200 monthly cross sections since 2010.
          </li>
        </ol>

        <h3>Factor taxonomy ({meta.n_factors} active factors)</h3>
        <p>Each factor is a documented cross sectional return predictor. Every raw factor is
          <Term id="winsorize"> winsorized</Term> then <Term id="zscore">z scored</Term>
          <strong> within GICS sector</strong> at each date ({meta.neutralize_method}), and sign flipped to its
          red flag direction so that <em>larger means more expected underperformance</em>.</p>
        <ul>
          {groups.map((g) => (
            <li key={g}><strong>{g}</strong> · {DIRECTION_NOTE[g] ?? ""}: <code>{byGroup(g).join(", ")}</code></li>
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
          against 400 peers only. IMA picks from the 600 (the <Term id="selectionuniverse">selection
          universe</Term>), so every validation statistic, backtest, and simulation runs on the 600 alone,
          while the 400 stays scored purely so graduated holdings remain monitorable in the overlay. The
          candidate lists default to 600 with a toggle.
        </p>

        <h3>Scoring grid</h3>
        <p>
          Cross sections are cut <strong>monthly back to 2010</strong> (~200 observation dates). Labels still
          look {(meta.horizon_phrase ?? `${meta.horizon_q} quarter(s)`).replace("next ", "")} ahead, so adjacent months are
          <Term id="overlapping"> overlapping observations</Term> and the <Term id="neweywest">Newey West</Term>
          lag count scales with the overlap. This is the standard Jegadeesh Titman construction, adopted for
          statistical power. Traded constructions (backtest, Monte Carlo) and quarter over quarter comparisons
          step on the quarter end subset: overlap is a statistics tool, not a tradeable rebalance. The monthly
          grid also guarantees a fresh post earnings cross section every quarter: rerun the pipeline the day
          after prints for IMA's post earnings updates.
        </p>

        <h3>Construction (sequenced to avoid the equal weight versus fitted inconsistency)</h3>
        <ol>
          <li>Compute every factor peer neutrally (z score within GICS sector × index at each date), sign
            aligned to its red flag direction.</li>
          <li><strong><Term id="familybalanced">Family balanced</Term> baseline</strong>: factors are averaged
            within their family first, then across families, so four collinear valuation ratios cast ONE vote,
            and the price derived families (Momentum, Volatility) cannot swamp the fundamental ones no matter
            how many price factors exist. A name needs at least 3 populated factors across at least 2 families
            to be scored at all, and the composite is standardized again within each peer group so thin coverage
            names cannot land in extreme deciles as a data artifact. Then peer neutral
            <Term id="decile"> deciles</Term>. This baseline ships and is validated first.</li>
          <li><Term id="learnedweight">Learned weight</Term> model (ridge), trained
            <Term id="walkforward"> walk forward</Term> on the selection universe against forward relative
            returns. Concretely: a ridge regression refit every month on an expanding window (fit on all cross sections strictly before t, never on t itself; alpha 10 shrinkage on the peer group z scores plus three pre registered interaction terms; the first fit waits for six cross sections of history). Its refit by refit coefficients are published on the Validation tab, and an in sample overfit ceiling is reported next to the out of sample IC. Fitted on every run since the 183 quarter history showed the factor families carry
            opposite signs (valuation flags work, quality flags inverted), which an equal weight sum cancels
            and a fit can learn. It becomes the default scorer only if it <strong>beats the baseline
            <Term id="oos"> out of sample</Term></strong> on a paired per date IC t test at a one sided 5% bar
            (t ≥ 1.645; the hypothesis is directional and tested walk forward), <strong>with
            hysteresis</strong>: once promoted, it keeps the default until its paired edge actually
            disappears (t below zero). Rationale: adding well signed factors raises the baseline and
            mechanically shrinks the paired edge, so a gate without hysteresis demotes the stronger model
            exactly when the ingredients improve (observed 2026 07 14 and adopted by PM decision that day,
            with the same disclosure discipline as the bar change below). Current default:
            <code> {meta.default_score}</code>. Fitted then ignored weights are never presented.</li>
        </ol>
        <p className="callout warn">
          Disclosure: the promotion bar was originally two sided (t ≥ 2.0) and was relaxed to the one sided
          5% bar (t ≥ 1.645) by PM decision on 2026 07 13, <em>after</em> observing a paired t of 1.88 on the
          2011 to 2026 history. The statistical case for one sided is legitimate (the hypothesis is directional
          and out of sample), but changing a bar after seeing the number is exactly the kind of judgment call
          that must be disclosed rather than buried, so it lives here, in the config comments, and in the git
          history. The side by side model comparison ships on every run regardless of which model is default.
        </p>

        <h3>Fundamentals source: SEC EDGAR (free, point in time)</h3>
        <p>
          Fundamental factors are built from the SEC's XBRL <code>companyfacts</code> API: every figure a
          company ever filed, quarterly back to ~2009 to 2012 for most names, each stamped with its actual
          <strong> filing date</strong>, which becomes the panel's as of date (true
          <Term id="pointintime"> point in time</Term> knowledge instead of a flat reporting lag guess). Values
          are always the <em>first filed</em> number, never a later restatement. Filers that tag the same line
          item under different concepts across the years are merged by an alias map, and year to date cash flow
          figures are differenced into quarters (Q4 = FY − Q3 YTD). No API key is involved; the SEC only
          requires an identifying User Agent header. yfinance remains a per name fallback.
        </p>

        <h3>From the same data to a torpedo percentile</h3>
        <p>
          The torpedo screener reuses the pipeline above with three deliberate differences, because it
          answers a different question: not "will ACME lag its sector peers" but "is ACME dangerous
          outright."
        </p>
        <ol>
          <li>
            <strong>Same measurements, plus liquidity and crowding.</strong> It uses
            {" "}{meta.n_torpedo_features} risk features: the sell model's factors plus torpedo only ones
            like Amihud illiquidity (how violently the price moves per dollar traded, a measure of how hard
            the exit is) and the short interest snapshot. Illiquidity is torpedo only on purpose: as a
            return predictor it points the wrong way (illiquid names earn a premium), but as an exit risk it
            belongs here.
          </li>
          <li>
            <strong>z scored against the WHOLE universe, not the sector.</strong> The sell model removes
            sector effects because it wants the best and worst of every sector. The torpedo keeps them,
            because an entire sector CAN be dangerous at once, and hiding that would defeat its purpose.
          </li>
          <li>
            <strong>Equal weights, no learning, then a percentile.</strong> The aligned z scores are simply
            averaged (deliberately simple and stable; nothing is fitted, so nothing can be overfit), and the
            average is converted into a 0 to 100 universe <Term id="percentile">percentile</Term>: torpedo 88
            means ACME screens riskier than 88% of every stock in the universe that day. The percentile maps
            to a plain language <Term id="tier">tier</Term>: 0 to 30 Stable, 30 to 70 Mainstream, 70 to 100
            Elevated.
          </li>
        </ol>
        <p>
          Its report card is the absolute damage chart on the Torpedo tab: how often each torpedo decile went
          on to lose 20% or 50% of its value over the horizon window, with delistings counted at their
          terminal value. And because the sell model's learned weights fade several documented flags that the
          torpedo counts fully (quality, accruals, volatility), the two rankings are EXPECTED to disagree on
          many names; the Torpedo tab explains that disagreement, and names where both agree are the
          platform's strongest signal.
        </p>

        <h3>Data integrity gate</h3>
        <p>
          Free price feeds occasionally join two different securities under one ticker (a bankruptcy emergence,
          a ticker reuse), which manufactures a fake giant one day "return" that no investor earned. Any single
          day price ratio beyond 4x (or below 0.25x) is flagged as a <Term id="splice">splice artifact</Term>,
          every forward return window spanning that day is <strong>excluded from labels and logged</strong>
          (see the Validation tab), and a backstop drops any window beyond 50x, a pure data error net set far
          above the largest genuine small cap moonshots (~26x over two quarters in 2020 to 2021), which are
          deliberately <em>kept</em>: deleting real right tail events would erase the model's worst potential
          misses and flatter every statistic. Display statistics
          additionally report <Term id="winsorizedmean">winsorized means</Term> and medians next to plain means,
          because sector relative returns are right skewed and one lottery quarter can otherwise carry an
          average. Rank statistics like the <Term id="ic">IC</Term> are unaffected by winsorization; backtests
          always use raw (gated) returns.
        </p>

        <h3><Term id="coveragera">Coverage eras</Term></h3>
        <p>
          yfinance fundamentals reach back only ~4 to 5 quarters, so most historical cross sections were scored by
          the two price factors alone while the latest ones use all {meta.n_factors}. Every headline statistic
          is therefore split into a <em>price only era</em> and a <em>full factor era</em>: pooling them would
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
            an IC by year split, and the per era split are all reported.</li>
          <li><strong><Term id="calibration">Calibration</Term>, the Fama MacBeth way</strong>: score buckets are
            cut <em>within each quarter</em>, per bucket outcomes averaged across quarters with
            <Term id="standarderror"> standard errors</Term>, and skew robust companions (median,
            <Term id="winsorizedmean"> winsorized mean</Term>) shown alongside. The
            <Term id="reliability"> reliability curve</Term> reports P(underperform sector) per bucket: the
            score translated into a probability statement.</li>
          <li><strong><Term id="eventstudy">Event study</Term></strong>: the average cumulative sector relative
            return in the 1 to 4 quarters <em>after</em> a name sits in (or newly enters) the worst decile: the
            most presentation ready read of what a flag has historically meant.</li>
          <li><strong><Term id="decile">Decile</Term> spread</strong> (best minus worst) per period and pooled,
            with a t statistic, plus a <Term id="monotonicity">monotonicity</Term> test across deciles.</li>
          <li><strong>Backtests</strong> (quarterly rebalance, {meta.cost_bps} <Term id="turnover">bps</Term>
            cost, turnover reported): the screen is judged as <em>avoid the worst decile</em> minus
            <em> hold everything</em>, both equal weight, because comparing an equal weight portfolio to the cap
            weighted <Term id="benchmark">{meta.benchmark}</Term> would credit the model with the structural
            equal weight effect, so {meta.benchmark} is shown as market context only. Calendar year and market
            regime segments are reported so no single period can quietly carry the result.</li>
          <li><strong><Term id="montecarlo">IMA Monte Carlo</Term></strong>: thousands of random 20 name
            portfolios drawn per rebalance under each screening rule (no screen / drop decile 10 / drop 9 and 10 /
            top half only), compared as full distributions: the honest way to measure what the screen does for
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
          name's decile (each factor's raw value, formula, direction aligned sector <Term id="zscore">z
          score</Term>, within sector percentile, and quarter over quarter change), plus a coverage badge (how
          many of the {meta.n_factors} factors are actually populated), the as of date of the fundamentals used,
          the torpedo contrast, and a copyable risks section draft. "Why is this name flagged" should never
          require reading code.
        </p>

        <h3>How this differs from the Piper Sandler Sell Model</h3>
        <p>
          The PSC Sell Model shares this model's architecture (an equal weighted, sector neutral red flag
          count, deciled within sector, decile 10 = most at risk), but the ingredient lists overlap only
          partially. Piper's 14 factors (7 categories × 2) include equity duration, shareholder yield, revenue
          variance, change in days payable, EPS variance, change in receivables, EVA, change in depreciable
          life, and <Term id="sue">SUE</Term> (none of which are carried here), while this model carries
          valuation multiples (P/E, EV/EBITDA, P/S, FCF yield) and explicit quality levels (ROE, ROA, margins)
          that Piper's list does not. The peer groups also differ: Piper ranks within S&amp;P 1500 / Russell
          universe sectors, this model within the S&amp;P 600+400 union. Rank disagreements between the two on a
          specific name are therefore <em>expected</em> and usually explainable by a factor one model carries
          and the other does not; the drill down is the tool for answering exactly that question.
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
          <li><strong>No portfolio level risk model.</strong> The risk accounting table on the Validation tab
            reports what the flagged sleeve tilts toward (beta, idiosyncratic vol, liquidity, sector
            concentration), but there is no factor exposure accounting at portfolio construction. Fine at
            IMA's ~20 name scale; required before anyone sizes positions off this model. Capacity is likewise
            a non issue at student fund size and untested beyond it.</li>
          <li><strong>EDGAR fundamentals reach back to ~2009 to 2012, not further.</strong> Pre XBRL cross sections
            carry price factors only; some filers tag line items idiosyncratically (the alias map is maintained,
            not perfect); and names without a CIK fall back to shallow yfinance statements. The coverage era
            split reports exactly which cross sections carry full factor coverage. Read it before quoting any
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
