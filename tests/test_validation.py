"""Unit tests for decision feasibility validation."""

from gungnir.engine import validate
from gungnir.models import (
    Decision,
    GameState,
    MarketId,
    ProductId,
    ProductionSchedule,
    ProductState,
)


def _state(**kwargs):
    defaults = dict(
        cash=5_000_000.0,
        workers=100,
        machines=50,
        raw_material_units=1_000_000.0,
        net_assets=10_000_000.0,
        products={
            ProductId.A: ProductState(rnd_level=1, factory_inventory=0),
            ProductId.B: ProductState(rnd_level=1, factory_inventory=0),
        },
    )
    defaults.update(kwargs)
    return GameState(**defaults)


def _codes(report):
    return {v.code for v in report.violations}


def test_labor_shortfall():
    state = _state(workers=10)
    decision = Decision(
        production={ProductId.A: ProductionSchedule(first_normal=100.0)}
    )
    report = validate(state, decision)
    assert "labor_shortfall" in _codes(report)


def test_machine_shortfall():
    state = _state(machines=1)
    decision = Decision(
        production={ProductId.A: ProductionSchedule(first_normal=100.0)}
    )
    report = validate(state, decision)
    assert "machine_shortfall" in _codes(report)


def test_raw_material_shortfall():
    state = _state(raw_material_units=0.0)
    decision = Decision(
        production={ProductId.A: ProductionSchedule(first_normal=10.0)}
    )
    report = validate(state, decision)
    assert "material_shortfall" in _codes(report)


def test_shipment_infeasible():
    state = _state()
    decision = Decision(
        production={ProductId.A: ProductionSchedule(first_normal=10.0)},
        shipments={ProductId.A: {MarketId.M1: 1000}},
    )
    report = validate(state, decision)
    assert "shipment_infeasible" in _codes(report)


def test_hire_limit():
    state = _state(workers=100)
    decision = Decision(hire=60)  # > 50%
    report = validate(state, decision)
    assert "hire_limit" in _codes(report)


def test_layoff_limit():
    state = _state(workers=100)
    decision = Decision(layoff=20)  # > 10%
    report = validate(state, decision)
    assert "layoff_limit" in _codes(report)


def test_layoff_below_retirement():
    state = _state(workers=100)
    decision = Decision(layoff=0)  # < 3% (3 workers)
    report = validate(state, decision)
    assert "layoff_below_retirement" in _codes(report)


def test_rnd_required_before_production():
    state = _state(
        products={
            ProductId.A: ProductState(rnd_level=0),
            ProductId.B: ProductState(rnd_level=1),
        }
    )
    decision = Decision(production={ProductId.A: ProductionSchedule(first_normal=5.0)})
    report = validate(state, decision)
    assert "rnd_required" in _codes(report)


def test_wage_coefficient_below_min():
    decision = Decision(wage_coefficient=0.5)
    report = validate(_state(), decision)
    assert "wage_coefficient_below_min" in _codes(report)


def test_bond_limit():
    state = _state(net_assets=1_000_000.0)
    decision = Decision(bond_issue=600_000.0)  # > 50% of net assets
    report = validate(state, decision)
    assert "bond_limit" in _codes(report)


def test_feasible_decision():
    state = _state()
    decision = Decision(
        production={ProductId.A: ProductionSchedule(first_normal=10.0)},
        shipments={ProductId.A: {MarketId.M1: 5}},
        layoff=3,
        wage_coefficient=1.0,
    )
    report = validate(state, decision)
    assert report.feasible is True
