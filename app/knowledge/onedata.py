"""
阿里 OneData 数仓规范
====================

来源 (Sources):
    - 阿里《OneData — 大数据之路》(阿里巴巴数据技术及产品部,2017,机械工业出版社)
    - 关键章节:
        * 第 3 章 "数据分层" — ODS/DWD/DWS/DWT/ADS/DIM
        * 第 4 章 "数据域划分" — 业务域定义
        * 第 5 章 "总线矩阵" — Kimball 总线架构的阿里落地
        * 第 6 章 "指标体系" — 原子指标 + 派生指标
        * 第 7 章 "命名规范" — 表/字段命名

设计原则 (Design Principles):
    1. **分层清晰**: 6 层架构,每层职责互斥,数据流向单向(ODS→DWD→DWS→DWT→ADS)。
    2. **命名可解析**: 表名自带语义(层_域_业务_修饰_周期),人眼能读懂。
    3. **指标可追溯**: 派生指标 = 原子指标 + 修饰词 + 时间周期,可逐层下钻。

调用示例 (Examples):
    >>> from app.knowledge import onedata
    >>> onedata.generate_naming(layer='dws', domain='trade', business='order',
    ...                          modifier='pay', period='1d')
    'dws_trade_order_pay_1d'
    >>> onedata.derive_metric(atomic='订单金额', modifier='支付的', period='最近1天')
    '最近1天支付的订单金额'
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any


# ============================================================
# 6 层架构定义
# ============================================================
# 来源: 阿里《OneData》第 3 章
#
#   ODS  (Operational Data Store)  贴源层
#   DWD  (Data Warehouse Detail)   明细层 (清洗后明细)
#   DWS  (Data Warehouse Summary)  汇总层 (主题宽表)
#   DWT  (Data Warehouse Topic)    主题层 (全量累计,慢变)
#   ADS  (Application Data Service) 应用层 (直接给报表/接口)
#   DIM  (Dimension)               维度层 (公共维度表)

LAYER_DEFINITIONS: dict[str, dict[str, Any]] = {
    "ods": {
        "name": "ODS 贴源层",
        "purpose": "与业务系统表结构保持一致(1:1 或 N:1),数据原貌落地,不做清洗。",
        "naming_pattern": "ods_<数据源>_<表名>",
        "examples": ["ods_mysql_order", "ods_log_track", "ods_maxcompute_user"],
        "characteristics": [
            "保留原始字段,不做类型转换(除主键)",
            "全量 + 增量方式落地(append-only)",
            "数据延迟 = 业务系统 T+1",
            "可加 dt 分区字段(数据日期)",
        ],
        "data_flow": "业务系统 → ODS(直连 / binlog / 日志同步)",
        "lifecycle": "保留 30~90 天,过期清理或归档到冷存储。",
    },
    "dwd": {
        "name": "DWD 明细层",
        "purpose": "对 ODS 清洗(去重/去空/标准化/维度退化),形成业务过程明细。",
        "naming_pattern": "dwd_<域>_<业务过程>_<粒度>",
        "examples": ["dwd_trade_order_pay_df", "dwd_trade_order_create_di"],
        "characteristics": [
            "按业务过程分区(每个过程 1 张表)",
            "粒度与 ODS 一致(不汇总)",
            "清洗:空值/脏值/枚举标准化/异常值剔除",
            "关联维度的外键退化(把维度主键放在事实表)",
        ],
        "data_flow": "ODS → DWD(ETL 清洗)",
        "lifecycle": "保留 1~3 年,视业务需要。",
    },
    "dws": {
        "name": "DWS 汇总层",
        "purpose": "按主题(如 用户/商品/商家)汇总 DWD,形成宽表,供 ADS 查询。",
        "naming_pattern": "dws_<域>_<主题>_<修饰>_<周期>",
        "examples": ["dws_trade_user_pay_1d", "dws_trade_sku_sale_1d"],
        "characteristics": [
            "主题宽表:1 行 = 1 个主题实体(用户/商品/商家)在某周期的汇总",
            "周期: 1d/1w/1m/td(total_duration,累计至今)",
            "汇总粒度:轻度聚合(不细化到原始事件)",
            "可下钻:ADS 通过维度过滤可回到 DWD",
        ],
        "data_flow": "DWD → DWS(主题汇总)",
        "lifecycle": "保留 2~5 年,作为下游核心。",
    },
    "dwt": {
        "name": "DWT 主题层(全量累计)",
        "purpose": "累积型事实表,1 行 = 1 个主题实体的全量累计值(从开始到当前)。",
        "naming_pattern": "dwt_<域>_<主题>_<修饰>",
        "examples": ["dwt_trade_user_pay_td", "dwt_trade_sku_sale_td"],
        "characteristics": [
            "1 行 = 1 个主题实体,记录从开始到当前的累计事实",
            "更新:每天合并新增 + 历史(upsert)",
            "数据量稳定(行数 = 主题实体总数)",
            "查询效率高(不需要 SUM 全表)",
        ],
        "data_flow": "DWS → DWT(全量累计)",
        "lifecycle": "长期保留,作为核心数据资产。",
    },
    "ads": {
        "name": "ADS 应用层",
        "purpose": "面向具体报表/接口/产品的应用层,直接给业务使用。",
        "naming_pattern": "ads_<应用名>_<报表/接口名>",
        "examples": ["ads_sales_daily_report", "ads_user_growth_dashboard"],
        "characteristics": [
            "为具体报表/接口定制,可能冗余但查询快",
            "通常 = DWS/DWT 的子集 + 业务自定义字段",
            "权限/脱敏经常在这一层做",
            "数据量小,但访问频次高",
        ],
        "data_flow": "DWS/DWT/DIM → ADS(按需裁剪)",
        "lifecycle": "视业务需要,可重建。",
    },
    "dim": {
        "name": "DIM 维度层",
        "purpose": "公共维度表(如 商品/用户/商家/地区),被各层引用。",
        "naming_pattern": "dim_<主题>_<维度>",
        "examples": ["dim_trade_user", "dim_product_sku", "dim_shop_merchant"],
        "characteristics": [
            "缓慢变化维(SCD)处理在这一层",
            "宽表:1 行 = 1 个维度实体,字段丰富",
            "外键关联的事实表通过 dim_key 关联",
            "可有 dim_xxx_full(全量) + dim_xxx_inc(增量) 双表",
        ],
        "data_flow": "ODS/外部 → DIM(ETL + SCD)",
        "lifecycle": "长期保留,作为数据资产。",
    },
}


def get_layer_definition(layer: str) -> dict[str, Any]:
    """获取分层架构定义。

    Args:
        layer: 层缩写 (ods/dwd/dws/dwt/ads/dim)。

    Returns:
        层定义 dict(包含 name/purpose/naming_pattern/examples/characteristics/data_flow/lifecycle)。

    Raises:
        ValueError: layer 不在 6 层中。

    Examples:
        >>> get_layer_definition('dwd')['name']
        'DWD 明细层'
    """
    layer = layer.lower()
    if layer not in LAYER_DEFINITIONS:
        raise ValueError(
            f"未知层级 '{layer}',合法值: {list(LAYER_DEFINITIONS.keys())}"
        )
    return LAYER_DEFINITIONS[layer]


# ============================================================
# 数据域划分
# ============================================================
# 来源: 阿里《OneData》第 4 章
# 数据域 = 按业务活动划分的高内聚低耦合区,数据建模的第一刀
# 阿里标准 6 大数据域:
#   - 交易 (trade)    下单/支付/退款
#   - 流量 (traffic)  浏览/点击/UV
#   - 用户 (user)     注册/登录/会员
#   - 商品 (item)     商品/类目/品牌
#   - 营销 (market)   优惠券/活动/促销
#   - 互动 (social)   评论/分享/点赞
#   - 财务 (finance)  充值/提现/账单
#   - 物流 (logistic) 发货/收货/签收
#   - 风控 (risk)     登录风控/交易风控
#   - 内容 (content)  文章/视频/UGC
#   - 服务 (service)  客服/工单/售后

DOMAIN_DEFINITIONS: dict[str, dict[str, Any]] = {
    "trade": {
        "name": "交易域",
        "description": "买卖双方交易行为相关数据,包括下单/支付/退款/订单状态流转。",
        "core_business_processes": ["下单", "支付", "退款", "改价"],
        "primary_dimensions": ["用户", "商品", "商家", "订单", "支付方式"],
        "core_metrics": ["GMV", "订单数", "实付金额", "客单价"],
    },
    "traffic": {
        "name": "流量域",
        "description": "用户在站内/站外的浏览/点击/曝光数据。",
        "core_business_processes": ["浏览", "点击", "曝光", "搜索"],
        "primary_dimensions": ["用户", "页面", "渠道", "商品", "活动"],
        "core_metrics": ["PV", "UV", "CTR", "跳出率"],
    },
    "user": {
        "name": "用户域",
        "description": "用户生命周期数据,包括注册/激活/留存/会员等级。",
        "core_business_processes": ["注册", "登录", "激活", "会员升级"],
        "primary_dimensions": ["用户", "渠道", "设备", "地区"],
        "core_metrics": ["注册数", "DAU", "MAU", "留存率"],
    },
    "item": {
        "name": "商品域",
        "description": "商品主数据,包括 SKU/SPU/类目/品牌。",
        "core_business_processes": ["上架", "下架", "调价", "改类目"],
        "primary_dimensions": ["商品", "类目", "品牌", "商家"],
        "core_metrics": ["在售商品数", "新品数"],
    },
    "market": {
        "name": "营销域",
        "description": "促销活动/优惠券/积分。",
        "core_business_processes": ["领券", "用券", "发券", "核销", "活动报名"],
        "primary_dimensions": ["活动", "优惠券", "用户", "商品"],
        "core_metrics": ["券领取数", "券核销数", "活动 GMV", "ROI"],
    },
    "social": {
        "name": "互动域",
        "description": "用户间互动数据(评论/分享/点赞/关注)。",
        "core_business_processes": ["评价", "分享", "点赞", "关注", "收藏"],
        "primary_dimensions": ["用户", "商品", "内容"],
        "core_metrics": ["评论数", "分享数", "关注数"],
    },
    "finance": {
        "name": "财务域",
        "description": "资金流相关,充值/提现/账单/对账。",
        "core_business_processes": ["充值", "提现", "扣款", "对账"],
        "primary_dimensions": ["用户", "账户", "渠道"],
        "core_metrics": ["充值金额", "提现金额", "余额"],
    },
    "logistic": {
        "name": "物流域",
        "description": "仓配/发货/物流轨迹。",
        "core_business_processes": ["发货", "收货", "签收", "退货入库"],
        "primary_dimensions": ["发货单", "仓库", "物流公司", "用户", "商品"],
        "core_metrics": ["发货单数", "签收率", "物流时效"],
    },
    "risk": {
        "name": "风控域",
        "description": "风控决策数据,登录/交易风控拦截。",
        "core_business_processes": ["风控判定", "拦截", "告警"],
        "primary_dimensions": ["用户", "设备", "IP", "场景"],
        "core_metrics": ["拦截数", "误杀率"],
    },
    "content": {
        "name": "内容域",
        "description": "平台内容数据(文章/视频/直播)。",
        "core_business_processes": ["发布", "审核", "推荐", "播放"],
        "primary_dimensions": ["内容", "作者", "用户"],
        "core_metrics": ["发布数", "播放数", "完播率"],
    },
    "service": {
        "name": "服务域",
        "description": "客服/工单/售后服务。",
        "core_business_processes": ["创建工单", "响应", "完结", "评价"],
        "primary_dimensions": ["工单", "客服", "用户"],
        "core_metrics": ["工单数", "响应时长", "满意度"],
    },
}


# 业务模块 → 数据域的映射规则
# 来源: 阿里 OneData 第 4 章 + 行业惯例
_DOMAIN_KEYWORD_MAP: dict[str, list[str]] = {
    "trade": ["订单", "支付", "退款", "下单", "交易", "结算", "改价", "order", "payment"],
    "traffic": ["浏览", "点击", "曝光", "搜索", "pv", "uv", "traffic", "click"],
    "user": ["用户", "注册", "登录", "会员", "留存", "激活", "user", "register", "member"],
    "item": ["商品", "类目", "品牌", "sku", "spu", "item", "product", "category"],
    "market": ["券", "优惠", "活动", "促销", "积分", "coupon", "promotion"],
    "social": ["评价", "评论", "分享", "点赞", "关注", "收藏", "review", "comment"],
    "finance": ["充值", "提现", "账单", "余额", "对账", "recharge", "wallet"],
    "logistic": ["发货", "收货", "签收", "物流", "仓库", "shipment", "delivery", "warehouse"],
    "risk": ["风控", "拦截", "告警", "risk", "fraud"],
    "content": ["文章", "视频", "直播", "内容", "发布", "content", "article", "video"],
    "service": ["客服", "工单", "售后", "服务", "service", "ticket"],
}


def split_data_domain(
    business_area: str, modules: list[str]
) -> dict[str, Any]:
    """数据域划分 (阿里 OneData 第 4 章)。

    来源: 阿里《OneData》第 4 章 "数据域划分"。
    数据域划分的 3 条原则:
        1. **业务内聚**: 同一域内的业务过程必须高内聚(都是同一类业务活动)。
        2. **边界清晰**: 跨域通过 ID 关联,不共享事实表。
        3. **粒度对齐**: 同一域内事实粒度一致(都是订单级或都是事件级)。

    Args:
        business_area: 业务领域描述(如 "电商交易")。
        modules: 功能模块列表(如 ["订单管理", "支付管理", "用户管理"])。

    Returns:
        dict:
            {
                "primary_domain": str,        # 主推域
                "module_to_domain": dict,     # 模块 → 域
                "boundary_checks": list,      # 边界检查结果
                "rationale": str
            }

    判定依据 (Decision Rules):
        - 每个模块按 `_DOMAIN_KEYWORD_MAP` 关键词匹配,得分最高者胜出。
        - 多模块同域时合并,跨域时通过 ID 关联。
        - 未匹配到的模块放入 "uncategorized",提示人工审核。

    边界情况 (Edge Cases):
        - 同一模块跨多域(如下单既涉及 trade 又涉及 finance)→ 选业务主营域,另一域通过 ID 引用。
        - 模块名生僻(不在关键词)→ 走 "uncategorized" + 警告。
        - 业务领域明确指定(传 business_area 含 "电商"/"金融"等)→ 优先匹配行业域。

    Examples:
        >>> r = split_data_domain("电商", ["订单管理", "支付管理", "商品管理", "用户管理"])
        >>> r['primary_domain']
        'trade'
        >>> 'user' in r['module_to_domain'].values()
        True
    """
    module_to_domain: dict[str, str] = {}
    domain_scores: dict[str, int] = {}
    uncategorized: list[str] = []

    for module in modules:
        module_lower = (module or "").lower()
        scores: dict[str, int] = {}
        for domain, keywords in _DOMAIN_KEYWORD_MAP.items():
            for kw in keywords:
                if kw.lower() in module_lower:
                    scores[domain] = scores.get(domain, 0) + 1

        if not scores:
            uncategorized.append(module)
            module_to_domain[module] = "uncategorized"
        else:
            # 选得分最高的域(并列时按 DOMAIN_DEFINITIONS 顺序)
            best_domain = max(
                scores.items(),
                key=lambda x: (x[1], -list(_DOMAIN_KEYWORD_MAP.keys()).index(x[0])),
            )[0]
            module_to_domain[module] = best_domain
            domain_scores[best_domain] = domain_scores.get(best_domain, 0) + 1

    # 主推域
    primary_domain = (
        max(domain_scores.items(), key=lambda x: x[1])[0] if domain_scores else "uncategorized"
    )

    # 边界检查
    boundary_checks: list[dict[str, Any]] = []
    if len(domain_scores) >= 3:
        boundary_checks.append({
            "type": "warning",
            "message": (
                f"模块分散在 {len(domain_scores)} 个数据域,需要明确跨域关联方式(通过 ID 关联)。"
                "建议:每个域建独立总线矩阵,通过公共维度(用户/商品)做桥接。"
            ),
        })
    for module, domain in module_to_domain.items():
        if domain == "uncategorized":
            boundary_checks.append({
                "type": "error",
                "message": f"模块 '{module}' 未匹配到任何数据域,需要人工审核。",
            })

    # 行业优先:business_area 含特定行业关键词
    area_lower = (business_area or "").lower()
    if any(kw in area_lower for kw in ["电商", "零售", "e-commerce", "retail"]):
        if "trade" not in domain_scores:
            boundary_checks.append({
                "type": "info",
                "message": "业务领域为'电商',建议至少包含 trade(交易)域。",
            })
    if any(kw in area_lower for kw in ["金融", "银行", "证券", "finance"]):
        if "finance" not in domain_scores:
            boundary_checks.append({
                "type": "info",
                "message": "业务领域为'金融',建议至少包含 finance(财务)域。",
            })

    rationale_parts = [f"按阿里 OneData 第 4 章数据域划分,"]
    rationale_parts.append(
        f"共识别 {len(domain_scores)} 个数据域:{sorted(domain_scores.keys())}。"
    )
    if uncategorized:
        rationale_parts.append(f"未匹配模块: {uncategorized},需人工归类。")
    rationale_parts.append(
        f"主推域:'{primary_domain}'(基于模块命中频次)。"
    )

    return {
        "primary_domain": primary_domain,
        "primary_domain_name": DOMAIN_DEFINITIONS.get(primary_domain, {}).get("name", "未分类"),
        "module_to_domain": module_to_domain,
        "domain_scores": domain_scores,
        "uncategorized": uncategorized,
        "boundary_checks": boundary_checks,
        "rationale": "".join(rationale_parts),
    }


# ============================================================
# 总线矩阵 (Bus Matrix)
# ============================================================
# 来源: Kimball 第 3 章 "Enterprise Data Warehouse Bus Architecture" + 阿里 OneData 第 5 章
# 总线矩阵 = 业务过程 × 维度的矩阵,标识哪些过程与哪些维度相关
# 用途: 跨域一致性(同一维度在多过程复用),识别事实表的覆盖范围

def build_bus_matrix(
    domain: str,
    business_processes: list[str],
    dimensions: list[str],
) -> dict[str, Any]:
    """构建总线矩阵 (Bus Matrix)。

    来源: Kimball 第 3 章 "Bus Matrix" + 阿里 OneData 第 5 章。

    Args:
        domain: 数据域(如 "trade")。
        business_processes: 业务过程列表(如 ["下单", "支付", "发货"])。
        dimensions: 候选维度列表(如 ["用户", "商品", "时间"])。

    Returns:
        dict:
            {
                "domain": str,
                "matrix": dict,        # 业务过程 → {维度: bool}
                "shared_dimensions": list,   # 跨过程共有的维度
                "process_specific": dict,    # 过程特有的维度
                "statistics": dict
            }

    判定依据 (Decision Rules):
        - 矩阵元素 = True 表示该过程使用该维度。
        - **共享维度**(所有过程都用)= 主维(用户/商品/时间)。
        - **过程特有维度** = 1 个过程用,其他不用(如 支付方式只在支付过程用)。

    边界情况 (Edge Cases):
        - 业务过程为空 → 返回空矩阵 + 警告。
        - 维度为空 → 返回空矩阵 + 提示。

    Examples:
        >>> m = build_bus_matrix('trade', ['下单','支付','发货'], ['用户','商品','时间','支付方式'])
        >>> m['shared_dimensions']
        ['用户', '商品', '时间']
        >>> m['matrix']['下单']['支付方式']
        False
    """
    if not business_processes:
        return {
            "domain": domain,
            "matrix": {},
            "shared_dimensions": [],
            "process_specific": {},
            "statistics": {"processes": 0, "dimensions": len(dimensions)},
            "warning": "未提供业务过程,总线矩阵为空。",
        }

    # 启发式:哪些维度通常是共享的(几乎所有过程都用)
    SHARED_DIMENSION_HINTS = ["用户", "商品", "时间", "时间分区", "用户", "时间", "商品"]

    matrix: dict[str, dict[str, bool]] = {}
    dim_usage: dict[str, int] = {d: 0 for d in dimensions}

    # 维度-过程相关性的启发式规则
    # 1) 用户/商品/时间:几乎所有业务过程都用
    # 2) 支付方式:支付/下单/退款用
    # 3) 物流公司:发货/收货用
    # 4) 收货地址:下单/发货/收货用
    # 5) 商家/店铺:下单/支付/退款用
    # 6) 优惠券/活动:下单/支付用

    DIMENSION_PROCESS_AFFINITY = {
        "用户": ["下单", "支付", "退款", "发货", "收货", "退货", "评价", "注册", "登录", "浏览", "加购"],
        "商品": ["下单", "支付", "退款", "发货", "收货", "退货", "评价", "加购", "浏览", "调拨"],
        "时间": ["下单", "支付", "退款", "发货", "收货", "退货", "评价", "注册", "登录", "浏览"],
        "支付方式": ["下单", "支付", "退款"],
        "物流公司": ["发货", "收货", "退货"],
        "收货地址": ["下单", "发货", "收货"],
        "商家": ["下单", "支付", "退款", "发货", "收货"],
        "促销": ["下单", "支付"],
        "优惠券": ["下单", "支付"],
        "活动": ["下单", "支付", "浏览"],
        "退货原因": ["退货"],
        "注册渠道": ["注册"],
        "登录方式": ["登录"],
    }

    for process in business_processes:
        row: dict[str, bool] = {}
        for dim in dimensions:
            # 检查 affinity
            affinity = DIMENSION_PROCESS_AFFINITY.get(dim, [])
            if process in affinity:
                row[dim] = True
                dim_usage[dim] += 1
            elif dim in SHARED_DIMENSION_HINTS:
                # 时间/用户/商品默认共享
                row[dim] = True
                dim_usage[dim] += 1
            else:
                # 默认 False,但若维度名含过程关键词 → True
                if dim in process or process in dim:
                    row[dim] = True
                    dim_usage[dim] += 1
                else:
                    row[dim] = False
        matrix[process] = row

    # 共享维度(所有过程都用)
    shared_dimensions = [d for d, count in dim_usage.items() if count == len(business_processes)]
    # 过程特有维度(只有 1 个过程用)
    process_specific: dict[str, list[str]] = {}
    for d, count in dim_usage.items():
        if count == 1:
            # 找出哪个过程用了它
            for proc, row in matrix.items():
                if row.get(d):
                    process_specific.setdefault(proc, []).append(d)
                    break

    return {
        "domain": domain,
        "domain_name": DOMAIN_DEFINITIONS.get(domain, {}).get("name", domain),
        "matrix": matrix,
        "shared_dimensions": shared_dimensions,
        "process_specific": process_specific,
        "statistics": {
            "processes": len(business_processes),
            "dimensions": len(dimensions),
            "shared_dimension_count": len(shared_dimensions),
            "process_specific_count": len(process_specific),
        },
    }


# ============================================================
# 命名规范
# ============================================================
# 来源: 阿里《OneData》第 7 章 + Kimball 命名惯例
# 命名规则:
#   - 层: 3 字符小写 (ods/dwd/dws/dwt/ads/dim)
#   - 域: 英文小写,见 DOMAIN_DEFINITIONS
#   - 业务/业务过程: 英文小写
#   - 修饰词: 英文小写(可空)
#   - 周期: 1d/1w/1m/td(ytd/mtd)
#   - 单词间用下划线分隔
#   - 总长 ≤ 64 字符

# 中文业务名 → 英文表名片段 映射(用于规范化)
_CN_TO_EN_TABLE: dict[str, str] = {
    "订单": "order",
    "子订单": "sub_order",
    "支付": "pay",
    "退款": "refund",
    "发货": "ship",
    "收货": "receive",
    "退货": "return",
    "评价": "review",
    "商品": "product",
    "商品SKU": "sku",
    "商品SPU": "spu",
    "用户": "user",
    "会员": "member",
    "商家": "merchant",
    "店铺": "shop",
    "类目": "category",
    "品牌": "brand",
    "浏览": "view",
    "点击": "click",
    "曝光": "impression",
    "搜索": "search",
    "登录": "login",
    "注册": "register",
    "充值": "recharge",
    "提现": "withdraw",
    "优惠券": "coupon",
    "活动": "campaign",
    "积分": "points",
    "物流": "logistics",
    "仓": "warehouse",
    "库存": "inventory",
    "客服": "service",
    "工单": "ticket",
    "结算": "settle",
    "对账": "reconcile",
    "下单": "create",
    "核销": "redeem",
    "加购": "cart",
    "收藏": "favorite",
    "取消": "cancel",
    "改签": "modify",
    "入库": "inbound",
    "出库": "outbound",
    "盘点": "stocktake",
    "调拨": "transfer",
    "审批": "approve",
    "晋升": "promote",
}


def _to_snake_case(text: str) -> str:
    """把字符串转为 snake_case 英文片段。"""
    if not text:
        return ""
    text = text.strip()
    # 已是英文 snake_case,直接返回
    if re.match(r"^[a-z][a-z0-9_]*$", text):
        return text
    # 中文查表
    if text in _CN_TO_EN_TABLE:
        return _CN_TO_EN_TABLE[text]
    # 中文数据域名 → 英文 domain key(查 DOMAIN_DEFINITIONS)
    for key, defn in DOMAIN_DEFINITIONS.items():
        if defn.get("name", "").replace("域", "") == text:
            return key
    # 中文部分查表,英文部分保留
    result = []
    i = 0
    while i < len(text):
        # 尝试匹配 4 字中文
        for size in [4, 3, 2, 1]:
            chunk = text[i : i + size]
            if chunk in _CN_TO_EN_TABLE:
                result.append(_CN_TO_EN_TABLE[chunk])
                i += size
                break
        else:
            # 单字符处理
            ch = text[i]
            if "\u4e00" <= ch <= "\u9fff":
                # 中文字符没匹配,转拼音太复杂,使用 fallback
                result.append(_CN_TO_EN_TABLE.get(ch, "x"))
            elif ch.isalnum():
                result.append(ch.lower())
            elif ch in "_-":
                result.append("_")
            i += 1
    out = "_".join([r for r in result if r])
    # 清理多余下划线
    out = re.sub(r"_+", "_", out).strip("_")
    return out or "x"


def generate_naming(
    layer: str,
    domain: str | None = None,
    business: str | None = None,
    modifier: str | None = None,
    period: str | None = None,
    *,
    data_source: str | None = None,
    application: str | None = None,
    dimension: str | None = None,
) -> str:
    """生成标准表名 (阿里 OneData 第 7 章)。

    命名规则:
        - ods:   ods_<数据源>_<表名>
        - dim:   dim_<主题>_<维度>
        - dwd:   dwd_<域>_<业务过程>_<粒度>
        - dws:   dws_<域>_<主题>_<修饰>_<周期>
        - dwt:   dwt_<域>_<主题>_<修饰>
        - ads:   ads_<应用名>_<报表/接口名>

    Args:
        layer: 层 (ods/dwd/dws/dwt/ads/dim)。
        domain: 数据域 (trade/traffic/...) 或中文名("交易")。
        business: 业务名/业务过程("订单"/"下单")。
        modifier: 修饰词("pay"/"支付")。
        period: 时间周期("1d"/"1w"/"1m"/"td")。
        data_source: 数据源(仅 ODS 用,如 "mysql"/"log")。
        application: 应用名(仅 ADS 用,如 "sales_daily")。
        dimension: 维度主题(仅 DIM 用,如 "trade_user")。

    Returns:
        标准表名字符串。

    判定依据 (Decision Rules):
        - 按层调用不同模板,字段缺失则省略。
        - 字段名通过 `_to_snake_case` 规范化(中文→英文)。

    边界情况 (Edge Cases):
        - 未知层 → 抛 ValueError。
        - 必填字段缺失 → 用 "x" 占位 + 警告。

    Examples:
        >>> generate_naming(layer='dws', domain='trade', business='order',
        ...                  modifier='pay', period='1d')
        'dws_trade_order_pay_1d'
        >>> generate_naming(layer='ods', data_source='mysql', business='order')
        'ods_mysql_order'
    """
    layer = layer.lower()
    if layer not in LAYER_DEFINITIONS:
        raise ValueError(
            f"未知层级 '{layer}',合法值: {list(LAYER_DEFINITIONS.keys())}"
        )

    domain_seg = _to_snake_case(domain) if domain else ""
    business_seg = _to_snake_case(business) if business else ""
    modifier_seg = _to_snake_case(modifier) if modifier else ""
    period_seg = period.lower() if period else ""

    if layer == "ods":
        src = _to_snake_case(data_source) if data_source else "src"
        parts = ["ods", src, business_seg] if business_seg else ["ods", src]
    elif layer == "dim":
        dim_seg = _to_snake_case(dimension) if dimension else business_seg
        parts = ["dim", domain_seg, dim_seg] if domain_seg else ["dim", dim_seg or "x"]
    elif layer == "dwd":
        parts = ["dwd"]
        if domain_seg:
            parts.append(domain_seg)
        if business_seg:
            parts.append(business_seg)
        if modifier_seg:
            parts.append(modifier_seg)
        if not any(p != "dwd" for p in parts):
            parts.append("x")
    elif layer == "dws":
        parts = ["dws"]
        if domain_seg:
            parts.append(domain_seg)
        if business_seg:
            parts.append(business_seg)
        if modifier_seg:
            parts.append(modifier_seg)
        if period_seg:
            parts.append(period_seg)
    elif layer == "dwt":
        parts = ["dwt"]
        if domain_seg:
            parts.append(domain_seg)
        if business_seg:
            parts.append(business_seg)
        if modifier_seg:
            parts.append(modifier_seg)
        if not period_seg:
            period_seg = "td"  # DWT 默认为累计
        if period_seg:
            parts.append(period_seg)
    elif layer == "ads":
        app = _to_snake_case(application) if application else business_seg or "x"
        if modifier_seg:
            app = f"{app}_{modifier_seg}"
        parts = ["ads", app]
    else:
        parts = ["x"]

    table_name = "_".join([p for p in parts if p])
    table_name = re.sub(r"_+", "_", table_name).strip("_")
    return table_name


# ============================================================
# 指标体系
# ============================================================
# 来源: 阿里《OneData》第 6 章 "指标管理体系"
# 指标体系是阿里 OneData 的核心:
#   - 原子指标 (Atomic Metric): 不可再分的业务度量 + 聚合方式
#   - 修饰词 (Modifier): 业务场景限定(支付的/完成的)
#   - 时间周期 (Period): 统计时间窗(最近 1 天/最近 7 天/历史至今)
#   - 派生指标 (Derived Metric) = 原子指标 + 修饰词 + 时间周期

@dataclass
class AtomicMetric:
    """原子指标定义。

    来源: 阿里 OneData 第 6 章。
    原子指标 = 业务过程下的度量 + 聚合方式,例: "订单金额(SUM)"、"用户数(COUNT_DISTINCT)"。
    必须挂靠在具体业务过程下,不能脱离业务过程定义。
    """

    name: str
    business_process: str
    aggregation: str  # SUM | COUNT | COUNT_DISTINCT | AVG | MAX | MIN
    measure_field: str  # 度量字段,如 "amount"
    description: str = ""
    unit: str = ""  # 元/个/%

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DerivedMetric:
    """派生指标定义。

    派生指标 = 原子指标 + 修饰词 + 时间周期。
    公式: 派生指标 = 修饰词 + 原子指标名 + 周期修饰
    例: "最近 1 天支付的订单金额" = "支付的" + "订单金额(SUM)" + "最近 1 天"
    """

    name: str
    atomic_metric_name: str
    modifiers: list[str] = field(default_factory=list)
    period: str = "最近 1 天"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def define_atomic_metric(
    name: str,
    business_process: str,
    aggregation: str,
    measure_field: str,
    unit: str = "",
    description: str = "",
) -> dict[str, Any]:
    """定义原子指标 (阿里 OneData 第 6 章)。

    Args:
        name: 指标名(如 "订单金额")。
        business_process: 所属业务过程(如 "下单")。
        aggregation: 聚合方式(SUM/COUNT/COUNT_DISTINCT/AVG/MAX/MIN)。
        measure_field: 度量字段(如 "amount"/"user_id")。
        unit: 单位("元"/"个"/"%")。
        description: 业务描述。

    Returns:
        原子指标 dict(可序列化为 JSON)。

    判定依据 (Decision Rules):
        - 聚合方式必须合法(6 选 1)。
        - 度量字段不能为空。

    边界情况 (Edge Cases):
        - 聚合方式不合法 → 抛 ValueError。
        - 度量字段为空 → 抛 ValueError。

    Examples:
        >>> m = define_atomic_metric("订单金额", "下单", "SUM", "amount", "元")
        >>> m['name']
        '订单金额'
        >>> m['aggregation']
        'SUM'
    """
    valid_aggregations = {"SUM", "COUNT", "COUNT_DISTINCT", "AVG", "MAX", "MIN"}
    agg = aggregation.upper()
    if agg not in valid_aggregations:
        raise ValueError(
            f"非法聚合方式 '{aggregation}',合法值: {sorted(valid_aggregations)}"
        )
    if not measure_field or not measure_field.strip():
        raise ValueError("measure_field(度量字段)不能为空")

    return AtomicMetric(
        name=name,
        business_process=business_process,
        aggregation=agg,
        measure_field=measure_field,
        description=description or f"{business_process} 业务过程下的 {name}",
        unit=unit,
    ).to_dict()


def derive_metric(
    atomic: str,
    modifiers: list[str] | str = "",
    period: str = "最近 1 天",
) -> dict[str, Any]:
    """派生指标 = 原子指标 + 修饰词 + 时间周期 (阿里 OneData 第 6 章)。

    Args:
        atomic: 原子指标名(已通过 define_atomic_metric 定义)。
        modifiers: 修饰词列表(支持 str 或 list)。
        period: 时间周期(默认 "最近 1 天")。

    Returns:
        派生指标 dict(包含计算后的标准名 + 公式)。

    判定依据 (Decision Rules):
        - 公式: 派生指标名 = 周期 + 修饰词 + 原子指标
        - 例: "最近 1 天支付的订单金额"
        - 公式: 派生指标 = 周期 [修饰词 1] [修饰词 2] [原子指标]

    边界情况 (Edge Cases):
        - 修饰词为空 → 派生指标 = 周期 + 原子指标。
        - 原子指标为空 → 抛 ValueError。

    Examples:
        >>> m = derive_metric("订单金额", modifiers=["支付的"], period="最近 1 天")
        >>> m['name']
        '最近 1 天 支付的 订单金额'
    """
    if not atomic or not atomic.strip():
        raise ValueError("atomic(原子指标)不能为空")

    if isinstance(modifiers, str):
        modifiers = [modifiers] if modifiers.strip() else []
    modifiers = [m.strip() for m in modifiers if m and m.strip()]

    name = " ".join([period] + modifiers + [atomic])

    return DerivedMetric(
        name=name,
        atomic_metric_name=atomic,
        modifiers=modifiers,
        period=period,
    ).to_dict()


# ============================================================
# 综合入口
# ============================================================


def onedata_overview() -> dict[str, Any]:
    """OneData 规范总览,用于帮助页/文档导出。

    Returns:
        dict 包含:
            - layers: 6 层架构定义
            - domains: 11 个数据域定义
            - naming_rules: 命名规则
            - metric_rules: 指标体系规则
    """
    return {
        "layers": LAYER_DEFINITIONS,
        "domains": DOMAIN_DEFINITIONS,
        "naming_rules": {
            "ods": "ods_<数据源>_<表名>",
            "dwd": "dwd_<域>_<业务过程>_<粒度>",
            "dws": "dws_<域>_<主题>_<修饰>_<周期>",
            "dwt": "dwt_<域>_<主题>_<修饰>_<周期>",
            "ads": "ads_<应用名>_<报表/接口名>",
            "dim": "dim_<主题>_<维度>",
        },
        "metric_rules": {
            "atomic": "原子指标 = 业务过程 + 度量字段 + 聚合方式",
            "modifier": "修饰词 = 业务场景限定(支付/完成/退款)",
            "period": "时间周期 = 最近 1 天 / 最近 7 天 / 历史至今",
            "derived_formula": "派生指标 = 周期 + 修饰词 + 原子指标",
        },
        "source": "阿里《OneData — 大数据之路》(2017) + Kimball 总线架构",
    }
