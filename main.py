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
import json
import logging
import time

import pandas as pd

import config

logger = logging.getLogger("rsm")


def _load_promotion_state() -> dict:
    """Which model holds the default (hysteresis incumbency); {} if none."""
    try:
        return json.loads(config.PROMOTION_STATE_JSON.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _save_promotion_state(state: dict) -> None:
    try:
        config.PROMOTION_STATE_JSON.write_text(json.dumps(state, indent=1))
    except Exception as exc:  # noqa: BLE001
        logger.warning("promotion state not saved: %s", exc)


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
def build_real_panel(args) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.DataFrame | None]:
    """Return (panel, prices, exclusions, benchmark_px) from live data."""
    from data_loader import (download_prices, download_benchmark, fetch_fundamentals,
                             load_short_interest, load_volumes)
    from feature_engine import build_panel, _rebalance_dates, _fundamental_timeseries
    from universe import all_known_tickers, membership_panel, index_membership_map

    logger.info("=== STEP 1: point in time universe ===")
    uni = all_known_tickers()
    tickers = uni["ticker"].tolist()
    if args.max_tickers:
        tickers = sorted(tickers)[: args.max_tickers]
        logger.info("Subset to %d tickers (--max-tickers)", len(tickers))

    logger.info("=== STEP 2: prices + volume (deep history, %s ->) ===",
                config.PRICE_HISTORY_START)
    prices = download_prices(tickers + [config.BENCHMARK_TICKER], force_refresh=args.refresh)
    prices = prices[[c for c in prices.columns if c != config.BENCHMARK_TICKER]]
    volumes = load_volumes()
    try:
        bench_px = download_benchmark(years=config.PRICE_HISTORY_YEARS,
                                      force_refresh=args.refresh)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Benchmark fetch failed: %s (beta/ivol will be skipped)", exc)
        bench_px = pd.Series(dtype=float)

    logger.info("=== STEP 3: fundamentals (source=%s) + short interest ===", args.source)
    bundles = fetch_fundamentals(tickers, force_refresh=args.refresh)
    short_int = load_short_interest(bundles)

    logger.info("=== STEP 3b: FINRA daily short sale volume (flow, 2018-10 ->) ===")
    short_volume = None
    try:
        from finra_loader import fetch_short_volume
        short_volume = fetch_short_volume(tickers, force_refresh=args.refresh)
    except Exception as exc:  # noqa: BLE001
        logger.warning("FINRA short volume unavailable: %s "
                       "(short activity factors will be NaN this run)", exc)

    logger.info("=== STEP 3c: SEC insider transactions (Form 4 open market flow) ===")
    insider = None
    try:
        from insider_loader import fetch_insider_transactions, map_to_tickers
        insider = map_to_tickers(fetch_insider_transactions(force_refresh=args.refresh),
                                 tickers)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Insider transactions unavailable: %s "
                       "(insider factor will be NaN this run)", exc)

    logger.info("=== STEP 3d: EDGAR earnings event dates (8-K item 2.02) ===")
    earnings_events = None
    try:
        from edgar_loader import fetch_earnings_events
        earnings_events = fetch_earnings_events(tickers, force_refresh=args.refresh)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Earnings events unavailable: %s "
                       "(earnings reaction factor will be NaN this run)", exc)

    fund_override = None
    if args.source == "edgar":
        from edgar_loader import fetch_edgar_fundamentals
        edgar_ts = fetch_edgar_fundamentals(tickers, force_refresh=args.refresh)
        # yfinance fallback for names EDGAR could not serve (missing CIK etc.)
        fund_override = dict(edgar_ts)
        n_fallback = 0
        for tk in tickers:
            if tk in fund_override or tk not in bundles:
                continue
            try:
                ts = _fundamental_timeseries(bundles[tk])
                if not ts.empty:
                    fund_override[tk] = ts
                    n_fallback += 1
            except Exception:  # noqa: BLE001
                continue
        logger.info("Fundamentals: %d EDGAR + %d yfinance fallback tickers",
                    len(edgar_ts), n_fallback)

    logger.info("=== STEP 4: membership panel (%s grid) ===", config.REBALANCE_FREQ)
    r_dates = _rebalance_dates(prices)
    mem = membership_panel(r_dates)
    # Stamp per name index membership (600 vs 400): peer groups, deciles, and
    # the relative label median all separate the two.
    imap = index_membership_map()
    unknown = mem.loc[~mem["ticker"].isin(imap), "ticker"].nunique()
    if unknown:
        logger.warning("membership: %d tickers missing an index label; defaulting to %s",
                       unknown, config.SELECTION_INDEX)
    mem["index_name"] = mem["ticker"].map(imap).fillna(config.SELECTION_INDEX)

    # Optional estimate factors — gated; returns None unless wired + .env set.
    estimate_ts = None
    if config.USE_ESTIMATE_FACTORS:
        from deep_loader import estimate_timeseries, DeepHistoryUnavailable
        try:
            estimate_ts = estimate_timeseries(tickers, r_dates[0], r_dates[-1], source=args.source)
        except (DeepHistoryUnavailable, NotImplementedError) as exc:
            logger.warning("Estimate factors requested but unavailable (%s); dropping them", exc)

    logger.info("=== STEP 5: panel assembly ===")
    panel, exclusions = build_panel(prices, bundles, mem, short_interest=short_int,
                                    estimate_ts=estimate_ts, volumes=volumes,
                                    benchmark_px=bench_px, fund_ts_override=fund_override,
                                    short_volume=short_volume, insider=insider,
                                    earnings_events=earnings_events)
    return panel, prices, exclusions, bench_px, earnings_events


