#!/bin/bash
# 117 端到端真验证
set -e
BASE="http://127.0.0.1/dw-api"

echo "=== 1. 业务过程识别 ==="
curl -s -X POST $BASE/api/modeling/business-process \
    -H "Content-Type: application/json" \
    -d '{"session_id":"e2e-117","business_description":"用户在下单后,会经历支付、发货、收货"}' \
    | jq -r '"  识别到 " + ([.processes[].name] | length | tostring) + " 个过程: " + ([.processes[].name] | join(" / "))'

echo "=== 2. 事实表类型决策 ==="
curl -s -X POST $BASE/api/modeling/fact-type \
    -H "Content-Type: application/json" \
    -d '{"session_id":"e2e-117","business_processes":["下单","支付","发货","收货"],"has_time_intervals":true}' \
    | jq -r '"  推荐: " + .fact_type_name + " (置信度 " + (.confidence|tostring) + ")"'

echo "=== 3. 命名规范 ==="
curl -s -X POST $BASE/api/architecture/naming \
    -H "Content-Type: application/json" \
    -d '{"session_id":"e2e-117","layer":"dws","domain":"trade","business":"order","process":"pay","period":"1d"}' \
    | jq -r '"  表名: " + .table_name'

echo "=== 4. 后端 health ==="
curl -s $BASE/health | jq -r '"  status: " + .status + ", version: " + .version'

echo "=== 5. 前端 /dw/ 真实可访问 ==="
curl -s -m 5 -o /dev/null -w "  /dw/ HTTP %{http_code}, size %{size_download} bytes\n" http://127.0.0.1/dw/

echo "=== 6. 7 阶段页面 ==="
for slug in "01_业务调研" "02_需求调研" "03_架构设计" "04_规范定义" "05_模型设计" "06_跑数" "07_测试验证"; do
    url="http://127.0.0.1/dw/${slug}"
    code=$(curl -s -m 5 -o /dev/null -w "%{http_code}" "$url")
    echo "  /dw/${slug}: HTTP ${code}"
done
