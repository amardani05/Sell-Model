"""Point in time S&P 600 membership.

The whole backtest hinges on using the universe **as it was** at each rebalance
date, not today's membership — otherwise the results are survivorship biased
(you only ever rank the names that survived to today). Ben's earnings model left
this out; we do not.

Resolution order for `members_on(date)`:
  1. A real point in time membership store at ``data/sp600_membership.csv``
     (schema documented in that file). Used silently if it has real rows.
  2. Current Wikipedia membership, scraped and seeded into the store with
     ``start_date = today`` — and a LOUD warning that the panel is now
     survivorship biased and only valid at/after today.

`members_on` returns the ticker set valid on a date together with the GICS
sector each name belonged to at that time (the sector neutral grouping key).
"""

from __future__ import annotations

import csv
import logging
import time
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

_MEMBERSHIP_COLUMNS = [
    "ticker", "company", "gics_sector", "start_date", "end_date", "delist_note",
]


def _normalize_ticker(ticker: str) -> str:
    """Yahoo uses '-' instead of '.' for share classes (BRK.B -> BRK B)."""
    return str(ticker).strip().upper().replace(".", "-")


# =============================================================================
# Membership store I/O
# =============================================================================
def load_membership() -> pd.DataFrame:
    """Load the PIT membership store, ignoring comment / blank rows.

    Returns a frame with parsed ``start_date`` / ``end_date`` (NaT end = current
    member). Empty frame (correct columns) if the store has no real rows yet.
    """
    path = config.SP600_MEMBERSHIP_CSV
    if not path.exists():
        return pd.DataFrame(columns=_MEMBERSHIP_COLUMNS)

    # Keep comment (#) / blank / header lines out, then parse the rest with the
    # csv module so quoted company names containing commas survive intact.
    data_lines = []
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.lower().startswith("ticker,"):
            continue
        data_lines.append(line)
    if not data_lines:
        return pd.DataFrame(columns=_MEMBERSHIP_COLUMNS)

    parsed = []
    for fields in csv.reader(data_lines):
        if len(fields) < 5:
            continue
        # Tolerate a stray unquoted comma in legacy company names: collapse extras.
        if len(fields) > 6:
            fields = [fields[0], ",".join(fields[1:len(fields) - 4]), *fields[-4:]]
        fields = (fields + [""] * 6)[:6]
        parsed.append(fields)

    df = pd.DataFrame(parsed, columns=_MEMBERSHIP_COLUMNS)
    df["ticker"] = df["ticker"].map(_normalize_ticker)
    df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")
    df["end_date"] = pd.to_datetime(df["end_date"].replace("", pd.NA), errors="coerce")  # NaT = current
    df = df.dropna(subset=["ticker", "start_date"])
    return df.reset_index(drop=True)


def _write_membership(df: pd.DataFrame) -> None:
    """Append a current membership snapshot to the store, preserving the header.

    Uses ``csv.writer`` so company names containing commas are quoted correctly.
    """
    existing = config.SP600_MEMBERSHIP_CSV.read_text().rstrip("\n") if config.SP600_MEMBERSHIP_CSV.exists() else ""
    buf = StringIO()
    writer = csv.writer(buf)
    for _, r in df.iterrows():
        end = "" if pd.isna(r["end_date"]) else pd.Timestamp(r["end_date"]).date().isoformat()
        writer.writerow([
            r["ticker"], r["company"], r["gics_sector"],
            pd.Timestamp(r["start_date"]).date().isoformat(), end, r.get("delist_note", ""),
        ])
    block = buf.getvalue().rstrip("\n")
    out = (existing + "\n" + block) if existing else block
    config.SP600_MEMBERSHIP_CSV.write_text(out + "\n")


def has_real_membership() -> bool:
    """True only for a genuine point in time store, detected STRUCTURALLY.

    A real PIT export has history: names entering on many different dates, and/or
    names that have left (a filled end_date or delist_note). A snapshot seeded
    from current Wikipedia membership has every row sharing ONE start_date, no
    end_dates and no delist_notes. We test the structure, not the age, so a
    snapshot never silently "ages into" looking like real history (which would
    wrongly switch off the current only survivorship broadcast).
    """
    df = load_membership()
    if df.empty:
        return False
    multiple_start_dates = df["start_date"].nunique() > 1
    any_end_dates = df["end_date"].notna().any()
    any_delist_note = df.get("delist_note", pd.Series(dtype=str)).fillna("").str.strip().ne("").any()
    return bool(multiple_start_dates or any_end_dates or any_delist_note)


