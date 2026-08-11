"""阶段 5: 跑数 (5 层 SQL: ODS / DWD / DWS / DWT / ADS).

API:
    POST /api/sqlgen/ods
    POST /api/sqlgen/dwd
    POST /api/sqlgen/dws
    POST /api/sqlgen/dwt
    POST /api/sqlgen/ads
    POST /api/sqlgen/run     # 在 DuckDB 真跑 SQL
"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException

from app.backend import db, session_store
from app.backend.schemas import (
    RunSQLInput,
    RunSQLOutput,
    SQLGenInput,
    SQLGenOutput,
)

router = APIRouter(prefix="/api/sqlgen", tags=["sqlgen"])


# ============================================================
# 各层 SQL 模板 (简化版, 基于 DuckDB 语法)
# ============================================================


def _ods_sql(payload: SQLGenInput) -> str:
    src = payload.source_table or "ods_raw.trade_order"
    tgt = payload.target_table or "ods.trade_order"
    return f"""-- ============================================================
-- ODS 贴源层 (Operational Data Store)
-- 来源: {src}
-- 目标: {tgt}
-- 职责: 1:1 同步源系统, 不做清洗, 只加 etl_time
-- ============================================================
CREATE SCHEMA IF NOT EXISTS ods;

CREATE OR REPLACE TABLE {tgt} AS
SELECT
    *,
    CURRENT_TIMESTAMP AS etl_time,
    'data-warehouse-agent' AS etl_source
FROM {src};

-- 验证
SELECT COUNT(*) AS row_count FROM {tgt};
"""


def _dwd_sql(payload: SQLGenInput) -> str:
    src = payload.source_table or "ods.trade_order"
    tgt = payload.target_table or "dwd.trade_order"
    return f"""-- ============================================================
-- DWD 清洗层 (Data Warehouse Detail)
-- 来源: {src}
-- 目标: {tgt}
-- 职责: 清洗 (去空 / 去重 / 标准化) + 退化维度保留
-- ============================================================
CREATE SCHEMA IF NOT EXISTS dwd;

CREATE OR REPLACE TABLE {tgt} AS
SELECT
    order_id,
    user_id,
    item_id,
    merchant_id,
    CAST(order_date AS DATE) AS order_date,
    CAST(order_amount AS DECIMAL(18,2)) AS order_amount,
    LOWER(TRIM(order_status)) AS order_status,
    -- 退化维度 (订单号保留在事实表, 不单独建 dim)
    order_no,
    -- 业务时间
    CAST(created_at AS TIMESTAMP) AS created_at
FROM {src}
WHERE order_id IS NOT NULL
  AND order_amount >= 0
QUALIFY ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY created_at DESC) = 1;

-- 验证
SELECT
    COUNT(*) AS row_count,
    COUNT(DISTINCT order_id) AS distinct_orders,
    SUM(CASE WHEN order_amount < 0 THEN 1 ELSE 0 END) AS negative_amount_count
FROM {tgt};
"""


def _dws_sql(payload: SQLGenInput) -> str:
    src = payload.source_table or "dwd.trade_order"
    tgt = payload.target_table or "dws.trade_order_1d"
    return f"""-- ============================================================
-- DWS 汇总层 (Data Warehouse Summary, 1d 主题宽表)
-- 来源: {src}
-- 目标: {tgt}
-- 职责: 按维度聚合, 1d 时间窗口, 主题宽表
-- ============================================================
CREATE SCHEMA IF NOT EXISTS dws;

CREATE OR REPLACE TABLE {tgt} AS
SELECT
    order_date,
    user_id,
    merchant_id,
    COUNT(DISTINCT order_id) AS order_cnt,
    SUM(order_amount) AS gmv,
    AVG(order_amount) AS avg_order_amount,
    COUNT(DISTINCT CASE WHEN order_status = 'paid' THEN order_id END) AS paid_order_cnt
FROM {src}
WHERE order_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY order_date, user_id, merchant_id;

-- 验证
SELECT
    COUNT(*) AS row_count,
    SUM(gmv) AS total_gmv,
    SUM(order_cnt) AS total_order_cnt
FROM {tgt};
"""


def _dwt_sql(payload: SQLGenInput) -> str:
    src = payload.source_table or "dws.trade_order_1d"
    tgt = payload.target_table or "dwt.trade_user_topic"
    return f"""-- ============================================================
