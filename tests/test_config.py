"""Configuration sanity checks."""

import pytest

from gungnir.config import CONFIG
from gungnir.engine.scoring import metric_weights


def test_scoring_weights_sum_to_one():
    assert sum(metric_weights().values()) == pytest.approx(1.0)


def test_products_loaded():
    assert [p.name for p in CONFIG.products] == ["A", "B"]


def test_product_a_params():
    a = CONFIG.product("A")
    assert a.machine_hours == 100.0
    assert a.labor_hours == 150.0
    assert a.raw_material_units == 300.0
    assert a.rnd_cumulative_cost == (100_000, 200_000, 300_000, 400_000, 500_000)


def test_finance_params():
    assert CONFIG.finance.initial_cash == 2_500_000.0
    assert CONFIG.finance.minimum_cash == 2_000_000.0
    assert CONFIG.finance.credit_limit == 8_000_000.0


def test_freight_tables():
    a = CONFIG.product("A")
    assert a.fixed_freight == (680.0, 1_820.0, 4_000.0)
    assert a.variable_freight == (34.0, 91.0, 200.0)
