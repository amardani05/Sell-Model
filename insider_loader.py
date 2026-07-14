"""SEC insider transactions loader (roadmap 2.4 — EDGAR Form 4).

Source: the SEC's quarterly "Insider Transactions Data Sets" — structured
TSVs derived from every Form 3/4/5 XML filing, one zip per quarter back to
2006, ~8MB each (schema verified live 2026-07-14). This is the bulk channel:
fetching a million individual Form 4 filings through the 8 req/s EDGAR limit
would take days; the quarterly zips take minutes once.

What is kept: open market purchases and sales only (TRANS_CODE P and S from
NONDERIV_TRANS) — awards, option exercises, gifts and swaps are compensation
mechanics, not information. Rows where the filer checked the 10b5-1 plan box
(AFF10B5ONE, reliably populated since the 2023 rule change) are stored
separately so the factor can exclude scheduled trades. Everything is joined
to the issuer via SUBMISSION and keyed by CIK (the trading symbol field is
too messy to key on), stamped with the FILING date — Form 4s are due within
two business days of the trade, so the filing date is an honest point in
time knowledge stamp.

FRESHNESS LIMIT (say it out loud): the SEC posts each quarter's data set a
week or two AFTER quarter end, so the most recent cross sections are missing
up to ~3 months of the trailing window right after a quarter turn. The
trailing 6 month factor window keeps that gap a minority of the signal, and
the Methodology tab discloses it.

Reading: Lakonishok & Lee (2001) — insider purchases predict returns, small
caps most; Cohen, Malloy & Pomorski (2012) — separating routine from
opportunistic traders sharpens the signal (a per insider refinement this
loader's aggregation does not yet attempt).
"""

from __future__ import annotations

import io
import json
import logging
import zipfile

import pandas as pd
import requests

import config

logger = logging.getLogger(__name__)

# The newest quarter sometimes lives under a different prefix while DERA
# migrates pages; try in order (both verified live 2026-07-14).
_ZIP_URLS = [
    "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{q}_form345.zip",
    "https://www.sec.gov/files/datastandardsinnovation/data/insider-transactions-data-sets/{q}_form345.zip",
]
_OPEN_MARKET_CODES = {"P", "S"}


def _quarters(start: str) -> list[str]:
    out = []
    q = pd.Period(start, freq="Q")
    now = pd.Period(pd.Timestamp.today(), freq="Q")
    while q <= now:
        out.append(f"{q.year}q{q.quarter}")
        q += 1
    return out


def _fetch_quarter(session: requests.Session, q: str) -> pd.DataFrame | None:
    """One quarter's open market transactions, aggregated per (cik, filing date)."""
    blob = None
    for tmpl in _ZIP_URLS:
        try:
            r = session.get(tmpl.format(q=q), timeout=120,
                            headers={"User-Agent": config.USER_AGENT})
        except requests.RequestException as exc:  # noqa: PERF203
            logger.debug("insider %s: %s", q, exc)
            continue
        if r.status_code == 200 and r.content[:2] == b"PK":
            blob = r.content
            break
    if blob is None:
        return None  # not published yet (current quarter) or transient failure

    z = zipfile.ZipFile(io.BytesIO(blob))
    sub = pd.read_csv(io.BytesIO(z.read("SUBMISSION.tsv")), sep="\t",
                      usecols=["ACCESSION_NUMBER", "FILING_DATE", "ISSUERCIK"],
                      dtype={"ISSUERCIK": "Int64"}, low_memory=False)
    want = {"ACCESSION_NUMBER", "TRANS_CODE", "TRANS_ACQUIRED_DISP_CD",
            "TRANS_SHARES", "AFF10B5ONE"}
    # AFF10B5ONE (the 10b5-1 plan checkbox) joined the schema with the 2023
    # rule change; older quarters simply lack the column.
    nd = pd.read_csv(io.BytesIO(z.read("NONDERIV_TRANS.tsv")), sep="\t",
                     usecols=lambda c: c in want, low_memory=False)
    if "AFF10B5ONE" not in nd.columns:
        nd["AFF10B5ONE"] = 0
    nd = nd[nd["TRANS_CODE"].isin(_OPEN_MARKET_CODES)].copy()
    if nd.empty:
        return pd.DataFrame()
    nd["TRANS_SHARES"] = pd.to_numeric(nd["TRANS_SHARES"], errors="coerce")
    nd = nd.dropna(subset=["TRANS_SHARES"])
    nd["is_buy"] = nd["TRANS_ACQUIRED_DISP_CD"].astype(str).str.upper().eq("A")
    nd["is_plan"] = (pd.to_numeric(nd["AFF10B5ONE"], errors="coerce")
                     .fillna(0).astype(int).eq(1))

    m = nd.merge(sub, on="ACCESSION_NUMBER", how="left").dropna(subset=["ISSUERCIK"])
    m["FILING_DATE"] = pd.to_datetime(m["FILING_DATE"], errors="coerce")
    m = m.dropna(subset=["FILING_DATE"])
    m["buy_shares"] = m["TRANS_SHARES"].where(m["is_buy"] & ~m["is_plan"], 0.0)
    m["sell_shares"] = m["TRANS_SHARES"].where(~m["is_buy"] & ~m["is_plan"], 0.0)
    m["plan_shares"] = m["TRANS_SHARES"].where(m["is_plan"], 0.0)
    agg = (m.groupby(["ISSUERCIK", "FILING_DATE"], as_index=False)
             [["buy_shares", "sell_shares", "plan_shares"]].sum())
    agg = agg.rename(columns={"ISSUERCIK": "cik", "FILING_DATE": "filing_date"})
    agg["cik"] = agg["cik"].astype(int)
    return agg


