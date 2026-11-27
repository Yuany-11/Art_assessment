#!/usr/bin/env bash
# ============================================================================
# deploy.sh —— 一键部署（含健康检查 + 自动回滚）
# 用法：IMAGE_TAG=v1.2.0 ./deploy.sh
# 功能：拉代码 → 构建镜像 → 数据库迁移 → 启动容器 → 健康检查 → 失败回滚
# ============================================================================
set -euo pipefail

# ---------- 配置 ----------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
IMAGE_TAG="${IMAGE_TAG:-$(date +%Y%m%d%H%M)}"
LOG_FILE="$SCRIPT_DIR/deploy-$(date +%Y%m%d%H%M).log"
BACKUP_TAG="pre-${IMAGE_TAG}"

# 自动检测机器规格：内存 < 3G 自动加 2c2g 覆盖
TOTAL_MEM_MB=$(awk '/MemTotal/ { printf "%d", $2/1024 }' /proc/meminfo 2>/dev/null || echo 0)
OVERLAY_ARGS=""
if [ "$TOTAL_MEM_MB" -gt 0 ] && [ "$TOTAL_MEM_MB" -lt 3072 ] && [ -f "$SCRIPT_DIR/docker-compose.2c2g.yml" ]; then
    OVERLAY_ARGS="-f deploy/docker-compose.2c2g.yml"
    echo "⚠️  检测到 ECS 内存 ${TOTAL_MEM_MB}MB (< 3GB)，自动加载 2C2G 内存调优覆盖"
fi

COMPOSE="docker compose -f docker-compose.yml $OVERLAY_ARGS --env-file .env"

# 健康检查触发回滚的阈值
MAX_FAILS=10
FAIL_INTERVAL=5

log()  { echo "[$(date '+%F %T')] $*" | tee -a "$LOG_FILE"; }
err()  { echo "[$(date '+%F %T')] ❌ $*" | tee -a "$LOG_FILE" >&2; }
ok()   { echo "[$(date '+%F %T')] ✅ $*" | tee -a "$LOG_FILE"; }

cd "$PROJECT_ROOT"
mkdir -p "$SCRIPT_DIR/backup"

# ---------- 前置检查 ----------
log "=== 部署开始 tag=$IMAGE_TAG ==="

if [ ! -f .env ]; then
    err ".env 不存在，复制 deploy/.env.production.example 后再填"
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    err "docker compose 不可用，请先安装 Docker 24+"
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -q '^art-mysql$'; then
    # 第一次启动：先拉基础设施
    log "首次部署：先启动 MySQL/Redis/MinIO 并等待健康"
    $COMPOSE up -d mysql redis minio
    $COMPOSE up -d minio-init || log "minio-init 已存在则忽略"
    for svc in mysql redis minio; do
        $COMPOSE ps "$svc" | grep -q healthy || {
            err "$svc 未就绪，终止部署"
            exit 1
        }
    done
fi

# ---------- 1. 数据库备份 ----------
log "📦 备份数据库 -> backup/${BACKUP_TAG}.sql.gz"
MYSQL_ID=$(docker ps --filter name=art-mysql --format '{{.ID}}')
if [ -n "$MYSQL_ID" ]; then
    docker exec "$MYSQL_ID" mysqldump \
        -uroot -p"$(grep MYSQL_ROOT_PASSWORD .env | cut -d= -f2)" \
        --single-transaction --routines --triggers art_assessment \
        | gzip > "$SCRIPT_DIR/backup/${BACKUP_TAG}.sql.gz" || \
        err "mysqldump 失败（继续部署，可稍后手动备份）"
    ok "备份完成 $(du -h "$SCRIPT_DIR/backup/${BACKUP_TAG}.sql.gz" | cut -f1)"
else
    log "未发现 art-mysql 容器，跳过备份（首次部署无需）"
fi

# 上一个可运行镜像 tag 留作回滚用
PREVIOUS_TAG=$(docker image inspect art-assessment-backend:latest 2>/dev/null \
    | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['Config']['Image'])" 2>/dev/null \
    || echo "")

# ---------- 2. 拉代码 ----------
log "git pull dev ..."
git fetch origin dev
git checkout dev
git pull --ff-only origin dev || {
    err "git pull 失败（有未推推送的提交或冲突），先手动解决"
    exit 1
}

