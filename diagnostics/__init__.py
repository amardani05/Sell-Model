"""Diagnostics: placebo IC, look ahead assertion, survivorship assertion.

These guard the three ways a cross sectional return model silently lies:
  * a score that isn't really predictive (placebo) — shuffle it, IC must die;
  * a feature that peeks at the future (look ahead) — truncation must not move it;
  * a universe that quietly drops losers (survivorship) — delisted names must be
    carried to terminal value, never dropped.
"""
