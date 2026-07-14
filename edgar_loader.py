"""SEC EDGAR XBRL companyfacts loader — deep, free, point in time fundamentals.

Why this exists: yfinance carries ~4-5 quarters of statements, so 30 of 31
historical cross sections were scored by price factors alone. EDGAR's
companyfacts API returns every XBRL tagged figure a company ever filed —
quarterly back to ~2009 for most names — and stamps every value with its
actual FILING date. That filing date becomes the panel's ``as_of``: a true
point in time knowledge date instead of a flat 60 day guess.

NO API KEY. The SEC requires only (a) an identifying User-Agent — reused from
``config.USER_AGENT``, which carries the maintainer email — and (b) staying
under ~10 requests/second (throttled here to ``config.EDGAR_REQUESTS_PER_SEC``).

The two classic XBRL headaches, handled explicitly:

* **Tag aliasing** — filers use different us-gaap concepts for the same line
  item (``Revenues`` vs ``RevenueFromContractWithCustomer...``). Same alias
  list pattern as ``feature_engine.get_field``.
* **Year to date flows** — 10-Q cash flow statements (and Q4 income figures)
  are cumulative. Quarterly values are recovered by differencing consecutive
  YTD figures within a fiscal year and deriving Q4 = FY − Q1..Q3.

Amended figures: for every (concept, period) the FIRST filed value wins — the
number the market actually knew — never the restated one.

Output: per ticker, an ``as_of`` indexed frame with exactly the schema of
``feature_engine._fundamental_timeseries`` so ``build_panel`` consumes it via
``fund_ts_override`` with zero downstream changes.
"""

from __future__ import annotations

import json
import logging
import time

import numpy as np
import pandas as pd
import requests

import config

logger = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": config.USER_AGENT,
                         "Accept-Encoding": "gzip, deflate"})
_last_request_ts = 0.0


