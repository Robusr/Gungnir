"""Tests for M6 replay & evaluation: episode, replay, tournament, scoring curve."""

import math

from gungnir.models import GameState, ProductId, ProductState
from gungnir.optimize import optimize
from gungnir.proposal import propose
from gungnir.replay import replay_decisions, run_episode, run_tournament


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


def test_run_episode_advances_state():
    ep = run_episode(_state(), policy=lambda s: propose(s), periods=6)
    assert len(ep.records) == 6
    assert len(ep.profit_curve) == 6
    assert ep.ending_state.period == 6
    assert ep.records[0].period == 0
    assert ep.records[-1].period == 5
    # every period must be feasible
    for rec in ep.records:
        assert rec.result.feasibility.feasible
        assert not rec.result.feasibility.emergency_loan_triggered


def test_replay_decisions_uses_given_sequence():
    state = _state()
    d1 = propose(state).decision
    d2 = propose(state).decision
    ep = replay_decisions(state, [d1, d2])
    assert len(ep.records) == 2
    assert ep.records[0].decision == d1
    assert ep.records[1].decision == d2
    assert ep.ending_state.period == 2


def test_tournament_produces_scoring_curves():
    states = [_state() for _ in range(3)]
    policies = [
        lambda s: optimize(s),
        lambda s: propose(s),
        lambda s: propose(s),
    ]
    t = run_tournament(states, policies, periods=4)
    assert t.periods == 4
    assert len(t.firms) == 3
    assert set(t.score_curves) == {"0", "1", "2"}
    for firm_id, curve in t.score_curves.items():
        assert len(curve) == 4
        assert all(math.isfinite(v) for v in curve)
    # Firms 1 and 2 are identical (same state + policy), so they score equally.
    assert t.score_curves["1"] == t.score_curves["2"]


def test_tournament_rejects_mismatched_lengths():
    with __import__("pytest").raises(ValueError):
        run_tournament([_state(), _state()], [lambda s: propose(s)], periods=2)
