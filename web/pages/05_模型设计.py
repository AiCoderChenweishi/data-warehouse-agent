"""阶段 4: 模型设计 (核心!) — Kimball 4 步法

1. 业务过程识别
2. 声明粒度
3. 识别维度
4. 识别事实 → 决定事实表类型 → 生成 DDL
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import streamlit as st
from app import api_post, mark_completed, init_session

init_session()

st.title("🧩 阶段 4 — 模型设计 (Kimball 4 步法)")
st.caption("核心!按 4 步法走完,自动生成事实表 DDL")

# 1. 业务过程
st.subheader("Step 1️⃣ 业务过程识别")
business_desc = st.text_area(
    "用 1-2 句话描述业务场景",
    value="用户在下单后,会经历支付、发货、收货",
    height=80,
)
if st.button("识别业务过程"):
    with st.spinner("分析中..."):
        r = api_post("/api/modeling/business-process", {
            "session_id": st.session_state.session_id,
            "business_description": business_desc,
        })
    if r["ok"]:
        st.session_state.modeling = {"processes": r["data"].get("processes", [])}
        st.success(f"识别到 {len(r['data'].get('processes', []))} 个业务过程")
        for p in r["data"].get("processes", []):
            st.markdown(f"- **{p.get('name')}** (置信度: {p.get('confidence', 0):.1%}) — {p.get('rationale', '')[:100]}")
    else:
        st.error(r["error"])

# 2. 粒度
if st.session_state.get("modeling", {}).get("processes"):
    st.divider()
    st.subheader("Step 2️⃣ 声明粒度")
    process = st.selectbox(
        "选业务过程",
        [p["name"] for p in st.session_state.modeling["processes"]],
    )
    if st.button("推荐粒度"):
        with st.spinner("..."):
            r = api_post("/api/modeling/grain", {
                "session_id": st.session_state.session_id,
                "business_process": process,
            })
        if r["ok"]:
            st.session_state.modeling["grain"] = r["data"]
            st.success(f"**推荐粒度:** {r['data'].get('grain', '?')}")
            st.json(r["data"])

# 3. 维度
if st.session_state.get("modeling", {}).get("grain"):
    st.divider()
    st.subheader("Step 3️⃣ 识别维度")
    if st.button("推荐维度"):
        with st.spinner("..."):
            r = api_post("/api/modeling/dimensions", {
                "session_id": st.session_state.session_id,
                "business_process": process,
                "grain": st.session_state.modeling["grain"].get("grain", ""),
            })
        if r["ok"]:
            st.session_state.modeling["dimensions"] = r["data"]
            st.success("✅ 维度已识别")
            st.json(r["data"])

# 4. 事实 + 事实表类型
if st.session_state.get("modeling", {}).get("dimensions"):
    st.divider()
    st.subheader("Step 4️⃣ 识别事实 + 决定事实表类型")
    if st.button("推荐事实 + 事实表类型"):
        with st.spinner("..."):
            r1 = api_post("/api/modeling/facts", {
                "session_id": st.session_state.session_id,
                "business_process": process,
                "grain": st.session_state.modeling["grain"].get("grain", ""),
                "dimensions": st.session_state.modeling["dimensions"].get("dimensions", []),
            })
            r2 = api_post("/api/modeling/fact-type", {
                "session_id": st.session_state.session_id,
                "business_processes": [p["name"] for p in st.session_state.modeling["processes"]],
                "has_time_intervals": True,
            })
        if r1["ok"] and r2["ok"]:
            st.session_state.modeling["facts"] = r1["data"]
            st.session_state.modeling["fact_type"] = r2["data"]
            st.success("✅ 事实 + 事实表类型已确定")
            st.markdown(f"**事实表类型:** {r2['data'].get('fact_type_name', '?')}")
            st.json({**r1["data"], **r2["data"]})

# 5. 生成 DDL
if st.session_state.get("modeling", {}).get("fact_type"):
    st.divider()
    st.subheader("📜 生成 DDL")
    table_name = st.text_input("表名", value="dwd_trade_order_pay")
    if st.button("生成 DDL", type="primary"):
        with st.spinner("生成 DDL..."):
            r = api_post("/api/modeling/ddl", {
                "session_id": st.session_state.session_id,
                "fact_type": st.session_state.modeling["fact_type"].get("fact_type", "transaction"),
                "table_name": table_name,
                "grain": st.session_state.modeling["grain"].get("grain", ""),
                "dimensions": st.session_state.modeling["dimensions"].get("dimensions", []),
                "facts": st.session_state.modeling["facts"].get("facts", []),
            })
        if r["ok"]:
            st.session_state.modeling["ddl"] = r["data"]
            st.session_state.stage_outputs["04_模型设计"] = r["data"]
            st.success("✅ DDL 已生成")
            ddl = r["data"].get("ddl", "")
            st.code(ddl, language="sql")
            st.download_button(
                "📥 下载 DDL",
                data=ddl,
                file_name=f"{table_name}.sql",
                mime="text/plain",
            )
        else:
            st.error(r["error"])

if st.session_state.get("modeling", {}).get("ddl"):
    if st.button("完成本阶段, 进入下一阶段 →"):
        mark_completed(5)
