#!/bin/bash
# 启动 Streamlit Web UI
# 用法: bash web/run.sh
set -e

cd "$(dirname "$0")/.."

PORT=${STREAMLIT_PORT:-8501}

echo "[startup] 启动 Streamlit 端口 $PORT"
echo "[startup] API_BASE_URL=${API_BASE_URL:-http://127.0.0.1:8000}"

export API_BASE_URL=${API_BASE_URL:-http://127.0.0.1:8000}

exec python3 -m streamlit run web/app.py \
    --server.port "$PORT" \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false \
    --theme.base dark
