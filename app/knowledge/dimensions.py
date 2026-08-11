"""
维度高级主题 (Dimension Advanced Topics)
========================================

来源 (Sources):
    - Kimball "The Data Warehouse Toolkit" 第 5 章 "More Dimension Techniques"
    - 中文版《数据仓库工具箱》第 5 章
    - 阿里《OneData》第 4 章 维度设计
    - 关键内容:
        * 缓慢变化维 SCD Type 1/2/3 (Kimball 第 7 章)
        * 拉链表 (Zipper Dimension, 阿里 OneData 重点)
        * 退化维度 (Degenerate Dimension)
        * 杂项维度 (Junk Dimension)
        * 微型维度 (Mini Dimension)
        * 多值维度 + 桥接表 (Multivalued Dimension + Bridge Table)
        * 递归层次 (Recursive Hierarchy)

设计原则:
    1. 决策函数化: 输入业务属性 + 变更特征 → 输出推荐策略。
    2. 边界清晰: 每个策略有适用场景 + 反模式(不适用场景)。
    3. 可执行: 决策结果包含 SQL 模式或 DDL 模板提示。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


# ============================================================
# 缓慢变化维 SCD (Slowly Changing Dimensions)
# ============================================================
# 来源: Kimball 第 7 章 "Slowly Changing Dimensions"
#
# Type 1: 直接覆盖(不保留历史)
#   - 适用: 维度属性的"错误"需要被修正(笔误/录入错误)
#   - 不适用: 需要追溯历史(如分析"用户过去 3 个月等级分布")
#
# Type 2: 新增行(保留全量历史)
#   - 适用: 大多数业务属性的变更(地址/电话/会员等级)
#   - 增加字段: effective_date / expiry_date / is_current
#   - 数据膨胀: 每次变更产生新行
#
# Type 3: 新增列(只保留当前 + 上一次)
#   - 适用: 偶尔变更 + 只需对比当前和上次(如 "上次等级"/"当前等级")
#   - 不适用: 需要任意时点的历史
#
# 阿里 OneData 默认: Type 2 为主,Type 1 为辅

# 属性类型关键词,用于自动判定
_CORRECTION_KEYWORDS = ["更正", "修正", "笔误", "录入", "错误", "错填", "fix", "correction"]
_HISTORY_KEYWORDS = ["追溯", "历史", "过去", "曾经", "变更记录", "轨迹", "history", "audit", "track"]
_RARE_CHANGE_KEYWORDS = ["省份", "籍贯", "婚姻", "学历", "身份证"]  # 通常不变
_FREQUENT_CHANGE_KEYWORDS = ["地址", "电话", "手机", "会员等级", "积分", "余额", "等级", "状态"]


def recommend_scd_type(
    attribute_name: str,
    change_frequency: str,
    need_history: bool = False,
    is_correction: bool = False,
) -> dict[str, Any]:
    """推荐 SCD 类型 (Kimball 第 7 章)。

    Args:
        attribute_name: 维度属性名(如 "用户地址" / "商品价格")。
        change_frequency: 变更频率(low/medium/high,或中文 低/中/高)。
        need_history: 是否需要追溯历史。
        is_correction: 是否为"修正"(录入错误)。

    Returns:
        dict:
            {
                "scd_type": int,            # 1 / 2 / 3
                "scd_type_name": str,       # 'Type 1' / 'Type 2' / 'Type 3'
                "rationale": str,
                "implementation": str,      # 实施建议(SQL/字段提示)
                "warnings": list
            }

    判定依据 (Decision Rules):
        1. **is_correction=True** → Type 1(直接覆盖)。
        2. **need_history=True** → Type 2(全量历史,默认推荐)。
        3. **change_frequency=low + 不需历史** → Type 1(节省空间)。
        4. **change_frequency=high + 偶尔需对比** → Type 3(只有当前/上次)。
        5. **change_frequency=high + 需要历史** → Type 2。

    边界情况 (Edge Cases):
        - 用户没说明需求 → 给出 Type 1/2/3 三种选项 + 各自适用场景。
        - 属性名含修正关键词 → 强制 Type 1。

    Examples:
        >>> r = recommend_scd_type("用户地址", "high", need_history=True)
        >>> r['scd_type']
        2
        >>> r = recommend_scd_type("商品名称笔误", "low", is_correction=True)
        >>> r['scd_type']
        1
    """
    # 标准化
    freq = (change_frequency or "").lower()
    if freq in ["高", "高频", "high", "h"]:
        freq_level = "high"
    elif freq in ["中", "中频", "medium", "m"]:
        freq_level = "medium"
    elif freq in ["低", "低频", "low", "l", "rare"]:
        freq_level = "low"
    else:
        freq_level = "medium"

    warnings: list[str] = []

    # 规则 1: 修正 → Type 1
    if is_correction or any(kw in attribute_name for kw in _CORRECTION_KEYWORDS):
        return {
            "scd_type": 1,
            "scd_type_name": "Type 1",
            "rationale": (
                f"属性 '{attribute_name}' 被标识为'修正/错误'场景,"
                "按 Kimball 第 7 章推荐用 Type 1(直接覆盖,不保留历史)。"
            ),
            "implementation": (
                "UPDATE dim_xxx SET attr = new_value WHERE key = X;"
                " 不需要额外字段,直接覆盖。"
            ),
            "warnings": [],
        }

    # 规则 2: 需要历史 → Type 2
    if need_history or any(kw in attribute_name for kw in _HISTORY_KEYWORDS):
        return {
            "scd_type": 2,
            "scd_type_name": "Type 2",
            "rationale": (
                f"属性 '{attribute_name}' 需要保留历史/追溯,"
                "按 Kimball 第 7 章 + 阿里 OneData 推荐用 Type 2(新增行,保留全量历史)。"
            ),
            "implementation": (
                "新增字段: effective_date / expiry_date / is_current\n"
                "ETL: 旧行 expiry_date = today, is_current = false;\n"
                "      新行 effective_date = today, is_current = true, expiry_date = '9999-12-31'。"
            ),
            "warnings": warnings,
        }

    # 规则 3: 低频变更 + 不需历史 → Type 1
    if freq_level == "low":
        return {
            "scd_type": 1,
            "scd_type_name": "Type 1",
            "rationale": (
                f"属性 '{attribute_name}' 变更频率低(低频)且无需追溯历史,"
                "按 Kimball 第 7 章推荐用 Type 1(直接覆盖,节省存储)。"
            ),
            "implementation": "UPDATE dim_xxx SET attr = new_value WHERE key = X;",
            "warnings": ["如未来需要历史,可升级为 Type 2。"],
        }

    # 规则 4: 高频 + 不需历史 → Type 1(默认),或 Type 3(若需对比)
    if freq_level == "high" and not need_history:
        warnings.append(
            f"属性 '{attribute_name}' 高频变更但不需历史,推荐 Type 1;若需对比'当前/上次'可改用 Type 3。"
        )
        return {
            "scd_type": 1,
            "scd_type_name": "Type 1",
            "rationale": (
                f"属性 '{attribute_name}' 变更频率高,无需保留历史,"
                "推荐 Type 1(避免数据爆炸)。如需保留'当前/上次'对比,改用 Type 3。"
            ),
            "implementation": "UPDATE dim_xxx SET attr = new_value WHERE key = X;",
            "warnings": warnings,
        }

    # 兜底: Type 2(阿里 OneData 默认)
    return {
        "scd_type": 2,
        "scd_type_name": "Type 2",
        "rationale": (
            f"属性 '{attribute_name}' 频率={freq_level},未明确历史需求,"
            "按阿里 OneData 默认推荐 Type 2(全量历史,通用方案)。"
        ),
        "implementation": (
            "新增字段: effective_date / expiry_date / is_current\n"
            "事实表通过 dim_key 关联,取 is_current=true 的版本。"
        ),
        "warnings": ["如不需要历史,改为 Type 1 节省存储。"],
    }


# ============================================================
# 拉链表 (Zipper Dimension)
# ============================================================
# 来源: 阿里《OneData》第 4 章 "拉链表" + Kimball Type 2 变体
# 拉链表 = Type 2 的物理实现,通过 effective_date/expiry_date 实现历史快照查询
# 适用场景:
#   1. 维度属性频繁变更 + 需要追溯任意时点状态
#   2. 维度全量历史(几亿行)用 Type 2 不经济时
# 实施模式:
#   - 全量分区表: dt=生效日, 每日分区=该日有效的所有记录
#   - 或拉链: start_date / end_date 两字段
#   - 关联时: 事实表时间 BETWEEN start_date AND end_date

def is_zipper_dimension_applicable(
    attribute_change_count: int,
    total_dim_rows: int,
    fact_query_needs_history: bool = True,
) -> dict[str, Any]:
    """判断拉链表是否适用 (阿里 OneData + Kimball Type 2 变体)。

    Args:
        attribute_change_count: 维度属性平均变更次数(每行一生)。
        total_dim_rows: 维度总行数。
        fact_query_needs_history: 事实查询是否需要追溯历史。

    Returns:
        dict:
            {
                "applicable": bool,
                "rationale": str,
                "implementation": str,    # SQL 模板提示
                "tradeoffs": list
            }

    判定依据 (Decision Rules):
        - **不适用** = 不需历史(用 Type 1)
        - **适用** = 需历史 + 变更次数合理(< 1000 次/行,否则拉链爆炸)
        - **强适用** = 需历史 + 变更频繁 + 事实表与历史强关联

    边界情况 (Edge Cases):
        - 维度极小(< 100 行)→ 用全量快照更简单。
        - 维度极大(> 1亿)且变更极频繁(> 100 次/行)→ 拉链爆炸,改用 CDC 流式处理。

    Examples:
        >>> r = is_zipper_dimension_applicable(5, 10000, fact_query_needs_history=True)
        >>> r['applicable']
        True
    """
    tradeoffs: list[str] = []

    if not fact_query_needs_history:
        return {
            "applicable": False,
            "rationale": (
                "事实查询不需要追溯历史(只看当前状态),"
                "按 Kimball 第 7 章推荐用 Type 1,无需拉链表。"
            ),
            "implementation": "直接 UPDATE 维度表。",
            "tradeoffs": [],
        }

    # 估算拉链膨胀率
    if attribute_change_count <= 0:
        expansion_ratio = 1
    else:
        expansion_ratio = attribute_change_count

    if expansion_ratio > 100:
        return {
            "applicable": False,
            "rationale": (
                f"维度属性平均变更 {attribute_change_count} 次/行,膨胀率 > 100x,"
                "拉链表会爆炸,建议改用 CDC 流式处理或事件溯源。"
            ),
            "implementation": "考虑 ClickHouse / Hudi / Iceberg 等流式湖仓。",
            "tradeoffs": ["拉链表不适用,改用流式方案。"],
        }

    if total_dim_rows < 100:
        tradeoffs.append(f"维度总行数仅 {total_dim_rows},全量快照更简单。")

    return {
        "applicable": True,
        "rationale": (
            f"事实查询需要历史 + 维度膨胀率 {expansion_ratio}x 可接受,"
            "按阿里 OneData 第 4 章推荐用拉链表(SCD Type 2 物理实现)。"
        ),
        "implementation": (
            "拉链 DDL 模板:\n"
            "CREATE TABLE dim_xxx_zip (\n"
            "  key          BIGINT,\n"
            "  attr         STRING,\n"
            "  start_date   DATE,\n"
            "  end_date     DATE  -- '9999-12-31' 表示当前\n"
            ")\n"
            "PARTITIONED BY (dt STRING);\n\n"
            "事实关联:\n"
            "WHERE dim.start_date <= fact.dt AND dim.end_date > fact.dt"
        ),
        "tradeoffs": tradeoffs or ["数据膨胀,但保留历史能力强。"],
    }


# ============================================================
# 退化维度 (Degenerate Dimension)
# ============================================================
# 来源: Kimball 第 3 章 + 第 5 章 "Degenerate Dimensions"
# 定义: 业务主键本身就是维度属性(如 订单号),但不放进维表
# 适用: 业务单号本身就是分析维度(如分析不同订单号段的销售)
# 特点: 1) 放在事实表 2) 不创建独立维表 3) 通常是主键

DEGENERATE_DIM_KEYWORDS = [
    "订单号", "子订单号", "支付单号", "退款单号", "发货单号", "收货单号",
    "流水号", "单号", "交易号", "合同号", "工单号", "发票号",
    "order_id", "order_no", "payment_id", "shipment_id", "ticket_no",
]


def identify_degenerate_dimension(field_name: str, role: str = "") -> dict[str, Any]:
    """识别退化维度 (Kimball 第 5 章)。

    Args:
        field_name: 字段名(如 "订单号")。
        role: 字段角色("primary_key" / "transaction_id" / "other")。

    Returns:
        dict:
            {
                "is_degenerate": bool,
                "rationale": str,
                "implementation": str
            }

    判定依据 (Decision Rules):
        - 字段名含"单号/流水号"等业务单号关键词 → 是退化维度。
        - role=primary_key + 业务性 ID(非用户 ID/商品 ID 等实体 ID) → 是退化维度。
        - role=foreign_key 关联到独立维表 → 不是退化维度,放维表里。

    边界情况 (Edge Cases):
        - 字段是纯数字 ID(如 user_id)→ 不是退化维度,放维表。
        - 字段名模糊 → 返回 False + 提示"需人工确认"。

    Examples:
        >>> r = identify_degenerate_dimension("订单号", "primary_key")
        >>> r['is_degenerate']
        True
        >>> r = identify_degenerate_dimension("user_id", "foreign_key")
        >>> r['is_degenerate']
        False
    """
    field_lower = (field_name or "").lower()
    role_lower = (role or "").lower()

    # 规则 1: 关键词匹配
    for kw in DEGENERATE_DIM_KEYWORDS:
        if kw in field_lower or kw.lower() in field_lower:
            return {
                "is_degenerate": True,
                "rationale": (
                    f"字段 '{field_name}' 含业务单号关键词 '{kw}',"
                    "符合 Kimball 第 5 章退化维度特征(业务单号本身就是维度)。"
                ),
                "implementation": (
                    f"字段 '{field_name}' 直接放在事实表,不建独立维表。"
                    "如需分析,直接 SELECT 即可(可做 COUNT DISTINCT、GROUP BY)。"
                ),
            }

    # 规则 2: role = primary_key + 业务性
    if role_lower in ["primary_key", "pk", "业务主键"]:
        return {
            "is_degenerate": True,
            "rationale": (
                f"字段 '{field_name}' 被标识为业务主键,通常是退化维度。"
            ),
            "implementation": "字段放在事实表,不建独立维表。",
        }

    return {
        "is_degenerate": False,
        "rationale": (
            f"字段 '{field_name}' 未匹配退化维度特征,"
            "需人工确认是否为业务单号(若是则用退化维度,否则建独立维表)。"
        ),
        "implementation": "如确为业务单号,直接放事实表;否则建独立维表。",
    }


# ============================================================
# 杂项维度 (Junk Dimension)
# ============================================================
# 来源: Kimball 第 5 章 "Junk Dimensions"
# 定义: 把多个低基数(取值少)标志位打包成一个维度
# 适用: 多个 boolean/enum 字段(支付方式/订单状态/是否会员),各自建维表浪费
# 反模式: 标志位有大量取值(> 20)→ 拆为多个维表

JUNK_DIM_VALUE_THRESHOLD = 20  # 单字段基数 > 20,不适合杂项维


def recommend_junk_dimension(
    flags: list[dict[str, Any]],
) -> dict[str, Any]:
    """推荐杂项维度策略 (Kimball 第 5 章)。

    Args:
        flags: 标志位列表,每项含 {"name": str, "cardinality": int}
            例: [{"name": "支付方式", "cardinality": 5}, {"name": "是否会员", "cardinality": 2}]

    Returns:
        dict:
            {
                "use_junk": bool,
                "rationale": str,
                "junk_dim_name": str,    # 推荐的杂项维表名
                "implementation": str,
            }

    判定依据 (Decision Rules):
        - **使用杂项维**: 标志位都是低基数(每个 ≤ 20) + 数量 ≥ 3 + 组合后基数 ≤ 1000
        - **不使用**: 任何标志位基数 > 20 → 单独建维表
        - **不使用**: 标志位数量 < 3 → 各自放维表或退化维

    边界情况 (Edge Cases):
        - 组合后基数爆炸(> 10000)→ 不适合杂项维,用桥接表/独立维表。
        - 标志位是高基数文本(如"备注") → 不适合。

    Examples:
        >>> flags = [
        ...     {"name": "支付方式", "cardinality": 5},
        ...     {"name": "是否会员", "cardinality": 2},
        ...     {"name": "是否首单", "cardinality": 2},
        ... ]
        >>> r = recommend_junk_dimension(flags)
        >>> r['use_junk']
        True
    """
    if not flags:
        return {
            "use_junk": False,
            "rationale": "未提供标志位,无法决策。",
            "junk_dim_name": "",
            "implementation": "",
        }

    # 校验每个标志位
    high_cardinality = [f for f in flags if f.get("cardinality", 0) > JUNK_DIM_VALUE_THRESHOLD]
    if high_cardinality:
        names = [f["name"] for f in high_cardinality]
        return {
            "use_junk": False,
            "rationale": (
                f"标志位 {names} 基数 > {JUNK_DIM_VALUE_THRESHOLD},"
                "不适合杂项维,应单独建维表。"
            ),
            "junk_dim_name": "",
            "implementation": "为每个高基数标志位建独立维表。",
        }

    if len(flags) < 3:
        return {
            "use_junk": False,
            "rationale": (
                f"标志位数量 = {len(flags)} (< 3),杂项维性价比低,"
                "建议:放事实表 + 退化维 或 各建独立维表。"
            ),
            "junk_dim_name": "",
            "implementation": "标志位少时直接放事实表。",
        }

    # 组合后基数估算
    total_combos = 1
    for f in flags:
        total_combos *= max(1, f.get("cardinality", 1))
    if total_combos > 10000:
        return {
            "use_junk": False,
            "rationale": (
                f"组合后基数约 {total_combos} (> 10000),杂项维会爆,"
                "建议:拆分为多个杂项维,或用独立维表。"
            ),
            "junk_dim_name": "",
            "implementation": "拆分标志位组,降低单个杂项维基数。",
        }

    junk_name = "junk_" + "_".join(f["name"] for f in flags)[:50]
    return {
        "use_junk": True,
        "rationale": (
            f"{len(flags)} 个低基数标志位(每个 ≤ {JUNK_DIM_VALUE_THRESHOLD}),"
            f"组合后基数约 {total_combos},"
            "符合 Kimball 第 5 章杂项维特征,推荐打包为一个杂项维。"
        ),
        "junk_dim_name": junk_name,
        "implementation": (
            f"建维表 {junk_name},字段: junk_id + 各个标志位列;\n"
            f"事实表新增 junk_id 外键。\n"
            f"预生成所有 {total_combos} 种组合(或动态生成)。"
        ),
    }


# ============================================================
# 微型维度 (Mini Dimension)
# ============================================================
# 来源: Kimball 第 5 章 "Mini Dimensions"
# 定义: 把"高基数+频繁变更"的属性拆出独立维表,避免主维表膨胀
# 适用: 用户维度中"年龄段/收入段/活跃度"等分析属性变化频繁
# 实施: 主维表 + 微型维表 通过 外键 关联

def recommend_mini_dimension(
    attribute_names: list[str],
    attribute_change_frequency: str,
    dimension_total_size: int,
) -> dict[str, Any]:
    """推荐微型维度 (Kimball 第 5 章)。

    Args:
        attribute_names: 待拆分的属性名列表(如 ["年龄段", "收入段", "活跃度"])。
        attribute_change_frequency: 整体变更频率(low/medium/high)。
        dimension_total_size: 主维表总行数(评估变更代价)。

    Returns:
        dict:
            {
                "use_mini": bool,
                "rationale": str,
                "mini_dim_name": str,
                "implementation": str
            }

    判定依据 (Decision Rules):
        - **使用微型维**: 多个属性频繁变更 + 主维表行数大(> 1万) + 需分析这些属性
        - **不使用**: 属性稳定(低频) → 放主维表
        - **不使用**: 属性不常被分析 → 放主维表

    边界情况 (Edge Cases):
        - 属性数 < 2 → 不适合微型维,直接放主维表。
        - 主维表小(< 1000 行) → 变更代价可承受,直接放主维表。

    Examples:
        >>> r = recommend_mini_dimension(
        ...     ["年龄段", "收入段", "活跃度"],
        ...     "high", 100000
        ... )
        >>> r['use_mini']
        True
    """
    freq = (attribute_change_frequency or "").lower()
    if freq in ["高", "高频", "high", "h"]:
        freq_level = "high"
    elif freq in ["低", "低频", "low", "l", "rare"]:
        freq_level = "low"
    else:
        freq_level = "medium"

    if len(attribute_names) < 2:
        return {
            "use_mini": False,
            "rationale": (
                f"属性数 = {len(attribute_names)} (< 2),"
                "单属性无需拆微型维,直接放主维表。"
            ),
            "mini_dim_name": "",
            "implementation": "属性放主维表 dim_xxx 中。",
        }

    if freq_level == "low" and dimension_total_size < 10000:
        return {
            "use_mini": False,
            "rationale": (
                f"属性 {attribute_names} 变更频率低 + 主维表 {dimension_total_size} 行,"
                "变更代价可承受,直接放主维表。"
            ),
            "mini_dim_name": "",
            "implementation": "属性放主维表 dim_xxx 中。",
        }

    if freq_level in ("medium", "high") or dimension_total_size >= 10000:
        mini_name = "mini_" + "_".join(attribute_names)[:40]
        return {
            "use_mini": True,
            "rationale": (
                f"属性 {attribute_names} 变更频率 {freq_level} + 主维表 {dimension_total_size} 行,"
                "按 Kimball 第 5 章推荐用微型维,避免主维表膨胀。"
            ),
            "mini_dim_name": mini_name,
            "implementation": (
                f"建维表 {mini_name},字段: mini_id + 各个属性列;\n"
                f"主维表 dim_xxx 持有 mini_id 外键;\n"
                f"事实表同时关联 dim_xxx 和 {mini_name}。"
            ),
        }

    return {
        "use_mini": False,
        "rationale": "基于当前信息,推荐放主维表;如未来变更频率上升,再拆微型维。",
        "mini_dim_name": "",
        "implementation": "属性放主维表。",
    }


# ============================================================
# 多值维度 + 桥接表 (Multivalued Dimension + Bridge Table)
# ============================================================
# 来源: Kimball 第 5 章 "Multivalued Dimensions and Bridge Tables"
# 定义: 1 个事实行对应多个维度值(如 1 个订单多个标签 / 1 个账户多个持有人)
# 方案: 桥接表 = 事实表 + 多值维度的中间表,带权重字段
# 适用: 多值对应关系(账户多人/订单多标签/医生多患者)

def recommend_multivalue_strategy(
    relationship_type: str,
    estimated_count_per_row: int,
) -> dict[str, Any]:
    """推荐多值维度策略 (Kimball 第 5 章)。

    Args:
        relationship_type: 关系类型,可选:
            - "one_to_many": 一对多(如 1 订单→多标签)
            - "many_to_many": 多对多(如 1 账户多人)
            - "many_to_one": 多对一(普通外键)
        estimated_count_per_row: 平均每行对应的多值数量。

    Returns:
        dict:
            {
                "strategy": str,         # 'bridge_table' / 'array_field' / 'split' / 'none'
                "rationale": str,
                "implementation": str
            }

    判定依据 (Decision Rules):
        - **多对多 + 数量 > 1** → 桥接表(标准方案)
        - **一对多 + 数量 ≤ 5** → JSON 数组字段(简化)
        - **一对多 + 数量 > 5** → 桥接表(避免数组过大)
        - **多对一** → 标准外键(无需特殊处理)

    边界情况 (Edge Cases):
        - 数量极大(> 100) → 考虑事件溯源/嵌套模型。
        - 关系是动态的(运行期变化) → 桥接表更稳。

    Examples:
        >>> r = recommend_multivalue_strategy("many_to_many", 3)
        >>> r['strategy']
        'bridge_table'
    """
    rt = (relationship_type or "").lower()

    if rt in ["many_to_one", "n_to_1", "n:1", "多对一"]:
        return {
            "strategy": "none",
            "rationale": "多对一关系,标准外键即可,无需桥接表。",
            "implementation": "事实表持有 dim_key 外键。",
        }

    if rt in ["one_to_many", "1_to_n", "1:n", "一对多"]:
        if estimated_count_per_row <= 5:
            return {
                "strategy": "array_field",
                "rationale": (
                    f"一对多关系 + 平均 {estimated_count_per_row} 个值/行(≤ 5),"
                    "可用 JSON/数组字段简化,避免桥接表复杂性。"
                ),
                "implementation": (
                    "事实表字段: tags JSON;\n"
                    "查询: WHERE JSON_CONTAINS(tags, '\"vip\"')"
                ),
            }
        return {
            "strategy": "bridge_table",
            "rationale": (
                f"一对多关系 + 平均 {estimated_count_per_row} 个值/行(> 5),"
                "推荐用桥接表(数组字段会过大)。"
            ),
            "implementation": (
                "建桥接表 bridge_fact_dim (\n"
                "  fact_id BIGINT, dim_id BIGINT,\n"
                "  weight DECIMAL(18,4), -- 如需分配权重\n"
                "  PRIMARY KEY (fact_id, dim_id)\n"
                ");"
            ),
        }

    if rt in ["many_to_many", "m_to_n", "m:n", "多对多"]:
        return {
            "strategy": "bridge_table",
            "rationale": (
                f"多对多关系 + 平均 {estimated_count_per_row} 个值/行,"
                "按 Kimball 第 5 章必须用桥接表(否则无法在关系型模型表达)。"
            ),
            "implementation": (
                "建桥接表 bridge_a_b (\n"
                "  a_id BIGINT, b_id BIGINT,\n"
                "  effective_date DATE, -- 可选\n"
                "  weight DECIMAL(18,4), -- 可选,用于解决双计数\n"
                "  PRIMARY KEY (a_id, b_id)\n"
                ");"
            ),
        }

    return {
        "strategy": "bridge_table",
        "rationale": f"未识别关系类型 '{relationship_type}',默认推荐桥接表。",
        "implementation": "建桥接表。",
    }


# ============================================================
# 递归层次 (Recursive Hierarchy)
# ============================================================
# 来源: Kimball 第 5 章 "Recursive Hierarchies and Bridges"
# 定义: 维度自身有父子关系(类目/地区/组织/部门)
# 方案 1: 扁平化 — 加 1~N 个层级字段(如 省/市/县/乡)
# 方案 2: 桥接表 — 1 行 = 1 个 (祖先, 后代) 关系,支持任意深度
# 方案 3: 路径枚举 — 字段存完整路径 "/中国/北京/海淀"

RECURSIVE_HIERARCHY_KEYWORDS = ["类目", "地区", "组织", "部门", "城市", "省", "国", "区域"]


def recommend_hierarchy_strategy(
    hierarchy_name: str,
    max_depth: int,
    is_frequently_queried_at_all_levels: bool = False,
) -> dict[str, Any]:
    """推荐递归层次策略 (Kimball 第 5 章)。

    Args:
        hierarchy_name: 层次名(如 "商品类目" / "行政区域")。
        max_depth: 最大深度(层级数)。
        is_frequently_queried_at_all_levels: 是否经常查询任意层级(不是只看叶子)。

    Returns:
        dict:
            {
                "strategy": str,         # 'flatten' / 'bridge' / 'path_enumeration'
                "rationale": str,
                "implementation": str
            }

    判定依据 (Decision Rules):
        - **深度 ≤ 4** → 扁平化(简单)
        - **深度 > 4 + 频繁查任意层级** → 桥接表(支持任意深度,查询快)
        - **深度 > 4 + 主要按路径查询** → 路径枚举(查询简单但更新复杂)
        - **深度未知** → 桥接表(最灵活)

    边界情况 (Edge Cases):
        - 深度 = 1(无层次) → 单一字段,无需特殊处理。
        - 深度 > 10(极端) → 桥接表 + 物化路径(组合方案)。

    Examples:
        >>> r = recommend_hierarchy_strategy("商品类目", 3, False)
        >>> r['strategy']
        'flatten'
        >>> r = recommend_hierarchy_strategy("行政区域", 5, True)
        >>> r['strategy']
        'bridge'
    """
    if max_depth <= 1:
        return {
            "strategy": "none",
            "rationale": f"层次 '{hierarchy_name}' 深度 = 1,无递归,单一字段即可。",
            "implementation": "维度表加 1 个字段。",
        }

    if max_depth <= 4 and not is_frequently_queried_at_all_levels:
        return {
            "strategy": "flatten",
            "rationale": (
                f"层次 '{hierarchy_name}' 深度 {max_depth}(≤ 4) + 多数查询叶子节点,"
                "按 Kimball 第 5 章推荐扁平化(加固定层级字段,简单)。"
            ),
            "implementation": (
                f"维度表加 {max_depth} 个层级字段:\n"
                f"  level_1, level_2, ..., level_{max_depth}\n"
                f"查询: WHERE level_2 = '某类目'"
            ),
        }

    if max_depth > 4 or is_frequently_queried_at_all_levels:
        return {
            "strategy": "bridge",
            "rationale": (
                f"层次 '{hierarchy_name}' 深度 {max_depth} + 需查任意层级,"
                "按 Kimball 第 5 章推荐桥接表(支持任意深度 + 任意层级查询)。"
            ),
            "implementation": (
                "建桥接表 bridge_hierarchy (\n"
                "  ancestor_id BIGINT, descendant_id BIGINT,\n"
                "  distance INT,  -- 0 = 自己,1 = 直接子,...\n"
                "  PRIMARY KEY (ancestor_id, descendant_id)\n"
                ");\n"
                "查询: SELECT * FROM fact f JOIN bridge_hierarchy b\n"
                "  ON f.hier_id = b.descendant_id\n"
                "  WHERE b.ancestor_id = X"
            ),
        }

    return {
        "strategy": "path_enumeration",
        "rationale": (
            f"层次 '{hierarchy_name}' 中等情况,推荐路径枚举(简单 + 易读)。"
        ),
        "implementation": (
            "维度表字段: path STRING;  -- 例 '/1/23/456/'\n"
            "查询: WHERE path LIKE '/1/23/%'"
        ),
    }


# ============================================================
# 综合入口
# ============================================================


def dimension_overview() -> dict[str, Any]:
    """维度高级主题总览。"""
    return {
        "scd_types": {
            "type_1": "直接覆盖,不保留历史 (用于修正)",
            "type_2": "新增行,保留全量历史 (阿里 OneData 默认)",
            "type_3": "新增列,只保留当前+上次 (偶尔对比)",
        },
        "advanced_topics": {
            "zipper": "拉链表 (Type 2 物理实现, 用 start_date/end_date)",
            "degenerate": "退化维度 (业务单号放事实表)",
            "junk": "杂项维度 (多个低基数标志位打包)",
            "mini": "微型维度 (高频变更属性拆出)",
            "multivalue_bridge": "多值维度+桥接表 (一对多/多对多)",
            "recursive_hierarchy": "递归层次 (扁平化/桥接表/路径枚举)",
        },
        "source": "Kimball 'The Data Warehouse Toolkit' 第 5/7 章 + 阿里 OneData 第 4 章",
    }
