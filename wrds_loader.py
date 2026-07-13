"""WRDS connector (CRSP / Compustat) — RESEARCH ONLY, scaffold pending credentials.

WRDS is the university's research data platform: CRSP gives survivorship free
prices with **delisting returns and reason codes** (the exact input our
delisting terminal return logic needs), Compustat gives point in time
fundamentals, IBES gives estimate revisions. It is a Postgres service, not a
REST API: the ``wrds`` package opens a database connection with your WRDS
ACCOUNT login (there is no separate API key).

Setup (one time):
    pip install wrds
    # then put your WRDS account credentials in .env (never committed):
    #   WRDS_USERNAME=your_wrds_username
    #   WRDS_PASSWORD=your_wrds_password
    # First connection may prompt to create a ~/.pgpass entry — accept it.

LICENSE BOUNDARY (do not cross): WRDS data is licensed for research use by
authorized university users. It must NEVER be exported into the public
dashboard (webapp/public), committed to the repo, or redistributed. Use it to
validate the EDGAR pipeline, compute clean delisting adjusted history for the
paper/IMA writeups, and benchmark data quality — the public site keeps running
on EDGAR + yfinance.

STATUS: scaffold. The queries below are written and documented but UNTESTED
until credentials exist. Nothing in main.py imports this module yet — wiring
happens after a first successful connection is verified interactively.
"""

from __future__ import annotations

import logging

import pandas as pd

import config

logger = logging.getLogger(__name__)


class WRDSUnavailable(RuntimeError):
    """Raised when credentials or the wrds package are missing."""


def connect():
    """Open a WRDS connection from .env credentials.

    Returns a ``wrds.Connection``. Raises WRDSUnavailable with a actionable
    message otherwise.
    """
    if not (config.WRDS_USERNAME and config.WRDS_PASSWORD):
        raise WRDSUnavailable(
            "WRDS credentials missing: set WRDS_USERNAME / WRDS_PASSWORD in .env "
            "(see .env.example). These are your WRDS account login, not an API key.")
    try:
        import wrds  # optional dependency: pip install wrds
    except ImportError as exc:
        raise WRDSUnavailable("The 'wrds' package is not installed: pip install wrds") from exc
    logger.info("Connecting to WRDS as %s (research license — data stays local)",
                config.WRDS_USERNAME)
    return wrds.Connection(wrds_username=config.WRDS_USERNAME,
                           wrds_password=config.WRDS_PASSWORD)


def crsp_delisting_events(db, start: str = "2010-01-01") -> pd.DataFrame:
    """Delisting events with CRSP reason codes and delisting returns.

    This is the dataset that fixes ``DELISTING_TERMINAL_RETURN``: CRSP's
    ``dlstcd`` distinguishes mergers (2xx — usually a PREMIUM, not a wipeout),
    exchanges (3xx), liquidations (4xx) and performance related drops (5xx),
    and ``dlret`` is the actual return shareholders realized at the event.
    Returns [permno, ticker, dlstdt, dlstcd, dlret].
    """
    q = f"""
        select d.permno, n.ticker, d.dlstdt, d.dlstcd, d.dlret
        from crsp.msedelist d
        join crsp.stocknames n
          on d.permno = n.permno
         and d.dlstdt between n.namedt and n.nameenddt
        where d.dlstdt >= '{start}'
    """
    out = db.raw_sql(q, date_cols=["dlstdt"])
    logger.info("CRSP delistings: %d events since %s", len(out), start)
    return out


def compustat_quarterly(db, start: str = "2010-01-01") -> pd.DataFrame:
    """Compustat quarterly fundamentals mapped toward the panel's schema.

    ``rdq`` (the earnings report date) plays the role EDGAR's filing date plays
    for us: the point in time knowledge stamp. Column mapping to our factors:
    revtq→revenue, niq→net_income, atq→total_assets, ltq→total_liabilities,
    seqq→equity, cheq→cash, dlttq+dlcq→debt, cshoq→shares, oancfy→OCF (YTD —
    de accumulate like EDGAR), capxy→capex (YTD).
    Returns the raw quarterly frame; adaptation into
    ``feature_engine._fundamental_timeseries`` schema happens after the first
    live connection validates column availability.
    """
    q = f"""
        select gvkey, tic, datadate, rdq, fyearq, fqtr,
               revtq, cogsq, niq, oiadpq, dpq, atq, ltq, seqq,
               cheq, dlttq, dlcq, cshoq, oancfy, capxy
        from comp.fundq
        where indfmt = 'INDL' and datafmt = 'STD' and popsrc = 'D'
          and consol = 'C' and datadate >= '{start}'
    """
    out = db.raw_sql(q, date_cols=["datadate", "rdq"])
    logger.info("Compustat quarterly: %d rows since %s", len(out), start)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    db = connect()  # raises with instructions if credentials are absent
    print(crsp_delisting_events(db).head())
