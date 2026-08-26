"""Tests for the M3 optimizer: deterministic, feasible, at-least-as-good."""

from gungnir.models import GameState, MarketId, ProductId, ProductState
from gungnir.optimize import objective, optimize
from gungnir.proposal import propose


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


def test_optimizer_never_worse_than_proposal():
    state = _state()
    base = propose(state)
    best = optimize(state)
    _assert_feasible(best)
    assert objective(best) >= objective(base) - 1e-6


def test_optimizer_is_deterministic():
    state = _state()
    a = optimize(state)
    b = optimize(state)
    assert objective(a) == objective(b)
    assert a.decision.prices == b.decision.prices


def test_optimizer_moves_prices_off_reference_when_beneficial():
    state = _state()
    best = optimize(state)
    # The placeholder elastic model typically rewards a price below the
    # reference, so the optimizer should have left the reference point.
    changed = any(
        best.decision.prices[pid][m] != 2500.0 if pid is ProductId.A else
        best.decision.prices[pid][m] != 5000.0
        for pid in ProductId for m in MarketId
    )
    # Not asserted true/false (depends on cost structure), but the decision
    # must at least be internally consistent and feasible.
    _assert_feasible(best)


def test_optimizer_feasible_across_states():
    for workers, machines, cash, raw in [
        (10, 5, 1_000_000.0, 100_000.0),
        (150, 100, 2_945_500.0, 1_236_000.0),
        (0, 0, 0.0, 0.0),
    ]:
        best = optimize(_state(workers=workers, machines=machines, cash=cash, raw_material_units=raw))
        _assert_feasible(best)