def fetch_insider_transactions(force_refresh: bool = False) -> pd.DataFrame:
    """All issuers' open market insider flow: [cik, filing_date, buy_shares,
    sell_shares, plan_shares], aggregated per issuer and filing date.

    Cached in ``config.INSIDER_CACHE``; completed quarters are recorded in
    ``config.INSIDER_QUARTERS_JSON`` and never refetched, so a warm run only
    checks whether a new quarter has been posted. The frame is universe
    agnostic (keyed by CIK) — ticker mapping happens in the caller via the
    EDGAR CIK map, so universe changes never force a refetch.
    """
    cache, qjson = config.INSIDER_CACHE, config.INSIDER_QUARTERS_JSON
    done: list[str] = []
    old = None
    if not force_refresh and cache.exists() and qjson.exists():
        try:
            old = pd.read_parquet(cache)
            done = json.loads(qjson.read_text())
        except Exception as exc:  # noqa: BLE001
            logger.warning("insider cache unreadable (%s); refetching", exc)
            old, done = None, []

    todo = [q for q in _quarters(config.INSIDER_HISTORY_START) if q not in done]
    frames = [old] if old is not None else []
    if todo:
        logger.info("Insider transactions: fetching %d quarterly data sets (%s -> %s)",
                    len(todo), todo[0], todo[-1])
        session = requests.Session()
        for i, q in enumerate(todo, 1):
            got = _fetch_quarter(session, q)
            if got is None:
                logger.info("Insider transactions: %s not published yet, stopping", q)
                break
            frames.append(got)
            done.append(q)
            if i % 8 == 0:
                logger.info("Insider transactions: %d/%d quarters fetched", i, len(todo))
    out = (pd.concat([f for f in frames if f is not None and len(f)], ignore_index=True)
           if any(f is not None and len(f) for f in frames)
           else pd.DataFrame(columns=["cik", "filing_date", "buy_shares",
                                      "sell_shares", "plan_shares"]))
    if len(out):
        out = (out.drop_duplicates(subset=["cik", "filing_date"], keep="last")
                  .sort_values(["cik", "filing_date"]).reset_index(drop=True))
        out.to_parquet(cache, index=False)
        qjson.write_text(json.dumps(sorted(done)))
        logger.info("Insider cache: %d issuer day rows, %d quarters, through %s",
                    len(out), len(done), out["filing_date"].max().date())
    return out


def map_to_tickers(agg: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Filter the CIK keyed frame to our universe and stamp tickers.

    Uses the EDGAR CIK map the fundamentals loader already maintains
    (``config.EDGAR_CIK_CACHE``). Names without a CIK simply carry NaN
    insider factors — never guessed.
    """
    if agg.empty or not config.EDGAR_CIK_CACHE.exists():
        return pd.DataFrame(columns=["date", "ticker", "buy_shares",
                                     "sell_shares", "plan_shares"])
    cik_map = json.loads(config.EDGAR_CIK_CACHE.read_text())
    want = {int(cik): tk for tk, cik in cik_map.items() if tk in set(tickers)}
    out = agg[agg["cik"].isin(want)].copy()
    out["ticker"] = out["cik"].map(want)
    out = out.rename(columns={"filing_date": "date"})
    out = out[["date", "ticker", "buy_shares", "sell_shares", "plan_shares"]]
    logger.info("Insider transactions: %d rows for %d of %d requested tickers",
                len(out), out["ticker"].nunique(), len(tickers))
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    frame = fetch_insider_transactions()
    print(frame.tail(6))
