"""
7 阶段引导式问答模板 (Guided Questioning Prompts)
=================================================

来源 (Sources):
    - 阿里《OneData》方法论的 7 阶段实施流程
    - Kimball 维度建模生命周期 4 步
    - Data Vault 2.0 的需求引导方法论

设计原则 (Design Principles):
    1. **新手友好**: 每个问题配示例 + 提示,初学者能照着填。
    2. **老手可跳**: 高级用户提供"skip_hint",问题可被压缩。
    3. **结构化**: 每阶段输出固定 JSON schema,便于后续程序消费。
    4. **可追溯**: 每个问题带 source(来源依据)。

7 阶段定义 (7 Stages):
    0 - 业务调研: 了解业务领域、功能模块、用户角色
    1 - 需求调研: 列出指标、维度、数据源
    2 - 架构设计: 数据域划分 + 总线矩阵
    3 - 规范定义: 命名规范 + 指标字典
    4 - 模型设计: Kimball 4 步法(业务过程→粒度→维度→事实) + 事实表类型
    5 - 跑数建模: DDL + 5 层 ETL SQL(ODS/DWD/DWS/DWT/ADS)
    6 - 测试验证: 对账 + 边界 + 性能 + mock 数据
"""

from __future__ import annotations

from typing import Any


# ============================================================
# 阶段 0: 业务调研
# ============================================================

STAGE_0_BUSINESS = {
    "stage": 0,
    "name": "业务调研",
    "goal": "理解业务领域、功能模块、用户角色,形成业务-功能-角色矩阵",
    "source": "阿里 OneData 实施流程第 1 步 + 需求调研方法论",
    "estimated_minutes": 10,
    "questions": [
        {
            "id": "biz_name",
            "text": "你要建模的核心业务是什么?",
            "type": "text",
            "required": True,
            "example": "电商订单业务 / 金融支付业务 / 物流配送业务",
            "skip_hint": "老手可直接给业务名,跳过引导",
            "rationale": "业务名 = 数仓的根,后续所有指标/表名都依赖它。",
        },
        {
            "id": "biz_modules",
            "text": "这个业务包含哪些功能模块?",
            "type": "multi_text",
            "required": True,
            "example": "订单管理, 支付管理, 库存管理, 售后服务, 用户管理",
            "min_items": 1,
            "rationale": "模块 = 数据域划分的基础。",
        },
        {
            "id": "biz_users",
            "text": "主要用户角色有哪些?",
            "type": "multi_text",
            "required": True,
            "example": "买家, 卖家, 平台运营, 客服, 财务",
            "min_items": 1,
            "rationale": "用户角色 = 决定指标维度和报表视角。",
        },
        {
            "id": "biz_industry",
            "text": "业务属于哪个行业?",
            "type": "select",
            "options": ["电商", "金融", "物流", "游戏", "内容", "教育", "医疗", "其他"],
            "required": True,
            "example": "电商",
            "rationale": "行业 = 决定 OneData 数据域默认配置。",
        },
        {
            "id": "biz_scale",
            "text": "预计数据量级?",
            "type": "select",
            "options": ["小 (< 100w 行)", "中 (100w~1亿行)", "大 (1亿~100亿行)", "超大 (> 100亿行)"],
            "required": True,
            "example": "中 (100w~1亿行)",
            "rationale": "数据量级 = 决定存储选型(DuckDB/Hive/ClickHouse)。",
        },
    ],
    "output_schema": {
        "biz_name": "str",
        "biz_modules": "list[str]",
        "biz_users": "list[str]",
        "biz_industry": "str",
        "biz_scale": "str",
    },
}


# ============================================================
# 阶段 1: 需求调研
# ============================================================

