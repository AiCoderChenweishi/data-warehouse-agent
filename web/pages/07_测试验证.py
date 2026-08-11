"""阶段 7: 测试验证

对账 SQL / 边界用例 / 性能基线
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import streamlit as st
from app import api_post, mark_completed, init_session

init_session()

st.title("✅ 阶段 6 — 测试验证")
st.caption("对账 / 边界 / 性能,确保数据准确 + 完整 + 一致")

table_name = st.text_input("目标表", value="dws_trade_order_pay_1d")
source_table = st.text_input("源表 (业务系统, 用于对账)", value="ods_trade_order")

# 1. Mock 数据
st.subheader("🎲 1. 生成 mock 测试数据")
st.caption("# MOCK_DATA: 本节数据由 mock-data API 生成,USER 已明确允许")
mock_rows = st.number_input("行数", min_value=10, max_value=10000, value=200, step=10)
if st.button("生成 mock 数据"):
    with st.spinner("生成..."):
        r = api_post("/api/testing/mock-data", {
            "session_id": st.session_state.session_id,
            "table_name": table_name,
            "rows": int(mock_rows),
        })
    if r["ok"]:
        st.success(f"✅ 生成 {r['data'].get('row_count', mock_rows)} 行 mock 数据")
        st.json(r["data"])
        st.session_state.mock_ready = True
    else:
        st.error(r["error"])

# 2. 对账 SQL
st.divider()
st.subheader("🔍 2. 对账 SQL (业务源 vs 数仓)")
if st.button("生成对账 SQL"):
    with st.spinner("..."):
        r = api_post("/api/testing/recon", {
            "session_id": st.session_state.session_id,
            "source_table": source_table,
            "target_table": table_name,
        })
    if r["ok"]:
        st.code(r["data"].get("sql", ""), language="sql")
        st.session_state.recon_sql = r["data"].get("sql", "")
    else:
        st.error(r["error"])

# 3. 边界用例
st.divider()
st.subheader("🧪 3. 边界用例 (空/脏/跨周期)")
if st.button("生成边界用例"):
    with st.spinner("..."):
        r = api_post("/api/testing/edge", {
            "session_id": st.session_state.session_id,
            "table_name": table_name,
        })
    if r["ok"]:
        st.code(r["data"].get("sql", ""), language="sql")
    else:
        st.error(r["error"])

# 4. 性能
st.divider()
st.subheader("⚡ 4. 性能基线")
if st.button("生成性能 SQL"):
    with st.spinner("..."):
        r = api_post("/api/testing/performance", {
            "session_id": st.session_state.session_id,
            "table_name": table_name,
        })
    if r["ok"]:
        st.code(r["data"].get("sql", ""), language="sql")
    else:
        st.error(r["error"])

# 5. 跑测试
st.divider()
st.subheader("🚀 5. 跑全部测试")
if st.button("跑测试 + 出报告", type="primary"):
    with st.spinner("执行中...", ):
        r = api_post("/api/testing/run", {
            "session_id": st.session_state.session_id,
            "target_table": table_name,
            "source_table": source_table,
        }, timeout=120)
    if r["ok"]:
        st.session_state.stage_outputs["06_测试验证"] = r["data"]
        st.success("✅ 测试完成!")
        st.json(r["data"])

        # 4 维度展示
        if "report" in r["data"]:
            rep = r["data"]["report"]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("准确性", rep.get("accuracy", "—"))
            c2.metric("完整性", rep.get("completeness", "—"))
            c3.metric("一致性", rep.get("consistency", "—"))
            c4.metric("性能", rep.get("performance", "—"))

        st.download_button(
            "📥 下载测试报告",
            data=str(r["data"]),
            file_name="test_report.md",
            mime="text/markdown",
        )
    else:
        st.error(r["error"])

if st.session_state.get("stage_outputs", {}).get("06_测试验证"):
    st.balloons()
    if st.button("🎉 收工!所有阶段完成!"):
        mark_completed(7)
