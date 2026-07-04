"""Download and cache prices, fundamentals, and short interest.

Three sources, all cached as parquet:

* **Prices** — yfinance adjusted close, DEEP history (``PRICE_HISTORY_YEARS``).
  Deep history is what lets the price based factors (momentum, reversal) be
  measured at many quarterly cross sections; the fundamental factors are
  shallower (see below). Delisting aware: a ticker whose series terminates
  early is **kept**, not dropped — the empty tail is the delisting signal that
  ``feature_engine`` carries to a terminal return.

* **Fundamentals** — yfinance quarterly financials / balance sheet / cash flow
  + ``.info``. yfinance only returns ~4 5 quarters, so the fundamental factors
  populate only the most RECENT cross sections. This is the documented depth
  limit; the FactSet / S&P Global loader (``deep_loader.py``) is the upgrade.

* **Short interest** — short % of float. Baseline is the yfinance ``.info``
  snapshot (current only). FINRA's bi monthly consolidated short interest flat
  files (``config.FINRA_SHORT_INTEREST_URL``) are the historical upgrade. Short
  interest is carried as panel METADATA, not a scored factor (it is not in the
  documented factor taxonomy), but it is available for inspection.

Per ticker errors are swallowed and logged; one bad ticker never breaks a batch.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

import config

logger = logging.getLogger(__name__)


def _cache_is_fresh(path: Path, max_age: int = config.CACHE_MAX_AGE_SECONDS) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < max_age


# =============================================================================
# Prices
# =============================================================================
def _extract_close(raw: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Normalize yfinance output into a flat adjusted close DataFrame."""
    if raw is None or raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        if "Close" in raw.columns.get_level_values(0):
            close = raw.xs("Close", axis=1, level=0)
        elif "Close" in raw.columns.get_level_values(-1):
            close = raw.xs("Close", axis=1, level=-1)
        else:
            close = raw["Close"] if "Close" in raw.columns else pd.DataFrame()
    else:
        if "Close" in raw.columns:
            close = raw[["Close"]].copy()
            if len(tickers) == 1:
                close.columns = [tickers[0]]
        else:
            close = raw.copy()
    return close.dropna(axis=1, how="all")


def _download_batch(tickers: list[str], start: str, end: str, max_retries: int = 2) -> pd.DataFrame:
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            raw = yf.download(
                tickers=tickers, start=start, end=end, progress=False,
                auto_adjust=True, multi_level_index=False, ignore_tz=True, threads=True,
            )
            return _extract_close(raw, tickers)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("yfinance batch attempt %d failed: %s", attempt + 1, exc)
            time.sleep(2 + attempt * 2)
    logger.error("yfinance batch failed after retries: %s", last_exc)
    return pd.DataFrame()