STAGE_1_REQUIREMENT = {
    "stage": 1,
    "name": "需求调研",
    "goal": "列出关键指标、维度清单、数据源清单",
    "source": "阿里 OneData 第 6 章指标体系 + Kimball 业务需求文档 BRD",
    "estimated_minutes": 15,
    "questions": [
        {
            "id": "metrics",
            "text": "关键业务指标有哪些?",
            "type": "multi_text",
            "required": True,
            "example": "GMV, 订单数, 客单价, 复购率, 退款率, 转化率",
            "min_items": 1,
            "rationale": "指标 = 事实表的度量,也是 ADS 应用层报表的输出。",
        },
        {
            "id": "dimensions",
            "text": "分析维度有哪些?",
            "type": "multi_text",
            "required": True,
            "example": "用户维度(新老客/会员等级), 商品维度(类目/品牌), 时间维度(日/周/月), 渠道维度",
            "min_items": 1,
            "rationale": "维度 = 指标的下钻路径。",
        },
        {
            "id": "data_sources",
            "text": "原始数据源有哪些?",
            "type": "multi_text",
            "required": True,
            "example": "MySQL 订单库, MySQL 用户库, 业务日志(Nginx), 第三方支付回调",
            "min_items": 1,
            "rationale": "数据源 = ODS 贴源层的来源。",
        },
        {
            "id": "data_freshness",
            "text": "数据更新频率?",
            "type": "select",
            "options": ["T+1 (每日)", "小时级", "分钟级", "实时 (秒级)"],
            "required": True,
            "example": "T+1 (每日)",
            "rationale": "更新频率 = 决定 ETL 调度周期。",
        },
        {
            "id": "data_retention",
            "text": "数据保留周期?",
            "type": "select",
            "options": ["1年", "3年", "5年", "长期"],
            "required": True,
            "example": "3年",
            "rationale": "保留周期 = 决定存储成本和归档策略。",
        },
    ],
    "output_schema": {
        "metrics": "list[str]",
        "dimensions": "list[str]",
        "data_sources": "list[str]",
        "data_freshness": "str",
        "data_retention": "str",
    },
}


# ============================================================
# 阶段 2: 架构设计
# ============================================================

STAGE_2_ARCHITECTURE = {
    "stage": 2,
    "name": "架构设计",
    "goal": "数据域划分 + 总线矩阵 + 分层架构",
    "source": "阿里 OneData 第 4 章 数据域 + 第 5 章 总线矩阵 + Kimball 总线架构",
    "estimated_minutes": 20,
    "questions": [
        {
            "id": "domain_split",
            "text": "功能模块 → 数据域划分?",
            "type": "auto_from_modules",  # 自动从阶段 0 推导
            "required": True,
            "example": "订单管理 → trade, 用户管理 → user, 商品管理 → item",
            "rationale": "数据域 = 数仓的'一楼'。同域内聚,跨域通过 ID 关联。",
        },
        {
            "id": "business_processes",
            "text": "核心业务过程列表?",
            "type": "multi_text",
            "required": True,
            "example": "下单, 支付, 发货, 收货, 退货, 评价",
            "min_items": 1,
            "rationale": "业务过程 = 事实表的根,Kimball 4 步法 Step 1。",
        },
        {
            "id": "shared_dimensions",
            "text": "跨过程共用的维度?",
            "type": "multi_text",
            "required": True,
            "example": "用户, 商品, 时间, 商家",
            "min_items": 1,
            "rationale": "共享维度 = 总线矩阵的核心,确保跨域一致性。",
        },
        {
            "id": "layer_choice",
            "text": "选择分层架构?",
            "type": "select",
            "options": ["阿里 OneData (ODS/DWD/DWS/DWT/ADS/DIM)", "Kimball 经典 (Staging/Atomic/DataMart)", "Data Vault 2.0"],
            "required": True,
            "example": "阿里 OneData (ODS/DWD/DWS/DWT/ADS/DIM)",
            "rationale": "分层架构 = 数仓的物理结构。",
        },
    ],
    "output_schema": {
        "domain_split": "dict[str, str]",      # 模块 → 数据域
        "business_processes": "list[str]",
        "shared_dimensions": "list[str]",
        "layer_choice": "str",
    },
}


# ============================================================
# 阶段 3: 规范定义
# ============================================================

