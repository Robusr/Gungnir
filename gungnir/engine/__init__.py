"""Gungnir rule engine (L0 trust anchor).

The engine is a set of pure functions: given a :class:`~gungnir.models.GameState`,
a :class:`~gungnir.models.Decision` and an estimated sales revenue, it produces a
deterministic :class:`~gungnir.models.PeriodResult` (cash-flow, profit/tax,
feasibility report, score projection). No randomness, no side effects.
"""

from gungnir.engine.cashflow import simulate
from gungnir.engine.scoring import compute_composite, compute_our_metrics
from gungnir.engine.validation import validate

__all__ = ["simulate", "validate", "compute_composite", "compute_our_metrics"]
