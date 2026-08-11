"""阶段 4: 模型设计 (Kimball 4 步法) + DDL 生成.

API:
    POST /api/modeling/business-process
    POST /api/modeling/grain
    POST /api/modeling/dimensions
    POST /api/modeling/facts
    POST /api/modeling/fact-type
    POST /api/modeling/ddl
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.backend import session_store
from app.backend.schemas import (
    BusinessProcessInput,
    BusinessProcessOutput,
    DDLInput,
    DDLOutput,
    DimensionsInput,
    DimensionsOutput,
    FactsInput,
    FactsOutput,
    FactTypeInput,
    FactTypeOutput,
    GrainInput,
    GrainOutput,
)
from app.knowledge import kimball

router = APIRouter(prefix="/api/modeling", tags=["modeling"])


@router.post("/business-process", response_model=BusinessProcessOutput)
def post_business_process(payload: BusinessProcessInput) -> BusinessProcessOutput:
    """Step 1: 识别业务过程."""
    if not payload.business_description.strip():
        raise HTTPException(400, "business_description 不能为空")

    processes = kimball.identify_business_process(payload.business_description)
    sess = session_store.get_or_create(payload.session_id)
    sess.data["stage4_processes"] = processes
    session_store.mark_complete(payload.session_id, 4)

    return BusinessProcessOutput(
        session_id=payload.session_id,
        processes=processes,
    )


@router.post("/grain", response_model=GrainOutput)
def post_grain(payload: GrainInput) -> GrainOutput:
    """Step 2: 声明粒度."""
    if not payload.business_process.strip():
        raise HTTPException(400, "business_process 不能为空")

    grain = kimball.declare_grain(payload.business_process)
    decision_questions = [
        "一行 = 一个什么事件?",
        "这个事件能不能再分得更细?",
        "如果是订单,选 '子订单' 还是 '主订单'? (推荐子订单,包含 SKU 维度)",
        "如果不确定,选最细粒度,后续用聚合事实表补 (DWS)",
    ]
    sess = session_store.get_or_create(payload.session_id)
    sess.data["stage4_grain"] = grain
    session_store.mark_complete(payload.session_id, 4)

    return GrainOutput(
        session_id=payload.session_id,
        grain=grain,
        decision_questions=decision_questions,
    )


@router.post("/dimensions", response_model=DimensionsOutput)
def post_dimensions(payload: DimensionsInput) -> DimensionsOutput:
    """Step 3: 识别维度."""
    if not payload.business_process or not payload.grain:
        raise HTTPException(400, "business_process 和 grain 不能为空")

    dimensions = kimball.identify_dimensions(
        business_process=payload.business_process,
        grain=payload.grain,
    )
    # 兜底: 如果知识库返回空, 加默认维度
    if not dimensions:
        dimensions = [
            {"name": "日期", "role": "primary", "attributes": ["日期", "周", "月", "季度"]},
            {"name": "用户", "role": "primary", "attributes": ["用户ID", "用户类型", "注册时间"]},
        ]
    sess = session_store.get_or_create(payload.session_id)
    sess.data["stage4_dimensions"] = dimensions
    session_store.mark_complete(payload.session_id, 4)

    return DimensionsOutput(
        session_id=payload.session_id,
        dimensions=dimensions,
    )


@router.post("/facts", response_model=FactsOutput)
def post_facts(payload: FactsInput) -> FactsOutput:
    """Step 4: 识别事实."""
    if not payload.business_process or not payload.grain:
        raise HTTPException(400, "business_process 和 grain 不能为空")

    facts = kimball.identify_facts(
        business_process=payload.business_process,
        grain=payload.grain,
        dimensions=payload.dimensions,
    )
    if not facts:
        facts = [
            {"name": "度量金额", "additivity": "additive", "data_type": "DECIMAL(18,2)"},
            {"name": "度量数量", "additivity": "additive", "data_type": "BIGINT"},
        ]
    sess = session_store.get_or_create(payload.session_id)
    sess.data["stage4_facts"] = facts
    session_store.mark_complete(payload.session_id, 4)

    return FactsOutput(
        session_id=payload.session_id,
        facts=facts,
    )


@router.post("/fact-type", response_model=FactTypeOutput)
def post_fact_type(payload: FactTypeInput) -> FactTypeOutput:
    """Step 5: 决定事实表类型."""
    if not payload.business_processes:
        raise HTTPException(400, "business_processes 不能为空")

    result = kimball.decide_fact_type(
        business_processes=payload.business_processes,
        has_time_intervals=payload.has_time_intervals,
    )

    # 中文映射
    fact_type_name_map = {
        "transaction": "事务事实表",
        "periodic_snapshot": "周期快照事实表",
        "accumulating_snapshot": "累积快照事实表",
    }
    fact_type = result["fact_type"]
    fact_type_name = fact_type_name_map.get(fact_type, fact_type)

    sess = session_store.get_or_create(payload.session_id)
    sess.data["stage4_fact_type"] = result
    session_store.mark_complete(payload.session_id, 4)

    return FactTypeOutput(
        session_id=payload.session_id,
        fact_type=fact_type,
        fact_type_name=fact_type_name,
        confidence=result.get("confidence", 0.0),
        rationale=result.get("rationale", ""),
        alternatives=result.get("alternatives", []),
        warnings=result.get("warnings", []),
    )


@router.post("/ddl", response_model=DDLOutput)
def post_ddl(payload: DDLInput) -> DDLOutput:
    """生成 DDL: 事实表 + 维度表."""
    if not payload.fact_table_name:
        raise HTTPException(400, "fact_table_name 不能为空")

    dim_tables = []
    dim_create_stmts = []
    for d in payload.dimensions:
        dim_name = d.get("name", "dim_unknown")
        dim_tbl = f"dim_{dim_name.lower()}"
        attrs = d.get("attributes", ["id"])
        # 简单生成 dim 表 DDL
        col_lines = ["    id BIGINT PRIMARY KEY"]
        for a in attrs:
            if a.lower() == "id":
                continue
            if "时间" in a or "日期" in a or "date" in a.lower() or "time" in a.lower():
                col_lines.append(f"    {a} DATE")
            elif "数" in a or "量" in a or "id" in a.lower():
                col_lines.append(f"    {a} BIGINT")
            else:
                col_lines.append(f"    {a} VARCHAR(255)")
        col_lines.append("    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        ddl = f"CREATE TABLE IF NOT EXISTS {dim_tbl} (\n" + ",\n".join(col_lines) + "\n);"
        dim_tables.append({"name": dim_tbl, "ddl": ddl, "dimension": dim_name})
        dim_create_stmts.append(ddl)

    # 事实表 DDL
    fact_cols = ["    id BIGINT PRIMARY KEY"]
    # 累积快照: 多日期列
    if payload.fact_type == "accumulating_snapshot":
        for proc in ["order_date", "pay_date", "ship_date", "receive_date"]:
            fact_cols.append(f"    {proc} DATE")
    else:
        fact_cols.append("    event_date DATE")
    # 维度外键
    for d in payload.dimensions:
        dim_name = d.get("name", "")
        fact_cols.append(f"    {dim_name.lower()}_id BIGINT")
    # 度量
    for f in payload.facts:
        fname = f.get("name", "measure")
        ftype = f.get("data_type", "DECIMAL(18,2)")
        fact_cols.append(f"    {fname.lower()} {ftype}")
    fact_cols.append("    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    fact_ddl = (
        f"-- 事实表: {payload.fact_table_name} ({payload.fact_type})\n"
        f"-- 业务过程: {payload.business_process}\n"
        f"-- 粒度: {payload.grain}\n"
        f"CREATE TABLE IF NOT EXISTS {payload.fact_table_name} (\n"
        + ",\n".join(fact_cols)
        + "\n);"
    )

    full_ddl = "\n\n".join(dim_create_stmts + [fact_ddl])

    sess = session_store.get_or_create(payload.session_id)
    sess.data["stage4_ddl"] = {
        "fact_table": payload.fact_table_name,
        "dim_tables": dim_tables,
        "ddl": full_ddl,
    }
    session_store.mark_complete(payload.session_id, 4)

    return DDLOutput(
        session_id=payload.session_id,
        ddl=full_ddl,
        fact_table=payload.fact_table_name,
        dim_tables=dim_tables,
    )
