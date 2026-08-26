"""Central parameter configuration for the Gungnir rule engine.

This is the single source of truth for every numeric rule parameter (L0 trust
anchor). It is deliberately a dependency-free module (pure ``dataclasses``) so
that the rule engine can import and validate it in any environment.

All values are captured for scenario **5A** (2 products x 3 markets, 10 firms)
as published by the BizSim platform (edu.ibizsim.cn) and cross-checked against
``docs/rules.md`` and the reference decision tool ``决策工具.xls``.

Conventions
-----------
* Money ......... 元 (yuan), integers at decision boundaries
* Product ....... 件 (units)
* Machine time .. 时 (hours); human time .. 时 (hours)
* People ........ 人

Items whose exact interpretation is not yet pinned down are marked with
``TODO(待确认)`` and are resolved in M1 by reconciliation against the
reference tool. See ``docs/rules.md`` for the full discussion.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScenarioParams:
    """Global scenario facts shared by all firms."""

    difficulty: str = "5A"
    num_products: int = 2  # A, B
    num_markets: int = 3  # market 1/2/3
    num_companies: int = 10
    periods_per_year: int = 4  # 1 期 = 1 季度
    # Normal / overtime hours per period.
    normal_shift_hours: float = 520.0
    overtime_hours: float = 260.0
    # Per-resource shift ceilings (FAQ 2.1).
    max_hours_per_worker_per_day: float = 12.0
    max_hours_per_machine_per_day: float = 20.0
    # Distribution: share of current-period output that may be shipped out.
    producible_ratio: float = 0.75
    # Raw material: max share of this-period purchases usable this period.
    raw_material_usable_ratio: float = 0.50


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProductParams:
    """Static parameters for a single product."""

    name: str
    # Per-unit resource consumption (件 -> hours / raw-material units).
    machine_hours: float
    labor_hours: float
    raw_material_units: float
    # Per-shift fixed production setup cost (the "管理费" component).
    first_shift_fixed_cost: float
    second_shift_fixed_cost: float
    # Cumulative R&D cost required to reach each level (level 1..5).
    rnd_cumulative_cost: tuple[float, ...]
    # Finished-goods storage cost per unit per period.
    inventory_cost_per_unit: float
    # Freight per market: (fixed, variable) tuples, one per market.
    fixed_freight: tuple[float, float, float]
    variable_freight: tuple[float, float, float]


# ---------------------------------------------------------------------------
# Raw material
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawMaterialParams:
    """Raw-material pricing, freight and storage."""

    standard_price_per_unit: float = 1.0
    # Volume discount tiers: (order_qty_threshold, unit_price). Ordered ascending.
    bulk_discount_tiers: tuple[tuple[float, float], ...] = (
        (0.0, 1.00),
        (1_000_000.0, 0.96),
        (1_500_000.0, 0.92),
        (2_000_000.0, 0.88),
    )
    fixed_freight: float = 5_000.0
    # TODO(待确认): basis of the 0.02 variable freight — per unit (== 2% of
    # standard price) vs. per yuan of purchase value. The two coincide when the
    # standard price is 1 yuan/unit, but must be confirmed against the platform.
    variable_freight: float = 0.02
    # Storage cost per yuan of inventory per period (0.05 元/元/期).
    storage_cost_rate: float = 0.05


# ---------------------------------------------------------------------------
# Demand (L2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DemandParams:
    """Deterministic demand model used by the proposal (M2) and optimizer (M3).

    The platform's exact demand coefficients are not published, so this model is
    a *working placeholder* (TODO 待确认). Its role is to give the proposer a
    monotone, reproducible demand surface to size production/shipments against;
    feasibility does not depend on its exact values.

    demand[pid][m] = base[pid][m] * (price / ref[pid])**elasticity
                     * (1 + adv_sens * advertising[pid] / 1000)
                     * (1 + promo_sens * promotion[m] / 1000)
                     * grade**grade_sens,  clamped to >= 0.
    """

    # Per-product per-market base demand (件/期): (A: m1,m2,m3), (B: m1,m2,m3).
    base_demand: tuple[tuple[float, float, float], tuple[float, float, float]] = (
        (400.0, 400.0, 400.0),
        (200.0, 200.0, 200.0),
    )
    # Reference price at which base demand is realized (元): (A, B).
    reference_price: tuple[float, float] = (2500.0, 5000.0)
    # Own-price elasticity (negative): % demand change per % price change.
    price_elasticity: float = -1.5
    # TODO(待确认): advertising / promotion / grade sensitivities (set to 0
    # until the platform's marketing & grade response is characterized).
    advertising_sensitivity: float = 0.0
    promotion_sensitivity: float = 0.0
    grade_sensitivity: float = 0.0


# ---------------------------------------------------------------------------
# Labor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LaborParams:
    """Wage and headcount rules."""

    # Base hourly wage for the first-shift normal class. Confirmed against the
    # reference tool: 基本工资 = 在岗人数 * 520 * base * 工资系数.
    base_hourly_wage: float = 3.0
    # Shift-based hourly wages. The parameter sheet lists four values
    # (3, 4.5, 4, 6); our working hypothesis (TODO 待确认) is that they are
    # shift-based, with overtime = 1.5x its own shift's normal rate:
    #   first_normal=3, first_overtime=4.5, second_normal=4, second_overtime=6.
    # The engine's 特殊班工资 formula depends on this mapping and is reconciled
    # against 财务!R16 in M1.
    first_normal_wage: float = 3.0
    first_overtime_wage: float = 4.5
    second_normal_wage: float = 4.0
    second_overtime_wage: float = 6.0
    # New-worker training: fee and wage ratio during training.
    new_worker_training_fee: float = 500.0
    new_worker_training_wage_ratio: float = 0.25
    # New workers count as 1/4 of a full worker for basic-wage purposes.
    new_worker_equiv_denominator: int = 4
    # Hiring ceiling: <= 50% of period-start headcount.
    max_hire_ratio: float = 0.50
    # Normal retirement rate per period.
    retirement_rate: float = 0.03
    # Layoff ceiling (incl. retirement): <= 10% of period-start headcount.
    max_layoff_ratio: float = 0.10
    layoff_severance_fee: float = 1_000.0
    min_wage_coefficient: float = 1.0


# ---------------------------------------------------------------------------
# Machines
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MachineParams:
    """Machine purchase, depreciation and maintenance."""

    price: float = 40_000.0
    depreciation_rate: float = 0.05  # per period
    maintenance_fee: float = 200.0  # per machine per period
    # Lead time: purchase paid this period -> installed next period -> usable the
    # period after (2-period delay).
    lead_time_periods: int = 2


# ---------------------------------------------------------------------------
# Finance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FinanceParams:
    """Cash, credit, debt and tax rules."""

    initial_cash: float = 2_500_000.0
    minimum_cash: float = 2_000_000.0
    credit_limit: float = 8_000_000.0
    bank_loan_annual_rate: float = 0.08  # repaid principal + interest at period end
    bond_annual_rate: float = 0.12
    bond_repay_periods: int = 20  # amortised over 20 periods
    treasury_annual_rate: float = 0.06
    emergency_loan_annual_rate: float = 0.40
    # Bond ceiling as a fraction of net assets.
    bond_max_ratio_of_equity: float = 0.50
    tax_rate: float = 0.30
    # Dividend conditions: end-of-period cash > minimum_cash AND amount <=
    # current-period after-tax profit.
    dividend_min_cash: float = 2_000_000.0


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoringParams:
    """Seven-metric weighted scoring."""

    # Weights, in canonical order.
    weight_current_profit: float = 0.20
    weight_net_assets: float = 0.20
    weight_market_share: float = 0.15
    weight_return_on_capital: float = 0.15
    weight_cumulative_dividend: float = 0.10
    weight_cumulative_tax: float = 0.10
    weight_profit_per_capita: float = 0.10
    # TODO(待确认): the FAQ (3.4) mentions cumulative tax/dividend are converted
    # to net present value at a 7% annual rate *for scoring only*. Not present in
    # the prompt's section 3.8. Confirm before M1 scoring projection.
    scoring_npv_annual_rate: float | None = 0.07
    # TODO(待确认): weight applied to the previous-period composite score when
    # computing this period's score (the "滞后影响").
    lag_weight: float | None = None
    # TODO(待确认): exact rule for the standard-score down-adjustment when
    # reserved cash < period-start cash or < period cost.
    reserved_cash_penalty: bool = True


# ---------------------------------------------------------------------------
# Aggregated config
# ---------------------------------------------------------------------------


def _product_a() -> ProductParams:
    return ProductParams(
        name="A",
        machine_hours=100.0,
        labor_hours=150.0,
        raw_material_units=300.0,
        first_shift_fixed_cost=4_000.0,
        second_shift_fixed_cost=5_000.0,
        rnd_cumulative_cost=(100_000.0, 200_000.0, 300_000.0, 400_000.0, 500_000.0),
        inventory_cost_per_unit=20.0,
        fixed_freight=(680.0, 1_820.0, 4_000.0),
        variable_freight=(34.0, 91.0, 200.0),
    )


def _product_b() -> ProductParams:
    return ProductParams(
        name="B",
        machine_hours=200.0,
        labor_hours=250.0,
        raw_material_units=1_500.0,
        first_shift_fixed_cost=6_000.0,
        second_shift_fixed_cost=7_000.0,
        rnd_cumulative_cost=(200_000.0, 350_000.0, 480_000.0, 600_000.0, 700_000.0),
        inventory_cost_per_unit=80.0,
        fixed_freight=(6_500.0, 9_500.0, 12_000.0),
        variable_freight=(325.0, 475.0, 600.0),
    )


@dataclass(frozen=True)
class Config:
    """Immutable aggregation of all rule parameters."""

    scenario: ScenarioParams = field(default_factory=ScenarioParams)
    products: tuple[ProductParams, ProductParams] = field(
        default_factory=lambda: (_product_a(), _product_b())
    )
    raw_material: RawMaterialParams = field(default_factory=RawMaterialParams)
    demand: DemandParams = field(default_factory=DemandParams)
    labor: LaborParams = field(default_factory=LaborParams)
    machine: MachineParams = field(default_factory=MachineParams)
    finance: FinanceParams = field(default_factory=FinanceParams)
    scoring: ScoringParams = field(default_factory=ScoringParams)

    def product(self, name: str) -> ProductParams:
        for p in self.products:
            if p.name == name:
                return p
        raise KeyError(f"unknown product: {name}")


# Default configuration instance used by the engine.
CONFIG = Config()
