"""L5 UI backend: FastAPI serving the closed loop 录入 → 提案 → 调整 → 导出.

Endpoints
---------
* ``POST /api/propose``  — propose a feasible decision from a ``GameState``.
* ``POST /api/optimize`` — optimize that proposal (deterministic search).
* ``POST /api/evaluate`` — re-simulate an arbitrary (user-edited) decision.
* ``POST /api/explain``  — explain a decision in Chinese (LLM or template).
* ``POST /api/export``   — export the decision + cash flow as CSV.
* ``GET  /``             — serve the single-page frontend.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from gungnir import llm
from gungnir.models import (
    Decision,
    EpisodeResult,
    Explanation,
    GameState,
    MarketId,
    PeriodResult,
    ProductId,
    ProposalResult,
    TournamentResult,
)
from gungnir.optimize import optimize
from gungnir.proposal import evaluate, propose
from gungnir.replay import run_episode, run_tournament

_STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Gungnir", version="0.1.0")
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


class StateBody(BaseModel):
    state: GameState


class EvaluateBody(BaseModel):
    state: GameState
    decision: Decision


class EpisodeBody(BaseModel):
    state: GameState
    periods: int = 8


class TournamentBody(BaseModel):
    states: list[GameState]
    periods: int = 8


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


@app.post("/api/propose", response_model=ProposalResult)
def api_propose(body: StateBody) -> ProposalResult:
    return propose(body.state)


@app.post("/api/optimize", response_model=ProposalResult)
def api_optimize(body: StateBody) -> ProposalResult:
    return optimize(body.state)


@app.post("/api/evaluate", response_model=PeriodResult)
def api_evaluate(body: EvaluateBody) -> PeriodResult:
    return evaluate(body.state, body.decision)


@app.post("/api/explain", response_model=Explanation)
def api_explain(body: EvaluateBody) -> Explanation:
    result = evaluate(body.state, body.decision)
    prop = ProposalResult(
        decision=body.decision,
        result=result,
        state=body.state,
        feasible=result.feasibility.feasible,
    )
    return llm.explain(prop)


@app.post("/api/episode", response_model=EpisodeResult)
def api_episode(body: EpisodeBody) -> EpisodeResult:
    return run_episode(body.state, policy=None, periods=body.periods)


@app.post("/api/tournament", response_model=TournamentResult)
def api_tournament(body: TournamentBody) -> TournamentResult:
    # Policies cannot be serialized over HTTP, so all firms use the optimizer;
    # score differences come from differing initial states.
    policies = [None] * len(body.states)
    return run_tournament(body.states, policies, body.periods)


@app.post("/api/export")
def api_export(body: EvaluateBody) -> Response:
    result = evaluate(body.state, body.decision)
    csv_text = _decision_csv(body.decision, result)
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="gungnir_decision.csv"'},
    )


def _decision_csv(decision: Decision, result: PeriodResult) -> str:
    """Render the decision sheet and key results as a two-column CSV."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["类型", "项目", "值"])
    for pid in ProductId:
        p = decision.prices.get(pid, {})
        w.writerow(["决策", f"产品{pid.value}价格", "/".join(f"{p.get(m, 0):,.0f}" for m in MarketId)])
        w.writerow(["决策", f"产品{pid.value}广告费", f"{decision.advertising.get(pid, 0):,.0f}"])
        w.writerow(["决策", f"产品{pid.value}研发", f"{decision.rnd_investment.get(pid, 0):,.0f}"])
        w.writerow(["决策", f"产品{pid.value}产量", f"{decision.production[pid].total:,.0f}"])
        w.writerow(["决策", f"产品{pid.value}供货量", f"{sum(decision.shipments.get(pid, {}).values()):,}"])
    for m in MarketId:
        w.writerow(["决策", f"市场{m.value}促销费", f"{decision.promotion.get(m, 0):,.0f}"])
    w.writerow(["决策", "招聘", decision.hire])
    w.writerow(["决策", "解聘", decision.layoff])
    w.writerow(["决策", "买机器", decision.machine_purchase])
    w.writerow(["决策", "订购原材料", f"{decision.raw_material_purchase:,.0f}"])
    w.writerow(["决策", "银行贷款", f"{decision.bank_loan:,.0f}"])
    w.writerow(["决策", "发债券", f"{decision.bond_issue:,.0f}"])
    w.writerow(["决策", "分红", f"{decision.dividend:,.0f}"])
    w.writerow(["决策", "工资系数", f"{decision.wage_coefficient:.2f}"])
    w.writerow(["结果", "税前利润", f"{result.profit:,.0f}"])
    w.writerow(["结果", "纳税", f"{result.tax:,.0f}"])
    w.writerow(["结果", "期末现金", f"{result.ending_cash:,.0f}"])
    w.writerow(["结果", "可行", "是" if result.feasibility.feasible else "否"])
    return buf.getvalue()
