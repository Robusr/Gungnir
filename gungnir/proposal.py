"""Decision proposal (M2): turn a ``GameState`` into a *feasible* ``Decision``.

The proposer is deliberately conservative — it is the trust-anchor baseline, not
an optimizer. It

1. prices at the last period's level (or a config default),
2. unlocks level-1 R&D for any product that has not started,
3. forecasts demand (L2) with zero marketing spend,
4. sizes production to meet that demand, subject to the joint labour / machine
   capacity (scaled down uniformly on whichever resource binds),
5. ships at most (opening inventory + 75% of production),
6. purchases raw material to cover production, and
7. finances any cash shortfall — first bonds (≤ 50% net assets), then bank loans
   (≤ credit limit), scaling production down only as a last resort.

The guarantee for any well-formed state is: ``ProposalResult.feasible`` is True,
no emergency loan is triggered, and running cash never goes negative. Optimizing
this baseline (marketing spend, pricing, headcount growth, machine buys, R&D
ramp, treasury) is M3.
"""

from __future__ import annotations

import math

from gungnir import demand
from gungnir.config import CONFIG, Config
from gungnir.engine import simulate
from gungnir.models import (
    Decision,
    GameState,
    MarketId,
    ProductId,
    ProductionSchedule,
    ProductState,
    ProposalResult,
)

_PID_INDEX = {ProductId.A: 0, ProductId.B: 1}
_MARKET_INDEX = {MarketId.M1: 0, MarketId.M2: 1, MarketId.M3: 2}


def propose(
    state: GameState,
    config: Config = CONFIG,
    prices: dict[ProductId, dict[MarketId, float]] | None = None,
) -> ProposalResult:
    """Propose a feasible decision for ``state``.

    ``prices`` may override the pricing step (used by the M3 optimizer); when
    omitted, last-period prices (or config defaults) are used.
    """
    state = _normalize_state(state)
    products = state.products

    if prices is None:
        prices = _default_prices(state, config)
    rnd = _rnd_investment(products, config)
    advertising = {pid: 0.0 for pid in ProductId}
    promotion = {m: 0.0 for m in MarketId}
    grade = {pid: max(1.0, products[pid].grade) for pid in ProductId}
    forecast = demand.forecast_demand(state, prices, advertising, promotion, grade, config)
    layoff = _min_layoff(state, config)
    hire = 0

    # Scale production down only if the physical+financial plan is infeasible at
    # full demand (rare: happens when debt service alone exceeds financing room).
    scale = 1.0
    decision: Decision | None = None
    result = None
    while scale >= 0.05:
        production, shipments = _plan_production(state, forecast, scale, config)
        raw_purchase = _raw_material_purchase(state, production, config)
        decision = Decision(
            prices=prices,
            advertising=advertising,
            promotion=promotion,
            shipments=shipments,
            production=production,
            rnd_investment=rnd,
            hire=hire,
            layoff=layoff,
            machine_purchase=0,
            raw_material_purchase=raw_purchase,
            bank_loan=0.0,
            bond_issue=0.0,
            treasury_purchase=0.0,
            dividend=0.0,
            wage_coefficient=1.0,
        )
        result, decision = _finance_repair(state, decision, config)
        if (
            result.feasibility.feasible
            and not result.feasibility.emergency_loan_triggered
            and not result.feasibility.cash_shortfall
        ):
            break
        scale *= 0.8

    assert decision is not None and result is not None
    feasible = (
        result.feasibility.feasible
        and not result.feasibility.emergency_loan_triggered
        and not result.feasibility.cash_shortfall
    )
    rationale = _rationale(state, decision, forecast, result, config)
    return ProposalResult(
        decision=decision,
        result=result,
        demand=forecast,
        rationale=rationale,
        feasible=feasible,
        state=state,
    )


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def _normalize_state(state: GameState) -> GameState:
    """Ensure both products exist so validation never hits a missing key."""
    if ProductId.A in state.products and ProductId.B in state.products:
        return state
    products = dict(state.products)
    for pid in ProductId:
        if pid not in products:
            products[pid] = ProductState()
    return state.model_copy(update={"products": products})


def _default_prices(state: GameState, config: Config) -> dict[ProductId, dict[MarketId, float]]:
    prices: dict[ProductId, dict[MarketId, float]] = {}
    for pid in ProductId:
        ref = config.demand.reference_price[_PID_INDEX[pid]]
        prices[pid] = {}
        for m in MarketId:
            prices[pid][m] = state.last_period_prices.get(pid, {}).get(m, ref)
    return prices


