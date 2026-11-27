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
python manage.py seed_sichuan_organizations # 四川 21 市州、45 区县、37 所学校
python manage.py seed_demo_accounts     # 七类角色演示账号（密码默认 Demo@123456）
python manage.py seed_demo              # 演示课程、试题、班级、试卷与测评
python manage.py seed_question_bank     # 七年级音乐/美术 3500 道题（自动补章节知识讲解）
python manage.py seed_grade_question_bank # 1~9 年级分层题库 900 道（每年级每科 50 道，按年级难度）
python manage.py seed_rich_demo         # 丰富的分类题库、自动组卷、测评、作答与学情报告
python manage.py rebalance_question_grades # 按难度把题库均衡到各年级（每级约 500 道）
python manage.py seed_all_portals       # 为所有学生 / 教师账号补齐各功能页面数据
python manage.py seed_classes           # 演示中学新增 4 个班、每班 20 名学生（可重复执行）
python manage.py seed_primary_classes   # 九年一贯制学校补充小学部 2 个班（可重复执行）
python manage.py seed_chapter_knowledge # 单独补充趣味课堂的章节知识讲解（可重复执行）
python manage.py seed_curriculum_units  # 按 1~9 年级教材单元重建章节与单元练习（每单元 23~25 题）
python manage.py classify_question_chapters # 把其他题归入教材单元或“拓展类”
python manage.py organize_question_bank # 题库去重、下线填空题，并按知识点把拓展题归入章节
python manage.py clean_question_stems   # 去掉题干中的单元/年级/变式等生成标签
python manage.py seed_class_assessments # 为每个班级补齐音乐/美术正式测评与练习测评（可重复执行）
python manage.py realify_demo_data      # 换成真实学校/姓名/题目（保留业务记录，bootstrap_demo 已包含）
python manage.py seed_teacher_roster    # 每班一位独立班主任 + 音乐/美术教师账号
python manage.py realify_demo_data --purge-records  # 可选：同时清空演示业务记录（仅首次清理时用）
```

`seed_demo_accounts` 默认密码为 `Demo@123456`，可用 `DEMO_PASSWORD` 覆盖；`seed_demo` 创建的
`teacher` / `student` / `student2` 账号本身就带有班级、试卷、测评和成绩数据，适合直接联调前端。
`realify_demo_data` 会把测试教师 `teacher`（陈志远）挂到测试学生 `student`（王浩然）所在的
七年级（1）班 `C20260701`，教师发布的测评和试卷对该班学生可见。

与测试学生同班的测试老师账号：`teacher / Demo@123456`（七年级（1）班班主任）、
`teacher_music / Demo@123456`（该班音乐老师）、`teacher_art / Demo@123456`（该班美术老师）。
测试学生 `student`、`student_001` 等也在该班，登录页快捷账号栏的四个身份全部来自该班。
`seed_teacher_roster` 保证每个班级只有一位班主任、一位音乐教师和一位美术教师，
且同一位教师不会同时担任两个班级的班主任；9 个教师账号都有班级任课信息。
每班每学科只允许一位科任老师，教师只能操作本人任教学科的试卷、试题、测评与成绩。

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
| 实践题 | 50（唱歌，音频上传） | 50（绘画，图片上传） | `audio_upload` / `image_upload` |
| 合计 | 1550 | 1550 | 全部为已通过审核状态 |

题目按人教版七年级音乐、人美版七年级美术的课标主题整理，使用结构化模板生成，
不是逐字抓取某一网站的题库。系统已取消简答题，题库、组卷、作答和人工评分均不再包含简答题。

`seed_grade_question_bank` 为一年级到九年级的每个年级单独建册（音乐、美术各一套课程），
每年级每科 45 道（30 单选、12 多选、3 实践），共 810 道；七年级沿用已有课程，
只补充缺少的题目，不会重复。题目按人教版音乐、人美版美术各年级教材的作品与知识点整理。

`seed_curriculum_units` 按教材单元重建 1~9 年级音乐、美术章节：音乐 1~6 年级每年级
6 个单元，音乐 7~9 年级和美术各年级每年级 5 个单元，另设“拓展类”章节。每个单元包含
单元概述、学习目标、知识结构、重点作品、核心概念、相关概念、易错提醒、
学习方法与课堂任务，并生成 7~9 道单选、3 道多选、12 道判断、1 道实践题，
共 23~25 道单元练习。填空题已整体下线，不再生成或抽取。每个单元只聚焦
一个重点作品与一个核心概念，避免不同单元出现相同题目。题库按年级分册，
组卷与随机练习只抽取同年级题目；
不再使用跨年级回退。题干在入库前统一经 `clean_stem()` 清理，
不再带“【单元练习】”“【音乐·七年级】”“（变式 2）”“（拓展练习）”等生成标签。

`classify_question_chapters` 把单元练习之外的题目按内容归类：题干、选项或解析中
命中教材单元的重点作品、核心概念或章节名称时，移入对应单元章节；没有命中的题目
统一放入该课程的“拓展类”章节。命令幂等，支持 `--dry-run`、`--subject`、`--grade`。

`organize_question_bank` 用于一次性整理历史题库：先整体下线填空题，再按清洗后的题干
全局去重（同题干只保留一条，优先保留已被试卷引用、位于章节内、已通过审核的题），
最后按学科跨年级匹配章节知识中的作品名与核心概念，把“拓展类”或未绑定章节的题
归入知识点最相关的章节，并同步修正年级与课程；仍匹配不到的题保留为“拓展类”。
命令幂等，支持 `--dry-run` 统计影响范围。

`seed_class_assessments` 按班级任课关系为音乐、美术各生成一张正式卷和一张练习卷，
提交题库管理员审核后由任课教师发布到本班，保证学生端「正式测评 / 练习测评」都能查到
数据。每张卷为 6 单选 + 3 多选 + 1 实践作品题、合计 100 分；命令幂等，重复执行只补缺失项，
可用 `--class-code` 只处理指定班级。

`seed_sichuan_organizations` 初始化四川 21 个市州（官方行政区划代码）、45 个区县和
37 所学校，已存在的组织按编码更新，不会重复创建。

题库、课程章节和组卷统一按 1~9 年级分册，题目只抽取同年级内容；难度仅作为题目内部
元数据保留，教师端试题库和学生端知识页不再展示或按难度筛选。命令可重复执行，默认
`--grades 1-9`，也可用 `--grades 3,6`、`--subject music`、`--single 30` 等参数只补
某几个年级或调整题量。

`seed_classes` 在「演示中学」下补充七年级（2）（3）班和八年级（1）（2）班，
每班 20 名学生，并把音乐 / 美术教师挂到班级上。学生账号形如 `student_7_2_01`，
密码默认 `Demo@123456`（可用 `DEMO_PASSWORD` 覆盖），可用 `--per-class` 调整人数、
`--school-code` 指定学校；命令可重复执行，不会重复创建。

`seed_primary_classes` 在真实学校的九年一贯制校区补充小学部三年级（1）班
`C20260301`、六年级（1）班 `C20260601`，每班 20 名学生，账号形如
`student_3_1_01`；命令可重复执行，已有班级和学生不会重复创建。

`seed_teacher_roster` 为 7 个演示班级各配置一名独立班主任，并保证每班有且只有
一位音乐教师、一位美术教师。除 `teacher`（七年级（1）班班主任）、`teacher_music`
（李静，七年级（1）班音乐）、`teacher_art`（赵敏，七年级（1）班美术）外，还创建 `teacher_wang`（王海涛）、
`teacher_liu`（刘雅琴）、`teacher_zhou`（周晓梅）、`teacher_zhang`（张建国）、
`teacher_he`（何晓燕）、`teacher_luo`（罗文静）六个班主任账号，密码统一为
`Demo@123456`。班级原有测评会同步转交给新的任课教师；命令可重复执行，并输出
“每班一位班主任、一位音乐教师、一位美术教师”的检查结果。

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

- 教师自动组卷时先从本人任教的班级中选择班级，再按「年级 → 章节（课程）→ 单元（章节）」
  逐级多选缩小抽题范围；年级全选或留空时不限制年级，该学科题库中所有已通过试题都可被抽取。
  试卷归属年级仍与任教班级一致，抽题范围允许跨年级。
- 自动组卷总分固定为 100 分，按实际题数分配；单题分值权重为
  单选 < 多选 < 实践（图片/音频），四舍五入后自动调整最后一道题保证总分恰好 100。
- 学生随机练习固定生成 10 道客观题：6 道单选、3 道多选、1 道判断，
  共 100 分按题数平均分配，不含简答题与实践作品题；
  练习卷交卷后即时给出成绩，也不会产生教师评分任务。
- 交卷时若试卷含实践作品题，只记录客观题得分并进入「待评分」，
  不生成成绩、不显示总分；教师在评分页完成终评后才生成成绩并在学生端公布。
- 人工评分只处理实践作品题（图片/音频上传）和课外作品；课外作品在教师端「学生管理 →
  课外学习材料」中按 0~100 分评分并填写评语，学生端可查看分数与评语。
- 学生作答页支持单选、多选、判断以及图片/音频作品上传；
  音乐实践题可以直接用麦克风录音，前端转成 WAV 后经 `POST /files`（`category=other`）保存，
  并通过 `/media/` 提供访问。文件服务支持 MP3 / WAV / M4A / WEBM / OGG 音频，
  `other` 分类单文件上限 20 MB。
- 作答过程中可「保存并退出」，答案写入服务端；再次进入同一测评会继续原答卷并保留已答内容。
- 学生交卷后可进入试卷阅览页查看逐题作答、得分和教师评语；标准答案与解析按测评的
  `showAnswerMode` 控制：`never` 不展示、`after_submit` 交卷后展示、`after_end` 截止后展示。
  接口为 `GET /api/v1/attempts/{id}/review`，未提交答卷返回 409。
- 已审核通过的试卷可以重复用于发布新测评；只有已归档试卷不能再次发布。
- 教师端班级、学生、测评、试卷、成绩、证书、评分任务和学习报告均限定在本人任教班级
  与任教学科内；班级列表和详情返回 `myIdentity`，显示当前用户在该班的身份。
- 试题审核和试卷审核都只在题库管理端处理：其他角色只能创建、提交和查看审核记录，
  `POST /papers/{id}/review` 仅允许 `question_admin` 调用。

## 测试

```bash
pytest
```

测试使用 `config.settings.test`：内存 SQLite、本地内存缓存、临时媒体目录，不依赖外部服务。

## 评分方式

系统只支持自动判分与教师人工评分：客观题交卷即自动判分，实践作品题（图片/音频上传）
和课外作品由教师人工评分。原外部 AI 评分适配层、模型评分规则库及其接口、AI 评分字段
与配置项（`AI_PROVIDER`、`AI_BASE_URL`、`AI_TIMEOUT_SECONDS`）均已移除，
判分链路不依赖任何本地模型文件或外部 AI 服务（音频标签模型仅作教学辅助，
不参与判分，见下节）。

## 音频标签辅助（arteval-v4）

系统接入 `arteval-v4` 音乐标签模型作为**教学辅助**：为题库音频、学生音频作品和
实践作品题生成曲风、情绪、调式、BPM 及削波/静音等标签，并支持题目按标签检索、
“相似音频题目”推荐和教师评分页参考卡。

模型不参与自动判分，不写入 `Attempt` / `AttemptAnswer` / `Score`，规则参考分只对
教师展示且不会自动填分。模型服务独立运行在 `http://127.0.0.1:8100`，未启动时系统
自动降级，上传、组卷、判分和成绩等功能不受影响。

