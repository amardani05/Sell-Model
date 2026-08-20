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


class StalePriceData(RuntimeError):
    """Raised when the price matrix is too far behind today to publish."""


def _fetch_window(tickers: list[str], start: str, end: str, what: str = "prices") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Batched fetch of one date window for many tickers -> (close, volume)."""
    px_frames: list[pd.DataFrame] = []
    vol_frames: list[pd.DataFrame] = []
    n_batches = (len(tickers) + config.BATCH_SIZE - 1) // config.BATCH_SIZE
    for i in range(0, len(tickers), config.BATCH_SIZE):
        batch = tickers[i : i + config.BATCH_SIZE]
        logger.info("  %s batch %d/%d (%d tickers)", what,
                    i // config.BATCH_SIZE + 1, n_batches, len(batch))
        close, vol = _download_batch(batch, start, end)
        if not close.empty:
            px_frames.append(close)
        if not vol.empty:
            vol_frames.append(vol)
        if i + config.BATCH_SIZE < len(tickers):
            time.sleep(config.BATCH_DELAY_SECONDS)
    px = pd.concat(px_frames, axis=1) if px_frames else pd.DataFrame()
    vol = pd.concat(vol_frames, axis=1) if vol_frames else pd.DataFrame()
    if not px.empty:
        px = px.loc[:, ~px.columns.duplicated()].sort_index()
    if not vol.empty:
        vol = vol.loc[:, ~vol.columns.duplicated()].sort_index()
    return px, vol


def _reconcile_adjustments(old: pd.DataFrame, new: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Align a cached matrix to a freshly fetched overlapping window.

    yfinance serves SPLIT AND DIVIDEND ADJUSTED prices, so any corporate action
    retroactively rescales a ticker's entire history by a constant factor.
    Appending a fresh tail onto an unadjusted body would manufacture exactly the
    kind of overnight jump the splice gate exists to catch (this is the CHRD
    failure mode, self inflicted). For every ticker present in both matrices we
    compare the overlap:

      ratio ~ 1 (within tolerance)  -> nothing happened, keep history as is
      ratio constant but != 1       -> a corporate action; rescale the stored
                                       history by that constant
      ratio inconsistent            -> the series genuinely disagree; the
                                       ticker is returned for a full refetch

    Returns (possibly rescaled ``old``, tickers needing a full refetch).
    """
    tol = config.PRICE_ADJUSTMENT_TOLERANCE
    overlap = old.index.intersection(new.index)
    shared = [c for c in new.columns if c in old.columns]
    if len(overlap) == 0 or not shared:
        return old, []

    out = old.copy()
    rescaled: list[tuple[str, float]] = []
    refetch: list[str] = []
    for tk in shared:
        o = out.loc[overlap, tk]
        n = new.loc[overlap, tk]
        both = o.notna() & n.notna() & (o != 0)
        if both.sum() < 2:
            continue                      # too little overlap to judge; leave alone
        ratio = (n[both] / o[both]).astype(float)
        med = float(ratio.median())
        if not np.isfinite(med) or med <= 0:
            refetch.append(tk)
            continue
        spread = float((ratio.max() - ratio.min()) / med)
        if abs(med - 1.0) <= tol:
            continue                      # unchanged
        if spread <= tol:
            out[tk] = out[tk] * med       # clean corporate action rescale
            rescaled.append((tk, med))
        else:
            refetch.append(tk)

    if rescaled:
        logger.info("Price merge: rescaled %d tickers for corporate actions (%s)",
                    len(rescaled),
                    ", ".join(f"{t} x{r:.4f}" for t, r in sorted(rescaled)[:6])
                    + (" ..." if len(rescaled) > 6 else ""))
    if refetch:
        logger.warning("Price merge: %d tickers disagree with the cache beyond a constant "
                       "factor; refetching their full history (%s)",
                       len(refetch), ", ".join(sorted(refetch)[:8])
                       + (" ..." if len(refetch) > 8 else ""))
    return out, refetch


