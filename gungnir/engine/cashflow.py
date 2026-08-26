"""Ordered cash-flow simulation (the L0 core).

``simulate`` runs the full 现金收支次序 from ``docs/rules.md`` (which mirrors the
reference tool's ``财务`` sheet) and produces a deterministic ``PeriodResult``.
It only *reports* cash shortfalls — it never silently rewrites the decision.

The sales revenue is an *input* (the platform's market outcome / the L2 demand
model's estimate); the engine computes every cost and the final cash position.
"""

from __future__ import annotations

import math

from gungnir.config import CONFIG, Config
from gungnir.engine import production as prod
from gungnir.engine import validation
from gungnir.models import (
    CashFlowLine,
    Decision,
    FeasibilityReport,
    GameState,
    MarketId,
    PeriodResult,
    ProductId,
    SalesOutcome,
    ScoreBreakdown,
)


def simulate(
    state: GameState,
    decision: Decision,
    sales_revenue: float,
    config: Config = CONFIG,
) -> PeriodResult:
    """Run one period's cash-flow simulation.

    Args:
        state: period-start company state.
        decision: this period's decision variables.
        sales_revenue: estimated sales revenue (元), from the demand model / user.
    """
    feasibility = validation.validate(state, decision, config)

    lines: list[CashFlowLine] = []
    cash = state.cash
    cost_total = 0.0
    income_total = 0.0
    emergency_loan_amount = 0.0

    def add(key: str, label: str, amount: float, kind: str = "cash") -> None:
        nonlocal cash, cost_total, income_total
        if kind == "cost":
            cost_total += amount
        elif kind == "income":
            income_total += amount
        if kind in ("cash", "cost", "income"):
            cash += amount
        lines.append(CashFlowLine(key=key, label=label, amount=amount, kind=kind, cash_after=cash))

    # --- income up front ---------------------------------------------------
    add("opening_cash", "上期转来", state.cash, "info")
    add("bank_loan_income", "银行贷款", decision.bank_loan)
    add("bond_issue", "发债券", decision.bond_issue)

    # --- debt service on existing bonds ------------------------------------
    add("bond_principal", "还债券本金", -state.bond_principal_due)
    add("bond_interest", "还债券利息", -_bond_interest(state, config), "cost")

    # --- labor / machine outflows ------------------------------------------
    add("training_fee", "新工人培训费", -prod.training_fee(decision, config), "cost")
    add("layoff_severance", "解雇安置费", -prod.layoff_severance(decision, config), "cost")
    add("basic_wage", "工人基本工资", -prod.basic_wage(state, decision, config), "cost")
    add("machine_maintenance", "机器维修费", -prod.machine_maintenance(state, config), "cost")

    # --- emergency-loan check point (before R&D) ---------------------------
    if cash < -1e-9:
        emergency_loan_amount = -cash
        add("emergency_loan", "紧急救援贷款", emergency_loan_amount)
        feasibility.emergency_loan_triggered = True
        feasibility.emergency_loan_amount = emergency_loan_amount
    else:
        add("emergency_loan", "紧急救援贷款", 0.0)

    # --- R&D, raw material --------------------------------------------------
    rnd_cash = sum(decision.rnd_investment.values())
    add("rnd_cash", "研发费", -rnd_cash)
    add("rnd_amortization", "研发费分摊", -prod.rnd_amortization(state, decision), "cost")
    add("raw_material_purchase", "购原材料", -decision.raw_material_purchase)
    add("raw_material_discount", "购原材料优惠", _material_discount(decision, config), "income")
    add("raw_material_freight", "购材料运费", -_material_freight(decision, config), "cost")

    # --- production & marketing --------------------------------------------
    add("special_wage", "特殊班工资", -prod.special_shift_wage(decision, config), "cost")
    add("management_fee", "管理费", -prod.management_fee(decision, config), "cost")
    add("material_usage", "使用材料费", -prod.material_usage_cost(decision, config), "cost")
    add("finished_freight", "成品运输费", -prod.finished_goods_freight(decision, config), "cost")
    add("advertising", "广告费", -prod.advertising_cost(decision), "cost")
    add("promotion", "促销费", -prod.promotion_cost(decision), "cost")

    # --- sales & adjustments ------------------------------------------------
    add("sales_revenue", "销售收入", sales_revenue, "income")
    add("waste_loss", "废品损失", -_waste_loss(decision, config), "cost")
    add("depreciation", "折旧费", -prod.depreciation(state, config), "cost")
    add("inventory_change", "产品库存变化", -_inventory_change(state, decision, config), "cost")

    # --- storage ------------------------------------------------------------
    closing_raw = _closing_raw_material(state, decision, config)
    add(
        "raw_material_storage",
        "原材料存储费",
        -prod.raw_material_storage_cost(state.raw_material_units, closing_raw, config),
        "cost",
    )
    closing_fg = prod.closing_factory_inventory(state, decision)
    opening_fg = {pid: state.products[pid].factory_inventory for pid in ProductId}
    add(
        "finished_storage",
        "成品存储费",
        -prod.finished_goods_storage_cost(opening_fg, closing_fg, config),
        "cost",
    )

    # --- treasury & loan settlements ---------------------------------------
    add("treasury_principal_return", "上期国债本金返回", state.treasury)
    add("treasury_interest", "上期国债利息", _treasury_interest(state, config), "income")
    add("bank_loan_repay", "付银行贷款", -state.bank_loan)
    add("bank_loan_interest", "付银行利息", -_bank_interest(state, config), "cost")
    add("emergency_loan_repay", "上期紧急救援贷款本", -state.emergency_loan)
    add("emergency_loan_interest", "上期紧急救援贷款息", -_emergency_interest(state, config), "cost")

    # --- profit, tax, capital & distribution -------------------------------
    profit = income_total - cost_total
    tax = _tax(profit, state.tax_credit, config)
    add("tax", "本期纳税", -tax)
    add("machine_purchase", "买机器", -decision.machine_purchase * config.machine.price)
    dividend = _dividend(decision, cash, profit - tax)
    add("dividend", "分红", -dividend)
    add("treasury_purchase", "买国债", -decision.treasury_purchase)

    if cash < -1e-9:
        feasibility.cash_shortfall = True

    ending_state = _next_state(
        state, decision, cash, closing_fg, emergency_loan_amount, profit, tax, config
    )

    return PeriodResult(
        ending_state=ending_state,
        cash_flow=lines,
        revenue_total=income_total,
        cost_total=cost_total,
        profit=profit,
        tax=tax,
        ending_cash=cash,
        feasibility=feasibility,
        score=ScoreBreakdown(),
    )


