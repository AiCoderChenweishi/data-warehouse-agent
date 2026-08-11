"""Streamlit 主入口 — 数仓开发 Agent

7 阶段引导式数仓搭建 (业务调研 → 测试验证)
"""
import os
import uuid
import requests
import streamlit as st

# 配置
API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="数仓开发 Agent",
    page_icon="🗄️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 自定义 CSS
st.markdown(
    """
    <style>
    .stProgress > div > div > div > div { background-color: #4CAF50; }
    .step-completed { color: #4CAF50; }
    .step-current { color: #FFA500; font-weight: bold; }
    .step-pending { color: #888; }
    </style>
""",
    unsafe_allow_html=True,
)


def api_post(path: str, payload: dict, timeout: int = 30) -> dict:
    """调用 FastAPI 后端 (带 try/except)"""
    url = f"{API_BASE_URL}{path}"
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        return {"ok": True, "data": r.json()}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": f"后端未启动: {API_BASE_URL}。请先 bash app/backend/run.sh"}
    except requests.exceptions.Timeout:
        return {"ok": False, "error": f"后端超时 ({timeout}s)"}
    except requests.exceptions.HTTPError as e:
        try:
            return {"ok": False, "error": f"后端 HTTP 错误: {e.response.json().get('detail', str(e))}"}
        except Exception:
            return {"ok": False, "error": f"后端 HTTP 错误: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"调用失败: {e}"}


def api_get(path: str, timeout: int = 10) -> dict:
    """GET 调用"""
    url = f"{API_BASE_URL}{path}"
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return {"ok": True, "data": r.json()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def init_session():
    """初始化 session state"""
    if "session_id" not in st.session_state:
        st.session_state.session_id = f"sess-{uuid.uuid4().hex[:8]}"
    if "completed_stages" not in st.session_state:
        st.session_state.completed_stages = set()
    if "stage_outputs" not in st.session_state:
        st.session_state.stage_outputs = {}


def render_stepper():
    """侧栏: 7 阶段 stepper"""
    st.sidebar.title("🗄️ 数仓开发 Agent")
    st.sidebar.caption(f"Session: `{st.session_state.session_id}`")
    st.sidebar.caption(f"API: `{API_BASE_URL}`")

    # 后端健康检查
    health = api_get("/health")
    if health["ok"]:
        st.sidebar.success(f"✅ 后端在线 v{health['data'].get('version', '?')}")
    else:
        st.sidebar.error(f"❌ 后端未连接: {health['error']}")

    st.sidebar.divider()
    st.sidebar.markdown("### 7 阶段流程")

    stages = [
        ("01", "业务调研", "需求起点"),
        ("02", "需求调研", "指标 / 维度 / 数据源"),
        ("03", "架构设计", "数据域 / 总线矩阵"),
        ("04", "规范定义", "命名 / 指标字典"),
        ("05", "模型设计", "Kimball 4 步法"),
        ("06", "跑数", "5 层 ETL"),
        ("07", "测试验证", "对账 / 边界 / 性能"),
    ]

    for code, name, desc in stages:
        idx = int(code)
        done = idx in st.session_state.completed_stages
        marker = "✅" if done else "⏳"
        st.sidebar.markdown(
            f"{marker} **{code}. {name}**  \n"
            f"<small style='color: #888;'>{desc}</small>",
            unsafe_allow_html=True,
        )

    st.sidebar.divider()
    progress = len(st.session_state.completed_stages) / 7
    st.sidebar.progress(progress, text=f"进度: {len(st.session_state.completed_stages)}/7")
    st.sidebar.caption(f"完成度: {progress*100:.0f}%")


def mark_completed(stage: int):
    st.session_state.completed_stages.add(stage)
    st.rerun()


def main():
    init_session()
    render_stepper()

    st.title("🗄️ 数仓开发 Agent")
    st.markdown(
        """
        **让新手像数仓专家一样开发数仓。**

        基于 Kimball《数据仓库工具箱》+ 阿里《OneData》方法论的 7 阶段引导式工作流。
        引擎:DuckDB  ·  后端:FastAPI  ·  前端:Streamlit
        """
    )

    st.info("👈 **左侧 stepper 选阶段开始**。每个阶段会引导你完成关键决策,自动产出 DDL / SQL / 验证报告。")

    # 状态总览
    st.markdown("### 📊 当前会话状态")

    cols = st.columns(4)
    cols[0].metric("Session", st.session_state.session_id, delta_color="off")
    cols[1].metric("已完成阶段", f"{len(st.session_state.completed_stages)}/7")
    cols[2].metric("API", API_BASE_URL)
    cols[3].metric("数据引擎", "DuckDB")

    if st.session_state.stage_outputs:
        st.markdown("### 📦 阶段产出")
        for stage_key, output in st.session_state.stage_outputs.items():
            with st.expander(f"📄 {stage_key}"):
                if isinstance(output, (dict, list)):
                    st.json(output)
                else:
                    st.text(str(output))


# 子页面注册 (multipage app)
main()
