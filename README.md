# Relative Sell Model

Rank S&P 600 (SmallCap) and S&P 400 (MidCap) stocks by expected **relative
underperformance versus their GICS sector peers** over a forward horizon (default 1 and 2
quarters). The output is a continuous relative risk score and a **sector neutral decile**,
validated as a cross sectional return ranking problem. The S&P 400 is unioned in so names
that graduate out of the 600 up into the 400 are still scored and still match in the
portfolio overlay.

The label for every name on every rebalance date is its **sector relative forward
return**:

```
fwd_rel_ret(t, h) = stock_return(t, t+h) − median(sector_peers)(t, t+h)
```

This is deliberately a *different question* from two adjacent models — see the contrast
below. Validation is the whole point of the project, not an appendix.

---

## The three way contrast (enforced in code and docs)

| Model | Cross section | Target |
|---|---|---|
| **This — Relative Sell Model** | **within GICS sector** (sector neutral) | **relative** forward return (stock − sector peer median) |
| Torpedo screener | whole universe (cross sectional Z score in PCA space) | **absolute** drawdown / blow up risk |
| Earnings event model | per event window | binary post earnings direction |

Concretely, in this repo: every factor is neutralized *within* GICS sector before it is
used (`feature_engine.neutralize_factors`), and the only label the model is ever scored
against is the sector relative forward return (`feature_engine.build_panel`,
`validate.ic_time_series`). There is no universe wide Z score and no 0/1 event label.

---

## Quickstart

```bash
pip install -r requirements.txt

# Deterministic machinery demo (no network) — planted signal, clean diagnostics:
python main.py --synthetic --learned-weights

# Real data on a fast subset of the universe:
python main.py --max-tickers 80 --learned-weights

# Full universe, 1-quarter horizon, 10 bps cost:
python main.py --horizon-q 1 --cost-bps 10

# Diagnostics only (placebo / look-ahead / survivorship):
python -m diagnostics.run_all

# Dashboard (after any run populates webapp/public/data):
cd webapp && npm install && npm run dev
```

CLI flags: `--synthetic`, `--since YYYY-MM-DD`, `--horizon-q {1,2}`, `--cost-bps N`,
`--learned-weights`, `--max-tickers N`, `--source {yfinance,factset,spglobal}`,
`--refresh`, `--no-webapp`.

> **Interpreter:** built and tested against Python 3.11 (the repo uses `statsmodels`
> for the Newey West HAC t stat). Any 3.10+ env meeting `requirements.txt` works.

---

## Architecture (mirrors IMA PCA conventions)

| Module | Role |
|---|---|
| `config.py` | factor taxonomy (incl. **Volatility family**), red flag direction map, **selection universe** (S&P 600), monthly grid + horizons, cost bps, **data integrity gate thresholds**, coverage era threshold, Monte Carlo knobs, source flags, paths |
| `universe.py` | **point in time** S&P 600 + 400 membership store loader + Wikipedia current fallback (warns loudly) |
| `data_loader.py` | deep price + **volume** history from 2010 (delisting aware), shallow yfinance fundamentals (fallback), short interest |
| `edgar_loader.py` | **SEC EDGAR XBRL companyfacts**: free quarterly fundamentals back to ~2009 with true **filing date as of stamps**, tag alias merging, YTD de-accumulation, first filed values (never restatements). No API key — User-Agent only |
| `feature_engine.py` | sector relative factor computation (`get_field` alias pattern), the panel, **delisting aware, splice gated forward relative returns** (`detect_price_anomalies` + exclusion log), sector neutralization |
| `model.py` | equal weight baseline + optional **walk forward** learned weight model; sector neutral deciles |
| `validate.py` | Fama MacBeth IC + Newey West t stat (lags scale with label overlap), **per date calibration with SE bands / medians / winsorized means**, **P(underperform) reliability curve**, **decile 10 event study**, **coverage era split**, IC by year, decile spread + monotonicity, per factor IC, baseline vs learned + **paired promotion test** |
| `backtest.py` | equal weight **hold all** base + "avoid worst decile" sleeve (screen judged vs its own EW universe; IJR = context), benchmark metrics row, **calendar year + market regime segments** |
| `simulate.py` | **IMA Monte Carlo**: distributions of random 20 name portfolios per screening tier (replaces the removed long/short sleeve) |
| `wrds_loader.py` | **WRDS scaffold** (CRSP delisting events + reason codes, Compustat quarterly) — research license only, never exported to the public site; credentials in `.env` |
| `deep_loader.py` | **gated** FactSet / S&P Global PIT fundamentals + estimate revision loader |
| `webapp_export.py` | dump every table to `webapp/public/data/*.json` + `meta.json`, incl. **per name drill down**, transitions, exclusions, MC results |
| `main.py` | orchestrator + CLI |
| `diagnostics/` | placebo IC, look ahead assertion, survivorship assertion, synthetic generator, `run_all` |
| `overrides.py` | **analyst override layer**: attributed, expiring annotations that never touch the score, scored quarterly (analyst vs model hit rates by reason code) |
| `webapp/` | React + Vite + TypeScript dashboard (Plotly), 7 tabs + click through per name drill down |
| `docs/` | design documents (override layer rationale, IC improvement roadmap) |

