"""阶段 5: 跑数 — 5 层 ETL SQL 生成

ODS / DWD / DWS / DWT / ADS
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import streamlit as st
from app import api_post, mark_completed, init_session

init_session()

st.title("🏃 阶段 5 — 跑数 (5 层 ETL)")
st.caption("基于模型设计自动生成各层 SQL")

# 拿上一阶段 DDL
prev_ddl = st.session_state.get("modeling", {}).get("ddl", {}).get("ddl", "")
if not prev_ddl:
    st.warning("⚠️ 请先完成阶段 4 模型设计")

table_name = st.text_input("目标表名 (DWS / ADS 之类)", value="dws_trade_order_pay_1d")
source_table = st.text_input("源表 (ODS / DWD 之类)", value="ods_trade_order")
fact_type = st.selectbox("事实表类型", ["transaction", "periodic_snapshot", "accumulating_snapshot"])

layers = ["ods", "dwd", "dws", "dwt", "ads"]
tabs = st.tabs([f"📦 {l.upper()}" for l in layers])

for layer, tab in zip(layers, tabs):
    with tab:
        st.subheader(f"{layer.upper()} 层 SQL")
        if st.button(f"生成 {layer.upper()} SQL", key=f"gen_{layer}"):
            with st.spinner(f"生成 {layer} SQL..."):
                r = api_post(f"/api/sqlgen/{layer}", {
                    "session_id": st.session_state.session_id,
                    "source_table": source_table,
                    "target_table": table_name,
                    "fact_type": fact_type,
                })
            if r["ok"]:
                sql = r["data"].get("sql", "")
                st.code(sql, language="sql")
                st.download_button(
                    f"📥 下载 {layer}.sql",
                    data=sql,
                    file_name=f"{layer}_{table_name}.sql",
                    mime="text/plain",
                    key=f"dl_{layer}",
                )
                st.session_state.stage_outputs[f"05_{layer}"] = sql
            else:
                st.error(r["error"])

# 实际跑
st.divider()
st.subheader("▶️ 在 DuckDB 真跑")
if st.button("跑 SQL (创建表+插 mock)"):
    with st.spinner("执行中..."):
        r = api_post("/api/sqlgen/run", {
            "session_id": st.session_state.session_id,
            "target_table": table_name,
        }, timeout=120)
    if r["ok"]:
        st.success("✅ 跑通!")
        st.json(r["data"])
    else:
        st.error(r["error"])

if st.button("完成本阶段, 进入下一阶段 →"):
    mark_completed(6)
