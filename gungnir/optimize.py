"""Decision optimizer (M3): improve the M2 baseline by deterministic search.

The optimizer wraps :func:`gungnir.proposal.propose` and does coordinate ascent
over price. Every candidate is a full feasible proposal, so the optimizer
inherits the M2 guarantee: the returned decision is always feasible and never
triggers emergency financing.

The objective is a *forward-looking* value (:func:`rollout_value`): the
candidate decision is rolled forward a short horizon with the baseline proposer
as the follow-on policy, and scored as discounted profit + dividend credit + a
terminal net-assets term. This makes the long-horizon levers a single-period
profit objective would ignore — treasury parking, dividends and bulk-discount
raw material (all confirmed in ``docs/rules.md``) — worth taking. The search is
deterministic (a fixed price grid evaluated in a fixed order); no randomness.

``discount`` / ``terminal_weight`` / ``div_weight`` are *policy* constants (not
platform rules) and are marked TODO(待确认) for calibration.
"""

from __future__ import annotations

from gungnir.config import CONFIG, Config
from gungnir.models import Decision, GameState, MarketId, ProductId, ProposalResult
from gungnir.proposal import evaluate, propose

_PID_INDEX = {ProductId.A: 0, ProductId.B: 1}

# Price grid as multipliers of the reference price (coarse and deterministic).
_PRICE_MULTIPLIERS = (0.60, 0.75, 0.90, 1.00, 1.10, 1.25, 1.40)

# --- rollout objective (policy constants; TODO 待确认 calibration) ----------
HORIZON = 4                 # quarters to roll forward
DISCOUNT = 0.97             # ~3% per quarter
TERMINAL_NET_ASSET_WEIGHT = 0.25  # value of net assets at the horizon
DIVIDEND_WEIGHT = 0.10             # scoring weight of cumulative dividend (§9)
_INFEASIBLE_PENALTY = -1e12


def objective(proposal: ProposalResult) -> float:
    """Single-period projected pre-tax profit (元).

    Kept for backward compatibility and quick comparisons; :func:`optimize`
    maximizes :func:`rollout_value` instead.
    """
    return proposal.result.profit


def rollout_value(
    state: GameState,
    decision: Decision,
    config: Config = CONFIG,
    horizon: int = HORIZON,
    discount: float = DISCOUNT,
    terminal_weight: float = TERMINAL_NET_ASSET_WEIGHT,
    div_weight: float = DIVIDEND_WEIGHT,
) -> float:
    """Forward-looking value of ``decision`` given ``state``.

    Period 0 is simulated with ``decision``; periods 1..horizon-1 use the
    baseline proposer as the (deterministic) follow-on policy. Infeasible or
    emergency-financing paths return a large negative penalty.
    """
    value = 0.0
    s = state
    d = decision
    for t in range(horizon):
        r = evaluate(s, d, config)
        if (
            not r.feasibility.feasible
            or r.feasibility.emergency_loan_triggered
            or r.feasibility.cash_shortfall
        ):
            return _INFEASIBLE_PENALTY
        value += (r.profit + div_weight * d.dividend) * (discount ** t)
        s = r.ending_state
        d = propose(s, config).decision
    value += terminal_weight * s.net_assets * (discount ** horizon)
    return value


def optimize(
    state: GameState, config: Config = CONFIG, horizon: int = HORIZON
) -> ProposalResult:
    """Return the best feasible decision by coordinate ascent over price, scored
    by :func:`rollout_value`."""
    def value_of(prop: ProposalResult) -> float:
        return rollout_value(state, prop.decision, config, horizon=horizon)

    best = propose(state, config)
    best_value = value_of(best)
    for _ in range(2):  # two passes help settle cross-market interactions
        improved = False
        for pid in ProductId:
            for market in MarketId:
                candidate, candidate_value = _best_price(
                    state, best, best_value, pid, market, config, value_of
                )
                if candidate_value > best_value + 1e-6:
                    best, best_value = candidate, candidate_value
                    improved = True
        if not improved:
            break
    return best


def _best_price(state, current, current_value, pid, market, config, value_of):
    ref = config.demand.reference_price[_PID_INDEX[pid]]
    best, best_value = current, current_value
    for mult in _PRICE_MULTIPLIERS:
        price = ref * mult
        prices = _copy_prices(current.decision.prices)
        prices[pid][market] = price
        candidate = propose(state, config, prices=prices)
        if candidate.feasible:
            v = value_of(candidate)
            if v > best_value + 1e-6:
                best, best_value = candidate, v
    return best, best_value


def _copy_prices(prices: dict[ProductId, dict[MarketId, float]]):
    return {pid: dict(by_market) for pid, by_market in prices.items()}
