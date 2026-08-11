"""DuckDB 连接管理 (单例模式).

- 启动时初始化 db 目录
- 暴露 get_conn() / execute() / query_rows() / query_one()
- 同时支持内存模式 (测试) 和持久化文件模式 (生产)
- 不依赖 pandas, 直接用 duckdb 的 fetchall
"""
from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import duckdb

# 全局配置
DB_PATH = os.environ.get("WAREHOUSE_DB_PATH", "./db/warehouse.duckdb")
DB_MODE = os.environ.get("WAREHOUSE_DB_MODE", "file")  # "file" | "memory"


def _ensure_db_dir() -> None:
    """确保 db 目录存在 (file 模式下)."""
    if DB_MODE == "file":
        path = Path(DB_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)


_conn: Optional[duckdb.DuckDBPyConnection] = None


def get_conn() -> duckdb.DuckDBPyConnection:
    """获取 DuckDB 单例连接."""
    global _conn
    if _conn is None:
        _ensure_db_dir()
        if DB_MODE == "memory":
            _conn = duckdb.connect(":memory:")
        else:
            _conn = duckdb.connect(DB_PATH)
    return _conn


def _normalize_value(v: Any) -> Any:
    """把 DuckDB 返回的特殊类型 (Decimal / date / datetime) 转成可 JSON 序列化的值."""
    if v is None:
        return None
    # Decimal
    if hasattr(v, "as_tuple"):  # Decimal
        return float(v)
    # date / datetime
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    # numpy 标量
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            pass
    return v


def execute(sql: str, params: Optional[list[Any]] = None) -> None:
    """执行 SQL (无返回)."""
    conn = get_conn()
    if params:
        conn.execute(sql, params)
    else:
        conn.execute(sql)


def query_one(sql: str, params: Optional[list[Any]] = None) -> Optional[dict[str, Any]]:
    """查询单行, 返回 dict (无行返回 None)."""
    conn = get_conn()
    rel = conn.execute(sql, params) if params else conn.execute(sql)
    row = rel.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in rel.description]
    return {c: _normalize_value(v) for c, v in zip(cols, row)}


def query_rows(sql: str, params: Optional[list[Any]] = None) -> list[dict[str, Any]]:
    """查询多行, 返回 list[dict] (供 API 序列化)."""
    conn = get_conn()
    rel = conn.execute(sql, params) if params else conn.execute(sql)
    cols = [d[0] for d in rel.description]
    rows = rel.fetchall()
    return [{c: _normalize_value(v) for c, v in zip(cols, row)} for row in rows]


def query_columns(sql: str, params: Optional[list[Any]] = None) -> list[str]:
    """查询列名."""
    conn = get_conn()
    rel = conn.execute(sql, params) if params else conn.execute(sql)
    return [d[0] for d in rel.description]


def reset() -> None:
    """重置连接 (测试用)."""
    global _conn
    if _conn is not None:
        try:
            _conn.close()
        except Exception:
            pass
        _conn = None
