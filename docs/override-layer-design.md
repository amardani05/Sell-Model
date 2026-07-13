# Analyst Override Layer — design document

**Status: BUILT (approved 2026-07-12).** Implementation: `overrides.py` (load /
validate / quarterly scoring), `data/overrides.csv` (the append-only log, with the
schema documented in its header), the "Analyst view" block + row-drafting form in the
per-name drill down, ⚑ markers in the portfolio overlay, and the scoreboard card on
the Validation tab. The dashboard is static, so filing = appending the drafted CSV row
to `data/overrides.csv` and re-running `python main.py`. This document remains the
rationale and the spec.

---

## The problem

Piper-style quantitative sell models are pure red-flag counters. IMA analysts,
though, sometimes *know things the factors cannot see*: a pending acquisition, an
accrual spike caused by a divestiture, a new contract that hasn't hit the
statements yet. The obvious ask — "let analysts adjust the score" — is also the
dangerous one, for two reasons:

1. **The evidence is against blended judgment.** The clinical-vs-actuarial
   literature (Meehl, *Clinical versus Statistical Prediction*, 1954; Grove &
   Meehl, 2000 — a meta-analysis of 136 studies) consistently finds that simple
   mechanical models match or beat expert judgment, and that *experts adjusting a
   model's output* usually degrade it. The exception Meehl himself allowed is the
   **"broken-leg case"**: the model doesn't know the subject broke a leg, so the
   human should overrule it — *when they genuinely have information outside the
   model's inputs*. The design problem is separating broken-leg overrides from
   mood-based ones.
2. **The echo chamber.** If analyst views feed the score and the score feeds
   analyst views, the model stops being an independent check and becomes a
   mirror. Its entire value to IMA — a disagreeing voice that must be answered —
   evaporates.

## Design principles

1. **The quantitative score is immutable.** No override ever changes the score,
   the decile, or anything downstream (validation, backtests, simulations). The
   model's track record must remain the track record of *the model*.
2. **Overrides are annotations, displayed side by side.** "Model: decile 9.
   Analyst: risk downgraded — accrual flag reflects divestiture accounting
   (J. Smith, 2026-07-12)."
3. **Every override is structured, attributed, and dated** — so it can be scored.
4. **Overrides are scored quarterly.** The whole payoff of the layer: after each
   quarter, did the overridden name behave like the model said or like the
   analyst said? Publish both hit rates. If analysts systematically beat the
   model on overrides, that is a genuinely valuable discovery (and license to
   trust them more). If not, that is worth knowing before anyone's grade or P&L
   depends on it.

## Data model

One append-only file (or table), `data/overrides.csv`:

| field | example | notes |
|---|---|---|
| `date` | 2026-07-12 | when the override was filed |
| `ticker` | UNFI | |
| `analyst` | jsmith | attribution is non-negotiable |
| `direction` | `less_risky` \| `more_risky` | which way the analyst disagrees |
| `reason_code` | `corporate_action` | from the controlled list below |
| `factor` | `accruals_ocf_ni` | optional: the specific factor being disputed |
| `note` | "OCF/NI distorted by the Q1 divestiture; cash conversion normal ex-item" | free text, one or two sentences |
| `expires` | 2026-12-31 | overrides decay; stale judgment is not judgment |

**Reason codes** (controlled vocabulary — the difference between an override log
you can score and a comment box):

- `corporate_action` — pending M&A, spin, tender, special dividend
- `accounting_artifact` — the factor input is real but economically misleading
  (divestiture accruals, one-time charge, biotech pre-revenue P/S)
- `data_error` — the underlying data is wrong (report it upstream too)
- `new_information` — post-statement contract win/loss, guidance, litigation
- `structural_peer_mismatch` — the sector peer group is unfair (e.g. a grocery
  distributor z-scored against branded CPG margins — the UNFI case)
- `thesis_disagreement` — the analyst simply disagrees. Allowed, but tracked
  separately: this is the bucket the literature says will underperform, and the
  quarterly scoring will show whose priors are right.

## UI

- In the per-name drill-down: an "Analyst view" block under the risks-section
  draft. Shows active overrides (direction, reason, analyst, note, age) and an
  "Add override" form (the six fields above; no free-form score editing).
- In the portfolio overlay: an ⚑ marker on rows with an active override, with
  hover detail. The decile pill never changes.
- A "Overrides scoreboard" card on the Validation tab, per quarter:
  - N overrides expired this quarter
  - Analyst hit rate: fraction where the subsequent sector-relative return sided
    with the analyst's direction
  - Model hit rate on the same names
  - Split by reason code (expect `corporate_action` and `data_error` to score
    well; expect `thesis_disagreement` to be the honest embarrassment)

## Echo-chamber safeguards

1. Immutable score (principle 1) — the model never learns from overrides.
2. Overrides expire (default: two quarters) — no permanent whitelists.
3. Reason codes force the analyst to state *what the model can't see*, which is
   Kahneman's broken-leg test in form-field shape.
4. The scoreboard is public inside IMA. Overrides are cheap to file and
   expensive to be wrong about, which is the correct incentive.
5. No factor-weight sliders. Re-weighting factors interactively is re-fitting
   the model by vibes; if sensitivity views are ever wanted, ship fixed,
   clearly-labeled presets ("value-tilted lens") that never persist and never
   replace the default score.

## What we deliberately did NOT design

- **Bayesian blending of analyst priors into the score.** Elegant on paper,
  ruinous to auditability: once blended, nobody can say what the model alone
  believed, and the quarterly scoreboard becomes impossible.
- **Anonymous overrides.** Attribution is the mechanism that keeps the layer
  honest.

## Reading list (for the IMA presentation)

- Meehl (1954), *Clinical versus Statistical Prediction* — the original case.
- Grove & Meehl (2000), "Comparative efficiency of informal and formal
  prediction procedures" — the 136-study meta-analysis.
- Kahneman, *Thinking, Fast and Slow*, ch. 21 ("Intuitions vs. Formulas") — the
  broken-leg exception and why simple equal-weight models are hard to beat
  (which is also why this repo's baseline is equal-weight).
- Grinold & Kahn, *Active Portfolio Management*, ch. 10 — combining information
  sources formally, if IMA ever wants the blended-signal version done right.

## Implementation estimate

Small: one CSV, one export hook, two UI blocks, one scoreboard computation that
reuses `fwd_rel_ret_1q`. The design is the hard part; it is above. Approve or
amend, and the build is a short follow-up.