---

## Factors

Every factor is a *documented cross sectional return predictor*, not an ad hoc flag.
Direction is expressed as a **red flag direction**: after sign alignment, **larger ⇒ more
expected sector relative underperformance**, so the equal weight composite is a simple
mean (no internal sign inconsistency).

| Family | Factors | Red flag | Anomaly |
|---|---|---|---|
| Valuation | `pe_ratio`, `ev_to_ebitda`, `ps_ratio`, `fcf_yield` | rich (low FCF yield) | value premium / HML |
| Momentum | `mom_12_1`, `reversal_1m`, `high_52w` | low 12 1 momentum; high last month return; far below the 52w high | Jegadeesh Titman + short term reversal + George Hwang |
| Volatility | `ivol_63d`, `max_ret_1m`, `beta_252d` | high idio vol / lottery pops / high beta | IVOL puzzle (Ang et al) + MAX (Bali et al) + BAB (Frazzini Pedersen) |
| Quality | `roe`, `roa`, `gross_margin`, `fcf_margin`, `roe_yoy`, `gross_margin_yoy` | low / declining | profitability premium / RMW |
| Investment | `asset_growth_yoy`, `net_issuance_yoy` | high | asset growth (CGS) + dilution (Daniel Titman) |
| Earnings quality | `accruals_ocf_ni` | low OCF/NI (high accruals) | Sloan accruals |
| Short activity | `short_vol_ratio`, `short_vol_chg` | high / rising share of volume sold short | informed shorting flow (Boehmer Jones Zhang; Diether Lee Werner). FINRA Reg SHO daily files (flow, not positions), history from Oct 2018 |
| Estimates *(gated)* | `est_revision_3m`, `sue` | downward revisions / low SUE | post revision / SUE drift |

The estimate factors are **off by default** and only populated by `deep_loader.py`
(FactSet / S&P Global). Amihud illiquidity is computed but feeds the **torpedo
screener only**: as a *return* predictor it points the other way (the illiquidity
premium), so it is deliberately kept out of the sell ranking.

---

## Construction (sequenced to avoid the equal weight vs fitted inconsistency)

0. **Peer groups are (date, sector, index)** and cross sections are **monthly back to
   2010** (~200 overlapping observation dates; Newey West lags scale with the overlap).
   S&P 600 names are ranked against 600 sector peers only; S&P 400 graduates against 400
   peers only — the 400 exists to be *monitored*, never picked from. Every headline
   statistic runs on the **S&P 600 selection universe** (`config.SELECTION_INDEX`).
1. Compute each factor **peer neutrally** (winsorize, then z score within sector × index
   at each date), sign aligned to its red flag direction.
2. **Baseline = family balanced composite**: factors are averaged within family first,
   then across families ("equal weight by information") — four collinear valuation ratios
   cast one vote, and the price derived families (Momentum, Volatility) can never swamp
   the fundamentals. Names need ≥ `MIN_FACTORS_FOR_SCORE` factors over
   ≥ `MIN_FAMILIES_FOR_SCORE` families, and the composite is re-standardized within each
   peer group (thin coverage names must not land in extreme deciles as an artifact).
   → peer neutral deciles. This baseline ships and is validated **first**.
