#!/usr/bin/env bash
# ============================================================================
# update.sh —— 拉取别人推送到 GitHub 的改动并上线
#
# 用法（在服务器 /opt/art-assessment 下）：
#   ./update.sh                 # 自动：拉 dev 分支最新代码 → 按改动范围重建 → 重启
#   ./update.sh --dry-run       # 只看会拉什么/会改什么，不做任何变更
#   BRANCH=main ./update.sh     # 换分支
#   ./update.sh --frontend-only # 只重建前端
#   ./update.sh --backend-only  # 只重建后端
#
# 特点：
#   1. 自动备份被本地覆盖的 docker-compose.yml / deploy/ / .env，拉完代码再恢复
#   2. 用 commit tag 打镜像，旧镜像保留，失败可回滚
#   3. 健康检查不过自动切回旧代码
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"

BRANCH="${BRANCH:-dev}"
OVERLAY="${HOME:-/home/ecs-user}/art-overlay"
COMPOSE="docker compose -f docker-compose.yml --env-file .env"
DRY_RUN=0
ONLY=""

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --frontend-only) ONLY="frontend" ;;
        --backend-only) ONLY="backend" ;;
        *) echo "未知参数: $arg"; exit 1 ;;
    esac
done

log() { echo "[$(date '+%F %T')] $*"; }

# ---------- 0. 保护：工作区有未提交改动时拒绝覆盖 ----------
if [ "$DRY_RUN" -eq 0 ] && [ "${FORCE:-0}" != "1" ]; then
    if [ -n "$(git status --porcelain)" ]; then
        cat <<'MSG'
[拒绝执行] 服务器工作区有未提交的改动，update.sh 会用 GitHub 代码覆盖它们。
已自动停止，未修改任何文件。
确认要覆盖请先备份，再执行：FORCE=1 ./update.sh
MSG
        exit 1
    fi
fi

# ---------- 1. 记录当前状态 ----------
OLD_TAG=$(grep -E '^IMAGE_TAG=' .env | cut -d= -f2 | tr -d '\r' || true)
OLD_COMMIT=$(git rev-parse HEAD)
log "当前: commit=${OLD_COMMIT:0:8} tag=${OLD_TAG:-none}"

# ---------- 2. 备份本地覆盖的部署文件 ----------
if [ "$DRY_RUN" -eq 0 ]; then
    mkdir -p "$OVERLAY"
    cp -a docker-compose.yml "$OVERLAY/docker-compose.yml"
    cp -a .env "$OVERLAY/.env"
    rm -rf "$OVERLAY/deploy"
    cp -a deploy "$OVERLAY/deploy"
    log "已备份 docker-compose.yml / .env / deploy/ → $OVERLAY"
fi

# ---------- 3. 拉取代码 ----------
log "拉取 origin/$BRANCH ..."
git fetch --depth 1 origin "$BRANCH"
NEW_COMMIT=$(git rev-parse FETCH_HEAD)
log "远端最新: ${NEW_COMMIT:0:8}"

if [ "$OLD_COMMIT" = "$NEW_COMMIT" ]; then
    log "代码已是最新（${OLD_COMMIT:0:8}），无需更新"
    exit 0
fi

CHANGED=$(git diff --name-only "$OLD_COMMIT" "$NEW_COMMIT" 2>/dev/null || echo "UNKNOWN")
log "变更文件数: $(echo "$CHANGED" | wc -l)"
echo "$CHANGED" | head -40 | sed 's/^/    /'

if [ "$DRY_RUN" -eq 1 ]; then
    log "--dry-run 结束，未做任何修改"
    exit 0
fi

git checkout -f "$NEW_COMMIT"
log "代码已切换到 ${NEW_COMMIT:0:8}"

# ---------- 4. 恢复部署覆盖文件（git 会覆盖它们） ----------
if [ -f "$OVERLAY/docker-compose.yml" ]; then
    cp -a "$OVERLAY/docker-compose.yml" docker-compose.yml
    cp -a "$OVERLAY/deploy/." deploy/
    cp -a "$OVERLAY/.env" .env
    # 中文文件名请求头修复尚未上游化，更新代码后保留此补丁。
    if [ -f deploy/backend-patches/audio_tags.py ]; then
        cp -a deploy/backend-patches/audio_tags.py backend/apps/files/audio_tags.py
    fi
    log "部署配置已恢复"
fi

# ---------- 5. 判断要重建哪些镜像 ----------
NEED_BACKEND=0
NEED_FRONTEND=0
if [ "$CHANGED" = "UNKNOWN" ]; then
    NEED_BACKEND=1; NEED_FRONTEND=1
else
    echo "$CHANGED" | grep -qE '^(backend/|requirements)' && NEED_BACKEND=1
    echo "$CHANGED" | grep -qE '^(src/|public/|package\.json|pnpm-lock|vite\.config|index\.html|tsconfig)' && NEED_FRONTEND=1
fi
case "$ONLY" in
    backend)  NEED_FRONTEND=0; NEED_BACKEND=1 ;;
    frontend) NEED_BACKEND=0; NEED_FRONTEND=1 ;;
esac
log "重建计划: backend=$NEED_BACKEND frontend=$NEED_FRONTEND"

if [ "$NEED_BACKEND" -eq 0 ] && [ "$NEED_FRONTEND" -eq 0 ]; then
    log "本次改动不涉及前后端源码，无需重建（如改了 compose/nginx 请手动 up -d）"
    $COMPOSE up -d
    exit 0
fi

# ---------- 6. 用 commit 号打 tag，旧镜像保留 ----------
NEW_TAG="${NEW_COMMIT:0:8}"
sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$NEW_TAG/" .env 2>/dev/null || echo "IMAGE_TAG=$NEW_TAG" >> .env

TARGETS=""
[ "$NEED_BACKEND" -eq 1 ] && TARGETS="$TARGETS web"
[ "$NEED_FRONTEND" -eq 1 ] && TARGETS="$TARGETS frontend"

log "构建镜像 tag=$NEW_TAG （2C2G 机器前端约需 2-4 分钟，请耐心等）"
# shellcheck disable=SC2086
$COMPOSE build $TARGETS

log "重启服务"
if [ "$NEED_BACKEND" -eq 1 ]; then
    $COMPOSE up -d --no-deps web worker scheduler
fi
if [ "$NEED_FRONTEND" -eq 1 ]; then
    $COMPOSE up -d --no-deps frontend
fi

# ---------- 7. 健康检查 ----------
log "等待健康检查 ..."
OK=0
for i in $(seq 1 30); do
    if curl -fsS http://127.0.0.1/health >/dev/null 2>&1; then OK=1; break; fi
    sleep 5
done

if [ "$OK" -eq 1 ]; then
    log "✅ 更新成功：${OLD_COMMIT:0:8} → ${NEW_COMMIT:0:8}"
    docker ps --format '{{.Names}}  {{.Status}}' | grep art-
    exit 0
fi

# ---------- 8. 失败回滚 ----------
log "❌ 健康检查失败，回滚到 ${OLD_COMMIT:0:8}"
docker logs art-web --tail 50 || true
git checkout -f "$OLD_COMMIT"
cp -a "$OVERLAY/docker-compose.yml" docker-compose.yml
cp -a "$OVERLAY/deploy/." deploy/
if [ -n "$OLD_TAG" ]; then
    sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$OLD_TAG/" .env
fi
$COMPOSE up -d --no-deps web worker scheduler frontend
sleep 10
curl -fsS http://127.0.0.1/health && log "已回滚并恢复服务" || log "回滚后仍不健康，请手动排查"
exit 2
