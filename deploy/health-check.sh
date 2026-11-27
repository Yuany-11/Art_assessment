#!/usr/bin/env bash
# ============================================================================
# 轻量健康检查 —— 被云监控 / 巡检脚本调用
# 返回：0=健康 1=不健康
# ============================================================================
set -euo pipefail

errors=()

# 1. Nginx /health
if ! curl -fsS http://127.0.0.1/health >/dev/null 2>&1; then
    errors+=("nginx /health 不响应")
fi

# 2. Django /ready
ready_code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1/ready || echo "000")
if [ "$ready_code" != "200" ]; then
    errors+=("backend /ready 返回 $ready_code")
fi

# 3. 关键容器在跑
for c in art-web art-frontend art-mysql art-redis; do
    if ! docker ps --format '{{.Names}}' | grep -q "^${c}$"; then
        errors+=("容器 $c 未运行")
    fi
done

# 4. 磁盘水位 80%
DISK_PCT=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DISK_PCT" -ge 80 ]; then
    errors+=("根分区磁盘 ${DISK_PCT}%")
fi

if [ ${#errors[@]} -eq 0 ]; then
    echo "✅ healthy"
    exit 0
else
    echo "❌ unhealthy:"
    for e in "${errors[@]}"; do echo "  - $e"; done
    exit 1
fi