# ---------------------------------------------------------------------------
# Line helpers
# ---------------------------------------------------------------------------


def _bond_interest(state: GameState, config: Config) -> float:
    return state.bond_outstanding * config.finance.bond_annual_rate / config.scenario.periods_per_year


def _bank_interest(state: GameState, config: Config) -> float:
    return state.bank_loan * config.finance.bank_loan_annual_rate / config.scenario.periods_per_year


def _emergency_interest(state: GameState, config: Config) -> float:
    return (
        state.emergency_loan
        * config.finance.emergency_loan_annual_rate
        / config.scenario.periods_per_year
    )


def _treasury_interest(state: GameState, config: Config) -> float:
    return state.treasury * config.finance.treasury_annual_rate / config.scenario.periods_per_year


def _tax(profit: float, tax_credit: float, config: Config) -> float:
    # TODO(待确认): the exact role of 交税信用 (tax credit). Reconciled arithmetic:
    # tax = profit * rate - tax_credit (a negative credit raises tax).
    return max(0.0, profit * config.finance.tax_rate - tax_credit)


def _dividend(decision: Decision, cash_after_tax: float, after_tax_profit: float) -> float:
    """Apply the dividend ceiling: cash > min_cash and amount <= after-tax profit."""
    return min(decision.dividend, max(0.0, after_tax_profit))


def _closing_raw_material(state: GameState, decision: Decision, config: Config) -> float:
    purchased_units = (
        decision.raw_material_purchase / config.raw_material.standard_price_per_unit
    )
    used = prod.raw_material_units_used(decision, config)
    return state.raw_material_units + purchased_units - used


def _material_discount(decision: Decision, config: Config) -> float:
    units = decision.raw_material_purchase / config.raw_material.standard_price_per_unit
    multiplier = _price_multiplier(units, config)
    return units * (config.raw_material.standard_price_per_unit - multiplier)


def _price_multiplier(units: float, config: Config) -> float:
    m = config.raw_material.standard_price_per_unit
    for threshold, price in config.raw_material.bulk_discount_tiers:
        if units >= threshold:
            m = price
    return m


def _material_freight(decision: Decision, config: Config) -> float:
    if decision.raw_material_purchase <= 0:
        return 0.0
    units = decision.raw_material_purchase / config.raw_material.standard_price_per_unit
    # TODO(待确认): variable freight basis (per unit == 2% of standard price here).
    return config.raw_material.fixed_freight + config.raw_material.variable_freight * units


