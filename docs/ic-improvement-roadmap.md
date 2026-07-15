# IC Improvement Roadmap — free data first, every paid dollar justified

**Status: sections 1 and 2 approved and largely BUILT (2026-07-13).** Implemented:
1.1 (monthly grid back to 2010, ~200 overlapping cross sections, NW lags scale with
overlap), 1.2 (family-balanced composite + coverage floors + re-standardization),
1.3 (satisfied by the monthly grid — re-run the pipeline the day after prints for a
fresh post-earnings cross section), 1.4 (peer groups are (date, sector, index); all
headline stats on the S&P 600 selection universe), 2.1 (EDGAR XBRL loader —
`edgar_loader.py`, default source), 2.2 (52w-high, IVOL, MAX, beta into the model
under a capped Volatility family; Amihud into the torpedo only — as a *return*
predictor it points the wrong way for a sell model). Per Amar: 2.6 delisting-reason
curation deprioritized, 2.7 (13F) skipped. Tier 0 is COMPLETE (1.1 through 1.6)
and section 2 is now COMPLETE too (2.3/2.4/2.5 built 2026-07-14, notes below)
except 2.6-lite, closed as infeasible on the free path (verdict below). Tier 2
and the vendor ladder remain as written.

**2.3 BUILT (2026-07-14, premise corrected):** FINRA's free bi-monthly short
interest POSITION files turned out to cover OTC equities only with one rolling
year online (verified against api.finra.org) — useless for an S&P 600 history.
The free listed-name dataset is the Reg SHO daily short sale VOLUME file
(~2018-10 onward), so the model carries short ACTIVITY (flow):
`short_vol_ratio` (trailing 63d mean short share of volume) IC +0.028 (t 2.9,
90 monthly periods) and `short_vol_chg` (flat, t 0.1, kept because specified
ex ante). Torpedo swapped its today-only short_pct_float snapshot for the
FINRA ratio, killing a quiet look-ahead. Position history (level, days to
cover) still arrives via WRDS/Compustat when access lands.

**2.4 BUILT (2026-07-14):** `insider_loader.py` pulls the SEC's quarterly
insider transactions data sets (every Form 4, structured, 2006+), keeps open
market P/S codes only, excludes 10b5-1 plan-flagged rows, keys by CIK, stamps
by FILING date. Factor `insider_npr_6m` = (buys − sells)/(buys + sells) over
126 sessions: **IC +0.023 (t 3.5, 192 monthly periods)** — instantly among
the strongest factors in the model, and its term structure RISES to +0.050
(t 4.0) at 4Q, the best slow signal we have (Lakonishok-Lee small-cap result
reproduced). Known limit: the SEC posts each quarter's set ~1-2 weeks after
quarter end, so the newest cross sections briefly lag (disclosed in UI).
CMP routine-vs-opportunistic separation is a future refinement.

**2.5 BUILT (2026-07-14):** price-based SUE. `edgar_loader.fetch_earnings_events`
collects 8-K item 2.02 dates (~67k events, 994 names, archives included) with
UTC acceptance times converted to Eastern to pick the true reaction session.
Factor `earn_react_1q` = benchmark-adjusted close-to-close move around the
print, expiring after 70 sessions: IC +0.013 (t 2.2, 195 periods), positive
at every horizon (PEAD, Bernard-Thomas). Estimates-based SUE stays gated.

**2.6-lite CLOSED (2026-07-14): Wayback route is dead.** The iShares IJR
holdings ajax/CSV endpoints have ZERO archived snapshots in the Wayback CDX
index (probed two URL shapes) — there is nothing to reconstruct membership
from on that path. Real remaining options for PIT membership: (a) IJR's own
SEC filings — N-PORT monthly XML holdings 2019+, N-Q quarterly 2004-2019
(HTML parsing, a full session of work, free); (b) WRDS comp.idxcst_his when
the account unblocks; (c) Norgate ~$40/mo. Recommendation: (b) if WRDS
unblocks soon, else (a) as its own session; the survivorship banner stays up
honestly until then.