def _incremental_refresh(tickers: list[str], cache_path: Path, end: str) -> pd.DataFrame | None:
    """Top up the cached price/volume matrices with a short recent window.

    Returns the merged matrix, or None when the caller should fall back to a
    full download. Fetching ~2 weeks instead of ~16 years per ticker is roughly
    a 500x smaller request footprint, which is what stops the rate limiting
    that silently froze this cache for a month.
    """
    try:
        old_px = pd.read_parquet(cache_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("price cache unreadable (%s); full download", exc)
        return None
    if old_px.empty:
        return None
    old_vol = load_volumes()

    last = pd.Timestamp(old_px.index.max()).normalize()
    end_ts = pd.Timestamp(end)
    known = [t for t in tickers if t in old_px.columns]
    fresh_names = [t for t in tickers if t not in old_px.columns]
    if not known:
        return None

    start = (last - pd.Timedelta(days=config.PRICE_INCREMENTAL_OVERLAP_DAYS)).date().isoformat()
    logger.info("Incremental price refresh: cache ends %s, fetching %s..%s for %d known "
                "tickers (+%d new)", last.date(), start, end, len(known), len(fresh_names))
    new_px, new_vol = _fetch_window(known, start, end, what="recent prices")

    if new_px.empty:
        logger.error("PRICE REFRESH FAILED: no data returned for the recent window; "
                     "keeping the existing cache (check network / rate limiting)")
        return old_px
    covered = sum(1 for c in known if c in new_px.columns and new_px[c].notna().any())
    if covered < 0.5 * len(known):
        logger.error("PRICE REFRESH DEGRADED: only %d of %d known tickers returned data; "
                     "keeping the existing cache untouched (check network)", covered, len(known))
        return old_px

    merged_px, refetch = _reconcile_adjustments(old_px, new_px)
    merged_vol = old_vol.copy() if old_vol is not None else None

    if refetch:
        full_px, full_vol = _fetch_window(sorted(refetch), config.PRICE_HISTORY_START, end,
                                          what="full history refetch")
        for tk in full_px.columns:
            merged_px[tk] = full_px[tk]
        if merged_vol is not None and not full_vol.empty:
            for tk in full_vol.columns:
                merged_vol[tk] = full_vol[tk]

    # new rows win on the overlap, cached history fills everything before it
    merged_px = new_px.combine_first(merged_px).sort_index()
    if merged_vol is not None and not new_vol.empty:
        merged_vol = new_vol.combine_first(merged_vol).sort_index()

    if fresh_names:
        add_px, add_vol = _fetch_window(sorted(fresh_names), config.PRICE_HISTORY_START, end,
                                        what="new ticker history")
        if not add_px.empty:
            merged_px = merged_px.join(add_px[[c for c in add_px.columns
                                               if c not in merged_px.columns]], how="outer")
            logger.info("Incremental: added %d newly covered tickers", add_px.shape[1])
        if merged_vol is not None and not add_vol.empty:
            merged_vol = merged_vol.join(add_vol[[c for c in add_vol.columns
                                                  if c not in merged_vol.columns]], how="outer")

    added_rows = len(merged_px.index.difference(old_px.index))
    logger.info("Incremental price refresh: %d new trading days, matrix now %d x %d "
                "through %s", added_rows, merged_px.shape[0], merged_px.shape[1],
                pd.Timestamp(merged_px.index.max()).date())
    merged_px.to_parquet(cache_path)
    if merged_vol is not None:
        merged_vol = merged_vol[[c for c in merged_vol.columns if c in merged_px.columns]]
        merged_vol.to_parquet(config.VOLUME_CACHE)
    return merged_px


def assert_price_freshness(prices: pd.DataFrame,
                           max_stale: int = config.PRICE_MAX_STALE_TRADING_DAYS) -> tuple[pd.Timestamp, int]:
    """Refuse to publish when the price matrix is too far behind today.

    The degraded download guard deliberately keeps the previous cache rather
    than poisoning it. That is right, but on its own it let the pipeline
    rebuild every table from month old prices and stamp the result with today's
    date, which is the one failure this project's honesty layer cannot survive.
    Raises :class:`StalePriceData` so the unattended job aborts and the site
    keeps the last good data instead of publishing a fresh looking lie.
    """
    if prices is None or prices.empty:
        raise StalePriceData("price matrix is empty")
    last = pd.Timestamp(prices.index.max()).normalize()
    today = pd.Timestamp(datetime.utcnow().date())
    stale = int(np.busday_count(last.date(), today.date()))
    if stale > max_stale:
        raise StalePriceData(
            f"price data ends {last.date()}, {stale} trading days behind {today.date()} "
            f"(limit {max_stale}). The download is failing, so the dashboard would be "
            f"stamped today but built on stale prices. Fix connectivity and run "
            f"'python3 main.py --refresh' to rebuild the cache.")
    logger.info("Price freshness OK: through %s (%d trading days behind today)",
                last.date(), stale)
    return last, stale


def download_prices(
    tickers: list[str],
    years: int = config.PRICE_HISTORY_YEARS,
    force_refresh: bool = False,
    cache_path: Path = config.PRICE_CACHE,
    start: str | None = None,
) -> pd.DataFrame:
    """Wide daily adjusted close matrix (index = date, columns = ticker).

    Three paths, in order: a fresh cache is served as is; an existing universe
    cache is topped up INCREMENTALLY with a short recent window (the default
    daily path); otherwise the full history is downloaded. Delisting aware:
    columns that terminate early are kept. The universe fetch also maintains
    the daily VOLUME matrix at ``config.VOLUME_CACHE`` (Amihud input).
    """
    is_universe_cache = cache_path == config.PRICE_CACHE
    if not force_refresh and is_universe_cache and cache_path.exists():
        # Freshness by DATA date, not file mtime. A cache rewritten an hour ago
        # from a failed fetch is not fresh, and the old 24h mtime rule meant a
        # job running at the same time each morning could skip the top up
        # entirely on a rounding edge. Only skip the round trip when the cache
        # already contains today's session.
        try:
            cached = pd.read_parquet(cache_path)
            last = pd.Timestamp(cached.index.max()).date()
            if int(np.busday_count(last, datetime.utcnow().date())) <= 0:
                logger.info("Price cache already current through %s; no fetch needed", last)
                return cached
        except Exception as exc:  # noqa: BLE001
            logger.warning("price cache probe failed (%s); refetching", exc)
    elif not force_refresh and _cache_is_fresh(cache_path):
        logger.info("Loading cached prices from %s", cache_path)
        return pd.read_parquet(cache_path)

    end_dt = datetime.utcnow().date()
    if start is None:
        start = (config.PRICE_HISTORY_START if is_universe_cache
                 else (end_dt - timedelta(days=int(years * 365.25) + 10)).isoformat())
    end = end_dt.isoformat()
    tickers = sorted({t.upper() for t in tickers})

    if is_universe_cache and not force_refresh and cache_path.exists():
        merged = _incremental_refresh(tickers, cache_path, end)
        if merged is not None:
            return merged

    logger.info("Downloading %d tickers of prices+volume, %s..%s (full history)",
                len(tickers), start, end)
    prices, volumes_raw = _fetch_window(tickers, start, end, what="prices")
    if prices.empty:
        raise RuntimeError("yfinance returned no price data for any batch")

    # Keep names with at least MIN_TRADING_DAYS of data ANYWHERE in the window
    # (delisting aware: a name alive for 2y then gone still qualifies).
    keep = prices.notna().sum(axis=0)
    keep = keep[keep >= config.MIN_TRADING_DAYS].index
    dropped = prices.shape[1] - len(keep)
    prices = prices[keep]
    logger.info("Prices: kept %d tickers (dropped %d for < %d obs)",
                prices.shape[1], dropped, config.MIN_TRADING_DAYS)
    # CACHE POISON GUARD (added after the 2026-07-20 incident): a degraded
    # download (machine woke without network, DNS not up, rate limiting) must
    # never overwrite a good cache. If the fresh matrix covers under half the
    # names the existing cache has, keep the old matrix untouched and serve it.
    if is_universe_cache and cache_path.exists():
        try:
            old_px = pd.read_parquet(cache_path)
        except Exception:  # noqa: BLE001
            old_px = None
        if old_px is not None and prices.shape[1] < 0.5 * old_px.shape[1]:
            logger.error("PRICE DOWNLOAD DEGRADED: %d tickers fetched vs %d in the "
                         "existing cache; keeping the previous cache (check network)",
                         prices.shape[1], old_px.shape[1])
            return old_px
    prices.to_parquet(cache_path)

    if is_universe_cache and not volumes_raw.empty:
        volumes = volumes_raw[[c for c in volumes_raw.columns if c in prices.columns]]
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
