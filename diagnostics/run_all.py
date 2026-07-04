"""Run the full diagnostics suite and write a summary.

By default runs on the synthetic panel (deterministic, no network), proving the
machinery: placebo IC collapses, look ahead truncation invariance holds, and the
delisting/survivorship guard carries dead names. ``main.py`` re runs these on the
REAL panel as an acceptance gate.

    python -m diagnostics.run_all
"""

from __future__ import annotations

import json
import logging

import config
from feature_engine import neutralize_factors
from model import equal_weight_score
from diagnostics.synth import make_synthetic_panel
from diagnostics.placebo import run_placebo
from diagnostics.lookahead_assert import run_lookahead
from diagnostics.survivorship_assert import run_survivorship

logger = logging.getLogger("diagnostics")


def run_all(panel=None, prices=None) -> dict:
    if panel is None:
        logger.info("No panel supplied; building synthetic panel for diagnostics")
        raw = make_synthetic_panel()
        panel = equal_weight_score(neutralize_factors(raw))

    results = {
        "placebo": run_placebo(panel, "score_ew"),
        "lookahead": run_lookahead(prices, panel),
        "survivorship": run_survivorship(),
    }
    results["all_passed"] = all(r.get("passed") for r in results.values())

    out = config.OUTPUT_DIR / "diagnostics_summary.json"
    out.write_text(json.dumps(results, indent=2, default=str))
    logger.info("Diagnostics %s -> %s",
                "ALL PASS" if results["all_passed"] else "FAILURES PRESENT", out)
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    res = run_all()
    print(json.dumps(res, indent=2, default=str))
    assert res["all_passed"], "Diagnostics failed"
