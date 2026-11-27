#!/usr/bin/env bash
# ============================================================================
# 定时备份（由 crontab 每日凌晨执行）
# 功能：MySQL 全量 + MinIO 同步 + 本地压缩 + 超过 7 天自动清理
# 建议 crontab：0 3 * * * cd /opt/art-assessment && bash deploy/backup.sh >> deploy/backup/backup.log 2>&1
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="$SCRIPT_DIR/backup"
RETENTION_DAYS=7
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"
cd "$PROJECT_ROOT"

MYSQL_ID=$(docker ps --filter name=art-mysql --format '{{.ID}}' | head -1)
if [ -z "$MYSQL_ID" ]; then
    echo "[$DATE] mysql 容器未运行，跳过备份"
    exit 0
fi

MYSQL_ROOT_PASSWORD=$(grep MYSQL_ROOT_PASSWORD .env | cut -d= -f2 || true)
[ -z "$MYSQL_ROOT_PASSWORD" ] && MYSQL_ROOT_PASSWORD="root_pass"

echo "[$DATE] ===== MySQL 备份开始 ====="
docker exec "$MYSQL_ID" mysqldump \
    -uroot -p"$MYSQL_ROOT_PASSWORD" \
    --single-transaction \
    --routines --triggers --events \
    --hex-blob \
    art_assessment \
    | gzip > "$BACKUP_DIR/mysql_$DATE.sql.gz"

# 保留元数据（行数、大小）
LINE_COUNT=$(gzip -dc "$BACKUP_DIR/mysql_$DATE.sql.gz" | wc -l)
BACKUP_SIZE=$(du -h "$BACKUP_DIR/mysql_$DATE.sql.gz" | cut -f1)
echo "[$DATE] ✅ MySQL 备份完成 $BACKUP_SIZE / $LINE_COUNT 行"

# MinIO 数据卷备份（可选：直接 dump volume）
if docker ps --filter name=art-minio --format '{{.ID}}' | grep -q .; then
    echo "[$DATE] MinIO 数据卷打包 ..."
    docker run --rm \
        -v art_minio_data:/data \
        -v "$BACKUP_DIR":/backup \
        alpine tar czf "/backup/minio_$DATE.tar.gz" -C /data . 2>/dev/null \
        && echo "[$DATE] ✅ MinIO 备份完成" || echo "[$DATE] ⚠️ MinIO 备份跳过"
fi

# 清理过期
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true
echo "[$DATE] 🧹 超过 $RETENTION_DAYS 天的备份已清理"

# 磁盘水位
DISK_PCT=$(df -h "$BACKUP_DIR" | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DISK_PCT" -ge 80 ]; then
    echo "⚠️ 备份目录磁盘占用已达 ${DISK_PCT}%，需要扩容或清理"
fi
