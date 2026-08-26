"""Unit tests for the ordered cash-flow simulation."""

import pytest

from gungnir.engine import simulate
from gungnir.models import (
    Decision,
    GameState,
    MarketId,
    ProductId,
    ProductionSchedule,
    ProductState,
)


def cash_by_key(result):
    return {line.key: line for line in result.cash_flow}


def test_cashflow_order_is_stable(reference_state, reference_decision):
    result = simulate(reference_state, reference_decision, 6_005_730.0)
    keys = [line.key for line in result.cash_flow]
    expected = [
        "opening_cash",
        "bank_loan_income",
        "bond_issue",
        "bond_principal",
        "bond_interest",
        "training_fee",
        "layoff_severance",
        "basic_wage",
        "machine_maintenance",
        "emergency_loan",
        "rnd_cash",
        "rnd_amortization",
        "raw_material_purchase",
        "raw_material_discount",
        "raw_material_freight",
        "special_wage",
        "management_fee",
        "material_usage",
        "finished_freight",
        "advertising",
        "promotion",
        "sales_revenue",
        "waste_loss",
        "depreciation",
        "inventory_change",
        "raw_material_storage",
        "finished_storage",
        "treasury_principal_return",
        "treasury_interest",
        "bank_loan_repay",
        "bank_loan_interest",
        "emergency_loan_repay",
        "emergency_loan_interest",
        "tax",
        "machine_purchase",
        "dividend",
        "treasury_purchase",
    ]
    assert keys == expected


def test_profit_is_revenue_minus_cost(reference_state, reference_decision):
    result = simulate(reference_state, reference_decision, 6_005_730.0)
    assert result.profit == pytest.approx(result.revenue_total - result.cost_total)


def test_bond_interest(reference_state, reference_decision):
    # 550,000 * 12% / 4 = 16,500
    result = simulate(reference_state, reference_decision, 0.0)
    line = cash_by_key(result)["bond_interest"]
    assert line.amount == pytest.approx(-16_500.0)


def test_bond_principal_paid(reference_state, reference_decision):
    result = simulate(reference_state, reference_decision, 0.0)
    assert cash_by_key(result)["bond_principal"].amount == pytest.approx(-20_500.0)


def test_dividend_ceiling_on_after_tax_profit():
    state = GameState(
        cash=5_000_000.0,
        workers=0,
        products={ProductId.A: ProductState(rnd_level=1), ProductId.B: ProductState(rnd_level=1)},
    )
    decision = Decision(dividend=1_000_000.0)
    # no revenue -> profit 0 -> after-tax profit 0 -> dividend clamped to 0
    result = simulate(state, decision, 0.0)
    assert cash_by_key(result)["dividend"].amount == pytest.approx(0.0)


def test_emergency_loan_triggered_when_cash_short():
    # Opening cash insufficient to cover even the first-shift basic wage.
    state = GameState(
        cash=10_000.0,
        workers=100,
        machines=0,
        products={ProductId.A: ProductState(rnd_level=1), ProductId.B: ProductState(rnd_level=1)},
    )
    decision = Decision(
        production={
            ProductId.A: ProductionSchedule(first_normal=50.0),
        },
        layoff=0,
        wage_coefficient=1.0,
    )
    result = simulate(state, decision, 0.0)
    assert result.feasibility.emergency_loan_triggered is True
    assert result.feasibility.emergency_loan_amount > 0


def test_ending_cash_matches_last_line(reference_state, reference_decision):
    result = simulate(reference_state, reference_decision, 6_005_730.0)
    assert result.ending_cash == pytest.approx(result.cash_flow[-1].cash_after)


def test_tax_uses_tax_credit(reference_state, reference_decision):
    # profit = revenue - cost; tax = profit * 30% - tax_credit (credit = -2,475)
    result = simulate(reference_state, reference_decision, 6_005_730.0)
    expected = max(0.0, result.profit * 0.30 - (-2_475.0))
    assert result.tax == pytest.approx(expected)


def test_sales_revenue_formula():
    from gungnir.engine.cashflow import compute_sales_revenue
    from gungnir.models import SalesOutcome

    sales = SalesOutcome(sold={ProductId.A: {MarketId.M1: 120}})
    prices = {ProductId.A: {MarketId.M1: 100.0}}
    backorders = {ProductId.A: {MarketId.M1: 20}}
    last_prices = {ProductId.A: {MarketId.M1: 90.0}}
    # 20 * min(90,100) + (120-20)*100 = 20*90 + 100*100 = 1,800 + 10,000
    revenue = compute_sales_revenue(sales, prices, backorders, last_prices)
    assert revenue == pytest.approx(11_800.0)
