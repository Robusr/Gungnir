"""M6 replay & evaluation: multi-period rollout, self-play, scoring curves.

Three entry points:

* ``run_episode(state, policy, periods)`` — roll a single firm forward with a
  policy (a callable ``(GameState) -> ProposalResult``), collecting per-period
  results and the profit curve.
* ``replay_decisions(state, decisions)`` — replay a *recorded* decision list
  through the engine (历史回放).
* ``run_tournament(states, policies, periods)`` — run N firms in parallel and
  score each against the other N-1 every period, producing the per-firm Z-score
  "scoring curve".

The seven-metric composite needs a population (the arena's ten firms); a single
``run_episode`` therefore has no meaningful composite, so its ``score_curve`` is
only filled inside ``run_tournament``. The firms here do **not** compete for
demand (the L2 demand model is per-firm); demand coupling is TODO(待确认).
"""

from __future__ import annotations

from gungnir.config import CONFIG, Config
from gungnir.engine.scoring import compute_composite, compute_our_metrics
from gungnir.models import (
    Decision,
    EpisodeResult,
    FirmSeries,
    GameState,
    PeriodRecord,
    ProposalResult,
    TournamentResult,
)
from gungnir.optimize import optimize
from gungnir.proposal import evaluate


def run_episode(
    state: GameState,
    policy=None,
    periods: int = 8,
    config: Config = CONFIG,
) -> EpisodeResult:
    """Roll ``state`` forward ``periods`` steps using ``policy``.

    ``policy`` defaults to the optimizer (``optimize``). It returns a
    ``ProposalResult`` whose ``result`` was already simulated, so we advance
    ``state = result.ending_state`` each period.
    """
    if policy is None:
        policy = lambda s: optimize(s, config)  # noqa: E731
    state = state.model_copy(deep=True)
    records: list[PeriodRecord] = []
    profit_curve: list[float] = []
    for _ in range(periods):
        proposal: ProposalResult = policy(state)
        decision = proposal.decision
        result = proposal.result
        metrics = compute_our_metrics(result, state, decision, config)
        records.append(
            PeriodRecord(period=state.period, decision=decision, result=result, metrics=metrics)
        )
        profit_curve.append(result.profit)
        state = result.ending_state
    return EpisodeResult(
        ending_state=state, records=records, profit_curve=profit_curve, score_curve=[]
    )


def replay_decisions(
    state: GameState, decisions: list[Decision], config: Config = CONFIG
) -> EpisodeResult:
    """Replay a recorded decision list through the engine (历史回放)."""
    state = state.model_copy(deep=True)
    records: list[PeriodRecord] = []
    profit_curve: list[float] = []
    for decision in decisions:
        result = evaluate(state, decision, config)
        metrics = compute_our_metrics(result, state, decision, config)
        records.append(
            PeriodRecord(period=state.period, decision=decision, result=result, metrics=metrics)
        )
        profit_curve.append(result.profit)
        state = result.ending_state
    return EpisodeResult(
        ending_state=state, records=records, profit_curve=profit_curve, score_curve=[]
    )


def run_tournament(
    states: list[GameState],
    policies: list,
    periods: int = 8,
    config: Config = CONFIG,
) -> TournamentResult:
    """Run ``len(states)`` firms in parallel and score them relative to each other."""
    if len(states) != len(policies):
        raise ValueError("states and policies must have the same length")

    episodes = [run_episode(s, p, periods, config) for s, p in zip(states, policies)]
    score_curves: dict[str, list[float]] = {str(i): [] for i in range(len(episodes))}

    for t in range(periods):
        metrics_list = [ep.records[t].metrics for ep in episodes]
        for i, ep in enumerate(episodes):
            peers = [metrics_list[j] for j in range(len(episodes)) if j != i]
            breakdown = compute_composite(metrics_list[i], peers, config)
            ep.records[t].composite = breakdown.composite
            score_curves[str(i)].append(breakdown.composite)

    # Back-fill each episode's score_curve for convenience.
    for i, ep in enumerate(episodes):
        ep.score_curve = score_curves[str(i)]

    firms = [FirmSeries(firm_id=str(i), episode=ep) for i, ep in enumerate(episodes)]
    return TournamentResult(firms=firms, periods=periods, score_curves=score_curves)
