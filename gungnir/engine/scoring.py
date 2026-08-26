"""Score projection (seven-metric Z-score).

The composite score is computed over *all* companies in the arena, so the
engine can only project it given our own metrics plus the competitors' metrics
(entered from platform data, or estimated). This module is pure: given the ten
companies' seven metrics, it returns a ``ScoreBreakdown``.

Metric keys (canonical order) map to ``config.ScoringParams`` weights.
"""

from __future__ import annotations

import statistics

from gungnir.config import CONFIG, Config
from gungnir.models import Decision, GameState, PeriodResult, ScoreBreakdown

METRIC_KEYS = (
    "current_profit",
    "net_assets",
    "market_share",
    "return_on_capital",
    "cumulative_dividend",
    "cumulative_tax",
    "profit_per_capita",
)


def metric_weights(config: Config = CONFIG) -> dict[str, float]:
    s = config.scoring
    return {
        "current_profit": s.weight_current_profit,
        "net_assets": s.weight_net_assets,
        "market_share": s.weight_market_share,
        "return_on_capital": s.weight_return_on_capital,
        "cumulative_dividend": s.weight_cumulative_dividend,
        "cumulative_tax": s.weight_cumulative_tax,
        "profit_per_capita": s.weight_profit_per_capita,
    }


def z_score(value: float, mean: float, std: float) -> float:
    """标准分 = (value - mean) / std; 0 when std is 0 (all ties)."""
    if std <= 0:
        return 0.0
    return (value - mean) / std


def compute_composite(
    company: dict[str, float],
    peers: list[dict[str, float]],
    config: Config = CONFIG,
) -> ScoreBreakdown:
    """Compute the composite score for ``company`` against ``peers``.

    ``company`` and each peer are dicts keyed by ``METRIC_KEYS``. The standard
    deviation is the population std over all ten firms (the full arena).
    """
    weights = metric_weights(config)
    firms = [company, *peers]
    z: dict[str, float] = {}
    weighted: dict[str, float] = {}
    for key in METRIC_KEYS:
        values = [f[key] for f in firms]
        mean = statistics.fmean(values)
        std = statistics.pstdev(values)
        z[key] = z_score(company[key], mean, std)
        weighted[key] = z[key] * weights[key]
    return ScoreBreakdown(
        metrics={k: company[k] for k in METRIC_KEYS},
        z_scores=z,
        weighted=weighted,
        composite=sum(weighted.values()),
    )


def compute_our_metrics(
    result: PeriodResult,
    state: GameState,
    decision: Decision,
    config: Config = CONFIG,
) -> dict[str, float]:
    """Project our company's seven raw metrics from a simulation result.

    ``market_share`` and a precise ``net_assets`` depend on competitor / inventory
    valuation data not yet modelled (TODO 待确认); they are returned as 0.0 until
    the demand model (L2) and inventory-valuation rules land in M3/M4.
    """
    ending = result.ending_state
    net_assets = ending.net_assets
    capital = net_assets + ending.bond_outstanding
    return_on_capital = result.profit / capital if capital > 0 else 0.0
    headcount = state.workers + decision.hire  # includes laid-off + new (TODO 待确认)
    profit_per_capita = result.profit / headcount if headcount > 0 else 0.0
    return {
        "current_profit": result.profit,
        "net_assets": net_assets,
        "market_share": 0.0,  # TODO(待确认): needs arena sales data
        "return_on_capital": return_on_capital,
        "cumulative_dividend": ending.cumulative_dividend,
        "cumulative_tax": ending.cumulative_tax,
        "profit_per_capita": profit_per_capita,
    }
