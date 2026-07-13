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

# Minimum names a sector must have on a given date to be ranked sector neutrally.
# Below this, cross sectional ranks are meaningless; the names are dropped from
# that cross section (and logged).
MIN_NAMES_PER_SECTOR: int = 5

# =============================================================================
# Forward horizon + rebalance
# =============================================================================
# Horizons (in quarters) at which forward RELATIVE returns are measured.
HORIZONS_Q: tuple[int, ...] = (1, 2)
DEFAULT_HORIZON_Q: int = 1
REBALANCE_FREQ: str = "Q"          # quarterly rebalance for the backtest
TRADING_DAYS_PER_QUARTER: int = 63

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
#     Anomaly: Jegadeesh Titman 12 1 momentum (losers keep losing) + the
#     short term (1 month) reversal effect, kept as a SEPARATE factor.
MOMENTUM_FACTORS: list[str] = [
    "mom_12_1",        # 12m minus 1m total return (LOW = loser = red flag)
    "reversal_1m",     # last 1m return            (HIGH = reverses down = red flag)
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
    + QUALITY_FACTORS
    + INVESTMENT_FACTORS
    + EARNINGS_QUALITY_FACTORS
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
    # estimates (optional)
    "est_revision_3m": -1,
    "sue": -1,
}

# Group membership for the Factor IC webapp tab.
FACTOR_GROUPS: dict[str, str] = {
    **{f: "Valuation" for f in VALUATION_FACTORS},
    **{f: "Momentum" for f in MOMENTUM_FACTORS},
    **{f: "Quality" for f in QUALITY_FACTORS},
    **{f: "Investment" for f in INVESTMENT_FACTORS},
    **{f: "Earnings Quality" for f in EARNINGS_QUALITY_FACTORS},
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

# =============================================================================
# Model selection
# =============================================================================
# Baseline is ALWAYS the equal weight composite (Piper style). The learned weight
# model is OPTIONAL and only ever becomes the *default scorer* if it beats the
# baseline out of sample (validate.py decides; main.py reports both either way).
USE_LEARNED_WEIGHTS: bool = False
LEARNED_MODEL: str = "ridge"          # "ridge" | "logistic" | "gbm"
WALK_FORWARD_MIN_TRAIN_PERIODS: int = 6   # cross sections before first OOS fit
RIDGE_ALPHA: float = 10.0

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
    "mom_12_1", "reversal_1m",
    "roe", "roa", "gross_margin", "fcf_margin", "roe_yoy", "gross_margin_yoy",
    "asset_growth_yoy", "net_issuance_yoy", "accruals_ocf_ni",
    "short_pct_float",   # torpedo specific: crowded shorts flag blow up risk
]

# +1: a higher raw value means MORE absolute risk; -1: means LESS.
TORPEDO_RISK_DIRECTION: dict[str, int] = {
    "pe_ratio": +1, "ev_to_ebitda": +1, "ps_ratio": +1, "fcf_yield": -1,
    "mom_12_1": -1, "reversal_1m": +1,
    "roe": -1, "roa": -1, "gross_margin": -1, "fcf_margin": -1,
    "roe_yoy": -1, "gross_margin_yoy": -1,
    "asset_growth_yoy": +1, "net_issuance_yoy": +1,
    "accruals_ocf_ni": -1,
    "short_pct_float": +1,
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
# Optional estimate revision / deep history source (gated behind .env)
# =============================================================================
# OFF by default. yfinance CANNOT supply estimate revisions / SUE or deep
# point in time fundamentals; turning this on requires a real connector.
USE_ESTIMATE_FACTORS: bool = False
DEEP_HISTORY_SOURCE: str = os.getenv("RSM_SOURCE", "yfinance")  # "yfinance"|"factset"|"spglobal"
SPGLOBAL_API_KEY: str | None = os.getenv("SPGLOBAL_API_KEY") or None
FACTSET_API_KEY: str | None = os.getenv("FACTSET_API_KEY") or None

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
# this (a point estimate edge of +0.001 is noise, not a win).
PROMOTION_MIN_T: float = 2.0

# =============================================================================
# Data fetch / cache knobs
# =============================================================================
PRICE_HISTORY_YEARS: int = 8   # deep price history -> many quarterly cross sections
BATCH_SIZE: int = 40
BATCH_DELAY_SECONDS: float = 2.0
CACHE_MAX_AGE_SECONDS: int = 24 * 60 * 60
MIN_TRADING_DAYS: int = 252     # a ticker needs >=1y of prices to be scored

# FINRA bi monthly short interest (equity short interest) — public flat files.
FINRA_SHORT_INTEREST_URL: str = (
    "https://cdn.finra.org/equity/regsho/monthly/"  # consolidated short interest dir
)

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
BENCHMARK_CACHE: Path = DATA_DIR / "benchmark_cache.parquet"
FUNDAMENTALS_CACHE: Path = DATA_DIR / "fundamentals_cache.parquet"
SHORT_INTEREST_CACHE: Path = DATA_DIR / "short_interest_cache.parquet"
PANEL_CACHE: Path = DATA_DIR / "panel_cache.parquet"
