# Gungnir — 商战模拟 AI 副驾驶

> **AI 决策副驾驶（copilot），不是自动驾驶（autopilot）。** 人在环：引擎保证可行，模型解释「为什么」，最终决策由你提交。

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/version-0.1.0-informational.svg" alt="Version 0.1.0"></a>
  <a href="#测试"><img src="https://img.shields.io/badge/tests-81%20passed-brightgreen.svg" alt="Tests: 81 passed"></a>
  <a href="#交付路线图"><img src="https://img.shields.io/badge/status-M0%E2%80%93M6%20complete-brightgreen.svg" alt="Status: M0–M6 complete"></a>
</p>

Gungnir（永恒之枪）面向北大光华企业竞争模拟平台（[edu.ibizsim.cn](https://edu.ibizsim.cn)，2 产品 × 3 市场、10 家公司，场景 5A），是企业竞争模拟（BizSim）的 AI 决策副驾驶。

## 核心特性

| 特性 | 说明 |
|------|------|
| 🔒 **确定性规则引擎** | 纯函数、无随机性；同一输入 → 同一输出，现金流可精确对拍 |
| ✅ **永远可行** | 任何提案/优化结果都通过硬约束校验，绝不产生不可行决策 |
| 🧠 **LLM 只解释、不算术** | 数字全部由引擎算好，LLM 仅引用、不推导、不编造规则 |
| ⚙️ **单点配置** | 全部规则参数集中在 `gungnir/config.py`；LLM 端点经 env/.env 注入 |
| 🌐 **人在环** | 不自动网页操作、不追求全自动赢赛、不绕过平台规则 |

## 架构分层

| 层 | 职责 | 状态 |
|----|------|------|
| **L0 规则引擎** | 状态机 + 37 行现金流仿真 + 可行性校验 + 七指标评分投影（信任锚） | ✅ |
| **L1 状态采集** | 结构化录入/解析每期输入，重建完整公司状态 | ✅ |
| **L2 需求模型** | 参数化需求函数（价格/广告/促销/等级），预留历史标定接口 | ✅ |
| **L3 优化器** | 多期贴现目标 + 坐标上升定价；激活国债/分红/批量折扣长期杠杆 | ✅ |
| **L4 LLM 层** | 解释「为什么」、管理教学；无密钥时降级为确定性模板 | ✅ |
| **L5 UI** | 单页界面：录入 → 提案 → 调整 → 导出 | ✅ |
| **M6 复盘评估** | 多期回放、自博弈、评分曲线 | ✅ |

## 快速开始

```bash
# 1. 克隆并创建虚拟环境
git clone <repo-url> && cd Gungnir
python3 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖（含开发依赖）
pip install -e ".[dev]"

# 3. 运行测试
pytest
```

## 使用

### 启动 Web 界面

```bash
gungnir                 # 或 python -m gungnir.cli
# 打开 http://127.0.0.1:8000
```

完整跑通「**录入 → 提案 → 调整 → 导出**」闭环：录入状态 JSON → 一键提案/优化 → 编辑决策即时重新校验 → 导出 CSV 决策单。

### API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/propose` | 从状态生成一套可行决策 |
| `POST` | `/api/optimize` | 优化决策（确定性搜索） |
| `POST` | `/api/evaluate` | 重新模拟任意（用户改过的）决策 |
| `POST` | `/api/explain` | 生成中文解释（LLM 或模板） |
| `POST` | `/api/export` | 导出决策单 + 现金流（CSV） |
| `POST` | `/api/episode` | 多期回放（滚动策略） |
| `POST` | `/api/tournament` | N 公司自博弈 + 评分曲线 |

交互式文档见启动后的 `/docs`（FastAPI 自动生成）。

### 配置（LLM 层）

通过环境变量或 `.env` 文件注入（复制 `.env.example` 为 `.env`）：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `GUNGNIR_LLM_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI 兼容端点 |
| `GUNGNIR_LLM_API_KEY` | 空 | 空则降级为模板解释（离线可用） |
| `GUNGNIR_LLM_MODEL` | `deepseek-chat` | 模型名（如 DeepSeek V4） |

## 目录结构

```
Gungnir/
├── gungnir/
│   ├── __init__.py        # 包元信息
│   ├── config.py          # 集中参数配置（单文件，信任锚数据）
│   ├── models.py          # pydantic 领域模型
│   ├── settings.py        # 运行时设置（env/.env 注入）
│   ├── demand.py          # L2 需求模型（占位）
│   ├── proposal.py        # M2 决策提案（永远可行）
│   ├── optimize.py        # M3 优化器（确定性坐标上升）
│   ├── llm.py             # L4 LLM 层（解释/教学，可降级）
│   ├── web.py             # L5 UI 后端（FastAPI）
│   ├── replay.py          # M6 复盘/评估（回放·自博弈·评分）
│   ├── cli.py             # 启动 web 服务（uvicorn）
│   ├── static/            # L5 前端（单页 HTML/JS）
│   │   └── index.html
│   └── engine/            # L0 规则引擎
│       ├── production.py  #   排产/资源/成本（纯函数）
│       ├── validation.py  #   硬约束校验
│       ├── cashflow.py    #   37 行有序现金流仿真
│       └── scoring.py     #   七指标 Z-score
├── docs/
│   └── rules.md           # 领域规则规格 + 待确认项
├── tests/                 # 单元测试（81 个）
├── pyproject.toml         # 依赖与工具配置
├── .env.example           # LLM 配置示例
├── README.md
└── LICENSE                # MIT
```

## 领域参数（场景 5A）

- 2 产品（A/B）× 3 市场 × 10 公司；1 期 = 1 季度；难度 5A。
- 初始现金 2,500,000 元；最低现金 2,000,000 元；信用总额 8,000,000 元。
- 单件资源：A（机器 100h / 人力 150h / 原料 300）；B（机器 200h / 人力 250h / 原料 1500）。
- 评分：七项指标加权 Z-score（本期利润 .20 / 净资产 .20 / 市场份额 .15 / 资本利润率 .15 / 累计分红 .10 / 累计缴税 .10 / 人均利润率 .10）。

完整规则见 [docs/rules.md](docs/rules.md)；所有数值参数集中在 [gungnir/config.py](gungnir/config.py)。

## 测试

```bash
pytest                    # 运行全部测试
pytest --cov=gungnir      # 含覆盖率（需安装 pytest-cov）
```

当前 **81 个测试全部通过**，覆盖：现金流对拍、可行性校验、评分、需求模型、提案/优化（含批量折扣、国债部署、多期目标）、LLM 降级、Web 闭环、多期回放与自博弈。

## 交付路线图

- **M0 项目脚手架** ✅ —— repo 结构、依赖、集中 config、README、LICENSE、.gitignore。
- **M1 引擎核心** ✅ —— `GameState` + `Decision` + 现金流仿真 + 可行性校验 + 评分投影（对拍决策工具.xls）。
- **M2 决策提案** ✅ —— 给定状态生成一套可行决策（规则/简单搜索，不接 LLM）。
- **M3 优化器** ✅ —— 确定性坐标上升（定价）＋ 多期贴现目标，激活国债/分红/批量折扣长期杠杆。
- **M4 LLM 层** ✅ —— 接入 DeepSeek（OpenAI 兼容，端点/模型经 env 注入），解释 + 教学；无密钥降级。
- **M5 UI** ✅ —— 单页 HTML/JS + FastAPI，跑通「录入 → 提案 → 调整 → 导出」闭环。
- **M6 复盘/评估** ✅ —— 多期回放、自博弈（N 公司并行）、评分曲线。

## 验收标准（关键）

- **M1**：同一组输入，现金流与评分和手工「决策工具.xls」一致（对拍）。
- **M2/M3**：输出决策**永远可行**，且能解释每项选择。
- **M4**：解释清晰、引用具体数值、不编造规则。
- **M5**：完整跑通「录入 → 提案 → 调整 → 导出」闭环。
- **M6**：多期回放与自博弈输出稳定、可复现的评分曲线。
- 全流程：任何不可行决策都不允许出现；现金流断裂必须预警。

## License

[MIT](LICENSE) © Gungnir contributors
