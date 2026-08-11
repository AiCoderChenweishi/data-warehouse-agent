#!/bin/bash
# 改 nginx 加 /dw/ 和 /dw-api/ 反代
set -e

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

    # chat-bi-mavis (老项目) - 保留
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

# 备份 + 替换
if [ -f /etc/nginx/sites-enabled/default ]; then
    cp /etc/nginx/sites-enabled/default /etc/nginx/sites-enabled/default.bak.dwa
    rm /etc/nginx/sites-enabled/default
fi
ln -sf /etc/nginx/sites-available/dwa /etc/nginx/sites-enabled/default
nginx -t 2>&1 | head -3
systemctl reload nginx
echo "nginx reloaded"

# 端到端真验证
echo "=== 端到端验证 ==="
echo "1) /dw/ (前端):"
curl -s -m 5 -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1/dw/
echo "2) /dw-api/health (后端):"
curl -s -m 5 http://127.0.0.1/dw-api/health
echo ""
echo "3) /dw-api/api/modeling/business-process (API 端到端):"
curl -s -X POST http://127.0.0.1/dw-api/api/modeling/business-process \
    -H "Content-Type: application/json" \
    -d '{"session_id":"e2e-117","business_description":"用户在下单后,会经历支付、发货、收货"}' \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print('识别到',len(d.get('processes',[])),'个过程:',[p['name'] for p in d.get('processes',[])])"
echo ""
echo "4) /dw/ 取 HTML (前 5 行):"
curl -s -m 5 http://127.0.0.1/dw/ | head -5
