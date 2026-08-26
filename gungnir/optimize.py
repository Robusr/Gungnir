"""Decision optimizer (M3): improve the M2 baseline by deterministic search.

The optimizer wraps :func:`gungnir.proposal.propose` and does coordinate ascent
over price — the only lever the placeholder demand model currently responds to
(advertising/promotion/grade sensitivities are 0 in :class:`DemandParams`).
Every candidate is a full feasible proposal, so the optimizer inherits the M2
guarantee: the returned decision is always feasible and never triggers emergency
financing.

The objective is projected pre-tax profit (the "本期利润" scoring metric). Full
seven-metric Z-score optimization against nine peers is deferred to M6, where
the peer loop exists. The search is deterministic (a fixed price grid evaluated
in a fixed order); no randomness.
"""

from __future__ import annotations

from gungnir.config import CONFIG, Config
from gungnir.models import GameState, MarketId, ProductId, ProposalResult
from gungnir.proposal import propose

_PID_INDEX = {ProductId.A: 0, ProductId.B: 1}

# Price grid as multipliers of the reference price (coarse and deterministic).
_PRICE_MULTIPLIERS = (0.60, 0.75, 0.90, 1.00, 1.10, 1.25, 1.40)


def objective(proposal: ProposalResult) -> float:
    """Projected pre-tax profit (元). Stand-in for the score metric until M6."""
    return proposal.result.profit


def optimize(state: GameState, config: Config = CONFIG) -> ProposalResult:
    """Return the best feasible decision found by coordinate ascent over price."""
    best = propose(state, config)
    for _ in range(2):  # two passes help settle cross-market interactions
        improved = False
        for pid in ProductId:
            for market in MarketId:
                candidate = _best_price(state, best, pid, market, config)
                if candidate is not None and objective(candidate) > objective(best) + 1e-6:
                    best = candidate
                    improved = True
        if not improved:
            break
    return best


def _best_price(state, current, pid, market, config) -> ProposalResult | None:
    ref = config.demand.reference_price[_PID_INDEX[pid]]
    best = current
    for mult in _PRICE_MULTIPLIERS:
        price = ref * mult
        prices = _copy_prices(current.decision.prices)
        prices[pid][market] = price
        candidate = propose(state, config, prices=prices)
        if candidate.feasible and objective(candidate) > objective(best) + 1e-6:
            best = candidate
    return best if best is not current else None


def _copy_prices(prices: dict[ProductId, dict[MarketId, float]]):
    return {pid: dict(by_market) for pid, by_market in prices.items()}
