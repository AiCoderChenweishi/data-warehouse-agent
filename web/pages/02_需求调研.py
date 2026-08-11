"""阶段 1: 需求调研

目标: 列出指标 / 维度 / 数据源 → 输出指标清单 + 维度清单 + 数据源清单
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import streamlit as st
from app import api_post, mark_completed, init_session

init_session()

st.title("📊 阶段 1 — 需求调研")
st.caption("把要算什么想清楚: 指标 / 维度 / 数据源")

col1, col2 = st.columns(2)

with col1:
    st.subheader("📈 指标")
    metrics = st.text_area(
        "关注的指标 (每行: 名称 | 业务过程 | 修饰词)\n例: 订单数 | 下单 | 最近 1 天",
        height=180,
        placeholder="订单数 | 下单 | 最近 1 天\nGMV | 下单 | 累计\n支付金额 | 支付 | 最近 1 天",
    )
    dimensions = st.text_area(
        "维度 (每行一个)\n例: 用户 / 商品 / 时间 / 商家 / 支付方式",
        height=100,
        placeholder="用户\n商品\n时间\n商家\n支付方式",
    )

with col2:
    st.subheader("🗄️ 数据源")
    sources = st.text_area(
        "数据源 (每行: 表名 | 类型 | 业务系统)\n例: ods_order | MySQL | 交易系统",
        height=180,
        placeholder="ods_order | MySQL | 交易系统\nods_payment | MySQL | 支付系统\nods_logistics | MySQL | 物流系统",
    )
    st.subheader("🔍 关注重点")
    focus = st.text_area(
        "业务方特别关注什么? (可空)",
        height=80,
        placeholder="例如: 转化漏斗 + 用户分层",
    )

if st.button("生成需求调研清单", type="primary"):
    if not metrics or not sources:
        st.error("指标和数据源是必填的")
        st.stop()

    metrics_list = [m.strip() for m in metrics.split("\n") if m.strip()]
    dimensions_list = [d.strip() for d in dimensions.split("\n") if d.strip()]
    sources_list = [s.strip() for s in sources.split("\n") if s.strip()]

    payload = {
        "session_id": st.session_state.session_id,
        "metrics": metrics_list,
        "dimensions": dimensions_list,
        "sources": sources_list,
        "focus": focus or "",
    }

    with st.spinner("调用后端..."):
        result = api_post("/api/requirements/metrics", payload)

    if not result["ok"]:
        st.error(result["error"])
        st.stop()

    st.session_state.stage_outputs["01_需求调研"] = result["data"]
    st.success("✅ 需求调研产出已生成!")
    st.json(result["data"])

    if st.button("完成本阶段, 进入下一阶段 →"):
        mark_completed(2)
