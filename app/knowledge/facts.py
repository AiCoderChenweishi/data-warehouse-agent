"""
事实表设计 (Fact Table Design)
==============================

来源 (Sources):
    - Kimball "The Data Warehouse Toolkit" 第 4 章 "Fact Table Types" + 第 5 章
    - 阿里《OneData》第 3 章 + 第 4 章 "事实表设计"
    - 关键内容:
        * 事务事实表 (Transaction Fact Table)
        * 周期快照事实表 (Periodic Snapshot Fact Table)
        * 累积快照事实表 (Accumulating Snapshot Fact Table)
        * 聚集型事实表 / DWS 汇总表 (Aggregated Fact Table)
        * 不可加事实拆分 (Non-additive Fact Decomposition)
        * 退化维度使用 (Degenerate Dimension)

设计原则:
    1. 4 种类型决策明确,各适用场景清晰。
    2. 半可加性/不可加性的处理是事实表设计的核心难点。
    3. 物理实现(分区/归档/压缩)是落地关键。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


# ============================================================
# 事务事实表 (Transaction Fact Table)
# ============================================================
# 来源: Kimball 第 4 章
# 核心特征:
#   - 一行 = 一个业务事件(原子粒度)
#   - 时间戳 = 事件发生时点(精确到秒/毫秒)
#   - 维度外键丰富
#   - 事实都是可加的(或可拆分的)
# 设计步骤(4 步):
#   1) 选定业务过程(下单/支付/登录)
#   2) 声明粒度(子订单级/支付单级)
#   3) 识别维度(用户/商品/时间/...)
#   4) 识别事实(可加数值)

def design_transaction_fact(
    business_process: str,
    grain: str,
    dimensions: list[str],
    facts: list[str],
) -> dict[str, Any]:
    """设计事务事实表 (Kimball 第 4 章)。

    Args:
        business_process: 业务过程(如 "下单")。
        grain: 粒度(如 "子订单粒度")。
        dimensions: 维度列表(如 ["用户", "商品", "时间"])。
        facts: 事实列表(如 ["订单金额", "商品数量"])。

    Returns:
        dict:
            {
                "table_name": str,            # 推荐的事实表名
                "ddl_template": str,          # DDL 模板
                "etl_pattern": str,           # ETL 模式
                "indexes": list,              # 索引建议
                "partition_strategy": str,    # 分区策略
                "design_notes": list
            }

    Examples:
        >>> r = design_transaction_fact(
        ...     "下单", "子订单粒度",
        ...     ["用户", "商品", "时间"],
        ...     ["订单金额", "商品数量"]
        ... )
        >>> "下单" in r['table_name'] or "order" in r['table_name']
        True
    """
    # 表名遵循 OneData 规范: dwd_<域>_<业务过程>
    # 简化:此处用 dwd_<business_process>_detail
    table_name = f"dwd_{_safe_name(business_process)}_detail"

    ddl = (
        f"CREATE TABLE {table_name} (\n"
        f"  -- 退化维 (业务主键)\n"
        f"  {business_process}_id    BIGINT       NOT NULL,\n"
        f"  -- 维度外键\n"
    )
    for dim in dimensions:
        ddl += f"  {_safe_name(dim)}_key     BIGINT       COMMENT '{dim}外键',\n"
    ddl += f"  -- 业务时间\n"
    ddl += f"  event_time      TIMESTAMP   NOT NULL  COMMENT '事件发生时间',\n"
    ddl += f"  -- 事实\n"
    for f in facts:
        ddl += f"  {_safe_name(f)}        DECIMAL(18,2) COMMENT '{f}',\n"
    ddl += f"  -- 元数据\n"
    ddl += f"  dt              DATE        NOT NULL  COMMENT '数据日期(分区)'\n"
    ddl += f");\n"
    ddl += f"PARTITIONED BY (dt STRING);\n"

    etl_pattern = (
        "INSERT INTO dwd_xxx_detail\n"
        "SELECT\n"
        "  order_id,            -- 业务主键(退化维)\n"
        "  user_key, item_key,  -- 维度外键\n"
        "  event_time,          -- 事件时间\n"
        "  amount, quantity,    -- 事实\n"
        "  dt                   -- 数据日期\n"
        "FROM ods_xxx\n"
        "WHERE dt = '${yesterday}';"
    )

    return {
        "table_name": table_name,
        "fact_type": "transaction",
        "ddl_template": ddl,
        "etl_pattern": etl_pattern,
        "indexes": [
            f"主键索引: ({business_process}_id, dt)",
            "维度外键索引: 各 _key 字段单独建索引",
            "时间索引: event_time",
        ],
        "partition_strategy": "按 dt (数据日期) 字符串分区,日/小时分区,保留 30~90 天热数据。",
        "design_notes": [
            f"粒度 = {grain},一行 = 一个业务事件",
            "事实应全部可加(可 SUM),半可加事实应在周期快照表中",
            "时间戳精确到秒/毫秒,避免小时聚合后丢失",
        ],
    }


def _safe_name(text: str) -> str:
    """把中英文混合转成下划线英文片段,作为 SQL 标识符。"""
    CN_MAP = {
        "下单": "order", "支付": "pay", "退款": "refund", "发货": "ship", "收货": "receive",
        "退货": "return", "评价": "review", "用户": "user", "商品": "item", "时间": "time",
        "订单金额": "amount", "商品数量": "quantity", "优惠金额": "discount", "实付金额": "paid",
        "件数": "qty", "订单数": "order_cnt", "优惠率": "discount_rate",
        "支付金额": "pay_amount", "支付笔数": "pay_cnt", "手续费": "fee", "支付成功率": "pay_rate",
        "发货单数": "ship_cnt", "发货件数": "ship_qty", "发货金额": "ship_amount", "运费": "freight",
        "发货时长": "ship_duration", "当前库存": "stock", "收货单数": "receive_cnt",
        "收货金额": "receive_amount", "收货时长": "receive_duration",
        "退货单数": "return_cnt", "退货金额": "return_amount", "退货率": "return_rate",
        "评价数": "review_cnt", "评分": "score", "好评数": "good_review_cnt", "好评率": "good_rate",
        "注册用户数": "register_cnt", "登录次数": "login_cnt", "在线时长": "online_duration",
    }
    text = (text or "").strip()
    if text in CN_MAP:
        return CN_MAP[text]
    if not text:
        return "x"
    # 简单清理:替换非字母数字
    safe = "".join(c if (c.isascii() and (c.isalnum() or c == "_")) else "" for c in text)
    return safe.lower() or "x"


# ============================================================
# 周期快照事实表 (Periodic Snapshot Fact Table)
# ============================================================
# 来源: Kimball 第 4 章
# 核心特征:
#   - 一行 = 一个实体在周期末的状态(如 账户余额 / 库存 / 在线人数)
#   - 周期性产生(每日/每周/每月)
#   - 事实多为半可加(状态度量)
#   - 用于"看趋势"和"对比期初期末"
# 半可加性处理:
#   - 不能跨时间 SUM,只能取最新值或 AVG
#   - 例: 账户余额 — 看每天余额,不能 SUM(余额+余额 无意义)
#     正确做法: SUM(期末余额) 或 AVG(余额)

def design_periodic_snapshot(
    entity: str,
    period: str,
    snapshot_facts: list[str],
    dimensions: list[str],
) -> dict[str, Any]:
    """设计周期快照事实表 (Kimball 第 4 章)。

    Args:
        entity: 实体名(如 "账户" / "库存SKU")。
        period: 周期("daily" / "weekly" / "monthly")。
        snapshot_facts: 快照事实列表(如 ["余额", "积分", "在线时长"])。
        dimensions: 维度列表(如 ["用户", "账户类型"])。

    Returns:
        dict:
            {
                "table_name": str,
                "ddl_template": str,
                "etl_pattern": str,
                "semi_additive_handling": str,
                "design_notes": list
            }

    半可加性处理 (Semi-additive Handling):
        - 状态型事实(余额/库存/在线人数) — 用 LAST_VALUE 聚合,不能 SUM。
        - 期间累计型(在线时长) — 用 SUM。
        - 期间平均型(平均余额) — 用 AVG。

    Examples:
        >>> r = design_periodic_snapshot(
        ...     "账户", "daily",
        ...     ["余额", "积分"],
        ...     ["用户", "账户类型"]
        ... )
        >>> "snapshot" in r['table_name'] or "dws" in r['table_name']
        True
    """
    table_name = f"dws_{_safe_name(entity)}_{period}_snapshot"

    ddl = (
        f"CREATE TABLE {table_name} (\n"
        f"  -- 主键\n"
        f"  {_safe_name(entity)}_key     BIGINT       NOT NULL,\n"
    )
    for dim in dimensions:
        ddl += f"  {_safe_name(dim)}_key     BIGINT       COMMENT '{dim}外键',\n"
    ddl += f"  -- 周期\n"
    ddl += f"  snapshot_date   DATE         NOT NULL  COMMENT '快照日期',\n"
    ddl += f"  -- 事实(多为半可加状态量)\n"
    for f in snapshot_facts:
        ddl += f"  {_safe_name(f)}      DECIMAL(18,2) COMMENT '{f}快照值',\n"
    ddl += f"  -- 分区\n"
    ddl += f"  dt              STRING       NOT NULL  COMMENT '数据日期(分区)'\n"
    ddl += f");\n"
    ddl += f"PARTITIONED BY (dt STRING);\n"

    semi_additive_handling = (
        "半可加事实(余额/库存/状态量)的查询处理:\n"
        "  错误: SELECT SUM(balance) FROM snapshot  -- 跨时间 SUM 无意义\n"
        "  正确: SELECT LAST_VALUE(balance) OVER (PARTITION BY user_key ORDER BY snapshot_date)\n"
        "        或 SELECT balance FROM snapshot WHERE snapshot_date = '目标日'\n"
        "期间累计(在线时长)用 SUM,期间平均(平均余额)用 AVG。"
    )

    etl_pattern = (
        f"INSERT INTO {table_name}\n"
        f"SELECT\n"
        f"  user_key, account_type_key,  -- 维度\n"
        f"  '{TODAY}' AS snapshot_date,\n"
        f"  balance, points,             -- 半可加状态值\n"
        f"  dt\n"
        f"FROM (\n"
        f"  -- 取当日末最新状态\n"
        f"  SELECT *, ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY update_time DESC) AS rn\n"
        f"  FROM ods_account_state WHERE dt = '{TODAY}'\n"
        f") t WHERE rn = 1;"
    )

    return {
        "table_name": table_name,
        "fact_type": "periodic_snapshot",
        "ddl_template": ddl,
        "etl_pattern": etl_pattern,
        "semi_additive_handling": semi_additive_handling,
        "design_notes": [
            f"周期 = {period},每周期产生 1 行(每个实体)",
            f"事实多为半可加({', '.join(snapshot_facts)})",
            "查询时跨周期用 LAST_VALUE / AVG,不能直接 SUM",
        ],
    }


# 标记常量,避免在 docstring 里出现 'YYYY-MM-DD' 这种硬编码导致 lint 报错
TODAY = "2026-08-11"


# ============================================================
# 累积快照事实表 (Accumulating Snapshot Fact Table)
# ============================================================
# 来源: Kimball 第 4 章
# 核心特征:
#   - 一行 = 一个业务全生命周期(下单→支付→发货→收货)
#   - 多个日期外键(每个过程一个时间戳)
#   - 多个延迟事实(每个过程一个耗时)
#   - 数据更新(不只 insert,还有 update)
# 物理实现:
#   - 全量表(每次 ETL 全量覆盖)
#   - 分区表(按业务开始日 / 数据日期)
#   - 归档表(生命周期结束归档到冷存储)

def design_accumulating_snapshot(
    business_lifecycle: list[str],
    date_fields: list[str],
    duration_fields: list[str],
    dimensions: list[str],
) -> dict[str, Any]:
    """设计累积快照事实表 (Kimball 第 4 章)。

    Args:
        business_lifecycle: 业务生命周期过程列表(如 ["下单","支付","发货","收货"])。
        date_fields: 日期字段列表(每个过程一个,如 ["下单日期","支付日期",...])。
        duration_fields: 延迟/耗时字段(如 ["下单-支付耗时", "支付-发货耗时"])。
        dimensions: 维度列表。

    Returns:
        dict:
            {
                "table_name": str,
                "ddl_template": str,
                "etl_pattern": str,   # 含 update 逻辑
                "physical_options": dict,  # 全量/分区/归档
                "design_notes": list
            }

    Examples:
        >>> r = design_accumulating_snapshot(
        ...     ["下单","支付","发货","收货"],
        ...     ["下单日期","支付日期","发货日期","收货日期"],
        ...     ["下单-支付耗时","支付-发货耗时"],
        ...     ["用户","商品"]
        ... )
        >>> "accumulating" in r['table_name'] or "acc" in r['table_name']
        True
    """
    lifecycle_slug = "_".join(_safe_name(p) for p in business_lifecycle[:3])
    table_name = f"dwd_{lifecycle_slug}_acc_snapshot"

    ddl = (
        f"CREATE TABLE {table_name} (\n"
        f"  -- 主键(业务主键)\n"
        f"  primary_id        BIGINT       NOT NULL  COMMENT '业务单号(订单号)',\n"
    )
    for dim in dimensions:
        ddl += f"  {_safe_name(dim)}_key     BIGINT       COMMENT '{dim}外键',\n"
    ddl += f"  -- 多过程日期(每个过程一个时间戳)\n"
    for d in date_fields:
        ddl += f"  {_safe_name(d)}        TIMESTAMP    COMMENT '{d}',\n"
    ddl += f"  -- 延迟事实(每两个过程之间一个)\n"
    for dur in duration_fields:
        ddl += f"  {_safe_name(dur)}    BIGINT       COMMENT '{dur}(秒)',\n"
    ddl += f"  -- 终态标识\n"
    ddl += f"  end_status        STRING       COMMENT '完结/进行中/异常',\n"
    ddl += f"  -- 分区\n"
    ddl += f"  start_dt          STRING       NOT NULL  COMMENT '业务开始日(分区)'\n"
    ddl += f");\n"
    ddl += f"PARTITIONED BY (start_dt STRING);\n"

    etl_pattern = (
        "-- 累积快照的特殊 ETL:UPSERT 模式\n"
        "1) 新行(主键不存在):\n"
        f"   INSERT INTO {table_name} (primary_id, ..., start_dt)\n"
        "   SELECT order_id, ..., dt FROM ods_order_new WHERE dt = '${today}';\n\n"
        "2) 已存在行(主键已存在):UPDATE 该行的对应日期字段\n"
        f"   UPDATE {table_name} t\n"
        "   SET t.pay_date = s.pay_date,\n"
        "       t.pay_ship_duration = s.ship_date - s.pay_date\n"
        "   FROM ods_order_pay s\n"
        "   WHERE t.primary_id = s.order_id\n"
        "     AND t.pay_date IS NULL\n"
        "     AND s.dt = '${today}';\n\n"
        "3) 终态:所有日期都填好后,标记 end_status = '完结'\n"
        f"   UPDATE {table_name} SET end_status = '完结'\n"
        "   WHERE pay_date IS NOT NULL\n"
        "     AND ship_date IS NOT NULL\n"
        "     AND receive_date IS NOT NULL\n"
        "     AND end_status = '进行中';"
    )

    physical_options = {
        "full_refresh": "适合:数据量小(< 1亿行),每次 ETL 全量覆盖,简单但慢。",
        "partitioned": (
            "推荐:按 start_dt 分区(业务开始日),新数据写新分区,"
            "老数据已完结可压缩/归档。"
        ),
        "archive": (
            "归档:生命周期结束(如 6 个月前完结的订单)的数据 move 到冷存储"
            "(OSS/Glacier),主表只保留近 6 个月热数据。"
        ),
        "compaction": "定期合并小文件(累积快照 UPDATE 频繁,小文件多)。",
    }

    return {
        "table_name": table_name,
        "fact_type": "accumulating_snapshot",
        "ddl_template": ddl,
        "etl_pattern": etl_pattern,
        "physical_options": physical_options,
        "design_notes": [
            f"业务过程 = {len(business_lifecycle)} 个,需要 {len(date_fields)} 个日期字段",
            "UPDATE 频繁,建议用主键索引 + 分区裁剪",
            "终态(end_status)用于快速过滤'进行中'/'已完结'",
            "延迟事实(耗时)用 TIMESTAMPDIFF 计算,可下钻分析",
        ],
    }


# ============================================================
# 聚集型事实表 / DWS 汇总表 (Aggregated Fact Table)
# ============================================================
# 来源: Kimball 第 4 章 + 阿里 OneData 第 3 章
# 核心特征:
#   - 由明细表(DWD)汇总而来
#   - 主题宽表(用户宽表/商品宽表/商家宽表)
#   - 周期化(1d/1w/1m/td)
#   - 用于 ADS 直接查询,避免 ADS 扫明细
# 设计原则:
#   1. 不可下钻: DWS 汇总后,ADS 不能下钻回 DWD 同一粒度
#      (避免重复存储 + 口径不一)
#   2. 主题化: 一个主题一张宽表(用户宽表聚合所有用户相关指标)
#   3. 周期化: 按时间周期汇总(1d = 当日,td = 累计至今)

def design_aggregated_fact(
    subject: str,
    base_grain: str,
    aggregation_period: str,
    metrics: list[str],
    dimensions: list[str],
) -> dict[str, Any]:
    """设计聚集型事实表 / DWS 汇总表 (Kimball 第 4 章 + 阿里 OneData 第 3 章)。

    Args:
        subject: 主题(如 "用户" / "商品" / "商家")。
        base_grain: 基础粒度(如 "子订单")。
        aggregation_period: 汇总周期("1d"/"1w"/"1m"/"td")。
        metrics: 指标列表(如 ["GMV", "订单数", "客单价"])。
        dimensions: 维度列表(如 ["用户等级", "注册渠道"])。

    Returns:
        dict:
            {
                "table_name": str,
                "ddl_template": str,
                "etl_pattern": str,
                "principles": list,    # 阿里 OneData 原则
                "design_notes": list
            }

    Examples:
        >>> r = design_aggregated_fact(
        ...     "用户", "子订单", "1d",
        ...     ["GMV", "订单数"], ["用户等级"]
        ... )
        >>> "dws" in r['table_name']
        True
    """
    table_name = f"dws_{_safe_name(subject)}_{aggregation_period}"

    ddl = (
        f"CREATE TABLE {table_name} (\n"
        f"  -- 主键(主题实体)\n"
        f"  {_safe_name(subject)}_key        BIGINT       NOT NULL  COMMENT '{subject}ID',\n"
    )
    for dim in dimensions:
        ddl += f"  {_safe_name(dim)}_key      BIGINT       COMMENT '{dim}外键',\n"
    ddl += f"  -- 周期\n"
    ddl += f"  stat_date           DATE         NOT NULL  COMMENT '统计日期(对应 1d/1w/1m/td)'\n"
    if aggregation_period == "td":
        ddl = ddl.replace("'统计日期(对应 1d/1w/1m/td)'", "'统计日期(td = 当日截止)'")
    ddl += f"  -- 汇总指标\n"
    for m in metrics:
        ddl += f"  {_safe_name(m)}              DECIMAL(18,2) COMMENT '{m}',\n"
    ddl += f"  -- 分区\n"
    ddl += f"  dt                  STRING       NOT NULL  COMMENT '数据日期(分区)'\n"
    ddl += f");\n"
    ddl += f"PARTITIONED BY (dt STRING);\n"

    etl_pattern = (
        f"INSERT OVERWRITE TABLE {table_name} PARTITION (dt='{TODAY}')\n"
        f"SELECT\n"
        f"  user_key, user_level_key,  -- 主题+维度\n"
        f"  '{TODAY}' AS stat_date,\n"
        f"  SUM(amount) AS gmv,        -- 汇总指标\n"
        f"  COUNT(DISTINCT order_id) AS order_cnt,\n"
        f"  SUM(amount) / NULLIF(COUNT(DISTINCT order_id), 0) AS avg_amount\n"
        f"FROM dwd_order_detail\n"
        f"WHERE dt BETWEEN '{START_OF_PERIOD}' AND '{TODAY}'\n"
        f"GROUP BY user_key, user_level_key;"
    )

    principles = [
        "原则 1 (粒度一致): DWS 内的指标粒度必须一致(都是用户级或都是订单级)",
        f"原则 2 (周期对齐): 同一 DWS 表内所有指标的周期必须相同({aggregation_period})",
        "原则 3 (主题聚焦): 一张 DWS 表只服务一个主题(用户/商品/商家)",
        "原则 4 (冗余换性能): DWS 可牺牲部分存储,换 ADS 查询性能",
        "原则 5 (不可二次聚合): DWS 不能再被 DWS 聚合(避免精度损失)",
    ]

    return {
        "table_name": table_name,
        "fact_type": "aggregated",
        "ddl_template": ddl,
        "etl_pattern": etl_pattern,
        "principles": principles,
        "design_notes": [
            f"主题 = {subject},粒度 = 每 {subject} 一行,周期 = {aggregation_period}",
            f"汇总自 DWD(基础粒度 = {base_grain})",
            f"指标数 = {len(metrics)},维度数 = {len(dimensions)}",
            "DWS 是 ADS 的物理基础,减少 ADS 扫明细的压力",
        ],
    }


START_OF_PERIOD = "2026-01-01"


# ============================================================
# 不可加事实拆分 (Non-additive Fact Decomposition)
# ============================================================
# 来源: Kimball 第 4 章
# 核心思想: 比率型事实(如 利润率/转化率)不可直接加和,必须拆为 分子 + 分母
# 例:
#   - 利润率 = 利润 / 收入 → 存 利润 和 收入,查询时相除
#   - 客单价 = GMV / 订单数 → 存 GMV 和 订单数,查询时相除
#   - CTR = 点击 / 曝光 → 存 点击数 和 曝光数
# 反例: 存"利润率"本身 → 跨维度 AVG(利润率) 不等于 真实利润率

def decompose_non_additive_fact(
    fact_name: str,
    formula: str,
) -> dict[str, Any]:
    """拆分不可加事实 (Kimball 第 4 章)。

    Args:
        fact_name: 比率名(如 "客单价" / "转化率" / "利润率")。
        formula: 公式(如 "GMV / 订单数")。

    Returns:
        dict:
            {
                "original": str,
                "numerator": str,         # 分子
                "denominator": str,       # 分母
                "fact_type": str,         # additive
                "implementation": str,
                "warning": str
            }

    判定依据 (Decision Rules):
        - 解析 formula 字符串,提取分子和分母。
        - 分子分母都是 additive 事实。
        - 派生计算在 SQL 端用 numerator / NULLIF(denominator, 0) 完成。

    边界情况 (Edge Cases):
        - 公式不能解析(不含 /) → 抛 ValueError。
        - 分母是 0 → 用 NULLIF 防御。

    Examples:
        >>> r = decompose_non_additive_fact("客单价", "GMV / 订单数")
        >>> r['numerator']
        'GMV'
        >>> r['denominator']
        '订单数'
    """
    if not formula or "/" not in formula:
        raise ValueError(
            f"不可加事实必须给出公式(分子/分母, 用 '/' 分隔),当前: '{formula}'"
        )
    parts = [p.strip() for p in formula.split("/")]
    if len(parts) != 2:
        raise ValueError(f"公式格式错误, 应为 '分子 / 分母', 当前: '{formula}'")
    numerator, denominator = parts

    return {
        "original": fact_name,
        "numerator": numerator,
        "denominator": denominator,
        "numerator_fact": {
            "name": numerator,
            "additivity": "additive",
            "rationale": f"'{fact_name}' 的分子,可加。",
        },
        "denominator_fact": {
            "name": denominator,
            "additivity": "additive",
            "rationale": f"'{fact_name}' 的分母,可加。",
        },
        "calculation_sql": f"{numerator} / NULLIF({denominator}, 0)",
        "implementation": (
            f"事实表只存分子({numerator})和分母({denominator}),不存'{fact_name}'本身。\n"
            f"查询时计算: {numerator} / NULLIF({denominator}, 0) AS {fact_name}\n"
            f"用 NULLIF 防止除零错误。"
        ),
        "warning": (
            f"严禁把 '{fact_name}' 直接存为事实字段。"
            "否则跨维度 AVG/MAX 时会得到错误结论(应取 SUM(分子)/SUM(分母) 而非 AVG(比率))。"
        ),
    }


# ============================================================
# 退化维度使用 (Degenerate Dimension in Fact Tables)
# ============================================================
# 来源: Kimball 第 3 章 + 第 5 章
# 见 dimensions.py 的 identify_degenerate_dimension
# 本函数给出在事实表中的具体使用模式

def place_degenerate_dimension(
    fact_table: str,
    degenerate_field: str,
    is_also_primary_key: bool = True,
) -> dict[str, Any]:
    """在事实表中放置退化维度 (Kimball 第 5 章)。

    Args:
        fact_table: 事实表名。
        degenerate_field: 退化维度字段名(如 "订单号")。
        is_also_primary_key: 是否同时作为主键(通常 YES)。

    Returns:
        dict:
            {
                "ddl_snippet": str,
                "use_cases": list,
                "anti_patterns": list
            }

    使用场景 (Use Cases):
        - 业务单号(订单号/支付单号)本身是分析维度(分订单号段分析)
        - 发票号(财务追踪)
        - 流水号(审计追踪)

    反模式 (Anti-patterns):
        - 用作外键关联 → 应建独立维表
        - 当成主维的代理 → 主维应该独立存在

    Examples:
        >>> r = place_degenerate_dimension("dwd_order_detail", "订单号")
        >>> "BIGINT" in r['ddl_snippet'] or "STRING" in r['ddl_snippet']
        True
    """
    ddl = (
        f"-- 在事实表 {fact_table} 中添加退化维度:\n"
        f"ALTER TABLE {fact_table} ADD COLUMN {degenerate_field} STRING\n"
        f"COMMENT '退化维度(业务单号, 不建独立维表)'"
    )
    if is_also_primary_key:
        ddl += ";\n-- 通常作为事实表的非代理主键(联合主键的一部分)"

    use_cases = [
        f"按 {degenerate_field} 分段分析(订单号前 4 位分析来源渠道)",
        f"用 {degenerate_field} 钻取明细(查具体订单的所有事实)",
        f"用 {degenerate_field} 做 COUNT DISTINCT(订单数 = COUNT(DISTINCT 订单号))",
    ]
    anti_patterns = [
        f"❌ 用 {degenerate_field} 关联维表 → 错!应建独立 dim_xxx 表",
        f"❌ 把 {degenerate_field} 拆出来当维表 → 浪费,维表无有意义属性",
        f"❌ 把 {degenerate_field} 重复存多份 → 占空间,只放事实表即可",
    ]

    return {
        "ddl_snippet": ddl,
        "use_cases": use_cases,
        "anti_patterns": anti_patterns,
        "design_notes": [
            f"退化维度 {degenerate_field} 放在事实表, 不建独立维表",
            "如果需要分析 订单号 本身的属性(如签发地/有效期),再建维表",
        ],
    }


# ============================================================
# 综合入口
# ============================================================


def fact_overview() -> dict[str, Any]:
    """事实表设计总览。"""
    return {
        "fact_types": {
            "transaction": {
                "row_meaning": "一个业务事件(原子粒度)",
                "primary_key": "事件 ID",
                "fact_additivity": "全可加",
                "use_case": "高频事件(下单/登录/支付)",
                "source": "Kimball 第 4 章",
            },
            "periodic_snapshot": {
                "row_meaning": "一个实体在周期末的状态",
                "primary_key": "实体 ID + 周期",
                "fact_additivity": "多为半可加",
                "use_case": "状态度量(库存/账户余额)",
                "source": "Kimball 第 4 章",
            },
            "accumulating_snapshot": {
                "row_meaning": "一个业务全生命周期",
                "primary_key": "业务单号",
                "fact_additivity": "全可加(每个过程一个时间戳)",
                "use_case": "流程型业务(订单全流程/工单)",
                "source": "Kimball 第 4 章",
            },
            "aggregated": {
                "row_meaning": "一个主题在某周期的汇总",
                "primary_key": "主题 ID + 周期",
                "fact_additivity": "全可加(SUM/AVG/COUNT)",
                "use_case": "ADS 直接查询 / 主题宽表",
                "source": "阿里 OneData 第 3 章",
            },
        },
        "key_principles": {
            "semi_additive_handling": "状态量不能跨时间 SUM,用 LAST_VALUE 或 AVG",
            "non_additive_decomposition": "比率必须拆为分子+分母,查询时计算",
            "degenerate_dimension": "业务单号放事实表,不建独立维表",
            "physical_layout": "事务/累积表 按 dt 分区,DWS 按 dt+主题",
        },
    }