**SECTIONS 3 + 4 BUILT, HYSTERESIS ADOPTED (2026-07-15, PM directed):**
(a) **Hysteresis on promotion** (`DEMOTION_MIN_T = 0`, state in
data/promotion_state.json): once promoted at 1.645, the learned model keeps
the default until its paired edge disappears (t < 0). Result: score_ml is
the default again; this run's paired t = +1.74 clears even the plain bar.
(b) **Tier 2 interactions**: three pre-registered family-score products
(value x quality, momentum x volatility, value x accruals) fed to the ridge
only — learned IC improved +0.035 -> **+0.038 (t 4.2)**, +0.052 (t 3.5) at
4Q. (c) **Factor-zoo null** (Harvey-Liu-Zhu discipline): 100 random
sign-consistent composites from the same pool have null mean IC +0.002
(p95 +0.012); the real model's +0.038 sits at p = 0.00 — not factor mining.
(d) **Regime-conditioned IC**: calm +0.016 (t 1.5), normal +0.036 (t 2.6),
stressed +0.061 (t 3.3) — the signal is strongest in stressed tape, the
right tail for a sell model (diagnostic split, cuts are full-sample).
(e) **Risk accounting lite**: decile 10 is NOT a beta bet (0.97 vs 1.00) —
its tilt is illiquidity (Amihud ~3x universe) and heavier shorting flow;
shipped as a Validation-tab table. (f) **Event awareness**: drill down now
shows each name's last earnings print date. (g) 1M/4Q added to the
validation horizon toggle; calibration + reliability moved up; Overview
shows the reliability curve instead of the diagnostics gate. (h) **2.6
dropped entirely per PM** (was already closed as infeasible on the free
path). Remaining ideas from section 3 not yet built: GBM with monotonicity
constraints, deflated Sharpe. Estimates (section 4.2) remain the known gap.

**PROMOTION FLIP (2026-07-14, consequence of 2.4/2.5):** the two new well
signed families lifted the equal weight baseline from ≈0 to IC +0.0105
(t 1.2) — and the ridge's paired edge over it fell to t = +1.57 < 1.645, so
**the gate demoted the learned model and score_ew is the default again**,
even though the learned model itself got STRONGER (IC +0.035, t 3.9; +0.049
t 3.2 at 4Q). The gate is doing its job (complexity must re-prove itself
against a better baseline), but the shipped default now has a weak headline
(spread −0.01, monotonicity +0.77). Whether to redesign promotion (hysteresis,
multi-horizon evidence) is a PM decision to take deliberately, with the same
disclosure discipline as the 1.645 bar decision — not a reactive tweak.

**1.6 BUILT (2026-07-13):** walk-forward IC-weighted family blending
(`model.ic_weighted_score`, `score_icw`): weights ∝ trailing 36-observation
mean family IC on REALIZED labels only (a stricter embargo than the ridge
applies — see below), negative ICs clipped to zero (families are muted, never
inverted), shrunk 50% toward equal weight; all knobs pre-registered in
config.py, not tuned. VERDICT on 2011–2026: the transparent blend is
statistically indistinguishable from the equal-weight baseline (paired
t = +0.21) while the ridge keeps a t = 1.90 edge over it. Diagnosis matches
the 1.5 term structure: the exploitable structure in this sample is the SIGN
INVERSION of quality/accruals, and a blend that can only mute (not invert)
captures none of it, while half its weight stays structurally spread over
negative-IC families. The interpretable middle ground exists but buys
essentially nothing here; reported as a third comparator on the Validation
tab (weights-over-time chart), never wired into default selection.

**1.5 BUILT (2026-07-13):** per-family IC measured at 1M/1Q/2Q/4Q
(`validate.horizon_term_structure`, diagnostic labels in `feature_engine`,
"IC decay curves" chart + table on the Validation tab). VERDICT on 2011–2026:
the quality/accruals inversion is **not** a speed problem — accruals IC
deepens from −0.014 (1M) to −0.041 (t=−2.8) at 4Q, quality negative at every
horizon. Valuation is the slow payer the literature predicts: +0.019 (1M) →
+0.061 (t=2.8) at 4Q, led by P/E and P/S. Momentum fades to negative at 4Q
(consistent with 12m momentum decay), volatility increasingly negative with
horizon (junk-rally regime compounding). The learned composite holds
+0.026→+0.036 with t ≥ 2.2 at all four horizons. Implication for 1.6: an
IC-weighted family blend would load positive on valuation and near-zero/negative
on quality/accruals — i.e. rediscover what the ridge found, transparently. No
fast/slow sleeve split is justified by speed alone; the split that matters is
sign, not horizon.

