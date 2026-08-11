#!/bin/bash
# 117 写 systemd 让 backend + streamlit 常驻
set -e

# backend service
cat > /etc/systemd/system/dwa-backend.service <<'SVCEOF'
[Unit]
Description=Data Warehouse Agent - FastAPI Backend (port 8001)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/data-warehouse-agent
Environment="PYTHONPATH=/opt/data-warehouse-agent"
EnvironmentFile=/opt/data-warehouse-agent/.env
ExecStart=/usr/bin/python3 -m uvicorn app.backend.main:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=3
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
SVCEOF

# streamlit service
cat > /etc/systemd/system/dwa-frontend.service <<'SVCEOF'
[Unit]
Description=Data Warehouse Agent - Streamlit Frontend (port 8501)
After=network.target dwa-backend.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/data-warehouse-agent
Environment="PYTHONPATH=/opt/data-warehouse-agent"
Environment="API_BASE_URL=/dw-api"
ExecStart=/usr/bin/python3 -m streamlit run web/app.py --server.port 8501 --server.headless true --server.address 0.0.0.0 --browser.gatherUsageStats false
Restart=always
RestartSec=3
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
SVCEOF

# 停掉临时 nohup 进程
pkill -9 -f 'uvicorn app.backend' 2>/dev/null
pkill -9 -f 'streamlit run' 2>/dev/null
sleep 2

systemctl daemon-reload
systemctl enable dwa-backend.service dwa-frontend.service
systemctl restart dwa-backend.service dwa-frontend.service
sleep 6

echo "=== systemd 状态 ==="
systemctl is-active dwa-backend.service
systemctl is-active dwa-frontend.service
echo ""
echo "=== 端到端 ==="
curl -s -m 5 -o /dev/null -w "/dw/ HTTP %{http_code}\n" http://127.0.0.1/dw/
curl -s -m 5 http://127.0.0.1/dw-api/health
echo ""
ps aux | grep -E 'uvicorn app.backend|streamlit run' | grep -v grep | awk '{print $2, $11, $12, $13}'
