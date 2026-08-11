#!/bin/bash
# 117 起 streamlit + 改 nginx + 端到端验证
set -e
cd /opt/data-warehouse-agent

# 1. 起 streamlit
pkill -9 -f 'streamlit run' 2>/dev/null
sleep 1
export PYTHONPATH=/opt/data-warehouse-agent
export API_BASE_URL=/dw-api
nohup python3 -m streamlit run web/app.py \
    --server.port 8501 \
    --server.headless true \
    --server.address 0.0.0.0 \
    --browser.gatherUsageStats false \
    > /tmp/dwa_frontend.log 2>&1 &
ST_PID=$!
echo "streamlit pid: $ST_PID"
sleep 6
echo "--- streamlit health ---"
curl -s -m 3 -o /dev/null -w "8501 HTTP %{http_code}\n" http://127.0.0.1:8501/
ps aux | grep 'streamlit run' | grep -v grep | head -2
tail -3 /tmp/dwa_frontend.log

# 2. 改 nginx — 在 / 之前加 /dw/ 和 /dw-api/ 反代
echo "--- nginx ---"
cat > /etc/nginx/sites-available/dwa <<'NGINXEOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    # 数仓 agent 前端 (streamlit)
    location /dw/ {
        proxy_pass http://127.0.0.1:8501/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
        proxy_buffering off;
        proxy_http_version 1.1;
        # 关键: streamlit SSE 需要 X-Accel-Buffering: no
        proxy_set_header X-Accel-Buffering no;
    }

    # 数仓 agent 后端 (fastapi)
    location /dw-api/ {
        proxy_pass http://127.0.0.1:8001/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    # chat-bi-mavis (老项目) - 保留 location / 不变
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
        proxy_connect_timeout 10s;
        proxy_buffering off;
        proxy_http_version 1.1;
    }
}
NGINXEOF

# 替换 default
mv /etc/nginx/sites-enabled/default /etc/nginx/sites-enabled/default.bak 2>/dev/null || true
ln -sf /etc/nginx/sites-available/dwa /etc/nginx/sites-enabled/default
nginx -t 2>&1 | head -5
systemctl reload nginx 2>&1 | head -3
echo "--- nginx reload ok ---"

# 3. 端到端验证
echo "--- 端到端真验证 ---"
sleep 2
echo "前端 /dw/ :"
curl -s -m 5 -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1/dw/

echo "后端 /dw-api/health :"
curl -s -m 5 http://127.0.0.1/dw-api/health
echo ""

echo "API call /dw-api/api/modeling/business-process :"
curl -s -X POST http://127.0.0.1/dw-api/api/modeling/business-process \
    -H "Content-Type: application/json" \
    -d '{"session_id":"e2e-final","business_description":"用户在下单后,会经历支付、发货、收货"}' | head -c 200
echo ""
