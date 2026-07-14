"""Configuration for the **Relative Sell Model**.

WHAT THIS MODEL IS  (read this before touching anything)
--------------------------------------------------------
This ranks S&P 600 stocks by expected **relative underperformance versus their
GICS sector peers** over a forward horizon (default 1 and 2 quarters). The
output is a continuous relative risk score and a **sector neutral decile**. It
is a cross sectional *return ranking* problem whose label is

    forward_relative_return = stock_return(t, t+h)  -  median(sector_peers)(t, t+h)

WHAT THIS MODEL IS **NOT**  (do not blur these — they are different questions)
-----------------------------------------------------------------------------
* It is NOT the IMA torpedo screener. That ranks across the WHOLE universe
  (cross sectional Z score in PCA space) and targets *absolute* drawdown /
  blow up risk. Here every factor is neutralized WITHIN GICS sector and the
  target is *relative* forward return, not absolute drawdown.
* It is NOT a binary post earnings event classifier (e.g. Ben's model). There
  is no event window and no 0/1 label; the label is a continuous cross sectional
  return rank.

Every factor below is a *documented cross sectional return predictor* with an
academic anomaly behind it — not an ad hoc risk flag. Direction is expressed as
"red flag direction": +1 means a HIGHER raw value predicts WORSE forward
relative return (more sell risk).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# Universe / benchmark
# =============================================================================
BENCHMARK_TICKER: str = "IJR"  # iShares S&P Small Cap 600 ETF (long only benchmark)
SECTOR_KEY: str = "gics_sector"  # the column factors are neutralized within

# IMA selects from the S&P 600 ONLY; the S&P 400 is unioned in purely so
# graduated holdings keep getting scored for the portfolio overlay. The two
# never share a peer group: factors are neutralized, labels medianed, and
# deciles cut within (date, sector, index), and every SELECTION statistic
# (IC, calibration, event study, backtest, Monte Carlo) runs on the selection
# index only. The 400 exists to be monitored, not to be picked from.
SELECTION_INDEX: str = "S&P 600"

# Minimum names a peer group (date x sector x index) must have to be ranked.
# Below this, cross sectional ranks are meaningless; the names are dropped from
# that cross section (and logged).
MIN_NAMES_PER_SECTOR: int = 5

# =============================================================================
# Forward horizon + rebalance
# =============================================================================
# Horizons (in quarters) at which forward RELATIVE returns are measured.
HORIZONS_Q: tuple[int, ...] = (1, 2)
DEFAULT_HORIZON_Q: int = 1
# Cross sections are cut MONTHLY (~200 observation dates back to 2010): the
# labels still look one/two quarters ahead, so adjacent months overlap and the
# Newey West lag count scales accordingly (see validate._nw_lags). The monthly
# grid is the standard overlapping-portfolio construction (Jegadeesh Titman
# 1993) and triples statistical power from the same price history. It also
# guarantees a fresh post earnings cross section every quarter — re-run
# ``python main.py`` the day after prints for IMA's post earnings updates.
# TRADED sleeves (backtest, Monte Carlo) still step quarter to quarter on the
# quarter end subset: overlapping holdings are a statistics tool, not a
# tradeable rebalance.
REBALANCE_FREQ: str = "M"          # "M" (monthly) | "Q" (quarterly) cross sections
PERIODS_PER_QUARTER: dict[str, int] = {"M": 3, "Q": 1}
TRADING_DAYS_PER_QUARTER: int = 63

# Horizon term structure (roadmap 1.5): DIAGNOSTIC label horizons on which the
# validation layer measures each factor family's IC — the "IC decay curves".
# Tuples are (label suffix, trading days, calendar months). The 1q/2q entries
# reuse the model's label columns; extra suffixes get their own
# fwd_ret_/fwd_rel_ret_ columns built the same way (delisting aware, splice
# gated). These horizons NEVER feed scoring; they answer "at what speed does
# each family pay" — e.g. whether the quality/accruals inversion at 1Q is a
# horizon mismatch (turns positive at 4Q) or a genuine regime problem
# (negative everywhere). The published exclusions log stays restricted to the
# model horizons so one splice event is not logged once per diagnostic label;
# the gate itself is applied to every horizon.
TERM_STRUCTURE_HORIZONS: list[tuple[str, int, int]] = [
    ("1m", 21, 1),
    ("1q", 63, 3),
    ("2q", 126, 6),
    ("4q", 252, 12),
]

# =============================================================================
# Factor taxonomy
# Each factor is computed, then neutralized WITHIN GICS sector at each date
# (cross sectional z score by default; see NEUTRALIZE_METHOD).
# RED_FLAG_DIRECTION: +1 => higher raw value predicts WORSE forward relative
# return (more sell risk); -1 => higher raw value predicts BETTER (less risk).
# After multiplying by direction every factor points the SAME way: larger =
# more expected underperformance. The equal weight composite is then just the
# mean of the direction aligned sector neutral factor scores.
# =============================================================================

# --- Valuation (rich = red flag): expensive names underperform peers ---------
#     Anomaly: value premium (Fama French HML); cheap > expensive cross sectionally.
VALUATION_FACTORS: list[str] = [
    "pe_ratio",        # trailing P/E              (high = rich = red flag)
    "ev_to_ebitda",    # EV / EBITDA               (high = rich = red flag)
    "ps_ratio",        # price / sales             (high = rich = red flag)
    "fcf_yield",       # FCF / EV                   (LOW = rich = red flag)
]

# --- Momentum ----------------------------------------------------------------
#     Anomalies: Jegadeesh Titman 12 1 momentum (losers keep losing), the
#     short term (1 month) reversal effect, and the 52 week high effect
#     (George Hwang 2004: names far below their high keep lagging).
MOMENTUM_FACTORS: list[str] = [
    "mom_12_1",        # 12m minus 1m total return (LOW = loser = red flag)
    "reversal_1m",     # last 1m return            (HIGH = reverses down = red flag)
    "high_52w",        # price / trailing 52w high (LOW = far below high = red flag)
]

# --- Volatility / lottery (high = red flag) -----------------------------------
#     Anomalies: idiosyncratic volatility (Ang Hodrick Xing Zhang 2006), the
#     MAX lottery demand effect (Bali Cakici Whitelaw 2011), and betting
#     against beta (Frazzini Pedersen 2014). A separate FAMILY on purpose: the
#     family balanced composite gives each family ONE vote, so the price
#     derived families (momentum, volatility, and the earnings reaction) stay
#     a minority of the family count and can never swamp the fundamental,
#     flow, and filing based signals no matter how many factors they contain.
VOLATILITY_FACTORS: list[str] = [
    "ivol_63d",        # residual daily vol vs benchmark, ~3m (HIGH = red flag)
    "max_ret_1m",      # max single day return, last month    (HIGH = lottery = red flag)
    "beta_252d",       # market beta vs benchmark, ~12m       (HIGH = red flag)
]

# --- Quality / profitability (low / declining = red flag) --------------------
#     Anomaly: quality / profitability premium (Novy Marx, Fama French RMW).
QUALITY_FACTORS: list[str] = [
    "roe",             # return on equity          (LOW = red flag)
    "roa",             # return on assets          (LOW = red flag)
    "gross_margin",    # gross profit / revenue    (LOW = red flag)
    "fcf_margin",      # FCF / revenue             (LOW = red flag)
    "roe_yoy",         # YoY change in ROE         (declining = red flag)
    "gross_margin_yoy",# YoY change in gross margin(declining = red flag)
]

# --- Investment / growth (high = red flag) -----------------------------------
#     Anomalies: asset growth anomaly (Cooper Gulen Schill) and the
#     net share issuance / dilution anomaly (Daniel Titman, Pontiff Woodgate).
INVESTMENT_FACTORS: list[str] = [
    "asset_growth_yoy",  # YoY total assets        (HIGH = empire building = red flag)
    "net_issuance_yoy",  # YoY shares outstanding  (HIGH = dilution = red flag)
]

# --- Earnings quality (low = red flag) ---------------------------------------
#     Anomaly: Sloan accruals — high accruals (earnings not backed by cash)
#     predict lower future returns. We express it as OCF/NI (LOW = red flag).
EARNINGS_QUALITY_FACTORS: list[str] = [
    "accruals_ocf_ni",   # operating cash flow / net income (LOW = red flag)
]

# --- Short activity (high / rising = red flag) --------------------------------
#     Anomaly: informed shorting FLOW. Boehmer Jones Zhang (2008) show heavily
#     shorted names underperform; Diether Lee Werner (2009) document daily
#     shorting activity predicting weak returns. Built from FINRA Reg SHO
#     daily short sale volume (see the FINRA note in the data fetch section) —
#     flow, deliberately NOT presented as short interest positions. History
#     begins ~2018-10; earlier cross sections carry NaN and the family simply
#     drops out of those composites under the coverage floors.
SHORT_ACTIVITY_FACTORS: list[str] = [
    "short_vol_ratio",   # trailing 3m mean daily short volume share (HIGH = red flag)
    "short_vol_chg",     # 3m change in that share                  (RISING = red flag)
]

# --- Insider activity (net selling = red flag) --------------------------------
#     Anomaly: insider purchases predict returns, strongest in small caps
#     (Lakonishok Lee 2001; Cohen Malloy Pomorski 2012 sharpen it by separating
#     routine from opportunistic trades — a refinement not yet attempted here).
#     Built from the SEC's quarterly insider transactions data sets (Form 4,
#     open market P/S codes only, 10b5-1 plan flagged rows excluded, keyed by
#     CIK, stamped by FILING date). The data sets post a week or two after each
#     quarter ends, so the newest cross sections can miss up to ~3 months of
#     the trailing window right after a quarter turn — disclosed in the
#     Methodology tab.
INSIDER_ACTIVITY_FACTORS: list[str] = [
    "insider_npr_6m",    # net purchase ratio (B−S)/(B+S), trailing 6m (LOW = red flag)
]

# --- Earnings surprise, price based (weak reaction = red flag) -----------------
#     Anomaly: post earnings announcement drift (Bernard Thomas 1989). Without
#     estimates data the market's own verdict is the surprise proxy: the
#     benchmark adjusted return around the earnings 8-K (item 2.02), which
#     then drifts. Event dates from EDGAR submissions (acceptance time decides
#     whether the reaction day is the filing day or the next session).
EARNINGS_SURPRISE_FACTORS: list[str] = [
    "earn_react_1q",     # abnormal return around the latest earnings event (LOW = red flag)
]

# --- OPTIONAL estimate factors (gated; never faked from yfinance) ------------
#     Analyst estimate revisions / SUE. yfinance cannot supply these reliably,
#     so they are OFF by default and only populated by the FactSet / S&P Global
#     loader (see USE_ESTIMATE_FACTORS below). If enabled but the loader returns
#     nothing, these are dropped from the cross section — never median faked.
ESTIMATE_FACTORS: list[str] = [
    "est_revision_3m",   # 3m fwd EPS estimate revision (DOWN = red flag)
    "sue",               # standardized unexpected earnings (LOW = red flag)
]

# Master factor list actually used = the always on factors, plus estimate
# factors iff USE_ESTIMATE_FACTORS. Keep this assembled in one place.
BASE_FACTORS: list[str] = (
    VALUATION_FACTORS
    + MOMENTUM_FACTORS
    + VOLATILITY_FACTORS
    + QUALITY_FACTORS
    + INVESTMENT_FACTORS
    + EARNINGS_QUALITY_FACTORS
    + SHORT_ACTIVITY_FACTORS
    + INSIDER_ACTIVITY_FACTORS
    + EARNINGS_SURPRISE_FACTORS
)

# Red flag direction for EVERY factor. +1: high raw value = more sell risk.
RED_FLAG_DIRECTION: dict[str, int] = {
    # valuation — rich is the red flag
    "pe_ratio": +1,
    "ev_to_ebitda": +1,
    "ps_ratio": +1,
    "fcf_yield": -1,
    # momentum
    "mom_12_1": -1,        # low momentum (loser) is the red flag
    "reversal_1m": +1,     # high last month return reverses -> red flag
    "high_52w": -1,        # far below the 52w high is the red flag
    # volatility / lottery
    "ivol_63d": +1,
    "max_ret_1m": +1,
    "beta_252d": +1,
    # quality
    "roe": -1,
    "roa": -1,
    "gross_margin": -1,
    "fcf_margin": -1,
    "roe_yoy": -1,
    "gross_margin_yoy": -1,
    # investment / growth
    "asset_growth_yoy": +1,
    "net_issuance_yoy": +1,
    # earnings quality
    "accruals_ocf_ni": -1,
    # short activity
    "short_vol_ratio": +1,
    "short_vol_chg": +1,
    # insider activity: net BUYING is bullish, so low/negative NPR is the flag
    "insider_npr_6m": -1,
    # earnings surprise: a strong positive reaction drifts UP (less sell risk)
    "earn_react_1q": -1,
    # estimates (optional)
    "est_revision_3m": -1,
    "sue": -1,
}

# Group membership: drives BOTH the Factor IC webapp tab AND the family
# balanced composite (model.equal_weight_score averages within family first,
# then across families, so four collinear valuation ratios carry one family
# vote, not four).
FACTOR_GROUPS: dict[str, str] = {
    **{f: "Valuation" for f in VALUATION_FACTORS},
    **{f: "Momentum" for f in MOMENTUM_FACTORS},
    **{f: "Volatility" for f in VOLATILITY_FACTORS},
    **{f: "Quality" for f in QUALITY_FACTORS},
    **{f: "Investment" for f in INVESTMENT_FACTORS},
    **{f: "Earnings Quality" for f in EARNINGS_QUALITY_FACTORS},
    **{f: "Short Activity" for f in SHORT_ACTIVITY_FACTORS},
    **{f: "Insider Activity" for f in INSIDER_ACTIVITY_FACTORS},
    **{f: "Earnings Surprise" for f in EARNINGS_SURPRISE_FACTORS},
    **{f: "Estimates" for f in ESTIMATE_FACTORS},
}

def active_factors() -> list[str]:
    """Factors actually fed to the model given the estimate source gate."""
    return list(BASE_FACTORS) + (ESTIMATE_FACTORS if USE_ESTIMATE_FACTORS else [])

# =============================================================================
# Neutralization + scoring
# =============================================================================
# How each factor is made sector neutral at each cross section:
#   "zscore" -> (x - sector_mean) / sector_std         (default; symmetric)
#   "rank"   -> within sector percentile rank in [0, 1] (robust to outliers)
NEUTRALIZE_METHOD: str = "zscore"
WINSORIZE_PCT: float = 0.02   # clip each factor at 2/98th pct before neutralizing
N_DECILES: int = 10           # sector neutral decile buckets (10 = worst, 1 = best)

# Family balanced composite: average factors WITHIN each family first, then
# average the family scores ("equal weight by information", not by factor
# count), re-standardize the composite within each peer group so a name scored
# on 2 families and a name scored on 6 are comparable, and refuse to score a
# name on too thin a base at all.
MIN_FACTORS_FOR_SCORE: int = 3   # a name needs >= this many populated factors
MIN_FAMILIES_FOR_SCORE: int = 2  # ...spread over >= this many families

# =============================================================================
# Model selection
# =============================================================================
# The learned weight model is now fitted on EVERY run (the 183 quarter EDGAR
# history showed the factor families carry OPPOSITE signs — valuation flags
# work, quality/accruals flags inverted — which an equal weight sum cancels
# out and a walk forward fit can learn). The baseline is still always computed
# and reported side by side; validate.paired_ic_test still decides the default.
USE_LEARNED_WEIGHTS: bool = True
LEARNED_MODEL: str = "ridge"          # "ridge" | "logistic" | "gbm"
WALK_FORWARD_MIN_TRAIN_PERIODS: int = 6   # cross sections before first OOS fit
RIDGE_ALPHA: float = 10.0

# Roadmap 1.6: walk forward IC weighted family blending — the transparent
# middle ground between equal family weights and the ridge. Family weights at
# each date are proportional to the family's TRAILING mean IC (negative
# trailing ICs clip to zero: a broken family is silenced, never inverted —
# inversion capture is deliberately left to the learned model), shrunk hard
# toward equal weight (James Stein intuition: family IC estimates are noisy,
# so only half the weight follows the evidence). STRICTLY point in time: the
# IC of cross section s enters the trailing window only once its forward
# label has fully realized (s + 3 x horizon months <= t), a stricter embargo
# than the learned model applies. These values are pre registered here, not
# tuned: changing them after seeing results is data snooping and must be
# disclosed like the promotion bar was.
ICW_TRAILING_WINDOW: int = 36    # realized IC observations per family (3y monthly)
ICW_SHRINKAGE: float = 0.5       # 0 = pure equal weight, 1 = pure IC proportional
ICW_MIN_REALIZED: int = 12       # realized ICs required before leaving equal weight

# =============================================================================
# Torpedo screener (integrated absolute risk view)
# =============================================================================
# The torpedo screener answers a DIFFERENT question than the sell model. It
# ranks each name against the WHOLE universe (not within its sector) and targets
# ABSOLUTE blow up / drawdown risk, not sector relative underperformance. It is
# integrated here purely as a contrast lens: a name can look risky on one view
# and calm on the other, and the platform shows both side by side.
#
# Implementation: winsorize each risk feature, z score it across the whole
# universe at each date (NOT within sector), align every feature so higher means
# more risk, average the available features into a composite, then convert the
# composite to a 0 to 100 universe percentile and a coarse tier.
TORPEDO_FEATURES: list[str] = [
    "pe_ratio", "ev_to_ebitda", "ps_ratio", "fcf_yield",
    "mom_12_1", "reversal_1m", "high_52w",
    "ivol_63d", "max_ret_1m", "beta_252d",
    "amihud_63d",        # torpedo ONLY: illiquidity = exit / blow up risk. As a
                         # RETURN predictor Amihud points the other way (the
                         # illiquidity premium), so it is deliberately kept out
                         # of the sell model's return ranking.
    "roe", "roa", "gross_margin", "fcf_margin", "roe_yoy", "gross_margin_yoy",
    "asset_growth_yoy", "net_issuance_yoy", "accruals_ocf_ni",
    "short_vol_ratio",   # crowded shorting flags blow up / squeeze risk. Replaces
                         # short_pct_float here: that yfinance field is a TODAY
                         # ONLY snapshot that was being broadcast to every
                         # historical date (a quiet look ahead); the FINRA flow
                         # ratio is a true per date value. short_pct_float stays
                         # in the panel as drill down metadata.
]

# +1: a higher raw value means MORE absolute risk; -1: means LESS.
TORPEDO_RISK_DIRECTION: dict[str, int] = {
    "pe_ratio": +1, "ev_to_ebitda": +1, "ps_ratio": +1, "fcf_yield": -1,
    "mom_12_1": -1, "reversal_1m": +1, "high_52w": -1,
    "ivol_63d": +1, "max_ret_1m": +1, "beta_252d": +1, "amihud_63d": +1,
    "roe": -1, "roa": -1, "gross_margin": -1, "fcf_margin": -1,
    "roe_yoy": -1, "gross_margin_yoy": -1,
    "asset_growth_yoy": +1, "net_issuance_yoy": +1,
    "accruals_ocf_ni": -1,
    "short_vol_ratio": +1,
    "short_pct_float": +1,   # metadata only since the FINRA swap; kept for safety
}

# Universe percentile buckets for the torpedo tier label.
TORPEDO_TIERS: list[tuple[float, float, str]] = [
    (0.0, 30.0, "Stable"),
    (30.0, 70.0, "Mainstream"),
    (70.0, 100.01, "Elevated"),
]
TORPEDO_TIER_COLORS: dict[str, str] = {
    "Stable": "#2c7a4b", "Mainstream": "#c98a00", "Elevated": "#b3001b",
}

# =============================================================================
# Fundamentals source / optional estimate factors
# =============================================================================
# Default fundamentals source is now SEC EDGAR XBRL companyfacts: free,
# official, ~2009+ quarterly history, and every value is stamped with its
# actual FILING date (true point in time knowledge). NO API KEY IS NEEDED —
# the SEC only requires an identifying User-Agent, which reuses USER_AGENT
# below. yfinance remains the per ticker fallback when a CIK is missing.
# WRDS (CRSP / Compustat / IBES through the university) is a separate,
# research only channel; when its connector is built, credentials will live in
# .env as WRDS_USERNAME / WRDS_PASSWORD (see .env.example) — never in code.
USE_ESTIMATE_FACTORS: bool = False
DEEP_HISTORY_SOURCE: str = os.getenv("RSM_SOURCE", "edgar")  # "edgar"|"yfinance"|"factset"|"spglobal"
SPGLOBAL_API_KEY: str | None = os.getenv("SPGLOBAL_API_KEY") or None
FACTSET_API_KEY: str | None = os.getenv("FACTSET_API_KEY") or None
WRDS_USERNAME: str | None = os.getenv("WRDS_USERNAME") or None
WRDS_PASSWORD: str | None = os.getenv("WRDS_PASSWORD") or None

# =============================================================================
# Backtest / costs
# =============================================================================
COST_BPS: float = 10.0        # round trip transaction cost per unit turnover, bps
# A delisted name's forward total return floors here unless a recovery value is
# known. -1.0 = went to zero (the strongest possible underperformer).
DELISTING_TERMINAL_RETURN: float = -1.0

# =============================================================================
# Data integrity gate
# =============================================================================
# A single day price ratio beyond these bounds is treated as a series splice /
# corporate action artifact, not a real return. Canonical case: CHRD, where
# yfinance splices pre Chapter 11 Oasis Petroleum ($0.07) onto the post
# emergence equity ($19.93) in Nov 2020 — a fake +28,000% day. Splits are
# already adjusted (auto_adjust=True), so genuine moves this size are
# vanishingly rare among index members. Any forward return whose window spans
# a flagged day is EXCLUDED from labels and logged, never silently kept.
MAX_DAILY_PRICE_RATIO: float = 4.0    # > 4x up in a single day  -> splice suspect
MIN_DAILY_PRICE_RATIO: float = 0.25   # < 0.25x down in a single day -> splice suspect
# Backstop: a window return beyond this magnitude is excluded and logged
# (reason "extreme_return") even if the daily gate missed the cause. This is a
# DATA ERROR net, not tail truncation: real small cap moonshots reach ~25x over
# two quarters (MARA Sep-2020..Mar-2021 ~26x, GME ~19x, SM ~11x — all genuine
# and all kept), and deleting real right tail events would flatter the model by
# erasing its worst potential misses. Skew handling for DISPLAY belongs to the
# winsorized/median statistics, never to label exclusion.
MAX_ABS_FORWARD_RETURN: float = 50.0  # 50x per horizon window = corruption
# Winsorization applied to LABELS for DISPLAY statistics only (calibration and
# decile means). Rank statistics (IC) are winsorization invariant; backtests
# always use raw returns.
LABEL_WINSOR_PCT: float = 0.01

# =============================================================================
# Stress windows — named disaster scenarios the model must be judged inside
# =============================================================================
# A sell model that only works in calm tape is a different product from one
# that works through dislocations. Every named episode gets its own row of
# validation stats (IC, decile spread) so regime failure is visible instead of
# averaged away. COVID gets two rows on purpose: the crash and the junk rally
# that followed are OPPOSITE regimes for a red flag model.
STRESS_WINDOWS: list[tuple[str, str, str]] = [
    ("US downgrade / EU crisis",   "2011-07-01", "2011-12-31"),
    ("Industrial recession 15/16", "2015-06-01", "2016-02-29"),
    ("Q4 2018 rate scare",         "2018-10-01", "2018-12-31"),
    ("COVID crash",                "2020-02-01", "2020-03-31"),
    ("COVID junk rally",           "2020-04-01", "2021-02-28"),
    ("2022 rate shock",            "2022-01-01", "2022-09-30"),
]

# =============================================================================
# Coverage eras
# =============================================================================
# yfinance fundamentals reach back only ~4-5 quarters, so historical cross
# sections are scored by the price factors alone. Cross sections whose average
# factor coverage is below this threshold are labeled the "price-only era" and
# every validation stat is reported per era, so a 2 factor history is never
# passed off as evidence about the 15 factor composite.
ERA_MIN_AVG_FACTORS: float = 4.0

# =============================================================================
# IMA Monte Carlo simulation (replaces the long/short sleeve)
# =============================================================================
# IMA holds ~20 names picked from the S&P 600 (kept if they graduate to the
# 400). The simulator draws many random 20 name portfolios from the universe
# with and without the sell screen applied and compares the DISTRIBUTIONS —
# the honest way to measure what the screen does for a concentrated picker,
# since any single 20 name path is dominated by luck.
MC_PORTFOLIO_SIZE: int = 20
MC_N_TRIALS: int = 1000
MC_SEED: int = 42

# Learned model promotion: the learned scorer becomes the default only if its
# per date IC beats the baseline's by a PAIRED Newey West t stat of at least
# this. The bar is ONE SIDED at 5% (t >= 1.645): the hypothesis is directional
# and pre registered (learned > baseline, walk forward out of sample), so a
# two sided 2.0 bar double charges for a tail we never claim. HONESTY NOTE:
# this bar was relaxed from 2.0 AFTER observing a paired t of 1.88 on the
# 2011-2026 EDGAR history — a judgment call by the PM (Amar, 2026-07-13),
# documented here and in the methodology tab rather than hidden. The paired
# test, the side by side comparison, and this note ship with every run.
PROMOTION_MIN_T: float = 1.645

# =============================================================================
# Data fetch / cache knobs
# =============================================================================
# Price history reaches back to 2010: with the monthly grid that is ~200
# cross sections. The membership caveat gets LOUDER the further back this
# goes (a current only snapshot in 2010 is heavily survivorship biased) —
# the era split and the header warning carry that message.
PRICE_HISTORY_START: str = "2010-01-01"
PRICE_HISTORY_YEARS: int = 17  # legacy knob; kept as ceiling for benchmark fetch
BATCH_SIZE: int = 40
BATCH_DELAY_SECONDS: float = 2.0
CACHE_MAX_AGE_SECONDS: int = 24 * 60 * 60
MIN_TRADING_DAYS: int = 252     # a ticker needs >=1y of prices to be scored

# SEC EDGAR (no key — identify yourself via USER_AGENT and respect ~10 req/s)
EDGAR_TICKER_CIK_URL: str = "https://www.sec.gov/files/company_tickers.json"
EDGAR_COMPANYFACTS_URL: str = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
EDGAR_REQUESTS_PER_SEC: float = 8.0
EDGAR_CACHE: Path | None = None  # set below after DATA_DIR exists

# FINRA short data (roadmap 2.3 — premise corrected 2026-07-13). The bi
# monthly short interest POSITION files FINRA publishes for free cover OTC
# equities only and keep one rolling year online, so they cannot serve an
# S&P 600 history (verified live against api.finra.org: listed names absent).
# What IS free for exchange listed names is the daily consolidated short sale
# VOLUME file (ShortVolume / TotalVolume per symbol, off exchange trades
# reported to FINRA facilities), available from ~2018-10 on the CDN. The
# model therefore carries short ACTIVITY (flow) factors, named accordingly —
# informed shorting is a flow result in the literature anyway (Boehmer Jones
# Zhang 2008; Diether Lee Werner 2009). True position history (level, days to
# cover) arrives via Compustat's short interest file when WRDS access lands.
# FINRA class share symbols use slashes (MOG/A == our MOG-A).
FINRA_SHORT_VOLUME_DAILY_URL: str = (
    "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{date:%Y%m%d}.txt")
FINRA_SHORT_VOLUME_START: str = "2018-10-01"

# SEC insider transactions data sets (roadmap 2.4) — quarterly zips of every
# Form 3/4/5, structured TSVs, back to 2006. History starts two quarters
# before the price grid so the trailing 6 month window is populated at the
# first cross section. See insider_loader.py for the freshness limitation.
INSIDER_HISTORY_START: str = "2009-07-01"

# EDGAR submissions index (roadmap 2.5) — per company filing lists with items
# and acceptance timestamps; the earnings event dates come from 8-K item 2.02.
EDGAR_SUBMISSIONS_URL: str = "https://data.sec.gov/submissions/{name}"

SP600_WIKI_URL: str = "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies"
# S&P 400 (MidCap) is unioned into the universe so names that graduated out of the
# 600 up into the 400 are still scored and still match in the portfolio overlay.
SP400_WIKI_URL: str = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
USER_AGENT: str = (
    "Relative Sell Model/1.0 (Student equity research; contact: dani@navaslabs.com)"
)

# =============================================================================
# Paths
# =============================================================================
PROJECT_ROOT: Path = Path(__file__).resolve().parent
DATA_DIR: Path = PROJECT_ROOT / "data"
OUTPUT_DIR: Path = PROJECT_ROOT / "output"
WEBAPP_PUBLIC: Path = PROJECT_ROOT / "webapp" / "public"
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Membership store (point in time) + current fallback
SP600_MEMBERSHIP_CSV: Path = DATA_DIR / "sp600_membership.csv"
SP600_FALLBACK_CSV: Path = DATA_DIR / "sp600_fallback.csv"

# Analyst override log (append only; see docs/override-layer-design.md).
# Overrides are ANNOTATIONS — they never touch the score — and are scored
# quarterly against realized relative returns.
OVERRIDES_CSV: Path = DATA_DIR / "overrides.csv"
OVERRIDE_MAX_AGE_QUARTERS: int = 2   # default expiry horizon if none supplied

# Caches
PRICE_CACHE: Path = DATA_DIR / "price_cache.parquet"
FINRA_SHORT_VOLUME_CACHE: Path = DATA_DIR / "finra_short_volume.parquet"
INSIDER_CACHE: Path = DATA_DIR / "insider_transactions.parquet"
INSIDER_QUARTERS_JSON: Path = DATA_DIR / "insider_quarters.json"
EARNINGS_EVENTS_CACHE: Path = DATA_DIR / "edgar_earnings_events.parquet"
VOLUME_CACHE: Path = DATA_DIR / "volume_cache.parquet"
BENCHMARK_CACHE: Path = DATA_DIR / "benchmark_cache.parquet"
FUNDAMENTALS_CACHE: Path = DATA_DIR / "fundamentals_cache.parquet"
SHORT_INTEREST_CACHE: Path = DATA_DIR / "short_interest_cache.parquet"
PANEL_CACHE: Path = DATA_DIR / "panel_cache.parquet"
EDGAR_CACHE = DATA_DIR / "edgar_fundamentals.parquet"
EDGAR_CIK_CACHE: Path = DATA_DIR / "edgar_cik_map.json"
