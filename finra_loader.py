"""FINRA Reg SHO daily short sale volume loader (roadmap 2.3).

WHY FLOW, NOT POSITIONS (premise correction, verified live 2026-07-13): the
bi monthly short interest POSITION files FINRA publishes for free cover OTC
equities only and keep one rolling year online — exchange listed names (the
whole S&P 600) are absent, their position history being exchange / vendor
data. The free dataset that DOES cover listed names is this one: the daily
consolidated short sale VOLUME file, per symbol ShortVolume / TotalVolume for
off exchange trades reported to FINRA facilities, published each evening and
available on the CDN from ~2018-10. The factors built from it are therefore
short ACTIVITY (flow) measures and are named that way. The informed shorting
literature is a flow result anyway: Boehmer, Jones & Zhang (2008) and
Diether, Lee & Werner (2009). True position history (level, days to cover)
arrives via Compustat's short interest file once WRDS access lands.

Mechanics: one pipe delimited file per trading day
(``config.FINRA_SHORT_VOLUME_DAILY_URL``). Missing dates (holidays, not yet
published) return 403/404 and are skipped. The cache keeps ALL symbols so a
later universe change never needs a refetch; the returned frame is filtered
to the requested tickers. Incremental by default: only days after the cache
maximum are downloaded (~1 file per run once warm). FINRA class share
symbols use slashes (MOG/A) where the rest of the repo uses dashes (MOG-A).

LICENSE NOTE: these are public files FINRA disseminates without registration.
The dashboard ships derived factors and aggregates, not a redistribution of
the raw files.
"""

from __future__ import annotations

import io
import logging
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

import config

logger = logging.getLogger(__name__)

_COLUMNS = {"Date": "date", "Symbol": "symbol",
            "ShortVolume": "short_vol", "TotalVolume": "total_vol"}
_MAX_WORKERS = 8


def _fetch_one(session: requests.Session, day: pd.Timestamp) -> pd.DataFrame | None:
    url = config.FINRA_SHORT_VOLUME_DAILY_URL.format(date=day)
    try:
        r = session.get(url, timeout=30, headers={"User-Agent": config.USER_AGENT})
    except requests.RequestException as exc:  # noqa: PERF203
        logger.debug("FINRA %s: %s", day.date(), exc)
        return None
    if r.status_code != 200 or not r.text.startswith("Date|"):
        return None  # holiday, weekend backstop, or not yet published
    df = pd.read_csv(io.StringIO(r.text), sep="|", usecols=list(_COLUMNS),
                     dtype={"Symbol": str}, on_bad_lines="skip")
    df = df.rename(columns=_COLUMNS)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["date", "symbol"])
    for c in ("short_vol", "total_vol"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def fetch_short_volume(tickers: list[str], force_refresh: bool = False) -> pd.DataFrame:
    """Long frame [date, ticker, short_vol, total_vol] for ``tickers``.

    Downloads any daily files newer than the cache (full backfill from
    ``config.FINRA_SHORT_VOLUME_START`` on first run, ~2000 files / a few
    minutes), then serves from the parquet cache.
    """
    cache = config.FINRA_SHORT_VOLUME_CACHE
    old = None
    if cache.exists() and not force_refresh:
        try:
            old = pd.read_parquet(cache)
        except Exception as exc:  # noqa: BLE001
            logger.warning("FINRA cache unreadable (%s); refetching", exc)

    start = pd.Timestamp(config.FINRA_SHORT_VOLUME_START)
    if old is not None and len(old):
        start = pd.Timestamp(old["date"].max()) + pd.Timedelta(days=1)
    end = pd.Timestamp.today().normalize()
    days = pd.bdate_range(start, end)

    frames = [old] if old is not None else []
    if len(days):
        logger.info("FINRA short volume: fetching %d daily files (%s -> %s)",
                    len(days), days[0].date(), days[-1].date())
        session = requests.Session()
        fetched, done = [], 0
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            for df in pool.map(lambda d: _fetch_one(session, d), days):
                done += 1
                if df is not None:
                    fetched.append(df)
                if done % 250 == 0:
                    logger.info("FINRA short volume: %d/%d days checked, %d files",
                                done, len(days), len(fetched))
        if fetched:
            frames.append(pd.concat(fetched, ignore_index=True))
    new_total = pd.concat([f for f in frames if f is not None and len(f)],
                          ignore_index=True) if frames else pd.DataFrame(
        columns=["date", "symbol", "short_vol", "total_vol"])
    if len(new_total):
        new_total = (new_total.drop_duplicates(subset=["date", "symbol"], keep="last")
                              .sort_values(["date", "symbol"]).reset_index(drop=True))
        new_total.to_parquet(cache, index=False)
        logger.info("FINRA short volume cache: %d rows, %d days, through %s",
                    len(new_total), new_total["date"].nunique(),
                    new_total["date"].max().date())

    want = {t.replace("-", "/"): t for t in tickers}
    out = new_total[new_total["symbol"].isin(want)].copy()
    out["ticker"] = out["symbol"].map(want)
    out = out[["date", "ticker", "short_vol", "total_vol"]]
    logger.info("FINRA short volume: %d rows for %d of %d requested tickers",
                len(out), out["ticker"].nunique(), len(tickers))
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    demo = fetch_short_volume(["AAON", "CHRD", "MOG-A"])
    print(demo.tail(6))
