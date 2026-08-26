"""Shared fixtures — the reference scenario from the decision tool ``决策工具.xls``."""

from __future__ import annotations

import pytest

from gungnir.models import (
    Decision,
    GameState,
    MarketId,
    ProductId,
    ProductionSchedule,
    ProductState,
)


def _ps(factory: int, level: int, cumulative: float, spent: float = 0.0) -> ProductState:
    return ProductState(
        factory_inventory=factory,
        rnd_level=level,
        rnd_cumulative=cumulative,
        rnd_spent_last_period=spent,
        grade=1.0,
    )


@pytest.fixture
def reference_state() -> GameState:
    """公司状况 sheet of the reference tool (period start)."""
    return GameState(
        period=0,
        cash=2_945_500.0,
        workers=150,
        machines=100,
        raw_material_units=1_236_000.0,
        accumulated_depreciation=1_600_000.0,
        bond_outstanding=550_000.0,
        bond_principal_due=20_500.0,
        cumulative_tax=67_227.0,
        tax_credit=-2_475.0,
        net_assets=6_395_930.0,
        last_period_profit=-5_675.0,
        products={
            ProductId.A: _ps(factory=204, level=1, cumulative=100_000.0),
            ProductId.B: _ps(factory=188, level=1, cumulative=200_000.0),
        },
    )


@pytest.fixture
def reference_decision() -> Decision:
    """决策单 sheet of the reference tool."""
    return Decision(
        prices={
            ProductId.A: {MarketId.M1: 2549.0, MarketId.M2: 2299.0, MarketId.M3: 2599.0},
            ProductId.B: {MarketId.M1: 5199.0, MarketId.M2: 5099.0, MarketId.M3: 5199.0},
        },
        advertising={ProductId.A: 70_000.0, ProductId.B: 70_000.0},
        promotion={MarketId.M1: 70_000.0, MarketId.M2: 70_000.0, MarketId.M3: 70_000.0},
        shipments={
            ProductId.A: {MarketId.M1: 100, MarketId.M2: 314, MarketId.M3: 400},
            ProductId.B: {MarketId.M1: 310, MarketId.M2: 100, MarketId.M3: 326},
        },
        production={
            ProductId.A: ProductionSchedule(first_normal=264.8, first_overtime=135.2),
            ProductId.B: ProductionSchedule(
                first_normal=127.6,
                first_overtime=62.12,
                second_normal=0.56,
                second_overtime=0.28,
            ),
        },
        layoff=5,
        dividend=100_000.0,
        wage_coefficient=1.02,
    )


# Reference sales revenue from the tool's 财务!R22 (blue/estimated input).
REFERENCE_SALES_REVENUE = 6_005_730.0
