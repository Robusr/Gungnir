"""Production, resource and cost computation (pure functions).

Every function here is deterministic and side-effect free. Costs are computed
from the decision and the current state; the ordered cash-flow assembly lives in
``cashflow.py``. Values reconciled against the reference decision tool are marked
``RECONCILED`` with the corresponding ``财务`` cell.
"""

from __future__ import annotations

import math

from gungnir.config import CONFIG, Config
from gungnir.models import Decision, GameState, MarketId, ProductId, ShiftId


# ---------------------------------------------------------------------------
# Quantities
# ---------------------------------------------------------------------------


def production_totals(decision: Decision) -> dict[ProductId, float]:
    """Total output per product across all shift classes (件)."""
    return {
        pid: decision.production[pid].total for pid in decision.production
    }


def labor_hours(decision: Decision, config: Config = CONFIG) -> dict[ShiftId, float]:
    """Labor hours per shift class, summed over products (时)."""
    hours = {s: 0.0 for s in ShiftId}
    for pid, schedule in decision.production.items():
        lh = config.product(pid.value).labor_hours
        for shift in ShiftId:
            hours[shift] += schedule.by_shift(shift) * lh
    return hours


def machine_hours(decision: Decision, config: Config = CONFIG) -> dict[ShiftId, float]:
    """Machine hours per shift class, summed over products (时)."""
    hours = {s: 0.0 for s in ShiftId}
    for pid, schedule in decision.production.items():
        mh = config.product(pid.value).machine_hours
        for shift in ShiftId:
            hours[shift] += schedule.by_shift(shift) * mh
    return hours


def total_labor_hours(decision: Decision, config: Config = CONFIG) -> float:
    return sum(labor_hours(decision, config).values())


def total_machine_hours(decision: Decision, config: Config = CONFIG) -> float:
    return sum(machine_hours(decision, config).values())


def raw_material_units_used(decision: Decision, config: Config = CONFIG) -> float:
    """Raw-material units consumed by the production plan."""
    return sum(
        schedule.total * config.product(pid.value).raw_material_units
        for pid, schedule in decision.production.items()
    )


# ---------------------------------------------------------------------------
# Labor / wage
# ---------------------------------------------------------------------------


def workers_in_service(state: GameState, decision: Decision) -> int:
    """Retained (full-pay) workers after layoffs; new workers are separate."""
    return max(0, state.workers - decision.layoff)


def effective_workers_for_wage(state: GameState, decision: Decision) -> float:
    """Full-time-equivalent headcount for basic wage (new workers 4->1)."""
    retained = workers_in_service(state, decision)
    return retained + decision.hire / CONFIG.labor.new_worker_equiv_denominator


def basic_wage(state: GameState, decision: Decision, config: Config = CONFIG) -> float:
    """基本工资 = in-service FTE * 520 * base_hourly_wage * wage_coefficient.

    RECONCILED against 财务!R8: 145 * 520 * 3 * 1.02 = 230,724.
    """
    fte = effective_workers_for_wage(state, decision)
    return (
        fte
        * config.scenario.normal_shift_hours
        * config.labor.base_hourly_wage
        * decision.wage_coefficient
    )


def special_shift_wage(
    decision: Decision, config: Config = CONFIG
) -> float:
    """特殊班工资 = overtime + second-shift wages, scaled by wage_coefficient.

    Working model (TODO 待确认): shift-based hourly rates with overtime = 1.5x.
    The exact platform formula is reconciled against 财务!R16 in M1; the current
    rates are ``config.labor.*_wage``.
    """
    labor = labor_hours(decision, config)
    raw = (
        labor[ShiftId.FIRST_OVERTIME] * config.labor.first_overtime_wage
        + labor[ShiftId.SECOND_NORMAL] * config.labor.second_normal_wage
        + labor[ShiftId.SECOND_OVERTIME] * config.labor.second_overtime_wage
    )
    return raw * decision.wage_coefficient


def training_fee(decision: Decision, config: Config = CONFIG) -> float:
    return decision.hire * config.labor.new_worker_training_fee


def layoff_severance(decision: Decision, config: Config = CONFIG) -> float:
    return decision.layoff * config.labor.layoff_severance_fee


# ---------------------------------------------------------------------------
# Production / logistics costs
# ---------------------------------------------------------------------------


