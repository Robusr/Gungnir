"""Golden reconciliation against the reference decision tool ``决策工具.xls``.

The reference tool's ``财务`` sheet mixes computed ("black") numbers with
user-entered ("blue") estimates. This test pins the *computed* lines our engine
must reproduce exactly, and documents the handful of items still marked
TODO(待确认) (special-shift wage rates, defect rate, storage/inventory valuation,
tax credit) with their tool targets for the M1 sign-off.
"""

import pytest

from gungnir.engine import simulate
from tests.conftest import REFERENCE_SALES_REVENUE


def cash_by_key(result):
    return {line.key: line.amount for line in result.cash_flow}


# --- confirmed (reconciled) lines: (key, expected amount) -------------------
CONFIRMED = {
    "opening_cash": 2_945_500.0,
    "bond_principal": -20_500.0,
    "bond_interest": -16_500.0,
    "training_fee": 0.0,
    "layoff_severance": -5_000.0,
    "basic_wage": -230_724.0,
    "machine_maintenance": -20_000.0,
    "rnd_cash": 0.0,
    "rnd_amortization": 0.0,
    "raw_material_purchase": 0.0,
    "raw_material_discount": 0.0,
    "raw_material_freight": 0.0,
    "management_fee": -17_000.0,
    "material_usage": -405_840.0,
    "finished_freight": -490_324.0,
    "advertising": -140_000.0,
    "promotion": -210_000.0,
    "sales_revenue": 6_005_730.0,
    "depreciation": -200_000.0,
}


def test_confirmed_lines_match_reference_tool(reference_state, reference_decision):
    result = simulate(reference_state, reference_decision, REFERENCE_SALES_REVENUE)
    amounts = cash_by_key(result)
    for key, expected in CONFIRMED.items():
        assert amounts[key] == pytest.approx(expected, abs=0.5), key


def test_pending_items_are_flagged(reference_state, reference_decision):
    """The still-open items are computed without crashing; targets documented here."""
    result = simulate(reference_state, reference_decision, REFERENCE_SALES_REVENUE)
    amounts = cash_by_key(result)

    # TODO(待确认) special-shift wage: engine ~ -165,367.5 vs tool -166,811.
    #   Rate mapping (first_overtime=4.5, second_normal=4, second_overtime=6) is
    #   our working hypothesis and needs one more reconciliation data point.
    assert amounts["special_wage"] < 0

    # TODO(待确认) 废品损失: engine 0 (defect rate unknown) vs tool -42,400.
    assert amounts["waste_loss"] == pytest.approx(0.0)

    # TODO(待确认) 原材料存储费: engine -51,654 vs tool -54,100 (valuation basis).
    assert amounts["raw_material_storage"] < 0

    # Finished-goods storage is undefined on this (infeasible) shipment example;
    # it is clamped and the shipment infeasibility is flagged separately.
    assert result.feasibility.feasible is False
    assert any(v.code == "shipment_infeasible" for v in result.feasibility.violations)
