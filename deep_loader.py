"""OPTIONAL deep history / estimate revision loader (FactSet / S&P Global).

This is the upgrade path past yfinance's ~4 5 quarters of fundamentals and its
complete lack of analyst estimates. It is GATED: nothing here runs unless you
both (a) set ``config.USE_ESTIMATE_FACTORS = True`` / pass ``--source factset``
and (b) provide credentials in ``.env``. yfinance must NEVER be used to
back fill these — estimate revisions / SUE faked from price data would be a lie,
so when credentials are absent we return ``None`` and the model simply drops the
estimate factors from the cross section.

Mirrors IMA PCA's loader style: thin connector, cached parquet, explicit env
gate. The two providers expose the same shape to the rest of the pipeline:

    point_in_time_fundamentals(tickers, start, end) -> dict[ticker, DataFrame]
        DataFrame indexed by as of date with the same columns the yfinance path
        produces in feature_engine._fundamental_timeseries (so it is a drop in
        replacement, only deeper and truly point in time).

    estimate_timeseries(tickers, start, end) -> dict[ticker, DataFrame]
        DataFrame indexed by as of date with columns config.ESTIMATE_FACTORS
        (est_revision_3m, sue).

Implement the two ``_fetch_*`` helpers against your connector and the rest of the
pipeline picks the data up automatically.
"""

from __future__ import annotations

import logging

import pandas as pd

import config

logger = logging.getLogger(__name__)


class DeepHistoryUnavailable(RuntimeError):
    """Raised when a deep history source is requested but not configured."""


def _require(source: str) -> None:
    if source == "factset" and not config.FACTSET_API_KEY:
        raise DeepHistoryUnavailable(
            "source=factset requested but FACTSET_API_KEY is unset. Add it to .env "
            "(see .env.example) or fall back to --source yfinance."
        )
    if source == "spglobal" and not config.SPGLOBAL_API_KEY:
        raise DeepHistoryUnavailable(
            "source=spglobal requested but SPGLOBAL_API_KEY is unset. Add it to .env "
            "(see .env.example) or fall back to --source yfinance."
        )


def estimate_timeseries(
    tickers: list[str], start: pd.Timestamp, end: pd.Timestamp,
    source: str | None = None,
) -> dict[str, pd.DataFrame] | None:
    """Per ticker estimate revision / SUE time series, or ``None`` if ungated.

    Returns ``None`` (not faked data) whenever estimate factors are disabled or
    the source is unconfigured — the model then drops the estimate factors.
    """
    source = source or config.DEEP_HISTORY_SOURCE
    if not config.USE_ESTIMATE_FACTORS or source == "yfinance":
        logger.info("Estimate factors gated off (use_estimate_factors=%s, source=%s); "
                    "skipping — they will be dropped from the cross section",
                    config.USE_ESTIMATE_FACTORS, source)
        return None
    _require(source)
    # Real implementation goes here, against your FactSet / S&P Global connector.
    return _fetch_estimates(tickers, start, end, source)


def point_in_time_fundamentals(
    tickers: list[str], start: pd.Timestamp, end: pd.Timestamp,
    source: str | None = None,
) -> dict[str, pd.DataFrame] | None:
    source = source or config.DEEP_HISTORY_SOURCE
    if source == "yfinance":
        return None  # the yfinance path in data_loader/feature_engine handles this
    _require(source)
    return _fetch_pit_fundamentals(tickers, start, end, source)


# --- connector stubs: implement against your S&P Global / FactSet client -----
def _fetch_estimates(tickers, start, end, source) -> dict[str, pd.DataFrame]:
    raise NotImplementedError(
        f"Wire up the {source} estimates connector here. Return "
        "{ticker: DataFrame(index=as_of_date, columns=['est_revision_3m', 'sue'])}."
    )


def _fetch_pit_fundamentals(tickers, start, end, source) -> dict[str, pd.DataFrame]:
    raise NotImplementedError(
        f"Wire up the {source} point in time fundamentals connector here. Return the "
        "same column shape as feature_engine._fundamental_timeseries."
    )
