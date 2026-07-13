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

LICENSE NOTE (PM decision, 2026-07-13): Amar has decided WRDS data may inform
the dashboard on educational use grounds (IMA is a student driven fund). The
recorded recommendation that accompanies that decision: WRDS derived AGGREGATE
statistics (IC series, delisting adjusted backtest curves, stress tables) are
the defensible zone — publishing per name RAW WRDS data (prices, fundamentals
line items) on a publicly reachable site is redistribution under most WRDS
subscription terms regardless of intent, and the subscription at risk is the
university's. If per name WRDS data must ship, put the deployment behind
access control first. Being a student fund changes the use case, not the
license text.

STATUS: connection scaffold live tested 2026-07-13 — network + TLS verified,
login rejected (see connect() docstring). Queries run the moment a working
login exists. Nothing in main.py imports this module yet.
"""

from __future__ import annotations

import logging

import pandas as pd

import config

logger = logging.getLogger(__name__)


class WRDSUnavailable(RuntimeError):
    """Raised when credentials or the wrds package are missing."""


def connect():
    """Open a direct SQLAlchemy engine to the WRDS Postgres service.

    WRDS is plain Postgres behind the scenes (wrds-pgdata.wharton.upenn.edu:9737,
    database ``wrds``, sslmode required). Connecting directly avoids the wrds
    package's interactive credential prompts, which break in non interactive
    runs. Raises WRDSUnavailable with an actionable message otherwise.

    Live test 2026-07-13: connectivity + TLS verified end to end; the login
    itself returned "PAM authentication failed" — either a password typo or a
    student account without pgdata access (verify at wrds-www.wharton.upenn.edu
    and ask the WRDS rep to enable API access if the web login works).
    """
    if not (config.WRDS_USERNAME and config.WRDS_PASSWORD):
        raise WRDSUnavailable(
            "WRDS credentials missing: set WRDS_USERNAME / WRDS_PASSWORD in .env "
            "(see .env.example). These are your WRDS account login, not an API key.")
    from urllib.parse import quote_plus
    from sqlalchemy import create_engine
    logger.info("Connecting to WRDS as %s", config.WRDS_USERNAME)
    dsn = (f"postgresql+psycopg2://{config.WRDS_USERNAME}:"
           f"{quote_plus(config.WRDS_PASSWORD)}"
           f"@wrds-pgdata.wharton.upenn.edu:9737/wrds?sslmode=require")
    return create_engine(dsn, connect_args={"connect_timeout": 30})


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
    import pandas as pd
    out = pd.read_sql(q, db, parse_dates=["dlstdt"])
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
    import pandas as pd
    out = pd.read_sql(q, db, parse_dates=["datadate", "rdq"])
    logger.info("Compustat quarterly: %d rows since %s", len(out), start)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    db = connect()  # raises with instructions if credentials are absent
    print(crsp_delisting_events(db).head())
