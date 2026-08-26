"""Unit tests for the seven-metric Z-score projection."""

import pytest

from gungnir.engine.scoring import compute_composite, metric_weights, z_score


def _metrics(**overrides):
    base = {
        "current_profit": 0.0,
        "net_assets": 0.0,
        "market_share": 0.0,
        "return_on_capital": 0.0,
        "cumulative_dividend": 0.0,
        "cumulative_tax": 0.0,
        "profit_per_capita": 0.0,
    }
    base.update(overrides)
    return base


def test_z_score_basic():
    assert z_score(15.0, 10.0, 5.0) == pytest.approx(1.0)
    assert z_score(10.0, 10.0, 5.0) == pytest.approx(0.0)
    assert z_score(10.0, 10.0, 0.0) == pytest.approx(0.0)


def test_weights_sum_to_one():
    assert sum(metric_weights().values()) == pytest.approx(1.0)


def test_composite_all_tied_is_zero():
    company = _metrics(current_profit=100.0)
    peers = [_metrics(current_profit=100.0) for _ in range(9)]
    score = compute_composite(company, peers)
    assert score.composite == pytest.approx(0.0)


def test_composite_better_than_average_is_positive():
    # Our profit far above the nine peers' (all 0) -> positive z-score.
    company = _metrics(current_profit=1_000_000.0)
    peers = [_metrics(current_profit=0.0) for _ in range(9)]
    score = compute_composite(company, peers)
    assert score.z_scores["current_profit"] > 0
    assert score.composite > 0