STAGE_3_STANDARD = {
    "stage": 3,
    "name": "规范定义",
    "goal": "表命名规范 + 字段命名规范 + 指标字典",
    "source": "阿里 OneData 第 7 章 命名规范 + 第 6 章 指标体系",
    "estimated_minutes": 15,
    "questions": [
        {
            "id": "naming_convention",
            "text": "选择命名规范?",
            "type": "select",
            "options": ["阿里 OneData (ods/dwd/dws/dwt/ads/dim)", "Kimball (stg/fct/dim)", "自定义"],
            "required": True,
            "example": "阿里 OneData (ods/dwd/dws/dwt/ads/dim)",
            "rationale": "命名规范 = 表的可读性和可追溯性的基础。",
        },
        {
            "id": "atomic_metrics",
            "text": "原子指标定义?",
            "type": "auto_from_metrics",  # 自动从阶段 1 推导
            "required": True,
            "example": "GMV = SUM(订单金额), 订单数 = COUNT(子订单号), 客单价 = SUM(订单金额)/COUNT(子订单号)",
            "rationale": "原子指标 = 不可再分 + 聚合方式。",
        },
        {
            "id": "derived_metrics",
            "text": "派生指标列表?",
            "type": "multi_text",
            "required": True,
            "example": "最近 1 天 GMV, 最近 7 天 GMV, 本月 GMV, 历史至今 GMV",
            "min_items": 1,
            "rationale": "派生指标 = 原子指标 + 修饰词 + 时间周期。",
        },
        {
            "id": "naming_samples",
            "text": "示例表名 (3 张)?",
            "type": "multi_text",
            "required": False,
            "example": "ods_mysql_order, dwd_trade_order_df, dws_trade_user_pay_1d",
            "rationale": "示例表 = 命名规范的'现身说法',人工校对。",
        },
    ],
    "output_schema": {
        "naming_convention": "str",
        "atomic_metrics": "list[dict]",
        "derived_metrics": "list[dict]",
        "naming_samples": "list[str]",
    },
}


# ============================================================
# 阶段 4: 模型设计 (Kimball 4 步法)
# ============================================================

STAGE_4_MODELING = {
    "stage": 4,
    "name": "模型设计 (Kimball 4 步法)",
    "goal": "业务过程 → 粒度 → 维度 → 事实 → 事实表类型 → DDL",
    "source": "Kimball 第 3 章 4 步法 + 第 4 章 事实表类型",
    "estimated_minutes": 30,
    "questions": [
        {
            "id": "step1_processes",
            "text": "Step 1: 业务过程有哪些?",
            "type": "auto_from_stage2",  # 从阶段 2 推导
            "required": True,
            "example": "下单, 支付, 发货, 收货",
            "rationale": "Kimball 4 步法 Step 1: Choose the Business Process",
        },
        {
            "id": "step2_grain",
            "text": "Step 2: 粒度声明是什么?",
            "type": "text",
            "required": True,
            "example": "子订单粒度 (一行 = 一个子订单)",
            "rationale": "Kimball 4 步法 Step 2: Declare the Grain。粒度决定一行事实。",
        },
        {
            "id": "step3_dimensions",
            "text": "Step 3: 涉及哪些维度?",
            "type": "multi_text",
            "required": True,
            "example": "用户, 商品, 时间, 商家, 支付方式, 收货地址",
            "min_items": 1,
            "rationale": "Kimball 4 步法 Step 3: Identify the Dimensions。维度 = 分析视角。",
        },
        {
            "id": "step4_facts",
            "text": "Step 4: 事实列有哪些?",
            "type": "multi_text",
            "required": True,
            "example": "订单金额, 商品数量, 优惠金额, 实付金额",
            "min_items": 1,
            "rationale": "Kimball 4 步法 Step 4: Identify the Facts。事实 = 可度量数值。",
        },
        {
            "id": "fact_type",
            "text": "事实表类型?",
            "type": "select",
            "options": ["事务", "周期快照", "累积快照"],
            "required": True,
            "example": "累积快照 (下单→支付→发货→收货有多个时间戳)",
            "rationale": "Kimball 第 4 章: 事务(单事件)/周期快照(状态)/累积快照(全生命周期)。",
        },
        {
            "id": "scd_decisions",
            "text": "维度 SCD 策略?",
            "type": "multi_text",
            "required": False,
            "example": "用户地址: SCD Type 2; 商品类目: SCD Type 1; 用户等级: SCD Type 2",
            "rationale": "SCD = 缓慢变化维策略,影响维表设计。",
        },
    ],
    "output_schema": {
        "step1_processes": "list[str]",
        "step2_grain": "str",
        "step3_dimensions": "list[dict]",  # 含 role: primary/related/junk/degenerate
        "step4_facts": "list[dict]",      # 含 additivity: additive/semi/non_additive
        "fact_type": "str",
        "scd_decisions": "list[dict]",
    },
}


# ============================================================
# 阶段 5: 跑数建模
# ============================================================

