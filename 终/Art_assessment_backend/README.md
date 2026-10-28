# 艺术素质测评系统 · 后端

> 项目更改记录见 [../CHANGELOG.md](../CHANGELOG.md)。

从 `Art_assessment` 仓库中独立出来的 Django 后端工程，可单独安装、运行和部署。

## 技术栈

- Python 3.11+、Django 5.2、Django REST Framework
- MySQL 8、Redis（缓存与 RQ 队列）、MinIO（对象存储）
- JWT 鉴权、drf-spectacular（OpenAPI 文档）
- pytest + pytest-django

## 本地运行

```bash
# 1. 创建并激活虚拟环境
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 2. 安装本地依赖（不含 mysqlclient，Windows 无需编译工具）
pip install -r requirements-local.txt

# 3. 初始化数据库
python manage.py migrate

# 4. 启动开发服务
python manage.py runserver
```

本地演示**不需要** MySQL / Redis / MinIO，也**不需要 `.env`**：
`config.settings.dev` 默认使用 SQLite（`db.sqlite3`）、进程内缓存和 `media/` 本地文件存储。
默认服务地址为 `http://127.0.0.1:8000`。

需要自定义配置时再复制环境文件：

```bash
cp .env.example .env     # .env.example 已按 SQLite + LocMem + local 配置
```

切换 MySQL / Redis / MinIO 时，在 `.env` 中设置 `DB_ENGINE=mysql`、`CACHE_BACKEND=redis`、
`FILE_STORAGE=minio`，并改用 `pip install -r requirements.txt`
（Windows 安装 mysqlclient 需要 MySQL 客户端库或 Visual C++ Build Tools）。

## 初始化数据

首次部署推荐一条命令：

```bash
python manage.py bootstrap_demo
```

它按固定顺序执行 `migrate` 与全部 `seed_*`（可重复执行）。顺序不能调整：
`seed_all_portals` 会自动组卷（含音频/图片上传题），题库必须先就绪，否则新库会报
「题库题目不足：audio_upload 需要 1 道」。只想先看界面可加 `--skip-bank`。

也可以逐步执行：

```bash
python manage.py migrate
python manage.py seed_menus             # 角色菜单
python manage.py seed_organizations     # 演示省/市/区县/学校
python manage.py seed_demo_accounts     # 七类角色演示账号（密码默认 Demo@123456）
python manage.py seed_demo              # 演示课程、试题、班级、试卷与测评
python manage.py seed_question_bank     # 音乐/美术共 3600 道题（自动补章节知识讲解）
python manage.py seed_rich_demo         # 丰富的分类题库、自动组卷、测评、作答与学情报告
python manage.py seed_all_portals       # 为所有学生 / 教师账号补齐各功能页面数据
python manage.py seed_classes           # 演示中学新增 4 个班、每班 20 名学生（可重复执行）
python manage.py seed_primary_classes   # 九年一贯制学校补充小学部 2 个班（可重复执行）
python manage.py seed_chapter_knowledge # 单独补充趣味课堂的章节知识讲解（可重复执行）
python manage.py realify_demo_data      # 换成真实学校/姓名/题目（保留业务记录，bootstrap_demo 已包含）
python manage.py realify_demo_data --purge-records  # 可选：同时清空演示业务记录（仅首次清理时用）
```

`seed_demo_accounts` 默认密码为 `Demo@123456`，可用 `DEMO_PASSWORD` 覆盖；`seed_demo` 创建的
`teacher` / `student` / `student2` 账号本身就带有班级、试卷、测评和成绩数据，适合直接联调前端。
`realify_demo_data` 会把测试教师 `teacher`（陈志远）挂到测试学生 `student`（王浩然）所在的
七年级（1）班 `C20260701`，教师发布的测评和试卷对该班学生可见。

`seed_rich_demo` 可重复执行，会补充 100 道音乐/美术分类试题（含待审核题）、5 张自动组卷试卷、
5 场已发布测评（其中音乐/美术各 1 场正在进行）、学生历史答卷与评分，为 4 名学生生成学情报告，
并生成两张演示证书（student 音乐、student_001 美术）和 6 件课外美术作品。

`seed_all_portals` 在 `seed_rich_demo` 之后执行，可重复运行，覆盖全部演示账号的功能页面：

- 四个教学组合（两个班级 × 音乐/美术）：每组 1 张手工组卷、3 张自动组卷（均已审核通过并用于测评）、
  1 张实践作品上传体验卷（含图片/音频上传题），班级 1 的两个组合另各有 1 张待审核试卷
  （题库管理员可在试卷审核页处理），共 22 张新试卷、20 场测评。
- 每名学生：音乐、美术两个学科均有历史成绩、错题、学情报告、成长曲线和证书；每个班级各有
  1 场进行中的综合测评和 1 场进行中的实践作品上传测评；每名学生均有音乐与美术两类课外作品。
- 每位教师：班级与学生、已审核/待审核试卷、进行中与已结束测评、待评分任务、成绩、统计、
  证书、题库与通知均有数据；`teacher_art` 同时承担两个班级的美术课。
- 两个班级各有一条待审核的转班申请，供教师端「班级申请」页演示。

`seed_question_bank` 可重复执行（再次执行为 0 新增），为七年级音乐、美术各补充：

| 题型 | 音乐 | 美术 | 说明 |
| --- | --- | --- | --- |
| 单选题 | 1000 | 1000 | 四选一，含乐理、欣赏、乐器、美术史、色彩等 |
| 多选题 | 500 | 500 | 五选三，选项与答案固定去重 |
| 简答题 | 200 | 200 | 参考答案按要点给出，人工评分 |
| 实践题 | 50（唱歌，音频上传） | 50（绘画，图片上传） | `audio_upload` / `image_upload` |
| 合计 | 1750 | 1750 | 全部为已通过审核状态 |