def build_synth_panel(args) -> tuple[pd.DataFrame, None, pd.DataFrame, pd.Series, None]:
    from diagnostics.synth import make_synthetic_panel
    logger.info("=== Synthetic panel (deterministic, no network) ===")
    empty_exclusions = pd.DataFrame(columns=["date", "ticker", "horizon_q", "reason", "value"])
    return make_synthetic_panel(), None, empty_exclusions, pd.Series(dtype=float), None


# =============================================================================
# Pipeline
# =============================================================================
def run(args) -> None:
    t0 = time.time()
    config.USE_LEARNED_WEIGHTS = args.learned_weights or config.USE_LEARNED_WEIGHTS
    horizon = (args.horizon or (f"{args.horizon_q}q" if args.horizon_q else None)
               or config.DEFAULT_HORIZON)

    from feature_engine import neutralize_factors, quarter_end_subset
    from model import (equal_weight_score, learned_weight_score, ic_weighted_score,
                       add_interaction_features, insample_overfit_check)
    from validate import (summarize_ic_for_label, decile_analysis_for_label,
                          calibration_fm,
                          decile_event_study, coverage_eras, ic_summary_by_era,
                          ic_by_year, paired_ic_test, factor_ic_table, compare_models,
                          family_ic_rolling, stress_window_table,
                          horizon_term_structure, factor_zoo_null,
                          ic_by_vol_regime, screen_exposures)
    from backtest import (backtest_long_only_avoid_worst, backtest_hold_all,
                          benchmark_result, relative_metrics,
                          segment_by_year, segment_by_regime)
    from simulate import simulate_ima_portfolios
    from diagnostics.run_all import run_all as run_diagnostics
    import webapp_export
    from universe import has_real_membership

    panel, prices, exclusions, bench_px, earnings_events = (build_synth_panel(args) if args.synthetic
                                           else build_real_panel(args))
    if panel.empty:
        raise SystemExit("Panel is empty: check data sources / universe.")

    if args.since:
        panel = panel[panel["date"] >= pd.Timestamp(args.since)].copy()
        logger.info("Filtered to dates >= %s: %d rows", args.since, len(panel))

    # --- score ---
    logger.info("=== Scoring: sector neutralize -> equal weight composite ===")
    panel = neutralize_factors(panel)
    panel = equal_weight_score(panel)
    logger.info("=== IC weighted family blend (walk forward, realized labels only) ===")
    panel, icw_weights = ic_weighted_score(panel, horizon_q=horizon)
    learned_coefs = pd.DataFrame(columns=["date", "feature", "coef"])
    if config.USE_LEARNED_WEIGHTS:
        logger.info("=== Learned weight model (walk forward, OOS) ===")
        # Tier 2 interactions: pre registered family products, ridge only
        panel = add_interaction_features(panel)
        panel, learned_coefs = learned_weight_score(panel, horizon_q=horizon)

    # Decide the default score HONESTLY: promotion requires the learned model
    # to beat the baseline out of sample by a PAIRED Newey West t test at
    # config.PROMOTION_MIN_T. WITH HYSTERESIS (PM decision 2026-07-14): an
    # incumbent learned default is only demoted when its paired edge actually
    # disappears (t < config.DEMOTION_MIN_T) — see the config note. Judged on
    # the SELECTION universe; the incumbent state persists across runs
    # (synthetic runs never read or write it).
    sel_for_choice = (panel[panel["index_name"] == config.SELECTION_INDEX]
                      if "index_name" in panel.columns else panel)
    comparison = compare_models(sel_for_choice, horizon)
    score_col = "score_ew"
    promotion = None
    if config.USE_LEARNED_WEIGHTS and "score_ml" in panel.columns and panel["score_ml"].notna().any():
        promotion = paired_ic_test(sel_for_choice, "score_ml", "score_ew", horizon)
        was_promoted = False
        if not args.synthetic:
            was_promoted = _load_promotion_state().get("promoted", False)
        t = promotion["t_stat"]
        if was_promoted:
            keep = bool(pd.notna(t) and t >= config.DEMOTION_MIN_T)
            decision = "retained (hysteresis)" if keep else "demoted"
        else:
            keep = bool(promotion["promote"])
            decision = "promoted" if keep else "baseline kept"
        promotion["promote"] = keep
        promotion["decision"] = decision
        promotion["was_promoted"] = was_promoted
        promotion["promotion_min_t"] = config.PROMOTION_MIN_T
        promotion["demotion_min_t"] = config.DEMOTION_MIN_T
        if keep:
            score_col = "score_ml"
        logger.info("Learned model %s (paired IC diff %+.4f, t=%+.2f; bar %.3f, "
                    "demotion floor %.1f, incumbent=%s)",
                    decision.upper(), promotion["mean_diff"], t,
                    config.PROMOTION_MIN_T, config.DEMOTION_MIN_T, was_promoted)
        if not args.synthetic:
            _save_promotion_state({"promoted": keep, "decision": decision,
                                   "paired_t": None if pd.isna(t) else float(t),
                                   "decided_on": str(pd.Timestamp(panel["date"].max()).date())})
    decile_col = "decile_ml" if score_col == "score_ml" else "decile_ew"

    # Roadmap 1.6 diagnostics: where does the transparent IC weighted blend
    # sit between the baseline and the ridge? REPORTING ONLY — the default
    # score decision above stays learned vs baseline until the PM changes it.
    icw_paired = None
    if "score_icw" in panel.columns and panel["score_icw"].notna().any():
        icw_paired = {
            "icw_vs_equal_weight": paired_ic_test(sel_for_choice, "score_icw", "score_ew", horizon),
            "learned_vs_icw": (paired_ic_test(sel_for_choice, "score_ml", "score_icw", horizon)
                               if "score_ml" in panel.columns and panel["score_ml"].notna().any()
                               else None),
        }

    # --- torpedo screener (absolute, whole universe risk view) ---
    logger.info("=== Torpedo screener (absolute whole universe risk) ===")
    from torpedo import compute_torpedo, torpedo_reliability
    panel = compute_torpedo(panel)

    # --- selection universe: every headline statistic describes what IMA
    # actually picks from (the S&P 600). The 400 stays scored for the overlay.
    if "index_name" in panel.columns:
        sel = panel[panel["index_name"] == config.SELECTION_INDEX].copy()
        logger.info("Selection universe (%s): %d of %d panel rows",
                    config.SELECTION_INDEX, len(sel), len(panel))
    else:
        sel = panel
    # traded constructions step on the non overlapping quarter end subset
    sel_q = quarter_end_subset(sel)

    # --- validate (on the selection universe, monthly grid) ---
    logger.info("=== Validation ===")
    # IC + decile blocks at every display horizon (1M/1Q/2Q/4Q toggle on the
    # Validation tab); calibration, event study, and traded sleeves stay at
    # the headline quarterly horizon.
    ic_summaries = {sfx: summarize_ic_for_label(sel, score_col, sfx, months)
                    for sfx, _days, months in config.TERM_STRUCTURE_HORIZONS}
    decile_summaries = {sfx: decile_analysis_for_label(sel, decile_col, sfx, months)
                        for sfx, _days, months in config.TERM_STRUCTURE_HORIZONS}
    factor_ic = factor_ic_table(sel, horizon)
    calibrations = {sfx: calibration_fm(sel, score_col, sfx)
                    for sfx, _d, _m in config.TERM_STRUCTURE_HORIZONS}
    calibration = calibrations[horizon]
    event_study = decile_event_study(quarter_end_subset(sel), decile_col)
    eras = coverage_eras(sel)
    era_ic = ic_summary_by_era(sel, score_col, horizon, eras)
    yearly_ic = ic_by_year(sel, score_col, horizon)
    family_roll = family_ic_rolling(sel, horizon)
    stress = stress_window_table(sel, score_col, decile_col, horizon,
                                 benchmark_px=bench_px)
    # roadmap 1.5: per family IC at 1M/1Q/2Q/4Q — the IC decay curves
    term_structure = horizon_term_structure(sel)
    # roadmap section 3: multiple testing null + regime conditioned IC
    logger.info("=== Factor zoo null distribution (%d draws) ===", config.FACTOR_ZOO_DRAWS)
    zoo = factor_zoo_null(sel, score_col, horizon)
    regime_ic = ic_by_vol_regime(sel, score_col, horizon, bench_px)
    # roadmap section 4: risk accounting lite for the flagged sleeve
    exposures = screen_exposures(sel_q, decile_col)
    # torpedo reliability: absolute damage frequency by torpedo decile
    torp_rel = torpedo_reliability(panel, horizon)
    # overfit evidence: deliberate in sample ceiling vs the OOS numbers
    overfit = insample_overfit_check(panel, horizon) if config.USE_LEARNED_WEIGHTS else {}

    # --- backtest (quarter end subset of the selection universe) ---
    logger.info("=== Backtest ===")
    hold_all = backtest_hold_all(sel_q, decile_col, bench_px, cost_bps=args.cost_bps)
    avoid = backtest_long_only_avoid_worst(sel_q, decile_col, bench_px, cost_bps=args.cost_bps)
    # The screen's value added is avoid-worst MINUS hold-all (equal weight vs
    # equal weight); IJR is context, never the yardstick for the screen.
    avoid.metrics.update(relative_metrics(avoid, hold_all))
    dates_q = sorted(sel_q["date"].unique())
    bench = benchmark_result(bench_px, dates_q)
    sleeves = {"hold_all": hold_all, "avoid_worst": avoid}
    seg_year = segment_by_year({**sleeves, "benchmark": bench})
    seg_regime = segment_by_regime(sleeves, bench.returns)

    # --- IMA Monte Carlo (random 20 name portfolios FROM THE S&P 600) ---
    logger.info("=== IMA Monte Carlo simulation (20 name portfolios per screen tier) ===")
    mc = simulate_ima_portfolios(sel_q, decile_col)

    # --- analyst overrides (annotations; never touch the score) ---
    from overrides import load_overrides, active_overrides, score_overrides
    overrides = load_overrides()
    latest_dt = panel["date"].max()
    ov_active = active_overrides(overrides, latest_dt)
    ov_scoreboard = score_overrides(overrides, panel)

    # --- diagnostics gate (placebo runs on the DEFAULT scorer) ---
    logger.info("=== Diagnostics ===")
    diag = run_diagnostics(panel=panel, prices=prices, score_col=score_col,
                           horizon=horizon)

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
            family_roll=family_roll, stress=stress, term_structure=term_structure,
            icw_weights=icw_weights, icw_paired=icw_paired,
            factor_zoo=zoo, regime_ic=regime_ic, exposures=exposures,
            earnings_events=earnings_events, calibrations=calibrations,
            learned_coefs=learned_coefs, overfit=overfit, torp_rel=torp_rel,
            prices=prices, benchmark_px=bench_px,
            backtests={"hold_all": hold_all, "avoid_worst": avoid, "benchmark": bench},
            seg_year=seg_year, seg_regime=seg_regime, mc=mc, exclusions=exclusions,
            ov_active=ov_active, ov_scoreboard=ov_scoreboard,
            meta_kwargs=dict(
                universe_size=int(latest["ticker"].nunique()),
                n_sectors=int(latest["gics_sector"].nunique()),
                horizon=horizon, source=("synthetic" if args.synthetic else args.source),
                learned_enabled=config.USE_LEARNED_WEIGHTS, default_score=score_col,
                membership_is_pit=(False if args.synthetic else has_real_membership()),
                diagnostics=diag, n_cross_sections=int(panel["date"].nunique()),
                rebalance_freq=config.REBALANCE_FREQ,
                selection_index=config.SELECTION_INDEX,
                n_selection=int(sel[sel["date"] == latest_date]["ticker"].nunique()) if len(sel) else 0,
                n_quarterly_cross_sections=int(sel_q["date"].nunique()),
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
                   exclusions, diag, horizon, time.time() - t0,
                   term_structure=term_structure, icw_paired=icw_paired,
                   promotion=promotion, zoo=zoo, regime_ic=regime_ic)


