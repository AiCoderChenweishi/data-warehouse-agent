"""FastAPI app 入口.

启动: uvicorn app.backend.main:app --port 8000
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.backend import db
from app.backend.api import architecture, modeling, requirements, sqlgen, testing
from app.backend.schemas import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    Path("./db").mkdir(exist_ok=True)
    try:
        conn = db.get_conn()
        # 简单 smoke
        conn.execute("SELECT 1").fetchall()
    except Exception as e:
        print(f"[startup] DB init failed: {e}")
    yield
    # 关闭
    db.reset()


app = FastAPI(
    title="数仓开发 Agent API",
    description="7 阶段引导式数仓搭建 (业务调研 → 测试验证)",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由
app.include_router(requirements.router)
app.include_router(architecture.router)
app.include_router(modeling.router)
app.include_router(sqlgen.router)
app.include_router(testing.router)


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version="0.1.0",
        db_mode=os.environ.get("WAREHOUSE_DB_MODE", "file"),
    )


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "name": "数仓开发 Agent",
        "version": "0.1.0",
        "endpoints": [
            "/health",
            "/api/requirements/business",
            "/api/requirements/metrics",
            "/api/architecture/domains",
            "/api/architecture/bus-matrix",
            "/api/architecture/naming",
            "/api/architecture/metric-dict",
            "/api/modeling/business-process",
            "/api/modeling/grain",
            "/api/modeling/dimensions",
            "/api/modeling/facts",
            "/api/modeling/fact-type",
            "/api/modeling/ddl",
            "/api/sqlgen/{ods,dwd,dws,dwt,ads}",
            "/api/sqlgen/run",
            "/api/testing/{recon,edge,performance,mock-data,run}",
        ],
    }