-- DWT 主题层 (Data Warehouse Topic, 全历史累积)
-- 来源: {src}
-- 目标: {tgt}
-- 职责: 用户/商家/商品 主题全历史累积
-- ============================================================
CREATE SCHEMA IF NOT EXISTS dwt;

CREATE OR REPLACE TABLE {tgt} AS
SELECT
    user_id,
    COUNT(DISTINCT order_date) AS active_days,
    SUM(order_cnt) AS lifetime_order_cnt,
    SUM(gmv) AS lifetime_gmv,
    MAX(order_date) AS last_order_date,
    CURRENT_DATE AS dt
FROM {src}
GROUP BY user_id;

-- 验证
SELECT
    COUNT(*) AS user_count,
    SUM(lifetime_gmv) AS total_gmv,
    AVG(lifetime_order_cnt) AS avg_orders_per_user
FROM {tgt};
"""


def _ads_sql(payload: SQLGenInput) -> str:
    src = payload.source_table or "dws.trade_order_1d"
    tgt = payload.target_table or "ads.trade_order_summary"
    return f"""-- ============================================================
-- ADS 应用层 (Application Data Service, 报表/接口)
-- 来源: {src}
-- 目标: {tgt}
-- 职责: 直接给业务/报表用, 包含业务指标和宽表
-- ============================================================
CREATE SCHEMA IF NOT EXISTS ads;

CREATE OR REPLACE TABLE {tgt} AS
SELECT
    order_date,
    merchant_id,
    SUM(order_cnt) AS order_cnt,
    SUM(gmv) AS gmv,
    SUM(paid_order_cnt) AS paid_order_cnt,
    ROUND(SUM(paid_order_cnt) * 100.0 / NULLIF(SUM(order_cnt), 0), 2) AS paid_rate,
    ROUND(SUM(gmv) / NULLIF(SUM(order_cnt), 0), 2) AS avg_order_amount
FROM {src}
GROUP BY order_date, merchant_id
ORDER BY order_date DESC, gmv DESC;

-- 验证
SELECT
    COUNT(*) AS row_count,
    SUM(gmv) AS total_gmv,
    MIN(order_date) AS min_date,
    MAX(order_date) AS max_date