def management_fee(decision: Decision, config: Config = CONFIG) -> float:
    """管理费 = per-(product, shift) fixed setup cost for shifts actually used.

    RECONCILED against 财务!R17: A(1st) 4000 + B(1st) 6000 + B(2nd) 7000 = 17,000.
    """
    total = 0.0
    for pid, schedule in decision.production.items():
        p = config.product(pid.value)
        if schedule.first_normal > 0 or schedule.first_overtime > 0:
            total += p.first_shift_fixed_cost
        if schedule.second_normal > 0 or schedule.second_overtime > 0:
            total += p.second_shift_fixed_cost
    return total


def material_usage_cost(decision: Decision, config: Config = CONFIG) -> float:
    """使用材料费 = units used * standard price (成本, not cash).

    RECONCILED against 财务!R18: 405,840.
    """
    return raw_material_units_used(decision, config) * config.raw_material.standard_price_per_unit


def machine_maintenance(state: GameState, config: Config = CONFIG) -> float:
    """机器维修费 = machines * maintenance_fee.

    RECONCILED against 财务!R9: 100 * 200 = 20,000.
    """
    return state.machines * config.machine.maintenance_fee


def depreciation(state: GameState, config: Config = CONFIG) -> float:
    """折旧费 = machine_price * machines * depreciation_rate (成本, not cash).

    RECONCILED against 财务!R24: 40,000 * 100 * 5% = 200,000.
    """
    return config.machine.price * state.machines * config.machine.depreciation_rate


def advertising_cost(decision: Decision) -> float:
    """广告费 (元). RECONCILED against 财务!R20: 70k + 70k = 140,000."""
    return sum(decision.advertising.values())


def promotion_cost(decision: Decision) -> float:
    """促销费 (元). RECONCILED against 财务!R21: 3 * 70k = 210,000."""
    return sum(decision.promotion.values())


def finished_goods_freight(decision: Decision, config: Config = CONFIG) -> float:
    """成品运输费 = per-market [fixed if shipped>0 + variable*qty].

    RECONCILED against 财务!R19: 490,324.
    """
    total = 0.0
    for pid, by_market in decision.shipments.items():
        p = config.product(pid.value)
        for market in MarketId:
            qty = by_market.get(market, 0)
            if qty <= 0:
                continue
            total += p.fixed_freight[market_idx(market)] + p.variable_freight[
                market_idx(market)
            ] * qty
    return total


def market_idx(market: MarketId) -> int:
    return {MarketId.M1: 0, MarketId.M2: 1, MarketId.M3: 2}[market]


def rnd_amortization(state: GameState, decision: Decision) -> float:
    """研发费分摊 = (上期研发 + 本期研发) / 2 (成本, not cash)."""
    last = sum(p.rnd_spent_last_period for p in state.products.values())
    current = sum(decision.rnd_investment.values())
    return (last + current) / 2.0


# ---------------------------------------------------------------------------
# Storage costs
# ---------------------------------------------------------------------------


def raw_material_storage_cost(
    opening_units: float, closing_units: float, config: Config = CONFIG
) -> float:
    """原材料存储费 = rate * avg inventory value (0.05 元/元/期)."""
    avg_value = (opening_units + closing_units) / 2.0 * config.raw_material.standard_price_per_unit
    return avg_value * config.raw_material.storage_cost_rate


def finished_goods_storage_cost(
    opening: dict[ProductId, float], closing: dict[ProductId, float], config: Config = CONFIG
) -> float:
    """成品存储费 = unit cost * avg inventory per product.

    Inventories are clamped to >= 0 (a negative closing inventory means the
    shipment decision was infeasible and is flagged separately).
    """
    total = 0.0
    for pid in ProductId:
        op = max(0.0, opening.get(pid, 0.0))
        cl = max(0.0, closing.get(pid, 0.0))
        total += config.product(pid.value).inventory_cost_per_unit * (op + cl) / 2.0
    return total


# ---------------------------------------------------------------------------
# Ending inventory
# ---------------------------------------------------------------------------


def closing_factory_inventory(
    state: GameState, decision: Decision
) -> dict[ProductId, float]:
    """Factory finished-goods inventory after production and shipments (件).

    May go negative if shipments exceed (opening + production) — that is a
    feasibility violation flagged separately.
    """
    closing: dict[ProductId, float] = {}
    for pid in ProductId:
        opening = state.products[pid].factory_inventory
        produced = decision.production[pid].total if pid in decision.production else 0.0
        shipped = sum(decision.shipments.get(pid, {}).values())
        closing[pid] = opening + produced - shipped
    return closing
