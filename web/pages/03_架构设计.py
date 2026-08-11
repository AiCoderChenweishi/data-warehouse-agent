"""阶段 2: 架构设计

目标: 划分数据域 + 生成总线矩阵
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import streamlit as st
from app import api_post, mark_completed, init_session

init_session()

st.title("🏗️ 阶段 2 — 架构设计")
st.caption("数据域划分 + 总线矩阵 (业务过程 × 维度)")

with st.form("arch_form"):
    business_modules = st.text_area(
        "业务模块 (每行一个)\n例: 交易 / 商品 / 用户 / 营销 / 物流",
        height=100,
        value="交易\n商品\n用户\n营销\n物流",
    )
    business_processes = st.text_area(
        "业务过程 (每行一个)\n例: 下单 / 支付 / 发货 / 收货 / 退款",
        height=100,
        value="下单\n支付\n发货\n收货\n退款",
    )
    submitted = st.form_submit_button("生成数据域 + 总线矩阵", type="primary")

if submitted:
    modules_list = [m.strip() for m in business_modules.split("\n") if m.strip()]
    processes_list = [p.strip() for p in business_processes.split("\n") if p.strip()]

    # 1. 数据域
    with st.spinner("生成数据域..."):
        r1 = api_post("/api/architecture/domains", {
            "session_id": st.session_state.session_id,
            "modules": modules_list,
        })

    if r1["ok"]:
        st.subheader("📦 数据域划分")
        st.json(r1["data"])

    # 2. 总线矩阵
    with st.spinner("生成总线矩阵..."):
        r2 = api_post("/api/architecture/bus-matrix", {
            "session_id": st.session_state.session_id,
            "data_domains": r1["data"].get("domains", modules_list) if r1["ok"] else modules_list,
            "business_processes": processes_list,
        })

    if r2["ok"]:
        st.subheader("🔗 总线矩阵 (业务过程 × 维度)")
        st.json(r2["data"])
        st.session_state.stage_outputs["02_架构设计"] = {
            "domains": r1["data"] if r1["ok"] else None,
            "bus_matrix": r2["data"],
        }
        st.success("✅ 架构设计产出已生成!")
    else:
        st.error(r2["error"])

    if st.button("完成本阶段, 进入下一阶段 →"):
        mark_completed(3)