3. **Optional learned weight model** (ridge / logistic / GBM), trained **walk forward on
   the selection universe** against forward relative returns. It becomes the default
   scorer **only if it beats the baseline out of sample on a paired per date IC t test**
   (`validate.paired_ic_test`, t ≥ `config.PROMOTION_MIN_T`); a point estimate edge is
   noise, not a win. Otherwise the baseline stays default. We never present fitted then
   ignored weights.

### Baseline vs learned — out of sample comparison

The dashboard's Validation tab and the terminal summary print both models side by side.
Example (synthetic demo, planted linear signal — learned correctly wins and is promoted):

```
equal_weight     IC=+0.140  t=+14.3  IR=1.73
learned_weight   IC=+0.232  t=+14.1  IR=3.30   <- beats baseline OOS, becomes default
```

Example (real, 73 name current only subset — learned loses, **baseline kept as default**):

```
equal_weight     IC=+0.018  t=+0.77  IR=0.14   <- default
learned_weight   IC=−0.027  t=−1.33  IR=−0.23
```

On a small, current only universe the baseline IC is statistically indistinguishable from
zero. That is an honest result (see limitations), and the learned model failing to beat it
is exactly why the code keeps the baseline in charge.

---

## Data integrity gate (runs before any statistic)

Free price feeds occasionally splice two securities under one ticker (bankruptcy
emergence, ticker reuse), manufacturing fake giant one day "returns" (canonical case:
CHRD, where the pre Chapter 11 Oasis stub at $0.07 meets the new equity at $19.93 — a
+28,000% day nobody earned; a single such window once made calibration bucket 4 the
"best" performer). The gate (`feature_engine.detect_price_anomalies`):

* flags any single day price ratio outside `[0.25x, 4x]` as a **splice artifact**;
* **excludes** every forward return window spanning a flagged day (reason
  `splice_window`), plus a 50x-per-window backstop (`extreme_return`) — a pure data error
  net set far above the largest *genuine* small cap moonshots (~26x over two quarters in
  2020–21), which are deliberately **kept**: deleting real right tail events would erase
  the model's worst potential misses and flatter every statistic;
* logs every exclusion to `webapp/public/data/exclusions.json` and the terminal — nothing
  is silently dropped, nothing corrupt is silently kept.

Display statistics additionally report **medians and 1% winsorized means** next to plain
means (`config.LABEL_WINSOR_PCT`), because sector relative returns are right skewed. Rank
statistics (IC) are winsorization invariant; backtests always use raw gated returns.

---

## Validation (first class deliverable)

* **Sector neutral IC** = −Spearman(score, forward relative return) per cross section
  (sign convention: *positive = skill*, because the score ranks underperformance),
  averaged Fama MacBeth with a **Newey West t stat whose lags scale with the label
  overlap** (h − 1 quarters, floored at 1); mean IC, t, IR, the IC time series, and an
  **IC by calendar year** split are all reported.
* **Coverage eras** — yfinance fundamentals reach back only ~4–5 quarters, so historical
  cross sections are scored by the price factors alone. Every headline stat is split into
  a **price-only era** and a **full-factor era** (`config.ERA_MIN_AVG_FACTORS`), so a two
  factor history is never presented as evidence about the 15 factor composite.
* **Calibration, the Fama MacBeth way** — score quantiles are cut **within each date**,
  then per bin stats are averaged across dates with **standard errors**; medians and
  winsorized means ride alongside. The **reliability curve** reports P(underperform
  sector median) per bin — the score translated into a probability a PM can use.
* **Decile 10 event study** — average cumulative sector relative return 1–4 quarters
  *after* a name sits in (or newly enters) the worst decile, with error bands. The
  presentation ready read of what a flag has historically meant (and the same chart
  format Piper leads its deck with).
* **"What broke, and when"** — rolling one year IC per factor FAMILY (the composite can
  net to zero while families are strongly nonzero in opposite directions), plus a
  **stress window table**: every named disaster (2011 downgrade, 2015/16 industrial
  recession, Q4 2018, COVID crash, COVID junk rally, 2022 rate shock) gets its own row
  of IC / spread / benchmark move, so regime failure is visible instead of averaged away.
* **Decile spread** = best decile minus worst decile forward relative return, per period and
  pooled, with a t stat, plus a **monotonicity** test (Spearman of decile vs mean relative
  return; a good model is ≈ −1).