def _rnd_investment(products, config: Config) -> dict[ProductId, float]:
    rnd: dict[ProductId, float] = {}
    for pid in ProductId:
        if products[pid].rnd_level == 0:
            rnd[pid] = config.product(pid.value).rnd_cumulative_cost[0]
        else:
            rnd[pid] = 0.0
    return rnd


def _min_layoff(state: GameState, config: Config) -> int:
    if state.workers <= 0:
        return 0
    return math.floor(state.workers * config.labor.retirement_rate)


def _plan_production(state: GameState, forecast, scale: float, config: Config):
    """Jointly size production and shipments under labour/machine capacity.

    Returns ``(production, shipments)``. All output is placed on the first normal
    shift (the cheapest and, in the current engine model, unconstrained by a
    separate per-shift ceiling). The binding resource is found by a uniform
    scale-down of desired production.
    """
    desired: dict[ProductId, float] = {}
    for pid in ProductId:
        # A product with no R&D level yet cannot be produced this period (the
        # proposal invests to unlock it, but production must wait a period).
        if state.products[pid].rnd_level < 1:
            desired[pid] = 0.0
            continue
        target_ship = sum(forecast[pid].values())
        opening = state.products[pid].factory_inventory
        desired[pid] = max(0.0, (target_ship - opening) / config.scenario.producible_ratio) * scale

    labor_need = sum(desired[pid] * config.product(pid.value).labor_hours for pid in ProductId)
    machine_need = sum(desired[pid] * config.product(pid.value).machine_hours for pid in ProductId)

    workers = max(0, state.workers - _min_layoff(state, config))
    labor_cap = workers * (config.scenario.normal_shift_hours + config.scenario.overtime_hours)
    # TODO(待确认): exact multi-shift machine capacity (engine model = 2 * 520).
    machine_cap = state.machines * config.scenario.normal_shift_hours * 2

    lam = 1.0
    if labor_need > 0.0 and labor_cap < labor_need:
        lam = min(lam, labor_cap / labor_need)
    if machine_need > 0.0 and machine_cap < machine_need:
        lam = min(lam, machine_cap / machine_need)

    production: dict[ProductId, ProductionSchedule] = {}
    shipments: dict[ProductId, dict[MarketId, int]] = {}
    for pid in ProductId:
        q = math.floor(desired[pid] * lam)
        production[pid] = ProductionSchedule(first_normal=float(q))
        producible = state.products[pid].factory_inventory + q * config.scenario.producible_ratio
        shipments[pid] = _allocate(forecast[pid], producible)
    return production, shipments


def _allocate(forecast: dict[MarketId, float], producible: float) -> dict[MarketId, int]:
    """Split ``floor(producible)`` units across markets by descending demand."""
    remaining = math.floor(producible)
    out: dict[MarketId, int] = {}
    for m in sorted(MarketId, key=lambda m: -forecast.get(m, 0.0)):
        q = min(math.floor(forecast.get(m, 0.0)), remaining)
        out[m] = q
        remaining -= q
    return out


def _raw_material_purchase(state: GameState, production, config: Config) -> float:
    need = sum(
        production[pid].total * config.product(pid.value).raw_material_units
        for pid in ProductId
    )
    if need <= state.raw_material_units:
        return 0.0
    short = need - state.raw_material_units
    units = short / config.scenario.raw_material_usable_ratio
    return math.ceil(units) * config.raw_material.standard_price_per_unit


def _finance_repair(state: GameState, decision: Decision, config: Config):
    """Add bond/bank financing until cash never goes negative.

    Returns ``(result, decision)``. Bond and bank income both arrive up front and
    are (essentially) un-repaid this period, so a single positive injection moves
    the whole running balance up. Bonds are preferred (amortised, no next-period
    balloon) up to 50% of net assets, then bank loans up to the credit limit.
    """
    decision = decision.model_copy(deep=True)
    bank_loan = 0.0
    bond_issue = 0.0
    result = None
    for _ in range(20):
        revenue = _sales_revenue(state, decision.shipments, decision.prices)
        result = simulate(state, decision, revenue, config)
        if not (result.feasibility.emergency_loan_triggered or result.feasibility.cash_shortfall):
            return result, decision
        deficit = 0.0
        if result.feasibility.emergency_loan_triggered:
            deficit = max(deficit, result.feasibility.emergency_loan_amount)
        if result.feasibility.cash_shortfall:
            deficit = max(deficit, -result.ending_cash)
        deficit += 1.0  # rounding buffer

        bond_headroom = max(
            0.0,
            state.net_assets * config.finance.bond_max_ratio_of_equity - bond_issue,
        )
        add_bond = min(deficit, bond_headroom)
        bond_issue += add_bond
        deficit -= add_bond

        if deficit > 0.0:
            bank_headroom = max(0.0, config.finance.credit_limit - bank_loan)
            bank_loan += min(deficit, bank_headroom)

        decision.bank_loan = bank_loan
        decision.bond_issue = bond_issue
        if add_bond <= 0.0 and deficit > 0.0 and bank_headroom <= 0.0:
            # No financing room left; report the infeasible result so the caller
            # scales production down.
            return result, decision
    return result, decision


