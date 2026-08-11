"""Backend API 测试 (用 httpx.AsyncClient).

至少 1 个端到端测试: 从 '我要建订单事实表' → 走完 6 阶段 → DuckDB 真建表 + 跑 ETL + 验证.
"""
from __future__ import annotations

import os

# 测试用内存 DuckDB
os.environ["WAREHOUSE_DB_MODE"] = "memory"

import pytest
from fastapi.testclient import TestClient

from app.backend.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ============================================================
# /health
# ============================================================


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert "name" in data


# ============================================================
# 阶段 0-1 调研
# ============================================================


def test_requirements_business(client):
    r = client.post("/api/requirements/business", json={
        "session_id": "test-1",
        "business_name": "电商订单",
        "functional_modules": ["订单", "商品", "用户"],
        "user_roles": ["买家", "卖家", "运营"],
    })
    assert r.status_code == 200
    data = r.json()
    assert data["business_name"] == "电商订单"
    assert len(data["matrix"]) >= 3  # 至少 3 行


def test_requirements_metrics(client):
    r = client.post("/api/requirements/metrics", json={
        "session_id": "test-1",
        "metrics": ["GMV", "订单数", "客单价"],
        "dimensions": ["用户", "商品", "时间"],
        "data_sources": ["mysql.orders", "kafka.click_log"],
    })
    assert r.status_code == 200
    data = r.json()
    assert len(data["metrics_list"]) == 3
    assert len(data["dimensions_list"]) == 3
    assert len(data["data_sources_list"]) == 2


# ============================================================
# 阶段 2-3 架构/规范
# ============================================================


def test_architecture_domains(client):
    r = client.post("/api/architecture/domains", json={
        "session_id": "test-1",
        "business": "电商",
        "functional_modules": ["订单", "商品", "用户"],
    })
    assert r.status_code == 200
    data = r.json()
    assert "primary_domain" in data
    assert "module_to_domain" in data


def test_architecture_bus_matrix(client):
    r = client.post("/api/architecture/bus-matrix", json={
        "session_id": "test-1",
        "domain": "trade",
        "business_processes": ["下单", "支付", "发货", "收货"],
        "dimensions": ["用户", "商品", "时间", "商家", "支付方式"],
    })
    assert r.status_code == 200
    data = r.json()
    assert "下单" in data["matrix"]
    assert "用户" in data["shared_dimensions"]


