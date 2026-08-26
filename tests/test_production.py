"""Unit tests for production / cost computations (reconciled vs 决策工具.xls)."""

import pytest

from gungnir.engine import production as prod


def test_production_totals(reference_decision):
    totals = prod.production_totals(reference_decision)
    assert totals["A"] == pytest.approx(400.0)
    assert totals["B"] == pytest.approx(190.56)


def test_labor_hours(reference_decision):
    hours = prod.labor_hours(reference_decision)
    # 一班正班 71,620 / 一班加班 35,810 / 二班 140 / 二班加班 70
    assert hours["first_normal"] == pytest.approx(71_620.0)
    assert hours["first_overtime"] == pytest.approx(35_810.0)
    assert hours["second_normal"] == pytest.approx(140.0)
    assert hours["second_overtime"] == pytest.approx(70.0)
    assert prod.total_labor_hours(reference_decision) == pytest.approx(107_640.0)


def test_machine_hours(reference_decision):
    assert prod.total_machine_hours(reference_decision) == pytest.approx(78_112.0)


def test_raw_material_units_used(reference_decision):
    assert prod.raw_material_units_used(reference_decision) == pytest.approx(405_840.0)


def test_basic_wage(reference_state, reference_decision):
    # 145 * 520 * 3 * 1.02 = 230,724
    assert prod.basic_wage(reference_state, reference_decision) == pytest.approx(230_724.0)


def test_workers_in_service(reference_state, reference_decision):
    assert prod.workers_in_service(reference_state, reference_decision) == 145


def test_training_and_severance(reference_decision):
    assert prod.training_fee(reference_decision) == pytest.approx(0.0)
    assert prod.layoff_severance(reference_decision) == pytest.approx(5_000.0)


def test_machine_maintenance(reference_state):
    assert prod.machine_maintenance(reference_state) == pytest.approx(20_000.0)


def test_depreciation(reference_state):
    assert prod.depreciation(reference_state) == pytest.approx(200_000.0)


def test_management_fee(reference_decision):
    # A(1st) 4000 + B(1st) 6000 + B(2nd) 7000 = 17,000
    assert prod.management_fee(reference_decision) == pytest.approx(17_000.0)


def test_material_usage_cost(reference_decision):
    assert prod.material_usage_cost(reference_decision) == pytest.approx(405_840.0)


def test_finished_goods_freight(reference_decision):
    assert prod.finished_goods_freight(reference_decision) == pytest.approx(490_324.0)


def test_advertising_and_promotion(reference_decision):
    assert prod.advertising_cost(reference_decision) == pytest.approx(140_000.0)
    assert prod.promotion_cost(reference_decision) == pytest.approx(210_000.0)


def test_rnd_amortization(reference_state, reference_decision):
    # (0 + 0) / 2 = 0
    assert prod.rnd_amortization(reference_state, reference_decision) == pytest.approx(0.0)


def test_closing_factory_inventory_infeasible(reference_state, reference_decision):
    closing = prod.closing_factory_inventory(reference_state, reference_decision)
    # A: 204 + 400 - 814 = -210 (infeasible — ships more than available)
    assert closing["A"] == pytest.approx(-210.0)
