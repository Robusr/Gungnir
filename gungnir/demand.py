"""L2 demand model (deterministic placeholder).

The BizSim platform does not publish its demand coefficients, so this module
implements a simple, monotone, reproducible demand surface — sufficient to size
production and shipments in M2 and to give the M3 optimizer a smooth objective.
All coefficients live in :class:`~gungnir.config.DemandParams` and are marked
TODO(待确认) there; **feasibility never depends on their exact values**.

demand[pid][m] = base[pid][m]
                 * (price / reference_price[pid]) ** price_elasticity
                 * (1 + advertising_sensitivity * advertising[pid] / 1000)
                 * (1 + promotion_sensitivity * promotion[m] / 1000)
                 * grade ** grade_sensitivity
"""

from __future__ import annotations

from gungnir.config import CONFIG, Config
from gungnir.models import MarketId, ProductId

# Product order used to index DemandParams tuples.
_PID_INDEX = {ProductId.A: 0, ProductId.B: 1}
_MARKET_INDEX = {MarketId.M1: 0, MarketId.M2: 1, MarketId.M3: 2}


def forecast_demand(
    state,
    prices: dict[ProductId, dict[MarketId, float]],
    advertising: dict[ProductId, float],
    promotion: dict[MarketId, float],
    grade: dict[ProductId, float],
    config: Config = CONFIG,
) -> dict[ProductId, dict[MarketId, float]]:
    """Forecast per-product per-market demand (件) given prices and marketing.

    ``state`` is accepted for interface symmetry (grade could be derived from it)
    but is not currently required by the placeholder model.
    """
    d = config.demand
    out: dict[ProductId, dict[MarketId, float]] = {}
    for pid in ProductId:
        i = _PID_INDEX[pid]
        ref = d.reference_price[i]
        g = max(1.0, grade.get(pid, 1.0))
        adv = advertising.get(pid, 0.0)
        grade_factor = g ** d.grade_sensitivity
        out[pid] = {}
        for market in MarketId:
            j = _MARKET_INDEX[market]
            price = prices.get(pid, {}).get(market, ref)
            if price <= 0.0 or ref <= 0.0:
                price_factor = 0.0
            else:
                price_factor = (price / ref) ** d.price_elasticity
            adv_factor = 1.0 + d.advertising_sensitivity * adv / 1000.0
            promo_factor = 1.0 + d.promotion_sensitivity * promotion.get(market, 0.0) / 1000.0
            q = d.base_demand[i][j] * price_factor * adv_factor * promo_factor * grade_factor
            out[pid][market] = max(0.0, q)
    return out