```bash
# 1. 安装模型依赖（在 arteval-v4 目录创建 venv）
python -m venv .venv
.venv\Scripts\pip install -r arteval-v4\requirements-service.txt

# 2. 启动推理服务
arteval-v4\arteval-v4\start_service.bat

# 3. 可选：批量补齐历史音频标签
python manage.py analyze_audio --dry-run
python manage.py analyze_audio
```

配置项：`AUDIO_TAGGER_ENABLED`、`AUDIO_TAGGER_URL`、`AUDIO_TAGGER_TIMEOUT`。
详细接口、限制及与现有功能的冲突审计见 [docs/audio-tagging.md](docs/audio-tagging.md)。

## 美术 AI 出题辅助（Model B）

`01_给后端A(1)` 中的 Qwen2.5-3B + QLoRA 美术出题模型作为**待审题草稿来源**接入：
默认只接受单选、判断，所有生成/导入题固定 `pending`，由题库管理员审核后才进入公共题库；
不参与组卷和判分，填空题、简答题按现有规则丢弃。

```bash
# 离线导入交付题库（不需要 GPU）
python manage.py import_qgen_bank --dry-run
python manage.py import_qgen_bank

# 在线生成（需要 8002 服务和 QGEN_ENABLED=true）
python manage.py generate_qgen_questions --unit g7-u2 --knowledge-point 色相 \
  --type single_choice --difficulty 1 --count 3
```

配置项：`QGEN_ENABLED`（默认 false）、`QGEN_URL`、`QGEN_TIMEOUT`、`QGEN_TOKEN`、
`QGEN_BANK_PATH`、`QGEN_UNIT_MAP_PATH`。接口为
`GET /api/v1/questions/qgen/catalog`、`POST /api/v1/questions/qgen/generate`。
单元映射在 `apps/qbank/qgen_unit_map.json`，详细说明与质量边界见
[docs/model-b-qgen.md](docs/model-b-qgen.md)。

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