# =============================================================================
# Current membership (Wikipedia) — fallback + seeding
# =============================================================================
def _scrape_wikipedia_index(url: str, index_label: str, min_count: int) -> pd.DataFrame:
    """Scrape one Wikipedia constituent table. Columns: ticker, company, gics_sector."""
    logger.info("Scraping current %s constituents from Wikipedia", index_label)
    headers = {"User-Agent": config.USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    df: pd.DataFrame | None = None
    for t in soup.find_all("table", {"class": "wikitable"}):
        try:
            cand = pd.read_html(StringIO(str(t)))[0]
        except ValueError:
            continue
        cols = [str(c).lower() for c in cand.columns]
        if any("symbol" in c or "ticker" in c for c in cols):
            df = cand
            break
    if df is None:
        raise RuntimeError(f"Could not locate {index_label} constituent table on Wikipedia")

    rename = {}
    for c in df.columns:
        cl = str(c).lower()
        if "symbol" in cl or "ticker" in cl:
            rename[c] = "ticker"
        elif "security" in cl or "company" in cl:
            rename[c] = "company"
        elif "sector" in cl and "sub" not in cl:
            rename[c] = "gics_sector"
    df = df.rename(columns=rename)
    for col in ["company", "gics_sector"]:
        if col not in df.columns:
            df[col] = "Unknown"
    df = df[["ticker", "company", "gics_sector"]].copy()
    df["ticker"] = df["ticker"].map(_normalize_ticker)
    df = df.drop_duplicates(subset=["ticker"]).reset_index(drop=True)

    if len(df) < min_count:
        raise RuntimeError(f"Suspiciously few {index_label} tickers scraped ({len(df)})")
    logger.info("Scraped %d current %s constituents", len(df), index_label)
    return df


def _scrape_current_wikipedia() -> pd.DataFrame:
    """Scrape today's combined S&P 600 + S&P 400 universe.

    The S&P 400 (MidCap) is unioned in so that names which have graduated out of
    the S&P 600 up into the 400 are still scored and still match in the portfolio
    overlay. Duplicates (a ticker appearing on both lists) keep the first.
    """
    sp600 = _scrape_wikipedia_index(config.SP600_WIKI_URL, "S&P 600", 400)
    try:
        sp400 = _scrape_wikipedia_index(config.SP400_WIKI_URL, "S&P 400", 300)
    except Exception as exc:  # noqa: BLE001
        logger.warning("S&P 400 scrape failed (%s); proceeding with S&P 600 only", exc)
        sp400 = pd.DataFrame(columns=["ticker", "company", "gics_sector"])
    combined = pd.concat([sp600, sp400], ignore_index=True)
    combined = combined.drop_duplicates(subset=["ticker"]).reset_index(drop=True)
    logger.info("Combined universe: %d names (S&P 600 + S&P 400)", len(combined))
    return combined


def _seed_store_from_current() -> pd.DataFrame:
    """Scrape current membership, persist it as a today dated interval, warn loudly."""
    try:
        cur = _scrape_current_wikipedia()
    except Exception as exc:  # noqa: BLE001
        if config.SP600_FALLBACK_CSV.exists():
            logger.warning("Wikipedia scrape failed (%s); using bundled fallback list", exc)
            cur = pd.read_csv(config.SP600_FALLBACK_CSV)
            cur["ticker"] = cur["ticker"].map(_normalize_ticker)
        else:
            raise
    cur.to_csv(config.SP600_FALLBACK_CSV, index=False)

    today = pd.Timestamp.utcnow().normalize().tz_localize(None)
    seeded = cur.assign(start_date=today, end_date=pd.NaT, delist_note="")
    _write_membership(seeded[_MEMBERSHIP_COLUMNS])

    logger.warning(
        "\n" + "!" * 78 + "\n"
        "!! SURVIVORSHIP WARNING: no real point in time S&P 600 membership store was\n"
        "!! found. Seeded the store from TODAY's Wikipedia membership only. The panel\n"
        "!! is therefore survivorship biased: pre today cross sections silently use\n"
        "!! today's surviving names. Backtest IC/return numbers before today are\n"
        "!! OPTIMISTIC. Replace data/sp600_membership.csv with a true PIT export\n"
        "!! (S&P Global / CRSP) for clean results.\n"
        + "!" * 78
    )
    return seeded


# =============================================================================
# Public API
# =============================================================================
def members_on(date: pd.Timestamp) -> pd.DataFrame:
    """Return the membership valid on ``date``: ticker, company, gics_sector.

    Uses the real PIT store if present, else a current only snapshot (seeded +
    warned once).
    """
    df = load_membership()
    if df.empty:
        df = _seed_store_from_current()

    date = pd.Timestamp(date).normalize()
    if date.tzinfo is not None:
        date = date.tz_localize(None)

    if not has_real_membership():
        # CURRENT ONLY fallback: we have no idea who was a member historically, so
        # (per the loud survivorship warning) we ASSUME today's members held for
        # every past date. This is survivorship biased on purpose — it is what
        # lets the backtest run at all without a PIT store. Still respect any
        # explicit end_date so a hand added delisting is honored.
        end = df["end_date"].fillna(pd.Timestamp.max.normalize())
        mask = date <= end
    else:
        end = df["end_date"].fillna(pd.Timestamp.max.normalize())
        mask = (df["start_date"] <= date) & (date <= end)
    out = df.loc[mask, ["ticker", "company", "gics_sector"]].drop_duplicates("ticker")
    return out.reset_index(drop=True)


def all_known_tickers() -> pd.DataFrame:
    """Every ticker that was EVER a member (union over all intervals).

    This is the download set: delisted names must be fetched too so the backtest
    can carry them to terminal value. Returns ticker, company, gics_sector
    (sector from the most recent interval).
    """
    df = load_membership()
    if df.empty:
        df = _seed_store_from_current()
    df = df.sort_values("start_date")
    latest = df.groupby("ticker", as_index=False).last()
    return latest[["ticker", "company", "gics_sector"]].reset_index(drop=True)


INDEX_MEMBERSHIP_JSON = config.DATA_DIR / "index_membership.json"


def index_membership_map(force_refresh: bool = False) -> dict[str, str]:
    """Map ticker -> "S&P 600" (SmallCap) or "S&P 400" (MidCap) for the UI flag.

    Scrapes both current constituent lists once and caches the result to
    ``data/index_membership.json``. A name present in both lists is labeled
    "S&P 600" (600 is written last so it wins). Best effort: on a scrape failure
    it returns whatever is cached, else an empty map (the flag simply renders as
    unknown for those tickers).
    """
    import json

    if (not force_refresh and INDEX_MEMBERSHIP_JSON.exists()
            and (time.time() - INDEX_MEMBERSHIP_JSON.stat().st_mtime) < config.CACHE_MAX_AGE_SECONDS):
        try:
            return json.loads(INDEX_MEMBERSHIP_JSON.read_text())
        except Exception:  # noqa: BLE001
            pass

    mapping: dict[str, str] = {}
    for url, label, min_count in [
        (config.SP400_WIKI_URL, "S&P 400", 300),
        (config.SP600_WIKI_URL, "S&P 600", 400),  # written last -> wins ties
    ]:
        try:
            df = _scrape_wikipedia_index(url, label, min_count)
            for t in df["ticker"]:
                mapping[_normalize_ticker(t)] = label
        except Exception as exc:  # noqa: BLE001
            logger.warning("index map: %s scrape failed: %s", label, exc)

    if mapping:
        INDEX_MEMBERSHIP_JSON.write_text(json.dumps(mapping))
    elif INDEX_MEMBERSHIP_JSON.exists():
        try:
            return json.loads(INDEX_MEMBERSHIP_JSON.read_text())
        except Exception:  # noqa: BLE001
            pass
    return mapping


def membership_panel(dates: list[pd.Timestamp]) -> pd.DataFrame:
    """Long frame [date, ticker, company, gics_sector] of who was a member when."""
    frames = []
    for d in dates:
        m = members_on(d)
        m = m.assign(date=pd.Timestamp(d).normalize())
        frames.append(m)
    if not frames:
        return pd.DataFrame(columns=["date", "ticker", "company", "gics_sector"])
    return pd.concat(frames, ignore_index=True)[["date", "ticker", "company", "gics_sector"]]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    today = pd.Timestamp.utcnow().normalize()
    m = members_on(today)
    print(f"Members today: {len(m)}")
    print(m.head())
    print(f"Real PIT store present: {has_real_membership()}")