# ---------- 3. 应用后端补丁（health 接口） ----------
log "应用健康检查补丁 ..."
if ! grep -q "from common.views import health_check" backend/config/urls.py 2>/dev/null; then
    # 追加 health 视图到 common/views.py（如不存在则创建）
    if [ ! -f backend/common/views.py ]; then
        cp deploy/backend-patches/health_view.py backend/common/views.py
        log "新建 backend/common/views.py"
    else
        cat deploy/backend-patches/common_views_append.py >> backend/common/views.py
        log "追加健康检查函数"
    fi
    # 注入 urls.py
    python3 - <<'PYEOF'
import re
p = "backend/config/urls.py"
with open(p, "r", encoding="utf-8") as f:
    content = f.read()
if "path(\"health\"" not in content:
    lines = content.splitlines()
    # 在第一个 path 之前插入 import 和两条路由
    new_lines = []
    inserted_import = False
    inserted_path = False
    for i, line in enumerate(lines):
        new_lines.append(line)
        if not inserted_import and line.startswith("from drf_spectacular"):
            new_lines.append("")
            new_lines.append("from common.views import health_check, readiness_check")
            inserted_import = True
        if not inserted_path and line.strip().startswith("urlpatterns"):
            # 找到列表开头下一行
            new_lines.append('    path("health", health_check, name="health"),')
            new_lines.append('    path("ready", readiness_check, name="ready"),')
            inserted_path = True
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines) + "\n")
    print("urls.py patched OK")
else:
    print("urls.py 已有 health 路由，跳过")
PYEOF
    ok "健康检查接口已就位"
else
    log "health 接口已存在，跳过补丁"
fi

# ---------- 4. 构建镜像 ----------
log "🏗  构建 backend + frontend 镜像 tag=$IMAGE_TAG"
sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$IMAGE_TAG/" .env 2>/dev/null || \
    echo "IMAGE_TAG=$IMAGE_TAG" >> .env

$COMPOSE build --no-cache web frontend
ok "镜像构建完成"

# ---------- 5. 滚动更新 ----------
log "🔄 滚动更新所有服务"
$COMPOSE up -d --remove-orphans
ok "容器已启动"

# ---------- 6. 等待健康 ----------
log "⏳ 等待健康检查通过 ..."
fail=0
until curl -fsS http://127.0.0.1/health >/dev/null 2>&1; do
    fail=$((fail+1))
    if [ $fail -ge $MAX_FAILS ]; then
        err "健康检查连续失败 $((MAX_FAILS * FAIL_INTERVAL)) 秒，触发自动回滚"
        bash "$SCRIPT_DIR/rollback.sh" "$PREVIOUS_TAG"
        exit 2
    fi
    sleep $FAIL_INTERVAL
done
ok "健康检查通过 ✅"

# ---------- 7. 数据库迁移 ----------
log "🐘 执行数据库迁移 ..."
$COMPOSE exec web python manage.py migrate --noinput || {
    err "迁移失败，执行回滚"
    bash "$SCRIPT_DIR/rollback.sh" "$PREVIOUS_TAG"
    exit 2
}
$COMPOSE exec web python manage.py collectstatic --noinput || log "collectstatic 失败（容器内已自带一次）"
ok "迁移 + 静态文件完成"

# ---------- 8. 冒烟测试 ----------
log "🧪 冒烟测试 ..."
CURL_BASE="http://127.0.0.1"
SMOKE_OK=1
for path in "/health" "/ready" "/api/schema/"; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "$CURL_BASE$path" || echo "000")
    if [ "$code" -ge 200 ] && [ "$code" -lt 500 ]; then
        ok "  $path → $code"
    else
        err "  $path → $code"
        SMOKE_OK=0
    fi
done

if [ $SMOKE_OK -eq 0 ]; then
    err "冒烟测试失败，执行回滚"
    bash "$SCRIPT_DIR/rollback.sh" "$PREVIOUS_TAG"
    exit 3
fi

# ---------- 完成 ----------
ok "🎉 部署成功 tag=$IMAGE_TAG"
log "下一步：SLB 健康检查改为 /ready；通知测试回归核心流程"