STAGE_5_BUILD = {
    "stage": 5,
    "name": "跑数建模 (5 层 ETL)",
    "goal": "生成 ODS / DWD / DWS / DWT / ADS 5 层 SQL",
    "source": "阿里 OneData 6 层架构 + DuckDB 语法",
    "estimated_minutes": 25,
    "questions": [
        {
            "id": "ods_sql",
            "text": "ODS 贴源 SQL 生成?",
            "type": "auto_generate",
            "required": True,
            "example": "INSERT INTO ods_mysql_order SELECT * FROM mysql_order WHERE dt='${yesterday}'",
            "rationale": "ODS = 贴源层,1:1 落地业务系统。",
        },
        {
            "id": "dwd_sql",
            "text": "DWD 清洗 SQL 生成?",
            "type": "auto_generate",
            "required": True,
            "example": "INSERT INTO dwd_trade_order_df SELECT ... FROM ods_mysql_order WHERE dt='${yesterday}'",
            "rationale": "DWD = 清洗后明细,去重/标准化/关联维外键。",
        },
        {
            "id": "dws_sql",
            "text": "DWS 汇总 SQL 生成?",
            "type": "auto_generate",
            "required": True,
            "example": "INSERT OVERWRITE dws_trade_user_pay_1d SELECT user_key, SUM(amount) FROM dwd_trade_order_df GROUP BY user_key",
            "rationale": "DWS = 主题汇总,ADS 直接查询。",
        },
        {
            "id": "dwt_sql",
            "text": "DWT 主题 SQL 生成?",
            "type": "auto_generate",
            "required": True,
            "example": "UPSERT INTO dwt_trade_user_pay_td ... (累计型, MERGE 增量)",
            "rationale": "DWT = 累计主题,1 行 = 1 实体的全量累计。",
        },
        {
            "id": "ads_sql",
            "text": "ADS 应用 SQL 生成?",
            "type": "auto_generate",
            "required": True,
            "example": "INSERT OVERWRITE ads_sales_daily_report SELECT ... FROM dws_trade_user_pay_1d",
            "rationale": "ADS = 应用层,面向报表/接口。",
        },
        {
            "id": "ddl_sql",
            "text": "DDL 表结构生成?",
            "type": "auto_generate",
            "required": True,
            "example": "CREATE TABLE dws_trade_user_pay_1d (user_key BIGINT, gmv DECIMAL(18,2), ...)",
            "rationale": "DDL = 物理表结构,建表语句。",
        },
    ],
    "output_schema": {
        "ods_sql": "str",
        "dwd_sql": "str",
        "dws_sql": "str",
        "dwt_sql": "str",
        "ads_sql": "str",
        "ddl_sql": "str",
    },
}


# ============================================================
# 阶段 6: 测试验证
# ============================================================

STAGE_6_TESTING = {
    "stage": 6,
    "name": "测试验证",
    "goal": "对账 + 边界 + 性能 + 准确性/完整性/一致性",
    "source": "DataVault 2.0 测试方法论 + 阿里 OneData 验收标准",
    "estimated_minutes": 20,
    "questions": [
        {
            "id": "recon_sql",
            "text": "对账 SQL 生成?",
            "type": "auto_generate",
            "required": True,
            "example": "业务源订单数 vs 数仓 dwd 订单数,CASE WHEN 差 = 0 THEN '通过'",
            "rationale": "对账 = 业务源 vs 数仓,验证数据一致性。",
        },
        {
            "id": "edge_sql",
            "text": "边界用例 SQL 生成?",
            "type": "auto_generate",
            "required": True,
            "example": "空值/脏值/跨周期/数据倾斜用例",
            "rationale": "边界 = 异常路径覆盖,生产环境第一杀手。",
        },
        {
            "id": "perf_sql",
            "text": "性能基线 SQL 生成?",
            "type": "auto_generate",
            "required": True,
            "example": "EXPLAIN ANALYZE,看执行计划,记录查询耗时",
            "rationale": "性能 = 数仓 SLA,慢查询会导致业务阻塞。",
        },
        {
            "id": "mock_data",
            "text": "Mock 测试数据生成?",
            "type": "auto_generate",
            "required": False,
            "example": "生成 1000 条订单 mock 数据,标注 # MOCK_DATA",
            "rationale": "Mock = 在没有真实数据时也能跑通 ETL。user 已明确允许。",
        },
        {
            "id": "report",
            "text": "测试报告生成?",
            "type": "auto_generate",
            "required": True,
            "example": "准确率 99.5%, 完整率 100%, 一致率 100%, 性能 P99 < 5s",
            "rationale": "报告 = 验收依据,4 维度(准确性/完整性/一致性/性能)。",
        },
    ],
    "output_schema": {
        "recon_sql": "str",
        "edge_sql": "str",
        "perf_sql": "str",
        "mock_data": "str",
        "report": "dict",  # 4 维度评分
    },
}


