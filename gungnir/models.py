"""Pydantic data models for the Gungnir rule engine (L0/L1).

These models are the *values* the engine consumes and produces. Every numeric
field is a plain number (``float``/``int``); the engine performs all arithmetic.
Rounding to integers happens only at decision boundaries, matching the platform
convention (8.4 people -> 9; 120.6 units -> at most 120).

Conventions (see ``docs/rules.md``): money in 元, products in 件, machine/human
time in 时, people in 人.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ProductId(str, Enum):
    A = "A"
    B = "B"


class MarketId(str, Enum):
    M1 = "M1"
    M2 = "M2"
    M3 = "M3"


class ShiftId(str, Enum):
    FIRST_NORMAL = "first_normal"
    FIRST_OVERTIME = "first_overtime"
    SECOND_NORMAL = "second_normal"
    SECOND_OVERTIME = "second_overtime"


# ---------------------------------------------------------------------------
# Period-start state
# ---------------------------------------------------------------------------


class ProductState(BaseModel):
    """Per-product state carried across periods."""

    # 工厂库存 (件): finished goods waiting at the factory.
    factory_inventory: int = 0
    # 市场库存 (件): finished goods already shipped to each market.
    market_inventory: dict[MarketId, int] = Field(default_factory=dict)
    # 上期订货 (件): unsatisfied demand carried over as backorders per market.
    backorders: dict[MarketId, int] = Field(default_factory=dict)
    # 研发等级 (1..5; 0 = not yet invested).
    rnd_level: int = 0
    # 累积研发投入 (元) toward the current level.
    rnd_cumulative: float = 0.0
    # 上期研发投入 (元), needed for the (last + current) / 2 amortization.
    rnd_spent_last_period: float = 0.0
    # 产品等级 (研发等级 + 工资系数调整), >= 1.0.
    grade: float = 1.0


class GameState(BaseModel):
    """Full company state at the start of a period."""

    period: int = 0
    cash: float = 0.0
    workers: int = 0
    machines: int = 0
    # Machine lead time (2 periods): bought last period -> usable next period.
    machines_in_transit: int = 0
    # Bought this period -> usable in two periods.
    machines_ordered: int = 0
    raw_material_units: float = 0.0
    accumulated_depreciation: float = 0.0
    # 国债 (元) held.
    treasury: float = 0.0
    # 本期初银行贷款 (元), repaid (principal + interest) at period end.
    bank_loan: float = 0.0
    # 上期紧急救援贷款 (元), repaid at period end.
    emergency_loan: float = 0.0
    # 债券余额 (元) and the scheduled principal installment due this period.
    bond_outstanding: float = 0.0
    bond_principal_due: float = 0.0
    # Financial history used by scoring.
    cumulative_tax: float = 0.0
    cumulative_dividend: float = 0.0
    tax_credit: float = 0.0
    net_assets: float = 0.0
    last_period_profit: float = 0.0
    composite_score: float = 0.0
    products: dict[ProductId, ProductState] = Field(default_factory=dict)
    # 上期末价格 (元), needed for the sales-revenue min(上期价, 本期价) rule.
    last_period_prices: dict[ProductId, dict[MarketId, float]] = Field(
        default_factory=dict
    )

    def product(self, pid: ProductId) -> ProductState:
        return self.products[pid]


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------


class ProductionSchedule(BaseModel):
    """One product's quantities across the four shift classes (件)."""

    first_normal: float = 0.0
    first_overtime: float = 0.0
    second_normal: float = 0.0
    second_overtime: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.first_normal
            + self.first_overtime
            + self.second_normal
            + self.second_overtime
        )

    def by_shift(self, shift: ShiftId) -> float:
        return {
            ShiftId.FIRST_NORMAL: self.first_normal,
            ShiftId.FIRST_OVERTIME: self.first_overtime,
            ShiftId.SECOND_NORMAL: self.second_normal,
            ShiftId.SECOND_OVERTIME: self.second_overtime,
        }[shift]