def test_architecture_naming(client):
    r = client.post("/api/architecture/naming", json={
        "session_id": "test-1",
        "layer": "dws",
        "domain": "trade",
        "business": "order",
        "modifier": "pay",
        "period": "1d",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["table_name"] == "dws_trade_order_pay_1d"


def test_architecture_metric_dict(client):
    r = client.post("/api/architecture/metric-dict", json={
        "session_id": "test-1",
        "atomic_name": "订单数",
        "business_process": "下单",
        "aggregation": "count",
        "measure_field": "order_id",
        "unit": "个",
        "description": "下单数",
        "derived_modifiers": ["最近", "最近7天"],
    })
    assert r.status_code == 200
    data = r.json()
    assert data["atomic"]["name"] == "订单数"
    assert len(data["derived"]) >= 1


# ============================================================
# 阶段 4 模型设计 (Kimball 4 步法)
# ============================================================


def test_modeling_business_process(client):
    r = client.post("/api/modeling/business-process", json={
        "session_id": "test-1",
        "business_description": "用户在下单后,会经历支付、发货、收货",
    })
    assert r.status_code == 200
    data = r.json()
    assert len(data["processes"]) >= 3


def test_modeling_grain(client):
    r = client.post("/api/modeling/grain", json={
        "session_id": "test-1",
        "business_process": "子订单",
    })
    assert r.status_code == 200
    data = r.json()
    assert "grain" in data


def test_modeling_dimensions(client):
    r = client.post("/api/modeling/dimensions", json={
        "session_id": "test-1",
        "business_process": "订单",
        "grain": "子订单",
    })
    assert r.status_code == 200
    data = r.json()
    assert len(data["dimensions"]) >= 1


def test_modeling_facts(client):
    r = client.post("/api/modeling/facts", json={
        "session_id": "test-1",
        "business_process": "订单",
        "grain": "子订单",
        "dimensions": [{"name": "用户", "role": "primary", "attributes": ["用户ID"]}],
    })
    assert r.status_code == 200
    data = r.json()
    assert len(data["facts"]) >= 1


def test_modeling_fact_type(client):
    r = client.post("/api/modeling/fact-type", json={
        "session_id": "test-1",
        "business_processes": ["下单", "支付", "发货", "收货"],
        "has_time_intervals": True,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["fact_type"] in ("transaction", "periodic_snapshot", "accumulating_snapshot")


def test_modeling_ddl(client):
    r = client.post("/api/modeling/ddl", json={
        "session_id": "test-1",
        "fact_type": "accumulating_snapshot",
        "fact_table_name": "fact_order_acc",
        "business_process": "订单",
        "grain": "子订单",
        "dimensions": [
            {"name": "用户", "role": "primary", "attributes": ["用户ID", "用户类型"]},
            {"name": "商品", "role": "primary", "attributes": ["商品ID", "商品名称"]},
        ],
        "facts": [
            {"name": "金额", "additivity": "additive", "data_type": "DECIMAL(18,2)"},
            {"name": "数量", "additivity": "additive", "data_type": "BIGINT"},
        ],
    })
    assert r.status_code == 200
    data = r.json()
    assert "CREATE TABLE" in data["ddl"]
    assert "fact_order_acc" in data["ddl"]


# ============================================================
# 阶段 5 跑数
# ============================================================


def test_sqlgen_5_layers(client):
    for layer in ["ods", "dwd", "dws", "dwt", "ads"]:
        r = client.post(f"/api/sqlgen/{layer}", json={
            "session_id": "test-1",
            "layer": layer,
            "source_table": "ods_raw.trade_order",
            "target_table": f"{layer}.trade_order",
        })
        assert r.status_code == 200, f"{layer} failed: {r.text}"
        data = r.json()
        assert "CREATE" in data["sql"].upper()


def test_sqlgen_run_with_mock(client):
    r = client.post("/api/sqlgen/run", json={
        "session_id": "test-1",
        "sql": "CREATE SCHEMA IF NOT EXISTS ods_raw; CREATE TABLE ods_raw.trade_order AS SELECT 1 AS order_id, 100.0 AS order_amount, CURRENT_DATE AS order_date;",
        "mock_data": False,
    })
    assert r.status_code == 200, f"failed: {r.text}"


def test_sqlgen_run_select_with_mock_inject(client):
    """跑含 ods_raw.trade_order 引用的 SQL, 应该自动注入 mock."""
    r = client.post("/api/sqlgen/run", json={
        "session_id": "test-1",
        "sql": "SELECT COUNT(*) AS c FROM ods_raw.trade_order",
        "mock_data": True,
    })
    assert r.status_code == 200, f"failed: {r.text}"
    data = r.json()
    assert data["is_mock"] is True
    assert data["row_count"] >= 1


# ============================================================
# 阶段 6 测试
# ============================================================


def test_testing_recon(client):
    r = client.post("/api/testing/recon", json={
        "session_id": "test-1",
        "source_table": "ods_raw.trade_order",
        "target_table": "dwd.trade_order",
        "join_keys": ["order_id"],
    })
    assert r.status_code == 200
    data = r.json()
    assert "SELECT" in data["sql"].upper()


def test_testing_edge(client):
    r = client.post("/api/testing/edge", json={
        "session_id": "test-1",
        "target_table": "dwd.trade_order",
    })
    assert r.status_code == 200
    data = r.json()
    assert "NULL" in data["sql"].upper()


def test_testing_performance(client):
    r = client.post("/api/testing/performance", json={
        "session_id": "test-1",
        "target_table": "dwd.trade_order",
    })
    assert r.status_code == 200
    data = r.json()
    assert "EXPLAIN" in data["sql"].upper()


def test_testing_mock_data(client):
    r = client.post("/api/testing/mock-data", json={
        "session_id": "test-1",
        "target_table": "ods_raw.trade_order",
        "row_count": 50,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["is_mock"] is True
    assert "MOCK_DATA" in data["sql"]


# ============================================================
# 端到端: 走完 6 阶段
# ============================================================


def test_e2e_order_fact(client):
    """端到端: '我要建订单事实表' → 走完 6 阶段 → DuckDB 真建表 + 跑 ETL."""
    sid = "e2e-order"

    # 阶段 0: 业务调研
    r = client.post("/api/requirements/business", json={
        "session_id": sid,
        "business_name": "电商订单",
        "functional_modules": ["订单", "商品", "用户"],
        "user_roles": ["买家", "卖家"],
    })
    assert r.status_code == 200

    # 阶段 1: 需求调研
    r = client.post("/api/requirements/metrics", json={
        "session_id": sid,
        "metrics": ["GMV", "订单数"],
        "dimensions": ["用户", "商品", "时间"],
        "data_sources": ["mysql.orders"],
    })
    assert r.status_code == 200

    # 阶段 2: 架构
    r = client.post("/api/architecture/domains", json={
        "session_id": sid,
        "business": "电商",
        "functional_modules": ["订单", "商品", "用户"],
    })
    assert r.status_code == 200

    r = client.post("/api/architecture/bus-matrix", json={
        "session_id": sid,
        "domain": "trade",
        "business_processes": ["下单", "支付", "发货", "收货"],
        "dimensions": ["用户", "商品", "时间", "商家"],
    })
    assert r.status_code == 200

    # 阶段 3: 规范
    r = client.post("/api/architecture/naming", json={
        "session_id": sid,
        "layer": "dws",
        "domain": "trade",
        "business": "order",
        "modifier": "pay",
        "period": "1d",
    })
    assert r.status_code == 200
    assert r.json()["table_name"] == "dws_trade_order_pay_1d"

    r = client.post("/api/architecture/metric-dict", json={
        "session_id": sid,
        "atomic_name": "订单数",
        "business_process": "下单",
        "aggregation": "count",
        "measure_field": "order_id",
        "derived_modifiers": ["最近", "最近7天"],
    })
    assert r.status_code == 200

    # 阶段 4: Kimball 4 步法
    r = client.post("/api/modeling/business-process", json={
        "session_id": sid,
        "business_description": "用户在下单后,会经历支付、发货、收货",
    })
    assert r.status_code == 200
    processes = [p["name"] for p in r.json()["processes"]]
    assert len(processes) >= 3

    r = client.post("/api/modeling/grain", json={
        "session_id": sid,
        "business_process": processes[0],
    })
    assert r.status_code == 200

    r = client.post("/api/modeling/dimensions", json={
        "session_id": sid,
        "business_process": "订单",
        "grain": "子订单",
    })
    assert r.status_code == 200
    dims = r.json()["dimensions"]

    r = client.post("/api/modeling/facts", json={
        "session_id": sid,
        "business_process": "订单",
        "grain": "子订单",
        "dimensions": dims,
    })
    assert r.status_code == 200
    facts = r.json()["facts"]

    r = client.post("/api/modeling/fact-type", json={
        "session_id": sid,
        "business_processes": processes[:4],
        "has_time_intervals": True,
    })
    assert r.status_code == 200
    fact_type = r.json()["fact_type"]

    r = client.post("/api/modeling/ddl", json={
        "session_id": sid,
        "fact_type": fact_type,
        "fact_table_name": "fact_order_acc",
        "business_process": "订单",
        "grain": "子订单",
        "dimensions": dims,
        "facts": facts,
    })
    assert r.status_code == 200
    ddl = r.json()["ddl"]

    # 真在 DuckDB 跑 DDL
    r = client.post("/api/sqlgen/run", json={
        "session_id": sid,
        "sql": ddl,
        "mock_data": False,
    })
    assert r.status_code == 200, f"DDL 执行失败: {r.text}"

    # 阶段 5: 跑 5 层 SQL (每层自动注入 mock 源数据)
    # 5 层表名: ods_raw -> ods -> dwd -> dws -> dwt -> ads
    layer_chain = [
        ("ods", "ods_raw.trade_order", "ods.trade_order"),
        ("dwd", "ods.trade_order", "dwd.trade_order"),
        ("dws", "dwd.trade_order", "dws.trade_order_1d"),
        ("dwt", "dws.trade_order_1d", "dwt.trade_user_topic"),
        ("ads", "dws.trade_order_1d", "ads.trade_order_summary"),
    ]
    for layer, src, tgt in layer_chain:
        r = client.post(f"/api/sqlgen/{layer}", json={
            "session_id": sid,
            "layer": layer,
            "source_table": src,
            "target_table": tgt,
        })
        assert r.status_code == 200
        sql = r.json()["sql"]

        r = client.post("/api/sqlgen/run", json={
            "session_id": sid,
            "sql": sql,
            "mock_data": (layer == "ods"),  # 只在 ODS 层注入 mock
        })
        assert r.status_code == 200, f"{layer} 执行失败: {r.text}"

    # 阶段 6: 测试
    r = client.post("/api/testing/mock-data", json={
        "session_id": sid,
        "target_table": "ods_raw.trade_order",
        "row_count": 100,
    })
    assert r.status_code == 200
    r = client.post("/api/sqlgen/run", json={
        "session_id": sid,
        "sql": r.json()["sql"],
        "mock_data": False,
    })
    assert r.status_code == 200

    r = client.post("/api/testing/run", json={
        "session_id": sid,
        "target_table": "dwd.trade_order",
        "use_mock_data": True,
    })
    assert r.status_code == 200, f"test run failed: {r.text}"
    report = r.json()
    assert "accuracy" in report
    assert "completeness" in report
    assert "consistency" in report
    assert "performance" in report
