#!/bin/bash
# 修 nginx 加 WebSocket support (streamlit 必须)
set -e

cat > /etc/nginx/sites-available/dwa <<'NGINXEOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    # 数仓 agent 前端 (streamlit) - 必须支持 WebSocket
    location /dw/ {
        proxy_pass http://127.0.0.1:8501/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Prefix /dw;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
        proxy_buffering off;
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
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
        proxy_connect_timeout 10s;
        proxy_buffering off;
    }
}
NGINXEOF

# 替换 default
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/dwa /etc/nginx/sites-enabled/default
nginx -t 2>&1 | head -3
systemctl reload nginx
echo "nginx reloaded (WebSocket enabled for /dw/)"