class Decision(BaseModel):
    """One period's decision variables (all that goes on the 决策单)."""

    # 价格 (元).
    prices: dict[ProductId, dict[MarketId, float]] = Field(default_factory=dict)
    # 广告费 (元), per product (affects all markets).
    advertising: dict[ProductId, float] = Field(default_factory=dict)
    # 促销费 (元), per market (affects all products in that market).
    promotion: dict[MarketId, float] = Field(default_factory=dict)
    # 向市场供货量 (件), per product per market.
    shipments: dict[ProductId, dict[MarketId, int]] = Field(default_factory=dict)
    # 生产安排 (件), per product across the four shift classes.
    production: dict[ProductId, ProductionSchedule] = Field(default_factory=dict)
    # 研究开发投入 (元), per product this period.
    rnd_investment: dict[ProductId, float] = Field(default_factory=dict)
    # 新雇 / 辞退 (人). Layoff includes normal retirement.
    hire: int = 0
    layoff: int = 0
    # 买机器 (台), paid at period end.
    machine_purchase: int = 0
    # 订购原材料金额 (元).
    raw_material_purchase: float = 0.0
    # 本期新银行贷款 (元).
    bank_loan: float = 0.0
    # 本期新发行债券 (元).
    bond_issue: float = 0.0
    # 购买国债 (元).
    treasury_purchase: float = 0.0
    # 分红 (元).
    dividend: float = 0.0
    # 工资系数 (>= 1.0).
    wage_coefficient: float = 1.0


# ---------------------------------------------------------------------------
# Sales outcome (produced by the demand model L2, consumed by the engine)
# ---------------------------------------------------------------------------


class SalesOutcome(BaseModel):
    """Actual sales per product per market this period (件).

    The cash-flow engine only needs revenue, but this struct keeps the
    demand-model interface explicit. ``sold`` is the quantity actually sold;
    ``new_backorders`` is demand carried into the next period.
    """

    sold: dict[ProductId, dict[MarketId, int]] = Field(default_factory=dict)
    new_backorders: dict[ProductId, dict[MarketId, int]] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


class CashFlowLine(BaseModel):
    """One line of the ordered cash-flow statement."""

    key: str  # stable English identifier, e.g. "opening_cash"
    label: str  # Chinese label, e.g. "上期转来"
    amount: float = 0.0  # signed: income positive, expense negative
    kind: str = "cash"  # "cash" | "cost" | "income" | "info"
    cash_after: float = 0.0  # running cash balance after this line


class Violation(BaseModel):
    """A feasibility violation or warning."""

    code: str
    message: str  # Chinese explanation
    severity: str = "error"  # "error" | "warning"


class FeasibilityReport(BaseModel):
    feasible: bool = True
    violations: list[Violation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # True if cash went negative at/before the emergency-loan check point.
    emergency_loan_triggered: bool = False
    emergency_loan_amount: float = 0.0
    # True if cash went negative at any point.
    cash_shortfall: bool = False


class ScoreBreakdown(BaseModel):
    """Projection of the seven weighted metrics."""

    metrics: dict[str, float] = Field(default_factory=dict)
    z_scores: dict[str, float] = Field(default_factory=dict)
    weighted: dict[str, float] = Field(default_factory=dict)
    composite: float = 0.0


class PeriodResult(BaseModel):
    """Everything the engine produces for one simulated period."""

    ending_state: GameState
    cash_flow: list[CashFlowLine] = Field(default_factory=list)
    revenue_total: float = 0.0
    cost_total: float = 0.0
    profit: float = 0.0
    tax: float = 0.0
    ending_cash: float = 0.0
    feasibility: FeasibilityReport = Field(default_factory=FeasibilityReport)
    score: ScoreBreakdown = Field(default_factory=ScoreBreakdown)


class ProposalResult(BaseModel):
    """A decision proposal (M2) together with its simulated outcome."""

    decision: Decision
    result: PeriodResult
    # Forecast demand (件) the proposal was sized against.
    demand: dict[ProductId, dict[MarketId, float]] = Field(default_factory=dict)
    # Chinese explanation lines for the LLM layer (L4) and UI (L5).
    rationale: list[str] = Field(default_factory=list)
    # True iff the proposal is feasible and never triggers emergency financing.
    feasible: bool = True


# Type aliases for readability.
MarketTable = dict[MarketId, float]
ProductMarketTable = dict[ProductId, dict[MarketId, float]]
