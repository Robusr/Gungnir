"""Unit tests for the L2 demand model (placeholder, deterministic)."""

from gungnir.demand import forecast_demand
from gungnir.models import MarketId, ProductId


def _prices(pa=2500.0, pb=5000.0):
    return {
        ProductId.A: {m: pa for m in MarketId},
        ProductId.B: {m: pb for m in MarketId},
    }


def _blank():
    return {}, {pid: 0.0 for pid in ProductId}, {m: 0.0 for m in MarketId}, {
        pid: 1.0 for pid in ProductId
    }


def test_forecast_positive_at_reference_price():
    state, adv, promo, grade = _blank()
    forecast = forecast_demand(state, _prices(), adv, promo, grade)
    for pid in ProductId:
        for m in MarketId:
            assert forecast[pid][m] > 0


def test_higher_price_lowers_demand():
    state, adv, promo, grade = _blank()
    low = forecast_demand(state, _prices(pa=2000.0), adv, promo, grade)
    high = forecast_demand(state, _prices(pa=3000.0), adv, promo, grade)
    assert high[ProductId.A][MarketId.M1] < low[ProductId.A][MarketId.M1]


def test_demand_clamped_non_negative():
    state, adv, promo, grade = _blank()
    forecast = forecast_demand(state, _prices(pa=1_000_000.0), adv, promo, grade)
    assert forecast[ProductId.A][MarketId.M1] >= 0.0


def test_demand_is_market_independent_when_prices_equal():
    state, adv, promo, grade = _blank()
    forecast = forecast_demand(state, _prices(), adv, promo, grade)
    a = [forecast[ProductId.A][m] for m in MarketId]
    assert abs(a[0] - a[1]) < 1e-9 and abs(a[1] - a[2]) < 1e-9