* **Backtests** (quarterly rebalance, configurable bps cost, turnover reported): the
  screen is judged as **"avoid the worst decile" minus "hold everything", both equal
  weight** — comparing an EW portfolio against the cap weighted IJR would credit the model
  with the structural equal weight effect, so IJR is reported as market context only
  (with its own metrics row). Value added is reported with tracking error, IR, and hit
  rate, plus **calendar year and market regime segments** so no single period can quietly
  carry the result.
* **IMA Monte Carlo** (`simulate.py`) — thousands of random 20 name portfolios per
  rebalance under each screening rule (no screen / drop decile 10 / drop 9–10 / top half
  only), compared as full distributions (median CAGR, tails, P(beat unscreened median)).
  This is the honest way to measure what the screen does for a concentrated picker, and
  it **replaces the removed long/short sleeve** (IMA is long only, and flat bps costs
  wildly understate small cap borrow).
* **Walk forward only**: features at t use data ≤ t; labels use returns in (t, t+h]. No
  global fit.

## Per name transparency

Every ticker in the dashboard is clickable: the drill down shows the factor
decomposition behind the decile (raw value, formula, direction aligned sector z score,
within sector percentile, QoQ change per factor), a coverage badge, the fundamentals
as of date, the torpedo contrast, and a **copyable risks section draft** whose base rate
claims are gated until the full factor era is long enough to cite honestly. The
Portfolio Overlay tab turns this into a quarterly **holdings risk review** (QoQ decile
transitions, NEW / DOUBLE flag badges, universe flag churn, decile transition matrix,
copy as markdown).

---

## Point in time data schema & survivorship

Universe membership is read from a point in time store, `data/sp600_membership.csv`:

```
ticker, company, gics_sector, start_date, end_date, delist_note
```

`is_member(ticker, date) := any row with start_date ≤ date ≤ (end_date or +∞)`. A name that
left and re entered the index has multiple rows. Names that left via `delisted` are the
survivorship cases the backtest carries to terminal value.

Forward returns are **delisting aware**: a name that stops trading during the horizon is the
strongest possible underperformer and is carried to `config.DELISTING_TERMINAL_RETURN`
(= −100%), never dropped (`feature_engine._forward_returns`,
`diagnostics/survivorship_assert.py`).

If no real PIT store is present, `universe.py` seeds the store from **today's** Wikipedia
membership and **warns loudly** that the panel is now survivorship biased (current members
are assumed to have held for all past dates). Replace the file with a true PIT export
(S&P Global / CRSP) for a clean backtest.

---

## Diagnostics (acceptance gate)

`python -m diagnostics.run_all` (and every `main.py` run):

* **Placebo** — shuffling the score within each cross section collapses IC to ≈ 0. If IC
  survives the shuffle, it was an artifact, not skill.
* **Look ahead** — recomputing price factors on history *truncated at t* must not change the
  value at t; and no forward return column may ever appear among the model's features.
* **Survivorship** — a synthetic delisting must surface as a terminal return, not a dropped
  row; and the membership store is flagged if it is current only.

---

## Methodology limitations (honest)

In the spirit of IMA PCA's limitations section — the things to say out loud:

- **Fundamental depth now comes from SEC EDGAR** (quarterly back to ~2009–2012 for most
  names, true filing date as of stamps). Residual gaps: pre XBRL history (~pre 2009) has
  no fundamentals, some filers tag idiosyncratically (alias map maintenance), and
  yfinance remains the fallback for names without a CIK. The coverage era split reports
  exactly which cross sections carry full factor coverage — read it before quoting any
  pooled number.
- **Estimate revision / SUE factors are off by default.** They cannot be reliably built from
  yfinance, so they are gated behind `config.USE_ESTIMATE_FACTORS` + a real connector. They
  are **never** synthesized from price data.
- **Current only membership is survivorship biased.** Until a true point in time store is
  supplied, pre today cross sections silently assume today's members, and backtest history
  is optimistic. The app header and Methodology tab both flag this.
- **Small universes ⇒ weak IC.** On a small / current only universe the IC is often
  statistically indistinguishable from zero. That is a truthful outcome, not a bug; a full
  PIT, deep history run is required for a real verdict.
