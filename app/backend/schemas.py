"""Pydantic v2 请求/响应模型 (6 阶段 API 全部).

每个阶段都有 Input/Output 两类.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ============================================================
# 通用
# ============================================================


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    db_mode: str = ""


class SessionResponse(BaseModel):
    session_id: str
    created_at: str = ""
    stages_completed: list[int] = []


# ============================================================
# 阶段 0: 业务调研
# ============================================================


class BusinessResearchInput(BaseModel):
    session_id: str
    business_name: str = Field(..., description="业务名, 如 '电商订单'")
    functional_modules: list[str] = Field(default_factory=list, description="功能模块, 如 ['订单', '商品', '用户']")
    user_roles: list[str] = Field(default_factory=list, description="用户角色, 如 ['买家', '卖家', '运营']")


class BusinessResearchOutput(BaseModel):
    session_id: str
    business_name: str
    matrix: list[dict[str, Any]]  # 业务-功能-角色矩阵
    summary: dict[str, Any]


# ============================================================
# 阶段 1: 需求调研
# ============================================================


class MetricsResearchInput(BaseModel):
    session_id: str
    metrics: list[str] = Field(..., description="指标, 如 ['GMV', '订单数']")
    dimensions: list[str] = Field(default_factory=list, description="维度, 如 ['用户', '商品']")
    data_sources: list[str] = Field(default_factory=list, description="数据源, 如 ['mysql.orders', 'kafka.click']")


class MetricsResearchOutput(BaseModel):
    session_id: str
    metrics_list: list[dict[str, Any]]
    dimensions_list: list[dict[str, Any]]
    data_sources_list: list[dict[str, Any]]


# ============================================================
# 阶段 2: 架构设计
# ============================================================


class DomainInput(BaseModel):
    session_id: str
    business: str = Field(..., description="业务领域, 如 '电商'")
    functional_modules: list[str] = Field(..., description="功能模块, 如 ['订单', '商品', '用户']")


class DomainOutput(BaseModel):
    session_id: str
    primary_domain: str
    primary_domain_name: str
    module_to_domain: dict[str, str]
    boundary_checks: list[dict[str, Any]] = []
    rationale: str = ""


class BusMatrixInput(BaseModel):
    session_id: str
    domain: str
    business_processes: list[str]
    dimensions: list[str]


class BusMatrixOutput(BaseModel):
    session_id: str
    domain: str
    domain_name: str
    matrix: dict[str, dict[str, bool]]
    shared_dimensions: list[str]
    statistics: dict[str, Any] = {}


# ============================================================
# 阶段 3: 规范定义
# ============================================================


class NamingInput(BaseModel):
    session_id: str
    layer: str = Field(..., description="ods / dwd / dws / dwt / ads / dim")
    domain: Optional[str] = None
    business: Optional[str] = None
    modifier: Optional[str] = None
    period: Optional[str] = None


class NamingOutput(BaseModel):
    session_id: str
    table_name: str
    layer_definition: dict[str, Any] = {}


class MetricDictInput(BaseModel):
    session_id: str
    atomic_name: str = Field(..., description="原子指标名, 如 '订单数'")
    business_process: str
    aggregation: str = Field(..., description="count / sum / avg")
    measure_field: str = Field(..., description="度量字段, 如 'order_id'")
    unit: str = ""
    description: str = ""
    derived_modifiers: list[str] = Field(default_factory=list, description="派生修饰词, 如 ['最近', '最近7天']")
    period: str = "最近 1 天"


class MetricDictOutput(BaseModel):
    session_id: str
    atomic: dict[str, Any]
    derived: list[dict[str, Any]]


# ============================================================
# 阶段 4: 模型设计 (Kimball 4 步法)
# ============================================================


class BusinessProcessInput(BaseModel):
    session_id: str
    business_description: str = Field(..., description="业务过程描述文本")


class BusinessProcessOutput(BaseModel):
    session_id: str
    processes: list[dict[str, Any]]


class GrainInput(BaseModel):
    session_id: str
    business_process: str


class GrainOutput(BaseModel):
    session_id: str
    grain: str
    decision_questions: list[str] = []


class DimensionsInput(BaseModel):
    session_id: str
    business_process: str
    grain: str


class DimensionsOutput(BaseModel):
    session_id: str
    dimensions: list[dict[str, Any]]


class FactsInput(BaseModel):
    session_id: str
    business_process: str
    grain: str
    dimensions: list[dict[str, Any]]


class FactsOutput(BaseModel):
    session_id: str
    facts: list[dict[str, Any]]


class FactTypeInput(BaseModel):
    session_id: str
    business_processes: list[str]
    has_time_intervals: bool = False


class FactTypeOutput(BaseModel):
    session_id: str
    fact_type: str
    fact_type_name: str
    confidence: float
    rationale: str
    alternatives: list[dict[str, Any]] = []
    warnings: list[str] = []


class DDLInput(BaseModel):
    session_id: str
    fact_type: str
    fact_table_name: str = "fact_order_acc"
    business_process: str = ""
    grain: str = ""
    dimensions: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []


class DDLOutput(BaseModel):
    session_id: str
    ddl: str
    fact_table: str
    dim_tables: list[dict[str, Any]] = []


# ============================================================
# 阶段 5: 跑数 (5 层 SQL)
# ============================================================


class SQLGenInput(BaseModel):
    session_id: str
    layer: str = Field(..., description="ods / dwd / dws / dwt / ads")
    domain: str = ""
    business: str = ""
    source_table: str = ""
    target_table: str = ""


class SQLGenOutput(BaseModel):
    session_id: str
    layer: str
    sql: str
    description: str = ""


class RunSQLInput(BaseModel):
    session_id: str
    sql: str
    mock_data: bool = True


class RunSQLOutput(BaseModel):
    session_id: str
    rows: list[dict[str, Any]] = []
    columns: list[str] = []
    row_count: int = 0
    execution_ms: float = 0.0
    is_mock: bool = False


# ============================================================
# 阶段 6: 测试验证
# ============================================================


class TestReconInput(BaseModel):
    session_id: str
    source_table: str
    target_table: str
    join_keys: list[str] = []


class TestReconOutput(BaseModel):
    session_id: str
    sql: str
    description: str = ""


class TestEdgeInput(BaseModel):
    session_id: str
    target_table: str
    scenario: str = "null_and_duplicate"


class TestEdgeOutput(BaseModel):
    session_id: str
    sql: str
    description: str = ""


class TestPerformanceInput(BaseModel):
    session_id: str
    target_table: str


class TestPerformanceOutput(BaseModel):
    session_id: str
    sql: str
    description: str = ""


class MockDataInput(BaseModel):
    session_id: str
    target_table: str
    row_count: int = 100
    seed: int = 42


class MockDataOutput(BaseModel):
    session_id: str
    sql: str  # 生成的 INSERT 语句 (含 MOCK_DATA 标注)
    mock_rows: int
    is_mock: bool = True


class RunTestsInput(BaseModel):
    session_id: str
    target_table: str
    include_recon: bool = True
    include_edge: bool = True
    include_performance: bool = True
    use_mock_data: bool = True


class TestReportDimension(BaseModel):
    name: str
    score: float
    passed: bool
    notes: str = ""
    details: list[dict[str, Any]] = []


class TestReport(BaseModel):
    session_id: str
    target_table: str
    overall_passed: bool
    accuracy: TestReportDimension
    completeness: TestReportDimension
    consistency: TestReportDimension
    performance: TestReportDimension
    generated_at: str = ""
    is_mock: bool = False
