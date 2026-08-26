"""L4 LLM layer: explain the engine's decision in Chinese.

The LLM **never performs arithmetic** — every number it may cite is pre-computed
by the rule engine and passed in as grounded context. It is instructed to only
reference numbers and rules present in that context, so it cannot fabricate
platform rules. When no API key is configured, or the API is unreachable, it
degrades to a deterministic template built from the same grounded numbers.
"""

from __future__ import annotations

from gungnir.config import CONFIG, Config
from gungnir.models import Explanation, MarketId, ProductId, ProposalResult
from gungnir.settings import settings

SYSTEM_PROMPT = (
    "你是「Gungnir」商战模拟（北大光华企业竞争模拟平台，场景 5A）的决策助教。\n"
    "你的任务是把规则引擎已经算好的决策，用中文讲清楚「做了什么、为什么、有什么管理启示」。\n"
    "严格约束：\n"
    "1. 你不做任何计算。所有数字都已在下方「事实数据」中给出，你只能引用其中出现的数字，"
    "禁止自行加减乘除或推导出任何新数字。\n"
    "2. 你不得编造平台规则。只能引用「规则要点」中明确列出的规则，除此之外的规则一律不要说。\n"
    "3. 用通俗的管理语言解释，可指出风险与改进方向，但不得声称某个数字是你计算出来的。\n"
    "4. 全文使用中文，控制在 200~400 字，分「决策要点」「为什么」「管理启示」三部分。"
)


def explain(
    proposal: ProposalResult, config: Config = CONFIG, client=None
) -> Explanation:
    """Explain ``proposal``. Uses the LLM when configured, else a template."""
    citations = _citations(proposal)
    if not settings.llm_api_key:
        return Explanation(
            text=_fallback(proposal, citations),
            citations=citations,
            used_llm=False,
            fallback_reason="未配置 GUNGNIR_LLM_API_KEY，使用模板解释",
        )
    context = build_explanation_context(proposal, config)
    try:
        text = _call_llm(context, client)
        return Explanation(
            text=text, citations=citations, used_llm=True, model=settings.llm_model
        )
    except Exception as exc:  # noqa: BLE001 — degrade gracefully on any API error
        return Explanation(
            text=_fallback(proposal, citations),
            citations=citations,
            used_llm=False,
            fallback_reason=f"LLM 调用失败：{exc}",
        )


def build_explanation_context(proposal: ProposalResult, config: Config = CONFIG) -> str:
    """Render the grounded context (state, decision, cash flow, rules) as text."""
    d = proposal.decision
    r = proposal.result
    s = proposal.state

    lines: list[str] = ["# 事实数据"]

    if s is not None:
        lines.append("## 公司状态")
        lines.append(
            f"期初现金 {s.cash:,.0f} 元；工人 {s.workers} 人；机器 {s.machines} 台；"
            f"原材料 {s.raw_material_units:,.0f} 单位；净资产 {s.net_assets:,.0f} 元；"
            f"债券余额 {s.bond_outstanding:,.0f} 元。"
        )

    lines.append("## 本期决策")
    for pid in ProductId:
        p = d.prices[pid]
        lines.append(
            f"产品 {pid.value}：定价 "
            + "/".join(f"{p[m]:,.0f}" for m in MarketId)
            + f" 元；生产 {d.production[pid].total:,.0f} 件；"
            + f"供货 {sum(d.shipments[pid].values()):,} 件；"
            + f"广告 {d.advertising.get(pid, 0):,.0f} 元；"
            + f"研发 {d.rnd_investment.get(pid, 0):,.0f} 元。"
        )
    lines.append(
        f"招聘 {d.hire} 人、解聘 {d.layoff} 人；买机器 {d.machine_purchase} 台；"
        f"工资系数 {d.wage_coefficient:.2f}；"
        f"订购原材料 {d.raw_material_purchase:,.0f} 元；"
        f"银行贷款 {d.bank_loan:,.0f} 元、发债券 {d.bond_issue:,.0f} 元；"
        f"分红 {d.dividend:,.0f} 元。"
    )

    lines.append("## 现金流与结果")
    for line in r.cash_flow:
        if line.amount != 0 or line.key in ("opening_cash", "sales_revenue"):
            lines.append(f"- {line.label}：{line.amount:,.0f} 元")
    lines.append(
        f"收入合计 {r.revenue_total:,.0f} 元；成本合计 {abs(r.cost_total):,.0f} 元；"
        f"税前利润 {r.profit:,.0f} 元；纳税 {r.tax:,.0f} 元；期末现金 {r.ending_cash:,.0f} 元。"
    )

    lines.append("## 规则要点")
    lines.append(_rules_snapshot(config))

    return "\n".join(lines)


