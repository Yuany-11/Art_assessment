# ============================================================================
# 艺术素质测评系统 —— 部署操作手册
# 目标环境：阿里云 ECS（2C4G 起步，Alibaba Cloud Linux 3 或 Ubuntu 22.04）
# 架构：Docker Compose 单机（Nginx + Django + MySQL + Redis + MinIO + RQ Worker + 定时任务）
# ============================================================================

## 目录

1. [阿里云侧先做什么](#1-阿里云侧先做什么)
2. [ECS 初始化](#2-ecs-初始化)
3. [拉代码与配置](#3-拉代码与配置)
4. [首次部署](#4-首次部署)
5. [后续版本发布](#5-后续版本发布)
6. [回滚](#6-回滚)
7. [日常运维命令速查](#7-日常运维命令速查)
8. [告警与监控](#8-告警与监控)

---

## 1. 阿里云侧先做什么

| 序号 | 动作 | 关键要点 |
|---|---|---|
| 1 | 购买 ECS | 2C4G 起步；**必须勾选 2 台同可用区**（SLB 需要至少 2 个后端） |
| 2 | 买 SLB | 监听 80；后端服务器组填 2 台 ECS；健康检查路径设 `http://<ECS内网IP>/ready` |
| 3 | 备案 + 域名 | 阿里云免费证书申请；DNS 把域名指向 SLB 公网 IP |
| 4 | 安全组 | **只开 80（SLB 入）、22（SSH，限定你自己的 IP）**；**数据库、Redis、MinIO 端口一律走容器网络，不开放公网** |
| 5 | 购买云监控 + SLS | 免费版够用：CPU/内存/磁盘告警、SLB 后端健康、Nginx 访问日志投递 SLS |
| 6 | RDS 备份策略（可选） | 若后续把 MySQL 迁到 RDS，开启自动备份 + 7 天 binlog 保留 |

> 不买 SLB 就 1 台 ECS 也能跑，但高可用就没了；如果暂时预算有限，先单机跑通，后续加 SLB 不涉及代码改动。

---

## 2. ECS 初始化

```bash
# Alibaba Cloud Linux 3 / CentOS 系
sudo yum -y install git curl wget
curl -fsSL https://get.docker.com | bash
sudo systemctl enable --now docker
sudo usermod -aG docker $USER   # 重新登录生效

# 安装 Docker Compose v2（阿里云自带镜像源）
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL https://mirrors.aliyun.com/docker-toolbox/linux/compose/2.34.0/docker-compose-linux-x86_64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# 验证
docker --version
docker compose version

# 配置阿里云镜像加速（可选但强烈推荐）
sudo tee /etc/docker/daemon.json >/dev/null << 'EOF'
{
  "registry-mirrors": ["https://<你的阿里云专属加速地址>.mirror.aliyuncs.com"]
}
EOF
sudo systemctl daemon-reload
sudo systemctl restart docker

# 建目录
sudo mkdir -p /opt/art-assessment && sudo chown $USER:$USER /opt/art-assessment
```

---

## 3. 拉代码与配置

```bash
cd /opt/art-assessment
git clone -b dev https://github.com/Yuany-11/Art_assessment.git .

# 生产环境变量
cp deploy/.env.production.example .env
# 填 .env：DJANGO_SECRET_KEY、DB_PASSWORD、MYSQL_ROOT_PASSWORD、JWT_SECRET 都要换随机值
# 生成随机值：openssl rand -base64 48 | tr -d '\n' > /tmp/x && cat /tmp/x
vi .env

# 给脚本加执行权限
chmod +x deploy/deploy.sh deploy/rollback.sh deploy/backup.sh deploy/health-check.sh

# 建备份目录
mkdir -p deploy/backup
```

---

## 4. 首次部署

```bash
cd /opt/art-assessment

# 一键部署（会自动建 MySQL / Redis / MinIO 并迁移数据库）
IMAGE_TAG=v1.0.0 ./deploy/deploy.sh
```

部署成功后应该看到：
```
✅ 健康检查通过 ✅
✅ MySQL 备份完成
✅ 冒烟测试通过
🎉 部署成功 tag=v1.0.0
```

然后验证：
```bash
# 本机验证
curl http://127.0.0.1/health       # 200 + {"status":"ok"}
curl http://127.0.0.1/ready        # 200 + {"status":"ready"}
curl http://127.0.0.1/api/schema/   # 返回 OpenAPI JSON

# 公网验证（域名解析完成后）
curl http://你的域名/health
curl http://你的域名/
# 浏览器打开登录页，输入 Demo@123456 / 密码 .env 里 DEMO_PASSWORD
```

SlB 健康检查设置：
- 协议：HTTP
- 路径：`/ready`
- 超时：5 秒，间隔：10 秒
- 不健康阈值：3

---

## 5. 后续版本发布

```bash
cd /opt/art-assessment
IMAGE_TAG=v1.1.0 ./deploy/deploy.sh
```

脚本会自动：备份 → git pull → 构建新镜像 → 迁移 → 健康检查 → 冒烟测试。

---

## 6. 回滚

```bash
# 回滚到上一个版本（根据 deploy/backup 里最近的备份自动选）
./deploy/rollback.sh

# 回滚到指定 tag
./deploy/rollback.sh v1.0.0
```

> 数据库迁移如果已经在新版本迁移了 Schema，单纯回滚镜像可能不兼容。**上线前请确保下一个版本的迁移只加字段、不删字段**；如需删字段，发新版本先废弃旧字段，再在下下个版本删除。

---

## 7. 日常运维命令速查

```bash
cd /opt/art-assessment
COMPOSE="docker compose -f docker-compose.yml --env-file .env"

# 查看所有服务状态
$COMPOSE ps

# 查看日志（-f 持续追）
$COMPOSE logs -f --tail 200 web
$COMPOSE logs -f --tail 200 frontend
$COMPOSE logs -f worker scheduler

# 重启单个服务
$COMPOSE restart web

# 进入容器
docker exec -it art-web bash

# 手动跑迁移（脚本自动做，仅异常时）
$COMPOSE exec web python manage.py migrate --noinput

# 手动备份数据库
bash deploy/backup.sh

# 查看磁盘水位
df -h
```

---

## 8. 告警与监控

### 云监控配置项（在阿里云控制台）

| 指标 | 阈值 | 动作 |
|---|---|---|
| ECS CPU | ≥ 85% 持续 5 分钟 | 电话/短信告警 |
| ECS 内存 | ≥ 85% | 短信 |
| ECS 系统盘磁盘使用率 | ≥ 80% | 电话 |
| SLB 后端异常实例 | 1 | 电话 |
| SLB 4xx / 5xx 比例 | ≥ 5% | 短信 |
| Nginx 5xx（SLS 日志里聚合） | ≥ 10 次/5min | 短信 |

### 健康检查接入告警

```bash
# 每 15 分钟跑一次
crontab -e   # 粘贴 deploy/crontab.txt 内容

# 手动验证
bash deploy/health-check.sh
```

### SLS 日志采集（可选）

阿里云 SLS 安装 logtail 后，采集：
- `/var/lib/docker/containers/*/*-json.log`（容器 stdout/stderr）
- `/var/log/nginx/access.log`、`/var/log/nginx/error.log`（如果把 nginx 日志挂到宿主机）

---

## 附录：迁移到 RDS / 云 Redis

当单机压力上来时可以拆分基础设施，应用服务改动极小：

```env
# .env 里把容器地址换成云产品域名
DB_HOST=xxx.mysql.rds.aliyuncs.com
DB_PORT=3306
REDIS_URL=rediss://user:pass@xxx.redis.rds.aliyuncs.com:6379/0
MINIO_ENDPOINT=oss-cn-hangzhou.aliyuncs.com   # 也可以迁到 OSS
```

`docker-compose.yml` 里移除 `mysql:` / `redis:` / `minio:` 三个服务段，`web` 依赖也一起删掉即可。

迁移步骤：
1. RDS 开启只读账号 + 内网白名单放 ECS VPC CIDR
2. 从容器 `mysqldump` 导出，`mysql` 导入 RDS
3. 改 `.env` 指向 RDS 域名，重启容器
4. 验证通过后再停掉本地 MySQL 容器
