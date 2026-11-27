#!/usr/bin/env bash
# ============================================================================
# rollback.sh —— 一键回滚
# 用法：./rollback.sh                 # 回滚到 .env 记录的上一个 tag
#      ./rollback.sh v1.1.0          # 回滚到指定 tag
# 说明：只影响 web/frontend 两个服务；MySQL/Redis/MinIO 保持不动
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 自动检测机器规格：内存 < 3G 自动加 2c2g 覆盖
TOTAL_MEM_MB=$(awk '/MemTotal/ { printf "%d", $2/1024 }' /proc/meminfo 2>/dev/null || echo 0)
OVERLAY_ARGS=""
if [ "$TOTAL_MEM_MB" -gt 0 ] && [ "$TOTAL_MEM_MB" -lt 3072 ] && [ -f "$SCRIPT_DIR/docker-compose.2c2g.yml" ]; then
    OVERLAY_ARGS="-f deploy/docker-compose.2c2g.yml"
fi

COMPOSE="docker compose -f docker-compose.yml $OVERLAY_ARGS --env-file .env"
cd "$PROJECT_ROOT"

TARGET_TAG="${1:-}"

# 从 .env 找 pre-* 备份，取最近的那个
if [ -z "$TARGET_TAG" ]; then
    LATEST_BACKUP=$(ls -1t "$SCRIPT_DIR/backup"/pre-*.sql.gz 2>/dev/null | head -1)
    if [ -n "$LATEST_BACKUP" ]; then
        TARGET_TAG=$(basename "$LATEST_BACKUP" .sql.gz | sed 's/^pre-//')
        echo "🔙 自动选择上一个 tag=$TARGET_TAG（对应备份 $LATEST_BACKUP）"
    else
        echo "❌ 无法推断回滚目标，请手动指定：./rollback.sh <tag>"
        exit 1
    fi
fi

echo "🔙 回滚到 tag=$TARGET_TAG ..."

# 1. 切 .env 中的 IMAGE_TAG
sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$TARGET_TAG/" .env || \
    echo "IMAGE_TAG=$TARGET_TAG" >> .env

# 2. 拉/构建对应 tag（本地应该已有；没有就从 registry 拉或重新 build）
echo "拉取/构建镜像 ..."
if docker image inspect "art-assessment-backend:$TARGET_TAG" >/dev/null 2>&1; then
    echo "本地已有 backend:$TARGET_TAG"
else
    $COMPOSE build web || { echo "❌ 无法构建 backend:$TARGET_TAG"; exit 1; }
fi

if docker image inspect "art-assessment-frontend:$TARGET_TAG" >/dev/null 2>&1; then
    echo "本地已有 frontend:$TARGET_TAG"
else
    $COMPOSE build frontend || echo "⚠️ 无法构建 frontend:$TARGET_TAG（可能无源代码变更，跳过）"
fi

# 3. 替换服务
echo "重启 web / frontend ..."
$COMPOSE up -d --no-deps web frontend

# 4. 健康检查
sleep 5
if curl -fsS http://127.0.0.1/health >/dev/null 2>&1; then
    echo "✅ 回滚成功 —— 健康检查通过"
else
    echo "❌ 回滚后健康检查不通过，当前容器状态："
    $COMPOSE ps
    exit 2
fi