def _rules_snapshot(config: Config) -> str:
    """Curated list of the rules actually applied (from config, not invented)."""
    s = config.scenario
    return (
        f"本期产量可运出比例 {s.producible_ratio:.0%}；"
        f"本期订购原材料可用比例 {s.raw_material_usable_ratio:.0%}；"
        f"正常班 {s.normal_shift_hours:.0f} 时、加班 {s.overtime_hours:.0f} 时；"
        f"招聘上限期初人数 {config.labor.max_hire_ratio:.0%}、"
        f"解聘上限 {config.labor.max_layoff_ratio:.0%}、"
        f"正常退休 {config.labor.retirement_rate:.0%}；"
        f"工资系数下限 {config.labor.min_wage_coefficient:.1f}；"
        f"机器价 {config.machine.price:,.0f} 元/台、每期折旧 {config.machine.depreciation_rate:.0%}；"
        f"债券利率 {config.finance.bond_annual_rate:.0%} 分 {config.finance.bond_repay_periods} 期；"
        f"税率 {config.finance.tax_rate:.0%}。"
    )


def _citations(proposal: ProposalResult) -> list[str]:
    """Grounded numeric facts the explanation may cite."""
    d = proposal.decision
    r = proposal.result
    c: list[str] = []
    for pid in ProductId:
        c.append(
            f"产品 {pid.value} 定价 "
            + "/".join(f"{d.prices[pid][m]:,.0f}" for m in MarketId)
            + " 元"
        )
        c.append(
            f"产品 {pid.value} 生产 {d.production[pid].total:,.0f} 件、"
            f"供货 {sum(d.shipments[pid].values()):,} 件"
        )
    c.append(f"税前利润 {r.profit:,.0f} 元")
    c.append(f"纳税 {r.tax:,.0f} 元")
    c.append(f"期末现金 {r.ending_cash:,.0f} 元")
    c.append(f"销售收入 {r.revenue_total:,.0f} 元")
    c.append(f"招聘 {d.hire} 人、解聘 {d.layoff} 人")
    if d.bank_loan or d.bond_issue:
        c.append(f"银行贷款 {d.bank_loan:,.0f} 元、发债券 {d.bond_issue:,.0f} 元")
    return c


def _fallback(proposal: ProposalResult, citations: list[str]) -> str:
    """Deterministic Chinese explanation built from the grounded numbers."""
    d = proposal.decision
    r = proposal.result
    lines = ["【决策要点】"]
    for pid in ProductId:
        lines.append(
            f"- 产品 {pid.value}：定价 "
            + "/".join(f"{d.prices[pid][m]:,.0f}" for m in MarketId)
            + f" 元，生产 {d.production[pid].total:,.0f} 件，供货 {sum(d.shipments[pid].values()):,} 件。"
        )
    lines.append(f"- 人力：招聘 {d.hire} 人，解聘 {d.layoff} 人。")
    if d.bank_loan or d.bond_issue:
        lines.append(f"- 融资：银行贷款 {d.bank_loan:,.0f} 元，发债券 {d.bond_issue:,.0f} 元。")
    else:
        lines.append("- 融资：本期无需融资。")

    lines.append("【财务结果】")
    lines.append(
        f"- 销售收入 {r.revenue_total:,.0f} 元，成本合计 {abs(r.cost_total):,.0f} 元，"
        f"税前利润 {r.profit:,.0f} 元，纳税 {r.tax:,.0f} 元，期末现金 {r.ending_cash:,.0f} 元。"
    )

    lines.append("【管理启示】")
    if r.profit >= 0:
        lines.append("- 本期方案为正利润且现金为正，现金流安全。")
    else:
        lines.append("- 本期利润为负，需关注定价与成本结构。")
    if d.bank_loan or d.bond_issue:
        lines.append("- 本期动用了外部融资，注意下期还本付息带来的现金流压力。")
    lines.append("- 以上为规则引擎生成的确定性方案，优化器可在此基础上进一步调价。")
    return "\n".join(lines)


def _call_llm(context: str, client=None) -> str:
    from openai import OpenAI

    c = client or OpenAI(
        base_url=settings.llm_base_url, api_key=settings.llm_api_key
    )
    resp = c.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ],
        temperature=0.3,
    )
    return resp.choices[0].message.content