# ============================================================
# 7 阶段总览
# ============================================================

ALL_STAGES: list[dict[str, Any]] = [
    STAGE_0_BUSINESS,
    STAGE_1_REQUIREMENT,
    STAGE_2_ARCHITECTURE,
    STAGE_3_STANDARD,
    STAGE_4_MODELING,
    STAGE_5_BUILD,
    STAGE_6_TESTING,
]


def get_stage(stage_id: int) -> dict[str, Any]:
    """获取指定阶段的引导问题模板。

    Args:
        stage_id: 阶段编号 (0~6)。

    Returns:
        阶段定义 dict(包含 name/questions/output_schema/source)。

    Raises:
        ValueError: stage_id 不在 0~6 范围。

    Examples:
        >>> s = get_stage(0)
        >>> s['name']
        '业务调研'
        >>> len(s['questions']) >= 1
        True
    """
    if not (0 <= stage_id <= 6):
        raise ValueError(f"阶段编号必须在 0~6,当前: {stage_id}")
    return ALL_STAGES[stage_id]


def list_stages() -> list[dict[str, Any]]:
    """列出所有 7 阶段的概览。"""
    return [
        {
            "stage": s["stage"],
            "name": s["name"],
            "goal": s["goal"],
            "question_count": len(s["questions"]),
            "estimated_minutes": s["estimated_minutes"],
        }
        for s in ALL_STAGES
    ]


def get_required_fields(stage_id: int) -> list[str]:
    """获取指定阶段的所有必填字段 ID 列表。"""
    stage = get_stage(stage_id)
    return [q["id"] for q in stage["questions"] if q.get("required", False)]


def get_question_by_id(stage_id: int, question_id: str) -> dict[str, Any] | None:
    """根据 question_id 查找具体问题。"""
    stage = get_stage(stage_id)
    for q in stage["questions"]:
        if q["id"] == question_id:
            return q
    return None


def validate_answers(stage_id: int, answers: dict[str, Any]) -> dict[str, Any]:
    """校验指定阶段的答案。

    Args:
        stage_id: 阶段编号。
        answers: 用户的答案 dict(question_id -> answer)。

    Returns:
        dict:
            {
                "valid": bool,
                "errors": list[str],     # 校验错误
                "warnings": list[str],   # 警告(如可选字段未填)
                "missing_required": list[str]
            }

    Examples:
        >>> r = validate_answers(0, {"biz_name": "电商", "biz_modules": ["订单"]})
        >>> r['missing_required']
        ['biz_users', 'biz_industry', 'biz_scale']
    """
    stage = get_stage(stage_id)
    errors: list[str] = []
    warnings: list[str] = []
    missing: list[str] = []

    for q in stage["questions"]:
        qid = q["id"]
        required = q.get("required", False)
        answer = answers.get(qid)

        if required and (answer is None or answer == "" or answer == []):
            missing.append(qid)
            errors.append(f"问题 '{qid}'({q['text']})为必填,但未提供答案。")
            continue

        if answer is None or answer == "" or answer == []:
            if not required:
                warnings.append(f"问题 '{qid}'({q['text']})未填写。")
            continue

        # 类型校验
        qtype = q.get("type", "text")
        if qtype == "multi_text" and isinstance(answer, list):
            min_items = q.get("min_items", 1)
            if len(answer) < min_items:
                errors.append(
                    f"问题 '{qid}' 至少需要 {min_items} 项,当前 {len(answer)} 项。"
                )
        elif qtype == "select" and "options" in q:
            if answer not in q["options"]:
                errors.append(
                    f"问题 '{qid}' 的答案 '{answer}' 不在合法选项 {q['options']} 中。"
                )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "missing_required": missing,
    }