def _sales_revenue(state: GameState, shipments, prices) -> float:
    total = 0.0
    for pid in ProductId:
        back = state.products[pid].backorders
        last = state.last_period_prices.get(pid, {})
        for m in MarketId:
            shipped = shipments.get(pid, {}).get(m, 0)
            b = min(back.get(m, 0), shipped)
            price = prices[pid][m]
            last_price = last.get(m, price)
            total += b * min(last_price, price) + (shipped - b) * price
    return total


def evaluate(state: GameState, decision: Decision, config: Config = CONFIG):
    """Simulate an arbitrary decision, estimating revenue from the L2 demand model.

    This is the re-validation primitive for the M5 "adjust" step: the user edits
    a decision and the engine re-runs the cash flow with demand-capped revenue
    (``sold = min(shipped, forecast)``). Returns the engine's ``PeriodResult``,
    whose ``feasibility`` field tells the user whether the edit is allowed.
    """
    state = _normalize_state(state)
    grade = {pid: max(1.0, state.products[pid].grade) for pid in ProductId}
    forecast = demand.forecast_demand(
        state, decision.prices, decision.advertising, decision.promotion, grade, config
    )
    revenue = 0.0
    for pid in ProductId:
        back = state.products[pid].backorders
        last = state.last_period_prices.get(pid, {})
        ref = config.demand.reference_price[_PID_INDEX[pid]]
        for m in MarketId:
            shipped = decision.shipments.get(pid, {}).get(m, 0)
            price = decision.prices.get(pid, {}).get(m, ref)
            sold = min(float(shipped), forecast[pid][m])
            b = min(back.get(m, 0), sold)
            last_price = last.get(m, price)
            revenue += b * min(last_price, price) + (sold - b) * price
    return simulate(state, decision, revenue, config)


# ---------------------------------------------------------------------------
# Rationale (Chinese, for L4/L5)
# ---------------------------------------------------------------------------


def _rationale(state, decision, forecast, result, config) -> list[str]:
    lines: list[str] = []
    for pid in ProductId:
        p = decision.prices[pid]
        if state.last_period_prices.get(pid):
            lines.append(
                f"产品 {pid.value} 沿用上期价格："
                + "/".join(f"{int(round(p[m]))}" for m in MarketId)
            )
        else:
            lines.append(
                f"产品 {pid.value} 采用参考价："
                + "/".join(f"{int(round(p[m]))}" for m in MarketId)
            )
    for pid in ProductId:
        fc = sum(forecast[pid].values())
        sh = sum(decision.shipments[pid].values())
        prod = decision.production[pid].total
        lines.append(
            f"产品 {pid.value} 预测需求 {fc:,.0f} 件，供货 {sh:,} 件，本期生产 {prod:,.0f} 件"
        )
    lines.append(
        f"招聘 {decision.hire} 人、解聘 {decision.layoff} 人（3% 正常退休）"
    )
    if decision.raw_material_purchase > 0:
        lines.append(f"订购原材料 {decision.raw_material_purchase:,.0f} 元")
    else:
        lines.append("原材料库存充足，无需订购")
    if decision.bond_issue > 0:
        lines.append(f"发行债券 {decision.bond_issue:,.0f} 元")
    if decision.bank_loan > 0:
        lines.append(f"银行贷款 {decision.bank_loan:,.0f} 元")
    if decision.bond_issue == 0 and decision.bank_loan == 0:
        lines.append("资金充足，无需融资")
    lines.append(f"预计期末现金 {result.ending_cash:,.0f} 元，税前利润 {result.profit:,.0f} 元")
    return lines