题目按人教版七年级音乐、人美版七年级美术的课标主题整理，使用结构化模板生成，
不是逐字抓取某一网站的题库。

`seed_classes` 在「演示中学」下补充七年级（2）（3）班和八年级（1）（2）班，
每班 20 名学生，并把音乐 / 美术教师挂到班级上。学生账号形如 `student_7_2_01`，
密码默认 `Demo@123456`（可用 `DEMO_PASSWORD` 覆盖），可用 `--per-class` 调整人数、
`--school-code` 指定学校；命令可重复执行，不会重复创建。

`seed_primary_classes` 在真实学校的九年一贯制校区补充小学部三年级（1）班
`C20260301`、六年级（1）班 `C20260601`，每班 20 名学生，账号形如
`student_3_1_01`；命令可重复执行，已有班级和学生不会重复创建。

`realify_demo_data` 用于在演示结束后交付一份干净的数据：默认只合并重复的演示组织树
和「七年级（1）班」，把学校改为「成都市石室联合中学蜀华分校」
（四川省 / 成都市 / 青羊区，九年一贯制，蜀华街 43 号），教师、管理员和学生改为真实姓名，
删除 `[演示]` 试题与课程，并去掉题干的 `【音乐】/【美术】` 前缀。
首次清理演示记录时加 `--purge-records`，才会删除试卷、测评、答卷、成绩、证书、错题、
学情报告、通知、审核 / 操作日志、入班申请、导入任务及其上传文件。
支持 `--dry-run` 预览，可重复执行；建议在所有 `seed_*` 命令之后运行一次。
清理后试卷、测评、成绩等列表为空，需要时重新运行 `seed_*` 即可再次生成演示记录；
再次运行时不要加 `--purge-records`，否则会连同新产生的业务记录一起删除。

### 自动组卷与上传

- 自动组卷总分固定为 100 分，按实际题数分配；单题分值权重为
  单选 < 多选 < 简答 < 实践（图片/音频），四舍五入后自动调整最后一道题保证总分恰好 100。
- 学生随机练习固定生成 10 题：6 道单选、3 道多选、1 道实践题
  （音乐为音频上传，美术为图片上传），不抽简答题，避免练习中出现需要教师人工评分的题目；
  练习卷交卷后按客观题即时给出成绩，实践题不计入分数、也不会出现在教师评分任务里。
- 交卷时若试卷含简答题等人工评分题，只记录客观题得分并进入「待评分」，
  不生成成绩、不显示总分；教师在评分页完成终评后才生成成绩并在学生端公布。
- 学生作答页支持单选、多选、判断、填空、简答以及图片/音频作品上传；
  音乐实践题可以直接用麦克风录音，前端转成 WAV 后经 `POST /files`（`category=other`）保存，
  并通过 `/media/` 提供访问。文件服务支持 MP3 / WAV / M4A / WEBM / OGG 音频，
  `other` 分类单文件上限 20 MB。
- 作答过程中可「保存并退出」，答案写入服务端；再次进入同一测评会继续原答卷并保留已答内容。
- 试题审核和试卷审核都只在题库管理端处理：其他角色只能创建、提交和查看审核记录，
  `POST /papers/{id}/review` 仅允许 `question_admin` 调用。

## 测试

```bash
pytest
```

测试使用 `config.settings.test`：内存 SQLite、本地内存缓存、临时媒体目录，不依赖外部服务。

## 音乐测评模型

`ai/music_evaluation/` 目录来自 GitHub 仓库 `Yuany-11/Art_assessment` 的 `music_evaluation`
分支，包含：

- `music_analysis/`：基于 librosa 的音乐分析服务（调性、节奏、动态、结构、情绪等），可独立运行。
- `schemas/`、`scripts/`、`tests/`：输出契约、评测脚本与回归测试。
- `training/runs/`：6 次训练产出的 `best_model.pt` 及 `config/labels/metrics`（最新为
  `20261026-120656`，任务为 genre / emotion / mode / BPM）。

独立启动分析服务：

```bash
cd ai/music_evaluation
pip install -r requirements.txt      # numpy / librosa / soundfile
python -m music_analysis.api --host 127.0.0.1 --port 8090
# 打开 http://127.0.0.1:8090/ui/ 可直接上传测试
```

> 注意：`training/score.py` 依赖的 `training/infer.py`、`training/features.py` 和
> `scoring/rubric.default.json` 未包含在该分支中，因此 `.pt` 权重目前无法直接加载推理；
> `music_analysis/` 是分支内完整可运行的部分。该服务与主后端
> `/api/v1/ai/music/analyze` 的适配也尚未接入。

## 接口文档

- OpenAPI Schema：`GET /api/schema/`
- 业务接口前缀：`/api/v1/`
- Django Admin：`/admin/`

## 目录结构

```text
api/v1/           API 路由汇总
apps/             业务应用
  accounts/       账号、角色、菜单、导入任务
  organizations/  省/市/区县/学校组织架构
  classes/        班级与课程
  qbank/          题库、章节、题目、日志
  exams/          测评、答卷、评分、报告
  files/          文件上传与 MinIO 存储
common/           鉴权、权限、分页、异常、审计等公共组件
config/           Django 配置（base / dev / prod / test）
conftest.py       pytest 公共 fixture
manage.py         命令行入口
```

## 生产部署

```bash
# 容器构建（需在包含 .env 的目录执行，或通过 --env-file 指定）
docker build -t art-assessment-backend .

# 启动
gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 --workers 2 --timeout 120
```

生产环境需设置 `DJANGO_SETTINGS_MODULE=config.settings.prod`，并在启动前执行：

```bash
python manage.py migrate --noinput
python manage.py collectstatic --noinput
```
