"""数仓开发 Agent - FastAPI 后端 (Web + DuckDB).

模块:
    main     - FastAPI app 入口
    db       - DuckDB 连接管理
    schemas  - Pydantic 请求/响应模型
    api      - 6 阶段 REST API (requirements/architecture/modeling/sqlgen/testing)
    sql_templates - Jinja2 SQL 模板 (DDL/ETL)

调用示例:
    >>> uvicorn app.backend.main:app --reload --port 8000
"""

__version__ = "0.1.0"