# =============================================================================
# Terminal summary
# =============================================================================
def _print_summary(panel, score_col, decile_col, latest, latest_date, ic_summaries,
                   decile_summaries, comparison, era_ic, hold_all, avoid, bench, mc,
                   exclusions, diag, horizon, secs, term_structure=None,
                   icw_paired=None, promotion=None, zoo=None, regime_ic=None) -> None:
    line = "=" * 76
    print(f"\n{line}\nRELATIVE SELL MODEL: sector neutral relative underperformance ranking")
    print(f"{line}")
    print(f"Universe: {latest['ticker'].nunique()} names, {latest['gics_sector'].nunique()} sectors "
          f"| {panel['date'].nunique()} cross sections ({config.REBALANCE_FREQ}) | default score = {score_col}")
    print(f"Latest cross section: {pd.Timestamp(latest_date).date()}  "
          f"(headline horizon = {str(horizon).upper()} forward relative return; "
          f"traded sleeves rebalance quarterly)")
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
    if icw_paired:
        a = icw_paired.get("icw_vs_equal_weight")
        b = icw_paired.get("learned_vs_icw")
        if a:
            print(f"  paired: ic_weighted vs equal_weight  diff={a['mean_diff']:+.4f} t={a['t_stat']:+.2f}")
        if b:
            print(f"  paired: learned vs ic_weighted       diff={b['mean_diff']:+.4f} t={b['t_stat']:+.2f}")
    if promotion:
        print(f"  default decision: {promotion.get('decision', '?')} "
              f"(paired t={promotion['t_stat']:+.2f}; promote at >= {promotion.get('promotion_min_t', 1.645):.3f}, "
              f"demote below {promotion.get('demotion_min_t', 0.0):.1f}; incumbent={promotion.get('was_promoted')})")
    if zoo and zoo.get("n_draws"):
        print(f"  factor zoo null: real IC {zoo['real_ic']:+.4f} vs null mean {zoo['null_mean']:+.4f} "
              f"(p95 {zoo['null_p95']:+.4f}) over {zoo['n_draws']} draws -> p={zoo['p_value']:.2f}")
    if regime_ic is not None and not regime_ic.empty:
        cells = "  ".join(f"{r['regime']}: {r['mean_ic']:+.3f} (t{r['t_stat']:+.1f})"
                          for _, r in regime_ic.iterrows())
        print(f"  IC by volatility regime: {cells}")

    if term_structure is not None and not term_structure.empty:
        present = set(term_structure["horizon"])
        horizons = [s.upper() for s, _d, _m in config.TERM_STRUCTURE_HORIZONS
                    if s.upper() in present]
        print(f"\nHORIZON TERM STRUCTURE  (IC by label horizon; read shapes, not stars)")
        print("  " + f"{'':<26}" + "".join(f"{h:>16}" for h in horizons))
        sub = term_structure[term_structure["kind"].isin(["composite", "family"])]
        for name in sub["series"].unique():
            g = sub[sub["series"] == name].set_index("horizon")
            cells = ""
            for h in horizons:
                if h in g.index:
                    r = g.loc[h]
                    cells += f"{r['mean_ic']:+.3f} (t{r['t_stat']:+.1f})".rjust(16)
                else:
                    cells += " " * 16
            print(f"  {name:<26}{cells}")

    print(f"\nBACKTEST  (quarterly rebalance, equal weight; screen judged vs hold all, IJR = context)")
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
    p.add_argument("--horizon", type=str, default=None,
                   choices=[sfx for sfx, _d, _m in config.TERM_STRUCTURE_HORIZONS],
                   help="headline label horizon the WHOLE model runs at "
                        f"(learned fit, promotion, calibration; default {config.DEFAULT_HORIZON})")
    p.add_argument("--horizon-q", type=int, default=None, choices=list(config.HORIZONS_Q),
                   dest="horizon_q", help="legacy alias: horizon in quarters (1 or 2)")
    p.add_argument("--cost-bps", type=float, default=config.COST_BPS, dest="cost_bps",
                   help="round trip transaction cost per unit turnover (bps)")
    p.add_argument("--learned-weights", action="store_true", dest="learned_weights",
                   help="also fit the walk forward learned weight model")
    p.add_argument("--max-tickers", type=int, default=None, dest="max_tickers",
                   help="cap universe size for a fast run")
    p.add_argument("--source", type=str, default=config.DEEP_HISTORY_SOURCE,
                   choices=["edgar", "yfinance", "factset", "spglobal"],
                   help="fundamentals source (edgar = free SEC XBRL, no key needed)")
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
