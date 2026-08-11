# 数仓开发 Agent 🗄️

> 让新手像数仓专家一样开发数仓 — 基于 Kimball《数据仓库工具箱》+ 阿里《OneData》方法论的 7 阶段引导式工作流。

## ✨ 核心特性

- **📚 知识库驱动**: Kimball 4 步法 + 阿里 OneData 6 层架构 + SCD/拉链/退化等高级主题
- **🧩 7 阶段引导式**: 业务调研 → 需求调研 → 架构设计 → 规范定义 → 模型设计 → 跑数 → 测试验证
- **🛢️ DuckDB 引擎**: 零运维、单文件、内嵌式,适合 MVP 和教学
- **🌐 Web UI**: Streamlit 引导式 7 阶段 stepper,后端没起时友好提示
- **🔌 REST API**: FastAPI 7 阶段 API 全覆盖,可独立集成
- **🧪 测试生成**: 自动产出对账 / 边界 / 性能 SQL,支持 mock 数据

## 🚀 快速开始

### 1. 装依赖
```bash
pip install -r app/backend/requirements.txt
pip install -r web/requirements.txt
```

### 2. 启动后端 (端口 8000)
```bash
bash app/backend/run.sh
```

### 3. 启动前端 (端口 8501)
```bash
bash web/run.sh
```

### 4. 打开浏览器
```
http://localhost:8501
```

## 🏗️ 项目结构

```
data-warehouse-agent/
├── app/
│   ├── knowledge/              # 数仓知识库 (Kimball + 阿里 OneData)
│   │   ├── kimball.py          # Kimball 4 步法决策树
│   │   ├── onedata.py          # 阿里 OneData 规范
│   │   ├── dimensions.py       # 维度高级主题 (SCD/拉链/退化/...)
│   │   ├── facts.py            # 事实表设计
│   │   ├── prompts.py          # 7 阶段引导式问答模板
│   │   └── tests/              # 103 个单元测试
│   └── backend/                # FastAPI 后端
│       ├── main.py             # FastAPI app
│       ├── api/                # 7 阶段 API
│       │   ├── requirements.py # 阶段 0-1
│       │   ├── architecture.py # 阶段 2-3
│       │   ├── modeling.py     # 阶段 4 (核心)
│       │   ├── sqlgen.py       # 阶段 5
│       │   └── testing.py      # 阶段 6
│       └── sql_templates/      # Jinja2 SQL 模板
└── web/                        # Streamlit Web UI
    ├── app.py                  # 主入口
    └── pages/01-07_*.py        # 7 阶段页面
```

## 📐 7 阶段工作流

| # | 阶段 | 关键产出 | API |
|---|---|---|---|
| 0 | 业务调研 | 业务-功能-角色矩阵 | `/api/requirements/business` |
| 1 | 需求调研 | 指标/维度/数据源清单 | `/api/requirements/metrics` |
| 2 | 架构设计 | 数据域 + 总线矩阵 | `/api/architecture/domains`, `/bus-matrix` |
| 3 | 规范定义 | 命名规范 + 指标字典 | `/api/architecture/naming`, `/metric-dict` |
| 4 | 模型设计 | DDL (事务/快照/累积) | `/api/modeling/*` |
| 5 | 跑数 | 5 层 ETL SQL | `/api/sqlgen/{ods,dwd,dws,dwt,ads}` |
| 6 | 测试验证 | 对账/边界/性能报告 | `/api/testing/{recon,edge,performance,run}` |

## 🧪 端到端示例

```bash
# 1. 业务过程识别
curl -X POST http://localhost:8000/api/modeling/business-process \
  -H "Content-Type: application/json" \
  -d '{"session_id":"s1","business_description":"用户在下单后,会经历支付、发货、收货"}'
# → 4 个过程: 下单/支付/发货/收货

# 2. 事实表类型决策
curl -X POST http://localhost:8000/api/modeling/fact-type \
  -H "Content-Type: application/json" \
  -d '{"session_id":"s1","business_processes":["下单","支付","发货","收货"],"has_time_intervals":true}'
# → 累积快照事实表

# 3. 命名规范
curl -X POST http://localhost:8000/api/architecture/naming \
  -H "Content-Type: application/json" \
  -d '{"session_id":"s1","layer":"dws","domain":"trade","business":"order","process":"pay","period":"1d"}'
# → dws_trade_order_pay_1d (或简化版)
```

## 📜 参考

- **《数据仓库工具箱:维度建模权威指南》** Ralph Kimball 等
- **《大数据之路:阿里巴巴大数据实践》** 阿里巴巴数据技术及产品部
- **《数据仓库架构:从需求到架构的方法论和实操》**

## 📊 状态

- 📐 designed: 7 阶段拆解 + agent 能力设计 ✅
- 💻 implemented: 知识库 5072 行 + 后端 5 API + 前端 7 页面 ✅
- 🚀 deployed: 端到端跑通,后端/前端都起,API 都通 ✅
- 🧪 validated: 1 个真实 case (订单累积快照) 跑通 ✅
