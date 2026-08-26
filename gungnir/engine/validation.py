"""Decision feasibility validation (pure).

The engine must never emit an infeasible decision. This module checks the hard
constraints from ``docs/rules.md`` and returns a structured report. It only
*reports* — it never mutates the decision (the platform's "随意修改决策" behavior
is exactly what we avoid).
"""

from __future__ import annotations

import math

from gungnir.config import CONFIG, Config
from gungnir.engine import production as prod
from gungnir.models import Decision, FeasibilityReport, GameState, MarketId, ProductId, Violation


def _error(code: str, message: str) -> Violation:
    return Violation(code=code, message=message, severity="error")


def validate(state: GameState, decision: Decision, config: Config = CONFIG) -> FeasibilityReport:
    """Return a feasibility report for ``decision`` given ``state``."""
    violations: list[Violation] = []
    warnings: list[str] = []

    _check_non_negative(decision, violations)
    _check_labor(decision, state, config, violations)
    _check_machine(decision, state, config, violations)
    _check_raw_material(decision, state, config, violations)
    _check_shipments(decision, state, config, violations)
    _check_headcount(decision, state, config, violations)
    _check_rnd(decision, state, violations)
    _check_wage_coefficient(decision, config, violations)
    _check_bond(decision, state, config, violations)

    feasible = not any(v.severity == "error" for v in violations)
    return FeasibilityReport(feasible=feasible, violations=violations, warnings=warnings)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_non_negative(decision: Decision, out: list[Violation]) -> None:
    if decision.hire < 0 or decision.layoff < 0:
        out.append(_error("negative_headcount", "招聘/解聘人数不能为负"))
    if decision.machine_purchase < 0:
        out.append(_error("negative_machines", "购买机器数不能为负"))
    if decision.wage_coefficient < 0:
        out.append(_error("negative_wage_coefficient", "工资系数不能为负"))
    for pid, by_market in decision.shipments.items():
        if any(q < 0 for q in by_market.values()):
            out.append(_error("negative_shipment", f"产品 {pid.value} 供货量不能为负"))
    for pid, schedule in decision.production.items():
        if min(schedule.first_normal, schedule.first_overtime, schedule.second_normal,
               schedule.second_overtime) < 0:
            out.append(_error("negative_production", f"产品 {pid.value} 产量不能为负"))


def _check_labor(decision: Decision, state: GameState, config: Config, out: list[Violation]) -> None:
    available = workers_in_service_count(state, decision)
    capacity = available * (
        config.scenario.normal_shift_hours + config.scenario.overtime_hours
    )
    need = prod.total_labor_hours(decision, config)
    if need > capacity + 1e-9:
        out.append(
            _error(
                "labor_shortfall",
                f"人力不足：需 {need:,.0f} 人时，可用 {capacity:,.0f} 人时（{available} 人 × 780 时）",
            )
        )


def _check_machine(decision: Decision, state: GameState, config: Config, out: list[Violation]) -> None:
    # TODO(待确认): exact multi-shift machine capacity. Working model = two
    # normal shifts per machine (2 * 520 = 1040 时). The reference tool's LP
    # example suggests a stricter per-shift model (~780 时/机器/班); reconcile in M1.
    capacity = state.machines * config.scenario.normal_shift_hours * 2
    need = prod.total_machine_hours(decision, config)
    if need > capacity + 1e-9:
        out.append(
            _error(
                "machine_shortfall",
                f"机时不足：需 {need:,.0f} 机时，可用 {capacity:,.0f} 机时（{state.machines} 台 × 1040 时）",
            )
        )


def _check_raw_material(decision: Decision, state: GameState, config: Config, out: list[Violation]) -> None:
    usable = state.raw_material_units + (
        decision.raw_material_purchase / config.raw_material.standard_price_per_unit
    ) * config.scenario.raw_material_usable_ratio
    need = prod.raw_material_units_used(decision, config)
    if need > usable + 1e-9:
        out.append(
            _error(
                "material_shortfall",
                f"原材料不足：需 {need:,.0f} 单位，可用 {usable:,.0f} 单位",
            )
        )


def _check_shipments(decision: Decision, state: GameState, config: Config, out: list[Violation]) -> None:
    for pid in ProductId:
        opening = state.products[pid].factory_inventory
        produced = decision.production[pid].total if pid in decision.production else 0.0
        producible = opening + produced * config.scenario.producible_ratio
        shipped = sum(decision.shipments.get(pid, {}).values())
        if shipped > producible + 1e-9:
            out.append(
                _error(
                    "shipment_infeasible",
                    f"产品 {pid.value} 供货 {shipped:,.0f} 件超过可运出量 {producible:,.0f} 件",
                )
            )


def _check_headcount(decision: Decision, state: GameState, config: Config, out: list[Violation]) -> None:
    workers = state.workers
    if workers <= 0:
        return
    max_hire = math.floor(workers * config.labor.max_hire_ratio)
    if decision.hire > max_hire:
        out.append(_error("hire_limit", f"招聘 {decision.hire} 人超过上限 {max_hire} 人（期初 50%）"))
    max_layoff = math.floor(workers * config.labor.max_layoff_ratio)
    if decision.layoff > max_layoff:
        out.append(_error("layoff_limit", f"解聘 {decision.layoff} 人超过上限 {max_layoff} 人（期初 10%）"))
    min_layoff = math.floor(workers * config.labor.retirement_rate)
    if decision.layoff < min_layoff:
        out.append(
            _error("layoff_below_retirement", f"解聘 {decision.layoff} 人低于正常退休 {min_layoff} 人，系统会改动")
        )


def _check_rnd(decision: Decision, state: GameState, out: list[Violation]) -> None:
    for pid, invest in decision.rnd_investment.items():
        if invest < 0:
            out.append(_error("negative_rnd", f"产品 {pid.value} 研发投入不能为负"))
        current_level = state.products[pid].rnd_level
        if invest > 0 and current_level >= 5:
            out.append(_error("rnd_max", f"产品 {pid.value} 已达最高研发等级 5"))
    for pid in decision.production:
        if decision.production[pid].total > 0 and state.products[pid].rnd_level < 1:
            out.append(_error("rnd_required", f"生产产品 {pid.value} 需先投入等级 1 研发费"))


def _check_wage_coefficient(decision: Decision, config: Config, out: list[Violation]) -> None:
    if decision.wage_coefficient < config.labor.min_wage_coefficient:
        out.append(_error("wage_coefficient_below_min", "工资系数不能小于 1.0"))


def _check_bond(decision: Decision, state: GameState, config: Config, out: list[Violation]) -> None:
    if decision.bond_issue < 0:
        out.append(_error("negative_bond", "发债券不能为负"))
        return
    ceiling = state.net_assets * config.finance.bond_max_ratio_of_equity
    if decision.bond_issue > ceiling + 1e-9:
        out.append(
            _error("bond_limit", f"发债券 {decision.bond_issue:,.0f} 元超过净资产上限 {ceiling:,.0f} 元（50%）")
        )


def workers_in_service_count(state: GameState, decision: Decision) -> int:
    return max(0, state.workers - decision.layoff)
