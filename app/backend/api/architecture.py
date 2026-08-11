"""阶段 2-3: 架构设计 (数据域 / 总线矩阵) + 规范定义 (命名 / 指标字典).

API:
    POST /api/architecture/domains
    POST /api/architecture/bus-matrix
    POST /api/architecture/naming
    POST /api/architecture/metric-dict
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.backend import session_store
from app.backend.schemas import (
    BusMatrixInput,
    BusMatrixOutput,
    DomainInput,
    DomainOutput,
    MetricDictInput,
    MetricDictOutput,
    NamingInput,
    NamingOutput,
)
from app.knowledge import onedata

router = APIRouter(prefix="/api/architecture", tags=["architecture"])


@router.post("/domains", response_model=DomainOutput)
def post_domains(payload: DomainInput) -> DomainOutput:
    """数据域划分."""
    if not payload.functional_modules:
        raise HTTPException(400, "functional_modules 不能为空")

    result = onedata.split_data_domain(payload.business, payload.functional_modules)
    sess = session_store.get_or_create(payload.session_id)
    sess.data["stage2_domains"] = result
    session_store.mark_complete(payload.session_id, 2)

    return DomainOutput(
        session_id=payload.session_id,
        primary_domain=result["primary_domain"],
        primary_domain_name=result["primary_domain_name"],
        module_to_domain=result["module_to_domain"],
        boundary_checks=result.get("boundary_checks", []),
        rationale=result.get("rationale", ""),
    )


@router.post("/bus-matrix", response_model=BusMatrixOutput)
def post_bus_matrix(payload: BusMatrixInput) -> BusMatrixOutput:
    """总线矩阵."""
    if not payload.business_processes or not payload.dimensions:
        raise HTTPException(400, "business_processes 和 dimensions 不能为空")

    result = onedata.build_bus_matrix(
        domain=payload.domain,
        business_processes=payload.business_processes,
        dimensions=payload.dimensions,
    )
    sess = session_store.get_or_create(payload.session_id)
    sess.data["stage2_bus_matrix"] = result
    session_store.mark_complete(payload.session_id, 2)

    return BusMatrixOutput(
        session_id=payload.session_id,
        domain=result["domain"],
        domain_name=result["domain_name"],
        matrix=result["matrix"],
        shared_dimensions=result["shared_dimensions"],
        statistics=result.get("statistics", {}),
    )


@router.post("/naming", response_model=NamingOutput)
def post_naming(payload: NamingInput) -> NamingOutput:
    """命名规范生成."""
    layer_def = onedata.get_layer_definition(payload.layer) or {}
    table_name = onedata.generate_naming(
        layer=payload.layer,
        domain=payload.domain,
        business=payload.business,
        modifier=payload.modifier,
        period=payload.period,
    )
    sess = session_store.get_or_create(payload.session_id)
    sess.data["stage3_naming"] = {"table_name": table_name, "layer_definition": layer_def}
    session_store.mark_complete(payload.session_id, 3)

    return NamingOutput(
        session_id=payload.session_id,
        table_name=table_name,
        layer_definition=layer_def,
    )


@router.post("/metric-dict", response_model=MetricDictOutput)
def post_metric_dict(payload: MetricDictInput) -> MetricDictOutput:
    """指标字典 (原子 + 派生)."""
    atomic = onedata.define_atomic_metric(
        name=payload.atomic_name,
        business_process=payload.business_process,
        aggregation=payload.aggregation,
        measure_field=payload.measure_field,
        unit=payload.unit,
        description=payload.description,
    )
    derived_list = []
    for mod in payload.derived_modifiers or [payload.period]:
        d = onedata.derive_metric(payload.atomic_name, mod, payload.period)
        derived_list.append(d)

    sess = session_store.get_or_create(payload.session_id)
    sess.data["stage3_metric_dict"] = {"atomic": atomic, "derived": derived_list}
    session_store.mark_complete(payload.session_id, 3)

    return MetricDictOutput(
        session_id=payload.session_id,
        atomic=atomic,
        derived=derived_list,
    )
