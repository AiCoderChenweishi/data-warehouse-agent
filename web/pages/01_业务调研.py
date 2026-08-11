"""阶段 0: 业务调研

目标: 描述业务领域 / 功能模块 / 用户角色 → 输出业务-功能-角色矩阵
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import streamlit as st
from app import api_post, mark_completed, init_session

init_session()

st.title("📋 阶段 0 — 业务调研")
st.caption("把业务说清楚: 业务名 / 功能模块 / 用户角色")

with st.form("business_form"):
    business_name = st.text_input("业务名 *", placeholder="例如: 电商交易业务")
    modules = st.text_area(
        "功能模块 (每行一个) *",
        placeholder="商品管理\n订单管理\n支付管理\n物流管理\n用户管理",
        height=120,
    )
    roles = st.text_area(
        "用户角色 (每行一个) *",
        placeholder="买家\n卖家\n运营\n客服\n管理员",
        height=100,
    )
    submitted = st.form_submit_button("生成业务-功能-角色矩阵", type="primary")

if submitted:
    if not business_name or not modules or not roles:
        st.error("请填写所有必填项")
        st.stop()

    modules_list = [m.strip() for m in modules.split("\n") if m.strip()]
    roles_list = [r.strip() for r in roles.split("\n") if r.strip()]

    payload = {
        "session_id": st.session_state.session_id,
        "business_name": business_name,
        "modules": modules_list,
        "roles": roles_list,
    }

    with st.spinner("调用后端..."):
        result = api_post("/api/requirements/business", payload)

    if not result["ok"]:
        st.error(result["error"])
        st.stop()

    st.session_state.stage_outputs["00_业务调研"] = result["data"]
    st.success("✅ 业务调研产出已生成!")

    data = result["data"]
    st.subheader("📊 业务-功能-角色矩阵")
    if "matrix" in data:
        st.dataframe(data["matrix"], use_container_width=True)
    else:
        st.json(data)

    col1, col2, col3 = st.columns(3)
    col1.metric("功能模块", len(modules_list))
    col2.metric("用户角色", len(roles_list))
    col3.metric("业务领域", 1)

    if st.button("完成本阶段, 进入下一阶段 →"):
        mark_completed(1)
