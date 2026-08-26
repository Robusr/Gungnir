"""Tests for the M2 decision proposal: decisions are always feasible."""

import math

import pytest

from gungnir.config import CONFIG
from gungnir.engine import validate
from gungnir.models import GameState, MarketId, ProductId, ProductState, ProductionSchedule
from gungnir.proposal import _raw_material_purchase, propose


def _state(**kwargs):
    defaults = dict(
        period=0,
        cash=5_000_000.0,
        workers=150,
        machines=100,
        raw_material_units=1_236_000.0,
        net_assets=10_000_000.0,
        products={
            ProductId.A: ProductState(factory_inventory=100, rnd_level=1),
            ProductId.B: ProductState(factory_inventory=80, rnd_level=1),
        },
    )
    defaults.update(kwargs)
    return GameState(**defaults)


def _assert_feasible(proposal):
    assert proposal.feasible is True, proposal.result.feasibility.violations
    assert proposal.result.feasibility.emergency_loan_triggered is False
    assert proposal.result.feasibility.cash_shortfall is False
    assert proposal.result.ending_cash >= 0.0


def test_proposal_is_feasible_on_reference_like_state():
    p = propose(_state())
    _assert_feasible(p)
    # Shipments must respect the producible ceiling.
    for pid in ProductId:
        opening = 100 if pid is ProductId.A else 80
        produced = p.decision.production[pid].total
        shipped = sum(p.decision.shipments[pid].values())
        assert shipped <= opening + produced * 0.75 + 1e-6


def test_proposal_covers_level0_with_rnd_and_no_production():
    state = _state(
        products={
            ProductId.A: ProductState(factory_inventory=0, rnd_level=0),
            ProductId.B: ProductState(factory_inventory=0, rnd_level=1),
        }
    )
    p = propose(state)
    assert p.decision.rnd_investment[ProductId.A] > 0
    assert p.decision.production[ProductId.A].total == 0
    _assert_feasible(p)


def test_proposal_scales_production_when_labor_binds():
    state = _state(workers=5)
    p = propose(state)
    _assert_feasible(p)
    # Labour is the binding resource; production is capped, not oversized.
    report = validate(state, p.decision)
    assert report.feasible


def test_proposal_finances_when_cash_is_tight():
    state = _state(cash=100_000.0, workers=150)
    p = propose(state)
    _assert_feasible(p)
    # With only 100k cash and 150 workers, some financing is unavoidable.
    assert p.decision.bank_loan > 0 or p.decision.bond_issue > 0


def test_proposal_without_machines_is_feasible():
    state = _state(machines=0, workers=0)
    p = propose(state)
    _assert_feasible(p)
    assert all(p.decision.production[pid].total == 0 for pid in ProductId)


def test_proposal_fuzz_over_states():
    for workers, machines, cash, raw in [
        (0, 0, 0.0, 0.0),
        (10, 5, 1_000_000.0, 100_000.0),
        (150, 100, 2_945_500.0, 1_236_000.0),
        (300, 200, 20_000_000.0, 5_000_000.0),
        (1, 1, 50_000.0, 0.0),
    ]:
        state = _state(workers=workers, machines=machines, cash=cash, raw_material_units=raw)
        p = propose(state)
        assert p.feasible, f"workers={workers} machines={machines} cash={cash}: {p.result.feasibility.violations}"
        assert not p.result.feasibility.emergency_loan_triggered
        assert not p.result.feasibility.cash_shortfall
        assert p.result.ending_cash >= 0.0


def test_raw_material_purchase_rounds_up_to_discount_tier():
    # 1500 units of A need 1500 * 300 = 450,000 raw units; purchase = 450k / 0.5
    # = 900,000 units, just below the 1M tier. The 0.96 tier is worth taking.
    production = {
        ProductId.A: ProductionSchedule(first_normal=1500.0),
        ProductId.B: ProductionSchedule(first_normal=0.0),
    }
    state = _state(raw_material_units=0.0)
    gross = _raw_material_purchase(state, production, CONFIG)
    assert gross == pytest.approx(1_000_000.0)


def test_raw_material_purchase_does_not_overbuy_when_no_tier():
    # A need far above the top tier (2M) has no higher tier to round up to.
    production = {
        ProductId.A: ProductionSchedule(first_normal=20_000.0),
        ProductId.B: ProductionSchedule(first_normal=0.0),
    }
    state = _state(raw_material_units=0.0)
    # need = 20,000 * 300 = 6,000,000; purchase = 6M / 0.5 = 12M units (> 2M).
    gross = _raw_material_purchase(state, production, CONFIG)
    assert gross == pytest.approx(12_000_000.0)


def test_proposal_deploys_surplus_to_treasury_and_dividend():
    p = propose(_state(cash=10_000_000.0))
    _assert_feasible(p)
    assert p.decision.treasury_purchase > 0
    assert p.decision.dividend > 0
    assert p.result.ending_cash >= CONFIG.finance.minimum_cash


def test_proposal_does_not_deploy_when_cash_tight():
    p = propose(_state(cash=100_000.0))
    _assert_feasible(p)
    assert p.decision.treasury_purchase == 0.0
    assert p.decision.dividend == 0.0
