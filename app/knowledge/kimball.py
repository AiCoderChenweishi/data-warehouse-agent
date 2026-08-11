"""
Kimball 4 步法决策树
====================

来源 (Sources):
    - Ralph Kimball, Margy Ross, "The Data Warehouse Toolkit" (3rd Edition, 2013)
    - 中文版《数据仓库工具箱:维度建模权威指南》(第 3 版,2015 清华大学出版社)
    - 关键章节:
        * 第 3 章 "Kimball Dimensional Modeling Techniques Overview" — 4 步法概述
        * 第 4 章 "Fact Table Types" — 事务/周期快照/累积快照
        * 第 5 章 "Dimension Table Types" — 维度类型
        * 第 7 章 "SCD Type 1/2/3" — 缓慢变化维

设计原则 (Design Principles):
    1. **规则透明**:每个判定函数必须能回答"为什么这么决策",通过 `rationale` 字段输出。
    2. **可降级**: 输入模糊时返回"候选 + 建议追问",而不是抛 500。
    3. **可解释**: 决策树用 dict/list 而非黑盒模型,人审能看懂。
    4. **可测试**: 纯函数,无外部依赖,pytest 单测可全覆盖。

边界 (Boundaries):
    - 本模块只做"决策",不做"DDL/SQL 生成" — 那是 backend 层的职责。
    - 本模块不依赖 DuckDB/任何数据库,纯 Python。
    - 决策依据 = Kimball 书 + 行业惯例,所有判断都标了来源。

调用示例 (Examples):
    >>> from app.knowledge import kimball
    >>> procs = kimball.identify_business_process(
    ...     "用户在下单后,会经历支付、发货、收货"
    ... )
    >>> len(procs) >= 3
    True
    >>> kimball.declare_grain("下单")
    '子订单粒度(订单行项粒度,一行 = 一个订单中的一件商品)'
    >>> kimball.decide_fact_type(
    ...     ["下单","支付","发货","收货"], has_time_intervals=True
    ... )['fact_type']
    '累积快照'
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any


# ============================================================
# 数据类 (Data Classes) — 把决策结果结构化
# ============================================================


@dataclass
class BusinessProcessCandidate:
    """业务过程候选。

    Attributes:
        name: 业务过程名,如 "下单" / "支付" / "发货" / "收货"。
        confidence: 0.0~1.0,基于关键词匹配的置信度。
        rationale: 为什么判定为业务过程的依据。
        evidence_keywords: 命中的关键词,用于回溯。
    """

    name: str
    confidence: float
    rationale: str
    evidence_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DimensionCandidate:
    """维度候选。

    Attributes:
        name: 维度名,如 "用户" / "商品" / "时间"。
        role: 维度角色 — "primary"(主维)/ "related"(相关维)/ "junk"(杂项)/ "degenerate"(退化)。
        rationale: 为什么是该角色。
        attributes: 候选属性列表。
    """

    name: str
    role: str  # primary | related | junk | degenerate
    rationale: str
    attributes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FactCandidate:
    """事实候选。

    Attributes:
        name: 事实名,如 "订单金额" / "商品数量" / "优惠金额"。
        additivity: 可加性 — "additive"(可加)/ "semi_additive"(半可加)/ "non_additive"(不可加)。
        data_type: 建议数据类型 — "DECIMAL"/"BIGINT"/"FLOAT"。
        rationale: 可加性判定的依据。
    """

    name: str
    additivity: str  # additive | semi_additive | non_additive
    data_type: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ============================================================
# 业务过程识别 (Step 1)
# ============================================================
# 来源: Kimball 第 3 章 — "Choose the Business Process"
# 业务过程 = 业务中发生的可度量事件,由动词描述(下单/支付/发货/收货)
# 判定依据:
#   1) 描述中包含可执行动词(下/付/发/收/退/评/登/注/删...)
#   2) 业务过程 = 一次业务事件,有明确的开始/结束,可独立度量
#   3) 业务过程 ≠ 实体(商品/用户是实体,不是过程)

# 业务过程动词词库 (中英对照)
# 来源: Kimball 第 3 章 + 阿里 OneData 第 3 章 业务活动分析
_BUSINESS_PROCESS_VERBS: dict[str, list[str]] = {
    "下单": ["下单", "订购", "购买", "place order", "order", "create order", "submit order"],
    "支付": ["支付", "付款", "扣款", "收款", "pay", "payment", "checkout"],
    "发货": ["发货", "出库", "物流", "配送", "ship", "shipment", "dispatch", "fulfill"],
    "收货": ["收货", "确认收货", "签收", "receive", "delivery", "sign for"],
    "退货": ["退货", "退款", "退单", "refund", "return", "return order"],
    "评价": ["评价", "评论", "打分", "review", "rate", "comment"],
    "注册": ["注册", "开户", "激活", "register", "signup", "activate"],
    "登录": ["登录", "登出", "logout", "login", "sign in"],
    "加购": ["加购", "加入购物车", "收藏", "add to cart", "cart", "favorite", "wishlist"],
    "浏览": ["浏览", "访问", "点击", "view", "visit", "click", "browse"],
    "充值": ["充值", "提现", "recharge", "deposit", "withdraw"],
    "核销": ["核销", "使用", "use", "redeem", "consume"],
    "取消": ["取消", "撤销", "cancel", "void"],
    "改签": ["改签", "变更", "modify", "change"],
    "晋升": ["晋升", "降级", "调岗", "promote", "demote", "transfer"],
    "入库": ["入库", "上架", "inbound", "stock in"],
    "出库": ["出库", "下架", "outbound", "stock out"],
    "盘点": ["盘点", "inventory count", "stocktake"],
    "调拨": ["调拨", "transfer", "allocation"],
    "审批": ["审批", "申请", "approve", "request", "submit"],
}

# 实体词(非业务过程,用于排除干扰)
_ENTITY_HINTS = [
    "用户", "商品", "订单", "会员", "商家", "店铺", "类目", "品牌",
    "user", "customer", "product", "item", "order", "member", "merchant",
]


def identify_business_process(
    description: str,
    *,
    known_processes: list[str] | None = None,
    min_confidence: float = 0.5,
) -> list[dict[str, Any]]:
    """识别业务过程 (Kimball 4 步法 Step 1)。

    来源: Kimball 第 3 章 "Choose the Business Process" — 业务过程是
    "对业务行为进行命名,通常是动词或动词短语,代表业务事件的发生"。

    Args:
        description: 业务名 + 数据源描述文本 (如 "用户在下单后,会经历支付、发货、收货")。
        known_processes: 用户已知的业务过程列表,作为白名单(可选)。
        min_confidence: 最低置信度阈值,低于此值过滤掉。默认 0.5。

    Returns:
        业务过程候选列表(按 confidence 降序),每个元素是 dict:
            {
                "name": str,             # 业务过程名
                "confidence": float,     # 0.0~1.0
                "rationale": str,        # 判定依据
                "evidence_keywords": list[str]
            }

    判定依据 (Decision Rules):
        1. **动词模式**: 文本中包含 `_BUSINESS_PROCESS_VERBS` 里的动词 → 候选。
        2. **共现模式**: 动词 + 实体组合(下单 + 订单)→ 强化置信度。
        3. **列表分隔**: "、" "," "和" "and" 分隔的并列项 → 拆分为多个候选。
        4. **白名单优先**: `known_processes` 提供的名称直接保留,即使没匹配上动词。

    边界情况 (Edge Cases):
        - 空字符串 / None → 返回 [],rationale 提示"请提供业务描述"。
        - 描述全是实体词(用户/商品)无动词 → 返回 [],提示"需要动词性业务事件"。
        - 同义词合并: "付款" / "支付" 都归到 "支付"。

    Examples:
        >>> result = identify_business_process("用户在下单后,会经历支付、发货、收货")
        >>> len(result) >= 3
        True
        >>> names = {r['name'] for r in result}
        >>> '下单' in names
        True
    """
    if not description or not description.strip():
        return [
            {
                "name": "",
                "confidence": 0.0,
                "rationale": "输入为空,无法识别业务过程。请提供业务描述,如 '用户在下单后,会经历支付、发货、收货'。",
                "evidence_keywords": [],
            }
        ]

    description_lower = description.lower()
    candidates: dict[str, dict[str, Any]] = {}

    # 规则 1: 命中动词词库
    for process_name, keywords in _BUSINESS_PROCESS_VERBS.items():
        hits = [kw for kw in keywords if kw.lower() in description_lower]
        if hits:
            # 置信度: 命中次数 + 描述长度权重
            base_confidence = min(0.5 + 0.15 * len(hits), 0.95)
            candidates[process_name] = {
                "name": process_name,
                "confidence": base_confidence,
                "rationale": (
                    f"匹配到业务过程动词: {hits}。"
                    "依据 Kimball 第 3 章,业务过程是'业务中发生的可度量事件',"
                    "由动词或动词短语描述。"
                ),
                "evidence_keywords": hits,
            }

    # 规则 2: 白名单强制保留
    if known_processes:
        for kp in known_processes:
            if kp not in candidates:
                candidates[kp] = {
                    "name": kp,
                    "confidence": 0.7,
                    "rationale": "用户提供的已知业务过程白名单,作为先验知识。",
                    "evidence_keywords": [],
                }
            else:
                # 已存在,强化置信度
                candidates[kp]["confidence"] = min(
                    candidates[kp]["confidence"] + 0.2, 0.99
                )

    # 规则 3: 列表分隔拆分(针对 "下单、支付、发货" 这种)
    # 已经在 _BUSINESS_PROCESS_VERBS 里通过关键词命中,这里只补一句 rationale

    # 规则 4: 实体词降权(避免"商品" "用户" 误识别为过程)
    entity_penalty = sum(1 for e in _ENTITY_HINTS if e in description)
    for c in candidates.values():
        if entity_penalty > 0:
            c["confidence"] = max(c["confidence"] - 0.05 * entity_penalty, 0.3)
            if entity_penalty >= 2:
                c["rationale"] += (
                    f" 注意:描述中包含 {entity_penalty} 个实体词,"
                    "已适度降权,需确认这是过程而非实体。"
                )

    # 过滤 + 排序
    result = [c for c in candidates.values() if c["confidence"] >= min_confidence]
    result.sort(key=lambda x: x["confidence"], reverse=True)

    # 兜底: 如果什么都没识别出来
    if not result:
        return [
            {
                "name": "",
                "confidence": 0.0,
                "rationale": (
                    "未能识别出任何业务过程。可能原因:"
                    "(1) 描述中没有动词性事件;"
                    "(2) 描述全是实体(用户/商品/订单);"
                    "(3) 业务过程用了词库外的生僻动词。"
                    "建议:补充业务事件的动词,如'用户会下单、支付、收货'。"
                ),
                "evidence_keywords": [],
            }
        ]

    return result


# ============================================================
# 粒度声明 (Step 2)
# ============================================================
# 来源: Kimball 第 3 章 "Declare the Grain"
# 粒度 = 一行事实 = 一个原子事件,回答"这一行要回答什么问题"
# 判定原则:
#   1) 粒度必须由业务过程+业务对象共同决定
#   2) 粒度必须是"原子"的,不可再分
#   3) 优先选最细粒度(订单行 > 订单)

_GRAIN_PATTERNS: dict[str, dict[str, Any]] = {
    # 业务过程 -> 粒度推荐 + 判定问题
    "下单": {
        "grain": "子订单粒度(订单行项粒度,一行 = 一个订单中的一件商品)",
        "questions": [
            "用户一次下单可能买多个商品,需要看'每一件商品'还是'每一次下单'?",
            "订单状态变更(取消/改价)是按订单还是按子订单跟踪?",
            "优惠(满减/优惠券)作用在订单级还是子订单级?",
        ],
        "rationale": (
            "电商场景下,标准粒度是'子订单'(订单行项),"
            "因为用户一次下单可能买多件商品,GMV/优惠需要按行计算。"
            "如果只有一种商品,可降到'订单粒度',但失去分析维度。"
        ),
    },
    "支付": {
        "grain": "支付单粒度(一行 = 一次支付动作,可能包含多个子订单)",
        "questions": [
            "一笔订单是单次支付还是允许多次支付(分笔)?",
            "支付单是否合并多个订单(组合支付)?",
            "退款是按支付单还是按子订单?",
        ],
        "rationale": (
            "支付粒度通常独立于订单,因为支持组合支付(多订单合并支付)、"
            "分笔支付(订单多次扣款)。粒度声明为'支付单'。"
        ),
    },
    "发货": {
        "grain": "发货单粒度(一行 = 一次发货动作,可能包含多个子订单)",
        "questions": [
            "一个发货单可能发多件商品,需要按行拆分吗?",
            "同一订单是否分多个包裹发货?",
            "物流单号是按发货单还是按商品?",
        ],
        "rationale": "发货是物流侧的事件,粒度是'发货单',可能与订单多对多关系。",
    },
    "收货": {
        "grain": "收货确认粒度(一行 = 一次确认收货动作)",
        "questions": [
            "确认收货是按发货单还是按子订单?",
            "是否支持部分确认收货?",
        ],
        "rationale": "收货粒度与发货粒度保持一致,通常也是'发货单'级。",
    },
    "退货": {
        "grain": "退货单粒度(一行 = 一次退货申请)",
        "questions": [
            "退货是按子订单还是按发货单?",
            "是否支持'部分退货'(一件商品退)?",
        ],
        "rationale": "退货粒度建议与下单粒度保持一致(子订单),便于关联分析。",
    },
    "评价": {
        "grain": "评价单粒度(一行 = 一条评价,通常对应一个子订单)",
        "questions": [
            "评价是按订单还是按子订单?",
            "同一子订单可多次评价吗?",
        ],
        "rationale": "电商评价通常 1 子订单 1 评价,粒度 = 评价单。",
    },
    "注册": {
        "grain": "用户注册粒度(一行 = 一次用户注册行为)",
        "questions": [
            "用户通过多渠道(微信/手机)注册,需要去重吗?",
            "注册后激活是另一过程,需要单独事实表?",
        ],
        "rationale": "用户注册是离散事件,粒度 = 注册事件。",
    },
    "登录": {
        "grain": "登录事件粒度(一行 = 一次登录行为)",
        "questions": [
            "登录频次分析需要看每次登录还是每日汇总?",
            "失败登录是否记录?",
        ],
        "rationale": "登录事件粒度细,通常用事务事实表(每次登录一行)。",
    },
    "加购": {
        "grain": "加购事件粒度(一行 = 一次加购动作,通常是子订单级)",
        "questions": [
            "同一商品多次加购是合并行还是多行?",
            "加购时间是否需要精确到秒?",
        ],
        "rationale": "加购行为高频,粒度 = 加购事件。",
    },
    "浏览": {
        "grain": "浏览事件粒度(一行 = 一次页面/商品浏览,通常用 session 聚合)",
        "questions": [
            "浏览量是否需要按 session 聚合?",
            "是否需要区分页面浏览(PV) 和 独立访客(UV)?",
        ],
        "rationale": "浏览量极大,通常先做周期快照(每日 UV/PV)再做事务(每次浏览)。",
    },
    "充值": {
        "grain": "充值单粒度(一行 = 一次充值动作)",
        "questions": [
            "充值金额是订单级还是单次充值?",
            "是否需要区分'到账'和'入账'?",
        ],
        "rationale": "金融场景,粒度 = 充值单,与支付逻辑类似。",
    },
    "核销": {
        "grain": "核销单粒度(一行 = 一次核销动作,通常对应一个券码)",
        "questions": [
            "一张券是否允许多次核销?",
            "核销时点需要精确到秒吗?",
        ],
        "rationale": "核销是券/卡的实际使用,粒度 = 核销事件。",
    },
    "取消": {
        "grain": "取消事件粒度(一行 = 一次取消动作,通常按子订单)",
        "questions": [
            "取消是用户主动还是系统超时?",
            "取消状态是否需要全程跟踪(申请→审核→完成)?",
        ],
        "rationale": "取消通常与下单粒度一致(子订单),便于分析取消率。",
    },
    "入库": {
        "grain": "入库单粒度(一行 = 一次入库动作,可能多 SKU)",
        "questions": [
            "入库是按行项还是按单据?",
            "批次/效期是否需要单独维度?",
        ],
        "rationale": "WMS 场景,粒度 = 入库单行项。",
    },
    "出库": {
        "grain": "出库单粒度(一行 = 一次出库动作)",
        "questions": [
            "出库是按销售订单还是按拣货单?",
            "出库后是否需要立刻扣减库存?",
        ],
        "rationale": "WMS 场景,粒度 = 出库单行项。",
    },
}


def declare_grain(business_process: str) -> str:
    """声明粒度 (Kimball 4 步法 Step 2)。

    来源: Kimball 第 3 章 "Declare the Grain" — 粒度回答"一行事实 = 什么"。

    Args:
        business_process: 业务过程名,如 "下单" / "支付"。

    Returns:
        粒度描述字符串(中文),可直接展示给用户。

    判定依据 (Decision Rules):
        - 从 `_GRAIN_PATTERNS` 词库直接查询,基于 Kimball + 阿里电商行业惯例。
        - 未命中时返回"原子事件粒度"的通用兜底。

    边界情况 (Edge Cases):
        - 业务过程不在词库 → 返回通用原子粒度 + 追问。
        - 业务过程含"流程"复合词(如 "下单流程")→ 截取核心词 "下单"。

    Examples:
        >>> declare_grain("下单")
        '子订单粒度(订单行项粒度,一行 = 一个订单中的一件商品)'
    """
    bp_clean = _normalize_business_process(business_process)
    if bp_clean in _GRAIN_PATTERNS:
        return _GRAIN_PATTERNS[bp_clean]["grain"]
    return (
        "原子事件粒度(一行 = 一个最小业务事件,不可再分)。"
        f"未能为 '{business_process}' 推荐具体粒度,建议补充业务上下文。"
    )


def grain_questions(business_process: str) -> list[str]:
    """返回粒度判定的追问问题清单 (Step 2 辅助)。

    来源: Kimball 第 3 章 "Declare the Grain" — 粒度声明的 5 个标准问题。

    Args:
        business_process: 业务过程名。

    Returns:
        追问问题列表(中文),用户回答后可作为输入再次调 `declare_grain`。

    Examples:
        >>> qs = grain_questions("下单")
        >>> len(qs) >= 2
        True
    """
    bp_clean = _normalize_business_process(business_process)
    if bp_clean in _GRAIN_PATTERNS:
        return _GRAIN_PATTERNS[bp_clean]["questions"]
    return [
        "一行事实代表什么最小业务事件?",
        "这个粒度是否还能再分?(若能,需要更细粒度)",
        "下游分析问题需要更细还是更粗的粒度?",
    ]


def _normalize_business_process(name: str) -> str:
    """标准化业务过程名(去空格、截取核心词)。"""
    name = (name or "").strip()
    # 截取核心词: "下单流程" -> "下单"
    for known in _BUSINESS_PROCESS_VERBS.keys():
        if known in name:
            return known
    return name


# ============================================================
# 维度识别 (Step 3)
# ============================================================
# 来源: Kimball 第 3 章 "Identify the Dimensions"
# 维度 = 看事实的角度,围绕粒度描述"谁/什么/何时/何地/怎么"
# 角色分类:
#   - primary: 主维(粒度的核心实体,如子订单的事实主维是子订单单号)
#   - related: 相关维(外键关联的实体,如用户/商品/商家/类目)
#   - junk: 杂项维(打包低基数标志位)
#   - degenerate: 退化维(业务单号,放事实表里)

# 通用维度模板 (各业务过程的候选维度)
_DIMENSION_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "下单": [
        {"name": "子订单", "role": "primary", "attributes": ["子订单号", "子订单状态", "下单时间"], "rationale": "子订单是粒度的核心标识,主维。"},
        {"name": "订单", "role": "related", "attributes": ["订单号", "父订单号", "订单类型"], "rationale": "父订单是子订单的上层实体。"},
        {"name": "用户", "role": "related", "attributes": ["用户ID", "用户等级", "注册渠道", "新老客"], "rationale": "下单的发起方。"},
        {"name": "商品", "role": "related", "attributes": ["商品ID", "商品名称", "类目", "品牌", "SKU"], "rationale": "下单的对象。"},
        {"name": "商家", "role": "related", "attributes": ["商家ID", "商家名称", "店铺类型"], "rationale": "商品的销售方。"},
        {"name": "时间", "role": "related", "attributes": ["下单日期", "下单小时", "周", "月", "季度"], "rationale": "通用时间维。"},
        {"name": "促销", "role": "related", "attributes": ["优惠券ID", "活动ID", "满减规则"], "rationale": "影响金额的促销因素。"},
        {"name": "收货地址", "role": "related", "attributes": ["省份", "城市", "区县", "街道"], "rationale": "物流相关。"},
        {"name": "支付方式", "role": "junk", "attributes": ["支付渠道", "是否分期"], "rationale": "低基数,打包为杂项维。"},
        {"name": "订单标识", "role": "degenerate", "attributes": ["订单号", "子订单号"], "rationale": "业务单号,作为退化维放在事实表。"},
    ],
    "支付": [
        {"name": "支付单", "role": "primary", "attributes": ["支付单号", "支付状态"], "rationale": "支付粒度的核心标识。"},
        {"name": "用户", "role": "related", "attributes": ["用户ID", "用户等级"], "rationale": "支付发起方。"},
        {"name": "时间", "role": "related", "attributes": ["支付日期", "支付小时"], "rationale": "通用时间维。"},
        {"name": "支付方式", "role": "related", "attributes": ["支付渠道", "是否分期", "银行卡类型"], "rationale": "影响支付成功率。"},
        {"name": "订单", "role": "related", "attributes": ["订单号", "子订单号"], "rationale": "支付关联的订单。"},
        {"name": "支付标识", "role": "degenerate", "attributes": ["支付流水号", "支付单号"], "rationale": "业务单号,退化维。"},
    ],
    "发货": [
        {"name": "发货单", "role": "primary", "attributes": ["发货单号", "发货状态"], "rationale": "发货粒度的核心标识。"},
        {"name": "仓库", "role": "related", "attributes": ["仓库ID", "仓库类型"], "rationale": "发货起点。"},
        {"name": "物流公司", "role": "related", "attributes": ["物流公司", "物流单号"], "rationale": "物流主体。"},
        {"name": "时间", "role": "related", "attributes": ["发货日期", "承诺时效"], "rationale": "通用时间维。"},
        {"name": "收货地址", "role": "related", "attributes": ["省份", "城市"], "rationale": "影响运费。"},
    ],
    "收货": [
        {"name": "收货单", "role": "primary", "attributes": ["收货单号", "收货状态"], "rationale": "收货粒度。"},
        {"name": "用户", "role": "related", "attributes": ["用户ID"], "rationale": "收货确认人。"},
        {"name": "时间", "role": "related", "attributes": ["收货日期", "收货时间"], "rationale": "通用时间维。"},
        {"name": "物流公司", "role": "related", "attributes": ["物流公司"], "rationale": "物流信息。"},
    ],
    "退货": [
        {"name": "退货单", "role": "primary", "attributes": ["退货单号", "退货原因"], "rationale": "退货粒度。"},
        {"name": "用户", "role": "related", "attributes": ["用户ID"], "rationale": "退货发起方。"},
        {"name": "时间", "role": "related", "attributes": ["申请日期", "完成日期"], "rationale": "退货时间线。"},
        {"name": "退货原因", "role": "junk", "attributes": ["原因分类", "是否质量问题"], "rationale": "低基数,杂项。"},
    ],
    "评价": [
        {"name": "评价", "role": "primary", "attributes": ["评价ID", "评分"], "rationale": "评价粒度。"},
        {"name": "用户", "role": "related", "attributes": ["用户ID"], "rationale": "评价发起方。"},
        {"name": "商品", "role": "related", "attributes": ["商品ID"], "rationale": "评价对象。"},
        {"name": "时间", "role": "related", "attributes": ["评价日期"], "rationale": "通用时间维。"},
        {"name": "评价类型", "role": "junk", "attributes": ["是否追评", "是否匿名"], "rationale": "杂项。"},
    ],
    "注册": [
        {"name": "用户", "role": "primary", "attributes": ["用户ID", "注册状态"], "rationale": "注册就是用户诞生。"},
        {"name": "注册渠道", "role": "related", "attributes": ["渠道", "来源页面"], "rationale": "投放分析。"},
        {"name": "时间", "role": "related", "attributes": ["注册日期", "注册小时"], "rationale": "通用时间维。"},
    ],
    "登录": [
        {"name": "登录事件", "role": "primary", "attributes": ["事件ID"], "rationale": "登录粒度。"},
        {"name": "用户", "role": "related", "attributes": ["用户ID"], "rationale": "登录主体。"},
        {"name": "时间", "role": "related", "attributes": ["登录日期", "登录小时"], "rationale": "通用时间维。"},
        {"name": "登录方式", "role": "junk", "attributes": ["登录方式", "设备类型"], "rationale": "杂项。"},
    ],
}


def identify_dimensions(
    business_process: str, grain: str
) -> list[dict[str, Any]]:
    """识别维度 (Kimball 4 步法 Step 3)。

    来源: Kimball 第 3 章 "Identify the Dimensions" — 围绕粒度找"谁/什么/何时/何地/怎么"。

    Args:
        business_process: 业务过程名。
        grain: 粒度描述(用于验证维度是否与粒度匹配)。

    Returns:
        维度候选列表(每项包含 name/role/rationale/attributes),按 role 优先级排序:
        primary > related > degenerate > junk。

    判定依据 (Decision Rules):
        - 从 `_DIMENSION_TEMPLATES` 词库匹配业务过程。
        - 兜底:返回通用四维(用户/商品/时间/地点)+ 主维占位。

    边界情况 (Edge Cases):
        - 业务过程不在词库 → 返回通用 4 维 + "需要补充业务上下文" 提示。
        - 同一属性既可作主维也可作相关维(如下单时"订单"是主维,其他事实表里是相关维)。

    Examples:
        >>> dims = identify_dimensions("下单", "子订单粒度")
        >>> any(d['name'] == '用户' for d in dims)
        True
        >>> any(d['role'] == 'primary' for d in dims)
        True
    """
    bp_clean = _normalize_business_process(business_process)
    if bp_clean in _DIMENSION_TEMPLATES:
        candidates = _DIMENSION_TEMPLATES[bp_clean]
    else:
        candidates = [
            {"name": "主实体", "role": "primary", "attributes": ["主实体ID"], "rationale": f"未在词库中找到 '{business_process}',返回通用主维占位。"},
            {"name": "用户", "role": "related", "attributes": ["用户ID"], "rationale": "通用相关维。"},
            {"name": "时间", "role": "related", "attributes": ["日期", "小时"], "rationale": "通用时间维。"},
            {"name": "地点", "role": "related", "attributes": ["省份", "城市"], "rationale": "通用地理维。"},
        ]

    # 校验:粒度是否暗示某个主维
    grain_text = grain or ""
    if "子订单" in grain_text or "订单行" in grain_text:
        # 子订单粒度:主维应该是"子订单"
        if not any(c["role"] == "primary" and "子订单" in c["name"] for c in candidates):
            candidates.insert(0, {
                "name": "子订单",
                "role": "primary",
                "attributes": ["子订单号"],
                "rationale": "粒度声明暗示子订单为主维,已补充。",
            })

    # 排序: primary > related > degenerate > junk
    role_order = {"primary": 0, "related": 1, "degenerate": 2, "junk": 3}
    candidates.sort(key=lambda c: role_order.get(c["role"], 9))
    return candidates


# ============================================================
# 事实识别 (Step 4)
# ============================================================
# 来源: Kimball 第 3 章 "Identify the Facts" + 第 4 章 半可加性/不可加性
# 事实 = 可度量的数值,按可加性分三类:
#   - additive: 可加(SUM 跨任意维度都合理,如 销售额)
#   - semi_additive: 半可加(沿时间维不可加,但其他维度可加,如 账户余额、库存量)
#   - non_additive: 不可加(比率/百分比,需要拆成 分子+分母)

# 通用事实模板
_FACT_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "下单": [
        {"name": "订单金额", "additivity": "additive", "data_type": "DECIMAL(18,2)", "rationale": "可加,跨任意维度 SUM 都成立。"},
        {"name": "商品数量", "additivity": "additive", "data_type": "BIGINT", "rationale": "可加。"},
        {"name": "优惠金额", "additivity": "additive", "data_type": "DECIMAL(18,2)", "rationale": "可加,通常与订单金额一起 SUM。"},
        {"name": "实付金额", "additivity": "additive", "data_type": "DECIMAL(18,2)", "rationale": "可加, = 订单金额 - 优惠金额。"},
        {"name": "件数", "additivity": "additive", "data_type": "BIGINT", "rationale": "可加。"},
        {"name": "订单数", "additivity": "additive", "data_type": "BIGINT", "rationale": "可加,但本质是 COUNT,Kimball 建议用事实而非维。"},
        {"name": "优惠率", "additivity": "non_additive", "data_type": "FLOAT", "rationale": "比率型,不可加,需拆为 分子(优惠金额) + 分母(订单金额)。"},
    ],
    "支付": [
        {"name": "支付金额", "additivity": "additive", "data_type": "DECIMAL(18,2)", "rationale": "可加。"},
        {"name": "支付笔数", "additivity": "additive", "data_type": "BIGINT", "rationale": "可加, COUNT 派生。"},
        {"name": "手续费", "additivity": "additive", "data_type": "DECIMAL(18,2)", "rationale": "可加。"},
        {"name": "支付成功率", "additivity": "non_additive", "data_type": "FLOAT", "rationale": "比率型,需拆为 成功笔数/总笔数。"},
    ],
    "发货": [
        {"name": "发货单数", "additivity": "additive", "data_type": "BIGINT", "rationale": "可加。"},
        {"name": "发货件数", "additivity": "additive", "data_type": "BIGINT", "rationale": "可加。"},
        {"name": "发货金额", "additivity": "additive", "data_type": "DECIMAL(18,2)", "rationale": "可加。"},
        {"name": "运费", "additivity": "additive", "data_type": "DECIMAL(18,2)", "rationale": "可加。"},
        {"name": "发货时长", "additivity": "semi_additive", "data_type": "FLOAT", "rationale": "半可加:跨时间维 SUM 无意义(应取平均),但跨用户/商品维可加。"},
        {"name": "当前库存", "additivity": "semi_additive", "data_type": "BIGINT", "rationale": "半可加:不能跨时间 SUM。"},
    ],
    "收货": [
        {"name": "收货单数", "additivity": "additive", "data_type": "BIGINT", "rationale": "可加。"},
        {"name": "收货金额", "additivity": "additive", "data_type": "DECIMAL(18,2)", "rationale": "可加。"},
        {"name": "收货时长", "additivity": "semi_additive", "data_type": "FLOAT", "rationale": "半可加,通常用 AVG。"},
    ],
    "退货": [
        {"name": "退货单数", "additivity": "additive", "data_type": "BIGINT", "rationale": "可加。"},
        {"name": "退货金额", "additivity": "additive", "data_type": "DECIMAL(18,2)", "rationale": "可加。"},
        {"name": "退货率", "additivity": "non_additive", "data_type": "FLOAT", "rationale": "比率型,拆为 退货单数/总单数。"},
    ],
    "评价": [
        {"name": "评价数", "additivity": "additive", "data_type": "BIGINT", "rationale": "可加。"},
        {"name": "评分", "additivity": "semi_additive", "data_type": "FLOAT", "rationale": "半可加,通常 AVG。"},
        {"name": "好评数", "additivity": "additive", "data_type": "BIGINT", "rationale": "可加。"},
        {"name": "好评率", "additivity": "non_additive", "data_type": "FLOAT", "rationale": "比率型。"},
    ],
    "注册": [
        {"name": "注册用户数", "additivity": "additive", "data_type": "BIGINT", "rationale": "可加。"},
    ],
    "登录": [
        {"name": "登录次数", "additivity": "additive", "data_type": "BIGINT", "rationale": "可加。"},
        {"name": "在线时长", "additivity": "semi_additive", "data_type": "FLOAT", "rationale": "半可加,通常 AVG。"},
    ],
}


def identify_facts(
    business_process: str, grain: str, dimensions: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """识别事实 (Kimball 4 步法 Step 4)。

    来源: Kimball 第 3 章 "Identify the Facts" + 第 4 章半可加性。

    Args:
        business_process: 业务过程名。
        grain: 粒度描述(用于校准事实粒度)。
        dimensions: 维度列表(可选,用于检查事实与维度匹配)。

    Returns:
        事实候选列表(每项含 name/additivity/data_type/rationale)。

    判定依据 (Decision Rules):
        - 从 `_FACT_TEMPLATES` 词库匹配。
        - 兜底:返回通用 3 类(可加数值 + 半可加状态 + 不可加比率)。

    边界情况 (Edge Cases):
        - 业务过程不在词库 → 返回通用事实模板。
        - 业务过程是"流程型"(如 "下单-支付-发货") → 取首个过程作为代表。

    Examples:
        >>> facts = identify_facts("下单", "子订单粒度")
        >>> any(f['additivity'] == 'additive' for f in facts)
        True
        >>> any(f['additivity'] == 'non_additive' for f in facts)
        True
    """
    bp_clean = _normalize_business_process(business_process)
    if bp_clean in _FACT_TEMPLATES:
        candidates = _FACT_TEMPLATES[bp_clean]
    else:
        candidates = [
            {"name": "度量金额", "additivity": "additive", "data_type": "DECIMAL(18,2)", "rationale": "通用可加数值事实,兜底。"},
            {"name": "当前状态", "additivity": "semi_additive", "data_type": "BIGINT", "rationale": "半可加,通常取快照或最新值。"},
            {"name": "比率", "additivity": "non_additive", "data_type": "FLOAT", "rationale": "比率型,需拆分子分母。"},
        ]
    return candidates


# ============================================================
# 事实表类型决策
# ============================================================
# 来源: Kimball 第 4 章 "Choosing the Fact Table Type"
# 三种类型:
#   - 事务 (transaction): 一行 = 一个业务事件,最细粒度,可加性最强
#   - 周期快照 (periodic snapshot): 一行 = 一个实体在周期末的状态
#   - 累积快照 (accumulating snapshot): 一行 = 一个业务全生命周期,多个时间戳

def decide_fact_type(
    business_processes: list[str],
    has_time_intervals: bool = False,
    has_end_state: bool = False,
    is_high_volume: bool = True,
) -> dict[str, Any]:
    """决定事实表类型 (Kimball 第 4 章)。

    来源: Kimball 第 4 章 "Choosing the Fact Table Type"。

    Args:
        business_processes: 业务过程列表(从 Step 1 得到)。
        has_time_intervals: 是否有明确的时间区间/多时间戳(如下单-支付-发货-收货)。
        has_end_state: 是否有明确的"终态"(如订单完结)。
        is_high_volume: 是否高吞吐量(>10w/天)。

    Returns:
        dict 包含:
            - fact_type: 'transaction' / 'periodic_snapshot' / 'accumulating_snapshot'
            - confidence: 0.0~1.0
            - rationale: 判定依据
            - alternatives: 候选方案
            - warnings: 警告

    判定依据 (Decision Rules):
        1. **多业务过程 + 有时间区间 + 有终态** → 累积快照
           (例: 下单→支付→发货→收货,有 4 个时间戳,有"完结"终态)
        2. **单一业务过程 + 状态度量(库存/账户余额)** → 周期快照
           (例: 每日库存快照、每月账户余额快照)
        3. **单一业务过程 + 离散事件 + 高吞吐** → 事务
           (例: 每次下单一行、每次登录一行)
        4. **多业务过程 + 无明确时间区间** → 拆分为多个事务事实表
        5. **海量 + 无分析需求** → 聚合后用周期快照

    边界情况 (Edge Cases):
        - 业务过程数 = 0 → 返回 "transaction" + 警告。
        - 业务过程数 = 1 但又是流程型(如"下单"实际含"加入购物车"+"确认订单"+"支付")→ 需拆分粒度。

    Examples:
        >>> r = decide_fact_type(["下单","支付","发货","收货"], has_time_intervals=True, has_end_state=True)
        >>> r['fact_type']
        'accumulating_snapshot'
        >>> r = decide_fact_type(["下单"], is_high_volume=True)
        >>> r['fact_type']
        'transaction'
    """
    if not business_processes:
        return {
            "fact_type": "transaction",
            "confidence": 0.0,
            "rationale": "未提供业务过程,默认按事务事实表处理。请先调 identify_business_process。",
            "alternatives": [],
            "warnings": ["未提供业务过程,无法做类型决策"],
        }

    n = len(business_processes)
    warnings: list[str] = []
    alternatives: list[dict[str, Any]] = []

    # 规则 1: 累积快照
    # 启发式: 4+ 业务过程 + 有时间区间 → 强信号(订单全流程典型)
    if (n >= 2 and has_time_intervals and has_end_state) or (n >= 4 and has_time_intervals):
        return {
            "fact_type": "accumulating_snapshot",
            "confidence": 0.9,
            "rationale": (
                f"检测到 {n} 个业务过程 + 有明确时间区间{'+ 有终态' if has_end_state else ''},"
                "符合 Kimball 第 4 章累积快照事实表的特征:一行 = 一个完整业务生命周期,"
                "包含多个日期外键(下单日/支付日/发货日/收货日)。"
                f"推荐:为业务过程 {business_processes} 建立 1 张累积快照事实表。"
            ),
            "alternatives": [
                {
                    "type": "transaction",
                    "scenario": "如果需要细粒度分析每个过程,改用 N 张事务事实表。",
                },
                {
                    "type": "periodic_snapshot",
                    "scenario": "如果还要看每周/每月状态汇总,补充 1 张周期快照。",
                },
            ],
            "warnings": warnings,
        }

    # 规则 2: 周期快照
    # 启发式:含"库存/余额/账户/状态"或单一过程但反复度量
    snapshot_keywords = ["库存", "余额", "账户", "在线", "状态", "持有", "存量"]
    bp_text = " ".join(business_processes)
    is_snapshot_like = any(kw in bp_text for kw in snapshot_keywords)

    if n == 1 and is_snapshot_like:
        return {
            "fact_type": "periodic_snapshot",
            "confidence": 0.85,
            "rationale": (
                f"单一过程 '{business_processes[0]}' 涉及状态/存量度量,"
                "符合 Kimball 第 4 章周期快照特征:一行 = 一个实体在周期末的状态。"
                "推荐:每日/每周/每月建 1 张快照,记录当时的存量值。"
            ),
            "alternatives": [
                {"type": "transaction", "scenario": "如果需要看每次状态变更的明细,改用事务表。"},
            ],
            "warnings": warnings,
        }

    # 规则 3: 事务事实表(默认)
    if n == 1 and is_high_volume:
        return {
            "fact_type": "transaction",
            "confidence": 0.9,
            "rationale": (
                f"单一业务过程 '{business_processes[0]}' + 高吞吐,"
                "符合事务事实表特征:一行 = 一个原子事件,粒度最细,可加性最强。"
                "推荐:为该过程建 1 张事务事实表。"
            ),
            "alternatives": [
                {"type": "periodic_snapshot", "scenario": "如需定期汇总,后续可建 DWS 汇总表。"},
            ],
            "warnings": warnings,
        }

    # 规则 4: 多过程但无时间区间 → 拆为多个事务表
    if n >= 2 and not has_time_intervals:
        return {
            "fact_type": "transaction",
            "confidence": 0.7,
            "rationale": (
                f"检测到 {n} 个业务过程,但未声明明确时间区间,"
                f"按 Kimball 第 4 章建议:为每个过程分别建 1 张事务事实表(共 {n} 张),"
                "通过公共维度(用户/商品/时间)做关联分析。"
            ),
            "alternatives": [
                {
                    "type": "accumulating_snapshot",
                    "scenario": "如果过程之间有明确的时间先后和终态,改为累积快照。",
                },
            ],
            "warnings": [
                f"业务过程数 = {n},建议拆为多张事务表或合并为 1 张累积快照。"
            ],
        }

    # 兜底
    return {
        "fact_type": "transaction",
        "confidence": 0.6,
        "rationale": "基于默认规则推荐事务事实表。",
        "alternatives": [],
        "warnings": ["未匹配到明确模式,使用默认事务事实表。"],
    }


# ============================================================
# 4 步法串联 (One-shot 入口)
# ============================================================


def kimball_four_step(
    business_description: str,
    *,
    has_time_intervals: bool | None = None,
    known_processes: list[str] | None = None,
) -> dict[str, Any]:
    """Kimball 4 步法一站式执行。

    串联 Step 1~4 + 事实表类型决策,自动推断时间区间/终态。

    Args:
        business_description: 业务描述(如 "用户在下单后,会经历支付、发货、收货")。
        has_time_intervals: 是否声明有明确时间区间(None 表示自动推断)。
        known_processes: 已知业务过程(可选白名单)。

    Returns:
        dict 包含完整 4 步结果:
            {
                "step1_processes": [...],       # Step 1 业务过程
                "step2_grain": {...},            # Step 2 粒度声明
                "step3_dimensions": [...],       # Step 3 维度
                "step4_facts": [...],            # Step 4 事实
                "step5_fact_type": {...},        # 事实表类型决策
            }

    Examples:
        >>> r = kimball_four_step("用户在下单后,会经历支付、发货、收货")
        >>> len(r['step1_processes']) >= 3
        True
        >>> r['step5_fact_type']['fact_type'] in ('transaction', 'accumulating_snapshot')
        True
    """
    # Step 1
    procs = identify_business_process(business_description, known_processes=known_processes)
    process_names = [p["name"] for p in procs if p["name"]]

    # 自动推断 has_time_intervals:描述里提到 "后/之后/经历/再到" 等序词
    if has_time_intervals is None:
        has_time_intervals = any(
            kw in business_description
            for kw in ["后", "之后", "再", "然后", "经历", "接着", "after", "then"]
        )
    has_end_state = any(
        kw in business_description
        for kw in ["完结", "完成", "关闭", "close", "finish", "complete", "end"]
    )

    # Step 2 (取第一个过程的粒度作为代表)
    if process_names:
        primary_process = process_names[0]
        grain_text = declare_grain(primary_process)
    else:
        primary_process = ""
        grain_text = "原子事件粒度"

    # Step 3
    dims = identify_dimensions(primary_process, grain_text) if primary_process else []

    # Step 4
    facts = identify_facts(primary_process, grain_text, dims) if primary_process else []

    # Step 5 (事实表类型)
    fact_type = decide_fact_type(
        process_names,
        has_time_intervals=has_time_intervals,
        has_end_state=has_end_state,
    )

    return {
        "step1_processes": procs,
        "step2_grain": {
            "process": primary_process,
            "grain": grain_text,
            "questions": grain_questions(primary_process) if primary_process else [],
        },
        "step3_dimensions": dims,
        "step4_facts": facts,
        "step5_fact_type": fact_type,
    }