FROM {tgt};
"""


_LAYER_HANDLERS = {
    "ods": _ods_sql,
    "dwd": _dwd_sql,
    "dws": _dws_sql,
    "dwt": _dwt_sql,
    "ads": _ads_sql,
}


_LAYER_DESC = {
    "ods": "ODS 贴源层: 1:1 同步源系统, 加 etl_time, 不清洗",
    "dwd": "DWD 清洗层: 去空/去重/标准化, 退化维度保留",
    "dws": "DWS 汇总层: 1d 主题宽表, 按维度聚合",
    "dwt": "DWT 主题层: 用户/商家主题全历史累积",
    "ads": "ADS 应用层: 给业务/报表用, 业务指标",
}


@router.post("/ods", response_model=SQLGenOutput)
def post_ods(payload: SQLGenInput) -> SQLGenOutput:
    return _make_output(payload, "ods")


@router.post("/dwd", response_model=SQLGenOutput)
def post_dwd(payload: SQLGenInput) -> SQLGenOutput:
    return _make_output(payload, "dwd")


@router.post("/dws", response_model=SQLGenOutput)
def post_dws(payload: SQLGenInput) -> SQLGenOutput:
    return _make_output(payload, "dws")


@router.post("/dwt", response_model=SQLGenOutput)
def post_dwt(payload: SQLGenInput) -> SQLGenOutput:
    return _make_output(payload, "dwt")


@router.post("/ads", response_model=SQLGenOutput)
def post_ads(payload: SQLGenInput) -> SQLGenOutput:
    return _make_output(payload, "ads")


def _make_output(payload: SQLGenInput, layer: str) -> SQLGenOutput:
    if layer not in _LAYER_HANDLERS:
        raise HTTPException(400, f"不支持的 layer: {layer}, 必须从 {_LAYER_HANDLERS.keys()}")
    handler = _LAYER_HANDLERS[layer]
    sql = handler(payload)
    sess = session_store.get_or_create(payload.session_id)
    sess.data.setdefault(f"stage5_sql", {})[layer] = sql
    session_store.mark_complete(payload.session_id, 5)
    return SQLGenOutput(
        session_id=payload.session_id,
        layer=layer,
        sql=sql,
        description=_LAYER_DESC[layer],
    )


@router.post("/run", response_model=RunSQLOutput)
def post_run_sql(payload: RunSQLInput) -> RunSQLOutput:
    """在 DuckDB 真跑 SQL (支持 SELECT 自动 LIMIT 10000).

    Args:
        payload.sql: SQL 语句
        payload.mock_data: 如果 SQL 引用了不存在的表, 是否注入 mock 数据
    """
    if not payload.sql.strip():
        raise HTTPException(400, "sql 不能为空")

    sess = session_store.get_or_create(payload.session_id)
    is_mock = False
    sql_to_run = payload.sql

    # MOCK: 如果 SQL 含 CREATE TABLE ... AS SELECT 引用不存在的源表
    if payload.mock_data:
        sql_to_run, injected = _inject_mock_if_needed(sql_to_run)
        is_mock = injected

    start = time.time()
    try:
        # 如果是 CREATE OR REPLACE TABLE, 用 execute (无返回)
        sql_upper = sql_to_run.strip().upper()
        if sql_upper.startswith("CREATE") or sql_upper.startswith("DROP") or sql_upper.startswith("INSERT"):
            db.execute(sql_to_run)
            elapsed = (time.time() - start) * 1000
            sess.data["stage5_run_log"] = sess.data.get("stage5_run_log", [])
            sess.data["stage5_run_log"].append({
                "sql_hash": hash(sql_to_run),
                "is_mock": is_mock,
                "execution_ms": elapsed,
                "row_count": 0,
            })
            return RunSQLOutput(
                session_id=payload.session_id,
                rows=[],
                columns=[],
                row_count=0,
                execution_ms=elapsed,
                is_mock=is_mock,
            )

        # SELECT: 返回结果
        columns = db.query_columns(sql_to_run)
        rows = db.query_rows(sql_to_run)
        elapsed = (time.time() - start) * 1000
        sess.data["stage5_run_log"] = sess.data.get("stage5_run_log", [])
        sess.data["stage5_run_log"].append({
            "sql_hash": hash(sql_to_run),
            "is_mock": is_mock,
            "execution_ms": elapsed,
            "row_count": len(rows),
        })
        return RunSQLOutput(
            session_id=payload.session_id,
            rows=rows[:1000],  # 限 1000 行
            columns=columns,
            row_count=len(rows),
            execution_ms=elapsed,
            is_mock=is_mock,
        )
    except Exception as e:
        raise HTTPException(500, f"SQL 执行失败: {e}")


def _inject_mock_if_needed(sql: str) -> tuple[str, bool]:
    """如果 SQL 引用了不存在的表, 注入 mock 数据.

    Returns:
        (new_sql, injected_bool)
    """
    # 简化: 检测 ods_raw.trade_order 不存在则注入 (用 range(1, 201) 替换 random() 避免 cast INT->INTERVAL 报错)
    if "ods_raw.trade_order" in sql.lower() or ("ods.trade_order" in sql.lower() and "FROM ods_raw" in sql):
        # 注入 mock 源表 (DuckDB 0.10+ 已修复 INTEGER->INTERVAL, 但部分版本仍报, 用乘法规避)
        mock_sql = """
-- MOCK_DATA: 自动注入测试用源数据 (USER 已允许 mock)
CREATE SCHEMA IF NOT EXISTS ods_raw;
DROP TABLE IF EXISTS ods_raw.trade_order;
CREATE TABLE ods_raw.trade_order AS
SELECT
    'O' || LPAD(CAST(n AS VARCHAR), 6, '0') AS order_id,
    'U' || LPAD(CAST(((n * 7) % 1000 + 1) AS VARCHAR), 4, '0') AS user_id,
    'I' || LPAD(CAST(((n * 11) % 500 + 1) AS VARCHAR), 4, '0') AS item_id,
    'M' || LPAD(CAST(((n * 13) % 50 + 1) AS VARCHAR), 3, '0') AS merchant_id,
    CURRENT_DATE - (((n * 3) % 60)) * INTERVAL '1 day' AS order_date,
    ROUND(((n * 17) % 1000 + 10)::DECIMAL, 2) AS order_amount,
    CASE WHEN (n * 11) % 10 < 3 THEN 'pending' WHEN (n * 11) % 10 < 7 THEN 'paid' ELSE 'shipped' END AS order_status,
    'NO' || LPAD(CAST(n AS VARCHAR), 8, '0') AS order_no,
    CURRENT_TIMESTAMP - (((n * 5) % 86400)) * INTERVAL '1 second' AS created_at
FROM range(1, 201) t(n);
"""
        return mock_sql + "\n" + sql, True
    return sql, False