- **Sectors with < 5 names on a date are dropped** from that cross section — within sector
  ranks are meaningless on tiny groups (`config.MIN_NAMES_PER_SECTOR`).
- **Transaction costs are a turnover × bps approximation** with target (not drift) weights.
  The Monte Carlo simulation is gross of costs (all tiers redraw identically, so costs
  cancel in the tier comparison).
- **Delistings are carried at −100%** (`config.DELISTING_TERMINAL_RETURN`), which is right
  for bankruptcies but wrong for acquisitions (usually a premium). With a current only
  membership snapshot the panel carries ~0 delistings so the bias is dormant, but a true
  PIT store must arrive with a `delist_note` distinguishing M&A from failure before the
  terminal return logic can be trusted on history.
- **The splice gate is a heuristic.** Single day moves beyond 4x are treated as data
  artifacts; every exclusion is logged to `exclusions.json` for human review rather than
  silently discarded — audit that file after each refresh.
- **Whatever `source` the header shows is what the dashboard is.** A `synthetic` source is
  a machinery demonstration with a planted signal, clearly labeled. Re run
  `python main.py` to point the dashboard at real data.

---

## Web dashboard

React + Vite + TypeScript under [`webapp/`](webapp/). Every run exports JSON to
`webapp/public/data/*.json` + `meta.json`; the app builds its Plotly figures from those
tables. Tabs:

- **Overview** — the question, three way contrast, headline IC/decile KPIs, coverage era
  callout, diagnostics gate (now incl. the data integrity / splice gate).
- **Sector Deciles** — sector × decile heatmap; names by sector.
- **Torpedo Screener** — the integrated absolute risk view: universe percentile + tier, and a relative versus absolute contrast scatter that flags the double red flag names.
- **Factor IC** — per factor IC bar (by family) + table, with a thin history warning when
  factors have too few scored quarters to mean anything.
- **Validation / Backtest** — coverage era split, IC time series + IC by year, Fama MacBeth
  calibration with error bands / medians / winsorized means, P(underperform) reliability
  curve, decile 10 event study, paired promotion test, exclusions log, EW vs EW backtest
  with IJR context, calendar year + regime segments, and the IMA Monte Carlo distributions.
- **Portfolio Overlay** — the quarterly holdings risk review: QoQ decile transitions,
  top quantitative flags per holding, NEW / DOUBLE badges, universe flag churn, decile
  transition matrix, copy as markdown.
- **Methodology** — full write up incl. limitations, PIT schema, data integrity gate, and
  the Piper Sandler contrast.

Every acronym and term in the dashboard (IC, IR, Fama MacBeth, Newey West, Sharpe, CAGR,
decile, accruals, and so on) is hoverable and shows an inline plain language definition.
**Every ticker is clickable** and opens the per name drill down: factor waterfall, raw
values + formulas, sector percentiles, QoQ changes, coverage badge, and a copyable risks
section draft.

---

## Deploying the dashboard to Vercel

The dashboard is a static single page app: it reads the JSON that the pipeline commits under
`webapp/public/`, so there is nothing to run server side and no environment variables are
needed. Config lives in [`webapp/vercel.json`](webapp/vercel.json) (Vite framework preset,
single page rewrites, and a short cache on the data files).

First deploy, from the repo root:

```bash
npm i -g vercel          # once
cd webapp
vercel                   # link + preview deploy; set Root Directory to "webapp" when asked
vercel --prod            # promote to production
```

On subsequent runs, refresh the data and redeploy:

```bash
python main.py           # regenerates webapp/public/data/*.json + meta.json
cd webapp && vercel --prod
```

Notes:

- The Vercel project **Root Directory must be `webapp`** (the app is not at the repo root).
  The CLI asks on first link; in the dashboard it is under Settings, General, Root Directory.
- Vercel runs `npm run build`, which copies `webapp/public/` (data + meta) into `dist/`, so the
  deployed site always ships the data from the last committed pipeline run. Rerun `python main.py`
  and commit to update what the site shows.
- The build is fully static and self contained; no API keys reach the browser.

---

## Acceptance

Runs end to end on recent data; placebo IC ≈ 0 (clean separation on synthetic);
look ahead + survivorship assertions pass; the Validation tab renders non empty
IC / decile / backtest charts; baseline IC and t stat are reported in the terminal,
`meta.json`, and the dashboard.
