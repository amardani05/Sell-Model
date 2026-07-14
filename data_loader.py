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

* **Short interest** — short % of float. yfinance ``.info`` snapshot (current
  only), carried as panel METADATA for the drill down. The scored, historical
  short signal lives in ``finra_loader.py`` (Reg SHO daily short sale VOLUME
  flow — free position history for listed names does not exist; see the FINRA
  note in config.py).

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
def _extract_field(raw: pd.DataFrame, tickers: list[str], field: str) -> pd.DataFrame:
    """Normalize one field ("Close" / "Volume") out of yfinance output."""
    if raw is None or raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        if field in raw.columns.get_level_values(0):
            out = raw.xs(field, axis=1, level=0)
        elif field in raw.columns.get_level_values(-1):
            out = raw.xs(field, axis=1, level=-1)
        else:
            out = raw[field] if field in raw.columns else pd.DataFrame()
    else:
        if field in raw.columns:
            out = raw[[field]].copy()
            if len(tickers) == 1:
                out.columns = [tickers[0]]
        else:
            out = raw.copy() if field == "Close" else pd.DataFrame()
    return out.dropna(axis=1, how="all")


def _download_batch(tickers: list[str], start: str, end: str,
                    max_retries: int = 2) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One yfinance batch -> (adjusted close, volume)."""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            raw = yf.download(
                tickers=tickers, start=start, end=end, progress=False,
                auto_adjust=True, multi_level_index=False, ignore_tz=True, threads=True,
            )
            return _extract_field(raw, tickers, "Close"), _extract_field(raw, tickers, "Volume")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("yfinance batch attempt %d failed: %s", attempt + 1, exc)
            time.sleep(2 + attempt * 2)
    logger.error("yfinance batch failed after retries: %s", last_exc)
    return pd.DataFrame(), pd.DataFrame()


def download_prices(
    tickers: list[str],
    years: int = config.PRICE_HISTORY_YEARS,
    force_refresh: bool = False,
    cache_path: Path = config.PRICE_CACHE,
    start: str | None = None,
) -> pd.DataFrame:
    """Wide daily adjusted close matrix (index = date, columns = ticker).

    Delisting aware: columns that terminate early are kept. Cached to
    ``cache_path`` (the benchmark download passes its own path so a single
    ticker fetch never clobbers the universe price cache). The main universe
    fetch starts at ``config.PRICE_HISTORY_START`` (2010) and also writes the
    daily VOLUME matrix to ``config.VOLUME_CACHE`` (Amihud illiquidity input).
    """
    is_universe_cache = cache_path == config.PRICE_CACHE
    if not force_refresh and _cache_is_fresh(cache_path):
        logger.info("Loading cached prices from %s", cache_path)
        return pd.read_parquet(cache_path)

    end_dt = datetime.utcnow().date()
    if start is None:
        start = (config.PRICE_HISTORY_START if is_universe_cache
                 else (end_dt - timedelta(days=int(years * 365.25) + 10)).isoformat())
    end = end_dt.isoformat()
    tickers = sorted({t.upper() for t in tickers})
    logger.info("Downloading %d tickers of prices+volume, %s..%s", len(tickers), start, end)

    px_frames: list[pd.DataFrame] = []
    vol_frames: list[pd.DataFrame] = []
    n_batches = (len(tickers) + config.BATCH_SIZE - 1) // config.BATCH_SIZE
    for i in range(0, len(tickers), config.BATCH_SIZE):
        batch = tickers[i : i + config.BATCH_SIZE]
        logger.info("  prices batch %d/%d (%d tickers)", i // config.BATCH_SIZE + 1, n_batches, len(batch))
        close, vol = _download_batch(batch, start, end)
        if not close.empty:
            px_frames.append(close)
        if not vol.empty:
            vol_frames.append(vol)
        if i + config.BATCH_SIZE < len(tickers):
            time.sleep(config.BATCH_DELAY_SECONDS)

    if not px_frames:
        raise RuntimeError("yfinance returned no price data for any batch")

    prices = pd.concat(px_frames, axis=1)
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

    if is_universe_cache and vol_frames:
        volumes = pd.concat(vol_frames, axis=1)
        volumes = volumes.loc[:, ~volumes.columns.duplicated()].sort_index()
        volumes = volumes[[c for c in volumes.columns if c in prices.columns]]
        volumes.to_parquet(config.VOLUME_CACHE)
        logger.info("Volumes: cached %d tickers to %s", volumes.shape[1], config.VOLUME_CACHE)
    return prices


def load_volumes() -> pd.DataFrame | None:
    """Cached daily volume matrix, if the last price download produced one."""
    if config.VOLUME_CACHE.exists():
        try:
            return pd.read_parquet(config.VOLUME_CACHE)
        except Exception as exc:  # noqa: BLE001
            logger.warning("volume cache unreadable: %s", exc)
    return None


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

    METADATA ONLY (drill down display): a today only value must never feed a
    historical statistic — the torpedo screener used to broadcast it to every
    date and now uses the FINRA short volume ratio instead (finra_loader.py).
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
