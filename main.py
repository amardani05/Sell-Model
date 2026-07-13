"""Relative Sell Model orchestrator.

Pipeline:
  1. Point in time S&P 600 universe (every name that was ever a member).
  2. Deep price history + shallow yfinance fundamentals + short interest.
  3. Build the panel: sector relative factors at each quarterly cross section +
     delisting aware forward RELATIVE returns.
  4. Sector neutralize every factor; equal weight composite -> sector neutral
     deciles. Optionally fit a walk forward learned weight model (OOS).
  5. Validate: Fama MacBeth IC (Newey West t), decile spread + monotonicity,
     calibration, baseline versus learned comparison.
  6. Backtest: long only avoid worst decile vs IJR + sector neutral long/short.
  7. Diagnostics gate: placebo, look ahead, survivorship.
  8. Export every table to webapp/public for the dashboard.

CLI (flag names keep their hyphens; they are the interface):
  python main.py [--synthetic] [--since YYYY MM DD] [--horizon-q {1,2}]
                 [--cost-bps N] [--learned-weights] [--max-tickers N]
                 [--source {yfinance,factset,spglobal}] [--refresh] [--no-webapp]
"""

from __future__ import annotations

import argparse
import logging
import time

import pandas as pd

import config

logger = logging.getLogger("rsm")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S",
    )
    for noisy in ("yfinance", "urllib3", "peewee", "matplotlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# =============================================================================
# Panel construction
# =============================================================================
def build_real_panel(args) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (panel, prices, exclusions) from live data."""
    from data_loader import download_prices, fetch_fundamentals, load_short_interest
    from feature_engine import build_panel, _quarter_end_dates
    from universe import all_known_tickers, membership_panel

    logger.info("=== STEP 1: point in time universe ===")
    uni = all_known_tickers()
    tickers = uni["ticker"].tolist()
    if args.max_tickers:
        tickers = sorted(tickers)[: args.max_tickers]
        logger.info("Subset to %d tickers (--max-tickers)", len(tickers))

    logger.info("=== STEP 2: prices (deep history) ===")
    prices = download_prices(tickers + [config.BENCHMARK_TICKER],
                             years=config.PRICE_HISTORY_YEARS, force_refresh=args.refresh)
    prices = prices[[c for c in prices.columns if c != config.BENCHMARK_TICKER]]

    logger.info("=== STEP 3: fundamentals + short interest ===")
    bundles = fetch_fundamentals(tickers, force_refresh=args.refresh)
    short_int = load_short_interest(bundles)

    logger.info("=== STEP 4: membership panel ===")
    q_dates = _quarter_end_dates(prices)
    mem = membership_panel(q_dates)

    # Optional estimate factors — gated; returns None unless wired + .env set.
    estimate_ts = None
    if config.USE_ESTIMATE_FACTORS:
        from deep_loader import estimate_timeseries, DeepHistoryUnavailable
        try:
            estimate_ts = estimate_timeseries(tickers, q_dates[0], q_dates[-1], source=args.source)
        except (DeepHistoryUnavailable, NotImplementedError) as exc:
            logger.warning("Estimate factors requested but unavailable (%s); dropping them", exc)

    logger.info("=== STEP 5: panel assembly ===")
    panel, exclusions = build_panel(prices, bundles, mem, short_interest=short_int,
                                    estimate_ts=estimate_ts)
    return panel, prices, exclusions


def build_synth_panel(args) -> tuple[pd.DataFrame, None, pd.DataFrame]:
    from diagnostics.synth import make_synthetic_panel
    logger.info("=== Synthetic panel (deterministic, no network) ===")
    empty_exclusions = pd.DataFrame(columns=["date", "ticker", "horizon_q", "reason", "value"])
    return make_synthetic_panel(), None, empty_exclusions


# =============================================================================
# Pipeline
# =============================================================================
def run(args) -> None:
    t0 = time.time()
    config.USE_LEARNED_WEIGHTS = args.learned_weights or config.USE_LEARNED_WEIGHTS
    horizon = args.horizon_q

    from feature_engine import neutralize_factors
    from model import equal_weight_score, learned_weight_score
    from validate import (summarize_ic, decile_analysis, calibration_fm,
                          decile_event_study, coverage_eras, ic_summary_by_era,
                          ic_by_year, paired_ic_test, factor_ic_table, compare_models)
    from backtest import (backtest_long_only_avoid_worst, backtest_hold_all,
                          benchmark_result, relative_metrics,
                          segment_by_year, segment_by_regime)
    from simulate import simulate_ima_portfolios
    from diagnostics.run_all import run_all as run_diagnostics
    import webapp_export
    from universe import has_real_membership

    panel, prices, exclusions = (build_synth_panel(args) if args.synthetic
                                 else build_real_panel(args))
    if panel.empty:
        raise SystemExit("Panel is empty — check data sources / universe.")

    if args.since:
        panel = panel[panel["date"] >= pd.Timestamp(args.since)].copy()
        logger.info("Filtered to dates >= %s: %d rows", args.since, len(panel))

    # --- score ---
    logger.info("=== Scoring: sector neutralize -> equal weight composite ===")
    panel = neutralize_factors(panel)
    panel = equal_weight_score(panel)
    if config.USE_LEARNED_WEIGHTS:
        logger.info("=== Learned weight model (walk forward, OOS) ===")
        panel = learned_weight_score(panel, horizon_q=horizon)

    # Decide the default score HONESTLY: the equal weight baseline stays the
    # default unless the learned model beats it out of sample by a PAIRED
    # Newey West t test (a point estimate edge is noise, not a win).
    comparison = compare_models(panel, horizon)
    score_col = "score_ew"
    promotion = None
    if config.USE_LEARNED_WEIGHTS and "score_ml" in panel.columns and panel["score_ml"].notna().any():
        promotion = paired_ic_test(panel, "score_ml", "score_ew", horizon)
        if promotion["promote"]:
            score_col = "score_ml"
            logger.info("Learned model PROMOTED (paired IC diff %+.4f, t=%+.2f >= %.1f)",
                        promotion["mean_diff"], promotion["t_stat"], config.PROMOTION_MIN_T)
        else:
            logger.info("Learned model NOT promoted (paired IC diff %+.4f, t=%+.2f < %.1f): baseline stays default",
                        promotion["mean_diff"], promotion["t_stat"], config.PROMOTION_MIN_T)
    decile_col = "decile_ml" if score_col == "score_ml" else "decile_ew"

    # --- torpedo screener (absolute, whole universe risk view) ---
    logger.info("=== Torpedo screener (absolute whole universe risk) ===")
    from torpedo import compute_torpedo
    panel = compute_torpedo(panel)

    # --- validate ---
    logger.info("=== Validation ===")
    ic_summaries = {h: summarize_ic(panel, score_col, h) for h in config.HORIZONS_Q}
    decile_summaries = {h: decile_analysis(panel, decile_col, h) for h in config.HORIZONS_Q}
    factor_ic = factor_ic_table(panel, horizon)
    calibration = calibration_fm(panel, score_col, horizon)
    event_study = decile_event_study(panel, decile_col)
    eras = coverage_eras(panel)
    era_ic = ic_summary_by_era(panel, score_col, horizon, eras)
    yearly_ic = ic_by_year(panel, score_col, horizon)

    # --- backtest ---
    logger.info("=== Backtest ===")
    bench_px = None
    if not args.synthetic:
        from data_loader import download_benchmark
        try:
            bench_px = download_benchmark(years=config.PRICE_HISTORY_YEARS, force_refresh=args.refresh)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Benchmark fetch failed: %s", exc)
    bench_px = bench_px if bench_px is not None else pd.Series(dtype=float)
    hold_all = backtest_hold_all(panel, decile_col, bench_px, cost_bps=args.cost_bps)
    avoid = backtest_long_only_avoid_worst(panel, decile_col, bench_px, cost_bps=args.cost_bps)
    # The screen's value added is avoid-worst MINUS hold-all (equal weight vs
    # equal weight); IJR is context, never the yardstick for the screen.
    avoid.metrics.update(relative_metrics(avoid, hold_all))
    dates_all = sorted(panel["date"].unique())
    bench = benchmark_result(bench_px, dates_all)
    sleeves = {"hold_all": hold_all, "avoid_worst": avoid}
    seg_year = segment_by_year({**sleeves, "benchmark": bench})
    seg_regime = segment_by_regime(sleeves, bench.returns)

    # --- IMA Monte Carlo (replaces the long/short sleeve) ---
    logger.info("=== IMA Monte Carlo simulation (20 name portfolios per screen tier) ===")
    mc = simulate_ima_portfolios(panel, decile_col)

    # --- analyst overrides (annotations; never touch the score) ---
    from overrides import load_overrides, active_overrides, score_overrides
    overrides = load_overrides()
    latest_dt = panel["date"].max()
    ov_active = active_overrides(overrides, latest_dt)
    ov_scoreboard = score_overrides(overrides, panel)

    # --- diagnostics gate ---
    logger.info("=== Diagnostics ===")
    diag = run_diagnostics(panel=panel, prices=prices)

    # --- export ---
    latest_date = panel["date"].max()
    latest = panel[panel["date"] == latest_date].copy()
    if not args.no_webapp:
        logger.info("=== Webapp export ===")
        webapp_export.export_all(
            panel=panel, latest=latest, score_col=score_col, decile_col=decile_col,
            factor_ic=factor_ic, horizon_q=horizon,
            ic_summaries=ic_summaries, decile_summaries=decile_summaries,
            calibration=calibration, comparison=comparison, promotion=promotion,
            event_study=event_study, eras=eras, era_ic=era_ic, yearly_ic=yearly_ic,
            backtests={"hold_all": hold_all, "avoid_worst": avoid, "benchmark": bench},
            seg_year=seg_year, seg_regime=seg_regime, mc=mc, exclusions=exclusions,
            ov_active=ov_active, ov_scoreboard=ov_scoreboard,
            meta_kwargs=dict(
                universe_size=int(latest["ticker"].nunique()),
                n_sectors=int(latest["gics_sector"].nunique()),
                horizon_q=horizon, source=("synthetic" if args.synthetic else config.DEEP_HISTORY_SOURCE),
                learned_enabled=config.USE_LEARNED_WEIGHTS, default_score=score_col,
                membership_is_pit=(False if args.synthetic else has_real_membership()),
                diagnostics=diag, n_cross_sections=int(panel["date"].nunique()),
                cost_bps=args.cost_bps, panel_rows=int(len(panel)),
                n_delisted=int(panel["delisted"].sum()) if "delisted" in panel else 0,
                exclusions_summary={
                    "n_labels_excluded": int(len(exclusions)),
                    "n_tickers": int(exclusions["ticker"].nunique()) if len(exclusions) else 0,
                    "reasons": exclusions["reason"].value_counts().to_dict() if len(exclusions) else {},
                },
            ),
        )

    _print_summary(panel, score_col, decile_col, latest, latest_date, ic_summaries,
                   decile_summaries, comparison, era_ic, hold_all, avoid, bench, mc,
                   exclusions, diag, horizon, time.time() - t0)


# =============================================================================
# Terminal summary
# =============================================================================
def _print_summary(panel, score_col, decile_col, latest, latest_date, ic_summaries,
                   decile_summaries, comparison, era_ic, hold_all, avoid, bench, mc,
                   exclusions, diag, horizon, secs) -> None:
    line = "=" * 76
    print(f"\n{line}\nRELATIVE SELL MODEL — sector neutral relative underperformance ranking")
    print(f"{line}")
    print(f"Universe: {latest['ticker'].nunique()} names, {latest['gics_sector'].nunique()} sectors "
          f"| {panel['date'].nunique()} quarterly cross sections | default score = {score_col}")
    print(f"Latest cross section: {pd.Timestamp(latest_date).date()}  (horizon = {horizon}Q forward relative return)")
    if len(exclusions):
        print(f"DATA INTEGRITY: {len(exclusions)} forward return labels EXCLUDED "
              f"({exclusions['ticker'].nunique()} tickers; splice/extreme gate)")
    print()

    s = ic_summaries[horizon]
    print(f"VALIDATION  (sector neutral IC, Fama MacBeth + Newey West h-1 lag)")
    print(f"  mean IC = {s.mean_ic:+.4f}   t = {s.t_stat:+.2f}   IR = {s.ir:+.2f}   "
          f"hit = {s.hit_rate*100:.0f}%   over {s.n_periods} periods")
    if era_ic is not None and not era_ic.empty:
        for _, r in era_ic.iterrows():
            print(f"    {r['era']:<14} IC={r['mean_ic']:+.4f} t={r['t_stat']:+.2f} over {r['n_periods']} qtrs")
    d = decile_summaries[horizon]
    print(f"  decile spread (best worst) = {d.spread_mean:+.4f}  t = {d.spread_tstat:+.2f}  "
          f"monotonicity rho = {d.monotonicity_rho:+.2f}")
    if not comparison.empty:
        print("  model comparison (OOS IC):")
        for _, r in comparison.iterrows():
            print(f"    {r['model']:<16} IC={r['mean_ic']:+.4f} t={r['t_stat']:+.2f} IR={r['ir']:+.2f}")

    print(f"\nBACKTEST  (quarterly rebalance, equal weight; screen judged vs hold-all, IJR = context)")
    for res in (hold_all, avoid, bench):
        m = res.metrics
        if not m:
            continue
        print(f"  {res.name:<36} CAGR={m.get('cagr', float('nan'))*100:+.1f}%  "
              f"Sharpe={m.get('sharpe', float('nan')):+.2f}  maxDD={m.get('max_drawdown', float('nan'))*100:.1f}%")
    x = avoid.metrics.get("excess_cagr_vs_base")
    if x is not None:
        print(f"  screen value added (avoid worst − hold all): {x*100:+.2f}%/yr  "
              f"IR={avoid.metrics.get('ir_vs_base', float('nan')):+.2f}  "
              f"hit={avoid.metrics.get('hit_rate_vs_base', float('nan'))*100:.0f}%")

    if mc and mc.get("tiers"):
        print(f"\nIMA MONTE CARLO  ({mc['n_trials']} random {mc['n_names']} name portfolios per tier)")
        for tier, t in mc["tiers"].items():
            c = t["cagr"]
            pb = t.get("prob_beat_full_median")
            print(f"  {t['label']:<32} median CAGR={c['p50']*100:+.1f}%  "
                  f"[p5 {c['p5']*100:+.1f}%, p95 {c['p95']*100:+.1f}%]"
                  + (f"  P(beat unscreened median)={pb*100:.0f}%" if pb is not None else ""))

    print(f"\nDIAGNOSTICS: {'ALL PASS' if diag['all_passed'] else 'FAILURES PRESENT'}  "
          f"(placebo IC={diag['placebo']['placebo_ic_mean']:+.3f} vs real {diag['placebo']['real_ic']:+.3f})")

    print(f"\nTOP 10 SELL CANDIDATES (worst sector neutral decile, latest cross section):")
    worst = latest[latest[decile_col] == config.N_DECILES].sort_values(score_col, ascending=False)
    for _, r in worst.head(10).iterrows():
        print(f"  {r['ticker']:<7} {r['gics_sector']:<24} score={r[score_col]:+.3f} decile={int(r[decile_col])}")
    print(f"\nDone in {secs:.1f}s.\n{line}")


# =============================================================================
# CLI
# =============================================================================
def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Relative Sell Model pipeline")
    p.add_argument("--synthetic", action="store_true",
                   help="run on a deterministic synthetic panel (no network)")
    p.add_argument("--since", type=str, default=None, help="only score dates >= YYYY MM DD")
    p.add_argument("--horizon-q", type=int, default=config.DEFAULT_HORIZON_Q, choices=list(config.HORIZONS_Q),
                   dest="horizon_q", help="forward horizon in quarters for headline metrics")
    p.add_argument("--cost-bps", type=float, default=config.COST_BPS, dest="cost_bps",
                   help="round trip transaction cost per unit turnover (bps)")
    p.add_argument("--learned-weights", action="store_true", dest="learned_weights",
                   help="also fit the walk forward learned weight model")
    p.add_argument("--max-tickers", type=int, default=None, dest="max_tickers",
                   help="cap universe size for a fast run")
    p.add_argument("--source", type=str, default=config.DEEP_HISTORY_SOURCE,
                   choices=["yfinance", "factset", "spglobal"], help="fundamentals source")
    p.add_argument("--refresh", action="store_true", help="ignore caches and re download")
    p.add_argument("--no-webapp", action="store_true", dest="no_webapp",
                   help="skip webapp JSON export")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    _setup_logging(args.verbose)
    config.DEEP_HISTORY_SOURCE = args.source
    run(args)