def _get(url: str, max_retries: int = 3) -> dict | None:
    """Rate limited GET with retries; None on terminal failure."""
    global _last_request_ts
    min_gap = 1.0 / config.EDGAR_REQUESTS_PER_SEC
    for attempt in range(max_retries):
        wait = _last_request_ts + min_gap - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_request_ts = time.time()
        try:
            resp = _SESSION.get(url, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return None
            if resp.status_code in (403, 429):
                logger.warning("EDGAR throttle (%d) on %s; backing off", resp.status_code, url)
                time.sleep(2.0 * (attempt + 1))
                continue
            logger.debug("EDGAR %d on %s", resp.status_code, url)
        except Exception as exc:  # noqa: BLE001
            logger.debug("EDGAR request failed (%s): %s", url, exc)
            time.sleep(1.0 + attempt)
    return None


# =============================================================================
# Ticker -> CIK
# =============================================================================
def ticker_cik_map(force_refresh: bool = False) -> dict[str, int]:
    """Map normalized ticker -> CIK, cached to data/edgar_cik_map.json."""
    cache = config.EDGAR_CIK_CACHE
    if not force_refresh and cache.exists() and (
            time.time() - cache.stat().st_mtime) < 7 * 24 * 3600:
        try:
            return {k: int(v) for k, v in json.loads(cache.read_text()).items()}
        except Exception:  # noqa: BLE001
            pass
    raw = _get(config.EDGAR_TICKER_CIK_URL)
    if not raw:
        logger.warning("EDGAR ticker->CIK download failed; using stale cache if any")
        if cache.exists():
            return {k: int(v) for k, v in json.loads(cache.read_text()).items()}
        return {}
    mapping = {}
    for row in raw.values():
        tk = str(row.get("ticker", "")).upper().replace(".", "-").strip()
        if tk:
            mapping[tk] = int(row["cik_str"])
    cache.write_text(json.dumps(mapping))
    logger.info("EDGAR: %d ticker->CIK mappings cached", len(mapping))
    return mapping


# =============================================================================
# Concept aliases (us-gaap unless noted)
# =============================================================================
FLOW_CONCEPTS: dict[str, list[str]] = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                "SalesRevenueNet", "SalesRevenueGoodsNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax"],
    "gross_profit": ["GrossProfit"],
    "net_income": ["NetIncomeLoss", "ProfitLoss",
                   "NetIncomeLossAvailableToCommonStockholdersBasic"],
    "ebit": ["OperatingIncomeLoss"],
    "dep_amort": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
                  "DepreciationAmortizationAndAccretionNet", "Depreciation"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment",
              "PaymentsToAcquireProductiveAssets",
              "PaymentsForCapitalImprovements"],
}
STOCK_CONCEPTS: dict[str, list[str]] = {
    "total_assets": ["Assets"],
    "total_liabilities": ["Liabilities"],
    "total_equity": ["StockholdersEquity",
                     "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "short_term_debt": ["LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "shares": ["CommonStockSharesOutstanding", "CommonStockSharesIssued"],
}
# shares: prefer the dei cover-page count (updated every filing)
DEI_SHARES = "EntityCommonStockSharesOutstanding"


def _entries(facts: dict, taxonomy: str, tag: str) -> list[dict]:
    node = facts.get(taxonomy, {}).get(tag)
    if not node:
        return []
    units = node.get("units", {})
    for unit in ("USD", "shares", "USD/shares", "pure"):
        if unit in units:
            return units[unit]
    return next(iter(units.values()), [])


def _first_filed(rows: list[tuple]) -> dict:
    """{key: (val, filed)} keeping the EARLIEST filed value per key."""
    out: dict = {}
    for key, val, filed in rows:
        if key not in out or filed < out[key][1]:
            out[key] = (val, filed)
    return out


def _quarterly_flow(entries: list[dict]) -> dict[pd.Timestamp, tuple[float, pd.Timestamp]]:
    """end -> (quarterly value, first filed date) for a duration (flow) concept.

    Direct ~3 month figures win. Cash flow statements (and some Q4 income
    figures) only exist as YEAR TO DATE numbers, so every cumulative sequence
    sharing one (fiscal year, period start) is differenced end to end — the
    ~90 day first leg anchors the chain (it IS Q1), each later leg whose gap is
    one quarter yields that quarter, and FY − Q3 YTD yields Q4.
    """
    parsed = []
    for e in entries:
        try:
            start = pd.Timestamp(e["start"])
            end = pd.Timestamp(e["end"])
            filed = pd.Timestamp(e.get("filed"))
            val = float(e["val"])
        except (KeyError, TypeError, ValueError):
            continue
        dur = (end - start).days
        if dur < 60:
            continue
        parsed.append({"start": start, "end": end, "dur": dur, "val": val,
                       "filed": filed, "fy": e.get("fy")})
    if not parsed:
        return {}

    # 1) direct quarterly figures (~60-120 day duration), first filed wins
    direct = _first_filed([(p["end"], p["val"], p["filed"])
                           for p in parsed if p["dur"] <= 120])

    # 2) cumulative chains: ALL durations sharing (fy, start), diffed in order
    derived: list[tuple] = []
    by_chain: dict = {}
    for p in parsed:
        by_chain.setdefault((p["fy"], p["start"]), []).append(p)
    for (_fy, _start), rows in by_chain.items():
        best = _first_filed([(p["end"], p["val"], p["filed"]) for p in rows])
        seq = sorted(best.items())  # [(end, (cum_val, filed)), ...] ascending
        prev_end, prev_val = None, None
        for end, (cum, filed) in seq:
            if prev_end is None:
                prev_end, prev_val = end, cum
                continue
            gap = (end - prev_end).days
            if 60 <= gap <= 120:
                derived.append((end, cum - prev_val, filed))
            prev_end, prev_val = end, cum

    for end, val, filed in derived:
        if end not in direct:
            direct[end] = (val, filed)
    return direct


def _quarterly_stock(entries: list[dict]) -> dict[pd.Timestamp, tuple[float, pd.Timestamp]]:
    """end -> (value, first filed) for an instantaneous (balance) concept."""
    rows = []
    for e in entries:
        if "start" in e and e.get("start"):
            # some filers tag balances with a duration; treat end as the date
            pass
        try:
            rows.append((pd.Timestamp(e["end"]), float(e["val"]),
                         pd.Timestamp(e.get("filed"))))
        except (KeyError, TypeError, ValueError):
            continue
    return _first_filed(rows)


def _concept_series(facts: dict, aliases: list[str], flow: bool) -> dict:
    """MERGE aliases: earlier aliases win per period, later ones fill gaps.

    Filers switch tags over the years (``SalesRevenueNet`` pre-2018,
    ``RevenueFromContractWithCustomer...`` after ASC 606) — first-alias-wins
    would silently discard the older era, so every alias contributes the
    periods it alone covers.
    """
    merged: dict = {}
    for tag in aliases:
        entries = _entries(facts, "us-gaap", tag)
        if not entries:
            continue
        out = _quarterly_flow(entries) if flow else _quarterly_stock(entries)
        for end, v in out.items():
            merged.setdefault(end, v)
    return merged


# =============================================================================
# Per ticker: quarterly frame -> the _fundamental_timeseries schema
# =============================================================================
def _safe(numer, denom):
    if numer is None or denom is None or not np.isfinite(numer) or not np.isfinite(denom) or denom == 0:
        return np.nan
    return numer / denom


def fundamentals_from_facts(facts: dict) -> pd.DataFrame:
    """Build the as_of indexed factor frame from one companyfacts payload."""
    series: dict[str, dict] = {}
    for key, aliases in FLOW_CONCEPTS.items():
        series[key] = _concept_series(facts, aliases, flow=True)
    for key, aliases in STOCK_CONCEPTS.items():
        series[key] = _concept_series(facts, aliases, flow=False)
    # dei cover page share count usually stamps every filing
    dei = _quarterly_stock(_entries(facts, "dei", DEI_SHARES))
    if dei:
        merged = dict(series.get("shares", {}))
        for end, v in dei.items():
            merged.setdefault(end, v)
        series["shares"] = merged

    ends = sorted({e for s in series.values() for e in s})
    if not ends:
        return pd.DataFrame()

    rows = []
    for end in ends:
        rec: dict = {"quarter_end": end}
        filed_dates = []
        for key, s in series.items():
            v = s.get(end)
            rec[key] = v[0] if v else np.nan
            if v is not None and pd.notna(v[1]):
                filed_dates.append(v[1])
        core = [series[k].get(end) for k in ("revenue", "net_income", "total_assets")]
        core_filed = [c[1] for c in core if c is not None and pd.notna(c[1])]
        if core_filed:
            rec["as_of"] = max(core_filed)
        elif filed_dates:
            rec["as_of"] = max(filed_dates)
        else:
            rec["as_of"] = end + pd.Timedelta(days=60)
        rows.append(rec)

    q = pd.DataFrame(rows).sort_values("quarter_end").reset_index(drop=True)
    # a quarter must at least have income or assets to count
    q = q[q[["revenue", "net_income", "total_assets"]].notna().any(axis=1)]
    if q.empty:
        return pd.DataFrame()

    # trailing twelve months on flows (4 consecutive fiscal quarters)
    for col in ("revenue", "gross_profit", "net_income", "ebit", "dep_amort", "ocf", "capex"):
        q[f"{col}_ttm"] = q[col].rolling(4, min_periods=4).sum()
    ebitda = q["ebit_ttm"] + q["dep_amort_ttm"].abs()
    q["ebitda_ttm"] = ebitda
    q["fcf_ttm"] = q["ocf_ttm"] - q["capex_ttm"].abs()

    equity = q["total_equity"].where(
        q["total_equity"].notna(), q["total_assets"] - q["total_liabilities"])
    debt = q[["long_term_debt", "short_term_debt"]].sum(axis=1, min_count=1)

    out = pd.DataFrame({
        "as_of": q["as_of"],
        "quarter_end": q["quarter_end"],
        "net_income_ttm": q["net_income_ttm"],
        "ebitda_ttm": q["ebitda_ttm"],
        "revenue_ttm": q["revenue_ttm"],
        "fcf_ttm": q["fcf_ttm"],
        "total_debt": debt,
        "cash": q["cash"],
        "shares": q["shares"],
        "total_assets": q["total_assets"],
        "roe": [ _safe(n, d) for n, d in zip(q["net_income_ttm"], equity) ],
        "roa": [ _safe(n, d) for n, d in zip(q["net_income_ttm"], q["total_assets"]) ],
        "gross_margin": [ _safe(n, d) for n, d in zip(q["gross_profit_ttm"], q["revenue_ttm"]) ],
        "fcf_margin": [ _safe(n, d) for n, d in zip(q["fcf_ttm"], q["revenue_ttm"]) ],
        "accruals_ocf_ni": [ _safe(n, d) for n, d in zip(q["ocf_ttm"], q["net_income_ttm"]) ],
    })
    out = out.set_index("as_of").sort_index()
    out["roe_yoy"] = out["roe"] - out["roe"].shift(4)
    out["gross_margin_yoy"] = out["gross_margin"] - out["gross_margin"].shift(4)
    out["asset_growth_yoy"] = out["total_assets"] / out["total_assets"].shift(4) - 1.0
    out["net_issuance_yoy"] = out["shares"] / out["shares"].shift(4) - 1.0
    return out


# =============================================================================
# Bulk fetch with cache
# =============================================================================
def fetch_edgar_fundamentals(tickers: list[str],
                             force_refresh: bool = False) -> dict[str, pd.DataFrame]:
    """Per ticker as_of indexed fundamental frames, cached to one parquet."""
    cache = config.EDGAR_CACHE
    if not force_refresh and cache.exists() and (
            time.time() - cache.stat().st_mtime) < config.CACHE_MAX_AGE_SECONDS:
        logger.info("Loading cached EDGAR fundamentals from %s", cache)
        flat = pd.read_parquet(cache)
        return {tk: g.drop(columns="ticker").set_index("as_of").sort_index()
                for tk, g in flat.groupby("ticker")}

    ciks = ticker_cik_map(force_refresh=force_refresh)
    tickers = sorted({t.upper() for t in tickers})
    out: dict[str, pd.DataFrame] = {}
    missing_cik, empty = [], []
    t0 = time.time()
    for i, tk in enumerate(tickers):
        if i and i % 100 == 0:
            logger.info("  EDGAR %d/%d (%.0fs elapsed, %d ok)",
                        i, len(tickers), time.time() - t0, len(out))
        cik = ciks.get(tk)
        if cik is None:
            missing_cik.append(tk)
            continue
        facts = _get(config.EDGAR_COMPANYFACTS_URL.format(cik=cik))
        if not facts:
            empty.append(tk)
            continue
        try:
            ts = fundamentals_from_facts(facts.get("facts") or {})
        except Exception as exc:  # noqa: BLE001
            logger.debug("%s: EDGAR parse failed: %s", tk, exc)
            empty.append(tk)
            continue
        if ts.empty:
            empty.append(tk)
            continue
        out[tk] = ts

    logger.info("EDGAR fundamentals: %d/%d tickers parsed (%d no CIK, %d empty/failed) "
                "in %.0fs", len(out), len(tickers), len(missing_cik), len(empty),
                time.time() - t0)
    if missing_cik:
        logger.info("  no CIK (fall back to yfinance): %s%s",
                    ", ".join(missing_cik[:15]), " …" if len(missing_cik) > 15 else "")

    if out:
        flat = pd.concat([ts.reset_index().assign(ticker=tk) for tk, ts in out.items()],
                         ignore_index=True)
        flat.to_parquet(cache)
    return out


# =============================================================================
# Earnings event dates (roadmap 2.5 — 8-K item 2.02)
# =============================================================================
def _events_from_filing_arrays(arr: dict) -> list[tuple[str, str]]:
    """[(filingDate, acceptanceDateTime)] for earnings 8-Ks in one filings block."""
    forms = arr.get("form") or []
    items = arr.get("items") or []
    fdates = arr.get("filingDate") or []
    accept = arr.get("acceptanceDateTime") or []
    out = []
    for i in range(len(forms)):
        if forms[i] == "8-K" and "2.02" in (items[i] or ""):
            out.append((fdates[i], accept[i] if i < len(accept) else ""))
    return out


def _reaction_day(filing_date: str, acceptance: str) -> pd.Timestamp:
    """First session whose CLOSE can reflect the news.

    acceptanceDateTime is UTC (verified live 2026-07-14: after close filers
    cluster at 20-21Z = 16-17 Eastern). Accepted before 16:00 Eastern -> the
    filing day's close already reacts; at or after 16:00 -> the next day is
    the reaction day. Missing acceptance falls back to the filing day (the
    surrounding [r0-1, r0+1] window still spans the true reaction).
    """
    try:
        et = pd.Timestamp(acceptance).tz_convert("America/New_York")
        r0 = et.normalize().tz_localize(None)
        if et.hour >= 16:
            r0 = r0 + pd.offsets.BDay(1)
        return r0
    except (ValueError, TypeError):
        return pd.Timestamp(filing_date)


def fetch_earnings_events(tickers: list[str], force_refresh: bool = False) -> pd.DataFrame:
    """Earnings event reaction days per ticker: [ticker, reaction_date].

    Events are 8-K filings carrying item 2.02 (Results of Operations), the
    disclosure vehicle for the earnings press release, pulled from the EDGAR
    submissions index. The recent page covers ~1000 filings; older archive
    pages are fetched only the first time a ticker enters the cache (they are
    immutable), so a warm refresh is one request per name. Events within four
    weeks of a prior one are dropped (amended or duplicate 2.02 filings in
    the same cycle).
    """
    cache = config.EARNINGS_EVENTS_CACHE
    old = pd.DataFrame(columns=["ticker", "reaction_date"])
    if cache.exists():
        try:
            old = pd.read_parquet(cache)
        except Exception as exc:  # noqa: BLE001
            logger.warning("earnings events cache unreadable (%s); refetching", exc)
    if (not force_refresh and cache.exists()
            and (time.time() - cache.stat().st_mtime) < config.CACHE_MAX_AGE_SECONDS
            and set(tickers) <= set(old["ticker"].unique())):
        return old[old["ticker"].isin(set(tickers))].copy()

    ciks = ticker_cik_map(force_refresh=force_refresh)
    known = set(old["ticker"].unique())
    t0 = time.time()
    rows: list[dict] = []
    n_arch = 0
    for n, tk in enumerate(tickers, 1):
        cik = ciks.get(tk.upper().replace(".", "-"))
        if cik is None:
            continue
        d = _get(config.EDGAR_SUBMISSIONS_URL.format(name=f"CIK{cik:010d}.json"))
        if not d:
            continue
        filings = d.get("filings") or {}
        pairs = _events_from_filing_arrays(filings.get("recent") or {})
        # archive pages: immutable deep history, only on first acquaintance
        if tk not in known:
            for f in filings.get("files") or []:
                arch = _get(config.EDGAR_SUBMISSIONS_URL.format(name=f["name"]))
                if arch:
                    n_arch += 1
                    pairs.extend(_events_from_filing_arrays(arch))
        for fdate, accept in pairs:
            rows.append({"ticker": tk, "reaction_date": _reaction_day(fdate, accept)})
        if n % 200 == 0:
            logger.info("EDGAR earnings events: %d/%d tickers", n, len(tickers))

    new = pd.DataFrame(rows, columns=["ticker", "reaction_date"])
    parts = [f for f in (old, new) if len(f)]
    merged = (pd.concat(parts, ignore_index=True) if parts
              else pd.DataFrame(columns=["ticker", "reaction_date"]))
    merged["reaction_date"] = pd.to_datetime(merged["reaction_date"])
    merged = (merged.dropna()
                    .drop_duplicates(subset=["ticker", "reaction_date"])
                    .sort_values(["ticker", "reaction_date"]).reset_index(drop=True))
    # collapse near duplicates (amendments / split 2.02 filings): keep the first
    merged["gap"] = merged.groupby("ticker")["reaction_date"].diff()
    merged = merged[(merged["gap"].isna()) | (merged["gap"] > pd.Timedelta(days=28))]
    merged = merged.drop(columns=["gap"]).reset_index(drop=True)
    merged.to_parquet(cache, index=False)
    logger.info("EDGAR earnings events: %d events for %d tickers (%d archive pages) "
                "in %.0fs", len(merged), merged["ticker"].nunique(), n_arch,
                time.time() - t0)
    return merged[merged["ticker"].isin(set(tickers))].copy()
