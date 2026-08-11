#!/bin/bash
# 117 部署脚本 - scp 上去后 bash 跑
set -e
cd /opt/data-warehouse-agent

# 1. .env
mkdir -p db
cat > .env <<'ENVEOF'
PORT=8001
WAREHOUSE_DB_PATH=/opt/data-warehouse-agent/db/warehouse.duckdb
STREAMLIT_PORT=8501
API_BASE_URL=/dw-api
ENVEOF

# 2. 装依赖 (已装过会快)
pip3 install --break-system-packages --quiet duckdb fastapi 'uvicorn[standard]' pydantic jinja2 httpx pytest python-multipart streamlit streamlit-extras 2>&1 | tail -3

# 3. 起后端 (kill 旧)
pkill -9 -f 'uvicorn app.backend' 2>/dev/null
sleep 1
export PYTHONPATH=/opt/data-warehouse-agent
nohup python3 -m uvicorn app.backend.main:app --host 0.0.0.0 --port 8001 > /tmp/dwa_backend.log 2>&1 &
echo "backend pid: $!"
sleep 3
curl -s -m 3 http://127.0.0.1:8001/health || echo "backend not up yet"
echo ""

# 4. 起 streamlit
pkill -9 -f 'streamlit run' 2>/dev/null
sleep 1
export API_BASE_URL=/dw-api
nohup python3 -m streamlit run web/app.py --server.port 8501 --server.headless true --server.address 0.0.0.0 --browser.gatherUsageStats false > /tmp/dwa_frontend.log 2>&1 &
echo "streamlit pid: $!"
sleep 5
curl -s -m 3 -o /dev/null -w "streamlit HTTP %{http_code}\n" http://127.0.0.1:8501/
