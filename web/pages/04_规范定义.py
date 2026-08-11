"""阶段 3: 规范定义

目标: 表命名 + 指标字典
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import streamlit as st
from app import api_post, mark_completed, init_session

init_session()

st.title("📐 阶段 3 — 规范定义")
st.caption("表命名规范 + 指标字典 (原子指标 + 派生指标)")

col1, col2 = st.columns(2)

with col1:
    st.subheader("🏷️ 表命名生成")
    domain = st.text_input("数据域", value="trade")
    business = st.text_input("业务名", value="order")
    process = st.text_input("业务过程", value="pay")
    layer = st.selectbox("分层", ["ods", "dwd", "dws", "dwt", "ads", "dim"])
    period = st.text_input("统计周期 (1d / td / nd / 留空)", value="1d")

    if st.button("生成表名"):
        with st.spinner("调用..."):
            r = api_post("/api/architecture/naming", {
                "session_id": st.session_state.session_id,
                "layer": layer,
                "domain": domain,
                "business": business,
                "process": process,
                "period": period,
            })
        if r["ok"]:
            st.success(f"**表名:** `{r['data'].get('table_name', '?')}`")
            st.json(r["data"])
        else:
            st.error(r["error"])

with col2:
    st.subheader("📚 指标字典")
    indicator = st.text_input("指标名", value="支付金额")
    business_process = st.text_input("业务过程", value="支付")
    modifiers = st.text_input("修饰词 (逗号分隔)", value="花呗,最近 1 天")

    if st.button("生成指标定义"):
        with st.spinner("调用..."):
            r = api_post("/api/architecture/metric-dict", {
                "session_id": st.session_state.session_id,
                "indicator": indicator,
                "business_process": business_process,
                "modifiers": [m.strip() for m in modifiers.split(",") if m.strip()],
            })
        if r["ok"]:
            st.session_state.stage_outputs["03_规范定义"] = r["data"]
            st.success("✅ 指标定义已生成")
            st.json(r["data"])
        else:
            st.error(r["error"])

if st.button("完成本阶段, 进入下一阶段 →"):
    mark_completed(4)
