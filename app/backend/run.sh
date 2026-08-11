#!/bin/bash
# 启动 FastAPI 后端
# 用法: bash app/backend/run.sh
# 默认端口 8000 (从 .env 的 PORT 读, 缺省 8000)

set -e

# 读 .env
if [ -f .env ]; then
    set -a
    . ./.env
    set +a
fi

PORT=${PORT:-8000}
DB_PATH=${WAREHOUSE_DB_PATH:-./db/warehouse.duckdb}

echo "[startup] PORT=$PORT"
echo "[startup] WAREHOUSE_DB_PATH=$DB_PATH"
echo "[startup] 启动 FastAPI 后端..."

cd "$(dirname "$0")/../.."

# 删除旧 db (开发模式, 让 DDL 重新跑)
rm -f "$DB_PATH"

export PYTHONPATH="$(pwd):${PYTHONPATH:-}"

exec python3 -m uvicorn app.backend.main:app --host 0.0.0.0 --port "$PORT" --reload