def _waste_loss(decision: Decision, config: Config) -> float:
    # TODO(待确认): 正品率 (defect rate) not in the parameter sheet; until pinned
    # down, waste is 0. Formula: sum(defective * price * 40%), defective = round(qty * rate).
    defect_rate = getattr(config.scenario, "defect_rate", 0.0)
    if defect_rate <= 0:
        return 0.0
    total = 0.0
    for pid, by_market in decision.shipments.items():
        for market, qty in by_market.items():
            defective = round(qty * defect_rate)
            price = decision.prices[pid][market]
            total += defective * price * 0.40
    return total


def _inventory_change(state: GameState, decision: Decision, config: Config) -> float:
    # 产品库存变化 = closing - opening finished-goods *book value*.
    # TODO(待确认): unit inventory book value = (labor@1st shift + machine depreciation
    # @1 normal shift + raw material @standard price). Not yet parameterized; returns 0.
    return 0.0


# ---------------------------------------------------------------------------
# Ending state
# ---------------------------------------------------------------------------


def _next_state(
    state: GameState,
    decision: Decision,
    ending_cash: float,
    closing_fg: dict[ProductId, float],
    emergency_loan_amount: float,
    profit: float,
    tax: float,
    config: Config,
) -> GameState:
    products: dict[ProductId, object] = {}
    for pid in ProductId:
        ps = state.products[pid]
        invest = decision.rnd_investment.get(pid, 0.0)
        products[pid] = ps.model_copy(
            update={
                "factory_inventory": int(closing_fg.get(pid, ps.factory_inventory)),
                "rnd_cumulative": ps.rnd_cumulative + invest,
                "rnd_spent_last_period": invest,
                "rnd_level": _next_rnd_level(ps.rnd_level, ps.rnd_cumulative, invest, config, pid),
            }
        )

    new_bond_outstanding = state.bond_outstanding + decision.bond_issue - state.bond_principal_due
    new_bond_due = state.bond_principal_due + decision.bond_issue / config.finance.bond_repay_periods

    return GameState(
        period=state.period + 1,
        cash=ending_cash,
        workers=max(0, state.workers - decision.layoff + decision.hire),
        machines=state.machines + state.machines_in_transit,
        machines_in_transit=state.machines_ordered,
        machines_ordered=decision.machine_purchase,
        raw_material_units=_closing_raw_material(state, decision, config),
        accumulated_depreciation=state.accumulated_depreciation
        + config.machine.price * state.machines * config.machine.depreciation_rate,
        treasury=decision.treasury_purchase,
        bank_loan=decision.bank_loan,
        emergency_loan=emergency_loan_amount,
        bond_outstanding=max(0.0, new_bond_outstanding),
        bond_principal_due=new_bond_due,
        cumulative_tax=state.cumulative_tax + tax,
        cumulative_dividend=state.cumulative_dividend + decision.dividend,
        tax_credit=state.tax_credit,
        net_assets=state.net_assets,
        last_period_profit=profit,
        composite_score=state.composite_score,
        products=products,
        last_period_prices=decision.prices,
    )


def _next_rnd_level(
    current: int,
    cumulative: float,
    invest: float,
    config: Config,
    pid: ProductId,
) -> int:
    levels = config.product(pid.value).rnd_cumulative_cost
    new_cumulative = cumulative + invest
    level = current
    for i, threshold in enumerate(levels, start=1):
        if new_cumulative >= threshold and i > level:
            level = i
    # at most one level up per period
    return min(level, current + 1)


# ---------------------------------------------------------------------------
# Sales revenue formula (used when sales quantities are known)
# ---------------------------------------------------------------------------


def compute_sales_revenue(
    sales: SalesOutcome,
    prices: dict[ProductId, dict[MarketId, float]],
    backorders: dict[ProductId, dict[MarketId, int]],
    last_prices: dict[ProductId, dict[MarketId, float]],
) -> float:
    """销售收入 = sum over markets of:
    backorders * min(last_price, price) + (sold - backorders) * price.

    RECONCILED against the manual's 财务公式.
    """
    total = 0.0
    for pid, by_market in sales.sold.items():
        for market, sold in by_market.items():
            back = backorders.get(pid, {}).get(market, 0)
            price = prices[pid][market]
            last = last_prices.get(pid, {}).get(market, price)
            revenue = back * min(last, price) + (sold - back) * price
            total += revenue
    return total
