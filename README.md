# Relative Sell Model

Rank S&P 600 stocks by expected **relative underperformance versus their GICS sector
peers** over a forward horizon (default 1 and 2 quarters). The output is a continuous
relative risk score and a **sector neutral decile**, validated as a cross sectional
return ranking problem.

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
| `config.py` | factor taxonomy, sector neutral **red flag direction** map, horizons, cost bps, rebalance freq, model + estimate source flags, paths |
| `universe.py` | **point in time** S&P 600 membership store loader + Wikipedia current fallback (warns loudly) |
| `data_loader.py` | deep price history (delisting aware), shallow yfinance fundamentals, short interest |
| `feature_engine.py` | sector relative factor computation (`get_field` alias pattern), the panel, **delisting aware forward relative returns**, sector neutralization |
| `model.py` | equal weight baseline + optional **walk forward** learned weight model; sector neutral deciles |
| `validate.py` | Fama MacBeth IC + Newey West (5 lag) t stat, decile spread + monotonicity, calibration, per factor IC, baseline vs learned |
| `backtest.py` | long only "avoid worst decile" vs IJR + sector neutral long/short; turnover, costs, delisting aware |
| `deep_loader.py` | **gated** FactSet / S&P Global PIT fundamentals + estimate revision loader |
| `webapp_export.py` | dump every table to `webapp/public/data/*.json` + `meta.json` |
| `main.py` | orchestrator + CLI |
| `diagnostics/` | placebo IC, look ahead assertion, survivorship assertion, synthetic generator, `run_all` |
| `webapp/` | React + Vite + TypeScript dashboard (Plotly), 6 tabs |

---

## Factors

Every factor is a *documented cross sectional return predictor*, not an ad hoc flag.
Direction is expressed as a **red flag direction**: after sign alignment, **larger ⇒ more
expected sector relative underperformance**, so the equal weight composite is a simple
mean (no internal sign inconsistency).

| Family | Factors | Red flag | Anomaly |
|---|---|---|---|
| Valuation | `pe_ratio`, `ev_to_ebitda`, `ps_ratio`, `fcf_yield` | rich (low FCF yield) | value premium / HML |
| Momentum | `mom_12_1`, `reversal_1m` | low 12 1 momentum; high last month return | Jegadeesh Titman + short term reversal |
| Quality | `roe`, `roa`, `gross_margin`, `fcf_margin`, `roe_yoy`, `gross_margin_yoy` | low / declining | profitability premium / RMW |
| Investment | `asset_growth_yoy`, `net_issuance_yoy` | high | asset growth (CGS) + dilution (Daniel Titman) |
| Earnings quality | `accruals_ocf_ni` | low OCF/NI (high accruals) | Sloan accruals |
| Estimates *(gated)* | `est_revision_3m`, `sue` | downward revisions / low SUE | post revision / SUE drift |

The estimate factors are **off by default** and only populated by `deep_loader.py`
(FactSet / S&P Global). yfinance cannot supply them, so they are never faked from it.

---

## Construction (sequenced to avoid the equal weight vs fitted inconsistency)

1. Compute each factor **sector neutrally** (winsorize, then z score within GICS sector at
   each date), sign aligned to its red flag direction.
2. **Baseline = equal weight composite** of the sector neutral factors → sector neutral
   deciles. This Piper style baseline ships and is validated **first**.
3. **Optional learned weight model** (ridge / logistic / GBM), trained **walk forward**
   against forward relative returns. It becomes the default scorer **only if it strictly
   beats the baseline out of sample** (`main.py`); otherwise the baseline stays default.
   We never present fitted then ignored weights.

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

## Validation (first class deliverable)

* **Sector neutral IC** = −Spearman(score, forward relative return) per cross section
  (sign convention: *positive = skill*, because the score ranks underperformance),
  averaged Fama MacBeth with a **Newey West (HAC, 5 lag) t stat**; mean IC, t, IR, and the
  IC time series are all reported.
* **Decile spread** = best decile minus worst decile forward relative return, per period and
  pooled, with a t stat, plus a **monotonicity** test (Spearman of decile vs mean relative
  return; a good model is ≈ −1).
* **Backtests** (quarterly rebalance, configurable bps cost, turnover reported):
  (a) long only "avoid the worst sector neutral decile" vs IJR; (b) sector neutral
  long/short (long best decile, short worst). CAGR, vol, Sharpe, max DD, hit rate.
* **Walk forward only**: features at t use data ≤ t; labels use returns in (t, t+h]. No
  global fit.

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

- **yfinance caps fundamental depth at ~4–5 quarters.** Valuation, quality, accruals,
  asset growth and issuance factors only populate the most recent cross sections; YoY trend
  factors need ~5 quarters and are frequently `NaN` and dropped (never imputed/faked). The
  **deep history that drives the multi year backtest is the price factors** (momentum,
  reversal). The fix is `deep_loader.py` (FactSet / S&P Global), gated behind `.env`.
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
- **Transaction costs are a turnover × bps approximation** with target (not drift) weights;
  the long/short sleeve turns over heavily by construction (full decile refresh each quarter).
- **The committed dashboard data uses `source = synthetic`** — a machinery demonstration with
  a planted signal, clearly labeled in the header. Re run `python main.py` to point the
  dashboard at real data.

---

## Web dashboard

React + Vite + TypeScript under [`webapp/`](webapp/). Every run exports JSON to
`webapp/public/data/*.json` + `meta.json`; the app builds its Plotly figures from those
tables. Tabs:

- **Overview** — the question, three way contrast, headline IC/decile KPIs, diagnostics gate.
- **Sector Deciles** — sector × decile heatmap; names by sector.
- **Torpedo Screener** — the integrated absolute risk view: universe percentile + tier, and a relative versus absolute contrast scatter that flags the double red flag names.
- **Factor IC** — per factor IC bar (by family) + table.
- **Validation / Backtest** — IC time series, decile monotonicity, calibration, baseline vs learned, equity curves.
- **Portfolio Overlay** — paste a sleeve; see which holdings sit in the worst sell decile.
- **Methodology** — full write up incl. limitations and PIT schema.

Every acronym and term in the dashboard (IC, IR, Fama MacBeth, Newey West, Sharpe, CAGR,
decile, accruals, and so on) is hoverable and shows an inline plain language definition.

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
