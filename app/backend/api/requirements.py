"""阶段 0-1: 需求调研 (业务 / 指标 / 维度 / 数据源).

API:
    POST /api/requirements/business
    POST /api/requirements/metrics
    GET  /api/requirements/session/{sid}
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.backend import session_store
from app.backend.schemas import (
    BusinessResearchInput,
    BusinessResearchOutput,
    MetricsResearchInput,
    MetricsResearchOutput,
    SessionResponse,
)

router = APIRouter(prefix="/api/requirements", tags=["requirements"])


@router.post("/business", response_model=BusinessResearchOutput)
def post_business(payload: BusinessResearchInput) -> BusinessResearchOutput:
    """业务调研: 生成业务-功能-角色矩阵."""
    if not payload.business_name.strip():
        raise HTTPException(400, "business_name 不能为空")

    sess = session_store.get_or_create(payload.session_id)

    # 生成矩阵: 行=功能模块, 列=用户角色, 单元=该角色对该模块的关注点
    role_focus = {
        "买家": "下单/支付/收货体验",
        "卖家": "商品/库存/订单履约",
        "运营": "GMV/转化率/客单价",
        "管理员": "权限/审计/对账",
    }
    matrix = []
    for module in payload.functional_modules or ["(未指定模块)"]:
        for role in payload.user_roles or ["(未指定角色)"]:
            focus = role_focus.get(role, f"{role}对该模块的核心关注")
            matrix.append({
                "business": payload.business_name,
                "functional_module": module,
                "user_role": role,
                "focus": focus,
            })

    summary = {
        "business": payload.business_name,
        "module_count": len(payload.functional_modules),
        "role_count": len(payload.user_roles),
        "matrix_rows": len(matrix),
    }

    sess.data["stage0"] = {
        "business_name": payload.business_name,
        "functional_modules": payload.functional_modules,
        "user_roles": payload.user_roles,
        "matrix": matrix,
        "summary": summary,
    }
    session_store.mark_complete(payload.session_id, 0)

    return BusinessResearchOutput(
        session_id=payload.session_id,
        business_name=payload.business_name,
        matrix=matrix,
        summary=summary,
    )


@router.post("/metrics", response_model=MetricsResearchOutput)
def post_metrics(payload: MetricsResearchInput) -> MetricsResearchOutput:
    """需求调研: 列出指标 / 维度 / 数据源清单."""
    if not payload.metrics:
        raise HTTPException(400, "metrics 不能为空")

    sess = session_store.get_or_create(payload.session_id)
    # 引用 stage0 模块做交叉 (如果有)
    stage0 = sess.data.get("stage0", {})
    business_name = stage0.get("business_name", "(未指定业务)")

    # 原子指标: 简化推断
    metrics_list = []
    for m in payload.metrics:
        # 推断单位 / 聚合方式
        if "率" in m or "占比" in m or "比例" in m:
            unit = "%"
            agg = "ratio"
        elif "金额" in m or "GMV" in m or "价" in m:
            unit = "元"
            agg = "sum"
        elif "数" in m or "量" in m or "次" in m:
            unit = "个"
            agg = "count"
        else:
            unit = ""
            agg = "sum"
        metrics_list.append({
            "name": m,
            "business": business_name,
            "aggregation": agg,
            "unit": unit,
            "type": "atomic",
        })

    # 维度清单: 标准化
    dim_categorize = {
        "用户": "entity",
        "商品": "entity",
        "商家": "entity",
        "时间": "temporal",
        "地区": "geography",
        "渠道": "channel",
        "支付方式": "channel",
        "订单": "transaction",
    }
    dimensions_list = []
    for d in payload.dimensions or []:
        dimensions_list.append({
            "name": d,
            "category": dim_categorize.get(d, "other"),
            "scd_default": 1,
        })

    # 数据源清单: 简单分类
    data_sources_list = []
    for ds in payload.data_sources or []:
        if "mysql" in ds.lower():
            kind = "RDBMS"
        elif "kafka" in ds.lower() or "log" in ds.lower():
            kind = "Stream"
        elif "hive" in ds.lower() or "iceberg" in ds.lower():
            kind = "Lake"
        else:
            kind = "Unknown"
        data_sources_list.append({
            "name": ds,
            "kind": kind,
            "ingestion": "batch" if kind == "RDBMS" else ("stream" if kind == "Stream" else "batch"),
        })

    sess.data["stage1"] = {
        "metrics_list": metrics_list,
        "dimensions_list": dimensions_list,
        "data_sources_list": data_sources_list,
    }
    session_store.mark_complete(payload.session_id, 1)

    return MetricsResearchOutput(
        session_id=payload.session_id,
        metrics_list=metrics_list,
        dimensions_list=dimensions_list,
        data_sources_list=data_sources_list,
    )


@router.get("/session/{sid}", response_model=SessionResponse)
def get_session(sid: str) -> SessionResponse:
    """拉取会话状态."""
    sess = session_store.get(sid)
    if not sess:
        return SessionResponse(session_id=sid, created_at="", stages_completed=[])
    return SessionResponse(
        session_id=sid,
        created_at=sess.created_at,
        stages_completed=sess.stages_completed,
    )