Each item below says what it is, why it should raise the IC, what it costs
(time/money), and what to read to understand it before green-lighting. Ordered so
the free statistical power comes first and money is the *last* resort.

---

## 0. Diagnosis — why the IC is ~0 today

The current composite has IC ≈ +0.017 (t ≈ 0.9). Decomposed, that's:

1. **The history only tests 2 of 15 factors.** 30 of 31 scored quarters are
   momentum + reversal (yfinance fundamentals reach ~4–5 quarters back). Of those
   two, `reversal_1m` carries everything (IC +0.025) and `mom_12_1` is flat here.
2. **33 quarterly cross sections is a tiny sample.** Even a genuinely good model
   (true IC 0.04) would fail a t-test more often than not on 33 observations.
   Statistical power, not just signal, is missing.
3. **Construction leaks.** Equal weight over 15 correlated factors makes the
   composite ~valuation-weighted (4 collinear valuation factors), thin-coverage
   names get mechanically extreme scores, and the 600+400 union makes small caps
   compete with mid caps inside one "peer" group.
4. **Horizon mismatch.** Reversal is a ~1-month effect being sampled quarterly;
   value/quality/accruals historically pay over 2–4 quarters. One horizon serves
   neither.

Fixing (2)–(4) is free. Fixing (1) is free too — that's the EDGAR project below.

**Expectation setting (read this before anything else):** a *good* small-cap
multifactor model earns a cross-sectional quarterly IC around **0.03–0.06**. The
goal is a statistically demonstrable IC with a stable sign, not 0.15. The bridge
from IC to portfolio value is Grinold & Kahn's *fundamental law of active
management*: IR ≈ IC × √breadth (independent bets per year). That's why item 1.1
(more cross sections) matters as much as any new factor: breadth is half the law.
Reading: Grinold & Kahn, *Active Portfolio Management*, ch. 6 & 10.

---

## 1. Tier 0 — free statistical power, no new data (do these first)

### 1.1 Monthly cross sections with overlapping labels
Score every month-end instead of quarter-end (same price data, same factors),
keeping the 1Q forward label. 33 observation dates become ~96. Labels overlap, so
the Newey–West lag count rises to ~2 (already scales in `validate._nw_lags`).
This is the single cheapest tripling of statistical power available, and it's the
standard construction (Jegadeesh & Titman 1993 run overlapping portfolios).
*Cost: small refactor of `_quarter_end_dates` → configurable frequency.*