def download_prices(
    tickers: list[str],
    years: int = config.PRICE_HISTORY_YEARS,
    force_refresh: bool = False,
    cache_path: Path = config.PRICE_CACHE,
) -> pd.DataFrame:
    """Wide daily adjusted close matrix (index = date, columns = ticker).

    Delisting aware: columns that terminate early are kept. Cached to
    ``cache_path`` (the benchmark download passes its own path so a single
    ticker fetch never clobbers the universe price cache).
    """
    if not force_refresh and _cache_is_fresh(cache_path):
        logger.info("Loading cached prices from %s", cache_path)
        return pd.read_parquet(cache_path)

    end_dt = datetime.utcnow().date()
    start_dt = end_dt - timedelta(days=int(years * 365.25) + 10)
    start, end = start_dt.isoformat(), end_dt.isoformat()
    tickers = sorted({t.upper() for t in tickers})
    logger.info("Downloading %d tickers of prices, %s..%s", len(tickers), start, end)

    frames: list[pd.DataFrame] = []
    n_batches = (len(tickers) + config.BATCH_SIZE - 1) // config.BATCH_SIZE
    for i in range(0, len(tickers), config.BATCH_SIZE):
        batch = tickers[i : i + config.BATCH_SIZE]
        logger.info("  prices batch %d/%d (%d tickers)", i // config.BATCH_SIZE + 1, n_batches, len(batch))
        close = _download_batch(batch, start, end)
        if not close.empty:
            frames.append(close)
        if i + config.BATCH_SIZE < len(tickers):
            time.sleep(config.BATCH_DELAY_SECONDS)

    if not frames:
        raise RuntimeError("yfinance returned no price data for any batch")

    prices = pd.concat(frames, axis=1)
    prices = prices.loc[:, ~prices.columns.duplicated()].sort_index()
    # Keep names with at least MIN_TRADING_DAYS of data ANYWHERE in the window
    # (delisting aware: a name alive for 2y then gone still qualifies).
    keep = prices.notna().sum(axis=0)
    keep = keep[keep >= config.MIN_TRADING_DAYS].index
    dropped = prices.shape[1] - len(keep)
    prices = prices[keep]
    logger.info("Prices: kept %d tickers (dropped %d for < %d obs)",
                prices.shape[1], dropped, config.MIN_TRADING_DAYS)
    prices.to_parquet(cache_path)
    return prices


def download_benchmark(ticker: str = config.BENCHMARK_TICKER,
                       years: int = config.PRICE_HISTORY_YEARS,
                       force_refresh: bool = False) -> pd.Series:
    """Daily adjusted close for the benchmark ETF (for the long only backtest).

    Caches to BENCHMARK_CACHE only; never touches the universe PRICE_CACHE.
    """
    if not force_refresh and _cache_is_fresh(config.BENCHMARK_CACHE):
        s = pd.read_parquet(config.BENCHMARK_CACHE)
        return s[ticker] if ticker in s.columns else s.iloc[:, 0]
    px = download_prices([ticker], years=years, force_refresh=True,
                         cache_path=config.BENCHMARK_CACHE)
    return px[ticker] if ticker in px.columns else px.iloc[:, 0]


# =============================================================================
# Fundamentals (yfinance) — shallow but real
# =============================================================================
@dataclass
class RawBundle:
    ticker: str
    info: dict = field(default_factory=dict)
    quarterly_financials: pd.DataFrame | None = None
    quarterly_balance_sheet: pd.DataFrame | None = None
    quarterly_cashflow: pd.DataFrame | None = None


def _df_to_json(df: pd.DataFrame | None) -> str:
    if df is None or df.empty:
        return "{}"
    out = df.copy()
    out.columns = [pd.Timestamp(c).isoformat() if not isinstance(c, str) else c for c in out.columns]
    return out.to_json(orient="split", date_format="iso")


def _json_to_df(s: str | None) -> pd.DataFrame | None:
    if not s or s == "{}":
        return None
    try:
        return pd.read_json(StringIO(s), orient="split")
    except Exception:  # noqa: BLE001
        return None


def _fetch_one_fundamental(ticker: str) -> RawBundle:
    bundle = RawBundle(ticker=ticker)
    try:
        tk = yf.Ticker(ticker)
        try:
            bundle.info = tk.info or {}
        except Exception as exc:  # noqa: BLE001
            logger.debug("%s: .info failed: %s", ticker, exc)
        bundle.quarterly_financials = tk.quarterly_financials
        bundle.quarterly_balance_sheet = tk.quarterly_balance_sheet
        bundle.quarterly_cashflow = tk.quarterly_cashflow
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: fundamental fetch failed: %s", ticker, exc)
    return bundle


def fetch_fundamentals(tickers: list[str], force_refresh: bool = False) -> dict[str, RawBundle]:
    """Per ticker quarterly fundamentals + info, cached as parquet.

    NOTE: yfinance returns only ~4 5 quarters, so YoY fundamental factors only
    populate for tickers with enough quarters. Missing -> NaN (dropped from the
    cross section by the model), never faked.
    """
    if not force_refresh and _cache_is_fresh(config.FUNDAMENTALS_CACHE):
        logger.info("Loading cached fundamentals from %s", config.FUNDAMENTALS_CACHE)
        cached = pd.read_parquet(config.FUNDAMENTALS_CACHE)
        bundles = {}
        for _, r in cached.iterrows():
            bundles[r["ticker"]] = RawBundle(
                ticker=r["ticker"],
                info=json.loads(r["info_json"]) if r["info_json"] else {},
                quarterly_financials=_json_to_df(r["financials_json"]),
                quarterly_balance_sheet=_json_to_df(r["balance_json"]),
                quarterly_cashflow=_json_to_df(r["cashflow_json"]),
            )
        return bundles

    tickers = sorted(set(tickers))
    logger.info("Fetching fundamentals for %d tickers (yfinance, ~4 5 quarters each)", len(tickers))
    bundles: dict[str, RawBundle] = {}
    rows = []
    for i, t in enumerate(tickers):
        if i and i % 25 == 0:
            logger.info("  fundamentals %d/%d", i, len(tickers))
            time.sleep(config.BATCH_DELAY_SECONDS)
        b = _fetch_one_fundamental(t)
        bundles[t] = b
        rows.append({
            "ticker": t,
            "info_json": json.dumps({k: v for k, v in (b.info or {}).items()
                                     if isinstance(v, (int, float, str, bool, type(None)))}),
            "financials_json": _df_to_json(b.quarterly_financials),
            "balance_json": _df_to_json(b.quarterly_balance_sheet),
            "cashflow_json": _df_to_json(b.quarterly_cashflow),
        })
    pd.DataFrame(rows).to_parquet(config.FUNDAMENTALS_CACHE)
    return bundles


# =============================================================================
# Short interest (metadata; FINRA upgrade documented)
# =============================================================================
def load_short_interest(bundles: dict[str, RawBundle]) -> pd.Series:
    """Current short % of float per ticker, from the yfinance info snapshot.

    Baseline only (current snapshot). The historical upgrade is the FINRA
    consolidated short interest flat files at ``config.FINRA_SHORT_INTEREST_URL``;
    wire those in for a point in time short interest factor.
    """
    out = {}
    for t, b in bundles.items():
        v = (b.info or {}).get("shortPercentOfFloat")
        out[t] = float(v) if isinstance(v, (int, float)) and v == v else np.nan
    return pd.Series(out, name="short_pct_float")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    px = download_prices(["AAPL", "MSFT", "IJR"], years=2, force_refresh=True)
    print(px.tail())
