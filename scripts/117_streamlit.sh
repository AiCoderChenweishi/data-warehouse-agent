#!/bin/bash
# 117 启动 streamlit
set -e
cd /opt/data-warehouse-agent
export PYTHONPATH=/opt/data-warehouse-agent
export API_BASE_URL=/dw-api
nohup python3 -m streamlit run web/app.py \
    --server.port 8501 \
    --server.headless true \
    --server.address 0.0.0.0 \
    --browser.gatherUsageStats false \
    > /tmp/dwa_frontend.log 2>&1 &
echo "streamlit pid: $!"
sleep 6
curl -s -m 3 -o /dev/null -w "streamlit HTTP %{http_code}\n" http://127.0.0.1:8501/
ps aux | grep 'streamlit run' | grep -v grep | head -2
tail -5 /tmp/dwa_frontend.log