### 1.2 Family-balanced, re-standardized composite
Average within each factor family first, then across families — otherwise the four
collinear valuation factors carry ~4× the weight of accruals ("equal weight by
factor" ≠ "equal weight by information"). Then z-score the composite within
sector-date again and require a minimum factor count (e.g. ≥ 3), because the mean
of 2 z-scores has ~√(15/2) times the σ of the mean of 15 — right now thin-coverage
names get extreme deciles as a data artifact (measured corr(n_factors, |score|) =
−0.13). *Cost: ~20 lines in `model.py`. Likely the largest free IC cleanup.*

### 1.3 Rebalance after earnings season
Quarter-end scoring uses the stalest possible fundamentals (right before the next
print). Score ~3 weeks into the quarter instead, when most 10-Qs are filed. Free
freshness; also matches IMA's meeting cadence better.

### 1.4 Size-and-subindustry-aware neutralization
The 600+400 union means a small-cap's "sector peers" include mid caps, so part of
every z-score is just ranking size. Either neutralize within sector × index, or
regress each factor on log-market-cap within sector and use residuals. Same
technique fixes the UNFI problem (distributor z-scored against branded CPG): GICS
industry-group (4-digit) neutralization where group sizes allow.
*Reading: any factor-construction discussion of "purifying" exposures — e.g.
Israel & Moskowitz on factor construction details mattering.*

### 1.5 Horizon term structure per family
Measure each factor's IC at 1M / 1Q / 2Q / 4Q. Expected result from the
literature: reversal pays at 1M and is noise at 1Q; value/quality/accruals build
toward 2–4Q. Then either run the model at the horizon where its families actually
pay, or split into a fast sleeve and a slow sleeve. *Cost: pure analysis on
existing data; would also make a strong dashboard chart ("IC decay curves").*

### 1.6 Walk-forward IC-weighted blending (after 1.1 gives enough history)
Replace equal family weights with weights ∝ trailing shrunk family IC (heavy
shrinkage toward equal weight; strictly walk-forward). This is the disciplined
version of "let winners carry more" without full ML. *Reading: Grinold & Kahn
ch. 10 on combining signals; shrinkage intuition from James–Stein.*

---

## 2. Tier 1 — free data upgrades (the real unlock)

### 2.1 SEC EDGAR XBRL fundamentals — THE project
`https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` returns **every
XBRL-tagged number a company ever filed**, quarterly, back to ~2009–2012 for most
names, **with the filing date attached**. Free, official, rate-limited (10 req/s,
set a User-Agent). This single source:

- extends every fundamental factor from ~5 quarters to 10+ **years** → the
  full-factor era goes from 1 scored quarter to 40+;
- replaces the flat 60-day reporting lag with the **actual filing date** (true
  point-in-time knowledge, the same property you'd pay Compustat PIT for);
- unlocks the Piper-style factors we currently can't build: change in
  receivables/DSO, change in days payable, revenue variance, EPS variance,
  depreciable-life change, plus Piotroski F-score inputs and
  Ohlson O-score / Altman Z-score distress measures.

Effort is real but bounded: the ugly part is us-gaap tag aliasing (same problem
`feature_engine.get_field` already solves for yfinance) and handling amended
filings (use the first-filed value, never the restated one). ~2–3 working
sessions. **This is the highest-value item in the whole document.**

### 2.2 New price-based factors (zero new data — the price cache already has them)
Documented cross-sectional predictors computable from existing prices + volume:

| Factor | Red flag | Reference |
|---|---|---|
| 52-week-high proximity | far below the high | George & Hwang (2004) |
| Idiosyncratic volatility | high IVOL | Ang, Hodrick, Xing, Zhang (2006) |
| MAX (biggest daily gain last month) | high (lottery demand) | Bali, Cakici, Whitelaw (2011) |
| Amihud illiquidity | high | Amihud (2002) |
| Market beta | high (betting against beta) | Frazzini & Pedersen (2014) |
| Residual momentum | low | Blitz, Huij, Martens (2011) |

These deepen the *price-only era* too — the part of history we can already
validate. IVOL + MAX are natural "torpedo" inputs as well.

### 2.3 FINRA short interest history
Bi-monthly consolidated files, free, already stubbed
(`config.FINRA_SHORT_INTEREST_URL`). Turns `short_pct_float` from a
current-snapshot metadata column into a real historical factor (level, change,
days-to-cover). *Reading: Boehmer, Jones & Zhang (2008) — short sellers are
informed.*

### 2.4 EDGAR Form 4 — insider trading
Net insider buying/selling, free from EDGAR. The refinement that matters:
separate routine trades (scheduled sellers) from opportunistic ones. *Reading:
Cohen, Malloy & Pomorski (2012), "Decoding Inside Information."*

### 2.5 Price-based earnings surprise (poor man's SUE)
Without estimates data, the market's own reaction is the surprise proxy: the
abnormal return on the earnings announcement day, which then drifts (PEAD).
Earnings dates come free from EDGAR 8-K filings or the yfinance calendar. This is
the closest free substitute for the estimates factors that are currently gated
off. *Reading: Bernard & Thomas (1989) on post-earnings-announcement drift.*

### 2.6 Point-in-time membership via ETF holdings archives
Clever free proxy: iShares publishes IJR / IJH holdings files; archived copies
(and the Wayback Machine) reconstruct historical index membership well enough to
kill most survivorship bias without buying an index-constituency feed. Not
perfect (rebalance-day gaps), but honest and free. Delisting *reasons* still need
hand-curation for the terminal-return fix.

### 2.7 13F institutional holdings (lower priority)
Ownership breadth changes predict returns (Chen, Hong, Stein 2002), free from
EDGAR, but the parsing lift is heavy relative to expected IC. Do last.

---

## 3. Tier 2 — methodology upgrades once the data exists

- **Interactions**: value conditional on quality (avoids value traps — the
  Piotroski logic), momentum conditional on IVOL, distress × valuation. The
  learned model can find these only after EDGAR gives it enough history; with
  n = 33 it cannot and should not.
- **Learned model upgrades**: rank-transformed labels, gradient boosting with
  monotonicity constraints (each factor constrained to its documented red-flag
  direction — interpretability preserved), expanding-window only. Promotion gate
  (paired t ≥ 2) already exists.
- **Multiple-testing discipline**: once we're trying 20+ factors, a t of 2.0 is
  no longer the bar. *Reading: Harvey, Liu & Zhu (2016), "…and the Cross-Section
  of Expected Returns" (argue t > 3 for new factors); López de Prado's deflated
  Sharpe ratio.* The Monte Carlo null-distribution harness (random sign-consistent
  composites) is the practical in-repo version.
- **Regime conditioning**: credit spreads / realized vol (free from FRED) as
  state variables for *when* the sell signal is trusted — only after the
  unconditional signal exists.

## 4. What the framework is structurally missing (honest list)

1. **A risk model.** No factor-exposure accounting (size/beta/industry) when
   judging the screen or building sleeves. Fine at current scale; required before
   anyone trades size on this.
2. **Estimates/revisions.** The one input free data genuinely cannot replicate
   (2.5 is a partial proxy). Also the historically strongest sell-side signal
   family for small caps.
3. **Capacity/liquidity awareness** — irrelevant for IMA's size, worth a line in
   the methodology tab.
4. **Event awareness** — the model scores through earnings dates blindly; a name
   flagged the day before a print is a different proposition than one flagged the
   day after.

---

## 5. Paid data — maximizing every dollar, in order

**Rule: don't pay for anything until EDGAR (2.1) is built and the Tier 0 items
are in.** Otherwise you're paying to widen a pipe that's leaking upstream.

**Step 0 — check WRDS access before spending anything.** UIUC (Gies) subscribes
to WRDS; students in many programs can get accounts. WRDS = CRSP
(survivorship-free prices, **delisting returns with reason codes** — exactly what
`DELISTING_TERMINAL_RETURN` needs), Compustat (point-in-time fundamentals), IBES
(estimate revisions — the unbuyable-on-a-budget dataset), and historical index
constituents. That is the entire professional research stack for **$0**. License
is research-only (no redistribution / no live-site data), so the public dashboard
would still run on EDGAR — use WRDS for validation-grade history and the paper.

If paying (personal licenses, per month, ~2026 pricing):

| Rank | Vendor | ~$ | What the dollar buys | Verdict |
|---|---|---|---|---|
| 1 | **Sharadar via Nasdaq Data Link** (SF1 fundamentals + SEP prices bundle) | ~$110 | 20+ yrs as-reported fundamentals with report dates (ARQ = PIT-ish), **including delisted names**, ticker-event history, clean and documented | Best overall $/quality for exactly this project; the standard budget-quant stack |
| 2 | **Norgate Data** (US Platinum) | ~$40 | Survivorship-free prices + **historical S&P 600/400 index constituency** | The cheapest clean solution to PIT membership specifically; pairs well with EDGAR fundamentals |
| 3 | **Financial Modeling Prep** / **EODHD** | $30–60 | As-reported statements w/ filing dates, delisted coverage thinner than Sharadar | Acceptable fallback; verify small-cap coverage before paying a year |
| 4 | **Tiingo** | $10–30 | Excellent clean prices, thin fundamentals | Price-feed redundancy, not a fundamentals answer |
| — | **Zacks / estimate feeds** | $300+ | Revisions & surprise history | **Don't** — last dollar, not first; IBES via WRDS if the university grants it |
| — | Real-time / streaming anything | any | Latency this model cannot use | Never — the model is quarterly |

Suggested spend curve: **$0 now** (Tier 0 + EDGAR + FINRA + WRDS-if-available) →
**~$40** (Norgate, when PIT membership becomes the binding constraint) →
**~$110** (Sharadar, when EDGAR tag-mapping maintenance costs more time than
$110/mo is worth) → estimates only after the model has demonstrated IC without
them.

---

## 6. Recommended sequence

1. **Tier 0, items 1.1–1.3** (monthly cross sections, family-balanced composite,
   post-earnings rebalance) — one working session, immediate power.
2. **EDGAR companyfacts loader (2.1)** — the big unlock; 2–3 sessions.
3. **FINRA short interest (2.3) + price-based factors (2.2)** — one session.
4. Re-validate everything: the era table will finally have a real full-factor
   era; horizon term structure (1.5) decides the headline horizon.
5. Then and only then: learned-model/interaction work (Tier 2), Norgate/Sharadar
   as needed, estimates last.
