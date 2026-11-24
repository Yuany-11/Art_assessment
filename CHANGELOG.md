# 艺术素质测评系统 · 更改记录

> 记录范围：`C:\Users\ter\Desktop\终` 下的 `Art_assessment_backend`（Django）与
> `Art_assessment_frontend`（Vue 3）两个工程。
>
> 记录方式：按时间顺序记录，最新更改追加到文末「最新更改」区域顶部；每次更改注明编号、
> 类型、涉及文件、原因、影响和验证方式。
> 未特别说明时，所有验证均在本地环境完成：后端 `127.0.0.1:8000`，前端 `127.0.0.1:5173`，
> 数据库 SQLite，缓存 LocMem，文件存储本地 `media/`。
>
> 最后更新：2026-11-19 16:51
>
> 本文件建立于本次前后端联调迭代，记录该阶段对项目所做的更改；后续更改继续按模板追加。

---

## 目录

1. [本次迭代摘要](#1-本次迭代摘要)
2. [环境与前后端联调](#2-环境与前后端联调)
3. [后端更改](#3-后端更改)
4. [前端更改](#4-前端更改)
5. [AI 音乐测评模型](#5-ai-音乐测评模型)
6. [演示数据体系](#6-演示数据体系)
7. [验证记录](#7-验证记录)
8. [已知限制与后续待办](#8-已知限制与后续待办)
9. [复现步骤](#9-复现步骤)
10. [后续记录模板](#10-后续记录模板)

---

## 1. 本次迭代摘要

本次迭代的目标是：让前后端在**不依赖 MySQL / Redis / MinIO** 的本地环境中真实联调，
为所有演示账号补齐可直接展示的功能数据，并把音乐测评模型纳入工程。

主要结果：

| 编号 | 类别 | 摘要 | 状态 |
| --- | --- | --- | --- |
| ENV-001 | 配置 | 后端切换为 SQLite + LocMem + 本地文件存储 | 已完成 |
| ENV-002 | 配置 | 前端关闭 mock，通过 Vite 代理访问真实后端 | 已完成 |
| ENV-003 | 前端 | 登录页按角色自动填入真实演示账号与密码 | 已完成 |
| BE-001 | 数据 | 新增 `seed_rich_demo`：100 道分类试题、组卷、测评、答卷、报告、证书、作品 | 已完成 |
| BE-002 | 数据 | 新增 `seed_all_portals`：覆盖全部学生/教师账号的所有功能页面 | 已完成 |
| BE-003 | 清理 | 修正 `seed_rich_demo` 重复导入与过时文档说明 | 已完成 |
| AI-001 | 模型 | 从 GitHub `music_evaluation` 分支导入音乐分析代码与训练产物 | 已完成（未接入业务） |
| DOC-001 | 文档 | 新增本更改记录，补充后端 README 初始化说明 | 已完成 |
| DATA-002 | 数据 | 新增 `seed_question_bank`：音乐/美术各 1750 道，共 3500 道 | 已完成 |
| BE-004 | 后端 | 自动组卷固定 100 分，按题数分配且单选 < 多选 < 简答 < 实践 | 已完成 |
| FE-002 | 前端 | 作答页支持全题型与图片/音频作品上传，评分页可预览 | 已完成 |
| FE-003 | 前端 | 作答中可「保存并退出」，重新进入续答 | 已完成 |
| BE-005 | 权限 | 试题审核统一到题库管理端，移除其他端口入口 | 已完成 |
| DATA-003 | 数据 | 新增 4 张实践作品上传卷与 4 场进行中测评 | 已完成 |
| DOC-002 | 文档 | 更新前后端 README 与本更改记录 | 已完成 |
| FE-004 | 前端 | 题库查询支持全题型与分页容量；学生测评显示「继续作答」 | 已完成 |
| BE-006 | 后端 | 测评列表 / 详情返回当前学生的答卷状态 | 已完成 |
| FE-005 | 前端 | 移除其他端口的试卷审核入口与审核按钮 | 已完成 |
| BE-007 | 后端 | 试卷审核权限和审核人统一到题库管理员 | 已完成 |
| DATA-004 | 数据 | 新增 `seed_classes`：4 个班级、每班 20 名学生 | 已完成 |
| FE-006 | 前端 | 登录页取消「先选工作端」，改为按账号角色直接登录并提供测试账号快捷填入 | 已完成 |
| FE-007 | 前端 | 音乐实践题新增浏览器录音上传，自动转 WAV | 已完成 |
| BE-008 | 后端 | 文件上传支持 WEBM / OGG 音频 | 已完成 |
| DATA-005 | 数据 | 清理演示业务记录，学校/班级/师生改为真实信息，题目去除演示标记 | 已完成 |
| DATA-006 | 数据 | 测试教师与测试学生编入同一班级，教师发布的测评学生可见 | 已完成 |
| BE-009 | 后端 | 随机练习固定 6 单选 + 3 多选 + 1 实践题，不含简答题 | 已完成 |
| BE-010 | 后端 | 含简答题的测评交卷后待教师终评，再生成并公布成绩 | 已完成 |
| FE-008 | 前端 | 交卷后按是否已出分跳转，待评分时提示并返回测评列表 | 已完成 |

前七项（ENV / BE-001~003 / AI / DOC-001）以配置、演示数据命令、登录联调体验和文档为主，
未改动核心业务流程；DATA-002 及之后的条目改动了组卷计分、作答、上传、权限与演示数据。

---

## 2. 环境与前后端联调

### ENV-001 后端本地化运行配置

**类型**：修改配置

**涉及文件**

- `Art_assessment_backend/.env`
- `Art_assessment_backend/config/settings/dev.py`
- `Art_assessment_backend/config/settings/base.py`

**更改内容**

1. 开发环境支持 `DB_ENGINE=sqlite`，无需安装 MySQL：
   - `config/settings/dev.py` 根据环境变量切换为 `django.db.backends.sqlite3`；
   - 数据库文件为 `Art_assessment_backend/db.sqlite3`。
2. 缓存支持 `CACHE_BACKEND=locmem`：
   - `config/settings/base.py` 在 locmem 模式下使用 `LocMemCache`，否则仍使用 Redis。
3. 文件存储支持 `FILE_STORAGE=local`：
   - 上传、证书、学生作品写入 `Art_assessment_backend/media/`；
   - 仍保留 MinIO 配置分支，生产环境可切回。
4. `.env` 写入本地联调参数：
   - `DJANGO_SETTINGS_MODULE=config.settings.dev`
   - `DJANGO_DEBUG=true`
   - `DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost`
   - `DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`
   - `DB_ENGINE=sqlite`
   - `CACHE_BACKEND=locmem`
   - `FILE_STORAGE=local`
   - `DEMO_PASSWORD=Demo@123456`
   - 本地 JWT 密钥与有效期。

**原因**

原默认配置依赖 MySQL、Redis、MinIO，本地启动成本高，无法快速联调前端。

**影响**

- 后端可在只有 Python 环境的机器上直接 `migrate`、`runserver`。
- 演示账号统一密码为 `Demo@123456`，与前端登录页一致。
- 生产配置不受影响，仍可通过环境变量切回 MySQL / Redis / MinIO。

**验证**

- `python manage.py check` 通过；
- `python manage.py migrate` 正常创建 `db.sqlite3`；
- 登录、上传作品、生成证书、下载 PDF 均在本地完成。

---

### ENV-002 前端关闭 mock 并接入真实后端

**类型**：修改配置

**涉及文件**

- `Art_assessment_frontend/.env`
- `Art_assessment_frontend/.env.example`
- `Art_assessment_frontend/vite.config.ts`
- `Art_assessment_frontend/src/api/client.ts`
- `Art_assessment_frontend/src/api/index.ts`

**更改内容**

1. `.env` / `.env.example`：
   - `VITE_API_BASE_URL=/api/v1`
   - `VITE_USE_MOCK=false`
   - `VITE_APP_TITLE=艺术素质测评系统`
2. Vite 开发服务器增加 `/api` 代理：
   - `/api` → `http://127.0.0.1:8000`
   - `changeOrigin: true`
   - 开发端口 `5173`。
3. Axios 使用环境变量作为 `baseURL`，默认 `/api/v1`。
4. mock 开关只在显式配置 `VITE_USE_MOCK=false` 时关闭：
   - `const useMock = import.meta.env.VITE_USE_MOCK !== 'false'`
   - 避免忘记配置时误连真实后端。
5. 真实请求自动携带 `Authorization: Bearer <token>`，并对 401 做刷新令牌重试；
   业务响应按统一信封 `{code, message, data}` 解包。

**原因**

项目原先默认使用内置 mock，无法验证真实接口与数据。

**影响**

- 前端所有页面请求真实 Django 接口；
- 登录后使用 JWT，刷新令牌失效时自动退出；
- 开发时修改 `.env` 需要重启 Vite。

**验证**

- 浏览器 Network 中 `/api/v1/*` 请求由 5173 代理到 8000；
- 登录返回真实 `token`、`refreshToken` 与用户信息；
- 学生/教师/管理员页面数据与数据库一致。

---

### ENV-003 登录页按角色自动填充演示账号

**类型**：修改前端交互

**涉及文件**

- `Art_assessment_frontend/src/views/LoginView.vue`

**更改内容**

1. 七类角色分别配置 mock 账号与真实演示账号：

   | 角色 | 真实演示账号 |
   | --- | --- |
   | 学生 | `student` |
   | 教师 | `teacher` |
   | 学校管理员 | `school_admin` |
   | 区县管理员 | `district_admin` |
   | 市州管理员 | `city_admin` |
   | 省级管理员 | `province_admin` |
   | 题库管理员 | `question_admin` |

2. 真实模式下统一密码为 `Demo@123456`，页面展示“测试密码”。
3. 点击右侧身份卡后：
   - 自动填入该角色的演示账号；
   - 自动填入密码；
   - 直接进入第二步。
4. mock 模式与真实模式分离：
   - mock 模式仍使用原 mock 账号与 `Abc@123456`；
   - 真实模式不再校验“登录身份与账号不匹配”的 mock 逻辑。
5. 记住账号功能保留：
   - `localStorage` 键为 `art-assessment-last-username`；
   - 刷新页面后若记住的账号匹配某角色，会自动选中对应角色。

**原因**

联调时需要频繁切换七类角色，手动输入账号密码效率低且容易出错。

**影响**

- 打开登录页默认选中“学校管理”并填入 `school_admin`；
- 点击任意角色卡即可用对应演示账号登录；
- 不影响手动修改账号密码。

**验证**

- 七类角色逐一点击后，账号与密码均正确填入；
- 各角色登录后跳转到对应默认首页；
- 错误密码会显示后端返回的错误信息。

---

## 3. 后端更改

### BE-001 新增 `seed_rich_demo` 丰富演示数据命令

**类型**：新增管理命令

**文件**

- `Art_assessment_backend/apps/exams/management/commands/seed_rich_demo.py`

**命令**

```bash
python manage.py seed_rich_demo
```

**背景**

原有 `seed_demo` 只提供少量演示课程、题目和测评，无法覆盖分类题库、自动组卷、
历史成绩、学情报告、证书、课外作品等页面。

**新增内容**

1. **课程与章节**

   | 课程 | 学科 | 年级 | 章节 |
   | --- | --- | --- | --- |
   | 七年级音乐（人教版） | 音乐 | 7 | 乐理基础、视唱练耳、音乐欣赏、乐器与演奏 |
   | 七年级美术（人美版） | 美术 | 7 | 造型基础、色彩知识、中国书画、美术欣赏、设计与工艺 |

2. **100 道分类试题**

   | 学科 | 单选 | 多选 | 判断 | 填空 | 简答 | 合计 |
   | --- | ---: | ---: | ---: | ---: | ---: | ---: |
   | 音乐 | 22 | 8 | 9 | 8 | 8 | 55 |
   | 美术 | 16 | 7 | 8 | 8 | 6 | 45 |
   | 合计 | 38 | 15 | 17 | 16 | 14 | 100 |

   状态分布：

   - 已审核：96 道；
   - 待审核：3 道；
   - 已驳回：1 道。

   每道题包含题干、选项、标准答案、解析、难度、章节与分值；单选/多选选项会按题目内容
   旋转正确答案位置，避免答案集中在 A。

3. **自动组卷试卷 5 张**

   - 音乐 3 张、美术 2 张；
   - 使用 `create_auto_paper` 与学科规则 `MUSIC_RULES` / `ART_RULES`；
   - 覆盖不同难度与题型组合。

4. **已发布测评 5 场**

   | 学科 | 测评 | 时间 | 状态 |
   | --- | --- | --- | --- |
   | 音乐 | 阶段测评（一） | 60 天前 ~ 45 天前 | 已结束，有成绩 |
   | 音乐 | 阶段测评（二） | 20 天前 ~ 10 天前 | 已结束，有成绩 |
   | 音乐 | 综合测评 | 1 小时前 ~ 10 天后 | 进行中，可作答 |
   | 美术 | 阶段测评（一） | 40 天前 ~ 25 天前 | 已结束，有成绩 |
   | 美术 | 综合测评 | 1 小时前 ~ 14 天后 | 进行中，可作答 |

5. **学生答卷与评分**

   - 直接创建 `Attempt` 与 `AttemptAnswer`，再调用 `submit_attempt(..., auto=True)`
     走真实自动评分流程；
   - 对简答题调用 `submit_grading` 完成人工评分；
   - 覆盖正常作答、部分错题、未完成主观题等情况。

6. **学情报告 4 份**

   - 为学生 `student`、`student2`、`student_001`、`student_002` 生成；
   - 报告包含摘要、优势、薄弱点、建议、分数趋势；
   - 只统计正式测评（`paper_type=formal`）的已评分成绩，避免练习数据污染趋势。

7. **证书 2 张**

   - `student` 音乐、`student_001` 美术；
   - 仅对正式测评且已评分的成绩生成 PDF；
   - 已存在的证书默认跳过。

8. **课外美术作品 6 件**

   - 使用 Pillow 生成 960×640 PNG（渐变背景、色块与线条组合）；
   - 通过 `save_upload` 走真实文件存储与校验流程；
   - 写入 `FileObject`，分类为 `student_work`。

**幂等性**

- 课程、章节、题目、试卷、测评均按名称/标题查找后复用；
- 已有答卷不重复创建；
- 报告使用 `update_or_create`；
- 证书与作品按评估/学生/文件名判重。

**影响**

- 题库管理、自动组卷、试卷审核、测评发布、学生作答、成绩、报告、证书、作品页面
  均有可展示数据；
- 可重复执行，不会成倍增加数据。

**验证**

- 命令执行成功，输出新增题目/试卷/测评/报告数量；
- 100 道题在题库中可按学科、章节、题型筛选；
- 学生可开始进行中的测评；
- 学情报告趋势图有多个时间点；
- 证书可下载 PDF，作品可预览 PNG。

---

### BE-002 新增 `seed_all_portals` 全账号演示数据命令

**类型**：新增管理命令

**文件**

- `Art_assessment_backend/apps/exams/management/commands/seed_all_portals.py`

**命令**

```bash
python manage.py seed_all_portals
```

**背景**

`seed_rich_demo` 只覆盖了部分班级与学生。实际演示时，登录任意学生或教师账号，
其“我的测评、成绩、错题、报告、证书、作品、班级、试卷、评分、统计”等页面都应有点击
可见的数据。

**覆盖的四个教学组合**

| 班级 | 学科 | 教师 | 学生 |
| --- | --- | --- | --- |
| `DEMO-7-1`（七年级（1）班） | 音乐 | `teacher` | `student`、`student2` |
| `DEMO-7-1`（七年级（1）班） | 美术 | `teacher_art` | `student`、`student2` |
| `DEMO-ACC-7-1`（七年级（1）班） | 音乐 | `teacher_music` | `student_001`、`student_002` |
| `DEMO-ACC-7-1`（七年级（1）班） | 美术 | `teacher_art` | `student_001`、`student_002` |

> `teacher_art` 原只教 `DEMO-ACC-7-1` 美术；本命令追加 `ClassTeacher`，
> 使其同时承担 `DEMO-7-1` 美术课，从而两个班都有美术教学数据。

**每个教学组合创建的内容**

1. 试卷 5 张：
   - 1 张手工组卷；
   - 3 张自动组卷（阶段一、阶段二、随堂检测）；
   - 1 张待审核试卷（仅 `DEMO-7-1` 两个组合创建，共 2 张）。
2. 测评 4 场：
   - 阶段测评（一）：50 天前 ~ 40 天前，已结束；
   - 阶段测评（二）：15 天前 ~ 5 天前，已结束；
   - 随堂检测：3 天前 ~ 2 天前，留下未评分答卷；
   - 综合测评：1 小时前 ~ 14 天后，进行中。
3. 学生答卷 5 份：
   - 两名学生在两场历史测评中各 1 份，共 4 份已评分；
   - 1 份随堂检测只提交、不完成人工评分，用于教师“评分任务”页面。
4. 证书 2 张：
   - 阶段测评（二）按学生生成，两名学生各 1 张；
   - 已存在则跳过。
5. 试卷审核：
   - 手工卷与自动卷通过 `submit_review` + `review_paper` 审核通过；
   - 确保 `AssessmentsView` 的“已审核试卷”下拉框有数据。

**全量首次运行新增量**

| 数据 | 数量 |
| --- | ---: |
| 新试卷 | 18 |
| 新测评 | 16 |
| 新答卷 | 20 |
| 新证书 | 8 |
| 学情报告（写入/更新） | 8 |
| 课外作品 | 10 |
| 转班申请 | 2 |

其中 18 张试卷 = 4 张手工 + 12 张自动 + 2 张待审核。

**其他补齐内容**

1. 每名学生音乐、美术两个学科的学情报告：
   - `student`、`student2`、`student_001`、`student_002` 各 2 份；
   - 报告趋势只取正式测评成绩。
2. 每名学生 4 件课外作品：
   - 2 件音乐（歌唱练习、节奏创编）；
   - 2 件美术（原有作品保留，缺少的学生补齐）。
3. 两个班级各 1 条待审核转班申请：
   - `student2` 申请转入 `DEMO-ACC-7-1`；
   - `student_002` 申请转入 `DEMO-7-1`；
   - 供教师端“班级申请”面板演示。
4. 旧课程章节补建：
   - 对“有试题但没有章节”的课程创建“综合练习”章节；
   - 将该课程未归章试题挂入该章节；
   - 保证学生“趣味课堂”页面展开后不是空列表。

**幂等性**

- 试卷按“创建人 + 标题”查找；
- 测评按“发布人 + 标题”查找；
- 答卷按“测评 + 学生”判重；
- 证书按评估与学生判重；
- 报告 `update_or_create`；
- 作品按“上传人 + 文件名”判重；
- 转班申请按“班级 + 申请人 + 类型”判重。

> 注意：待审核试卷一旦被管理员审核通过，再次执行本命令不会把状态改回待审核。
> 若演示前需要“待审核”数据，可在重新审核前手动重置状态或使用新的标题。

**影响**

- 4 名学生登录后，音乐与美术两个学科均有历史成绩、错题、报告、证书、作品；
- 3 名教师登录后，班级、学生、试卷、测评、评分任务、成绩、统计、证书、通知均有数据；
- 学校管理员可看到待审核试卷并执行审核；
- 演示不再依赖某个特定账号。

**验证**

- 四个教学组合的试卷、测评、答卷、证书数量正确；
- 每名学生两个学科的报告中均有分数趋势；
- 每名学生均有进行中的测评可开始作答；
- 教师评分任务中存在未完成评分的答卷；
- 管理员试卷审核列表中存在待审核记录（首次运行后）。

---

### BE-003 清理 `seed_rich_demo` 重复导入与文档说明

**类型**：代码清理

**文件**

- `Art_assessment_backend/apps/exams/management/commands/seed_rich_demo.py`

**更改内容**

1. 删除重复的 `from apps.qbank.models import ...` 导入。
2. 修正模块文档中的题目状态说明：
   - 原文：100 道题，94 道已审核、6 道待审核；
   - 实际：96 道已审核、3 道待审核、1 道已驳回。

**原因**

重复导入不影响运行但会产生静态检查告警；文档数量与实际数据不一致，容易误导演示。

**验证**

- `python -m compileall` / 命令执行无导入错误；
- 题库状态统计与文档一致。

---

## 4. 前端更改

前端核心业务页面本次未改动，主要更改集中在联调配置与登录体验：

| 编号 | 文件 | 更改 |
| --- | --- | --- |
| ENV-002 | `.env`、`.env.example`、`vite.config.ts`、`src/api/client.ts`、`src/api/index.ts` | 关闭 mock、代理到 8000、真实请求封装 |
| ENV-003 | `src/views/LoginView.vue` | 七类角色自动填入演示账号与密码 |
| DOC-002 | `README.md` | 补充联调步骤、环境变量、演示账号表 |

**前端 README 补充内容**

- `VITE_USE_MOCK=false` 的联调步骤；
- Vite 代理说明；
- 后端演示账号密码 `Demo@123456`；
- 常用账号表（学校管理员、教师、学生、各级管理、题库管理）；
- 登录页自动填充说明；
- mock 模式与真实模式密码不同的提醒。

---

## 5. AI 音乐测评模型

### AI-001 导入 `music_evaluation` 分支

**类型**：新增第三方代码/模型产物

**来源**

- GitHub 仓库：`Yuany-11/Art_assessment`
- 分支：`music_evaluation`

**落地目录**

```text
Art_assessment_backend/ai/music_evaluation/
```

**目录内容**

| 目录/文件 | 说明 |
| --- | --- |
| `music_analysis/` | 基于 librosa 的音乐分析服务：调性、节奏、动态、结构、情绪等 |
| `schemas/music_analysis.schema.json` | 分析输出契约 |
| `scripts/` | 评测与数据获取脚本 |
| `tests/` | 分析服务回归测试 |
| `training/runs/` | 6 次训练产物，每次包含 `best_model.pt`、`config.json`、`labels.json`、`metrics.json`、`state.json` |
| `requirements.txt` | numpy / librosa / soundfile 等依赖 |

最新训练目录：`training/runs/20261026-120656`，任务为 genre / emotion / mode / BPM。

**独立运行方式**

```bash
cd Art_assessment_backend/ai/music_evaluation
pip install -r requirements.txt
python -m music_analysis.api --host 127.0.0.1 --port 8090
# 打开 http://127.0.0.1:8090/ui/
```

**当前限制**

- 分支中缺少 `training/infer.py`、`training/features.py` 和 `scoring/rubric.default.json`；
- 因此 `best_model.pt` 目前无法直接加载推理；
- `music_analysis/` 可独立运行，但尚未接入主后端 `/api/v1/ai/music/analyze`；
- 本次只完成代码与模型产物的导入、目录核验和 README 说明，未做端到端推理验证。

**后续接入建议**

1. 补齐推理脚本与评分 rubric；
2. 在 `apps/exams` 增加 AI 分析适配层，将分析结果映射到题目评分；
3. 增加异步任务与失败重试；
4. 增加音频格式、大小、时长校验；
5. 补充端到端测试（上传音频 → 分析 → 评分）。

---

## 6. 演示数据体系

### 6.1 数据命令执行顺序

```bash
python manage.py migrate
python manage.py seed_menus
python manage.py seed_organizations
python manage.py seed_demo_accounts
python manage.py seed_demo
python manage.py seed_question_bank       # 七年级音乐/美术 3500 道
python manage.py seed_grade_question_bank # 1~9 年级分层题库 900 道
python manage.py seed_rich_demo
python manage.py rebalance_question_grades # 按难度均衡到各年级（每级约 500 道）
python manage.py seed_all_portals
python manage.py seed_classes          # 可选：补充 4 个班 × 20 名学生
python manage.py seed_primary_classes  # 可选：补充小学部 2 个班 × 20 名学生
python manage.py realify_demo_data --purge-records  # 可选：清空演示记录并改为真实学校/姓名/题目
```

### 6.2 各命令的职责

| 命令 | 职责 | 是否可重复 |
| --- | --- | --- |
| `seed_menus` | 角色菜单与权限 | 是 |
| `seed_organizations` | 演示省/市/区县/学校组织树 | 是 |
| `seed_demo_accounts` | 七类角色账号（密码取 `DEMO_PASSWORD`） | 是 |
| `seed_demo` | 基础班级、课程、试题、手工卷、测评 | 是（支持 `--reset`） |
| `seed_question_bank` | 七年级音乐/美术各 1750 道（含章节知识讲解） | 是 |
| `seed_grade_question_bank` | 一~九年级每个年级音乐/美术各 50 道，按年级难度分层 | 是 |
| `seed_rich_demo` | 分类题库、自动组卷、历史测评、报告、证书、作品 | 是 |
| `rebalance_question_grades` | 把七年级多余题目按难度分到其他年级，每级约 500 道 | 是（已均衡时 0 改动） |
| `seed_all_portals` | 全部学生/教师账号的全功能数据 | 是 |
| `seed_classes` | 在演示中学新增 4 个班、每班 20 名学生（含账号与班级关系） | 是 |
| `seed_primary_classes` | 在真实学校补充小学部三年级、六年级各 1 个班、每班 20 人 | 是 |
| `realify_demo_data` | 合并重复组织与班级，改为真实学校、师生姓名与题目；加 `--purge-records` 时清空演示记录 | 是（已清理后为 0 变更） |

### 6.3 演示账号与教学关系

`realify_demo_data` 执行后，保留账号本身（登录名与密码不变），把姓名、组织、班级改为
真实信息。学校为四川省成都市青羊区的九年一贯制公办学校
「成都市石室联合中学蜀华分校」（蜀华街 43 号），同时设有小学部和初中部。
当前对应关系：

| 账号 | 角色 | 真实姓名 | 组织 / 班级 |
| --- | --- | --- | --- |
| `student` | 学生 | 王浩然 | 七年级（1）班 `C20260701` |
| `student2` | 学生 | 李雨桐 | 七年级（1）班 `C20260701` |
| `student_001` | 学生 | 张子涵 | 七年级（1）班 `C20260701` |
| `student_002` | 学生 | 刘思远 | 七年级（1）班 `C20260701` |
| `teacher` | 教师 | 陈志远 | 七年级（1）班 / 八年级（1）班 音乐 |
| `teacher_music` | 教师 | 李静 | 三年级（1）班 / 七年级（2）班班主任，七年级音乐 |
| `teacher_art` | 教师 | 赵敏 | 六年级（1）班 / 七年级（3）班 / 八年级（2）班班主任，全校美术 |
| `school_admin` | 学校管理员 | 王建国 | 成都市石室联合中学蜀华分校 |
| `question_admin` | 题库管理员 | 孙倩 | 全局题库 |
| `district_admin` | 区县管理员 | 刘敏 | 青羊区 |
| `city_admin` | 市州管理员 | 陈建平 | 成都市 |
| `province_admin` | 省级管理员 | 周立新 | 四川省 |

其余 120 名学生账号为 `student_<年级>_<班号>_<序号>`，已生成互不重复的真实姓名
（如 `student_7_2_01` → 王子轩、`student_3_1_01` → 杜泽楷），组织均为
成都市石室联合中学蜀华分校。小学部由 `seed_primary_classes` 创建：
三年级（1）班 `C20260301`、六年级（1）班 `C20260601`，每班 20 人。

统一密码：`Demo@123456`。试卷、测评、成绩等页面为空时，可重新执行 `seed_*` 演示数据命令。

### 6.4 题库结构

`realify_demo_data` 删除 5 道 `[演示]` 试题和旧演示课程，并去掉题干的
`【音乐】` / `【美术】` 前缀。当前题库：

| 学科 | 课程 | 章节数 | 题数 |
| --- | --- | ---: | ---: |
| 音乐 | 一~九年级音乐（人教版），共 9 套 | 每套 4 | 2255 |
| 美术 | 一~九年级美术（人美版），共 9 套 | 每套 5 | 2245 |
| 合计 | 18 套 | — | 4500（已审核 4496，另有 3 道待审核、1 道已驳回） |

`rebalance_question_grades` 执行后，每个年级 500 道（音乐、美术各约 250 道），
难度与年级一一对应：一、二年级 1 级，三、四年级 2 级，五~七年级 3 级，
八年级 4 级，九年级 5 级。已审核题在七年级为 496 道，其余年级各 500 道；
另有 3 道待审核、1 道已驳回留在七年级。
分到低年级的题目内容仍来自七年级教材，属于演示数据的题量均衡。
题型分布见 [BE-001](#be-001-新增-seed_rich_demo-丰富演示数据命令)。

### 6.5 测评时间线

| 类型 | 时间设计 | 用途 |
| --- | --- | --- |
| 历史测评（一） | 40~60 天前 | 成绩趋势、报告、证书 |
| 历史测评（二） | 5~20 天前 | 成绩趋势、报告、证书 |
| 随堂检测 | 2~3 天前 | 教师待评分任务 |
| 综合测评 | 当前 ~ 14 天后 | 学生进行中、可作答 |

### 6.6 生成文件与运行时数据

以下内容属于运行时生成，不应作为源码提交：

- `Art_assessment_backend/db.sqlite3`
- `Art_assessment_backend/media/`（作品 PNG、证书 PDF）
- `Art_assessment_backend/staticfiles/`
- `Art_assessment_frontend/node_modules/`
- `Art_assessment_frontend/dist/`

---

## 7. 验证记录

### 7.1 验证环境

- 日期：2026-10-27
- 后端：Django 5.2 + DRF，SQLite，`127.0.0.1:8000`
- 前端：Vite + Vue 3，`127.0.0.1:5173`
- 登录方式：`POST /api/v1/auth/login`，统一密码 `Demo@123456`

### 7.2 学生端验证

对 `student`、`student2`、`student_001`、`student_002` 四个账号逐一验证：

| 功能 | 接口 | 结果 |
| --- | --- | --- |
| 我的测评 | `GET /assessments` | 200，音乐/美术均有历史与进行中测评 |
| 我的成绩 | `GET /scores/me` | 200，两学科均有成绩 |
| 我的错题 | `GET /students/me/wrong-questions` | 200，有错题列表与统计 |
| 错题详情 | `GET /students/me/wrong-questions/{id}` | 200 |
| 学情报告 | `GET /students/{id}/learning-report?subject=music|art` | 200，两学科均有报告 |
| 成长曲线 | `GET /students/{id}/growth-curve?subject=music|art` | 200，有多个分数点 |
| 我的证书 | `GET /certificates` | 200，可下载 PDF |
| 课外作品 | `GET /files?category=student_work` | 200，音乐/美术作品各 2 件 |
| 作品预览 | `GET /media/...` | 200，`image/png` |
| 趣味课堂 | `GET /courses` + `/courses/{id}/chapters` | 200，章节有题数 |
| 进行中测评 | `can_start` / 开始答题 | 4 名学生均可开始 |

补充验证：

- 学生音乐学情报告趋势示例：`76 → 102.5`；
- 证书 PDF 下载返回 200；
- 作品文件大小约 47~65 KB，格式为 PNG。

### 7.3 教师端验证

对 `teacher`、`teacher_music`、`teacher_art` 逐一验证：

| 功能 | 接口 | 结果 |
| --- | --- | --- |
| 我的班级 | `GET /classes` | 200 |
| 班级学生 | `GET /classes/{id}/students` | 200 |
| 班级申请 | `GET /classes/{id}/requests` | 200，有待审核申请 |
| 试卷列表 | `GET /papers` | 200，含已审核/待审核 |
| 试卷详情 | `GET /papers/{id}` | 200 |
| 审核历史 | `GET /papers/{id}/review-history` | 200 |
| 答案下载 | `GET /papers/{id}/answers/download` | 200 |
| 测评列表 | `GET /assessments` | 200 |
| 评分任务 | `GET /grading/tasks` | 200，有未评分答卷 |
| 评分详情 | `GET /grading/attempts/{id}` | 200 |
| 成绩列表 | `GET /scores` | 200 |
| 成绩详情 | `GET /scores/{id}` | 200 |
| 统计列表 | `GET /scores/statistics/list?groupBy=class` | 200 |
| 统计导出 | `GET /scores/statistics/export` | 200，返回文件流 |
| 证书列表/下载 | `GET /certificates` / `.../download` | 200 |
| 题库 | `GET /questions?status=approved|pending` | 200，已审核与待审核均有数据 |
| 通知 | `GET /notifications` | 200 |

补充验证：

- 教师端可看到两个学科的试卷与成绩（`teacher_art` 同时教两个班美术）；
- 教师评分任务中同时存在历史未评分答卷与新随堂检测答卷；
- 试卷材料下载在没有资源文件时返回 409，属于预期业务校验。

### 7.4 管理员端验证

| 功能 | 接口 | 结果 |
| --- | --- | --- |
| 待审核试卷 | `GET /papers?reviewStatus=pending` | 200，返回可访问试卷，其中包含待审核记录（该过滤参数尚未在后端生效，见 8.1） |
| 试卷审核 | `review_paper` 流程 | 可用 |
| 班级/账号/统计 | 既有接口 | 200 |

### 7.5 数据一致性抽查

- 每名学生均有 2 份学情报告（音乐、美术）；
- 每名学生均有 4 件课外作品（音乐 2、美术 2）；
- 每名学生均有 2~3 张证书；
- 每个教学组合均有历史测评与进行中测评；
- 每个教学组合均有已评分成绩与待评分答卷；
- 两个班级均有待审核转班申请。

---

## 8. 已知限制与后续待办

### 8.1 试卷列表的 `reviewStatus` 过滤未生效

**现象**

前端 `PaperReviewView.vue` 通过 `api.papers.list({ reviewStatus: 'pending' })` 请求待审核试卷，
但后端 `list_papers` 目前只支持 `subject`、`paperType`、`grade`、`scopeType`、`status`、
`keyword` 等过滤条件，未处理 `reviewStatus`。

**影响**

- 接口不会报错，但会返回当前权限范围内的全部试卷；
- 前端如果自行按 `reviewStatus` 过滤，仍可正确展示；若未过滤，会看到非待审核数据。

**建议**

在 `apps/exams/services/paper.py` 的列表查询中增加：

```python
review_status = params.get("reviewStatus")
if review_status:
    qs = qs.filter(review_status=review_status)
```

并补充接口测试。

### 8.2 待审核试卷状态不会被重置

`seed_all_portals` 按标题复用已存在的试卷。若演示过程中管理员已审核通过，
重新执行命令不会再次生成“待审核”状态。

**建议**

演示前如需恢复，可手动将指定试卷 `review_status` 改回 `pending`，或删除该试卷后重跑。
后续可增加 `--reset-pending` 参数。

### 8.3 音乐模型尚未接入业务

- `music_evaluation` 代码已导入，但缺少推理依赖文件；
- `.pt` 权重暂时无法直接加载；
- 主后端尚未调用该服务；
- 需要补齐推理脚本、评分 rubric、异步任务与端到端测试。

### 8.4 本地配置与生产配置差异

- 当前验证全部基于 SQLite + LocMem + 本地文件；
- 生产环境需要 MySQL 8、Redis、MinIO，并设置 `DJANGO_SETTINGS_MODULE=config.settings.prod`；
- 本地 SQLite 并发能力有限，不适合多人同时演示。

### 8.5 学生端班级列表权限

`GET /api/v1/classes` 对学生返回 403；学生首页实际使用 `GET /api/v1/classes/{id}`，
因此当前页面不受影响。若后续学生端需要“班级列表/搜索列表”，需要单独放开权限或提供
学生可见的班级搜索接口。

### 8.6 学生通知为空

学生角色没有通知页面，当前也未生成学生通知；教师与管理员的通知由试卷审核流程产生。
如需学生端通知，需要补充通知触发点与页面。

### 8.7 演示数据未加入自动化测试

当前通过真实 HTTP 接口进行冒烟验证，尚未把演示数据纳入 pytest 用例。

**建议**

后续增加：

- `seed_rich_demo` / `seed_all_portals` 幂等性测试；
- 每个账号关键接口的数据量断言；
- 证书、作品文件生成测试。

---

## 9. 复现步骤

### 9.1 后端

```bash
cd C:\Users\ter\Desktop\终\Art_assessment_backend

# 1. 安装依赖（建议使用虚拟环境）
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 2. 确认 .env（关键项）
# DB_ENGINE=sqlite
# CACHE_BACKEND=locmem
# FILE_STORAGE=local
# DEMO_PASSWORD=Demo@123456

# 3. 初始化数据库
python manage.py migrate

# 4. 初始化基础数据
python manage.py seed_menus
python manage.py seed_organizations
python manage.py seed_demo_accounts
python manage.py seed_demo

# 5. 生成丰富演示数据
python manage.py seed_rich_demo
python manage.py seed_all_portals

# 6. 启动
python manage.py runserver 127.0.0.1:8000
```

### 9.2 前端

```bash
cd C:\Users\ter\Desktop\终\Art_assessment_frontend

pnpm install

# .env 确认：
# VITE_API_BASE_URL=/api/v1
# VITE_USE_MOCK=false

pnpm dev
```

访问 `http://127.0.0.1:5173`，点击角色卡自动填入演示账号，统一密码 `Demo@123456`。

### 9.3 预期结果

- 七类角色均可登录；
- 学生端每个账号都有音乐/美术测评、成绩、错题、报告、证书、作品；
- 教师端每个账号都有班级、试卷、测评、评分任务、成绩、统计、证书；
- 管理员能看到待审核试卷与班级申请；
- 学生可开始进行中的综合测评并提交。

### 9.4 常用验证命令

```bash
# 检查后端配置
python manage.py check

# 查看题库状态统计
python manage.py shell -c "
from apps.qbank.models import Question
from collections import Counter
print(Counter(Question.objects.values_list('subject', 'status')))
"

# 查看每个学生的报告数量
python manage.py shell -c "
from apps.accounts.models import User
from apps.exams.models import LearningReport
for name in ['student','student2','student_001','student_002']:
    u = User.objects.get(username=name)
    print(name, LearningReport.objects.filter(student=u).count())
"
```

---

## 10. 后续记录模板

新增更改时，复制以下模板插入到文末「最新更改」区域的最前面，不要删除历史记录：

```markdown
### <编号> <一句话标题>

**类型**：新增 / 修改 / 修复 / 清理 / 文档

**日期**：YYYY-MM-DD

**涉及文件**

- `path/to/file`

**更改内容**

1. …
2. …

**原因**

…

**影响**

…

**验证**

- 命令 / 接口 / 页面
- 实际结果

**备注**

…
```

编号建议：

| 前缀 | 范围 |
| --- | --- |
| `ENV-` | 环境、配置、部署 |
| `BE-` | 后端业务与数据命令 |
| `FE-` | 前端页面、组件、交互 |
| `AI-` | 音乐分析模型 |
| `DATA-` | 演示数据与初始化脚本 |
| `DOC-` | 文档 |
| `FIX-` | 缺陷修复 |

---

## 变更文件清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `Art_assessment_backend/.env` | 修改 | 本地 SQLite / LocMem / 本地存储 / 演示密码 |
| `Art_assessment_backend/config/settings/dev.py` | 修改 | SQLite 切换 |
| `Art_assessment_backend/config/settings/base.py` | 修改 | LocMem 缓存、本地文件存储分支 |
| `Art_assessment_backend/apps/exams/management/commands/seed_rich_demo.py` | 新增/修改 | 100 道分类题、组卷、测评、报告、证书、作品；清理重复导入 |
| `Art_assessment_backend/apps/exams/management/commands/seed_all_portals.py` | 新增 | 全账号、全功能演示数据 |
| `Art_assessment_backend/apps/accounts/management/commands/realify_demo_data.py` | 新增/修改 | 清理演示记录，改为真实学校、师生与题目；测试教师挂到测试学生班级 |
| `Art_assessment_backend/apps/accounts/management/commands/seed_primary_classes.py` | 新增 | 小学部三年级、六年级各 1 个班，每班 20 人 |
| `Art_assessment_backend/apps/exams/management/commands/seed_question_bank.py` | 新增 | 音乐 / 美术题库各 1750 道 |
| `Art_assessment_backend/apps/exams/management/commands/seed_classes.py` | 新增 | 初中新增 4 个班、每班 20 人 |
| `Art_assessment_backend/apps/exams/services/paper.py` | 修改 | 自动组卷固定 100 分；随机练习固定 6 单选 + 3 多选 + 1 实践题 |
| `Art_assessment_backend/apps/exams/services/attempt.py` | 修改 | 交卷评分；含人工评分题时延后生成成绩 |
| `Art_assessment_backend/apps/exams/services/grading.py` | 修改 | 仅教师终评时生成 / 更新成绩与排名 |
| `Art_assessment_backend/apps/exams/presenters.py` | 修改 | 未终评时隐藏主观分与总分，返回 `scoreReleased` |
| `Art_assessment_backend/apps/exams/serializers.py` | 修改 | 随机练习请求参数调整 |
| `Art_assessment_backend/ai/music_evaluation/**` | 新增 | 从 GitHub `music_evaluation` 分支导入 |
| `Art_assessment_backend/README.md` | 修改 | 初始化顺序、演示数据说明 |
| `Art_assessment_frontend/.env` | 修改 | 关闭 mock、真实接口前缀 |
| `Art_assessment_frontend/.env.example` | 修改 | 联调说明 |
| `Art_assessment_frontend/vite.config.ts` | 修改 | `/api` 代理到 8000 |
| `Art_assessment_frontend/src/api/client.ts` | 修改/确认 | Axios baseURL、JWT、401 刷新 |
| `Art_assessment_frontend/src/api/index.ts` | 修改/确认 | mock 开关判定 |
| `Art_assessment_frontend/src/views/LoginView.vue` | 修改 | 取消先选工作端，按账号角色直接登录并快捷填入测试账号 |
| `Art_assessment_frontend/src/views/student/StudentAttemptView.vue` | 修改 | 浏览器录音上传；交卷后待评分提示与跳转 |
| `Art_assessment_frontend/src/layouts/AppShell.vue` | 修改 | 「演示环境」改为「本地环境」 |
| `Art_assessment_frontend/src/api/index.ts` | 修改 | 随机练习、录音上传、评分提交等接口 |
| `Art_assessment_frontend/README.md` | 修改 | 联调步骤、演示账号、练习与判分说明 |
| `CHANGELOG.md` | 新增 | 本更改记录 |

> 说明：`seed_demo`、`seed_demo_accounts`、`seed_menus`、`seed_organizations`
> 为本次联调依赖的既有演示命令，本次未对其业务逻辑做修改；如后续调整，请在下方追加记录。

---

## 最新更改


### 2026-11-19 16:51 · BE-024 / FE-024 学籍号改为兼容规则，省端增加只读区县总览

**修改时间**：2026-11-19 16:47–16:51

**类型**：后端 / 前端

**1. 学籍号兼容模式**

- 后端 `STUDENT_NO_PATTERN` 改为 `^[A-Za-z0-9]{6,20}$`，提示
  “学籍号需为 6~20 位字母或数字”；现有 `S2026...` 与 18 位数字都可通过。
- Serializer、创建/编辑服务、班级导入、`/auth/config` 同步。
- 前端常量、新建/编辑输入框同步：允许字母数字、最大 20 位；登录提示改回
  “登录账号或学籍号”，不再写死 18 位。
- 不再要求历史学号迁移，避免影响学生用旧学号登录。

**2. 省端只读区县总览**

- 省端菜单新增「区县总览」，路由 `/province/accounts/districts`，复用账号列表
  但 `readonly=true`：隐藏新建、编辑、重置密码、删除操作。
- 省端仍可查看区县及区县管理员；创建/编辑/删除/重置仍由所属市州管理员负责。
- 后端 `create_district()` 保持只允许市州；账号变更判定新增限制：省级管理员
  不能修改/删除/重置区县管理员账号。

**验证**

- 学籍号：`S20260001`、`S20260301001`、18 位数字通过；`S!2026`、5 位数字拒绝。
- `/auth/config` 返回 min=6、max=20、`^[A-Za-z0-9]{6,20}$`。
- 省端 `GET /accounts?role=district_admin` 可读取列表；前端只读模式无操作按钮。
- 后端全量 `pytest -q`、`manage.py check` 通过；前端 typecheck/build 通过。

**涉及文件**

- `apps/accounts/{validators.py,account_serializers.py,views.py,services/accounts.py}`
- `apps/accounts/tests/{test_accounts.py,test_me.py}`
- `src/constants/validation.ts`
- `src/views/{AccountsView.vue,TeacherStudentsView.vue,LoginView.vue}`
- `src/config/menu.ts`、`src/router/index.ts`


### 2026-11-19 16:46 · BE-023 / FE-023 按截图证据修复课程保存、成绩口径与登录提示

**修改时间**：2026-11-19 16:35–16:46

**类型**：后端 / 前端

**修复内容**

1. **课程/章节保存失败**：截图确认表单“课程简介/章节说明”为空时，后端
   `description` 字段不允许空字符串，返回 400，前端此前无提示。已将课程、
   章节的 create/update Serializer 改为 `allow_blank=True`，空简介可正常保存。
2. **登录页快捷填写旧姓名**：快捷身份按钮的姓名/Tooltip 是写死的演示名，
   后台改名后仍显示旧名。已移除姓名展示和提示，只显示角色/账号。
3. **账号复制按钮失败**：截图显示复制失败；新增 `utils/clipboard.ts`，
   Clipboard API 不可用时回退到临时 textarea + `execCommand('copy')`，并用于
   学生账号清单。
4. **教师成绩管理与学生端口径不一致**：成绩列表默认不再只查正式测评，
   改为展示教师/管理员发布的正式卷和练习卷，仅隐藏学生随机练习生成的卷。
5. **学生成绩趋势出现 0 分**：`my_scores()` 只返回 `status=graded` 的成绩，
   未评分/0 分记录不再进入“我的成绩”趋势。
6. **全局“本地环境”标识**：移除侧边栏底部和顶栏的「本地环境」调试标识。

**验证**

- `CourseCreateSerializer` / `ChapterCreateSerializer` 空 description 校验通过。
- 后端全量 `pytest -q`：全部通过；`manage.py check` 无问题。
- 前端 `npm run typecheck`、`npm run build` 通过。
- 教师成绩管理默认返回正式+练习（当前数据 9 条），学生 `/scores/me` 只返回
  已评分成绩（当前 2 条）。

**未改**

- 18 位学籍号与旧 S 学号冲突（产品规则未定）。
- 省端区县管理（与上一轮“只由市州管理”冲突）。
- 班级行操作多出的「…」按钮：当前代码只有一个「更多」下拉，未找到第二个
  按钮来源，需复测/查看 DOM。

**涉及文件**

- `apps/qbank/serializers.py`
- `apps/exams/services/score.py`
- `apps/exams/tests/test_scores_statistics.py`
- `src/views/{LoginView.vue,AccountsView.vue,TeacherStudentsView.vue}`
- `src/layouts/AppShell.vue`
- `src/utils/clipboard.ts`


### 2026-11-19 16:30 · BE-022 / FE-022 修复已确认的统计、日志与表单提示问题

**修改时间**：2026-11-19 16:15–16:30

**类型**：后端 / 前端

**修复内容**

1. **统计并列排名**：后端 `statistics.py` 与前端 `demoStatistics.ts` 改为同分并列
   （1、1、3），不再把同分对象排成 1、2、3。
2. **统计导出与页面不一致**：统计页导出改为直接导出当前表格数据（CSV，带 BOM），
   不再出现“页面有演示数据、后端导出为空”。
3. **操作日志搜索**：后端关键词从只搜 `description` 扩展为操作人姓名/账号、
   动作、说明，和前端“操作人、动作或说明”的提示一致。
4. **教师端数据统计筛选**：按班级分组时，关键词同时匹配班级名、学校名、
   区县名、市州名；搜索“成都/绵阳”可正确筛选。
5. **添加学生错误提示**：API 拦截器保留 `data.errors`，账号表单优先展示具体
   字段错误（如手机号格式），而不是统一的“请求参数校验失败”。
6. **课程/章节保存无反馈**：`saveCourse()` / `saveChapter()` 增加异常捕获，
   接口失败时提示错误，不再看起来“按钮点不动”。

**验证**

- 教师端统计：3 个同分班级排名均为 1；关键词“成都”返回 3 条、“绵阳”返回 0 条。
- 操作日志：搜索“student”“上传”“file.upload”均能命中（省级账号）。
- 后端 `manage.py check`、`pytest apps/exams/tests apps/qbank/tests` 通过。
- 前端 `npm run typecheck`、`npm run build` 通过。

**未修复（需确认口径或复现信息）**

- 学籍号 18 位与旧学号冲突（需要产品规则确认）。
- 省端区县管理（与上一轮“只由市州管理”的需求冲突）。
- 试卷/班级年级不匹配、成绩数据不一致等需要具体试卷/学生 ID。
- 赛事报名模块不在当前仓库。

**涉及文件**

- `apps/exams/services/statistics.py`
- `apps/qbank/services.py`
- `src/api/client.ts`
- `src/views/{StatisticsView.vue,AccountsView.vue,CoursesView.vue}`
- `src/utils/demoStatistics.ts`


### 2026-11-18 11:33 · DATA-011 从备份恢复旧题库并保证章节有题

**修改时间**：2026-11-18 11:30–11:33

**类型**：演示数据修复

**背景**

上一轮 `DATA-010` 按要求清空业务数据时把旧题库也删了，导致章节下没有旧题。
题库应按用户要求保留，只需重建试卷、测评、成绩等业务数据。

**恢复内容**

- 从 `db.sqlite3.bak-20261118-112249-before-realistic-seed` 恢复旧试题
  **6823 道**（已通过 5026、待审核 1797）及其选项、题目资源。
- 旧题目 ID 与新建题目不冲突；44 个题目图片文件重新分配当前库文件 ID 并
  保留原 `object_key`，图片仍可通过 `/media` 访问。
- 当前题库合计 **7205 道**（旧 6823 + 新 382），所有 **150 个有效章节** 均有题。
- 恢复前再次备份：`db.sqlite3.bak-20261118-113244-before-restore-question-bank`。

**命令行为调整**

`seed_realistic_reset` 默认**保留题库**，只重建试卷/测评/答卷/成绩/证书等；
确需清空题库时显式加 `--reset-questions`。保留题库模式会清理旧学生作品文件，
避免重复累加。

**验证**

- `GET /questions`：7205 道；美术 4557 道；待审核 1815 道。
- 空章节数量：0。
- 旧图片题（如 27509）资源仍可访问：`/media/question_image/...` 返回 200。

**涉及文件**

- `apps/exams/management/commands/seed_realistic_reset.py`
- 数据库：当前 `db.sqlite3`（恢复题库），备份如上


### 2026-11-18 11:29 · DATA-010 清空业务数据并重建互相关联的演示数据

**修改时间**：2026-11-18 11:22–11:29

**类型**：演示数据

**备份**

重建前已备份：`db.sqlite3.bak-20261118-112249-before-realistic-seed`。

**保留**

组织、账号、学生/教师档案、班级、课程与章节（保证登录和基础结构不重建）。

**清空并重建**

试题、试卷、测评、答卷、成绩、证书、错题、学情报告、通知、审核/操作日志、
入班申请、考试导入任务。

**重建结果**

- 试题 **382** 道：音乐/美术各 191，已通过 346、待审核 18、已驳回 18；
  含图像选择判断、音频选择判断、图片/音频实践题。
- 试卷 **40** 张：各年级音乐/美术期末测评卷、单元练习卷，标题统一为
  `2026-2027学年第一学期X年级音乐/美术期末测评卷（班级）`；含 2 张待审核卷。
- 测评 **28** 场：正式期末测评 + 单元练习，覆盖 3/6/7/8 年级班级。
- 答卷 **66** 份：42 份已评分、24 份待教师评分。
- 成绩 **42** 条、证书 **28** 张、错题 **108** 条、学情报告 **44** 份、
  通知 **546** 条、入班申请 **3** 条、学生课外作品 **8** 件。
- 题目由音乐/美术教师创建，已通过题目记录题库管理员审核人和审核意见。

**过程中发现并修复的问题**

1. 首轮证书为 0：证书要求正式测评得分率 ≥90%，原随机分不够；已让每场正式
   测评第一位学生生成满分答卷，并按教师/发布人权限重试生成证书。
2. 首轮教师评分页无待评分任务：实践作品题未进入试卷；已为每门课补实践题，
   并让部分学生答卷保持“已交卷待评分”。
3. 首轮入班申请为 0：只在前两个班级里找同年级目标班；已改为遍历全部班级。
4. 演示学生错题本为空：已为 `student`、`student_001`、`student_002`、`student2`
   补充错题记录。

**验证**

- `manage.py check` 无问题。
- 教师端：7 张试卷、6 场测评、4 个待评分任务、9 条成绩、6 张证书。
- 题库管理员：40 张试卷、18 道待审题、2 张待审试卷。
- 学生端：4 场测评、2 张证书、3 条错题、2 份学情报告。

**涉及文件**

- 新增 `apps/exams/management/commands/seed_realistic_reset.py`

**说明**

- 保留的账号/班级/课程不重建，所以旧账号密码不变；被清空的业务数据无法从
  页面恢复，只能使用上面的数据库备份。
- 旧上传文件未删除（只清空了业务记录），`media/` 中可能残留少量无引用文件。


### 2026-11-17 16:32 · BE-021 / FE-021 修复练习卷组卷后列表看不到

**修改时间**：2026-11-17 16:25–16:32

**类型**：后端 / 前端

**问题**

`list_papers()` 对非题库管理员默认只查 `paperType=formal`。教师创建练习卷后，
列表仍按正式卷过滤，导致“组卷成功但看不到试卷”；前端保存后也没有清掉旧的
类型筛选。

**修改**

- 后端不再默认只看正式卷；改为排除学生创建的随机练习卷，教师/管理员创建的
  正式卷和练习卷都正常显示。
- 前端组卷保存成功后清空 `paperType/status/reviewStatus/keyword` 筛选并回到
  第一页，确保新试卷立刻出现在列表。

**验证**

- 教师 `teacher_music` 调用 `GET /papers?pageSize=100`：练习卷 125、124 等
  已出现在列表中；学生随机练习卷仍被排除。
- `pytest apps/exams/tests` 全部通过；`npm run typecheck`、`npm run build` 通过。

**涉及文件**

- `apps/exams/services/paper.py`
- `src/views/PapersView.vue`


### 2026-11-17 14:20 · FE-020 章节顺序改为上移/下移，列表显示序号

**修改时间**：2026-11-17 14:15–14:20

**类型**：前端

**问题**

课程章节的排序要手动填写数字，历史章节又全是默认 0，列表里看不出实际顺序，
调整起来很麻烦。

**修改**

- 章节列表新增「序号」列（第 1、2、3…），直接显示当前顺序。
- 每行新增「上移 / 下移」按钮，点击后自动把该课程章节重排为 10、20、30…
  并保存，不需要手填数字。
- 新增章节默认排在最后；章节编辑弹窗移除「排序」输入，改为提示用上移/下移调整。
- 课程编辑保留排序输入，并补充「数字越小越靠前」提示。

**验证**

- `npm run typecheck`、`npm run build` 通过。
- 前端 5173 仍在运行，刷新「课程与章节」即可看到新按钮。

**涉及文件**

- `src/views/CoursesView.vue`


### 2026-11-17 09:29 · FE-019 统一答案展示，移除原始 JSON/values 字段

**修改时间**：2026-11-17 09:25–09:29

**类型**：前端

**问题**

错题详情把答案用 `JSON.stringify` 直接渲染，学生看到的是
`{"values":["A","C"]}` 或 `{"value":"B"}`，出现 `values` 等字段名；
美术多图答案也可能直接暴露 `files` 字段。

**修改**

- `utils/answers.ts` 的 `formatAnswer` 增强：支持多选/填空的 `values`、
  `value`、`text`、多图 `files`，只显示答案内容，不显示字段名；无答案统一
  「未作答」。
- 错题详情「你的答案 / 正确答案 / 答错记录」改用 `formatAnswer`，并新增
  `displayAnswer` 将选项 key 映射为「A. 选项内容」，多选按 `；` 分隔。
- 试题管理 AI 出题结果答案的兜底从 `JSON.stringify` 改为统一格式化。
- 评分页、成绩页、试卷阅览页原本复用 `AnswerPreview`，自动获得多选/填空题
  与多图作品的正确展示。

**验证**

- `npm run typecheck`、`npm run build` 通过。
- 前端 HMR 已生效，服务仍在 5173 运行。

**涉及文件**

- `src/utils/answers.ts`
- `src/views/student/WrongQuestionsView.vue`
- `src/views/QuestionsView.vue`


### 2026-11-17 09:20 · BE-020 / FE-018 执行 7 项新增修改

**修改时间**：2026-11-17 09:00–09:20

**类型**：后端 / 前端

**1. 图像/音频选择判断题**
- 新增 `QuestionType.IMAGE_CHOICE_JUDGE=image_choice_judge`（图像选择判断），
  仅美术学科可用；必须绑定至少一张题干图片，选项/答案与单选题一致。
- 音频选择判断题 `audio_choice_judge` 保持音乐学科可用。
- 创建/编辑表单新增题干图片上传（10 MB 限制），学生端先展示图片再选项作答，
  组卷、判分、试卷快照沿用现有资源与客观题链路。
- 说明：仓库没有音频出题模型，本次没有新增“自动生成音频题”能力；音频题仍为
  教师上传音频后创建。

**2. 概览待审核试卷**
- 区县/市州/省、学校管理员与教师概览中的「待审核试卷」卡片改为「组卷管理」，
  点击进入 `/papers`；题库管理员仍保留「待审核试卷」入口。

**3. 省级管理员右上角名称**
- 无学校/市州名称时回退显示「四川省」，不再显示「全域题库」。

**4. 今日待办**
- 删除各端概览的固定 3 条待办，改为可输入添加、逐条删除的待办列表；
  按用户 ID 存入 `localStorage`，刷新后保留。

**5. 试题管理学科题型**
- 题型筛选下拉随所选学科动态变化：选美术只显示美术题型，选音乐只显示音乐题型；
  切换学科清空非法题型筛选。
- 删除试题管理顶部「音频曲风」「音频情绪」筛选。

**6. 数据统计图表**
- 市州端区县池补齐成都 20 个区（市）县（含简阳市），省级补齐四川 21 个市州，
  区县/市州维度不再只显示前 8/10 个。
- 平均分对比改为上下两行柱状图，标签旋转、间距拉开；统计区改为单列，
  排名列表改为两列，减少留白。
- 区县管理员统计分组只保留「学校」，不再跨区县比较。

**7. 区县管理权限**
- 「区县账号」菜单与路由仅保留市州管理员；省级管理员不再管理区县。
- 后端 `create_district()` 仅允许市州管理员，跨市州创建仍被拒绝。

**验证**

- 后端 `pytest -q`：338 passed；`manage.py check` 无问题。
- 前端 `npm run typecheck`、`npm run build`：通过。
- 未新建数据库迁移（`image_choice_judge` 只新增枚举选项，字段长度不变）。

**涉及文件**

- 后端：`common/enums.py`、`common/subject_types.py`、`apps/qbank/services.py`、
  `apps/exams/services/{attempt.py,paper.py}`、`apps/accounts/services/accounts.py`
- 前端：`src/utils/{questionTypes.ts,demoStatistics.ts}`、`src/views/{DashboardView.vue,StatisticsView.vue,QuestionsView.vue}`、
  `src/layouts/AppShell.vue`、`src/config/menu.ts`、`src/router/index.ts`、
  `src/types/index.ts`、`src/styles/index.css`、各题型标签文件

**限制**

- 音频/图像“自动生成题目”仍受模型能力限制：当前只有美术出题模型（8002，未启动），
  没有音频出题模型；本次实现的是图像选择判断题型与人工上传链路。
- 待办为前端本地存储，不跨设备同步。


### 2026-11-16 10:59 · OPS-001 修复启动脚本换行符，恢复一键启动

**修改时间**：2026-11-16 10:58–10:59

**类型**：启动脚本

**背景**

`start_system.bat` 与 `arteval-v4/arteval-v4/start_service.bat` 使用 LF 换行，
Windows `cmd` 解析批处理时会把行拆错，一键启动脚本报“不是内部或外部命令”，
音频服务 8100 也无法随脚本启动。

**执行内容**

- 将 `start_system.bat`、`arteval-v4/arteval-v4/start_service.bat` 转为 CRLF，
  文件内容不变。
- 通过 `start_system.bat` 启动 8000/5173；8100 随后单独启动并验证 `/health`。
- 8002 仍因缺少 Qwen 基座权重与 `01_给后端A(1)/.venv` 跳过；当前 `.env`
  为 `QGEN_PROVIDER=api`，AI 出题走云接口，不依赖 8002。

**验证**

- `http://127.0.0.1:8000/api/v1/auth/config` → 200。
- `http://127.0.0.1:5173/` → 200。
- `http://127.0.0.1:8100/health` → `status=ok`，`arteval-v4/epoch40`。
- `question_admin` 登录成功，`/auth/me` 返回完整 `allowedQuestionTypes`，
  `/questions?pageSize=2` 的 `pages` 按实际 pageSize 计算。

**涉及文件**

- `start_system.bat`、`arteval-v4/arteval-v4/start_service.bat`


### 2026-11-16 10:17 · BE-019 / FE-017 / DOC-011 执行《AI修改指令_6项新增需求》

**修改时间**：2026-11-16 09:50–10:29

**类型**：后端 / 前端 / 模型服务 / 文档

**1. 学科—题型映射（新增 2）**

- 新增单一来源 `common/subject_types.py`：美术 = 单选/多选/判断/填空/图片作品；
  音乐 = 单选/多选/判断/填空/听赏/音频作品/音频选择判断。
  简答题仍在枚举中但产品已取消，故不进入任何学科的可用列表。
- `/auth/me` 下发 `allowedSubjects`、`allowedQuestionTypes`、
  `questionTypesBySubject`；前端所有题型下拉/筛选改为动态渲染。
- `create_question` / `update_question` / 组卷 `_validate_question` 强制校验
  “学科—题型”匹配；教师仍按任教学科限定，题库管理员可管全学科但不能混搭。
- 前端 `QuestionsView`、`TeacherQuestionBankView` 改用映射；切学科自动清空
  非法题型；美术老师不再出现音频题型与曲风/情绪筛选。
- 补齐填空题前端答案编辑（每行一个空）并按自动判分处理，避免映射放开后
  填空题无法保存。

**2. 学籍号固定格式（新增 6）**

- 后端单一定义：`STUDENT_NO_LENGTH=18`、`^\d{18}$`、统一文案
  「学籍号需为 18 位数字」；Serializer、创建/编辑服务、班级导入全部复用。
- 新增公开接口 `GET /api/v1/auth/config` 下发格式，登录页提示同步为
  「18 位学籍号」。
- 前端常量同步为 18 位数字；新建/编辑输入即时过滤非数字并限长；mock
  创建/修改使用同一正则。
- 历史不合规学籍号不批量改写：编辑时未修改可保存（前后端均放行原值），
  变更时必须符合新格式；合规性核查可用
  `StudentProfile.objects.exclude(student_no__regex=r'^\d{18}$')`。

**3. 转班同年级班级下拉（新增 1）**

- `GET /classes?grade=&status=active` 允许学生读取本校本年级正常班级；
  学生仅能看本校同年级，创建/修改仍返回 403。
- `StudentHomeView` 转班弹窗改为动态下拉（班级名 + 年级 + 班主任），排除
  当前班级，按名称排序，含 loading 与「本年级暂无可转入的班级」空态；
  提交前做同年级校验，后端原有同校/同年级/非当前班校验保留。
- mock `listClasses` 支持 `grade` 过滤。

**4. 美术作品拍照作答（新增 4）**

- 复用 `image_upload` + 答案里的 `captureMode`（camera/album/file），不新增
  数据库字段；仅美术题型映射包含 `image_upload`。
- 学生答题页新增「拍照上传作品」：`getUserMedia` 实时预览 + canvas 截帧；
  移动端保留 `capture="environment"` 后置相机入口；权限拒绝、无设备、
  非安全上下文时自动回退相册/文件上传并提示 HTTPS 要求。
- 图片上传限制 10 MB，保留预览/重拍/移除；页面卸载时
  `stream.getTracks().forEach(track => track.stop())` 释放摄像头。
- 交卷确认会提示哪些美术作品题尚未上传，不静默提交空答案。
- 作品题支持 1–3 张照片：答案新增 `files` 数组（主字段仍保留第一张兼容判分/
  AI），支持继续添加、单张删除、重拍；后端限制单题最多 3 张并校验格式；
  教师端 `AnswerPreview` 支持多图预览与放大。
- 教师评分页 `AnswerPreview` 改为可点击放大的 `el-image`。

**5. 美术 AI 辅助评分（新增 5）**

- 新增 `apps/exams/services/art_scoring.py` 与 `apps/exams/rules/art.yaml`：
  构图/色彩/造型技法/完整性/创意表现五维，权重和为 1。
- 未配置 `ART_SCORER_URL` 时使用可解释的规则式降级（`degraded=true`、
  `method=rule_based`、`confidence=0.35`），不会 500；配置外部服务后按其
  返回分数，失败自动回退。
- 接入现有 `ai_scoring` 链路：`image_upload` 题在评分详情和
  `POST /grading/attempts/{id}/ai-suggestions` 返回建议分、维度、分析和
  `needsReview`；不写 `AttemptAnswer.score` / `Score`，教师采纳后仍需保存。
- 前端评分页支持美术题生成建议分，展示维度进度条、分析文本与降级标签；
  评分详情下发 `aiScoringEnabled`，关闭时按钮置灰并提示「未启用 AI 评分」。
- mock 分支同步返回美术规则式建议分（含 `degraded`/维度），无服务也可演示。

**6. 音频标签准确度（新增 3）**

- 启动自检 checkpoint 的曲风/情绪标签顺序与 `training/infer.py` 常量一致，
  错位直接报错。
- 长音频由“只取中间 30 秒”改为开头/中间/结尾分段推理后聚合概率，返回
  `segments` 与 `segment_offsets`；短音频保持单窗口。
- 教师端低置信度（<0.4）显示「不确定，建议人工判断」，BPM 标注「估计值」，
  多段结果显示「N 段聚合」。
- 新增 `tools/music_calibration/evaluate_tags.py`、`tag_samples.csv` 与
  `make_synthetic_samples.py` 回归工具；合成样例（精确 BPM/调式）给出
  旧逻辑 vs 多段聚合的量化结果：调式 6/6 vs 6/6，BPM MAE 11.24 vs 11.38
  （60 BPM 存在倍频歧义）；真实学生样例无人工标签，只能验证结果未变化。
  训练集指标（曲风 63.26%、情绪 68.60%、调式 75.96%、BPM MAE 9.73）作为
  参考写入 `docs/audio-tag-accuracy.md`。

**验证**

- 后端 `pytest -q`：336 passed；`manage.py check` 无问题。
- 前端 `npm run typecheck`、`npm run build`：通过。
- 新增测试覆盖：学科题型越权、/auth/me 映射、/auth/config、学籍号格式、
  学生转班班级范围、美术规则评分降级与折算。

**涉及文件**

- 后端：`common/subject_types.py`、`common/enums.py`（未改枚举）、
  `apps/accounts/{services/profile.py,serializers.py,validators.py,account_serializers.py,services/accounts.py,views.py,urls.py}`、
  `apps/qbank/services.py`、`apps/exams/services/{paper.py,ai_scoring.py,art_scoring.py}`、
  `apps/exams/rules/art.yaml`、`apps/files/audio_tags.py`、`config/settings/base.py`、
  `.env.example`、`requirements*.txt`、相关测试
- 前端：`src/utils/questionTypes.ts`、`src/types/index.ts`、
  `src/views/{QuestionsView.vue,TeacherQuestionBankView.vue,GradingView.vue,LoginView.vue,AccountsView.vue}`、
  `src/views/student/{StudentHomeView.vue,StudentAttemptView.vue}`、
  `src/components/{AnswerPreview.vue,AudioTagCard.vue}`、
  `src/constants/validation.ts`、`src/api/mock.ts`
- 模型服务：`arteval-v4/arteval-v4/training/score.py`、`service.py`
- 工具/文档：`tools/music_calibration/{evaluate_tags.py,tag_samples.csv}`、
  `docs/{art-ai-scoring.md,audio-tag-accuracy.md,audio-tagging.md}`

**未完成/限制**

- 美术评分没有真实模型权重，目前是规则式降级；接入 `ART_SCORER_URL` 后
  才会返回模型结果。
- 真实音乐的曲风/情绪仍缺人工标注样例，无法给出真实音乐的前后准确率对比；
  合成样例只覆盖 BPM/调式。
- 未改历史归档副本，未批量改写历史学籍号或题目数据。


### 2026-11-16 10:03 · BE-018 / FE-016 / DOC-010 接入模型B图题能力（with_image、配图入库与前端展示）

**修改时间**：2026-11-16 09:50–10:03

**类型**：后端 / 前端 / 文档

**背景**

`01_后端A接入包` 的新版模型B服务支持图题（`with_image`、`role=question`
配图、218 道图题库、`fact_ids`）。现有接入层只出文字题，还会把「下图/如图」
类题干一律按 `image_dependent` 丢弃，图题能力没有进入系统。

**执行内容**

1. 在线生成默认向 8002 传 `with_image: true`（`QGEN_WITH_IMAGE` 可关闭）；
   无同题型素材时服务自动退回文字题。
2. 只入库 `role=question` 的题干配图；`role=reference` 教学参考图丢弃，
   避免前端把参考图画进题干。
3. 配图下载后按 `question_image` 存入本地媒体库/MinIO，创建
   `QuestionResource`；题干出现「下图/如图/第几幅」但没有题干配图时仍跳过。
4. 配图只允许从 `QGEN_URL` 或绝对 `QGEN_RESOURCE_URL_BASE` 下载，限制大小
   与 MIME；下载失败中止入库，不产生无图残题。
5. `fact_ids`、`generated_by`、配图清单写入 `Question.source_meta`，不新增
   数据库字段；`FileObject.biz_id` 关联题目 ID。
6. 前端「AI 出题」结果预览增加配图展示和图题提示；审核弹窗补拉题目详情并
   展示题干配图，避免看不到图就通过。题库详情、学生作答页原有图片渲染不变。
7. 校准/接口响应：`catalog` 增加 `withImage`，生成响应 `model.imageCount`
   与 `model.generatedBy` 便于排查。

**验证**

- `pytest apps/qbank/tests apps/files/tests -q`：52 passed。
- 新增用例覆盖：reference 图不入库、路径穿越拦截、图片依赖题干缺少配图仍
  跳过、生成图题后 `QuestionResource`/`source_meta` 正确落库。
- `npm run typecheck`：通过。
- 限制：本机尚未拿到新版带图题的服务代码与 `data/12_image_assets` 素材，
  本次用包内样例 JSON + mock 下载做离线验证，未做真实 8002 联调。

**涉及文件**

- 后端：`apps/qbank/qgen.py`、`apps/files/services.py`、
  `config/settings/base.py`、`.env.example`、`apps/qbank/tests/test_qgen.py`
- 前端：`src/views/QuestionsView.vue`、`src/types/index.ts`
- 文档：`Art_assessment_backend/docs/model-b-qgen.md`


### 2026-11-13 15:32 · BE-017 / DATA-009 修复题库课程/章节筛选与分页 pages，并批量审核 176 道美术图题

**修改时间**：2026-11-13 15:20–15:32

**类型**：后端 / 演示数据

**背景**

导入脚本把 176 道美术图题（id 27334–27509）以 `pending` 状态写入测试库，
并新建 36 个章节（chapterId 215–250）。使用中发现两个接口缺陷：

1. `GET /api/v1/questions?courseId=` / `?chapterId=` 返回 500。原因是列表服务
   直接把驼峰查询参数名当作 ORM 字段过滤（`filter(courseId=...)`），
   Django 抛出 `FieldError: Cannot resolve keyword 'courseId'`，题库按课程/
   章节筛选完全不可用。
2. 题目列表的 `pages` 恒按每页 10 条计算。DRF 的 `paginate_queryset()` 只在
   局部变量里使用请求的 `pageSize`，不会回写 `self.page_size`，而
   `StandardPagination.get_paginated_response()` 读取的正是该属性，导致
   `pages` 与实际返回条数不一致，前端按 `pages` 翻页会请求到不存在的页码。

**执行内容**

1. `apps/qbank/services.py` 的 `list_questions()` 改为显式映射：
   `courseId → course_id`、`chapterId → chapter_id`；非整数返回
   400「courseId/chapterId 必须为整数」，不再 500。
2. `common/pagination.py` 改用 `self.page.paginator.per_page`（实际分页器每页
   条数）计算 `pages`，`pageSize` 传 5/20/100 均与返回条数一致。
3. 新增 3 条回归测试（`apps/qbank/tests/test_questions.py`）：
   courseId/chapterId 过滤、非法 courseId 返回 400、`pages` 跟随 pageSize。
4. 使用 `question_admin` 调用 `POST /api/v1/questions/{id}/review`
   （`{"action":"approve"}`）批量审核 176 道题，全部通过，审核人记为
   `question_admin`，现在可用于组卷。

**验证**

- `pytest apps/qbank/tests/test_questions.py -q`：10 passed。
- 真实接口（重启后）：
  - `?courseId=6&pageSize=5` → 200，total 420，pages 84，返回 5 条；
  - `?chapterId=215&pageSize=5` → 200，total 8，pages 2，返回 5 条；
  - `?courseId=abc` → 400；
  - `?pageSize=20` → total 6823，pages 342，返回 20 条。
- 审核结果：176 条状态均为 `approved`，`reviewer=question_admin`。
- 审核副作用：审核事件按既有逻辑给创建人 `teacher_art` 生成 176 条
  「试题审核通过」通知（正常业务行为，未做特殊处理）。

**涉及文件**

- 后端：`apps/qbank/services.py`、`common/pagination.py`、
  `apps/qbank/tests/test_questions.py`
- 数据：`Art_assessment_backend/db.sqlite3`（审核 176 道题；
  操作前备份 `db.sqlite3.bak-20261113-153031-before-approve176`）

**未改动**

- 文件存储保持 `FILE_STORAGE=local`，`/media` 经 5173 代理访问，按用户要求不变。
- 未修改题目内容、章节归属和图片文件。


### 2026-11-13 09:05 · BE-016 / FE-015 / DOC-009 重新接入音乐 AI 建议分并完成校准

**修改时间**：2026-11-13 08:40–09:05

**类型**：后端 / 前端 / 模型规则 / 文档

**背景**

`AI修改指令_16项系统Bug修复.md` 第 7 条要求解决「音乐模型评分准确度过低」。
当前架构没有 8090 DSP 服务，`ai_score` 字段已在
`0008_remove_ai_scoring.py` 中移除，音频模型只有 8100（arteval-v4）。
本次按现有架构重新接入：以 8100 校准后的参考分为唯一口径，折算到题目满分后
只作教师参考，不写成绩、不覆盖人工分。

**执行内容**

1. 新增 `scoring/rubric.calibrated.json`：调整调性清晰度、大小调倾向、作品时长、
   段落层次、情绪置信度等锚点；加入可配置校准曲线；权重之和仍为 1。
2. 修复 `training/score.py` 的动态范围度量缺陷：极安静帧会把
   `dynamic_range_db` 算到 140–160 dB，现裁剪到 0–40 dB 并对非有限值兜底。
3. 规则可配置：`score.py` 新增 `resolve_rubric_path()`，支持 `ARTEVAL_RUBRIC`
   环境变量；8100 服务与 `start_service.bat` 默认加载校准规则。
4. 新增 `apps/exams/services/ai_scoring.py`：把 0–100 参考分按
   `参考分 / 100 × 本题满分` 折算为 0–maxScore 建议分（保留 2 位小数、裁剪越界）；
   置信度只用于「建议人工复核」，不参与分数、不压分；**从不写入**成绩字段。
5. 评分详情 `grading_question_item` 增加 `aiSuggestion`；新增
   `POST /api/v1/grading/attempts/{id}/ai-suggestions`，逐题降级返回状态。
6. 评分页新增「生成 AI 建议分」按钮、建议分卡片与「采用建议分」按钮；
   `AudioTagCard` 的 0–100 参考分同步按本题满分折算展示，并保留原始分说明。
7. 修复临时密码回归：`apps/accounts/services/accounts.py` 缺少
   `generate_password` 导入，导致无自定义密码的重置接口 500；已补导入。
8. 修复 `test_qgen_generate_creates_pending` 依赖本机 `.env` 的
   `QGEN_PROVIDER=api` 而失败的问题，测试内显式指定 `model_b`。
9. 新增校准报告 `docs/music-scoring-calibration.md` 与校准工具
   `tools/music_calibration/`（样例清单、评测脚本、前后 JSON）。

**校准结果**

| 样例 | 人工% | 调整前 | 调整后 | 误差变化 |
| --- | --- | --- | --- | --- |
| s52 | 100.0 | 83.9 | 93.8 | −16.1 → −6.2 |
| s44 | 100.0 | 71.3 | 84.1 | −28.7 → −15.9 |
| s33 | 74.9 | 79.1 | 90.7 | +4.2 → +15.8 |

平均绝对误差 16.3 → 12.6，排序保持不变；有人工分的样例仅 3 份，
校准保持温和，最终分仍以教师评分为准。

**涉及文件**

- 模型：`arteval-v4/arteval-v4/training/score.py`、`service.py`、
  `scoring/rubric.calibrated.json`、`start_service.bat`
- 后端：`apps/exams/services/ai_scoring.py`、`apps/exams/presenters.py`、
  `apps/exams/views/grading.py`、`apps/exams/urls.py`、
  `apps/files/audio_tags.py`、`config/settings/base.py`、
  `apps/exams/tests/test_ai_scoring.py`、`apps/accounts/services/accounts.py`、
  `apps/qbank/tests/test_qgen.py`
- 前端：`src/views/GradingView.vue`、`src/components/AudioTagCard.vue`、
  `src/types/index.ts`、`src/api/index.ts`
- 文档/工具：`docs/music-scoring-calibration.md`、`docs/audio-tagging.md`、
  `tools/music_calibration/`

**验证**

- `python manage.py check` 无问题；
- 后端全量 `pytest` 通过（含新增 10 项 AI 建议分测试）；
- `npm run build` 构建成功；
- 8100 服务以校准规则重启，`/health` 正常；
- 运行中验证：答卷 46 的音频题原始分 85.2 → 校准 90.7 → 折算
  **12.11 / 13.35**，评分详情与建议分接口均返回 `calibrated-v1`；
- 未新增数据库迁移，未改动业务演示数据。

---

### 2026-11-12 21:35 · BE-015 / FE-014 补齐 16 项反馈的剩余细节

**修改时间**：2026-11-12 21:20–21:35

**类型**：前端 / 后端 / 交互 / 权限

**背景**

复核 `AI修改指令_16项系统Bug修复.md` 后发现，主体功能已完成，但仍有若干条只做到了主路径，
本次逐条补齐：审核按钮消失、AI 新题筛选、临时密码复查、双签状态展示、密码确认框、
音频播放占位、头像加载失败兜底等。

**执行内容**

1. 试题审核：题库管理员的「通过 / 驳回」按钮由 `v-if` 改为始终显示、非待审时禁用；
   审核提交仍保留当前筛选和分页，不再出现按钮突然消失。
2. AI 出题：生成成功后弹窗保持打开并展示已入库题卡；列表自动清空干扰筛选并切到「待审核」、
   回到第一页，新题首行高亮；结果生成后按钮置灰，避免重复入库。
3. 错题删除确认文案统一为「确定删除这道错题？」。
4. 学生作答页移除音频振荡器占位，只播放题目真实音频 URL；音频缺失时给出明确提示。
5. 头像：学生首页、全局顶栏、个人信息页三处统一优先渲染 `avatarUrl`，图片加载失败自动回退姓名首字。
6. 密码 UI：个人中心改为 `el-form` 规则校验（含格式常驻提示、确认密码一致性）；
   管理员新建账号、班主任添加学生、两处重置密码均增加确认密码输入与校验。
7. 临时密码复查：重置成功后临时密码写入 10 分钟短期缓存，新增
   `GET /accounts/{id}/temporary-password`；学校端账号列表和班主任学生菜单可在有效期内再次查看、复制。
8. 入班审批：后端申请项补充 `sourceApproved / targetApproved`，审批页新增「双签进度」列；
   学生转班弹窗明确提示需原班与目标班双方班主任通过。
9. 菜单种子数据同步新增教师端、学校端「入班审批」菜单；登录页补充「首次登录后请及时修改初始密码」。
10. 学生测评列表继续显示已结束测评并禁用进入；当前演示数据中音乐/美术均有进行中的测评。

**涉及文件**

- 后端：`apps/accounts/services/accounts.py`、`apps/accounts/services/account_data.py`、
  `apps/accounts/services/auth.py`、`apps/accounts/account_serializers.py`、
  `apps/accounts/account_views.py`、`apps/accounts/account_urls.py`、
  `apps/accounts/management/commands/seed_menus.py`、`apps/classes/services.py`、
  `apps/classes/serializers.py`、`common/constants.py`
- 前端：`src/views/QuestionsView.vue`、`src/views/AccountsView.vue`、
  `src/views/TeacherStudentsView.vue`、`src/views/ClassApprovalView.vue`、
  `src/views/ProfileView.vue`、`src/views/student/StudentAttemptView.vue`、
  `src/views/student/WrongQuestionsView.vue`、`src/views/student/StudentHomeView.vue`、
  `src/layouts/AppShell.vue`、`src/views/LoginView.vue`、`src/types/index.ts`、`src/api/index.ts`

**验证**

- `python manage.py check` 无问题；
- 后端 `apps.accounts apps.classes apps.exams apps.qbank` 共 146 项测试全部通过；
- `npm run build` 构建成功；
- 运行中验证账号列表返回 `hasTemporaryPassword`，临时密码接口在无缓存时返回友好的 404 文案；
- 未新增数据库迁移，未改动业务演示数据。

---

### 2026-11-12 20:57 · BE-014 / FE-013 新增「音频选择判断题」

**修改时间**：2026-11-12 20:56–20:57

**类型**：后端 / 前端 / 题库

**背景**

反馈要求新增一种客观题型：播放音频后选择或判断，系统自动判分，音频真实上传并可播放。

**执行内容**

1. 后端 `QuestionType` 新增 `audio_choice_judge`（音频选择判断）；
   加入选择题选项校验、单答案校验、试卷题型权重与分节名称。
2. 自动判分将 `audio_choice_judge` 纳入客观题分支，按单选答案 `{value}` 判分；
   该题型创建/修改时必须绑定至少一个音频资源，否则返回 400。
3. 前端题库表单新增该题型：可上传/更换/移除音频，答案按单选处理；
   美术老师题型下拉不展示该音频题型。
4. 学生作答页复用现有音频播放与选项交互，提交后自动判分并进入错题本。
5. 题库列表排序改为最新创建优先，AI 新生成待审题出现在首行并高亮。

**涉及文件**

- `Art_assessment_backend/common/enums.py`
- `Art_assessment_backend/apps/qbank/services.py`
- `Art_assessment_backend/apps/exams/services/attempt.py`
- `Art_assessment_backend/apps/exams/services/paper.py`
- `Art_assessment_frontend/src/views/QuestionsView.vue`
- 学生端及题库各题型标签文件

**验证**

- `python manage.py check` 无问题；
- 新增 `apps/exams/tests/test_scoring_rules.py`，6 项判分规则测试通过；
- `npm run build` 构建成功。

---

### 2026-11-12 20:54 · FE-012 / BE-013 统一账号规则、入班审批与错题卡片

**修改时间**：2026-11-12 20:52–20:54

**类型**：前端 / 后端 / 交互

**执行内容**

1. 新增前端常量 `src/constants/validation.ts`：年级 1–9、密码 8–32 位且含字母和数字、
   登录账号 4–32 位、学籍号 6–20 位，并统一提示文案。
2. `ClassesView`、`CoursesView` 年级选项改为 1–9。
3. 新增「入班审批」独立页面 `/teacher/approvals` 和菜单入口：
   - 后端新增 `GET /classes/requests`，汇总当前班主任/学校管理员可审核的待处理申请；
   - 转班申请返回 `reviewClassId`，前端据此用原班或目标班身份审核；
   - 班级管理页顶部也提供「入班审批」快捷入口。
4. 学生测评卡片使用后端 `phase/isEnded/isStarted`：已结束/未开始显示禁用状态，
   学生列表不再因 `status=published` 过滤掉已结束测评。
5. 错题本四张统计卡片可点击筛选掌握状态，并高亮当前筛选；
   「我的错题」删除操作文案缩短。
6. 美术教师试题列表隐藏音频标签列与曲风/情绪筛选，题型只保留非音频题型；
   学生评分页只在音乐测评或音频题中展示音频分析。
7. 学生首页头像支持 `avatarUrl` 图片，未设置时回退姓名首字。

**验证**

- `npm run build` 构建成功；
- 后端 140 项原测试全部通过。

---

### 2026-11-12 20:48 · BE-012 / FE-011 账号密码、年级学籍与初始密码统一

**修改时间**：2026-11-12 20:47–20:59

**类型**：后端 / 前端 / 账号

**背景**

反馈指出年级范围、密码规则、登录账号/学籍号规则不统一，新建账号看不到初始密码，
编辑学生年级/班级不生效，临时密码关闭后丢失。

**执行内容**

1. 后端统一年级常量 `GRADE_MIN=1`、`GRADE_MAX=9`，账号、班级、试卷、题库序列化器全部引用。
2. 统一密码规则：8–32 位且至少包含字母和数字，提示文案
   `密码需为 8~32 位，且至少包含字母和数字`；新增 `StrongPasswordField`。
3. 登录账号规则 4–32 位字母/数字/下划线；学籍号 6–20 位字母或数字；
   学籍号登录改为大小写不敏感，并做大小写不敏感唯一性校验。
4. 新增 `DEFAULT_INITIAL_PASSWORD=Art@2026`；创建教师/学生/机构管理员时：
   - 可自定义初始密码，未填则使用默认密码；
   - 创建响应返回 `initialPassword`，前端弹窗展示并支持复制/下载。
5. 重置密码接口支持可选自定义新密码，返回 `temporaryPassword`；
   前端改为持久结果弹窗，可复制，关闭前不会丢失。
6. 编辑学生账号支持保存 `studentNo`、`grade`、`classId`，并校验班级与年级一致。
7. 个人信息修改密码、账号创建/重置、教师与学生导入统一使用同一密码规则。

**涉及文件**

- `Art_assessment_backend/common/constants.py`、`common/passwords.py`、`common/serializers.py`
- `Art_assessment_backend/config/settings/base.py`
- `apps/accounts/validators.py`、`account_serializers.py`、`services/accounts.py`、
  `services/account_data.py`、`services/auth.py`、`services/account_import.py`
- `apps/classes/serializers.py`、`apps/classes/imports.py`
- `apps/exams/serializers.py`、`apps/qbank/serializers.py`
- `Art_assessment_frontend/src/constants/validation.ts`
- `AccountsView.vue`、`TeacherStudentsView.vue`、`ProfileView.vue`、`LoginView.vue`

**验证**

- `python manage.py check` 无问题；
- 后端 `apps.accounts apps.classes apps.exams apps.qbank` 共 140 项测试通过；
- `npm run build` 构建成功。

---

### 2026-11-11 12:48 · DOC-008 4′00″ 脚本把收尾段移到题库段之后

**修改时间**：2026-11-11 12:48

**类型**：文档 / 演示

**背景**

用户指出第 10 段是结尾，不应停在题库段；要求把收尾放到最后。

**执行内容**

1. 调整 `项目演示脚本_艺术素质测评平台_4分钟.md` 的段落顺序：
   - 第 10 段：3:06–3:36，题库管理员（原第 11 段，前移 24 秒）；
   - 第 11 段：3:36–4:00，收尾（原第 10 段，移到全片最后）。
2. 收尾段的停留页由「省级证书页」改为「课程章节页」；
   收尾口播不变。
3. 同步更新标题说明、Tab 5 时间、差异表、加时/压缩说明和 3′30″ 回退方式。
4. DOC-007 中「3:30–4:00 题库段」为调整前版本，以本条为准。

**验证**

- 重新解析 11 个分段：0:00 起连续到 4:00，合计 **240 秒**；
- 段落编号顺序为 1–11，第 11 段为收尾，内容与 3′30″ 版一致；
- 3′30″ 回退方式：去掉第 10 段题库端，收尾回到 3:06–3:30。

---

### 2026-11-11 12:47 · DOC-007 演示脚本扩展到 4′00″，追加题库管理员镜头

**修改时间**：2026-11-11 12:47

**类型**：文档 / 演示

**背景**

用户要求在 3′30″ 版基础上把演示时长增加到 4 分钟，**前面的内容不改**，
在末尾补一段题库管理员介绍。

**执行内容**

1. 新增 `C:\Users\ter\Desktop\项目演示脚本_艺术素质测评平台_4分钟.md`，
   完整保留第 1–10 段（0:00–3:30）的时间轴、屏上描述和口播。
2. 在收尾后追加第 11 段（3:30–4:00，30 秒）「题库管理员：公共题库与 AI 出题」，
   使用 `question_admin`（孙倩）：
   - 「试题管理」展示公共题库筛选、「共 6641 道试题」、「AI 出题」和「创建试题」；
   - 打开「AI 出题（美术）」弹窗，展示年级、单元、知识点、题型、难度，
     以及「仅作为待审草稿，必须逐条审核」提示；**不点「生成待审题」**；
   - 「课程章节」展示 18 门课程、每门 6–7 个章节和章节表的「题目数」。
3. 开演前标签页由 4 个增加到 5 个；检查项补充 Tab 5 的题量、AI 弹窗和课程章节，
   并保留 `Ctrl+F5` 不清空 sessionStorage、重新登录后默认落在「项目概览」的提醒。
4. 红线补充题库端约束：只打开 AI 弹窗，不点「生成待审题」，
   不执行创建、编辑、删除、审核等会改数据的操作。
5. 更新差异表、加时/压缩说明：
   - 题库行改为「已放在 3:30–4:00 第 11 段」；
   - 只要 3′30″ 时去掉第 11 段即可；
   - 压缩到 3 分钟需去掉第 4、9、11 段。
6. 同步更新旧脚本顶部指针：
   - 4′30″ 原文件改为指向 4′00″ 版本，并注明 3′30″ 版仍可查；
   - 1′30″ 文件改为指向 4′00″ 版本。

**说明**

- 3′30″ 版 `项目演示脚本_艺术素质测评平台_3分30秒.md` 保留不动，可随时回退；
- 第 11 段为独立加时镜头，主流程在第 10 段已完整收尾；
- 题库端只读展示，不生成、不审核、不增删题目。

**验证**

- 解析 4′00″ 脚本的 11 个分段标题，时间轴连续：
  0:00–0:15、0:15–0:31、0:31–0:48、0:48–1:05、1:05–1:21、
  1:21–1:51、1:51–2:23、2:23–2:47、2:47–3:06、3:06–3:30、3:30–4:00，
  合计 **240 秒**；
- 用无头 Edge 实际渲染题库端核对：`question_admin` 可打开「试题管理」，
  底部为「共 6641 道试题」，「AI 出题」弹窗标题为「AI 出题（美术）」且带待审提示；
  「课程章节」为 18 门课程，当前「七年级音乐（人教版）」6 个章节，
  第一章「歌唱祖国」题目数为 101；
- 课程列表当前顺序为七年级在前、再一年级至九年级，**不是按年级升序**，
  脚本因此只描述「18 门课程、每门 6–7 个章节」，不写排序；
- `Ctrl+F5` 不会清空 sessionStorage，Tab 2–5 需退出重登的提醒已写入开演前检查。

---

### 2026-11-11 11:38 · DOC-006 演示脚本时长更正为 3′30″ 并按当前系统重写

**修改时间**：2026-11-11 11:38

**类型**：文档 / 演示

**背景**

用户更正上一轮需求：演示时长不是 1′30″，而是 **3′30″**（三分半）。
DOC-005 的 1′30″ 版本保留备查，但不再作为主演示脚本。

**执行内容**

1. 新增 `C:\Users\ter\Desktop\项目演示脚本_艺术素质测评平台_3分30秒.md`，
   以 4′30″ 旧脚本为底稿，按当前系统重写为 210 秒时间轴。
2. 主线确定为：登录页七种身份 → 学生音乐练习测评（第 10 题演唱录音）
   → 学生成绩构成、错题本、证书 → 美术老师人工评分
   → 数据统计环形图与教师学科权限提示 → 省级统计下钻 → 省级证书管理 → 收尾。
3. 提前打开 4 个标签页（登录页、学生、美术老师、省级），
   Tab 2–4 各自登录、互不影响；学生从答题页用「保存并退出」返回，不提交答卷。
4. 修正旧脚本与当前系统不一致的内容：
   - 当前 `teacher_music` 无待评分任务，改用有 2 条待处理美术答卷的 `teacher_art`
     （「113正式测评」，第 16 题 16.65 分，作品主题「风吹麦浪」）；
   - 评分页已移除 AI 建议分，实践题全部人工终评；
   - 学生成绩由 1 条 30.4 分变为 9 条，正式测评与平时练习分开展示；
   - 错题总数由 2 道变为 52 道；
   - 省级证书页当前只有关键词 + 学科筛选，没有市州/区县/学校三级联动，
     脚本明确不演示联动；
   - 统计页当前使用演示假数据，脚本要求不报具体统计数字；
   - 音频标签服务端口为 `:8100`，本流程不调用。
5. 同步更新两个旧脚本顶部指针：
   - 4′30″ 原文件指向新的 3′30″ 版本；
   - 1′30″ 文件标注「时长已更正为 3′30″，保留备查」。

**说明**

- 统计页假数据仍由 `src/utils/demoStatistics.ts` 提供，展示结束后删除；
- 脚本中的「您不是该科的老师，无法使用该功能」与前端实际提示一致；
- 脚本明确不提交答卷、不发布成绩、不生成证书，避免演示改动业务数据。

**验证**

- 按当前接口核对：`student` 王浩然可进入「七年级（1）班·音乐练习测评」，
  第 10 题为 `audio_upload`；共有 9 条成绩、52 道错题、3 张证书；
- `teacher_art` 赵敏有 4 个任教班级、2 条「评分中」答卷，
  第一行「七年级（1）班·美术阶段测评」为 0 题，第二行「113正式测评」
  待评分 1 题，第 16 题 16.65 分；
- 省级 `province_admin` 统计默认选中「市州」，证书页有 3 张证书；
- 用无头 Edge 实际渲染核对：学生「我的测评」按钮为「进入练习」；
  教师评分表 2 行、113 待评分 1 题；教师统计页环形图正常渲染
  （2 个 canvas）；省级统计页「市州」单选按钮为选中状态；
- 开演前检查已注明 `Ctrl+F5` 不会清空 sessionStorage，
  Tab 2–4 需点「退出」重新登录，才能拿到教师身份字段；
  重新登录后 Tab 3/4 默认落在「项目概览」，开演前需点回
  「学生评分」「数据统计」，不占用正式演示时间；
- 教师学科筛选拦截逻辑与提示文案已在前端实现并通过 typecheck / build。

---

### 2026-11-11 11:13 · DOC-005 演示脚本压缩为 1′30″ 并按当前系统修正

**修改时间**：2026-11-11 11:13

**类型**：文档 / 演示

**背景**

原 4′30″ 演示脚本仍包含已移除的 AI 自动评分（AI 建议分 13.51）、
旧音乐模型端口 `:8090`、`teacher_music` 有待评分任务等过期信息，
与当前系统不一致；用户要求把演示时间压缩到 1′30″。

**执行内容**

1. 新增 `C:\Users\ter\Desktop\项目演示脚本_艺术素质测评平台_1分30秒.md`，
   原 `项目演示脚本_艺术素质测评平台(1).md`（4′30″）保留备查，
   并在旧版顶部增加指向新版的一行说明。
2. 90 秒主线确定为：登录页七种身份 → 学生音乐练习测评（第 10 题演唱录音）
   → 美术老师人工评分 → 数据统计环形图与教师学科权限提示 → 收尾。
3. 提前打开 4 个标签页（登录页、学生、美术老师、省级可选），
   每个标签页独立登录，现场只切换，不把时间花在反复退出登录上。
4. 修正旧脚本与当前系统不一致的内容：
   - 登录页已改为「演示身份快捷填入」+「测试账号」，不再是「选中身份后变成登录XXX」；
   - 评分页已移除 AI 建议分，实践题全部人工终评；
   - 当前 `teacher_music` 无待评分任务，改用有 2 条待评美术作品的 `teacher_art`；
   - 音频标签服务端口由 `:8090` 改为 `:8100`，90 秒流程不调用；
   - 统计页当前使用演示假数据，脚本明确要求不报具体数字；
   - 「268 功能验收」已删除，不再出现。
5. 新增 10 秒可选省级镜头：切到 `province_admin` 的「数据统计」，
   默认按「市州」展示排名与参与情况。

**说明**

- 统计页假数据仍由 `src/utils/demoStatistics.ts` 提供，展示结束后删除；
- 脚本中的「您不是该科的老师，无法使用该功能」与前端实际提示一致；
- 脚本明确不提交答卷、不发布成绩、不生成证书，避免演示改动业务数据。

**验证**

- 账号与数据范围按当前接口核对：`student` 王浩然可进入
  「七年级（1）班·音乐练习测评」，第 10 题为 `audio_upload`；
  `teacher_art` 赵敏有 2 条待处理美术答卷，其中 1 条为「待评分 1 题」；
- 统计页教师端按班级、省级按市州，环形图使用 `demoStatRows` 生成的数据；
- 教师学科筛选拦截逻辑与提示文案已在前端实现并通过 typecheck / build。

---

### 2026-11-11 11:07 · FE-011 数据统计各端口填充演示假数据

**修改时间**：2026-11-11 11:07

**类型**：前端 / 演示数据

**背景**

演示数据中参与人数和成绩样本偏少，部分端口（学校、市州）只有一个统计对象，
扇形图与排名列表展示效果不足。用户要求先为每个端口填入假统计数据用于展示，
演示结束后再统一删除。

**执行内容**

1. 新增 `src/utils/demoStatistics.ts`：
   - 顶部注释标明「演示用假统计数据，展示结束后删除本文件」；
   - 覆盖教师、学校管理员、区县管理员、市州管理员、省管理员五种端口；
   - 保留接口返回的真实统计对象名称与 ID，对象不足时按维度补充名称；
   - 按对象名称做确定性哈希生成学生数、参与人数、平均分、合格率、优秀率，
     刷新页面数值稳定，不会随机跳动；
   - 班级 38–52 人、学校 820–1860 人、区县 5200–11800 人、市州 32000–78000 人，
     参与率 82%–98%。
2. `src/views/StatisticsView.vue`：
   - 统计接口返回后优先使用 `demoStatRows(...)`；标记 `DEMO-FAKE-STATS`；
   - 顶部四张指标卡改为按当前（假）统计行重新汇总，
     保证学生总数、实际参与、参与率、平均分与图表一致；
   - 关键词筛选仍作用于假数据对象名称。

**删除方式（演示结束后）**

删除 `src/utils/demoStatistics.ts`，移除 `StatisticsView.vue` 中的
`demoStatRows` 导入和 `DEMO-FAKE-STATS` 两行赋值即可恢复真实统计。

**验证**

- `npm run typecheck` 通过；
- Vite 热更新已加载新模块；
- 后端重启后 `/auth/me` 返回 `teacherSubjects` 与 `isHeadTeacher`，
  教师端统计页正常进入。

---

### 2026-11-11 11:04 · BE-011 / FE-010 教师三种身份的功能权限提示

**修改时间**：2026-11-11 11:04

**类型**：后端 / 前端 / 权限

**背景**

教师账号存在班主任、音乐老师、美术老师三种身份，不同身份可使用的功能不同。
此前教师仍可通过菜单或筛选器进入非本人学科的功能，页面只显示空数据，
没有明确提示。用户要求：无法使用的功能点击时不跳转，并提示
「您不是该科的老师，无法使用该功能」。

**执行内容**

1. 后端 `apps/accounts/services/profile.py`：
   - `build_user_profile` 新增 `teacherSubjects`（由 `ClassTeacher` 任教记录
     与 `TeacherProfile.subject` 合并推导）和 `isHeadTeacher`
     （是否为任一班级的班主任）；
   - 非教师账号返回空数组 / `false`。
2. 后端 `apps/accounts/tests/test_me.py`：
   - 原资料更新测试补充两个新字段断言；
   - 新增 `test_me_teacher_identities`，验证音乐教师返回
     `teacherSubjects == ["music"]`、`isHeadTeacher == True`。
3. 前端新增 `src/utils/teacherAccess.ts`：
   - `teacherSubjects`、`isHeadTeacher`、`isSubjectTeacher`；
   - `ensureTeacherSubject` 在学科不匹配时弹出统一警告
     「您不是该科的老师，无法使用该功能」并返回 `false`。
4. 前端 `src/router/index.ts`：
   - 教师端试题、评分、证书、组卷、测评、成绩、统计路由标记
     `teacherSubjectRequired`；
   - 导航守卫拦截：无任何任教学科的教师不得进入学科功能；
     带 `?subject=music|art` 且不是本人学科时原地停留并提示。
5. 前端学科筛选与切换拦截：
   - `CertificatesView.vue` 默认使用教师本人学科，切换到非本人学科时回退并提示；
   - `QuestionsView.vue`、`PapersView.vue`、`AssessmentsView.vue`、
     `ScoresView.vue`、`StatisticsView.vue` 的学科筛选同样拦截；
   - `PapersView.vue` 的选题学科选择器同步拦截。
6. 前端 `src/types/index.ts`：`UserProfile` 新增
   `teacherSubjects?: Subject[]`、`isHeadTeacher?: boolean`。

**说明**

- 后端原本已按 `ClassTeacher` 和 `TeacherProfile.subject` 做数据范围隔离，
  本次只补齐身份字段与前端入口提示，不改变已有数据权限；
- 班主任身份目前只用于身份展示与后续班主任功能判断，
  不额外授予音乐 / 美术学科操作权限。

**验证**

- `pytest apps/accounts/tests/test_me.py -q`：13 passed；
- `npm run typecheck` 通过；
- 后端重启后验证 `teacher` 账号返回
  `music / ["music"] / True`。

---

### 2026-11-11 10:51 · FE-009 移除「功能验收」并新增参与情况扇形图

**修改时间**：2026-11-11 10:51

**类型**：前端

**背景**

项目概览中的「268 功能验收」圆环属于开发验收标记，不应出现在正式界面；
数据统计只有平均分柱状图和明细表，缺少参与情况的直观比例展示。

**执行内容**

1. `src/views/DashboardView.vue`：删除 hero 区域的「268 功能验收」圆环，
   并移除文案中的「268 项功能可按角色持续验收」；
   同时删除 `src/styles/index.css` 中不再使用的 `.hero-orbit` 样式。
2. `src/views/StatisticsView.vue`：新增「参与情况」环形扇形图。
   - 已参与（绿色）/ 未参与（灰色）两片，中心显示总参与率；
   - 图例、悬浮提示显示人数与百分比；
   - 数据由当前筛选后的统计行汇总，随学科、关键词、分组维度联动；
   - 统计对象按端口区分，沿用现有分组选项：
     教师→班级；学校管理员→班级/学校；区县管理员→学校/区县；
     市州管理员→学校/区县/市州；省管理员→学校/区县/市州。
   - 右侧新增「各统计对象参与情况」列表，逐个显示参与率进度条、
     已参与人数与未参与人数；无数据时显示空状态。
3. `src/styles/index.css`：新增 `.participation-grid`、`.participation-list`、
   `.participation-bar` 等样式，窄屏下自动单列。

**补充（2026-11-11 10:55）**：无人参与或统计范围内没有学生时，扇形图仍渲染为
一整圈灰色「未参与」，中心显示 `0.0% / 暂无参与数据`，不再出现空白图表；
悬浮提示按实际人数显示 0 人，不受占位值影响。

**修复（2026-11-11 10:58）**：老师端实际仍看不到扇形图，定位为
`src/utils/echarts.ts` 按需引入时只注册了 `BarChart`、`LineChart`，
没有注册 `PieChart`、`LegendComponent`、`TitleComponent`，饼图配置被直接忽略。
已补齐这三个模块，老师端与其他管理端共用同一组件，刷新后均生效。

**验证**

- `npm run typecheck` 通过；
- `npm run build` 通过（8.79s）；
- 五种管理端账号调用统计数据接口，均返回对应统计对象：
  教师 3 个班级、学校管理员 1 所学校、区县管理员 10 个区县、
  市州管理员 1 个市州、省管理员 10 个市州；
- 参与人数与学生人数均可由接口字段直接汇总，扇形图无需新增后端接口。

---

### 2026-11-11 10:38 · AI-008 AI 出题支持云 API（本地模型就绪前的过渡方案）

**修改时间**：2026-11-11 10:38

**类型**：后端 / 配置 / 文档

**背景**

本地基座模型 Qwen2.5-3B-Instruct 尚未落盘，8002 服务无法启动。
按用户要求，先接入兼容 OpenAI Chat Completions 的云 API 出题，
后续拿到本地模型后只需切回 `QGEN_PROVIDER=model_b`，前端和业务链路不变。

**执行内容**

1. `apps/qbank/qgen.py`：
   - 新增 `qgen_provider()`，读取 `QGEN_PROVIDER`（`model_b` / `api`，其他值回退 `model_b`）；
   - 新增 API 模式的系统提示词与用户消息构造，约束 JSON 输出、单选 4 选项、
     禁止图片依赖题与评分话术；
   - 新增 `_api_chat()` 调用 `{QGEN_API_BASE}/chat/completions`，
     HTTP 错误返回 502、连接失败返回 503、未配置返回 503；
   - 新增 `_extract_json_object()` 兼容 ```json 代码块与前后说明文字；
   - 新增 `_generate_via_api()`，模型输出仍回填受控字段（学科/年级/单元/知识点/
     题型/难度），并标记 `source=cloud_api`、`created_by=api:<model>`；
   - 生成结果继续走原有题干预清洗、图片依赖/评分话术拦截、精确+近似查重、
     `pending` 入库与审计日志，`source_meta.provider` 记为 `qgen_api`；
   - `catalog_for_client()` 在 API 模式返回对应 `provider` 与说明文案。
2. `config/settings/base.py`：新增 `QGEN_PROVIDER`、`QGEN_API_BASE`、
   `QGEN_API_KEY`、`QGEN_API_MODEL`、`QGEN_API_TIMEOUT`、`QGEN_API_TEMPERATURE`。
3. `.env.example`：补充云 API 配置说明与服务商示例。
4. `docs/model-b-qgen.md`：新增「方式二替代：云 API」章节，含 DeepSeek /
   通义千问 / 智谱 / OpenAI 的地址与模型示例，注明密钥只写 `.env`。
5. `start_system.bat`：本地模型未就绪时不再强制 `QGEN_ENABLED=0`，
   避免覆盖 `.env` 中的云 API 配置。
6. `apps/qbank/tests/test_qgen.py`：新增云 API 生成成功、未配置返回 503 两个用例。

**安全说明**

- 密钥仅通过 `.env` 的 `QGEN_API_KEY` 读取，不写入代码、日志或仓库；
- 出题结果仍为 `pending`，必须由题库管理员审核，不会自动进入公共题库。

**验证**

- `python manage.py check` 无问题；
- `apps/qbank/tests/test_qgen.py` 7 个用例全部通过（含新增 2 个）；
- 2026-11-11 10:39 接入 DeepSeek（`QGEN_API_MODEL=deepseek-flash`，密钥仅写入
  `Art_assessment_backend/.env`），重启后端后实测：
  - `GET /api/v1/questions/qgen/catalog` 返回 `provider=qgen_api`、`enabled=true`；
  - `POST /api/v1/questions/qgen/generate` 生成题目 id 27326（一年级美术「三原色」
    单选，4 选项，答案 A），状态 `pending`，`source_meta.provider=qgen_api`；
- 该题保留在待审列表中，供审核流程演示，未自动通过。

---

### 2026-11-11 10:35 · ENV-004 新增项目一键启动脚本（含 AI 出题模型）

**修改时间**：2026-11-11 10:35

**类型**：运维 / 启动脚本

**背景**

此前启动项目需要分别启动后端、前端、音频模型；AI 出题模型（8002）还需要额外
设置环境变量并手动启动，容易遗漏。按用户要求，启动项目时自动尝试拉起 8002。

**执行内容**

1. 新增 `start_system.bat`（项目根目录）：
   - 先检测端口，已在运行的服务自动跳过，避免重复启动；
   - 依次启动后端 8000、前端 5173、音频模型 8100；
   - 检查基座模型与运行环境，满足条件时自动启动 AI 出题模型 8002；
   - 8002 可启动时给 Django 设置 `QGEN_ENABLED=1`，否则为 `0`。
2. 新增 `scripts/start_model_b.bat`：
   - 使用 `01_给后端A(1)\.venv` 启动 uvicorn；
   - 读取环境变量 `QGEN_MODEL`，或自动查找
     `D:\models\Qwen2.5-3B-Instruct`、`%USERPROFILE%\models\Qwen2.5-3B-Instruct`；
   - 基座模型或虚拟环境缺失时打印原因并退出，不阻塞其他服务。
3. `docs/model-b-qgen.md` 增加「一键启动」说明。

**当前限制**

交付包只有 LoRA 适配器，基座模型 Qwen2.5-3B-Instruct 不在磁盘上，
`01_给后端A(1)\.venv` 也未创建，因此当前脚本会跳过 8002 并提示。
补齐模型与依赖后无需改脚本，直接双击 `start_system.bat` 即可自动启动。

**验证**

- 实际运行 `start_system.bat`：8000 / 5173 / 8100 均正确识别为已运行并跳过；
- 8002 因缺少基座模型和环境，按预期提示跳过；
- `scripts/start_model_b.bat` 单独运行，正确提示缺少运行环境。

---

### 2026-11-11 10:24 · AI-007 补齐音频作品标签并移除 BPM 区间筛选

**修改时间**：2026-11-11 10:24

**类型**：数据 / 前端 / 后端

**背景**

题库管理页的 BPM 上下限筛选实际没有可用的题目资源（题库中无音频题资源），
属于无效入口；同时学生作品中的音频文件全部显示「待分析」。

**执行内容**

1. 批量生成音频标签：`python manage.py analyze_audio`
   - 处理学生作品音频 6 个，成功 5 个，失败 1 个；
   - 失败文件为 `test-tone.mp3`（ID 37，仅 2004 字节的合成测试音），
     arteval-v4 服务无法解码，标记为 `failed`；
   - 成功的 5 个文件已写入曲风、情绪、调式、BPM、参考分等标签，
     学生作品列表接口已能返回 `audioTags`。
2. 移除 BPM 上下限筛选：
   - 前端 `QuestionsView.vue` 删除两个输入框、`bpmMin/bpmMax` 表单字段及重置逻辑；
   - 后端 `question_views.py` 删除对应 OpenAPI 参数，
     `services.py` 删除 BPM 过滤逻辑；
   - `docs/audio-tagging.md` 同步更新过滤示例。
3. 排查「图片作品」题量：题库中实际有 117 道 `image_upload` 题，
   全部为美术、已通过状态，主要分布在七年级（75 道）；
   教师账号若只任教音乐，或列表仍保留「学科=音乐」筛选时会显示 0 条，
   属于权限/筛选条件所致，不是数据缺失。

**涉及文件**

- `apps/qbank/services.py`
- `apps/qbank/question_views.py`
- `docs/audio-tagging.md`
- `Art_assessment_frontend/src/views/QuestionsView.vue`

**验证**

- `manage.py check` 无问题；
- `apps/qbank/tests` 全部通过；
- `npm run typecheck` 通过；
- 后端已重启，登录、题库列表接口正常；
- 学生作品列表返回 5 条 `completed` 音频标签（实验/嘻哈/摇滚，BPM 108–130）。

---

### 2026-11-11 10:02 · AI-006 正式导入 Model B 题库（1789 道待审题）

**修改时间**：2026-11-11 10:02

**类型**：数据 / 出题辅助

**背景**

AI-005 只完成了接入与试运行，未写入演示库。经确认后执行正式导入，把 Model B
交付题库中的可用题卡写入系统，全部保持 `pending` 状态。

**执行内容**

1. 导入前备份数据库：`_backup_20261111_before_qgen_import/db.sqlite3`
   （14,020,608 字节，与导入前一致）。
2. 执行 `python manage.py import_qgen_bank`，默认读取
   `01_给后端A(1)/题库数据/train_clean_2698.jsonl`。
3. 导入结果：
   - 读取 2698 行，新增 **1789** 道待审题；
   - 跳过简答/填空 888 道（`type_filtered`）；
   - 跳过图片依赖题 21 道（`image_dependent`）；
   - 题目 ID 范围 25537–27325；
   - 创建人：首位题库管理员；审计日志 `question.qgen_create` 1789 条。

**导入后数据**

| 项目 | 导入前 | 导入后 |
| --- | --- | --- |
| 题目总数 | 6814 | 8603 |
| approved | 6813 | 6813（未变） |
| pending | 1 | 1790 |

- 题型：单选 764、判断 1025；
- 年级分布：一年级 156、二年级 147、三年级 153、四年级 123、五年级 164、
  六年级 201、七年级 278、八年级 282、九年级 285；
- 覆盖 36 个单元；单选题均生成选项（764 道）；
- 无空答案、无空解析、导入题卡之间无重复题干。

**影响与安全边界**

- 新题全部为 `pending`，不会进入组卷、测评、随机练习和错题本；现有
  `approved` 题量和演示数据未改动；
- 题库管理端可按状态筛选审核，通过后才进入公共题库；
- 回滚方式：停止后端后，用
  `_backup_20261111_before_qgen_import/db.sqlite3` 覆盖 `db.sqlite3` 即可。

**验证**

- 导入命令输出与试运行统计一致（1789 / 888 / 21）；
- ORM 核对：`source_meta.provider=model_b_qgen` 共 1789 条，全部 `pending`；
- 组卷服务仅取 `approved`，待审题不会被自动选入试卷。

---

### 2026-11-11 09:59 · AI-005 接入 Model B 美术出题模型（待审草稿）

**修改时间**：2026-11-11 09:59

**类型**：新增 / 出题辅助

**背景**

`01_给后端A(1)` 提供 Qwen2.5-3B-Instruct + QLoRA 美术出题模型。按冲突评估文档
（DOC-004）的方案接入：只做出题辅助，生成/导入题一律待审；不接模型的组卷和判分。

**涉及文件**

- 新增：`apps/qbank/qgen.py`（服务客户端、题卡转换、质量门禁、查重、导入）
- 新增：`apps/qbank/qgen_unit_map.json`（36 个模型单元 → 教材章节映射）
- 新增：`apps/qbank/management/commands/import_qgen_bank.py`
- 新增：`apps/qbank/management/commands/generate_qgen_questions.py`
- 新增：`apps/qbank/tests/test_qgen.py`
- 新增：`apps/qbank/migrations/0008_question_knowledge_point_question_source_meta.py`
- 新增：`docs/model-b-qgen.md`
- 修改：`apps/qbank/models.py`（`Question.knowledge_point`、`source_meta`）
- 修改：`apps/qbank/services.py`（题目详情返回知识点与来源元数据）
- 修改：`apps/qbank/serializers.py`、`question_views.py`、`question_urls.py`
  （目录与生成接口）
- 修改：`config/settings/base.py`、`.env.example`（`QGEN_*` 配置）
- 修改：`Art_assessment_frontend/src/types/index.ts`、`src/api/index.ts`、
  `src/api/mock.ts`、`src/views/QuestionsView.vue`（AI 出题入口）
- 修改：`README.md`、`CHANGELOG.md`

**更改内容**

1. 新增 `GET /api/v1/questions/qgen/catalog` 与 `POST /api/v1/questions/qgen/generate`，
   仅题库管理员可用；在线生成默认关闭（`QGEN_ENABLED=false`）。
2. 新增离线导入命令 `import_qgen_bank`：按映射表落到课程/章节，清洗题干，
   过滤简答/填空（填空可用参数打开），拦截图片依赖题与评分话术，
   精确 + 3-gram 近似去重，全部写为 `pending`。
3. 新增批量生成命令 `generate_qgen_questions`，支持 `--dry-run`、数量与失败跳过。
4. 题卡字段转换：模型分值丢弃，系统按题型给默认分（单选 5、判断 2）；
   `scoringMode` 固定 `auto`；难度 1~3 直接映射；来源/模型版本写入 `source_meta`
   并记审计日志。
5. 前端题库管理页新增「AI 出题」按钮与弹窗：选年级/单元/知识点/题型/难度，
   生成后展示题卡并提示已保存为待审；服务未启用时按钮提示。
6. 明确不接模型 `/paper`、`/grade`，组卷、判分、成绩链路不变。

**验证**

- `python manage.py check`：无问题；
- `python manage.py migrate qbank`：`0008` 已应用；
- `python -m pytest -q`：全部通过（新增 5 项 Model B 测试）；
- `import_qgen_bank --dry-run`：读取 2698 行，可新增 1789 道待审题，
  跳过简答/填空 888 道、图片依赖 21 道；
- 单元映射检查：36/36 单元全部落到现有美术章节，无缺失；
- `npm run typecheck`、`npm run build`：通过；
- 后端已重启，`/api/v1/questions/qgen/catalog` 路由生效（未登录 401）。

**说明**

未执行正式导入，也未修改演示题库数据；正式导入需经确认后运行
`python manage.py import_qgen_bank`。

---

### 2026-11-11 09:52 · DOC-004 新增 Model B 美术出题模型冲突评估文档

**修改时间**：2026-11-11 09:52

**类型**：文档

**内容**

评估 `01_给后端A(1)` 中的 Qwen2.5-3B-Instruct + QLoRA 美术出题模型
（Model B）接入现有系统的冲突点，输出文档
`C:\Users\ter\Desktop\ModelB_美术出题模型_冲突与解决方案.md`。

文档覆盖：简答题/填空题下线、单元章节体系不一致、题卡字段与难度映射、
多选题缺失、分值/组卷规则、与现有判分链路重复、重复题、美术单学科、
基座模型与 GPU 环境、生成质量、并发超时、服务鉴权、创建人与审计等
15 类冲突，并给出分阶段接入方案、字段映射表、验收清单与风险登记。
未修改任何代码或数据。

---

### 2026-11-11 09:23 · AI-004 接入 arteval-v4 音乐标签模型（辅助功能）

**修改时间**：2026-11-11 09:23

**类型**：新增 / 模型辅助

**背景**

`arteval-v4` 是仓库外的多任务 CNN 音乐标签模型（曲风 13 类、情绪 4 类、
大小调、BPM），带一套可配置规则参考分。它只做音频标签，不参与业务判分，
因此与 AI-003 移除 AI 评分的结论不冲突：系统仍然只有自动判分与教师人工评分。

**涉及文件**

- 新增后端：`apps/files/audio_tags.py`、`apps/files/models.py`（`AudioAnalysis`）、
  `apps/files/migrations/0005_audioanalysis.py`、
  `apps/files/management/commands/analyze_audio.py`、
  `apps/files/tests/test_audio_tags.py`、`docs/audio-tagging.md`
- 修改后端：`common/enums.py`、`config/settings/base.py`、`apps/files/minio.py`、
  `apps/files/services.py`、`apps/files/views.py`、`apps/files/urls.py`、
  `apps/exams/presenters.py`、`apps/qbank/services.py`、
  `apps/qbank/question_views.py`、`apps/qbank/question_urls.py`、`.env.example`、`README.md`
- 新增模型服务：`arteval-v4/arteval-v4/service.py`、
  `arteval-v4/arteval-v4/requirements-service.txt`、`start_service.bat`
- 修复模型代码：`training/score.py`、`training/features.py` 中 librosa 0.11 下
  `offset=None` 报错，改为直接传数值
- 新增前端：`src/components/AudioTagCard.vue`
- 修改前端：`src/types/index.ts`、`src/api/index.ts`、`src/views/GradingView.vue`、
  `src/views/QuestionsView.vue`、`src/views/student/StudentArtworkView.vue`、
  `src/views/TeacherStudentsView.vue`
- 修改：`CHANGELOG.md`

**更改内容**

1. 新增 `AudioAnalysis` 独立表（与 `FileObject` 一对一），保存曲风/情绪/调式/BPM/
   调性、参考分、维度明细、模型版本与错误信息；不写 `Attempt`、`AttemptAnswer`、
   `Score` 任何字段，不使用 `ScoringMode`。
2. 独立推理服务 `service.py`：`GET /health`、`POST /analyze`，标准库 HTTP 服务，
   CPU 串行推理，默认 `127.0.0.1:8100`，不把 torch 装进 Django 解释器。
3. Django 侧 `audio_tags.py`：上传音频自动建待分析记录；`analyze_audio()` 调用服务、
   失败记录 `failed` 并返回 502；`analysis_payload()` 对未分析/失败状态返回占位。
   服务未启动时整体降级，上传、组卷、判分、成绩不受影响。
4. 新增 `GET/POST /api/v1/files/{id}/audio-analysis`；题目库新增标签筛选
   （`genre`、`emotion`、`bpmMin/bpmMax`、`hasAudioTags`）与
   `GET /api/v1/questions/{id}/similar-audio` 相似音频题目推荐。
5. 参考答案可见性：学生作品接口永不返回 `referenceScore` 与维度明细；教师评分页、
   题库详情、教师端学生作品页可见，并统一附带「非成绩」免责声明。
6. 教师评分页在实践作品题下展示学生音频参考卡（曲风/情绪/调式/BPM/规则参考分）；
   题库页新增「音频标签」列与筛选，按标签检索并可查相似题；学生作品页只展示标签，
   不出现参考分。
7. 新增批量命令 `analyze_audio`（`--category/--file-id/--limit/--force/--dry-run`）。
8. 新增 `docs/audio-tagging.md`，逐项审计与 AI 评分、自动/人工判分、成绩/统计/排名/
   证书、题目审核、组卷、学生作品、学情报告、文件删除与权限、音频格式、CPU 并发的
   重叠点与处理方式。

**影响**

- 模型只提供教学辅助标签，不参与判分、不改变任何成绩、排名、证书与学情报告；
- 学生端不展示规则参考分，避免被误当成成绩；
- 推理服务未启动或超时时，相关按钮提示失败，其余功能保持可用；
- 上传音频文件会多一条待分析记录，删除文件时同步软删除分析记录。

**验证**

- `GET http://127.0.0.1:8100/health`：`{"status":"ok","arch":"v4","epoch":40}`；
- `POST /analyze` 实测 30s WAV 返回曲风 Experimental（0.395）、情绪 tense（0.570）、
  调式 major（0.967）、BPM 117.57、规则参考分 79.5；
- `python manage.py migrate files`：`0005_audioanalysis` 已应用；
- `python -m pytest -q`：297 项全部通过（含新增 5 项音频标签测试）；
- `npm run typecheck`、`npm run build`：通过；
- 重启后端 `127.0.0.1:8000`，`/api/v1/files/1/audio-analysis` 路由生效（未登录返回 401）。

---

### 2026-11-10 20:14 · AI-003 完整移除 AI 评分（前端与后端）

**修改时间**：2026-11-10 20:14

**类型**：清理 / 评分

**问题**

AI-002 只删除了本地模型文件，外部 AI 评分适配层、`ScoringMode.AI`、`ai_score`
等字段、模型评分规则库和相关界面仍然保留，系统中仍存在一套无法使用且容易误解的
AI 评分链路。

**涉及文件**

- 删除：`apps/exams/services/ai.py`、`apps/exams/services/scoring_rules.py`、
  `apps/exams/views/scoring_rules.py`、`apps/exams/tests/test_scoring_rules.py`
- 删除：`apps/exams/rules/` 下的模型评分规则文件（保留 `teacher_total.yaml`）
- 修改：`common/enums.py`、`config/settings/base.py`、`apps/qbank/models.py`
- 修改：`apps/exams/models.py`、`services/attempt.py`、`services/grading.py`、
  `services/score.py`、`presenters.py`、`serializers.py`、`views/scores.py`、`urls.py`
- 新增：`apps/exams/migrations/0008_remove_ai_scoring.py`、
  `apps/qbank/migrations/0007_remove_ai_scoring.py`
- 修改：`apps/exams/tests/test_scores_statistics.py`
- 修改：`Art_assessment_frontend/src/types/index.ts`、`src/api/index.ts`、`src/api/mock.ts`
- 修改：`GradingView.vue`、`ScoresView.vue`、`TeachersView` 相关学生成绩页、
  `QuestionsView.vue`、`StudentResultsView.vue`、`StudentAttemptReviewView.vue`
- 修改：`Art_assessment_backend/README.md`、`CHANGELOG.md`

**更改内容**

1. 删除外部 AI 评分适配层与模型评分规则库（含 `scoring-rules` 三个接口），
   移除 `AI_PROVIDER`、`AI_BASE_URL`、`AI_TIMEOUT_SECONDS` 配置项。
2. `ScoringMode` 只保留 `auto` / `manual`；题库、答卷、试卷快照的评分方式同步收窄。
3. 删除 `Attempt.ai_score`、`Attempt.ai_error`、`AttemptAnswer.ai_score`、
   `AttemptAnswer.ai_analysis`、`Score.ai_score`；历史 AI 分数在迁移中并入主观分，
   历史 AI 评分题转为人工评分。
4. 成绩导入/导出模板删除「AI得分」列；重新判分删除 `aiReevaluate` 参数与 `aiError` 返回。
5. 前端删除 AI 评分选项、AI 分数/分析展示、AI 列导出与相关 mock 字段；
   实践作品题只显示教师人工评分。
6. README 改为说明系统只支持自动判分与教师人工评分，不依赖本地模型或外部 AI 服务。

**影响**

- 系统不再存在任何 AI 评分入口、字段、配置、接口或界面；
- 客观题仍自动判分，实践作品题与课外作品仍由教师人工评分；
- 历史成绩总分保持不变，原 AI 分数已并入主观分；
- 教师总评规则默认值 `apps/exams/rules/teacher_total.yaml` 不属于 AI 评分，继续保留。

**验证**

- `python manage.py makemigrations --check --dry-run`：无变更；
- `python manage.py migrate`：迁移已应用；
- `python -m pytest -q`：全部通过；
- `npm run typecheck`：通过；
- `npm run build`：构建通过。

---

### 2026-11-10 20:07 · AI-002 移除本地 AI/机器学习模型模块

**修改时间**：2026-11-10 20:07

**类型**：清理 / AI 模型

**问题**

项目中保留着从外部仓库导入的 `ai/music_evaluation` 音乐分析模块和 6 次训练的
`best_model.pt` 权重，但该模型未接入 Django 运行链路（缺少推理脚本与 torch 依赖），
只作为历史产物占用空间，容易让人误以为系统在使用本地 AI 模型。

**涉及文件**

- 删除：`Art_assessment_backend/ai/`（含 `music_evaluation` 全目录）
- 修改：`Art_assessment_backend/README.md`
- 修改：`CHANGELOG.md`

**更改内容**

1. 删除 `ai/music_evaluation/`：6 个 `best_model.pt`、训练记录、DSP 分析器、
   评测脚本、schema 与测试全部移除；
2. README 删除「音乐测评模型」的启动说明，改为说明模型已移除、实践题由教师人工评分；
3. 保留外部 AI 评分适配入口 `apps/exams/services/ai.py` 与 `AI_PROVIDER` 配置
   （默认 `none`，未启用），系统不依赖任何本地模型文件。

**影响**

- 项目不再包含任何 `.pt` 模型权重或本地推理代码；
- 现有题库、组卷、测评、判分、证书等功能不受影响；
- 已通过配置外部 `AI_BASE_URL` 使用 AI 评分的部署，不受本地模型删除影响。

**验证**

- `python manage.py check`：无问题；
- `python -m pytest -q`：全部通过。

---

### 2026-11-04 15:08 · FEAT-041 教师自动组卷支持先选班级并按年级/章节/单元限定题库

**修改时间**：2026-11-04 15:08

**类型**：前端 / 后端 / 组卷

**问题**

教师自动组卷只能按试卷年级抽题，无法先按任教班级定位，也不能缩小或扩大抽题范围；
题目分布在不同年级、章节时，教师无法只从本班对应教材范围组卷，也无法让整库参与抽题。

**涉及文件**

- 修改：`Art_assessment_frontend/src/views/PapersView.vue`
- 修改：`Art_assessment_backend/apps/exams/serializers.py`
- 修改：`Art_assessment_backend/apps/exams/services/paper.py`
- 修改：`Art_assessment_backend/apps/exams/tests/test_papers_assessments.py`
- 修改：`Art_assessment_backend/README.md`
- 修改：`CHANGELOG.md`

**更改内容**

1. 自动组卷弹窗先显示「任教班级」（教师账号只列出本人任教的班级），选定班级后自动带入班级年级；
2. 新增「年级 → 章节（课程）→ 单元（章节）」三级多选级联下拉，逐级过滤候选范围；
3. 年级支持「全选（整库可抽）」：前端传空 `grades`，后端不限制年级，该学科所有已通过试题
   都可参与抽题；不传 `grades` 的旧客户端仍按试卷年级抽题；
4. 后端新增 `grades`、`courseIds`、`chapterIds` 过滤；自动组卷可跨年级成卷，
   试卷归属年级仍保持任教班级年级，不再触发跨年级校验错误；
5. 新增两个测试：指定跨年级抽题、全年级整库抽题。

**影响**

- 教师组卷路径变为：选任教班级 → 多选年级 → 多选章节 → 多选单元 → 设置题型数量；
- 三级筛选都不选或年级全选时，整库（该学科已通过试题）均可抽取；
- 手动组卷和已有试卷不受影响。

**验证**

- `python -m pytest -q`：全部通过（含新增跨年级、整库抽题测试）；
- `npm run typecheck`：通过；
- `npm run build`：通过（8.65s）；
- 真实题库回滚验证：任教三年级班级、年级全选时生成 10 题 100 分试卷，
  抽到的题目覆盖 1/3/5/6/7/8 年级，证明整库可抽且跨年级校验已放行。

---

### 2026-11-04 14:56 · FEAT-040 试题编号连续排列，移除试题管理的资源功能

**修改时间**：2026-11-04 14:56

**类型**：前端 / 后端 / 试题管理

**问题**

试题管理列表的「编号」直接显示数据库主键，删除试题后编号出现跳号，看起来杂乱；
页面还保留着「资源」列、上传/删除资源的按钮和弹窗，实际题库已不再使用该功能。

**涉及文件**

- 修改：`Art_assessment_frontend/src/views/QuestionsView.vue`
- 修改：`Art_assessment_frontend/src/api/index.ts`
- 修改：`Art_assessment_backend/apps/qbank/services.py`
- 修改：`CHANGELOG.md`

**更改内容**

1. 「编号」改为按当前页顺序自动生成：`(页码 - 1) × 每页条数 + 行号 + 1`，
   翻页后继续连续编号，不再显示跳号的数据库主键；
2. 后端题目列表改为按 `id` 升序稳定排列，保证分页顺序与编号一致；
3. 删除试题管理的「资源」列、「资源」按钮、资源上传/删除弹窗及相关前端函数，
   同步删除 `api.questions.uploadResource` / `removeResource`；
4. 页面说明去掉「音视频资源关联」表述。

**影响**

- 试题编号在每一页内连续递增，跨页也连续；
- 试题管理不再提供资源上传与删除入口；题库查询页已有的资源预览、组卷与作答读取的
  题目资源数据不受影响，后端资源接口保留。

**验证**

- `python -m pytest -q`：全部通过；
- `npm run typecheck`：通过；
- `npm run build`：通过（9.02s）。

---

### 2026-11-04 14:49 · FEAT-039 题库去重、下线填空题并按知识点归入章节

**修改时间**：2026-11-04 14:33–14:49

**类型**：后端 / 数据 / 题库

**问题**

历史题库经过多轮生成与年级均衡，存在三个问题：同一道题反复出现；每个单元只有 3 道判断题，
客观练习量不足；大量题目挂在「拓展类」，与教材章节知识点脱节。填空题判分依赖精确匹配，
实际使用价值低，用户要求整体下线。

**涉及文件**

- 新增：`Art_assessment_backend/apps/exams/management/commands/organize_question_bank.py`
- 修改：`Art_assessment_backend/apps/exams/management/commands/seed_curriculum_units.py`
- 修改：`Art_assessment_backend/apps/exams/management/commands/seed_rich_demo.py`
- 修改：`Art_assessment_backend/apps/exams/management/commands/seed_all_portals.py`
- 修改：`Art_assessment_backend/apps/exams/services/paper.py`
- 修改：`Art_assessment_backend/apps/exams/tests/test_curriculum_units.py`
- 修改：`Art_assessment_backend/README.md`
- 修改：`Art_assessment_frontend/src/views/QuestionsView.vue`
- 修改：`Art_assessment_frontend/README.md`
- 修改：`CHANGELOG.md`

**更改内容**

1. 单元练习改为 7~9 道单选、3 道多选、12 道判断、1 道实践题（共 23~25 题），不再生成填空题；
   判断题按作品事实、概念解释、易混概念成对生成正误说法，保证每单元正、误判断都有；
2. 每个单元只分配一个重点作品与一个核心概念，跨单元不再产生同题干；章节讲解补充
   【知识结构】【相关概念】【易错提醒】与【本章练习】说明；
3. 新增 `organize_question_bank` 命令：整体下线填空题 → 按清洗后的题干全局去重
   （优先保留已入卷、已在章节、已通过审核的题）→ 按学科跨年级匹配作品名与核心概念，
   把「拓展类」及未绑定章节的题归入知识点最相关的章节，同步修正课程与年级
   （作品名单字标题如《虾》《春》也参与匹配）；匹配不到的题保留为拓展题；
   支持 `--dry-run`；
4. `seed_rich_demo`、`seed_all_portals` 删除填空题生成与组卷规则，改为
   6 单选 + 2 多选 + 2 判断；自动组卷权重去掉填空；
5. 前端出题表单不再提供「填空题」选项，删除对应的答案录入与校验；
6. 说明文档同步更新为 23~25 题的单元构成，并补充 `organize_question_bank` 用法。

**数据结果（本地 `db.sqlite3`，未提交）**

- 有效题目 4850 道，题干全部唯一；
- 题型：单选 2887、多选 558、判断 1169、音频作品 119、图片作品 117，填空与简答均为 0；
- 归入教材单元 4261 道，「拓展类」589 道，无章节归属题目 0 道，无空章节；
- 每单元均含 12 道判断题；随机练习仍为 6 单选 + 3 多选 + 1 判断、共 100 分。

**验证**

- `python -m pytest -q`：全部通过；
- `npm run typecheck`：通过；
- 滚动回滚事务内调用 `create_practice`（音乐、美术各一次）：均为 10 题、总分 100，
  题型为 6 单选 + 3 多选 + 1 判断。

**备注**

题库数据改动只落在本地 SQLite，仓库与远端不包含 `db.sqlite3`；重新初始化时按
`seed_curriculum_units` → `organize_question_bank` 顺序执行即可复现。

---

### 2026-11-04 14:30 · FEAT-038 证书管理改为只读，删除修改证书功能

**修改时间**：2026-11-04 14:30

**类型**：前端 / 后端 / 证书

**问题**

证书由正式测评成绩按规则生成，管理端却允许手动改证书编号、成绩、发证日期和状态。
手工改分会让证书与测评成绩、成长曲线不一致，也绕过了「得分率 90% 才发优秀证书」的规则。

**涉及文件**

- 修改：`Art_assessment_frontend/src/views/CertificatesView.vue`
- 修改：`Art_assessment_frontend/src/api/index.ts`
- 修改：`Art_assessment_frontend/src/api/mock.ts`
- 修改：`Art_assessment_backend/apps/exams/views/certificates.py`
- 修改：`Art_assessment_backend/apps/exams/services/certificate.py`
- 修改：`Art_assessment_backend/apps/exams/serializers.py`
- 修改：`Art_assessment_backend/apps/exams/tests/test_certificates_growth.py`
- 修改：`CHANGELOG.md`

**更改内容**

1. 证书列表去掉「修改」按钮，详情弹窗去掉「修改证书信息」按钮，删除修改弹窗与相关状态；
2. 前端删除 `api.certificates.update` 与 mock 的 `updateCertificate`；
3. 后端删除 `PATCH /api/v1/certificates/{id}`、`update_certificate` 服务和 `CertificateUpdateSerializer`；
4. 原 4 个修改证书测试合并为 `test_certificate_is_read_only`，断言 PATCH 返回 405 且数据不变；
5. 页面说明改为「查看、生成和下载」。

**影响**

- 证书只能由「生成测评证书」按成绩产生，生成后不可手动改动；
- 生成、查看、下载、列表权限与范围不变。

**验证**

- `python -m pytest -q`：通过（含 405 只读断言）；
- `npm run typecheck`：通过；
- `npm run build`：通过（8.74s）。

---

### 2026-11-04 14:30 · FEAT-037 教师评分支持直接输入分数

**修改时间**：2026-11-04 14:30

**类型**：前端 / 评分

**问题**

评分页的分数控件只有「−」「+」两个按钮，教师给实践作品打分时要连点几十次才能到目标分数，
无法直接键入 85、92.5 这类成绩。

**涉及文件**

- 修改：`Art_assessment_frontend/src/components/ScoreStepper.vue`
- 修改：`Art_assessment_frontend/src/styles/index.css`
- 修改：`CHANGELOG.md`

**更改内容**

1. 分数显示改为可输入的输入框，点击即全选，回车或失焦提交；
2. 输入非数字或空值时保持原分；超出范围自动收敛到 0~满分，并按步长精度四舍五入；
3. 按 Esc 取消本次输入，保留原分；
4. 保留原有加减按钮与按住连续加减，按钮操作后输入框同步显示新值；
5. 教师评分与学生评语共用的 `ScoreStepper` 全部生效。

**验证**

- `npm run typecheck`：通过；
- `npm run build`：通过（8.74s）。

---

### 2026-11-04 10:07 · FEAT-036 随机练习只出客观题，去掉实践题

**修改时间**：2026-11-04 10:07

**类型**：后端 / 前端 / 随机练习

**问题**

随机练习每套都会抽 1 道实践作品题（音乐音频上传、美术图片上传）。实践作品需要上传并由
教师人工评分，练习却要求交卷后立即出分，题目实际无法当堂完成；同时它也让学生每次练习都
要额外准备录音或拍照。

**涉及文件**

- 修改：`Art_assessment_backend/apps/exams/services/paper.py`
- 修改：`Art_assessment_backend/apps/exams/serializers.py`
- 修改：`Art_assessment_backend/apps/exams/tests/test_papers_assessments.py`
- 修改：`Art_assessment_backend/README.md`
- 修改：`Art_assessment_frontend/src/api/mock.ts`
- 修改：`Art_assessment_frontend/src/views/student/StudentKnowledgeView.vue`
- 修改：`Art_assessment_frontend/README.md`
- 修改：`CHANGELOG.md`

**更改内容**

1. `PRACTICE_COMPOSITION` 改为 6 单选 + 3 多选 + 1 判断，全部为客观题；删除
   `PRACTICE_UPLOAD_TYPE`、`PRACTICE_UPLOAD_FALLBACK` 和实践题抽取逻辑；
2. 题量仍为 10 题，`_practice_question_scores` 平均分配 100 分，每题 10 分，总分恰好 100；
3. `_practice_type_label` 补充「判断题」；`PracticeRandomSerializer` 文档字符串同步；
4. 测试改为断言 1 道判断题、不含 `audio_upload` / `image_upload`；
5. mock 模式与后端一致（6 单选 + 3 多选 + 1 判断、固定 100 分），知识点页提示文案同步。

**影响**

- 新生成的随机练习不再出现实践题，交卷后全部客观题即时判分，不产生教师评分任务；
- 题库判断题充足：每个年级音乐 16~19 道、美术 16 道，均满足抽 1 道的需要；
- 历史练习卷保持原样，不受影响。

**验证**

- 真实题库回滚试跑（音乐、美术各一套）：10 题、6 单选 + 3 多选 + 1 判断、每题 10 分、
  满分 100、题干无重复；
- `python -m pytest -q`：通过；
- `npm run typecheck`：通过；
- `npm run build`：通过（12.27s）。

---

### 2026-11-04 09:58 · FEAT-035 试卷提交审核弹窗改为紧凑样式

**修改时间**：2026-11-04 09:58

**类型**：前端 / 交互

**问题**

组卷完成后点「提交审核」，弹出的说明输入框沿用 Element Plus 默认宽度（420px）
和较大内边距，在表格页面里显得又宽又长。

**涉及文件**

- 修改：`Art_assessment_frontend/src/views/PapersView.vue`
- 修改：`CHANGELOG.md`

**更改内容**

1. 提交审核弹窗改用页面已有的 `compact-confirm` 紧凑样式（320px 宽、更小内边距）；
2. 提示文案缩短为「可填写提交说明（可选）」。

**验证**

- `npm run typecheck`：通过；
- `npm run build`：通过（8.74s）。

---

### 2026-11-04 09:58 · FEAT-034 人工评分默认终评，避免打完分后成绩不发布

**修改时间**：2026-11-04 09:58

**类型**：前端 / 评分

**问题**

教师评分页的「完成终评并生成最终成绩」默认不勾选。教师给实践题打完分点「保存评分」时，
后端只保存评分草稿，答卷停留在「评分中」，不生成成绩，学生端「我的成绩」和学习报告
都看不到这次测评。演示数据中 attempts 53、59 就是这种状态（实践题已打 25 分 / 11.8 分，
但 `grading_status` 仍为 grading，且没有 Score 记录）。

**涉及文件**

- 修改：`Art_assessment_frontend/src/views/GradingView.vue`
- 修改：`CHANGELOG.md`

**更改内容**

1. 打开评分任务时「完成终评并生成最终成绩」默认勾选；需要保留草稿时手动取消；
2. 按钮文案随勾选状态变化：「保存并发布成绩」/「保存草稿」，明确保存结果的差异；
3. 保存后的提示区分两种情况：已发布时提示总分并说明学生可在「我的成绩」查看；
   存草稿时提示学生暂时看不到成绩。

**待处理数据**

演示库中 attempts 53、59 仍为未终评状态，未自动改动；在「学生评分」中打开对应答卷、
确认分数后点「保存并发布成绩」即可出分。

**验证**

- `npm run typecheck`：通过；
- `npm run build`：通过（8.74s）。

---

### 2026-11-04 09:58 · FEAT-033 随机练习按题干去重，并排除歧义题

**修改时间**：2026-11-04 09:58

**类型**：后端 / 随机练习 / 题库

**问题**

同一套随机练习里会出现重复题，例如「以下哪些乐器属于键盘乐器？」连续出现两次；
另外「以下哪个术语与 X 直接相关？」这类题的干扰项与正确答案同属一个类别，
四个选项都成立，答案有歧义。统计发现已审核题库 5724 道题中只有 3899 个不同题干，
存在 783 组重复题干，其中「直接相关」共 148 道。

**涉及文件**

- 修改：`Art_assessment_backend/apps/exams/services/paper.py`
- 修改：`Art_assessment_backend/apps/exams/management/commands/seed_question_bank.py`
- 修改：`Art_assessment_backend/apps/exams/tests/test_papers_assessments.py`
- 修改：`CHANGELOG.md`

**更改内容**

1. 随机练习抽取题目时按题干去重（`_distinct_question_ids`），同一套题不会出现相同题干；
2. 随机练习不再抽取题干含「直接相关」的歧义题；
3. 修正题库生成模板：音乐/美术「术语与类别」题改为「以下哪个术语属于“X”？」，干扰项
   只从其他类别的术语中选取（此前从全部术语中随机取，导致多个选项都对）；
4. 题库生成模板的修正在下次执行 `seed_question_bank` 时生效，不会自动改动已有题目。

**验证**

- 实测演示学生（7 年级音乐）：抽取 10 题，题干唯一 10 个，无「直接相关」题；
- `python -m pytest -q`：全部通过（含新增的题干去重、满分 100 断言）。

---

### 2026-11-04 09:58 · FEAT-032 学生随机练习固定 100 分

**修改时间**：2026-11-04 09:58

**类型**：后端 / 随机练习

**问题**

随机练习的试卷总分取各题原始分值之和（演示数据为 31 分），与正式测评 100 分不一致，
成绩趋势、报告统计和满分展示都需要额外换算。

**涉及文件**

- 修改：`Art_assessment_backend/apps/exams/services/paper.py`
- 修改：`Art_assessment_backend/apps/exams/tests/test_papers_assessments.py`
- 修改：`CHANGELOG.md`

**更改内容**

1. 新增 `PRACTICE_TOTAL_SCORE = 100` 与 `_practice_question_scores`：按题数平均分配 100 分，
   余数计入最后一题，保证合计正好 100；
2. 随机练习建卷时每道题使用分配后的分值（10 道题即每题 10 分），试卷、测评、答卷满分均为 100；
3. 新增测试断言：随机练习满分 100、每题 10 分。

**影响**

- 之后生成的随机练习统一 100 分；历史练习答卷仍保留原分值，不回填。

**验证**

- `python -m pytest -q`：全部通过；
- 实测抽取结果：10 题 × 10 分 = 100 分。

---

### 2026-11-04 09:46 · FEAT-031 成绩趋势拆成「正式测评」「平时练习」两张图

**修改时间**：2026-11-04 09:46

**类型**：前端 / 成绩展示

**问题**

FEAT-030 虽已把两类成绩分开成两条曲线，但仍画在同一张图里，共用 0–100% 的
得分率纵轴；用户要求直接分成两张图，各自按自己的满分显示。

**涉及文件**

- 修改：`Art_assessment_frontend/src/views/student/StudentResultsView.vue`
- 修改：`Art_assessment_frontend/src/utils/echarts.ts`
- 修改：`CHANGELOG.md`

**更改内容**

1. 删除合并图，改为两张独立卡片：「正式测评趋势」与「平时练习趋势」；
2. 每张图使用各自满分作为纵轴上限（正式 0–100 分，练习 0–当前练习卷满分，如 0–31 分），
   直接显示原始得分，不再换算得分率；
3. 图头部显示「满分 X 分 · 共 N 次」，无数据的类别整块隐藏；
4. 类型筛选（全部 / 正式测评 / 平时练习）继续保留，切换时按需渲染对应图表；
5. 图表实例按 DOM 元素重新绑定，筛选切换导致图表卸载重建时不会显示空白；
6. 不再需要图例，撤回 FEAT-030 中为合并图注册的 `LegendComponent`。

**影响**

- 两类成绩彻底分开，练习卷 31 分与正式卷 100 分不再互相拉低视觉比例；
- 成绩卡片仍保留「得分率」用于跨类别横向比较。

**验证**

- `npm run typecheck`：通过；
- `npm run build`：通过（11.70s）。

---

### 2026-11-03 16:31 · FEAT-030 我的成绩区分正式测评与平时练习，趋势改按得分率

**修改时间**：2026-11-03 16:31

**类型**：前端 / 成绩展示

**问题**

「我的成绩」把正式测评和平时练习画在同一条趋势曲线里，但两者满分不同
（正式卷 100 分，练习卷按题量计分，例如 31 分），把 4/31 和 90/100 放在一起，
曲线忽高忽低，且旧实现按 `createdAt` 倒序作图，趋势方向也是反的。

**涉及文件**

- 修改：`Art_assessment_backend/apps/exams/presenters.py`
- 修改：`Art_assessment_frontend/src/types/index.ts`
- 修改：`Art_assessment_frontend/src/views/student/StudentResultsView.vue`
- 修改：`Art_assessment_frontend/src/utils/echarts.ts`
- 修改：`Art_assessment_frontend/src/styles/index.css`
- 修改：`CHANGELOG.md`

**更改内容**

1. 成绩列表接口 `score_item` 增加 `maxScore` 字段，前端成绩类型同步；
2. 「我的成绩」筛选栏新增「全部 / 正式测评 / 平时练习」类型筛选；
3. 成绩趋势改为按得分率（`totalScore / maxScore`）绘制，y 轴固定 0–100%，
   正式测评（蓝色）与平时练习（紫色）各一条曲线，可按类型单独查看；
4. 曲线数据按时间正序排列，tooltip 显示日期、测评名称、得分 / 满分与得分率；
5. 成绩卡片按「正式测评」「平时练习」分组展示，并显示「得分 / 满分」和得分率；
6. 成绩详情弹窗补充「总分」行（得分 / 满分）；
7. ECharts 注册 `LegendComponent`，使图例可以正常显示。

**影响**

- 满分不同的测评现在可以横向比较，趋势曲线不再被练习卷拉低；
- 练习成绩仍保留在「我的成绩」中，只是与正式测评分开展示；
- 正式测评仍是等级、证书的唯一来源（与 FEAT-026 后的证书规则一致）。

**验证**

- `python -m pytest -q`：全部通过；
- 实查演示成绩：正式 100/100、75/100、90/100，练习 4/31，`maxScore` 均正确返回；
- `npm run typecheck`：通过；
- `npm run build`：通过（12.41s）。

---

### 2026-11-03 15:46 · FEAT-029 作答页右侧答题卡，可随时切题

**修改时间**：2026-11-03 15:46

**类型**：前端 / 交互

**问题**

作答页原先只在题目上方有一条横向题号条，题量多时需要横向滑动，且滚动到题目
下半部分后无法快速确认还有哪些题未答，也不能直接跳到任意一题。

**涉及文件**

- 修改：`Art_assessment_frontend/src/views/student/StudentAttemptView.vue`
- 修改：`Art_assessment_frontend/src/styles/index.css`
- 修改：`CHANGELOG.md`

**更改内容**

1. 作答页改为左右两栏：左侧题目卡片与操作栏，右侧固定「答题卡」；
2. 答题卡按顺序列出全部题号，点击任意题号即可切换到该题，并回到页面顶部从题面开始阅读；
3. 题号区分三种状态：当前题（实心主色）、已答（浅蓝底）、未答（白底），
   悬停显示「第 N 题（已答/未答）」，答题卡顶部实时显示「已答 x/y」；
4. 移除原先位于题目上方的横向题号条，避免重复；
5. 窄屏（≤900px）时答题卡自动变为题目上方的横向可滑动题号条，不再挤占作答宽度；
6. 打开作答页时若答卷已被后端自动交卷（`status !== 'in_progress'`），
   直接进入试卷阅览页，不再停留在无法作答的页面；
7. 倒计时基准改为服务器时间：进入页面时用接口返回的 `serverTime` 计算与本地时钟的差值，
   之后按服务器时间推进，避免本机时间不准导致提前或延后交卷。

**保持不变**

倒计时结束自动交卷逻辑此前已实现（到达 0 秒调用 `submit(true)`，后端另有
`auto_submit_expired` 兜底），本次未改动交卷流程，只修正倒计时的计时基准。

**验证**

- `npm run typecheck`：通过；
- `npm run build`：通过（8.91s）。

---

### 2026-11-03 14:40 · FEAT-028 学生年级与班级年级强制一致

**修改时间**：2026-11-03 14:40

**类型**：后端 / 基础逻辑

**问题**

学生入班、转班、管理员建号或改班时，只校验学校，不校验年级，可能把七年级
学生分到八年级班，后续组卷、测评和统计都会出现年级错位。

**涉及文件**

- 修改：`Art_assessment_backend/apps/classes/services.py`
- 修改：`Art_assessment_backend/apps/accounts/services/accounts.py`
- 修改：`CHANGELOG.md`

**更改内容**

1. 学生入班、转班申请及审核通过时，校验学生年级与目标班级年级一致；
2. 学校管理员创建学生并指定班级时，年级必须与班级一致，未传时自动取班级年级；
3. 管理员修改学生所属班级时，同样校验年级。

**验证**

- `python -m pytest -q`：全部通过。

---

### 2026-11-03 14:40 · FEAT-026 教学权限改为按「班级 + 学科」精确匹配

**修改时间**：2026-11-03 14:40

**类型**：后端 / 权限 / 基础逻辑

**问题**

系统原先分别用 `class_ids`（任教班级 ∪ 班主任班级）和 `teacher_subjects`
（任教学科 ∪ 档案学科）做权限判断，再把两个集合交叉使用。班主任因此可以在
自己管理、但并未任教的班级里，以档案学科身份组卷、发布测评、评分、查看成绩
和生成证书。例如：陈志远是七年级（1）班班主任、档案学科音乐，但该班音乐老师
是李静，系统仍允许他操作该班音乐数据。

**涉及文件**

- 修改：`Art_assessment_backend/apps/exams/scope.py`
- 修改：`Art_assessment_backend/apps/exams/services/paper.py`
- 修改：`Art_assessment_backend/apps/exams/services/assessment.py`
- 修改：`Art_assessment_backend/apps/exams/services/grading.py`
- 修改：`Art_assessment_backend/apps/exams/services/score.py`
- 修改：`Art_assessment_backend/apps/exams/services/certificate.py`
- 修改：`Art_assessment_backend/apps/exams/services/statistics.py`
- 修改：`Art_assessment_backend/apps/exams/services/growth.py`
- 修改：`Art_assessment_backend/apps/files/views.py`
- 修改：`Art_assessment_backend/apps/classes/models.py`
- 新增：`Art_assessment_backend/apps/classes/migrations/0004_class_teacher_unique_active_only.py`
- 新增：`Art_assessment_backend/apps/exams/tests/test_teacher_pair_scope.py`
- 修改：`Art_assessment_backend/conftest.py`、相关测试
- 修改：`CHANGELOG.md`

**更改内容**

1. `DataScope` 新增 `teaching_pairs`（未删除的 `ClassTeacher` 班级+学科组合）、
   `teaches_subject_in_class`、`teaching_subjects_for_class`、`ensure_teacher_pair`
   和 `teacher_pair_q`；
2. 组卷、发布测评、评分任务、重新判分、成绩查询/补录/导入、证书生成/列表、
   统计、成长报告、作品评分全部改为按具体任教组合校验；班主任身份只保留班级
   管理权限，不再自动获得该班某一学科的教学权限；
3. 教师组卷与发布测评增加年级校验：试卷年级必须等于目标班级年级，目标年级
   必须包含试卷年级；
4. 证书只允许正式测评（`formal`）生成，练习测评不再产生证书；
5. `ClassTeacher` 唯一约束改为仅约束未删除记录，解除任课后可以重新安排老师；
6. 新增权限回归测试，覆盖班主任越权、跨班发布、跨年级发布、重复任课关系、
   练习卷证书等场景。

**影响**

- 班主任若同时是某班某学科科任老师，不受影响；
- 仅担任班主任、未在该班任教的老师，将无法再操作该班教学数据；
- 已存在的历史越权试卷/测评不会被自动删除，仍可由创建人查看。

**验证**

- `python -m pytest -q`：全部通过（含新增 7 条权限测试）；
- 演示数据只读核对：陈志远只保留 `(八年级2班, 音乐)` 任教组合，无法访问
  李静在七年级（1）班的音乐测评（测评 79）；
- `python manage.py migrate`：`classes.0004` 应用成功；
- 事务回滚验证：软删除原音乐老师后可新增同班同学科老师。

---

### 2026-11-03 14:40 · FEAT-027 班级详情展示真实学科老师，区分班主任档案学科

**修改时间**：2026-11-03 14:40

**类型**：后端 / 前端 / 班级信息

**问题**

班级详情调用了 `headTeacherAccount`、`headTeacherSubject`、`headTeacherPhone`，
但后端没有返回这些字段；同时页面只显示班主任，导致用户把「班主任档案学科」
误认为「本班该学科老师」。例如七年级（1）班班主任陈志远档案学科是音乐，但该班
音乐老师实际是李静。

**涉及文件**

- 修改：`Art_assessment_backend/apps/classes/services.py`
- 修改：`Art_assessment_frontend/src/types/index.ts`
- 修改：`Art_assessment_frontend/src/views/ClassesView.vue`
- 修改：`CHANGELOG.md`

**更改内容**

1. `build_class_item` 返回班主任账号、档案学科、联系电话；
2. 班级详情展示 `subjectTeachers`，格式为「音乐：李静；美术：赵敏」；
3. 「任教学科」标签改为「班主任档案学科」，避免与班级学科老师混淆；
4. 打开班级详情时重新请求 `/classes/{id}`，确保拿到完整字段。

**验证**

- 演示数据核对：七年级（1）班显示班主任陈志远（档案音乐）、本班音乐李静、
  美术赵敏；
- `npm run typecheck`、`npm run build`：通过。

---

### 2026-11-03 14:29 · FEAT-025 学生评分列表交卷时间改为正常日期格式

**修改时间**：2026-11-03 14:29

**类型**：前端 / 学生评分

**现象**

学生评分列表的「交卷时间」直接显示后端 ISO 字符串（如
`2026-10-28T13:59:00+08:00`），其中的 `T` 和时区后缀看起来像乱码。

**涉及文件**

- 修改：`Art_assessment_frontend/src/views/GradingView.vue`
- 修改：`CHANGELOG.md`

**更改内容**

1. 新增 `formatDateTime`，把交卷时间统一显示为 `YYYY-MM-DD HH:mm`；
2. 没有交卷时间时显示「—」，不再出现 `null` 或原始 ISO 字符串。

**影响**

- 仅影响列表展示，接口数据和评分流程不变。

**验证**

- 无头 Edge 实测：两行分别显示 `2026-10-28 13:59`、`2026-11-03 10:15`；
- `npm run typecheck`、`npm run build`：通过。

---

### 2026-11-03 14:28 · FEAT-024 教师评分改为按档加减，不能直接输入得分

**修改时间**：2026-11-03 14:28

**类型**：前端 / 学生评分 / 课外作品评分

**现象**

教师评分时可以直接在数字框里键入任意分数，容易误输或跳过逐档评分。

**涉及文件**

- 新增：`Art_assessment_frontend/src/components/ScoreStepper.vue`
- 修改：`Art_assessment_frontend/src/views/GradingView.vue`
- 修改：`Art_assessment_frontend/src/views/TeacherStudentsView.vue`
- 修改：`Art_assessment_frontend/src/styles/index.css`
- 修改：`CHANGELOG.md`

**更改内容**

1. 新增只读分数步进组件 `ScoreStepper`：只显示当前分数和「−」「+」按钮，
   没有可输入的输入框，不能直接键入分数；
2. 单击一次加减一档；按住按钮约 0.4 秒后开始连续加减，方便把分数调到目标值；
3. 「学生评分」中每题得分按 0.5 分一档加减，范围限制在 0 到该题满分；
4. 「学生管理 → 课外学习材料 → 作品评分」按 1 分一档加减，范围 0–100；
   未评分的作品默认从 0 分开始，不再预填 90 分；
5. 到达 0 分或满分时对应按钮自动禁用。

**影响**

- 教师只能通过加减按钮评分，不能直接输入分数；
- 评分保存、终评、总分计算和接口参数不变；
- 管理员成绩补录、证书成绩修改等非教师评分入口不受影响。

**验证**

- 无头 Edge 1440×900：打开 25 分实践题，初始 0 分；
  单击「+」后变为 0.5，按住「+」约 0.9 秒后变为 3.5；
- 评分卡片内输入框数量为 0，确认无法直接键入；
- 减分至 0 后「−」按钮禁用，加到满分后「+」按钮禁用；
- `npm run typecheck`、`npm run build`：通过。

---

### 2026-11-03 14:18 · FEAT-023 个人信息与右上角头像支持双击查看大图

**修改时间**：2026-11-03 14:18

**类型**：前端 / 个人中心 / 顶栏

**现象**

个人信息页和右上角用户信息区只能看到小尺寸头像，无法放大查看细节；
用户希望双击头像即可查看原图。

**涉及文件**

- 修改：`Art_assessment_frontend/src/views/ProfileView.vue`
- 修改：`Art_assessment_frontend/src/layouts/AppShell.vue`
- 修改：`Art_assessment_frontend/src/styles/index.css`
- 修改：`CHANGELOG.md`

**更改内容**

1. 右上角用户头像增加双击事件，使用 Element Plus `el-image-viewer` 打开原图，
   点击遮罩或右上角关闭按钮退出；
2. 个人信息页的主头像和基本资料中的头像预览都支持双击查看大图；
3. 有头像时鼠标变为放大镜样式，并显示「双击查看头像」提示；
   没有头像、仅显示姓名首字时不响应双击；
4. 查看器通过 `teleported` 挂到 body，不会被顶栏或页面容器裁剪。

**影响**

- 双击头像即可查看原始尺寸图片，支持滚轮缩放和拖拽；
- 其他点击行为、头像上传/移除/保存逻辑不变；
- 未设置头像的账号保持原样。

**验证**

- 无头 Edge 1440×900：临时给教师账号设置头像后，双击右上角头像，
  `.el-image-viewer__wrapper` 出现且图片地址正确；点击关闭后查看器销毁；
  双击个人信息主头像同样可打开；
- `npm run typecheck`：通过；
- `npm run build`：通过（仅保留原有大 chunk 提示）；
- 测试用临时头像已恢复为未设置状态。

---

### 2026-11-03 14:17 · FEAT-022 证书等级固定为优秀，修改证书不再允许选择其他等级

**修改时间**：2026-11-03 14:17

**类型**：后端 / 前端 / 证书

**现象**

证书只发给得分率达到 90% 的成绩，但「修改证书信息」仍可把等级改成良好、
合格或待提升；数据库中还存在一份 90 分但等级为「良好」的旧证书。

**涉及文件**

- 修改：`Art_assessment_backend/apps/exams/serializers.py`
- 修改：`Art_assessment_backend/apps/exams/services/certificate.py`
- 修改：`Art_assessment_backend/apps/exams/tests/test_certificates_growth.py`
- 修改：`Art_assessment_frontend/src/views/CertificatesView.vue`
- 修改：`Art_assessment_frontend/src/api/mock.ts`
- 修改：`CHANGELOG.md`

**更改内容**

1. 证书更新序列化器只接受 `excellent`，提交 `good / pass / fail` 返回 400；
2. 证书更新服务无论修改哪个字段，都把等级统一写为「优秀」；
3. 自动发放证书时等级固定为「优秀」，不再依赖成绩记录上的旧等级值；
4. 前端修改证书弹窗移除等级下拉框，改为只读「优秀」，并提示
   「证书只发给得分率达到 90% 的学生，等级固定为优秀」；保存时固定提交 `excellent`；
5. mock 模式同步：修改证书或生成证书时等级固定为「优秀」；
6. 将数据库中唯一一份旧证书 `YS2026-MUSIC-000001`（90 分 / 良好）更新为优秀，
   并重新生成 PDF；核对后证书等级全部为 `excellent`。

**影响**

- 证书等级只有一个取值：优秀；
- 通过接口提交其他等级会被拒绝，已有证书在任意修改后也会归一到优秀；
- 证书编号、成绩、发证日期、状态、下载等功能不变。

**验证**

- `python -m pytest apps/exams/tests/test_certificates_growth.py -q`：20 项通过；
- `python -m pytest -q`：307 项全部通过；
- 新增测试覆盖：提交 `level=good` 返回 400；修改成绩时旧「良好」证书自动变为「优秀」；
- `npm run typecheck`、`npm run build`：通过；
- 数据库核对：证书等级分组结果为 `excellent: 1`。

---

### 2026-11-03 14:06 · FEAT-021 试题管理表格列宽修正，已驳回题操作列不再换行遮挡

**修改时间**：2026-11-03 14:06

**类型**：前端 / 表格布局

**现象**

教师端「试题管理」筛选「已驳回」后只剩编号 41 一道判断题，但该行显示异常：
「状态」列的「已驳回」标签被右侧固定的「收藏」列遮住一半，「操作」列的
「删除」按钮被挤到第二行，整行高度和其他行不一致。

**原因**

- 表格可视宽度为 1086px，原各列宽度合计 1140px，产生 54px 横向溢出；
  「收藏」「操作」固定在右侧，覆盖了最后一个非固定列「状态」；
- 「操作」列宽 240px，单元格左右内边距共 24px，可用 216px；四个链接按钮
  实际需要约 225px，因此「删除」换行。

**涉及文件**

- 修改：`Art_assessment_frontend/src/views/QuestionsView.vue`
- 修改：`CHANGELOG.md`

**更改内容**

1. 压缩非关键列：编号 90 → 80、题干最小宽度 280 → 240、题型 110 → 100、
   年级 80 → 70、资源 70 → 60，总宽度降至 1080px，小于表格可视宽度 1086px；
2. 「操作」列由 240px 加宽到 260px，四个按钮可在同一行显示；
3. 列顺序保持「状态 → 收藏 → 操作」，修复后「状态」不再被固定列覆盖。

**关于编号 41 的题目内容**

该题是正常的判断题：题干「3/4拍属于复拍子」，正确答案「错误」，所属课程
「七年级音乐（人教版）」、章节「拓展类」，由陈志远创建，审核人孙倩驳回，
驳回原因「题干表述不严谨，请修改后重新提交」。题目本身没有格式损坏；
与种子题相比，题干末尾少了句号，属于录入时的文字格式差异，不影响判题。
本次只修表格布局，未修改题目内容和审核状态。

**影响**

- 教师端试题管理表格在 1440px 视口下不再横向溢出；
- 已驳回题目的「编辑 / 提交审核 / 资源 / 删除」四个操作保持一行；
- 「状态」标签完整显示，行高恢复为 50px；
- 其他页面、接口和题目数据不变。

**验证**

- 无头 Edge 1440×900 实测：表格 `scrollWidth` 与容器宽度同为 1086px，
  无横向溢出；操作单元格高度 50px，四个按钮同一行；状态列右边界 1033px，
  收藏列左边界 1033px，无重叠；
- `npm run typecheck`：通过；
- `npm run build`：通过（仅保留原有大 chunk 提示）。

---

### 2026-11-03 14:00 · FEAT-020 证书规则统一为 90%，清理旧 60 分规则与本地产物缓存

**修改时间**：2026-11-03 14:00

**类型**：后端 / 规则一致性 / 缓存清理 / 前端表格

**现象**

- 证书自动发放的现行代码已是「得分率 ≥ 90%」，但学情联动模块的说明文字与交卷
  逻辑中的注释仍写着「达到 60 分」，测试也只断言 ≥ 60%，与现行规则不一致；
- 前端 mock 数据中存在 88 分、80 分的证书样本，mock 生成证书时也未按 90% 过滤；
- 用户要求确认不再存在满分 60 的正式测评，并把旧的、无效的规则缓存全部清理，
  只保留最新的 90 分规则；
- 题库查询页的「操作」列未固定在右侧，横向滚动时会随内容移动。

**涉及文件**

- 修改：`Art_assessment_backend/apps/exams/services/achievement.py`
- 修改：`Art_assessment_backend/apps/exams/services/attempt.py`
- 修改：`Art_assessment_backend/apps/exams/tests/test_certificates_growth.py`
- 修改：`Art_assessment_frontend/src/api/mock.ts`
- 修改：`Art_assessment_frontend/src/views/TeacherQuestionBankView.vue`
- 修改：`Art_assessment_frontend/src/views/QuestionsView.vue`
- 清理：后端 `__pycache__/`、`.pytest_cache/`；前端 `node_modules/.vite/`、
  `tsconfig.tsbuildinfo`

**更改内容**

1. 统一证书规则为「成绩已评分 + 发布者为教师/校级/区级/市级/省级管理员 +
   得分率 `total_score / max_score >= 0.9`」；正式测评在出分后自动发放，
   随机练习不自动发放，人工生成可覆盖练习卷。
2. 修正 `achievement.py` 模块说明与 `attempt.py` 交卷注释中的 60 分旧口径，
   改为 90% 得分率。
3. 更新证书测试：
   - 自动发放断言改为 `cert.score / max_score >= 0.9`，并校验证书记录分数等于成绩总分；
   - `test_no_certificate_below_60` 重命名为 `test_no_certificate_below_90`，
     使用 53.99 / 60（89.98%）验证不发证；
   - 新增 `test_certificate_issued_at_90_percent`，使用 54 / 60（刚好 90%）验证发证。
4. 前端 mock 同步：证书样本改为 92 分 / 优秀，删除不符合规则的 80 分样本；
   mock 生成证书时只选取总分 ≥ 90 的成绩。
5. 试题管理页把「操作」列移到「收藏」列右侧，两列均固定在表格右侧；
   操作列成为最右列，不再被收藏列挡在中间。
6. 题库查询页「操作」列改为 `fixed="right"`、`align="center"`，宽度 90 → 100，
   横向滚动时固定在表格右侧。
7. 删除后端 Python 字节码缓存、pytest 缓存、前端 Vite 缓存与 TS 增量构建缓存，
   并执行 Django `cache.clear()`；评分规则 YAML 缓存按文件 mtime 失效，无需手工保留。

**原因**

旧 60 分说明、注释、测试断言和 mock 样本会让后续维护者误判证书条件；清理后
代码、测试、演示数据与页面文案统一为 90% 规则。删除编译/构建缓存可避免旧规则
残留影响本地调试。

**影响**

- 证书发放条件只有一套：正式测评得分率达到 90% 自动发放，人工生成同样按 90% 校验；
- 数据库中不存在满分 60 的正式测评：试卷 `total_score` 仅 31 分（练习卷 9 张）
  与 100 分（43 张，其中正式卷 29 张）；
- 试题管理页操作列位于最右侧，收藏列在其左侧，两列都不会随横向滚动移动；
- 题库查询页操作列固定在右侧，不再被横向滚动带走；
- 业务接口、证书编号格式、证书状态流转均不变。

**验证**

- `python -m pytest -q`：305 项全部通过；
- `npm run typecheck`：通过；
- `npm run build`：通过（仅保留原有大 chunk 提示）；
- 数据库核对：正式试卷 29 张 `total_score` 全部为 100；18 场正式测评
  `max_score` 全部为 100；不存在满分 60 的正式测评；
- 全项目检索 `证书.*60 / 60.*证书 / 得分率 60`：业务代码、测试、前端均已无匹配。

---

### 2026-11-03 13:48 · FEAT-019 详情弹窗改为居中并支持全屏，学生侧栏收起同步缩小

**修改时间**：2026-11-03 13:48

**类型**：前端 / 交互布局

**现象**

- 查看错题、试卷、试题、成绩、证书、班级信息等详情时，内容从页面右侧以抽屉形式弹出；
- 用户不希望详情从右边弹出，希望从屏幕中间弹出，并且可以切换全屏查看；
- 学生端点击「收起导航」后只隐藏了菜单文字，侧栏仍保持 226px 宽度，没有真正缩小。

**涉及文件**

- 新增：`Art_assessment_frontend/src/components/DetailDialog.vue`
- 修改：`Art_assessment_frontend/src/styles/index.css`
- 修改详情页：`CertificatesView.vue`、`ClassesView.vue`、`GradingView.vue`、
  `LogsView.vue`、`PaperReviewView.vue`、`PapersView.vue`、`ScoresView.vue`、
  `TeacherQuestionBankView.vue`、`TeacherStudentsView.vue`、
  `student/StudentKnowledgeView.vue`、`student/StudentResultsView.vue`、
  `student/WrongQuestionsView.vue`

**更改内容**

1. 新增 `DetailDialog` 组件，基于 `el-dialog` 居中显示，默认宽度按原抽屉宽度
   （460～760px）；标题栏右侧提供「全屏查看 / 退出全屏」按钮。
2. 标题栏保留原有标题，内容区超出 88vh 时内部滚动；全屏时铺满整个视口，
   关闭后自动退出全屏。
3. 将 12 个页面中的 19 个右侧抽屉替换为居中弹窗，覆盖错题详情、成绩与解析、
   试卷详情、试题详情、人工评分、证书详情、班级/学生信息、审核记录、
   题库选题、学习材料等；`PapersView` 选题弹窗的底部按钮通过 footer 插槽保留。
4. 通知中心仍保留右侧抽屉，因为它是通知面板而非单据/详情查看。
5. 修正学生端收起导航的宽度：新增
   `.app-shell--student.app-shell--collapsed .sidebar { width: 82px; }`，
   并把折叠状态的 `--sidebar-width` 同步改为 82px；此前学生的 226px 规则
   覆盖了通用折叠规则，导致只隐藏文字、侧栏不缩窄。

**原因**

右侧抽屉会遮挡页面主体，且宽表格、逐题解析在窄抽屉里需要频繁滚动；
居中弹窗更符合“查看详情”的阅读习惯，全屏按钮可以应对题目和解析较多的场景。
学生侧栏宽度未同步缩小属于 CSS 优先级问题，需要在学生专用样式之后覆盖。

**影响**

- 所有单据/详情类内容从屏幕中间弹出，不再从右侧滑出；
- 每个详情弹窗都可以一键全屏、再一键还原；
- 学生端桌面宽度下，侧栏收起前后宽度为 226px → 82px，主内容区从
  1199px 扩展到 1343px（1440px 视口实测）；
- 弹窗内容超长时在弹窗内部滚动，不会撑出视口；
- 页面路由、接口和业务数据不变。

**验证**

- `npm run typecheck`：通过；
- `npm run build`：通过（仅保留原有的大 chunk 提示）；
- 无头 Edge 实测 1440×900：错题详情弹窗水平居中，高度 792px（88vh），
  内容区可滚动，点击全屏后尺寸为 1440×900；
- 无头 Edge 实测学生首页：侧栏收起前宽 226px、主区 1199px，
  收起后宽 82px、主区 1343px，菜单文字隐藏；
- 检索确认仅 `NotificationCenter.vue` 保留 `el-drawer`。

---

### 2026-11-03 13:34 · FEAT-018 题干标签清理，只保留纯题干

**修改时间**：2026-11-03 13:34

**类型**：后端 / 题库数据 / 文案

**现象**

- 题库、试卷、答卷和错题本中的题干带有“【单元练习】”“【音乐·七年级】”
  “[七年级音乐·劳动的歌]”“（变式 2）”“（拓展练习）”等生成标签，
  展示时干扰题目本身，用户要求只保留纯题干。

**涉及文件**

- 后端新增：`apps/qbank/stem_cleaner.py`、
  `apps/qbank/management/commands/clean_question_stems.py`
- 后端修改：`apps/exams/management/commands/seed_question_bank.py`、
  `apps/exams/management/commands/seed_grade_question_bank.py`、
  `apps/exams/management/commands/seed_curriculum_units.py`、
  `apps/exams/management/commands/classify_question_chapters.py`、
  `apps/accounts/management/commands/realify_demo_data.py`、`README.md`
- 测试新增：`apps/qbank/tests/test_stem_cleaner.py`

**更改内容**

1. 新增 `clean_stem()`：循环去掉题干开头的单元/年级/学科标签
   （`【单元练习】`、`【音乐·七年级】`、`【美术·八年级】`、
   `[七年级音乐·单元名]`）和结尾的“（变式 N）”“（拓展练习）”，
   压缩多余空白，函数幂等。
2. 新增 `python manage.py clean_question_stems` 命令，支持 `--dry-run`、
   `--subject`、`--grade`；同时清理题库 `Question.stem`、试卷快照
   `PaperQuestion.stem`、错题快照 `WrongQuestion.stem` 和答卷快照
   `Attempt.questions_snapshot` 中的题干，避免已发布试卷和已交答卷继续显示旧标签。
3. 三个组卷/题库生成命令不再写入标签：`seed_question_bank` 不再追加变式后缀，
   `seed_grade_question_bank` 不再加年级前缀，`seed_curriculum_units` 不再加单元前缀；
   `classify_question_chapters` 改用审核意见识别单元同步练习，避免清理后误分类。
4. `realify_demo_data` 的题干清理扩展到全部标签，而不只是 `【音乐】/【美术】` 前缀。
5. 新增题干清理单元测试，覆盖前缀、后缀、括号混用与幂等性。

**原因**

这些标签是早期批量生成题库时用于区分课程、年级和重复模板的临时标记，
不属于题目内容；展示在学生作答、试卷阅览、错题本和教师审核页面会造成干扰。

**影响**

- 现有题库及所有历史快照中的题干只保留题目正文；
- 重新执行 seed 命令不会再把标签写回题干；
- 清理后部分题干会变成相同文本（原“变式”题），但选项、答案和题目 ID 保持不变。

**验证**

- `python manage.py clean_question_stems --dry-run`：预览 3700 道待清理题目；
- `python manage.py clean_question_stems`：清理题目 3790 道、试卷快照 400 条、
  错题快照 21 条、答卷快照 15 份；
- 复查题库、试卷快照、错题快照和答卷快照：匹配
  `【单元练习】|【音乐·|【美术·|（变式 N）|（拓展练习）` 的记录为 0；
- `python -m pytest -q`：全部通过。

---

### 2026-11-03 13:29 · FEAT-017 快捷账号同班修正、试题管理列微调与真实测评闭环

**修改时间**：2026-11-03 13:29

**类型**：后端 / 前端 / 演示数据 / 业务流程

**现象**

- 登录页快捷账号中的“科任老师 · 音乐”使用 `teacher_music`，但该账号原本不在七年级（1）班；
- 试题管理列表右侧固定列仍会遮挡部分题干，操作列需要再向右让出一点空间；
- 需要在真实演示库中按流程新增一场测评，由教师评分后得到 90 分并自动生成证书。

**涉及文件**

- 后端：`apps/accounts/management/commands/seed_teacher_roster.py`、
  `apps/accounts/management/commands/realify_demo_data.py`、`README.md`
- 前端：`src/views/LoginView.vue`、`src/views/QuestionsView.vue`
- 演示库记录：试卷 106、测评 79、答卷 54、成绩 40、证书 12

**更改内容**

1. 将七年级（1）班的音乐任课教师调整为 `teacher_music`（李静），
   `teacher`（陈志远）继续担任该班班主任；`seed_teacher_roster` 的 `ROSTER`
   同步改为 `teacher` 班主任、`teacher_music` 音乐、`teacher_art` 美术。
   登录页四个快捷身份现在全部来自七年级（1）班，备注改为“七（1）班班主任 /
   七（1）班音乐老师 / 七（1）班美术老师”。
2. 试题管理右侧固定列由“操作 250 + 收藏 100”收窄为“操作 240 + 收藏 90”，
   固定区域左边界向右移动约 20px，进一步减少对题干和状态列的遮挡。
3. 通过真实接口完成一条完整业务链路：
   - `teacher_music` 手工组卷《七年级音乐综合能力测评（2026年11月）》，
     9 道单选各 10 分、1 道音频实践题 10 分，满分 100；
   - 提交题库管理员审核并批准；
   - 发布到七年级（1）班，截止时间为 3 天后，答案公布方式为 `after_submit`；
   - 学生 `student`（王浩然）作答，上传 5 秒 WAV 演唱音频；
   - 客观题答对 8 题得 80 分，教师对实践题评分 10 分并填写评语；
   - 终评后总分 90 分，自动生成证书 `YS2026-MUSIC-000001`，学情报告可查询，
     学生交卷后可阅览试卷并看到答案与解析。

**原因**

快捷账号需要与学生同班才能直接演示“本班老师发布本班测评”；右侧固定列继续收窄可
改善题库列表可读性；同时需要用真实业务数据验证 90 分证书链路。

**影响**

- `teacher_music` 现在同时任教七年级（1）班、七年级（3）班和六年级（1）班；
- 七年级（1）班班主任账号不再显示“音乐老师”身份，音乐身份由 `teacher_music` 承担；
- 题库列表右侧固定区域整体右移，收藏列仍独立固定在最右侧；
- 演示库新增一张已完成的音乐正式测评及对应成绩、证书、学情报告。

**验证**

- `python -m pytest -q`：301 项全部通过；
- `npm run typecheck`：通过；
- `npm run build`：通过（仅保留原有 chunk 体积提示）；
- 接口验证：测评 79 的发布教师为李静，学生端可见截止时间；
  答卷 54 客观题 80 分、实践题 10 分、总分 90 分；
  证书 12 状态 `ready`，PDF 下载返回 `%PDF` 文件头；
  `GET /api/v1/students/11/learning-report` 返回学情报告。

---

### 2026-11-03 10:14 · FEAT-016 班级数据隔离、试卷重复发布与交卷后阅览

**修改时间**：2026-11-03 10:14

**类型**：后端 / 前端 / 权限 / 业务流程

**现象**

- 教师端需要严格做到“对应哪个班的老师只能看到哪个班的信息”；
- 学生管理中的“导出身份材料”功能需要删除；
- 试题管理操作列的收藏按钮位于最左侧，固定列遮挡试题内容；
- 班级管理缺少“当前用户在本班的身份”展示；
- 已发布过的试卷无法再次用于发布新测评；
- 学生测评列表看不到发布老师和测评截止时间；
- 学生交卷后无法阅卷，答案是否可见未与老师设置的公布时间联动；
- 需要完整验证同班“组卷 → 审核 → 发布 → 作答 → 评分 → 证书 → 学情报告”流程。

**涉及文件**

- 后端：`apps/classes/services.py`、`apps/classes/serializers.py`、
  `apps/classes/views.py`、`apps/exams/services/assessment.py`、
  `apps/exams/services/attempt.py`、`apps/exams/views/attempts.py`、
  `apps/exams/urls.py`；
- 后端测试：`apps/exams/tests/test_papers_assessments.py`、
  `apps/exams/tests/test_scores_statistics.py`、
  `apps/exams/tests/test_same_class_flow.py`（新增）；
- 前端：`src/views/TeacherStudentsView.vue`、`src/views/QuestionsView.vue`、
  `src/views/ClassesView.vue`、`src/views/AssessmentsView.vue`、
  `src/views/student/StudentAssessmentsView.vue`、
  `src/views/student/StudentAttemptView.vue`、
  `src/views/student/StudentAttemptReviewView.vue`（新增）、
  `src/router/index.ts`、`src/api/index.ts`、`src/api/mock.ts`、
  `src/types/index.ts`、`src/styles/index.css`；
- `CHANGELOG.md`。

**更改内容**

1. 班级接口增加 `myIdentity`：班主任、音乐老师、美术老师可组合显示
   （如“班主任 · 音乐老师”），学生显示“学生”，管理员显示对应管理角色；
   班级管理列表和班级信息抽屉均展示“我的身份”。
2. 复核教师数据范围：班级列表、学生账号、学生详情、测评、试卷、成绩、
   证书、评分任务、学情报告、课外作品均按教师任教班级和任教学科过滤；
   新增测试验证其他班教师看不到本班学生、班级和账号详情。
3. 删除教师端学生管理的“身份材料”下拉项和“下载身份材料”按钮，
   保留成绩导出与学生账号清单导出。
4. 试题管理将收藏拆为独立列并固定在表格最右侧，操作列宽度由 300 收窄到 250，
   减少对题干内容的遮挡。
5. 测评发布允许重复使用已发布过的试卷：`publish_assessment` 仅拒绝已归档试卷，
   已发布试卷可再次发布；发布弹窗同时加载 `ready` 与 `published` 且审核通过的试卷，
   并标注“已发布过”。
6. 学生测评卡片展示发布老师姓名和测评截止时间；已交卷的测评提供“查看已交试卷”入口。
7. 新增 `GET /api/v1/attempts/{id}/review`：提交后可查看逐题作答、得分和教师评语；
   `correctAnswer`、`analysis`、正误标记按 `showAnswerMode` 控制：
   `never` 始终不展示，`after_submit` 交卷后展示，`after_end` 到截止时间后展示；
   未提交的答卷返回 409。
8. 交卷后统一跳转新的试卷阅览页 `/student/attempt/{id}/review`；
   待教师评分的答卷也能立即阅卷，总分在终评后公布。
9. 新增同班全流程测试，覆盖手工组卷、提交审核、题库管理员审核通过、
   教师发布、学生收到并作答、教师终评实践题、成绩发布（60/60）、
   自动生成证书、生成学情报告。

**影响**

- 教师端数据严格限制在本人任教班级与学科内；
- 同一张已审核试卷可反复发布，无需复制；
- 学生交卷后即可查看自己的答题情况，标准答案严格按老师设置的公布方式展示；
- 证书仍按得分率 ≥ 90% 自动发放，流程测试中满分答卷证书正常生成。

**验证**

```bash
python manage.py check
python -m pytest -q
npm run typecheck
npm run build
```

实际结果：Django 系统检查 0 问题；后端全量 301 项测试通过
（含新增同班全流程与权限隔离测试）；前端 TypeScript 检查与 Vite 生产构建通过
（仅保留原有大 chunk 提示）。

---

### 2026-11-03 09:43 · FEAT-015 登录页新增四类演示身份快捷填入

**修改时间**：2026-11-03 09:43

**类型**：前端 / 演示账号

**现象**

- 登录页原有测试账号按钮按工作端排列，教师端只有一个 `teacher` 账号；
- 用户希望快捷栏直接提供学生、班主任、两位科任老师四类身份，
  其中班主任可以同时是某一学科的老师。

**涉及文件**

- 前端：`src/views/LoginView.vue`、`src/styles/index.css`；
- `CHANGELOG.md`。

**更改内容**

1. 登录页新增「演示身份快捷填入」区域，提供四个按钮：
   - 学生 `student`（王浩然，七年级（1）班）；
   - 班主任 `teacher`（陈志远，七年级（1）班班主任兼音乐老师）；
   - 科任老师 · 音乐 `teacher_music`（李静，不担任班主任）；
   - 科任老师 · 美术 `teacher_art`（赵敏，不担任班主任）；
2. 点击按钮自动填入账号和统一密码 `Demo@123456`，鼠标悬停可看到姓名、
   身份说明和密码；
3. 保留原有按工作端排列的测试账号区域，管理员等其他端口仍可快捷登录；
4. 新增说明文字，明确陈志远同时担任班主任和音乐老师，李静、赵敏为纯科任老师。

**影响**

- 四类身份可在登录页一键切换，便于分别检查班主任和科任老师的权限差异；
- 原有测试账号、密码和登录逻辑不变。

**验证**

```bash
npm run typecheck
npm run build
```

实际结果：TypeScript 类型检查通过，Vite 生产构建通过（仅保留原有大 chunk 提示）；
四个账号均通过接口登录成功。

---

### 2026-11-03 09:40 · FEAT-014 每位班主任只管理一个班级，补齐教师账号

**修改时间**：2026-11-03 09:40

**类型**：后端 / 权限 / 演示数据

**现象**

- 演示数据中陈志远、李静、赵敏分别同时担任 2~3 个班级的班主任；
- 7 个班级只有 3 个教师账号，部分教师跨班管理，无法体现
  “每位班主任只管理一个班级”的权限边界；
- 用户要求系统中出现信息的教师都有对应账号，并保留纯科任老师身份。

**涉及文件**

- 后端：`apps/classes/services.py`（新增班主任占用校验）、
  `apps/accounts/management/commands/seed_teacher_roster.py`（新增）、
  `apps/accounts/management/commands/bootstrap_demo.py`、`README.md`；
- 测试：`apps/classes/tests/test_classes.py`；
- 前端：`src/views/ClassesView.vue`；
- `CHANGELOG.md`。

**更改内容**

1. 新增 `seed_teacher_roster` 命令：为 7 个演示班级各配置一名独立班主任，
   每班有且只有一位音乐教师、一位美术教师；
2. 新增 6 个班主任教师账号：`teacher_wang`（王海涛）、`teacher_liu`（刘雅琴）、
   `teacher_zhou`（周晓梅）、`teacher_zhang`（张建国）、`teacher_he`（何晓燕）、
   `teacher_luo`（罗文静），密码统一为 `Demo@123456`；
3. `teacher_music`（李静）和 `teacher_art`（赵敏）改为纯科任老师，不再担任班主任；
   `teacher`（陈志远）继续担任七年级（1）班班主任并任教音乐；
4. 班级原有测评的发布人和试卷创建人同步转交给新的任课教师，
   保证“哪个班的老师发哪个班的试题”；
5. `bootstrap_demo` 在 `realify_demo_data` 之后自动执行教师配置命令；
6. 班级创建/修改接口增加校验：教师已担任其他班级班主任时返回 409，
   每位班主任同一时间只能管理一个班级；
7. 学校管理端班级编辑的班主任下拉框会禁用已被其他班级占用的教师；
8. README 补充命令说明、9 个教师账号及四类演示身份。

**影响**

- 当前 7 个班级共有 7 位班主任，每位只管理一个班级；
- 教师账号由 3 个增加到 9 个：7 位班主任 + 2 位纯科任老师；
- 每个班级都有班主任、音乐教师、美术教师，任课教师均有账号；
- 测试学生 `student`、`student_001` 仍在七年级（1）班，
  音乐测评由陈志远发布，美术测评由赵敏发布。

**验证**

```bash
python manage.py seed_teacher_roster
python manage.py check
python -m pytest apps/classes/tests/test_classes.py -q
python -m pytest -q
npm run typecheck
npm run build
```

实际结果：教师配置命令输出 7 个班级配置完成、12 场测评完成转交；
检查结果显示每班各有一位班主任、一位音乐教师、一位美术教师，班主任不跨班管理；
班级管理测试 18 项通过，后端全量测试通过，前端类型检查与构建通过。

---

### 2026-11-02 20:22 · FEAT-013 测试账号同班与按班发布校验

**修改时间**：2026-11-02 20:22

**类型**：权限 / 演示数据校验

**现象**

- 用户要求测试账号必须同属一个班，并且“哪个班的老师发哪个班的试题”；
- 需要确认测试学生不会看到其他班级的测评，教师也不能把测评发布到未任教班级。

**涉及文件**

- 后端：`apps/exams/scope.py`、
  `apps/exams/tests/test_papers_assessments.py`；
- `CHANGELOG.md`。

**更改内容**

1. 核对演示数据：`student`（王浩然）、`student2`（李雨桐）、
   `student_001`（张子涵）均属于 `C20260701` 七年级（1）班（班级 id=1）；
2. 核对班级教师：该班音乐由 `teacher`（陈志远）任教，美术由 `teacher_art`（赵敏）任教；
   两位教师都只向班级 id=1 发布对应学科的班级测评；
3. 核对可见性：七年级（1）班学生只能看到目标为本班的 5 场测评
   （音乐/美术各一场正式、各一场练习，另有 1 场本班正式测评），
   其他班级学生只看到自己班级的测评；
4. 新增回归测试 `test_teacher_cannot_publish_to_unassigned_class`：
   教师用本班试卷向未任教班级发布时返回 403；
5. `DataScope.ensure_paper_scope` 的越权提示由“无权在该范围创建试卷”
   改为“无权在该范围创建或发布试卷”，同时覆盖组卷和发布两种场景。

**影响**

- 演示测试账号的班级归属和测评可见性符合“同班师生、按班发布”；
- 教师发布范围继续由试卷归属班级决定，后端强制校验班级任教关系；
- 仅调整提示文案，不改变权限判定逻辑。

**验证**

```bash
python manage.py check
python -m pytest apps/exams/tests/test_papers_assessments.py -q
python -m pytest -q
```

实际结果：`manage.py check` 无问题；测评/组卷测试 25 项通过；
后端全量测试通过；通过接口核对 `student_001` 的测评列表只包含本班测评。

---

### 2026-11-02 17:16 · FEAT-012 题库浏览页移除题目分值显示

**修改时间**：2026-11-02 17:16

**类型**：前端

**现象**

- 教师端题库查询、试题管理和学生端章节题目中，每道题后面都显示“分值”；
- 用户希望浏览题目时不再显示分值，避免题库被误认为固定按分值组织。

**涉及文件**

- 前端：`src/views/TeacherQuestionBankView.vue`、
  `src/views/QuestionsView.vue`、
  `src/views/student/StudentKnowledgeView.vue`、
  `src/styles/index.css`；
- `CHANGELOG.md`。

**更改内容**

1. 教师端「题库查询」删除表格“分值”列和详情中的“分值”项；
2. 试题管理列表删除“分值”列，创建/编辑表单中的“默认分值”保留；
3. 学生端章节题目删除题头后的“X 分”标记，并清理对应样式；
4. 组卷选题、自动组卷分值预览、作答页、评分页和成绩页的分值保留，
   这些页面需要用分值计算总分或人工评分。

**影响**

- 题库浏览和章节浏览更简洁，不再展示题目默认分值；
- 组卷、作答、评分和成绩统计不受影响；
- 题目数据中的 `score` 字段未删除，仍用于组卷和评分。

**验证**

```bash
npm run typecheck
npm run build
```

实际结果：TypeScript 类型检查通过，Vite 生产构建通过（仅保留原有大 chunk 提示）。

---

### 2026-11-02 17:05 · FEAT-011 题库题目按章节归类，无关题目归入拓展类

**修改时间**：2026-11-02 17:05

**类型**：数据 / 题库分类

**现象**

- 单元练习之外的 3996 道题全部堆在“综合复习”章节里；
- 题库和课程章节无法看出这些题与哪个教材单元有关；
- 老师按章节组卷时，综合复习章节题目过多，不方便筛选。

**原因**

- `seed_question_bank`、`seed_grade_question_bank` 早期按旧通用章节或轮询方式
  分配章节，`seed_curriculum_units` 重建教材单元时又把旧章节统一合并到“综合复习”，
  导致题目与教材单元失去对应关系。

**涉及文件**

- 后端：`apps/exams/management/commands/classify_question_chapters.py`（新增）、
  `apps/exams/management/commands/seed_curriculum_units.py`、
  `apps/accounts/management/commands/bootstrap_demo.py`、`README.md`；
- 测试：`apps/exams/tests/test_question_classification.py`（新增）；
- `CHANGELOG.md`。

**更改内容**

1. 新增 `classify_question_chapters` 命令：从教材单元章节的知识讲解中提取
   重点作品名称、核心概念和章节名称作为关键词；
2. 对每道非单元练习题的题干、选项和解析做关键词匹配，命中则移入得分最高的
   教材单元章节；没有命中任何单元的题目统一归入该课程的“拓展类”章节；
3. 原“综合复习”章节统一改名为“拓展类”，18 门课程各保留一个拓展类章节；
4. 命令幂等，支持 `--dry-run` 预演、`--subject` 和 `--grade` 限定范围；
5. `seed_curriculum_units` 的合并目标同步改为“拓展类”，章节知识讲解中的
   练习数量更新为 18 题；
6. `bootstrap_demo` 在生成教材单元后自动执行题目归类；
7. 教师端题库查询和手动组卷选题表增加“所属章节”列，可直接看到题目归入的单元或拓展类；
8. README 补充题目归类命令和章节结构说明。

**影响**

- 96 个教材单元章节除原有单元练习外，还接收了与该单元作品、概念相关的题库题；
- 其余与教材单元无直接对应的题目集中到各课程的“拓展类”章节；
- 当前分类结果：归入教材单元 1209 道，归入拓展类 2787 道；
- 章节总数仍为 114 个（96 个教材单元 + 18 个拓展类），不再保留“综合复习”；
- 题目本身、题量和审核状态均未改变，只调整章节归属。

**验证**

```bash
python manage.py classify_question_chapters --dry-run
python manage.py classify_question_chapters
python manage.py check
python -m pytest -q
```

实际结果：预演与正式执行均显示单元题 1209 道、拓展题 2787 道；数据库核对
18 个“拓展类”章节、0 个“综合复习”章节，非单元练习全部有章节归属；
新增测试验证相关题进入单元、无关题保留在拓展类，重复执行不再搬动题目；
`manage.py check` 无问题，后端全量测试通过；前端 `npm run typecheck` 与
`npm run build` 均通过。

---

### 2026-11-02 15:35 · FEAT-010 单元练习增加判断题与填空题

**修改时间**：2026-11-02 15:35

**类型**：数据 / 题库

**现象**

- 题库中判断题只有 17 道、填空题只有 16 道，占全部 5148 道题不到 1%；
- 每个教材单元的 12 道练习只有单选、多选和实践题，学生平时几乎接触不到
  判断题和填空题；
- 新环境执行 `bootstrap_demo` 时也没有自动生成教材单元练习。

**原因**

- `seed_curriculum_units` 的 `_build_specs` 只生成单选、多选和实践题；
- `bootstrap_demo` 的固定步骤中没有包含 `seed_curriculum_units`。

**涉及文件**

- 后端：`apps/exams/management/commands/seed_curriculum_units.py`、
  `apps/accounts/management/commands/bootstrap_demo.py`、`README.md`；
- `CHANGELOG.md`。

**更改内容**

1. 每个教材单元在原有 8 单选 + 3 多选 + 1 实践题基础上，新增 3 道判断题
   和 3 道填空题，共 18 道单元练习；随机练习仍保持 6 单选 + 3 多选 +
   1 实践共 10 道，不改变原有规则；
2. 判断题从本单元重点作品的作者、国家、体裁、表现形式生成正确与错误说法，
   正误交替，避免答案集中在同一项；
3. 填空题从作品作者、体裁、表现形式和概念解释生成，答案写入
   `answer.values`，由系统自动判分；
4. 重新执行 `seed_curriculum_units`，96 个单元共生成 1728 道单元练习，其中
   判断 288 道、填空 288 道；全库题目由 5148 道增加到 5724 道；
5. `bootstrap_demo` 增加 `seed_curriculum_units` 步骤，新环境初始化时自动
   生成教材单元、知识讲解和单元练习；
6. README 同步更新为每单元 18 题、96 个单元共 1728 道题。

**影响**

- 判断题和填空题数量从原来的 33 道增加到 609 道，学生端章节练习和教师端
  题库都能直接筛选、作答与判分；
- 新增题目全部挂在对应年级、对应教材单元下，不跨年级；
- `short_answer` 仍为 0 道，没有重新引入问答题。

**验证**

```bash
python manage.py seed_curriculum_units
python manage.py check
python -m pytest -q
```

实际结果：命令输出“96 个单元，生成 1728 道章节练习”；数据库核对单元练习
单选 768、多选 288、判断 288、填空 288、实践 96，问答题 0；全库共 5724 道题，
其中判断题 305 道、填空题 304 道；新增 `test_curriculum_units.py` 校验每个单元的
题型构成与答案格式；`manage.py check` 无问题，后端全量测试通过。

---

### 2026-11-02 15:25 · FEAT-009 班主任/科任权限分权、题库按年级筛选、补齐班级测评

**修改时间**：2026-11-02 15:25

**类型**：权限 / 前端 / 演示数据

**现象**

- 科任老师（美术老师、音乐老师）也能新增、导入、重置密码、移出学生，
  甚至审核入班申请，与“班主任可以增删改查，科任老师仅可查看本班信息”不符；
- 教师端试题库仍按难度筛选、展示难度，与学生端知识页的难度星级一起，
  与“题库按一到九年级分，不按难度分”的要求冲突；
- 学生端只能看到音乐正式测评和少量自主练习，美术练习测评、音乐/美术
  教师练习测评缺失，无法演示“正式测评 / 练习测评”分开查询；
- 试卷审核成功后没有提示“已通知提交人”。

**原因**

- 学生账号维护接口只校验“是否为本校教师”，未区分班主任与科任老师；
- 班级导入、移出学生、审核申请同样缺少班主任校验；
- 试题库页面沿用旧的难度字段和筛选条件；
- 演示数据只发布了部分学科的正式测评，练习测评未覆盖全部班级。

**涉及文件**

- 后端：`apps/accounts/services/accounts.py`、`apps/classes/imports.py`、
  `apps/classes/services.py`、
  `apps/exams/management/commands/seed_class_assessments.py`（新增）、
  `README.md`；
- 前端：`src/views/TeacherQuestionBankView.vue`、
  `src/views/student/StudentKnowledgeView.vue`、
  `src/views/ClassesView.vue`、`src/views/TeacherStudentsView.vue`、
  `src/views/PaperReviewView.vue`；
- `CHANGELOG.md`。

**更改内容**

1. 后端新增 `teacher_can_manage_student`：仅班主任可维护本班学生账号；
   `create_student`、`delete_account`、`_can_manage_class_account` 改为
   班主任校验，科任老师保留只读查看；
2. 班级批量导入学生要求操作人是班主任；`remove_student`、`review_request`
   改为 `can_manage_class` 校验，移动学生和审核入班申请仅班主任或学校管理员可操作；
3. 教师端试题库改为按学科、年级、题型、关键词筛选，移除难度筛选、难度列和
   难度详情，增加“返回全部”；学生端知识页移除难度星级展示；
4. 班级管理页与学生管理页按班主任身份显示“学生管理/学生名单”、批量导入、
   移出班级、重置密码、学生审核等操作，科任老师只保留查看入口；
5. 新增 `seed_class_assessments` 命令：按班级任课关系为音乐、美术各生成
   正式卷与练习卷，经题库管理员审核后由任课教师发布到本班；演示环境实际
   检查 28 张试卷、新增 28 场测评，`student_001` 可见美术/音乐各一场正式测评
   与练习测评；
6. 试卷审核成功/驳回提示补充“已通知提交人”。

**影响**

- 科任老师不能再增删改学生、导入名单或审核申请，避免越权；
- 题库与知识页统一按年级组织，不再出现难度相关展示；
- 每个演示班级的学生端都有音乐、美术的正式测评和练习测评可查；
- 权限收紧只影响写操作，科任老师查看本班学生的能力不变。

**验证**

```bash
python manage.py check
python -m pytest -q
python manage.py seed_class_assessments
cd ../Art_assessment_frontend && npm run typecheck && npm run build
```

实际结果：`manage.py check` 无问题，后端全量测试通过；新增回归测试
`test_subject_teacher_can_view_but_not_mutate_students` 和
`test_subject_teacher_cannot_remove_import_or_review`，验证科任老师可查看本班学生，
但新增、修改、重置密码、删除、移出、导入与审核申请均返回 403；`seed_class_assessments`
输出“班级测评已补齐：检查 28 张试卷，新增 28 场测评”；前端 `vue-tsc` 类型检查
与 Vite 生产构建均通过（仅有既有的大 chunk 体积提示）。

---

### 2026-11-02 15:18 · FEAT-008 补齐初中美术教材单元，统一各年级章节数量

**修改时间**：2026-11-02 15:18

**类型**：数据 / 课程章节

**现象**

- 七年级、八年级、九年级美术只有 4 个教材单元，明显少于其他年级；
- 用户要求“每个年级的学习章节内容丰富一点”“多一点、最好官方一点”；
- 同一套课程章节在前端展示时，初中美术章节数量偏少，单元练习也相应偏少。

**原因**

- `seed_curriculum_units.py` 的 `UNITS[ART][7..9]` 人工整理时只收录了 4 个主题，
  遗漏了人美版教材中“生肖的联想”“中国画的形式美”“明暗与立体的表现”等内容。

**涉及文件**

- 后端：`apps/exams/management/commands/seed_curriculum_units.py`、
  `README.md`；
- `CHANGELOG.md`。

**更改内容**

1. 七年级美术新增“生肖的联想”，对应人美版七上“生肖的联想”一课；
2. 八年级美术新增“中国画的形式美”，对应人美版八上“中国画的形式美”一课；
3. 九年级美术新增“明暗与立体的表现”，对应人美版九上“明暗与立体的表现”一课；
4. 重新执行 `seed_curriculum_units --subject art --grades 7-9`，新增 15 个单元、
   180 道单元练习；每个新增单元仍为 8 单选 + 3 多选 + 1 实践作品题；
5. 同步修正 README 中的课程单元口径：音乐 1~6 年级每年级 6 个单元，音乐 7~9 年级
   和美术各年级每年级 5 个单元，另设“综合复习”章节；合计 96 个单元、1152 道题。

**影响**

- 初中美术各年级由 4 个单元增加到 5 个，与音乐 7~9 年级及美术其他年级保持一致；
- 新增题目全部为客观题与实践作品题，不含简答题；
- 已有单元与题目保持不变，命令幂等，可重复执行。

**验证**

```bash
python manage.py seed_curriculum_units --subject art --grades 7-9
python manage.py check
python -m pytest -q
```

实际结果：九年级美术等 3 个年级共新增 15 个单元、180 道练习；数据库核对
音乐 1~6 年级各 6 个单元/72 题，音乐 7~9 年级与美术各年级各 5 个单元/60 题，
`short_answer` 数量为 0；`manage.py check` 无问题，后端全量测试通过。

**备注**

未为音乐 7~9 年级强行补第 6 个单元：人音版该三册教材本身为 5 个单元，
保持与官方目录一致，避免生成无教材依据的章节。

---

### 2026-11-02 15:11 · FEAT-007 取消简答题，人工评分仅限实践作品与课外作品

**修改时间**：2026-11-02 15:11（本批改动 14:35–15:11）

**类型**：后端 / 前端 / 数据清理

**现象**

1. 题库、组卷、作答和评分流程仍保留简答题，教师需要人工逐题批改；
2. 评分任务把简答题、实践作品题混在一起，学生交卷后长期停留在「待评分」；
3. 题库端、教师端和演示数据仍会生成简答题，与“取消简答题”的要求冲突。

**原因**

- `QuestionType.SHORT_ANSWER` 被写入多个 seed 命令、组卷规则和人工评分逻辑；
- `grading_task_item`、`grading_attempt_detail` 按 `scoring_mode != AUTO` 收集主观题，
  未区分实践作品题；
- 练习卷出分逻辑用「是否存在简答题」判断是否延迟发布。

**涉及文件**

- 后端：`apps/exams/services/paper.py`、`grading.py`、`attempt.py`、`presenters.py`、
  `apps/qbank/services.py`、`apps/exams/management/commands/seed_grade_question_bank.py`、
  `seed_question_bank.py`、`seed_all_portals.py`、`seed_demo.py`、`seed_rich_demo.py`、
  `seed_curriculum_units.py`、`rebalance_question_grades.py`、相关测试；
- 前端：`src/api/mock.ts`、`src/views/PapersView.vue`、`QuestionsView.vue`、
  `PaperReviewView.vue`、`TeacherQuestionBankView.vue`、`GradingView.vue`、
  `student/StudentAttemptView.vue`、`StudentKnowledgeView.vue`、`WrongQuestionsView.vue`；
- `CHANGELOG.md`。

**更改内容**

1. 将数据库中 504 道简答题全部软删除（保留 `deleted_at`，不物理删除历史数据）。
2. 历史试卷中的 10 条简答题记录转换为音频实践作品题，1 份答卷快照同步转换，
   保持原试卷 100 分结构与既有成绩不变。
3. 所有 seed 命令（题库、全端口、演示、丰富演示、课程单元）不再生成简答题；
   `seed_grade_question_bank --short` 保留参数但不再生效。
4. 题库创建/更新接口拒绝 `short_answer`；手动组卷与自动组卷规则含简答题时返回 422。
5. 人工评分只接受 `image_upload`、`audio_upload`：
   - `submit_grading` 校验题型，非实践题返回 422；
   - 待评数量与终评校验只统计实践题；
   - 评分任务列表只返回含人工评分题的答卷；
   - 练习卷交卷后直接按客观题出分，不再等待简答题。
6. 前端移除简答题的题型标签、表单、作答框、校验与 mock 数据，
   作答页不再渲染文本作答框，评分页文案改为“实践作品题与课外作品”。
7. 课程单元 seed 重新执行：93 个单元，每单元 8 单选 + 3 多选 + 1 实践，共 1116 道，
   全部为已通过审核状态。

**影响**

- 题库、组卷、作答、评分、错题与学情统计中不再出现简答题；
- 学生交卷后只有实践作品题会进入教师评分任务；
- 历史试卷结构与已有成绩保持可追溯。

**验证**

```bash
python manage.py seed_curriculum_units
python -m pytest -q
cd Art_assessment_frontend && npm run typecheck
```

实际结果：课程单元生成 93 个单元、1116 道练习；后端全量测试通过；
前端 `vue-tsc -b` 无错误；数据库中 `type=short_answer` 且未删除的题目为 0。

**备注**

`QuestionType.SHORT_ANSWER` 仍保留在枚举与数据库 choices 中，用于兼容历史快照，
但业务入口已全部禁止新建或使用。

---

### 2026-11-02 15:05（补记） · FEAT-006 多端口批量修复、四川真实数据与课程单元题库

**修改时间**：2026-11-02 15:05（补记 2026-11-02 上午至下午的未记录改动）

**类型**：后端 / 前端 / 数据 / 文档

**现象**

1. 演示数据只有成都市青羊区一所学校，缺少四川其他市州、区县与学校；
2. 证书对所有分数发放，没有 90 分门槛，导出 PDF 排版普通；
3. 各端口「我的信息」未校验邮箱格式，查询页缺少返回按钮；
4. 学生「我的测评」正式与练习混在一起，按名称/班级搜索失效；
   「我的成绩」只显示部分测评；
5. 教师端无法给课外作品打分，评分后也无法修改；
6. 学校端教师账号缺少任教班级信息，部分提示条过长；
7. 题库端试卷审核没有省/市州/区县/学校筛选；
8. 课程章节内容单薄，题库题目与章节不对应。

**原因**

- 组织 seed 只覆盖单个区县；
- 证书服务未校验成绩阈值，PDF 使用简单文字排版；
- 前端表单缺少统一邮箱正则与返回按钮；
- 学生测评列表把 `paperType` 混排，搜索参数未传给后端；
- 课外作品只有查看，没有评分接口调用页面；
- 试卷列表虽支持组织 ID 过滤，审核页未提供对应筛选控件；
- 章节与题目由不同 seed 命令生成，缺少按教材单元的统一结构。

**涉及文件**

- 后端：`apps/organizations/management/commands/seed_sichuan_organizations.py`、
  `apps/exams/services/certificate.py`、`apps/exams/services/paper.py`、
  `apps/exams/services/grading.py`、`apps/exams/presenters.py`、
  `apps/files/models.py`、`serializers.py`、`views.py`、`urls.py`、
  `apps/accounts/services/account_data.py`、`account_serializers.py`、`accounts.py`、
  `account_views.py`、`apps/exams/management/commands/seed_curriculum_units.py`；
- 前端：`src/views/AccountsView.vue`、`ProfileView.vue`、`GradingView.vue`、
  `ScoresView.vue`、`ClassesView.vue`、`TeacherStudentsView.vue`、
  `PaperReviewView.vue`、`PapersView.vue`、`student/StudentAssessmentView.vue`、
  `student/StudentResultsView.vue`、`student/StudentArtworkView.vue`、`src/types/index.ts`；
- 前后端 README、`CHANGELOG.md`。

**更改内容**

1. **四川组织数据**：新增 `seed_sichuan_organizations`，按官方行政区划代码初始化
   21 个市州、45 个区县、37 所学校，使用 `update_or_create` 可重复执行。
2. **证书**：正式测评达到 90 分才生成证书；重做横版 PDF（奶油底色、深青金边、
   圆形“艺”徽标、绶带成绩区、四列信息栏、签名线与红色印章），避免文字重叠。
3. **邮箱与返回**：账号管理、个人资料等“我的信息”统一校验邮箱格式；
   查询页补充「返回全部」；项目概览卡片可点击进入对应页面。
4. **学生端**：正式测评与练习测评分开显示；修复按名称、班级号搜索；
   「我的成绩」展示正式与练习全部测评；成绩详情显示客观分、实践分与总分。
5. **课外作品评分**：新增作品评分字段与 `PATCH /files/{id}/review`；
   教师端「学生管理 → 课外学习材料」可打分、写评语、修改评分；
   学生端作品卡片显示教师评分与评语。
6. **教师与学校端**：教师账号列表显示任教班级；支持教师手动添加学生；
   班级管理、学生管理补充返回/重置按钮；缩短重置密码、归档班级等提示。
7. **题库端**：试卷审核页新增省、市州、区县、学校四级联动筛选，
   后端 `/papers` 支持 `provinceId/cityId/districtId/schoolId`；
   审核后保留在当前页并提示结果。
8. **课程与题库**：新增 `seed_curriculum_units`，按 1~9 年级音乐/美术教材单元
   重建章节，章节包含单元概述、学习目标、重点作品、核心概念、学习方法与课堂任务；
   每单元生成 8 单选 + 3 多选 + 1 实践，题目与单元内容对应。
9. **文档**：更新前后端 README 的命令、题量、人工评分范围与作答题型说明。

**影响**

- 演示组织覆盖四川主要市州，可按省/市/区县/学校逐级查询与审核；
- 证书只在正式测评 90 分及以上生成，PDF 可直接导出展示；
- 教师可对实践作品题和课外作品进行人工评分并修改；
- 课程章节、单元练习与题库形成按年级、按单元的组织结构。

**验证**

```bash
python manage.py seed_sichuan_organizations
python manage.py seed_curriculum_units
python -m pytest -q
cd Art_assessment_frontend && npm run typecheck
```

实际结果：组织命令创建 21 市州 / 45 区县 / 37 所学校；课程单元生成 93 个单元、
1116 道练习；后端全量测试通过；前端类型检查通过。

**备注**

本节为补记，时间取本次整理时的 15:05；更早的 2026-10-29 FEAT-005 记录保持不变。

> 时间说明：从本条记录起，每条记录在标题与正文中标注修改时间（精确到分钟）；
> 更早的记录原只有日期，本次补记时保留原日期，并在正文补充记录时间。

### 2026-10-29 18:28 · FEAT-005 教师身份分权、题库去年级化、四档难度与试卷审核预览滚动

**修改时间**：2026-10-29 18:28（本批改动 18:26–18:28）

**类型**：后端 / 前端 / 数据迁移

**现象**

1. 班主任与科任老师权限没有区分，音乐老师能创建美术试卷、看到美术试题和美术测评，
   美术老师同样能操作音乐内容；
2. 每个班可以同时存在多位音乐老师或多位美术老师；
3. 演示学生 `student_001` 所在班级缺少可直接用于权限验证的测试老师账号说明；
4. 题库按年级分册，三年级、六年级、八年级等未建册年级组卷时可用题数为 0，
   需要靠「回退到同学科题库」的补丁逻辑兜底；
5. 难度使用 1~5 级，老师发布测评时无法选择难易程度；
6. 题库管理端「查看原卷并审核」弹窗中，试卷题目区不能独立滚动，
   内容一多就被弹窗底部裁掉，无法下滑看完。

**原因**

- `ClassTeacher` 只有 `(班级, 教师)` 唯一约束，没有 `(班级, 学科)` 约束；
- 测评模块的 `DataScope` 只按班级收敛数据，没有按教师任教学科过滤；
- 组卷与随机练习都带有 `grade` 过滤和「本年级无题则回退」逻辑；
- 难度字段注释与校验均为 1~5；
- 审核弹窗的 CSS Grid 子项默认 `min-height: auto`，`max-height: 72vh` 无法触发内部滚动。

**涉及文件**

- 后端：`common/enums.py`、`apps/classes/models.py`、`apps/classes/services.py`、
  `apps/classes/migrations/0003_classteacher_uniq_class_teacher_subject.py`、
  `apps/exams/scope.py`、`apps/exams/models.py`、`apps/exams/serializers.py`、
  `apps/exams/presenters.py`、`apps/exams/services/paper.py`、
  `apps/exams/services/assessment.py`、`apps/exams/services/grading.py`、
  `apps/exams/services/score.py`、`apps/exams/services/certificate.py`、
  `apps/exams/services/statistics.py`、`apps/qbank/models.py`、`apps/qbank/services.py`、
  `apps/qbank/serializers.py`、`apps/qbank/migrations/0005_alter_question_difficulty.py`、
  `apps/accounts/services/accounts.py`、`apps/accounts/services/account_import.py`、
  各 seed 命令与测试；
- 前端：`src/views/PapersView.vue`、`src/views/AssessmentsView.vue`、
  `src/views/QuestionsView.vue`、`src/views/TeacherQuestionBankView.vue`、
  `src/views/student/StudentKnowledgeView.vue`、`src/types/index.ts`、`src/styles/index.css`；
- `CHANGELOG.md`。

**更改内容**

1. **教师身份分权**：`DataScope.teacher_subjects` 汇总「教师档案任教学科 + 班级任课学科」，
   新增 `ensure_subject()`；试卷/测评/试题/评分/成绩/证书/统计导出都按该集合过滤。
   音乐老师只能读写音乐内容，美术老师只能读写美术内容；班主任身份只影响班级管理，
   不额外授予另一门学科权限。教师创建试卷或试题时，学科选择在前端锁定为本人任教学科。
2. **每班每科一位老师**：`ClassTeacher` 增加 `(class_obj, subject)` 唯一约束；
   教师申请入班时校验申请学科必须与本人任教学科一致，且该班该学科已有老师时返回 409；
   管理员创建/导入教师、修改教师学科时也做同样校验。迁移按「优先保留班主任、其次保留最早记录」
   清理历史重复数据。
3. **测试老师账号**：演示学生 `student_001`（七年级（1）班）同班的测试账号为
   `teacher / Demo@123456`（班主任 + 音乐老师）与 `teacher_art / Demo@123456`（美术老师）。
4. **题库去年级化**：移除自动组卷、手动组卷、随机练习中的年级过滤与回退逻辑；
   题库列表、教师题库查询与试题列表不再提供年级筛选，创建试题时也不再手选年级
   （年级随所选课程自动带入），所有年级共用同一学科题库。
   年级仍保留在试卷上作为适用范围说明。
5. **四档难度**：新增 `QuestionDifficulty`（1 简单 / 2 中等 / 3 较难 / 4 困难）并迁移旧数据
   （原 5 级压缩为 4 级，5→4）；试题接口返回 `difficultyLabel`，问卷、题库查询和选题表显示中文难度；
   组卷时可选择难度，发布测评时可选择「难易程度」并随测评保存（`assessment.difficulty`）。
6. **审核预览滚动**：`review-workspace` 使用 `grid-template-rows: minmax(0, 1fr)` 与固定可视高度，
   左侧原卷区、右侧审核区分别 `min-height: 0; overflow-y: auto`；窄屏下改为自然高度，
   题目再多也能在弹窗内下滑查看。
7. **章节浏览**：教师查看章节题目时也会校验章节所属课程学科，避免绕过题库列表直接访问
   另一门学科的章节内容。
8. **展示补充**：测评列表新增「难度」列；题库/选题/知识页的难度统一显示为四档中文名称，
   README 的题库分册与难度说明同步改为「全年级共用、四档难度」。

**影响**

- 教师越权操作会被 403 拦截，题库、组卷、测评、评分、成绩、证书、统计均按学科隔离；
- 新增 `(班级, 学科)` 唯一约束，历史重复任课关系已被清理，每班每科只保留一位老师；
- 各年级都可以使用全部题目组卷，不再出现「该年级可选题为 0」；
- 难度统一为四档，旧题目数据已完成压缩迁移，历史统计口径保持一致（只压缩不丢题）；
- 审核弹窗可正常滚动，长试卷可完整查看。

**验证**

- 数据库迁移：`classes.0003`、`qbank.0005`、`exams.0007` 均已应用；
- 后端 `python -m pytest`：`283 passed, 11 subtests passed`（新增教师学科权限、每班每科唯一、
  测评难度记录等 4 项用例）；
- 前端 `npm run typecheck` 通过；
- 实际接口验证：`teacher` 只能看到 music 试卷/试题/测评，创建 art 试卷返回 403；
  `teacher_art` 只能看到 art 内容；教师题库列表学科集合分别为 `{music}` / `{art}`；
- 后端已按新代码重启（`127.0.0.1:8000`），前端 `127.0.0.1:5173` 热更新。

---

### 2026-10-29 17:57 · FEAT-004 测评/考试的交卷与退出确认框改为紧凑样式

**修改时间**：2026-10-29 17:57

**类型**：前端

**现象**

学生作答页（正式测评与随机练习共用 `StudentAttemptView.vue`）点击「交卷」「保存并退出」时，
弹出的 Element Plus 确认框仍是默认 420px 宽、大图标、大按钮的样式，
在答题页里显得特别大，和系统整体风格不协调。

**原因**

两处 `ElMessageBox.confirm` 只传了 `type`，没有指定 `customClass`，
因此沿用组件默认尺寸；上一批只给顶栏「退出登录」加了 `compact-confirm`。

**涉及文件**

- `Art_assessment_frontend/src/views/student/StudentAttemptView.vue`
- `CHANGELOG.md`

**更改内容**

1. 「提交答卷」确认框加 `customClass: 'compact-confirm'`，按钮文案改为
   「确认交卷 / 再检查一下」，避免误触；
2. 「保存并退出」确认框同样加 `compact-confirm`，保留「保存并退出 / 继续答题」；
3. 复用已有的紧凑样式（320px 宽、圆角 16px、15px 标题、13px 正文、30px 高按钮），
   不再新增重复样式。

**影响**

- 交卷与退出确认框与顶栏退出框保持一致，占用屏幕更小，答题内容不被大面积遮挡；
- 仅调整确认框外观与按钮文案，交卷、保存、计时、自动交卷逻辑未改动。

**验证**

- 前端 `npm run typecheck` 通过；
- Vite 热更新后 `StudentAttemptView.vue` 编译返回 200；
- 后端 `127.0.0.1:8000`、前端 `127.0.0.1:5173` 均在运行（后端未改动）。

---

### 2026-10-29 16:21 · FEAT-003 九项界面与交互修复（登录提示、退出框、错题页、音频作品、头像、手机号校验、表格排版）

**修改时间**：2026-10-29 16:21（各子项时间见下）

**类型**：前端 / 后端

**现象**

1. 退出登录的确认框沿用了 Element Plus 默认 420px 大框，按钮和留白都偏大，和学生端整体风格不协调；
2. 「我的错题」页面宽度仍按普通学生页 920/980px 限制，表格 7 列放不下，
   操作列要到右侧横向滑动才能看到；
3. 音乐作品页只接受图片（`accept="image/*"`、10 MB、只渲染 `<img>`），MP3 传不上去；
   练习/测评上传的音频走 `other` 分类，落在 `media/other`，作品库和 `media/student_work`
   里都看不到；
4. 头像只能手填「头像地址」，学生无法更换头像；
5. 登录账号或密码错误时，`client.ts` 把 401 当成登录态过期，走刷新令牌→跳转登录页，
   错误提示被吞掉，页面上看不到「账号或密码填写错误」；
6. 新建账号、修改个人信息时手机号没有位数校验，12 位、非 1 开头也能保存成功；
7. 教师端「学生管理」操作列 230px 塞了 5 个文字按钮；
8. 学校端「班级管理」操作列 330px 塞了最多 6 个文字按钮，挤在一起且不齐。

**原因**

- 退出确认未传自定义样式，直接使用组件默认宽度；
- 学生端页面宽度由 `.student-page { max-width: 920/980px }` 统一约束，错题页没有单独放开；
- 后端 `CATEGORY_RULES[STUDENT_WORK]` 只允许图片，前端也只按图片校验与展示；
  测评上传 `uploadAnswer` 写死 `category: 'other'`；
- 个人信息页没有上传入口，只有 URL 文本框；
- 响应拦截器对所有 401 一视同仁，未排除 `/auth/login`、`/auth/refresh`；
- 后端仅有 `max_length`，没有格式校验；前端表单也没有校验；
- 操作列用固定宽度 + 多个 `link` 按钮平铺，没有主次层级。

**涉及文件**

- `Art_assessment_frontend/src/api/client.ts`
- `Art_assessment_frontend/src/views/LoginView.vue`
- `Art_assessment_frontend/src/layouts/AppShell.vue`
- `Art_assessment_frontend/src/views/ProfileView.vue`
- `Art_assessment_frontend/src/views/AccountsView.vue`
- `Art_assessment_frontend/src/views/student/WrongQuestionsView.vue`（样式层）
- `Art_assessment_frontend/src/views/student/StudentArtworkView.vue`
- `Art_assessment_frontend/src/views/student/StudentAttemptView.vue`
- `Art_assessment_frontend/src/views/TeacherStudentsView.vue`
- `Art_assessment_frontend/src/views/ClassesView.vue`
- `Art_assessment_frontend/src/api/index.ts`
- `Art_assessment_frontend/src/types/index.ts`
- `Art_assessment_frontend/src/styles/index.css`
- `Art_assessment_backend/apps/files/views.py`
- `CHANGELOG.md`

**更改内容**（按完成顺序）

1. **16:00 登录失败提示**：拦截器跳过 `/auth/login`、`/auth/refresh` 的 401，
   直接抛出后端 `message`；登录页新增行内错误条，凭据类错误统一显示
   「账号或密码填写错误」，修改账号或密码时自动清除。
2. **16:02 退出确认框**：改用 `compact-confirm` 自定义样式（320px、圆角 16px、
   按钮高 30px），主按钮「退出」、次按钮「取消」；用户点取消时静默返回，不再产生未处理异常。
3. **16:04 我的错题页放宽**：`.wrong-page` 在 1360px 内自适应，
   学生端容器在该路由下放宽到 1440px；筛选栏允许换行，7 列表格与操作列直接完整显示，
   无需左右滑动；16:34 进一步收紧列宽（合计约 901px），
   确保 1280/1366 宽度下也不出现横向滚动条。
4. **16:06 音乐作品与拖拽上传**：
   - 后端 `STUDENT_WORK` 放开音频扩展名（mp3/wav/m4a/webm/ogg）并把上限提到 20 MB；
   - 作品列表接口新增 `mimeType` 字段，前端据此区分音频/图片；
   - 作品页按学科切换 `accept`（音乐为音频、美术为图片），新增整块拖拽区
     （拖入高亮、松开上传），音频作品卡片显示音符图标 + `<audio>` 播放器，
     预览弹窗按类型播放音频或展示图片；
   - 新建账号/作品上传共用的 `api.files.upload(file, category)` 一并提供。
5. **16:09 测评内拖拽上传**：图片/音频作品题的上传区支持拖拽上传，
   拖入时边框与底色高亮；`uploadAnswer` 分类由 `other` 改为 `student_work`，
   练习/测评上传的作品从此与课外作品同目录，能在作品库和 `media/student_work` 中看到。
6. **16:11 可换头像**：个人信息页新增头像上传（JPG/PNG/WEBP，≤10 MB），
   上传后立即保存并同步侧栏与顶栏；支持移除头像，恢复姓名首字展示。
7. **16:13 手机号位数校验**：个人信息、账号新建/编辑表单统一 11 位、以 1 开头校验，
   输入框 `maxlength=11`、数字键盘；与后端校验规则保持一致。
8. **16:15 教师端学生管理排版**：操作列收窄到 170px，
   改为「查看学籍」主操作 + 「更多」下拉（测评成绩/学习材料/身份材料/重置密码），
   列内垂直居中；学习材料抽屉同步支持音频作品播放。
9. **16:16 学校端班级管理排版**：操作列 330px → 170px，
   改为「班级信息」主操作 + 「更多」下拉（编辑班级/申请科任/学生名单/学生审核/归档班级），
   按角色与班主任身份显隐，归档项单独分组。
10. **16:17 样式**：新增 `.login-error`、`.compact-confirm`、`.artwork-dropzone`、
    `.artwork-audio`、`.avatar-actions`、`.avatar-field`、`.table-row-actions`、
    `.row-more-button` 等样式，沿用现有蓝紫配色与圆角体系。
11. **16:40 历史作品归位**：把此前落在 `other` 分类、带答卷 `bizId` 的 4 份学生上传
    （2 个 WAV 录音、2 张练习图片）复制到 `student_work` 并更新分类，
    作品库与教师「学习材料」立即可见；原文件保留，历史答卷中的旧 URL 仍可播放。

**影响**

- 登录失败不再被跳转流程吞掉；退出、错题、作品、头像、账号管理等页面观感统一；
- 音乐作品可直接在网页上传、在线试听，测评音频作品也会出现在学生作品库，
  教师查看学习材料时可直接播放；
- 手机号在前后端双重校验，历史数据不受影响（仅在新建/修改时校验）；
- 表格操作列由平铺改为「主操作 + 更多」，窄屏下也不会挤在一起。

**验证**

- 后端 `python -m pytest`：`279 passed, 11 subtests passed`（含本批新增 14 项手机号/头像/音频用例）；
- 前端 `npm run typecheck` 通过；
- 本地接口验证（重启 `runserver` 后）：
  - 错误密码登录返回 `{"code":401,"message":"账号或密码错误"}`，前端显示「账号或密码填写错误」；
  - `student` 账号上传 `test.mp3` → 200，`media/student_work/….mp3` 落盘，
    作品列表返回 `mimeType=audio/mpeg`；
  - `PATCH /auth/me` 传 12 位手机号 → 400，`errors.phone=手机号需为 11 位数字，且以 1 开头`；
    合法手机号与 `/media/...` 头像地址保存成功；
  - 验证后已删除测试音频并清空测试头像，保持演示数据整洁。

---

### 2026-10-29 15:38 · BE-014 证书 PDF 改版与手机号、头像、音频上传后端校验

**修改时间**：2026-10-29 15:38（证书细节打磨至 16:28，测试补充至 16:19）

**类型**：后端

**现象**

1. 下载的证书 PDF 只有白底黑字、一排文字，没有边框、印章与排版设计，观感差；
2. 新建账号、修改个人信息可保存超长手机号（如 12 位）或非 1 开头的号码；
3. 头像地址可写入任意字符串（含 `javascript:`），存在注入风险；
4. 学生作品分类只允许图片，MP3 被拒绝（`该分类不支持 .mp3 文件`）；
5. 教师批量导入模板中的手机号只校验非空。

**原因**

- 原 `_pdf` 只绘制姓名、测评名称、分数三行文字；
- `phone` 字段只有 `max_length=32`，无格式校验；
- `avatarUrl` 原为 `URLField`，改为 `CharField` 后未限制取值；
- `CATEGORY_RULES[STUDENT_WORK]` 仅含图片扩展名；
- 导入服务只判断 `if not phone`。

**涉及文件**

- `Art_assessment_backend/apps/exams/services/certificate.py`
- `Art_assessment_backend/apps/accounts/validators.py`（新增）
- `Art_assessment_backend/apps/accounts/serializers.py`
- `Art_assessment_backend/apps/accounts/account_serializers.py`
- `Art_assessment_backend/apps/accounts/services/account_import.py`
- `Art_assessment_backend/apps/classes/imports.py`
- `Art_assessment_backend/apps/files/services.py`
- `Art_assessment_backend/apps/files/views.py`
- `Art_assessment_backend/apps/accounts/tests/test_me.py`
- `Art_assessment_backend/apps/accounts/tests/test_accounts.py`
- `Art_assessment_backend/apps/classes/tests/test_classes.py`
- `Art_assessment_backend/apps/files/tests/test_files.py`
- `CHANGELOG.md`

**更改内容**

1. **15:31 证书样式**：横版 A4 暖白底（`#FFFDF7`），金色双线边框 + 四角装饰，
   顶部蓝/青/绿/金/紫五色细带；标题「艺术素质测评证书」38pt，配英文副标题与菱形分隔；
   正文为「兹证明 X 同学…」三段式，成绩行用主题蓝 20pt；
   信息栏为圆角浅米色面板，四列展示测评学科、所在班级、所在学校、证书编号；
   左下为发证单位与发证日期签名线，右下为双圈红色印章（艺术素质测评 / 认证专用章），
   页脚注明证书编号可核验。长文本统一走 `_short()` 截断，避免溢出。
   **16:26~16:28 调整**：底色增加淡蓝/淡紫光晕（半透明圆），成绩行改为
   「成绩 88.0 分 · 评定等级：良好」，红色印章从信息栏右下方下移到发证单位右侧
   （y=96、r=44），不再压住信息栏；四列信息分别限制为 6/12/12/26 字以适应栏宽。
2. **15:34 手机号校验**：新增 `apps/accounts/validators.py`
   （`CN_MOBILE_PATTERN = ^1[3-9]\d{9}$`、`validate_mobile`、`is_valid_mobile`），
   接入个人信息、账号新建/编辑、教师导入；错误提示统一为
   「手机号需为 11 位数字，且以 1 开头」，学生手机号/监护人手机号允许留空。
3. **15:36 头像地址白名单**：`avatarUrl` 仅接受 `/media/`、`http://`、`https://` 开头或空值。
4. **15:37 学生作品支持音频**：`STUDENT_WORK` 允许 `mp3/wav/m4a/webm/ogg`，上限 20 MB；
   作品列表返回 `mimeType`，前端据此渲染播放器。
5. **15:38 导入模板校验**：教师导入、班级学生导入时，手机号与监护人手机号
   必须为合法 11 位号码，否则该行报错并计入失败明细。
6. **16:19 测试**：新增个人信息手机号（4 类非法值）/头像协议校验、
   教师与学生创建手机号校验、`student_work` 接受 MP3 且列表返回 `mimeType`、
   `avatar` 分类拒绝音频等用例。

**影响**

- 证书下载后即可直接打印/展示，具备边框、印章与信息栏；
- 手机号格式在所有入口一致，历史数据保持原样；
- 音乐作品在前后端都可用，作品目录统一为 `media/student_work`。

**验证**

- `python -m pytest`：`279 passed, 11 subtests passed`；
- 生成样例证书 PDF 成功（A4 横版，约 5 KB），并用 PDF 渲染器转成图片逐项检查：
  标题、正文、信息栏、签名线、印章、页脚均在边框内，印章不压信息栏；
- 本地接口：12 位手机号 → 400 且返回字段级错误；`student_work` 上传 MP3 → 200。

---

### 2026-10-28 14:11 · FEAT-002 趣味课堂完整展示章节知识讲解与全部题目

**修改时间**：2026-10-28 14:11

**类型**：前端 / 后端

**现象**

学生在「趣味课堂」点开章节后，抽屉里只有一段知识讲解和「开始本章练习」按钮，
看不到本章有哪些题、题目长什么样，也无法在练习前复习知识点对应的题目；
教师端题库页能看到的完整题目信息（选项、答案、解析），学生在课堂里完全看不到。

**原因**

章节详情接口 `GET /api/v1/chapters/{id}` 只返回章节本身（含 `content` 与题目数量），
题目列表接口 `GET /api/v1/questions` 仅对题库/教师角色开放；
前端 `StudentKnowledgeView.vue` 因此没有可用的数据源来展示题目。

**涉及文件**

- `Art_assessment_backend/apps/qbank/services.py`
- `Art_assessment_backend/apps/qbank/serializers.py`
- `Art_assessment_backend/apps/qbank/catalog_views.py`
- `Art_assessment_backend/apps/qbank/chapter_urls.py`
- `Art_assessment_backend/apps/qbank/tests/test_catalog.py`
- `Art_assessment_frontend/src/views/student/StudentKnowledgeView.vue`
- `Art_assessment_frontend/src/api/index.ts`
- `Art_assessment_frontend/src/api/mock.ts`
- `Art_assessment_frontend/src/types/index.ts`
- `Art_assessment_frontend/src/styles/index.css`
- `CHANGELOG.md`

**更改内容**

1. 新增学生可访问的接口 `GET /api/v1/chapters/{chapter_id}/questions`（CHP-06）：
   返回章节信息、该章节**全部已通过审核**的题目和总数；未通过/已下线的题目不下发。
2. 新增 `build_learner_question`：题目按学习视角输出
   `type / difficulty / stem / score / options / answer / analysis / scoringMode / resources`，
   不包含创建人、审核人、审核意见等内部字段。
3. 抽题逻辑 `list_chapter_questions` 复用 `get_chapter` 的权限判断：课程未启用时学生
   访问返回 403，章节不存在返回 404。
4. 前端章节抽屉改为「知识讲解 + 本章题目」两段式：
   - 知识讲解按 `【学习目标】``【知识要点】` 等标题自动分块，逐条项目符号展示；
   - 本章题目按题型分组（单选、多选、判断、填空、听赏、简答、图片/音频作品），
     顶部题型筛选标签显示各题型数量，默认展示全部题目；
   - 每题展示题号、题型、难度星级、分值、题干、选项（正确选项绿色高亮）、
     音频/图片素材（音频可直接播放）、参考答案与解析；
   - 保留「开始本章练习（10 题）」入口与随机练习说明。
5. `src/api`、mock 数据与 `ChapterQuestion` / `ChapterQuestionBundle` 类型同步新增接口，
   保持 mock 模式可用。
6. 新增两条回归测试：学生能取到章节全部已通过题目且包含选项/答案/解析、待审核题目
   不下发；课程停用时 403、章节不存在 404。

**影响**

- 学生可以在趣味课堂里完整浏览每个章节的知识讲解和全部题目，练习前先复习；
- 答案与解析对学习者公开，属于课堂复习场景；正式测评与随机练习仍使用独立答卷，
  题目快照在开考时生成，不受该接口影响；
- 每章题目数量随题库规模变化（演示数据约 50~60 道/章），抽屉内可滚动查看。

**验证**

- `python -m pytest apps/exams apps/qbank -q` 全部通过（161 项）；
- 前端 `npm run typecheck` 通过；
- 本地接口验证：`student_6_1_20` 请求六年级音乐「乐理基础」章节，
  返回 57 道题（33 单选 + 17 多选 + 5 简答 + 2 音频作品），含知识讲解全文、
  选项、答案与解析；
- 重启后端 `runserver` 后新路由生效，前端 Vite 热更新加载新页面。

---

### 2026-10-28 14:08 · BE-012 成绩发布后自动生成学情报告，正式测评满 60 分发证书

> 规则更新：自 2026-11-03 14:00 FEAT-020 起，证书门槛已由 60% 调整为 90%，
> 本条保留为历史记录，现行规则以 FEAT-020 为准。

**修改时间**：2026-10-28 14:08

**类型**：后端

**现象**

学生完成教师发布的测评或日常随机练习后，「学习报告」页面没有内容，需要学生自己
打开报告页才触发生成；证书也必须教师手动点「生成证书」才会出现。用户要求：
完成测评和随机练习后都要生成学习报告；证书只在完成教师测评且达到 60 分以上才发；
分数等级为 60 分以上合格、70 分以上良好、90 分以上优秀。

**原因**

`_build_learning_report` 只在读取报告接口时懒生成；证书生成只有教师手动触发的
`generate_certificates` / `generate_for_assessment` 两条路径，交卷、终评、补录、
重新判分后都没有调用。等级线中「良好」仍按 80 分计算，与用户要求不一致。

**涉及文件**

- `Art_assessment_backend/apps/exams/services/achievement.py`（新增）
- `Art_assessment_backend/apps/exams/services/attempt.py`
- `Art_assessment_backend/apps/exams/services/grading.py`
- `Art_assessment_backend/apps/exams/services/score.py`
- `Art_assessment_backend/apps/exams/services/certificate.py`
- `Art_assessment_backend/apps/exams/services/growth.py`
- `Art_assessment_backend/common/utils.py`
- `Art_assessment_backend/apps/exams/rules/teacher_total.yaml`
- `Art_assessment_backend/apps/exams/models.py`
- `Art_assessment_backend/apps/exams/migrations/0006_alter_totalscorerule_good_line.py`（新增）
- `Art_assessment_backend/apps/exams/tests/test_certificates_growth.py`
- `Art_assessment_frontend/src/views/student/StudentCertificatesView.vue`
- `CHANGELOG.md`

**更改内容**

1. 新增 `apps/exams/services/achievement.py`：`after_score_released(score)` 在成绩
   正式发布后刷新学情报告（正式测评与随机练习都生成），再对正式测评调用证书发放；
   两步各自捕获异常并记录日志，避免影响交卷主流程。
2. 接入四个出分入口：学生交卷即时出分（`submit_attempt`）、教师终评
   （`submit_grading(finalize=True)`）、重新判分（`regrade_score`）、教师补录成绩
   （`score.py` 的 manual），均在事务提交后调用该钩子。
3. 证书准入 `certificate_eligible`：成绩已评分、属于正式测评、得分率 ≥ 60%；
   不满足时自动发放直接跳过，随机练习不生成证书。教师手动生成同样按该准入过滤。
4. 等级线调整为优秀 ≥ 90、良好 ≥ 70、合格 ≥ 60、其余待提升：
   `level_for` 良好阈值 0.8 → 0.7，`teacher_total.yaml` 的 `good: 80` → `good: 70`，
   `TotalScoreRule.good_line` 默认值 80 → 70（附带迁移），证书等级文案保持「合格」。
5. 学情报告汇总同时统计正式测评与随机练习次数（如「已完成 3 次测评（正式测评 2 次、
   随机练习 1 次）」），不再只统计正式测评。
6. 测试补充：90/70/60 分界值（100、90、89.99、70、69.99、60、59.99）、
   终评后自动发证书、补录 30/60 分不发证书、随机练习生成报告但不发证书；
   原「手动生成证书」用例改为强制重生成后断言 1 份。
7. 14:15 同步学生证书页文案：页头改为「完成老师发布的测评并达到 60 分后自动生成，
   70 分良好、90 分优秀」，空状态提示同步说明 60 分发放条件。

**影响**

- 学生交卷即可在学习报告看到最新数据；正式测评达到 60 分即自动获得证书；
- 随机练习只更新学习报告，不会产生证书；
- 教师端「生成证书」按钮仍然保留，可对达标学生强制重生成，对未达标学生跳过；
- 已有 80 分以上但不足 90 分的学生等级由「优秀」调整为「良好」，符合新等级线。

**验证**

- `python -m pytest apps/exams apps/qbank -q` 全部通过（161 项），其中
  `test_certificates_growth.py` 18 项通过；
- 测试覆盖：补录 30/60 分成绩后无证书；终评达标答卷后自动生成 `ready` 证书；
  随机练习交卷生成报告且不产生证书；等级边界值逐项断言；
- 迁移 `0006_alter_totalscorerule_good_line` 已生成并应用。

---

### 2026-10-28 13:50 · DATA-008 题库按难度平均分到一~九年级（每级约 500 道）

**修改时间**：2026-10-28 13:50

**类型**：数据 / 后端

**现象**

DATA-007 之后一~九年级虽然都有题，但七年级有 3700 道，其他 8 个年级各只有 100 道，
题量差距过大；教师选低年级组卷时可选题目明显偏少，各年级的题库规模不平均。

**原因**

`seed_question_bank` 只按七年级教材建了 3500 道题，`seed_grade_question_bank`
给其他年级各补 50 道后，七年级仍然集中了大部分题目。

**涉及文件**

- `Art_assessment_backend/apps/exams/management/commands/rebalance_question_grades.py`（新增）
- `Art_assessment_backend/apps/accounts/management/commands/bootstrap_demo.py`
- `Art_assessment_backend/apps/qbank/tests/test_rebalance_grades.py`（新增）
- `Art_assessment_backend/README.md`
- `Art_assessment_frontend/README.md`
- `README.md`
- `C:\Users\ter\Desktop\项目完整获取与运行教程.md` / `.docx`
- `CHANGELOG.md`

**更改内容**

1. 新增管理命令 `rebalance_question_grades`：把七年级多出的约 3200 道题按题型分组，
   在难度序列上均匀抽取后分到其他年级，使每个年级题量接近 500 道（音乐 + 美术）。
2. 分到目标年级的题目同时改挂该年级的课程与章节（按章节名映射），难度改为该年级
   的难度层级，题干前缀改为 `【音乐·X年级】` / `【美术·X年级】`，审核意见标注
   「按难度均衡分配至 X 年级」；七年级保留的题目统一为难度 3。
3. 抽取时按难度排序、低年级拿较容易的部分，并让七年级留下的题目也覆盖各难度段；
   同一题型按各年级缺口比例分配，保证每个年级都有单选、多选、简答与实践题。
4. 命令幂等：七年级题量不再高于目标时直接跳过；支持 `--dry-run` 预览、
   `--subject` 只调一个学科、`--target-per-grade` 改目标题量。
5. `bootstrap_demo` 在 `seed_rich_demo` 之后、`seed_all_portals` 之前执行均衡；
   `--skip-bank` 同步跳过。
6. 新增测试：名额分配求和与权重、均衡后年级/课程/章节/难度一致、重复执行不变。
7. 文档同步：前后端 README 与桌面运行教程补充均衡命令、最终分布与内容说明，
   `.docx` 已重新生成。

**影响**

- 题库 4500 道保持不变，一~九年级每个年级 500 道（音乐、美术各约 250 道）；
- 每个年级只保留一个难度层级，自动组卷、随机练习均只抽本年级题目；
- 分到低年级的题目内容仍来自七年级教材（如《命运交响曲》），属于演示数据的
  题量均衡，不是按低年级教材重新命题。

**验证**

- 数据库核对：每个年级 500 道，已审核 4496 道（七年级 496 + 其他年级各 500），
  难度与年级一一对应，题目的课程、章节年级全部一致；
- 重复执行输出「各年级题量已接近目标，无需调整」；
- 三、六、七、八年级音乐与三年级美术自动组卷均返回 200、10 题、100 分，
  抽到的题目年级与难度全部匹配（3→2、6→3、7→3、8→4）；
- `python -m pytest apps/exams apps/qbank -q` 全部通过（159 项）。

---

### 2026-10-28 13:25 · DATA-007 按年级分层补充题库（1~9 年级，每年级难度不同）

**修改时间**：2026-10-28 13:25

**类型**：数据 / 后端

**现象**

题库只有七年级的 3600 道题，一~六年级、八~九年级都没有独立题册。
自动组卷虽然能靠 BE-011 回退到七年级题库，但低年级学生也会抽到七年级难度的题，
不同年级试卷难度完全一样，无法体现分层。

**原因**

`seed_question_bank` 只按七年级教材建课、建题；其他年级没有课程与题目，
组卷、随机练习只能跨年级回退。

**涉及文件**

- `Art_assessment_backend/apps/exams/management/commands/seed_grade_question_bank.py`（新增）
- `Art_assessment_backend/apps/accounts/management/commands/bootstrap_demo.py`
- `Art_assessment_backend/apps/exams/tests/test_papers_assessments.py`
- `Art_assessment_backend/README.md`
- `Art_assessment_frontend/README.md`
- `README.md`
- `C:\Users\ter\Desktop\项目完整获取与运行教程.md` / `.docx`
- `CHANGELOG.md`

**更改内容**

1. 新增管理命令 `seed_grade_question_bank`：为一~九年级每个年级分别建音乐、美术课程
   （七年级沿用已有课程），每年级每科生成 50 道（30 单选、12 多选、5 简答、3 实践），
   共 900 道，全部为已通过审核状态。
2. 难度按年级递增：一、二年级 1 级，三、四年级 2 级，五~七年级 3 级，八年级 4 级，
   九年级 5 级；题干带 `【音乐·X年级】` / `【美术·X年级】` 前缀，便于筛选与识别。
3. 题目素材按人教版音乐、人美版美术各年级教材的作品与知识点整理
   （如低年级《布谷》《小红帽》，高年级《命运交响曲》《开国大典》），
   并用结构化模板生成选项，不逐字抓取网站题库；对同义项、题材/时期/材质冲突
   做了过滤，避免出现「儿歌/儿童歌曲」这类两个选项都正确的情况。
4. 章节知识讲解按年级分低/高学段写入，低年级讲高低长短强弱快慢，高年级讲调式、和声、曲式。
5. `bootstrap_demo` 在 `seed_question_bank` 之后执行该命令；`--skip-bank` 同步跳过。
6. 新增测试：每年级每科的题量、题干去重、难度与年级对应；三年级自动组卷只抽
   三年级且难度为 2 的题。
7. 文档同步：前后端 README、根 README 与桌面运行教程补充新命令、难度表与
   4500 道总题量（3500 七年级 + 900 分层 + 100 分类），`.docx` 已重新生成。

**影响**

- 题库总量达到 4500 道，一~九年级每个年级都有音乐、美术独立题册；
- 自动组卷、学生随机练习优先抽本年级、对应难度的题目，未建册年级仍按 BE-011 回退；
- 七年级原有 3600 道题不受影响，命令重复执行为 0 新增。

**验证**

- `python manage.py seed_grade_question_bank` 首次新增 900 道，再次执行新增 0 道；
- 数据库核对：18 个年级/学科课程组合，每年级每科 50 道，章节讲解非空；
- 三、六、七、八年级音乐/美术自动组卷均返回 200，18 题、100 分；
- 三年级学生 `student_3_1_01` 随机练习 10 题（6 单选 + 3 多选 + 1 上传），全部来自三年级；
- `python -m pytest apps/exams apps/qbank -q` 全部通过（155 项）。

---

### 2026-10-28 13:15 · BE-011 自动/手动组卷在未建册年级回退到同学科题库

**修改时间**：2026-10-28 13:15

**类型**：后端修复

**现象**

教师在「自动组卷」中把年级选为八年级（或其他非七年级）时，保存提示
「题库题目不足：single_choice 需要 10 道，可用 0 道；multiple_choice 需要 5 道，可用 0 道……」，
各题型可用数全部为 0，无法生成试卷。

**原因**

`create_auto_paper` 的选题目 `_pick_questions` 与组卷校验 `_validate_question`
都严格要求 `question.grade == paper.grade`。演示题库（`seed_question_bank`）
全部按七年级生成，而演示班级包含三、六、八、七年级；非七年级班级组卷时
可用题数必然为 0。此前随机练习已做年级回退，组卷链路漏掉了。

**涉及文件**

- `Art_assessment_backend/apps/exams/services/paper.py`
- `Art_assessment_backend/apps/exams/tests/test_papers_assessments.py`

**更改内容**

1. 新增 `_grade_has_questions(subject, grade)`：判断题库是否为该年级单独建册。
2. `_pick_questions`：该年级没有已通过审核的题目时，去掉年级过滤，
   回退到同学科全部已通过题目（课程/章节筛选仍然生效）。
3. `_validate_question` / `_replace_questions` / `_build_paper` 增加 `enforce_grade`：
   仅当题库存在该年级题目时才校验「年级与试卷一致」；未建册年级允许跨年级用题，
   手动组卷同样适用，避免选不到题。
4. 新增两条回归测试：八年级自动组卷成功生成 3 题；三年级手动组卷成功 1 题。

**影响**

- 任意年级班级都可以正常自动组卷、手动组卷；
- 七年级等已有独立题册的年级仍严格校验年级，行为不变；
- 未建册年级的试卷会使用同学科（七年级）题目，属于演示数据限制，后续可按年级补题库。

**验证**

- `python -m pytest apps/exams apps/qbank -q` 全部通过（153 项）；
- 本地接口验证：`teacher` 对八年级（1）班自动组卷
  `6 单选 + 3 多选 + 1 音频实践` → 200，10 题、100 分；校验后已删除该测试试卷。

---

### 2026-10-28 10:48 · ENV-005 一条命令初始化演示环境，任何人拿到项目即可运行

**修改时间**：2026-10-28 10:48

**类型**：后端命令 / 文档 / 仓库配置

**背景**

ENV-004 已解决「克隆后默认走 mock、后端连 MySQL」的问题，但新机器仍需按顺序手动执行
11 条 seed 命令；顺序错误（题库晚于 `seed_all_portals`）会报
「题库题目不足：audio_upload 需要 1 道」。另外项目根目录没有 `.gitignore`，
整包上传时会带上 `node_modules`、`db.sqlite3`、`.env` 等本机内容。

**涉及文件**

- `Art_assessment_backend/apps/accounts/management/commands/bootstrap_demo.py`（新增）
- `Art_assessment_backend/apps/exams/management/commands/seed_chapter_knowledge.py`（新增）
- `Art_assessment_backend/apps/exams/management/commands/seed_question_bank.py`
- `Art_assessment_backend/README.md`
- `README.md`（仓库根目录）
- `.gitignore`（仓库根目录，新增）

**更改内容**

1. 新增 `bootstrap_demo` 命令：自动执行 `migrate` + 全部 seed，
   顺序固定为 menus → organizations → demo_accounts → demo → question_bank →
   rich_demo → all_portals → classes → primary_classes → **realify_demo_data**；
   题库提前到 `seed_all_portals` 之前，避免新库上传题不足；
   各步骤幂等，可重复执行；`--skip-bank` 快速模式同时跳过题库与 `seed_all_portals`。
2. `realify_demo_data` 作为最后一步：初始化完成后即为真实学校（成都市石室联合中学蜀华分校）、
   真实师生姓名与无演示前缀的题目，且**不加** `--purge-records`，保留业务记录。
3. `seed_question_bank` 末尾自动调用 `seed_chapter_knowledge`，题库与趣味课堂知识讲解一次补齐。
4. 新增仓库根 `.gitignore`：排除 `node_modules/`、`dist/`、`db.sqlite3`、`media/*`（保留
   `.gitkeep`）、`.env*`（保留 `.env.example`）、`.venv/`、`__pycache__/`、`_backup_*/` 等。
5. 根 README 增加「打包发给组员时」的包含/排除对照表、Node 版本与端口说明，
   常见问题扩充到 9 条；后端 README 补充 `bootstrap_demo`、命令顺序与 `realify_demo_data` 说明。

**影响**

- 新机器三步即可运行：`pip install -r requirements-local.txt` →
  `python manage.py bootstrap_demo` → `python manage.py runserver`，前端 `npm install && npm run dev`；
- 不需要 `.env`，不需要 MySQL / Redis / MinIO，初始化后直接可用全部演示账号登录；
- 发送项目文件夹（或整包上传）不会带上本机数据库、依赖目录与密钥配置。

**验证**

- 全新目录模拟：仅复制后端源码（排除 `.env`、`db.sqlite3`、`.venv`、`__pycache__`），
  执行 `python manage.py bootstrap_demo`，11 个步骤全部成功，退出码 0；
- 该新库中 `student / Demo@123456` 登录返回 200；
  `GET /api/v1/courses?subject=music` 返回 200（七年级音乐课程）；
  `/api/v1/courses/2/chapters` 四个章节均带 `content` 知识讲解（454 / 367 / 458 / 433 字）；
  `POST /api/v1/papers/practice/random` 传 `chapterId` 返回 200 并生成练习答卷；
- `realify_demo_data` 在新库输出真实姓名（教师 陈志远、学生 王浩然等）并完成；
- 后端 `python -m pytest -q` 全量用例通过。

---

### 2026-10-28 10:38 · ENV-004 新机器克隆后开箱可用（默认真实后端、本地零配置）

**修改时间**：2026-10-28 10:38

**类型**：配置 / 文档

**背景**

项目上传 GitHub 后，组员在自己电脑上运行，页面提示「还差一步才能真正连后端」，
默认走的是内置 mock，看不到真实数据。排查发现克隆后缺少三类被 `.gitignore` 排除的内容：

1. `Art_assessment_frontend/.env`：前端判断逻辑是 `VITE_USE_MOCK !== 'false'`，
   **文件缺失时等于走 mock**；
2. `Art_assessment_backend/.env`：`config/settings/dev.py` 中 `DB_ENGINE` 默认 `mysql`，
   `CACHE_BACKEND` 默认 `redis`，`FILE_STORAGE` 默认 `minio`，新机器没有这些服务会直接报错；
3. `Art_assessment_backend/db.sqlite3`：数据库不进仓库，必须自行初始化并执行演示数据命令。

**涉及文件**

- `Art_assessment_frontend/src/api/index.ts`
- `Art_assessment_frontend/src/views/LoginView.vue`
- `Art_assessment_frontend/.env.example`
- `Art_assessment_frontend/README.md`
- `Art_assessment_backend/config/settings/dev.py`
- `Art_assessment_backend/.env.example`
- `Art_assessment_backend/requirements-local.txt`（新增）
- `Art_assessment_backend/apps/accounts/management/commands/seed_demo_accounts.py`
- `Art_assessment_backend/media/.gitkeep`（新增）
- `Art_assessment_backend/README.md`
- `README.md`（仓库根目录，新增）

**更改内容**

1. 前端默认改为调用真实后端：`useMock = import.meta.env.VITE_USE_MOCK === 'true'`，
   只有显式设置为 `true` 才使用 mock，**克隆后不建 `.env` 即可连后端**。
2. 后端开发环境零配置：`config/settings/dev.py` 默认 SQLite + LocMem 缓存 + 本地文件存储，
   `.env` 缺失也能 `migrate` 与 `runserver`；显式配置仍优先生效。
3. `.env.example` 改为本地可直接复制的配置（SQLite + LocMem + local），
   MySQL / Redis / MinIO 项移入注释说明。
4. 新增 `requirements-local.txt`：去掉 Windows 上难装的 `mysqlclient`，
   本地演示用 `pip install -r requirements-local.txt`；连 MySQL 时仍用 `requirements.txt`。
5. `seed_demo_accounts` 未配置 `DEMO_PASSWORD` 时默认使用 `Demo@123456`（原为随机密码，
   新机器初始化后无法登录）。
6. 新增 `media/.gitkeep`，保证克隆后上传目录存在。
7. 新增仓库根 `README.md`：两个工程的完整启动顺序、演示账号表、7 条常见问题
   （页面显示 mock 数据、MySQL 连接失败、mysqlclient 安装失败、列表为空、密码不对、
   端口占用、上传失败）。
8. 前后端 README 同步更新：明确「不需要 `.env`」及本地依赖命令。

**影响**

- 组员克隆后按 README 三步即可运行：装依赖 → `migrate` + `seed_*` → 启动前后端；
- 不再需要手工创建 `.env`；仍想用 Mock 时设置 `VITE_USE_MOCK=true`；
- 数据库与上传文件依旧不进仓库，避免把本机数据带到其他人电脑。

**验证**

- 模拟全新克隆（复制后端目录，删除 `.env`、`db.sqlite3`、缓存）：
  `python manage.py check` 通过、`migrate` 建库成功、
  `seed_menus` / `seed_organizations` / `seed_demo_accounts` / `seed_demo` 全部成功，
  `seed_demo_accounts` 输出「演示账号密码：Demo@123456」；
- 用 `student / Demo@123456` 调用 `POST /api/v1/auth/login` 返回 200，
  `GET /api/v1/courses?subject=music` 返回 1 门课程；
- 删除前端 `.env` 后 `npm run build` 通过，产物走真实接口；
- 后端 `python -m pytest -q` 全量用例通过。

---

### 2026-10-28 10:28 · FEAT-001 趣味课堂补齐知识讲解与章节练习入口

**修改时间**：2026-10-28 10:28

**类型**：新增功能 / 修复缺陷

**涉及文件**

- `Art_assessment_backend/apps/qbank/models.py`
- `Art_assessment_backend/apps/qbank/migrations/0004_chapter_content.py`（新增）
- `Art_assessment_backend/apps/qbank/serializers.py`
- `Art_assessment_backend/apps/qbank/services.py`
- `Art_assessment_backend/apps/exams/management/commands/seed_chapter_knowledge.py`（新增）
- `Art_assessment_backend/apps/exams/management/commands/seed_question_bank.py`
- `Art_assessment_backend/apps/exams/services/paper.py`
- `Art_assessment_backend/apps/qbank/tests/test_catalog.py`
- `Art_assessment_backend/apps/exams/tests/test_papers_assessments.py`
- `Art_assessment_frontend/src/views/student/StudentKnowledgeView.vue`
- `Art_assessment_frontend/src/views/CoursesView.vue`
- `Art_assessment_frontend/src/api/index.ts`
- `Art_assessment_frontend/src/api/mock.ts`
- `Art_assessment_frontend/src/types/index.ts`
- `Art_assessment_frontend/src/styles/index.css`

**问题（检查结论）**

1. 趣味课堂只有「课程 → 章节名称 + 题目数」，**没有任何知识讲解正文**：
   9 个章节的 `description` 全为空，`Chapter` 模型也没有知识正文字段。
2. 章节**不可点击**，页面没有「开始本章练习」入口；3600 道题虽然挂在章节上，
   但学生端无法从课堂页进入练习。
3. 学生课程列表按 `course.grade == 学生年级` 过滤，而题库课程只有 7 年级分册，
   **三、六、八年级学生打开趣味课堂是空的**（7 个班级中 4 个受影响）。
4. 随机练习按学生年级严格抽题，上述年级题库为空，
   点击「随机练习」直接返回 409「题库中符合条件的单选题不足」。

**更改内容**

1. `Chapter` 新增 `content`（知识讲解正文，TextField）字段，
   章节列表/详情接口返回 `content`，题库管理员可新增与修改。
2. 新增 `seed_chapter_knowledge` 命令，为 9 个章节写入面向小学、初中的知识讲解：
   - 音乐：乐理基础、视唱练耳、音乐欣赏、乐器与演奏；
   - 美术：造型基础、色彩知识、中国书画、美术欣赏、设计与工艺；
   - 每章含「学习目标 / 知识要点 / 课堂小任务」，并补齐一句话章节说明；
   - 默认只补空内容，`--force` 覆盖；`seed_question_bank` 结束后自动调用。
3. 学生浏览范围调整：可查看本学科全部**已启用**课程（停用课程仍返回 403），
   课程卡片标注「适用 N 年级」，避免未建册年级看到空课堂。
4. 随机练习抽题增加年级回退：优先抽本年级题目，
   本年级题量不足时回退到同学科（同章节）题库，并在题量仍不足时给出明确 409。
5. 前端趣味课堂：
   - 章节行可点击，右侧抽屉展示章节说明、知识讲解正文与题量；
   - 抽屉内「开始本章练习（10 题）」调用 `/papers/practice/random` 并带 `chapterId`，
     创建后直接跳转 `/student/attempt/{attemptId}` 作答；
   - `api.attempts.startPractice(subject, chapterId?)` 支持章节参数，
     mock 模式同步为 6 单选 + 3 多选 + 1 实践题。
6. 题库管理端「课程与章节」：章节编辑弹窗新增「知识讲解」多行输入框，
   列表新增「知识讲解：已填写/未填写」标记。

**影响**

- 趣味课堂从「目录页」变为「可读、可练」的完整闭环：
  选课程 → 选章节 → 读知识点 → 做 10 题本章练习 → 交卷即时出分；
- 三、六、八年级学生可正常进入课堂并做练习，不再因题库分册缺失而报错；
- 章节知识讲解可由题库管理员在后台维护，无需改代码；
- 练习仍不计入正式测评统计，不生成证书。

**验证**

- 后端 `python -m pytest -q`：全量用例通过（新增 2 条用例：
  `test_chapter_knowledge_content_visible_and_editable`、
  `test_practice_falls_back_when_grade_bank_missing`）；
- 前端 `npx vue-tsc --noEmit` 与 `npm run build` 通过；
- 实机校验（三年级学生 `student_3_1_20`）：
  `GET /courses?subject=music` 返回 1 门课程，`GET /courses/{id}/chapters` 返回 4 个章节且均带 `content`；
  `POST /papers/practice/random {subject, chapterId}` 返回 200，
  题目 10 道、构成为 6 单选 + 3 多选 + 1 音频上传。

**已知限制**

- 题库由 `seed_question_bank` 按「轮转」方式挂到章节，同一个章节内会混有其它主题的题目
  （例如乐理基础下有作品赏析题）。本章练习抽题严格限定在该章节内，
  因此题量充足但主题不够纯粹；如需按知识点精准练习，需要后续对 3600 道题重新做主题归类。

---

### 2026-10-28 09:36 · DOC-003 导出全部用户账号统计表

**修改时间**：2026-10-28 09:36

**类型**：文档 / 数据统计

**涉及文件**

- `用户账号统计表_2026-10-28.xlsx`
- `用户账号统计表_2026-10-28.csv`

**更改内容**

1. 从当前 SQLite 数据库导出全部 132 个账号：
   - 学生 124 人、教师 3 人、管理员 5 人；
   - 覆盖 7 个班级，学生均已分班。
2. Excel 工作簿包含 5 个工作表：
   - `说明`：生成时间、数据来源、人数汇总、密码与保密提示；
   - `全部用户`：角色、姓名、登录账号、密码、学校/单位、单位类型、班级/任教班级、班主任班级、年级、学号、任教学科、职称、性别、手机号、邮箱、监护人手机号、状态、最近登录、创建时间；
   - `角色统计`：各角色人数与账号示例；
   - `班级统计`：学校、年级、班级、班级号、班主任、任课教师、学生数；
   - `班级花名册`：按班级列出的学生账号、密码、性别、监护人手机号与状态。
3. 同时导出 UTF-8 BOM 编码 CSV，便于直接打开。

**密码说明**

系统不保存明文密码。导出时对每个账号的密码哈希逐一校验，
确认 132 个账号当前均可使用 `Demo@123456` 登录；表中密码列据此填写。
若后续修改过密码，以实际修改为准。

**影响**

- 本表含登录凭据，仅用于本项目账号核对与教学演示，不应外传或提交到公开仓库；
- 未修改任何业务数据，仅新增两份导出文件。

**验证**

- 导出后核对：132 行用户、124 名学生、3 名教师、7 个班级；
- Excel 5 个工作表均可正常打开，CSV 为 20 列、132 行数据。

---

### 2026-10-28 01:36 · CHECK-001 全系统功能贯通检查与跨端逻辑修复

**修改时间**：2026-10-28 01:14:02 ~ 01:36（逐项时间见下）

**类型**：功能检查 / 修正业务逻辑 / 修正权限范围 / 修改前端交互 / 文档

**涉及文件**

- `Art_assessment_backend/apps/accounts/account_serializers.py`
- `Art_assessment_backend/apps/accounts/account_urls.py`
- `Art_assessment_backend/apps/accounts/account_views.py`
- `Art_assessment_backend/apps/accounts/services/accounts.py`
- `Art_assessment_backend/apps/accounts/tests/test_accounts.py`
- `Art_assessment_backend/apps/classes/imports.py`
- `Art_assessment_backend/apps/classes/services.py`
- `Art_assessment_backend/apps/classes/tests/test_classes.py`
- `Art_assessment_backend/apps/exams/presenters.py`
- `Art_assessment_backend/apps/exams/scope.py`
- `Art_assessment_backend/apps/exams/serializers.py`
- `Art_assessment_backend/apps/exams/urls.py`
- `Art_assessment_backend/apps/exams/views/scores.py`
- `Art_assessment_backend/apps/exams/services/attempt.py`
- `Art_assessment_backend/apps/exams/services/assessment.py`
- `Art_assessment_backend/apps/exams/services/grading.py`
- `Art_assessment_backend/apps/exams/services/growth.py`
- `Art_assessment_backend/apps/exams/services/paper.py`
- `Art_assessment_backend/apps/exams/services/score.py`
- `Art_assessment_backend/apps/exams/services/statistics.py`
- `Art_assessment_backend/apps/exams/tests/test_attempts_grading.py`
- `Art_assessment_backend/apps/exams/tests/test_certificates_growth.py`
- `Art_assessment_backend/apps/exams/tests/test_papers_assessments.py`
- `Art_assessment_backend/apps/exams/tests/test_scores_statistics.py`
- `Art_assessment_backend/apps/exams/tests/test_scope.py`
- `Art_assessment_backend/apps/files/services.py`
- `Art_assessment_backend/apps/files/views.py`
- `Art_assessment_backend/apps/files/tests/test_files.py`
- `Art_assessment_backend/apps/qbank/signals.py`
- `Art_assessment_backend/apps/qbank/tests/test_review_signal.py`
- `Art_assessment_frontend/src/api/index.ts`
- `Art_assessment_frontend/src/api/mock.ts`
- `Art_assessment_frontend/src/config/menu.ts`
- `Art_assessment_frontend/src/router/index.ts`
- `Art_assessment_frontend/src/types/index.ts`
- `Art_assessment_frontend/src/views/AccountsView.vue`
- `Art_assessment_frontend/src/views/AssessmentsView.vue`
- `Art_assessment_frontend/src/views/ClassesView.vue`
- `Art_assessment_frontend/src/views/PapersView.vue`
- `Art_assessment_frontend/src/views/QuestionsView.vue`
- `Art_assessment_frontend/src/views/ScoresView.vue`
- `Art_assessment_frontend/src/views/TeacherStudentsView.vue`
- `Art_assessment_frontend/src/views/student/StudentReportView.vue`
- `Art_assessment_frontend/src/views/student/StudentResultsView.vue`
- `系统功能贯通检查报告_2026-10-28.md`
- `docs/archive/2026-10-28/系统功能贯通检查报告_2026-10-28.md`
- `CHANGELOG.md`

**更改内容（按时间）**

1. **01:14 · 账号组织选项与市州直属学校**
   - 新增 `GET /accounts/org-options`，按 city/district/school 层级与角色数据范围返回可选组织；
   - 市州管理员未指定区县创建学校时，直接以市州组织为父级；
   - 前端账号编辑按层级联动加载组织选项。
2. **01:16 · 答卷结果等级**
   - 学生交卷结果增加 `level`，成绩页可直接展示等级。
3. **01:18 · 文件范围与试题审核通知**
   - 文件删除收紧：题库管理员仅可删除题目图片/音频，学校及上级管理员仅可删除本校范围内文件；
   - 教师作品列表仅返回任教班级学生作品；
   - 试题审核通过/驳回写入通知，跳转 `/teacher/questions`。
4. **01:20 · 成绩导入任务与正式卷口径**
   - 新增 `GET /scores/imports/{taskId}`，仅本人或有管理范围的管理员可查；
   - 成绩列表默认只取正式测评并返回 `paperType`；
   - 补录/导入拒绝随机练习卷；
   - 统计只统计正式测评。
5. **01:21 · 成绩导入进度**
   - 成绩管理导入后每 2 秒轮询任务，展示排队/处理中/完成/失败及成功失败数。
6. **01:22 · 自动交卷**
   - `SubmitSerializer.submitType` 接受 `manual` / `auto`，修复倒计时自动交卷 400。
7. **01:23 · 教师端权限与入口收口**
   - 试题页按角色拆分编辑、提交审核、审核、资源管理、删除；
   - 教师可重新提交被驳回试题；
   - 试卷、测评、班级、账号页按创建人/班主任/角色收口按钮；
   - 教师申请加入班级时传任教学科；
   - 学校管理员新增“学生评分”菜单与路由权限；
   - 省级管理员隐藏学生导入入口。
8. **01:25 · 数据范围、练习可见性与通知**
   - `DataScope` 教师班级/学校集合纳入班主任班级；
   - 随机练习仅发布者本人可见、可作答；
   - 终评后发送“测评成绩已发布”通知；
   - 学情报告在出现更新成绩后自动重建；
   - 试卷审核详情补齐选项、资源、解析、评分细则、评分方式。
9. **01:26 · 审核门禁与跨校校验**
   - 试卷审核中/已通过不可修改，未通过可修改后重提；
   - 未通过审核的试卷不可发布；
   - 教师/管理端试卷列表默认只返回正式卷；
   - 班级申请与审核增加同校校验；
   - 班级申请提交/审核结果写入通知。
10. **01:31 · 成绩重新判分入口**
    - 成绩管理增加“重新判分”，仅在线作答成绩可用，要求填写原因并写审计日志；
    - 新增 `api.scores.regrade` 与 mock。
11. **01:33 · 班级导入初始密码**
    - 导入结果返回新建学生的临时账号与密码；
    - 支持表格“初始密码”列；前端导入后弹窗展示并支持下载 CSV。
12. **01:34 · 学习报告兜底**
    - 移除学生报告页写死的 `1001` 兜底用户 ID，未登录不请求。
13. **01:35 · 账号导入异步轮询与学生初始账号**
    - 教师导入超过阈值转为后台任务后，前端轮询 `/accounts/imports/{taskId}`；
    - 学校管理员导入学生后展示初始账号/密码并支持下载。
14. **01:36 · 检查报告与归档**
    - 新增本报告，记录端到端走查、接口对照、18 类修复、12 项待决策事项与验证结果。

**原因**

前后端在连续迭代后出现“页面有入口但后端拒绝”“后端有数据但前端口径不同”“审核状态未真正约束发布”等跨功能问题，需要按真实用户路径整体核对，并把可修的直接修掉。

**影响**

- 随机练习与正式测评彻底分流：成绩、统计、学生成绩页、补录/导入不再混用；
- 试卷审核成为发布前的真实门禁；
- 班主任与科任教师的数据范围一致；
- 班级/试题/评分/导入等异步或跨端操作均有通知或进度反馈；
- 班级导入可直接拿到学生初始账号，避免导入后无法登录；
- 前端不再展示当前角色无法执行的按钮。

**验证**

```bash
cd Art_assessment_backend
python manage.py check          # System check identified no issues
python -m pytest -q             # 249 passed

cd Art_assessment_frontend
pnpm typecheck                  # vue-tsc -b 通过
pnpm build                      # vite build 通过（仅体积提示）
```

详细走查结果见 `系统功能贯通检查报告_2026-10-28.md`。

---

### 2026-10-28 01:01 · DATA-006 / BE-009 / BE-010 / FE-008 测试账号同班、随机练习固定配比与问答题延后出分

**修改时间**：2026-10-28 00:50:11 ~ 01:01

**类型**：修正数据 / 修改业务逻辑 / 修改前端交互

**涉及文件**

- `Art_assessment_backend/apps/accounts/management/commands/realify_demo_data.py`
- `Art_assessment_backend/apps/exams/services/paper.py`
- `Art_assessment_backend/apps/exams/serializers.py`
- `Art_assessment_backend/apps/exams/services/attempt.py`
- `Art_assessment_backend/apps/exams/services/grading.py`
- `Art_assessment_backend/apps/exams/presenters.py`
- `Art_assessment_backend/apps/exams/tests/base.py`
- `Art_assessment_backend/apps/exams/tests/test_papers_assessments.py`
- `Art_assessment_backend/apps/exams/tests/test_attempts_grading.py`
- `Art_assessment_backend/apps/exams/tests/test_scores_statistics.py`
- `Art_assessment_backend/apps/exams/tests/test_integration.py`
- `Art_assessment_frontend/src/views/student/StudentAttemptView.vue`
- `Art_assessment_backend/README.md`
- `Art_assessment_frontend/README.md`
- `CHANGELOG.md`

**更改内容**

1. 2026-10-28 00:50:11 · 测试教师与测试学生同班：
   - `realify_demo_data` 的 `CLASS_TEACHERS` 为 `C20260701` 增加 `teacher` 的音乐科任关系，
     与 `teacher_music`、`teacher_art` 共同任教；
   - 现有数据库已用 `ClassTeacher.get_or_create` 补写该关系；
   - 测试教师 `teacher`（陈志远）与测试学生 `student`（王浩然）、`student2`（李雨桐）、
     `student_001`（张子涵）、`student_002`（刘思远）现在同属七年级（1）班 `C20260701`，
     教师组卷、发布的测评对该班学生可见。
2. 2026-10-28 00:50:21 · 学生随机练习固定配比（BE-009）：
   - `POST /api/v1/papers/practice/random` 固定生成 10 题：6 道 `single_choice`、
     3 道 `multiple_choice`、1 道实践题；
   - 音乐实践题优先抽 `audio_upload`，美术优先抽 `image_upload`，没有对应学科实践题时
     回退到任意图片/音频上传题；仍不足时返回 409 并给出缺口数量；
   - 不再抽取 `short_answer`，也不抽判断、填空，避免练习中出现需要教师人工评分的题目；
   - `PracticeRandomSerializer` 移除 `questionCount`、`questionTypes`，题型与题数由服务端固定。
3. 2026-10-28 00:50:36 · 含简答题的测评延后出分（BE-010）：
   - `submit_attempt` 仅在 `grading_status=graded` 时生成 `Score` 并重算排名；
     正式测评存在待人工评分的简答题/实践题时只保存客观题得分，答卷状态为 `submitted`；
   - `submit_result` 在未终评时不再返回主观分、AI 分和总分（`null`），
     增加 `scoreReleased=false`，提示「简答题等待教师评分，评分完成后公布成绩」；
   - `submit_grading` 只有 `finalize=true` 时才创建/更新成绩并写入 `graded_at`、重算排名；
     教师暂存评分草稿不会提前生成成绩；
   - 学生「我的成绩」只有终评后才出现该次测评，证书生成也仍以 `graded` 成绩为前提。
4. 2026-10-28 00:50:47 · 前端交卷反馈（FE-008）：
   - 交卷成功提示改用后端 `message`；自动交卷时保留「答题时间已到」提示；
   - 后端返回 `scoreId` 时才跳转「我的成绩」并打开详情，未出分时返回测评列表，
     避免学生看到空成绩页。
5. 2026-10-28 00:54:26 · 练习卷即时反馈：
   - `_apply_grading` 对 `paper_type=practice` 且不含简答题的答卷直接置为 `graded`，
     按客观题即时生成成绩；实践作品题不进入教师评分任务；
   - 若练习卷本身含简答题，仍按第 3 项规则延后出分。
6. 2026-10-28 00:52:31 ~ 01:01 · 文档与记录：
   - 后端 README 补充随机练习配比、延后出分与测试账号同班说明；
   - 前端 README 补充练习配比、待评分提示与 `teacher` 任教班级；
   - 本文件新增本条记录，并补充变更文件清单与 DATA-005 的记录时间。

**原因**

用户要求：演示账号里的学生和教师要在同一个班，测试教师发布的题测试学生能看到；
学生随机练习固定 6 道单选、3 道多选、1 道实践题，不要问答题，因为问答题需要教师
人工判分；做有问答题的试题时不要直接出成绩，等教师手动判分后再出成绩。

**影响**

- 测试教师 `teacher` 的数据范围新增七年级（1）班，可看到该班学生、答卷与成绩；
- 随机练习每次固定 10 题，题库按年级/学科/章节/难度筛选后按题型分别抽取；
- 含简答题的测评交卷后学生端不显示分数，教师完成终评后成绩自动出现；
- 纯客观题测评仍在交卷时立即生成成绩，行为不变；
- 自动交卷与手动交卷使用同一套延后出分逻辑。

**验证**

- `python manage.py check`：0 issues；
- 数据库抽查：`ClassTeacher` 中 `C20260701` 包含 `teacher`（音乐）、`teacher_music`、
  `teacher_art`；`teacher` 与 `student` 的当前班级均为 `C20260701`；
- 新增 `test_practice_random_creates_fixed_composition`：断言 10 题、6 单选、3 多选、
  1 音频实践题且无简答题；交卷后即时生成成绩；
- 新增 `test_submit_grades_objective_but_holds_score_until_manual_grading`：
  含简答题交卷后 `Score` 数量为 0、总分返回 `null`；
- 新增 `test_fully_objective_submission_releases_score_immediately`：
  纯客观题交卷后立即生成成绩；
- 新增 `test_save_draft_without_finalize_does_not_create_score`：
  教师暂存评分不生成成绩；
- 全量 `pytest`：240 passed，4 subtests passed；
- `pnpm typecheck`、`pnpm build`：通过。

**未完成 / 说明**

- 题库目前只有七年级题目；小学部学生（三年级、六年级）发起随机练习时仍会因
  “题库中符合条件的试题不足”返回 409，后续如需小学练习需补充对应年级题库；
- 本次未重新执行 `realify_demo_data`，避免影响现有业务记录，仅补写了班级任教关系。

---

### 2026-10-28 00:28（补记） · DATA-005 清理演示记录并替换为真实学校、姓名与题目

**修改时间**：2026-10-28 00:27 ~ 00:28（本次补记时按文件修改时间整理）

**类型**：清理演示数据 / 修改数据

**涉及文件**

- `Art_assessment_backend/apps/accounts/management/commands/realify_demo_data.py`（新增）
- `Art_assessment_backend/apps/accounts/management/commands/seed_primary_classes.py`（新增）
- `Art_assessment_backend/apps/exams/tests/test_auth.py`
- `Art_assessment_frontend/src/layouts/AppShell.vue`
- `Art_assessment_backend/README.md`
- `Art_assessment_frontend/README.md`
- `CHANGELOG.md`

**更改内容**

1. 新增管理命令 `realify_demo_data`，支持 `--dry-run` 预览，重复执行结果一致：
   - 默认只改组织、班级、姓名与题目；首次清理演示数据时加 `--purge-records`
     才会删除全部业务记录：试卷、试卷题目、试卷审核日志、测评、测评目标 / 年级、
     答卷、作答明细、成绩、证书、评分日志、错题、学情报告、通知、入班申请、
     操作日志、总分规则与导入任务；
   - `--purge-records` 同时删除相关文件：32 个登记文件（证书 PDF、课外作品 PNG 等）
     及 `media/` 下 2 个未登记的残留文件（导入 CSV、试题图片）。
2. 组织改为真实信息并合并重复树：
   - 删除 `DEMO-PROVINCE/CITY/DISTRICT/SCHOOL` 一套重复组织，
     账号与班级统一迁到保留的树；
   - 四川省 `510000` → 成都市 `510100` → 青羊区 `510105` →
     成都市石室联合中学蜀华分校 `510105000001`
     （九年一贯制公办学校，青羊区蜀华街 43 号）。
3. 班级改为真实编码并合并重复班：
   - `DEMO-ACC-7-1` 的 2 名学生并入 `DEMO-7-1`，删除重复班级；
   - 5 个初中班改为 `C20260701` ~ `C20260802`，班主任与音乐 / 美术科任教师重新分配；
   - 新增 `seed_primary_classes` 管理命令，补充小学部三年级（1）班 `C20260301`、
     六年级（1）班 `C20260601`，每班 20 人。
4. 账号姓名改为真实姓名（登录名、密码、学籍号、工号不变）：
   `teacher` → 陈志远、`teacher_music` → 李静、`teacher_art` → 赵敏、
   `student` → 王浩然、`student2` → 李雨桐、`student_001` → 张子涵、
   `student_002` → 刘思远，各级管理员 → 周立新 / 陈建平 / 刘敏 / 王建国 / 孙倩；
   其余 120 名学生（含小学部 40 人）按固定规则生成互不重复的姓名并同步性别。
5. 清理题目：
   - 删除 5 道 `[演示]` 试题及其所属课程「[演示] 七年级音乐」；
   - 去除 3500 道题库题干的 `【音乐】` / `【美术】` 前缀；
   - 清理 4 个班级、2 门课程简介中的「演示」字样，94 条试题审核意见改为
     「批量导入，审核通过」；
   - 题库保留 3600 道真实学科试题（音乐 1805、美术 1795）。
6. 前端去掉「演示环境」字样：侧边栏改为「本地环境 / 数据服务已连接」，
   顶栏标签改为「本地环境」。

**原因**

用户要求：除演示账号外，删除所有演示内容与记录；把演示学校、教师、学生改为真实姓名，
演示题目改为真实题目。

**影响**

- 账号仍可用原用户名和 `Demo@123456` 登录，登录后不再有历史试卷、测评、成绩、
  证书、通知等业务记录；相关列表为空属于预期结果；
- 学校、班级、师生姓名、题库内容均为真实信息；学校为九年一贯制，覆盖小学与初中学段；
- 组织表由 8 条减为 4 条，班级为 7 个（小学 2 个、初中 5 个）、学生 124 人、
  账号 132 个，题库 3600 道；
- 执行前已备份数据库与媒体文件到
  `C:\Users\ter\Desktop\终\_backup_20261027_before_cleanup\`
  （`db.sqlite3` 与 `media/`），需要恢复时可直接替换；
- 若重新执行 `seed_*` 演示数据命令，会再次写入演示组织、试卷与测评数据；
  清理应在演示数据命令之后执行；
- 修正前重跑 `realify_demo_data` 时仍默认清空业务记录，误删了首次清理后新建的
  1 份试卷、1 场测评、2 条通知等 25 条记录，且不在备份范围内、无法恢复；
  命令现改为默认保留记录，必须显式加 `--purge-records` 才执行清空。

**验证**

- `python manage.py realify_demo_data --dry-run`：预览数量与实际执行一致；
- 加 `--purge-records` 首次执行后再次运行：删除项均为 0，姓名 / 班级 / 题目不再变化（幂等）；
- 不带 `--purge-records` 运行：显示「保留现有业务记录」，不再删除试卷 / 测评；
- `python manage.py check`：0 issues；
- 数据库抽查：组织 4 条；班级 7 个（三年级 20、六年级 20、七年级 4 / 20 / 20、
  八年级 20 / 20 人）；账号 132 个且姓名互不重复；
  题干中无 `演示`、`DEMO`、`示例`、`示范` 或学科前缀；
- 10 个账号依次登录 `POST /api/v1/auth/login` 并调用 `GET /api/v1/auth/me`，
  返回真实姓名、成都市石室联合中学蜀华分校与对应班级；
- `GET /api/v1/classes` 返回 7 个班及班主任，`GET /api/v1/questions` 返回 3600 道；
- 全量 `pytest -q`：242 项通过；同步更新 `test_auth.py` 中过时的
  「题库管理员不可查看试卷」断言（BE-007 后题库端可只读查看试卷，仍不可创建）；
- `pnpm typecheck`、`pnpm build`：通过。

---

### 2026-10-27 · FE-007 / BE-008 音乐实践题支持直接录音

**类型**：新增功能

**涉及文件**

- `Art_assessment_frontend/src/views/student/StudentAttemptView.vue`
- `Art_assessment_frontend/src/utils/answers.ts`
- `Art_assessment_frontend/src/styles/index.css`
- `Art_assessment_backend/apps/files/services.py`
- `Art_assessment_frontend/README.md`、`Art_assessment_backend/README.md`
- `CHANGELOG.md`

**更改内容**

1. 学生作答页的音频作品题（`audio_upload`，即音乐实践题）在「点击上传作品文件」旁新增
   「直接录音」入口：
   - 使用 `getUserMedia` + `MediaRecorder` 采集麦克风，录音时显示红点、已录制时长和
     「取消 / 停止并上传」按钮；
   - 单次录音上限 5 分钟，到时自动停止并上传；
   - 已上传作品后可点击「重新录音」覆盖，新录音上传成功前保留原文件。
2. 停止录音后先转码再上传：
   - 用 Web Audio 解码录音，经 `OfflineAudioContext` 重采样为 24 kHz 单声道，
     再手工写入 WAV 头生成 `audio/wav`，解决浏览器录音（webm）缺少时长、
     播放器进度条异常的问题；
   - 解码或转码失败时回退上传原始录音（webm / m4a / ogg），不影响交卷；
   - 处理期间显示「正在处理录音」，完成后自动调用现有答案上传与保存逻辑。
3. 安全清理：
   - 切换题目、交卷、保存并退出或离开页面时，自动取消未完成的录音并释放麦克风；
   - 取消的录音不会上传，已有答案不受影响。
4. 文件类型支持扩展：
   - 前端音频白名单增加 WEBM / OGG，`isAudioFile` 同步识别，评分与预览页可正常播放；
   - 后端 `AUDIO_EXTS` 增加 `.webm` / `.ogg`，补充 `audio/webm`、`audio/ogg` MIME
     和 EBML（`1A 45 DF A3`）、`OggS` 文件头校验；
   - `other` 分类仍限制单文件 20 MB。

**原因**

音乐实践题原先只能先在其他设备或软件里录好音频再上传，学生端缺少现场录制能力。
用户要求为音乐实践题增加录音上传。

**影响**

- 支持录音的浏览器（Chrome / Edge / Firefox，Safari 14.1+）可现场录制并上传；
- 不支持 `MediaRecorder` 的浏览器会提示改用文件上传，原流程不受影响；
- 录音转 WAV 后 5 分钟约 14 MB，仍在 20 MB 限制内；
- 评分端、成绩端通过现有音频播放器预览录音。

**验证**

- `pnpm typecheck`、`pnpm build` 通过；
- 后端 `validate_upload`：`.webm`、`.ogg`、`.mp3` 均通过，`.exe` 仍被拒绝；
- 登录 `student` 后调用 `POST /api/v1/files`（`category=other`、`bizId=39`、
  `subject=music`）上传 webm：返回 200，`mimeType=audio/webm`，`/media/other/*.webm` 可访问；
- 测试文件与记录已清理；
- `pytest apps/files/tests -q`：3 项通过。

---

### 2026-10-27 · FE-006 登录页改为按账号角色直接进入

**类型**：修改前端交互

**涉及文件**

- `Art_assessment_frontend/src/views/LoginView.vue`
- `Art_assessment_frontend/src/api/index.ts`
- `Art_assessment_frontend/src/styles/index.css`
- `Art_assessment_frontend/README.md`
- `CHANGELOG.md`

**更改内容**

1. 删除「选择身份 → 账号登录」两步流程、工作端卡片和返回按钮，
   登录页改为单页表单，直接输入账号与密码。
2. 登录接口改为不传 `role`：后端 `POST /auth/login` 的 `role` 本来可选，
   返回值里的 `user.role` 即账号真实角色；前端用它写入会话并跳转：
   - 学生 → `/student/home`；
   - 教师、各级管理员、题库管理员 → `/dashboard`，侧边栏菜单再按角色展示对应端口。
3. 密码框默认留空，不再预填某个工作端的测试账号；「记住账号」只记住用户名。
4. 表单下方新增「测试账号」区，7 个按钮分别对应学生、教师、学校、区县、市州、省、题库，
   点击后填入该端测试账号与密码（真实模式 `Demo@123456`，mock 模式 `Abc@123456`）。
5. `api.auth.login` 的 `role` 参数改为可选，仅在传入时才放入请求体。
6. mock 模式下按用户名匹配测试账号，由账号决定角色，不再要求与所选工作端一致。

**原因**

原登录页必须先选工作端再输账号，账号与工作端不匹配时还会报错，
多一步操作且容易选错。用户要求直接登录，由账号决定进入哪个端口，
并在下方提供各端口测试账号的快捷输入按钮。

**影响**

- 登录步骤由两步变一步，任意角色的账号都可直接登录；
- 账号角色以服务端返回为准，前端不再自行指定；
- 快捷按钮只填入表单，不会自动提交登录；
- 使用旧版前端缓存的页面需要刷新一次。

**验证**

- `pnpm typecheck`、`pnpm build` 均通过；
- 后端服务层以 7 个演示账号依次登录，返回角色均与账号一致
  （`student_7_2_01` → student，`question_admin` → question_admin 等）；
- 用学籍号 `S20260702001` 也能登录并解析为学生；
- 通过 Vite 代理调用 `POST /api/v1/auth/login`（不传 `role`）：
  `student_7_2_01` → 200 / student，`question_admin` → 200 / question_admin；
- 错误密码返回 401「账号或密码错误」；
- `pytest apps/accounts/tests/test_login.py -q`：6 项通过。

---

### 2026-10-27 · DATA-004 新增演示班级与批量学生

**类型**：补充演示数据

**涉及文件**

- `Art_assessment_backend/apps/accounts/management/commands/seed_classes.py`（新增）
- `Art_assessment_backend/README.md`
- `CHANGELOG.md`

**更改内容**

1. 新增管理命令 `seed_classes`，在「演示中学」(`S001`) 下补充 4 个班级：
   - 七年级（2）班 `DEMO-7-2`，班主任 `teacher`
   - 七年级（3）班 `DEMO-7-3`，班主任 `teacher_art`
   - 八年级（1）班 `DEMO-8-1`，班主任 `teacher`
   - 八年级（2）班 `DEMO-8-2`，班主任 `teacher_art`
2. 每个班级生成 20 名学生账号（可用 `--per-class` 调整），共 80 人：
   - 登录名 `student_<年级>_<班号>_<序号>`，如 `student_7_2_01`；
   - 学籍号 `S2026<年级><班号><序号>`，手机号与性别按规则稳定生成；
   - 密码默认 `Demo@123456`，可用 `DEMO_PASSWORD` 覆盖；
   - 学生组织归属为演示中学，`StudentProfile.classroom` 指向对应班级。
3. 每个新班级挂上音乐、美术科任教师（`teacher` / `teacher_art`），
   教师端「班级管理」「学生管理」和学校端「班级管理」可直接看到。
4. 命令可重复执行：已有的班级、账号、班级关系不会重复创建；
   软删除的班级会被恢复，学生班级归属不一致时自动纠正。

**原因**

原有演示数据只有 2 个班级、共 4 名学生，教师端和学校端的班级列表、学生名单、
统计分页都不够直观。用户要求增加几个班级、每班约 20 名学生。

**影响**

- 演示中学班级数由 1 增至 5，学生数由 2 增至 82；全校学生账号共 84 个；
- 新班级暂无试卷与测评，仅用于展示班级与学生管理；
- 新增 80 个可登录学生账号，密码与既有演示账号一致。

**验证**

- `python manage.py seed_classes`：首次运行新建 4 个班、80 名学生；
- 再次运行：新建 0 个、调整 0 人（幂等）；
- `GET /api/v1/classes` 以 `school_admin` 调用：5 个班，新班级 `studentCount` 均为 20；
- 以 `teacher` 调用：可见 5 个班级；
- 以 `student_7_2_01 / Demo@123456` 登录 `GET /api/v1/auth/me`：返回学籍号
  `S20260702001`、班级七年级（2）班、学校演示中学。

---

### 2026-10-27 · FE-005 / BE-007 试卷审核统一到题库管理端

**类型**：修改权限与界面

**涉及文件**

- `Art_assessment_frontend/src/config/menu.ts`
- `Art_assessment_frontend/src/router/index.ts`
- `Art_assessment_frontend/src/views/PapersView.vue`
- `Art_assessment_frontend/src/views/PaperReviewView.vue`
- `Art_assessment_backend/apps/exams/services/paper_review.py`
- `Art_assessment_backend/apps/exams/services/paper.py`
- `Art_assessment_backend/apps/exams/views/papers.py`
- `Art_assessment_backend/apps/accounts/management/commands/seed_menus.py`
- `Art_assessment_backend/apps/accounts/tests/test_menus.py`
- `Art_assessment_backend/apps/exams/management/commands/seed_all_portals.py`

**更改内容**

1. 前端菜单与路由：
   - 「试卷审核」从学校、区县、市州、省管理员菜单中删除；
   - 只在题库管理端「题库管理」分组保留，路由 `roles` 仅 `question_admin`；
   - 其他端登录后不再看到试卷审核入口。
2. 组卷管理页 `PapersView`：
   - 删除「审核试卷」按钮、审核弹窗和通过 / 驳回逻辑；
   - 保留「提交审核」和「审核记录」，其他端只能提交和查看结果，不能审核。
3. 题库管理端 `PaperReviewView`：
   - 不再按 `reviewerId` 只看分配给自己的试卷，改为展示全部待审核试卷；
   - 文案改为「题库管理端统一审核各端提交的试卷」；
   - 指标改为待审核总数、已分配给我、当前审核身份。
4. 后端权限：
   - `POST /papers/{id}/review` 仅允许 `question_admin`；
   - `review_paper` 服务层增加角色校验，非题库管理员直接 403；
   - 试卷审核人 `resolve_reviewer` 固定分配题库管理员，不再按组织层级向上分配；
   - 题库管理员可读取全部试卷列表和详情，并支持 `reviewStatus` 筛选；
   - 其他端仍可调用 `POST /papers/{id}/submit-review` 提交审核。
5. 数据与菜单：
   - `seed_menus` 删除四类组织管理员的试卷审核菜单，新增 `qbank.paper_review`；
   - 已有数据库中的四个旧菜单软删除；
   - `seed_all_portals` 的演示审核人改为 `question_admin`。
6. 新增一份待审核演示试卷（ID 46，音乐，100 分），审核人为 `question_admin`，
   用于演示题库端审核页面。

**原因**

此前试卷审核采用「教师 → 学校 → 区县 → 市州 → 省 → 题库」的层级分配，
学校、区县、市州、省管理员和组卷管理页都能直接通过 / 驳回；
用户要求试卷审核与试题审核一样，全部集中到题库管理端。

**影响**

- 其他端口的菜单、组卷页不再出现试卷审核入口；
- 审核接口对非题库管理员返回 403；
- 题库管理员可以在 `/paper-review` 看到并处理所有待审核试卷；
- 历史已审核试卷保留原审核人记录，不影响成绩与已发布测评。

**验证**

- `python manage.py check`：通过；
- `pytest apps/accounts/tests/test_menus.py -q`：3 项通过；
- 测试客户端调用 `POST /api/v1/papers/46/review`：
  - `school_admin`、`teacher` 返回 403；
  - `question_admin` 通过权限校验（故意传旧版本号返回 409，证明已进入业务校验）；
- `GET /api/v1/papers?reviewStatus=pending` 以 `question_admin` 调用返回 1 份待审核试卷；
- 以 `question_admin` 打开试卷详情返回 200；
- 前端 `pnpm typecheck`、`pnpm build` 均通过。

---

### 2026-10-27 · FE-004 题库查询与「继续作答」体验

**类型**：修改前端 / 补充接口字段

**涉及文件**

- `Art_assessment_frontend/src/views/TeacherQuestionBankView.vue`
- `Art_assessment_frontend/src/views/QuestionsView.vue`
- `Art_assessment_frontend/src/views/student/StudentAssessmentsView.vue`
- `Art_assessment_frontend/src/types/index.ts`
- `Art_assessment_frontend/src/styles/index.css`
- `Art_assessment_backend/apps/exams/presenters.py`
- `Art_assessment_backend/apps/exams/services/assessment.py`
- `Art_assessment_backend/apps/exams/views/assessments.py`

**更改内容**

1. 教师端「题库查询」：
   - 题型筛选由 3 种扩展为全部 8 种（单选、多选、判断、填空、简答、听赏、图片作品、音频作品）；
   - 表格题型列显示中文名称，不再显示 `single_choice` 等枚举值；
   - 分页支持每页 10 / 20 / 50 / 100 条和页码跳转，适应 3500 道题库；
   - 详情抽屉展示试题资源：图片直接预览，音频提供播放器；
   - 标准答案改用 `formatAnswer` 格式化，不再显示原始 JSON。
2. 题库管理端「试题管理」：
   - 表格题型列显示中文名称；
   - 分页增加每页条数选择与页码跳转。
3. 学生端「我的测评」：
   - 测评卡片显示当前学生的答卷状态；
   - 存在进行中答卷时，按钮显示「继续作答」，并提示「第 N 次作答 · 剩余 X 分钟」；
   - 点击后仍调用原开始接口，由后端返回同一份未交卷答卷。
4. 后端 `assessment_item` 增加 `myAttempt` 字段（学生角色才返回）：
   - 包含 `attemptId`、`status`、`attemptNo`、`remainingSeconds`；
   - 列表查询使用 `Prefetch` 一次性取当前学生的答卷，避免逐条查询；
   - 其他角色该字段固定为 `null`。

**原因**

题库扩充到 3500 道后，原有题型筛选和分页方式不够用；
「保存并退出」虽然已能续答，但学生回到测评列表时看不到哪些测评已有进行中答卷。

**影响**

- 教师可以按多选题、音频作品等新题型检索题库；
- 学生能直接看出哪场测评可以继续作答，减少重复进入；
- 接口新增字段为向后兼容，旧前端不受影响。

**验证**

- `python manage.py check`：无问题；
- Django shell 中以 `student2` 调用测评列表，进行中答卷返回
  `{'attemptId': 39, 'status': 'in_progress', 'attemptNo': 2, 'remainingSeconds': 1799}`；
- `pnpm typecheck` 与 `pnpm build` 均通过；
- 题库查询页题型下拉包含 8 种题型，分页可选 100 条/页。

---

### 2026-10-27 · DATA-002 扩充音乐 / 美术题库至 3500 道

**类型**：新增数据

**涉及文件**

- `Art_assessment_backend/apps/exams/management/commands/seed_question_bank.py`（新增）
- `Art_assessment_backend/apps/qbank/models.py`（读取，未改动）
- `Art_assessment_backend/apps/exams/management/commands/seed_all_portals.py`（关联组卷）

**更改内容**

1. 新增 `seed_question_bank` 管理命令，按学科和题型生成固定数量的已审核试题：

   | 题型 | 音乐 | 美术 | 合计 |
   | --- | --- | --- | --- |
   | 单选题 `single_choice` | 1000 | 1000 | 2000 |
   | 多选题 `multiple_choice` | 500 | 500 | 1000 |
   | 简答题 `short_answer` | 200 | 200 | 400 |
   | 图片实践题 `image_upload` | — | 50 | 50 |
   | 音频实践题 `audio_upload` | 50 | — | 50 |
   | 合计 | 1750 | 1750 | 3500 |

2. 题目按人教版七年级音乐、人美版七年级美术的课标主题组织，素材覆盖：
   - 音乐：中外作品（60 首）、乐理术语、民族/西洋乐器、体裁与风格、视唱练耳、唱歌实践；
   - 美术：中外作品（60 幅）、美术术语、色彩知识、美术流派、造型基础、绘画实践。
3. 每个学科的单选题使用四种选项、多选题使用五个选项且固定三个正确答案；
   简答题、图片/音频实践题采用人工评分模式，客观题采用自动评分模式。
4. 题干写入 `【音乐】` / `【美术】` 前缀，并按课程、学科、题型去重；
   课程为「七年级音乐（人教版）」和「七年级美术（人美版）」，章节覆盖乐理基础、视唱练耳、
   音乐欣赏、乐器与演奏、造型基础、色彩知识、中国书画、美术欣赏、设计与工艺。
5. 所有题目状态直接设为 `approved`，创建人与审核人均为 `question_admin`，
   便于题库管理端直接组卷，无需再次审核。
6. 命令可重复执行：已有同题干题目会跳过，第二次执行新增数量为 0。

**原因**

原有题库仅约 100 道，无法支撑自动组卷、按题型抽题和演示数据的规模要求；
需要为音乐、美术分别提供足量的单选、多选、简答和实践题。

**影响**

- 题库总量达到 3500+，自动组卷和手工组卷都有充足题源；
- 图片实践题用于美术绘画作品上传，音频实践题用于音乐唱歌作品上传；
- 题目为结构化整理与模板生成，不是对某一网站题库的逐字抓取。

**验证**

```bash
cd Art_assessment_backend
python manage.py seed_question_bank
python manage.py shell -c "
from apps.qbank.models import Question
from collections import Counter
print(Counter(Question.objects.filter(deleted_at__isnull=True)
      .values_list('subject', 'type')))
"
```

实际结果：`music` / `art` 各 1750 道，合计 3500 道；
2000 道单选题全部 4 个选项，1000 道多选题全部 5 个选项且 3 个正确答案，
题干无重复，全部为已审核状态。再次执行命令输出「合计新增 0 道」。

---

### 2026-10-27 · BE-004 自动组卷固定 100 分

**类型**：修改业务逻辑

**涉及文件**

- `Art_assessment_backend/apps/exams/services/paper.py`
- `Art_assessment_backend/apps/exams/serializers.py`
- `Art_assessment_frontend/src/views/PapersView.vue`

**更改内容**

1. 新增常量 `AUTO_PAPER_TOTAL_SCORE = 100`，自动组卷总分固定为 100 分，
   不再采用题目自带的 `score` 或前端传入的 `scorePerQuestion`。
2. 按题型权重分配单题分值：

   | 题型 | 权重 |
   | --- | --- |
   | 单选题 `single_choice` | 1.0 |
   | 听力题 `listening` | 1.1 |
   | 判断题 `true_false` | 1.2 |
   | 填空题 `fill_blank` | 1.4 |
   | 多选题 `multiple_choice` | 2.0 |
   | 简答题 `short_answer` | 3.0 |
   | 图片实践题 `image_upload` | 4.0 |
   | 音频实践题 `audio_upload` | 4.0 |

   即单题分值始终满足：单选 < 多选 < 简答 < 实践题。
3. 根据实际抽到的题数计算每道题分值，保留两位小数；
   四舍五入产生的差额调整到权重最高的题型上，最后一道题兜底修正，
   保证试卷总分严格等于 100.00。
4. `AutoRuleSerializer.scorePerQuestion` 改为可选且不再参与计算；
   前端自动组卷表单移除分值输入，显示「100 分（固定）」和实时单题分值预览。

**原因**

不同试卷题量不同，若沿用每题固定分值会出现 92、105 等非整百分制；
同时需要保证题型越主观、单题分值越高。

**影响**

- 任意题量组合的自动组卷总分都是 100 分；
- 已存在的历史试卷分值不受影响；
- 自动组卷接口仍兼容旧客户端传入 `scorePerQuestion`，但会忽略该字段。

**验证**

以 10 道单选、5 道多选、2 道简答、1 道音频实践题组卷，返回：

```text
single_choice   3.33
multiple_choice 6.67
short_answer    10.00
audio_upload    13.35
试卷总分 100.00，共 18 题，分值合计 100.00
```

---

### 2026-10-27 · FE-002 学生作答支持全题型与图片 / 音频上传

**类型**：新增功能

**涉及文件**

- `Art_assessment_frontend/src/views/student/StudentAttemptView.vue`
- `Art_assessment_frontend/src/api/index.ts`
- `Art_assessment_frontend/src/types/index.ts`
- `Art_assessment_frontend/src/utils/answers.ts`（新增）
- `Art_assessment_frontend/src/components/AnswerPreview.vue`（新增）
- `Art_assessment_frontend/src/views/GradingView.vue`
- `Art_assessment_frontend/src/views/student/StudentResultsView.vue`
- `Art_assessment_frontend/src/styles/index.css`
- `Art_assessment_frontend/vite.config.ts`

**更改内容**

1. 作答页按题型渲染不同控件：
   - 判断题：正确 / 错误按钮；
   - 单选、听力题：选项按钮；
   - 多选题：可多选的选项按钮，答案以 `values` 数组提交；
   - 填空题：按 `answerConfig.blankCount` 渲染多个输入框；
   - 简答题：多行文本输入；
   - 图片 / 音频实践题：文件上传、预览、重新上传、移除。
2. 新增 `api.attempts.uploadAnswer(attemptId, file, subject)`：
   使用 `FormData` 调用 `POST /files`，`category=other`，附带 `subject` 与 `bizId`；
   返回 `fileId`、`url`、`name`、`mimeType`、`size` 并写入该题答案。
3. 前端校验文件类型和大小：图片 JPG/JPEG/PNG/WEBP，音频 MP3/WAV/M4A，最大 20 MB；
   后端 `apps/files` 另有扩展名、MIME 与文件头校验。
4. 新增 `utils/answers.ts`，统一格式化 `{value}`、`{values}`、`{text}`、文件对象和布尔答案；
   新增 `AnswerPreview.vue`，在评分页和学生成绩页把上传作品渲染为图片或音频播放器，
   修复此前对象答案显示为 `[object Object]` 的问题。
5. `vite.config.ts` 增加 `/media` 代理到 `http://127.0.0.1:8000`，
   本地开发时上传后的图片、音频可直接预览。
6. 答案数据兼容旧格式：加载答卷时复制 `values` 数组，避免直接修改接口返回对象；
   清空某题答案时提交 `{}`，保持与服务端保存逻辑一致。

**原因**

自动组卷已包含图片实践题和音频实践题，原作答页只有文本输入，无法完成作品提交；
评分页也无法正确展示上传文件。

**影响**

- 学生可以在浏览器内完成绘画图片、唱歌音频作品的上传与替换；
- 上传成功后立即保存答案，刷新或重新进入不会丢失；
- 教师评分页、学生成绩页可查看和播放上传作品。

**验证**

- 以 `student2` 登录，开始美术实践测评（attempt 34），上传 1×1 PNG：
  `POST /api/v1/files` 返回 `fileId=30`，保存后重新读取答卷可见完整文件元数据；
- 以同一账号开始音乐实践测评（attempt 35），上传 WAV：返回 `fileId=31`，
  `/media/...wav` 经 Vite 代理返回 200、`audio/wav`；
- 教师评分详情接口返回学生答案对象，简答题为 `{"text": ...}`，
  图片题为 `{"fileId": 30, "url": "/media/...png", ...}`；
- `pnpm typecheck` 与 `pnpm build` 均通过。

---

### 2026-10-27 · FE-003 作答过程「保存并退出」与断点续答

**类型**：新增功能

**涉及文件**

- `Art_assessment_frontend/src/views/student/StudentAttemptView.vue`
- `Art_assessment_backend/apps/exams/services/attempt.py`（复用已有续答逻辑）

**更改内容**

1. 作答页底部新增「保存并退出」按钮，点击后二次确认：
   - 确认文案说明答案会立即保存、考试继续计时、可从「我的测评」继续作答；
   - 保存成功才跳转 `/student/assessments`，保存失败则留在当前页并提示重试。
2. 退出时清理倒计时和自动保存定时器；重新进入时由后端 `start_attempt`
   返回同一份未到截止时间的进行中答卷，前端加载 `savedAnswers` 恢复答案。
3. 保留每 15 秒自动保存、页面隐藏时保存、截止时间自动交卷；
   手动「保存答案」与自动保存共用同一个 Promise，避免并发重复提交。
4. 倒计时剩余 5 分钟时提示一次，时间到自动提交并跳转成绩页。

**原因**

考试时间较长或学生需要切换到其他页面时，原页面只能提交或直接离开，
离开会丢失未保存答案；需要支持中途退出且不终止考试。

**影响**

- 学生可以分多次完成同一场测评，已答内容不丢失；
- 退出不会交卷，也不会消耗作答次数；
- 截止时间到达时仍会自动交卷，避免超过考试时间。

**验证**

- attempt 34 保存 3 道题后退出，再次 `POST /attempts/{id}/start`
  返回同一 attempt 34、状态 `in_progress`、`savedAnswers` 3 条；
- 前端构建通过，页面按钮与提示文案正常渲染。

---

### 2026-10-27 · BE-005 试题审核统一到题库管理端

**类型**：修改权限与界面

**涉及文件**

- `Art_assessment_backend/apps/qbank/views.py`（确认仅 `question_admin` 可审核）
- `Art_assessment_backend/apps/accounts/management/commands/seed_menus.py`
- `Art_assessment_frontend/src/views/DashboardView.vue`
- `Art_assessment_frontend/src/router/index.ts`（确认题库审核仅题库端路由）

**更改内容**

1. 试题审核接口继续只允许 `question_admin` 调用，
   其他六类角色（学生、教师、学校、区县、市州、省管理员）不再看到试题审核入口。
2. 所有试题审核操作集中在题库管理端「试题管理」页（`/qbank/questions`）：
   列表筛选待审核试题、查看详情、通过或驳回。
3. 移除 `seed_menus` 中已无对应前端路由的 `qbank.review`「试题审核」菜单项，
   并将数据库中已存在的该菜单软删除，避免题库端出现 404 死链。
4. 首页「待审核试题」指标卡仅对 `question_admin` 显示；
   其他角色只保留试卷审核等本职功能。
5. 试卷审核（`paper_review`）保持不变，仍由学校 / 区县 / 市州 / 省管理员按组织层级处理；
   本次删除的是「试题审核」，不是「试卷审核」。

**原因**

此前多个端口存在试题审核入口或指标，权限与职责边界不清；
试题审核应只由题库管理员统一负责。

**影响**

- 除题库管理端外，任何角色都无法查看或操作试题审核；
- 题库管理端的审核入口不变，历史待审核试题仍可处理；
- 组织管理员的试卷审核流程不受影响。

**验证**

- 以教师、学校管理员账号访问题库审核相关接口返回 403；
- 前端菜单与首页指标中不再出现试题审核入口；
- `python manage.py seed_menus` 执行后共生成 7 类角色、68 项有效菜单，
  `qbank.review` 不再生成。

---

### 2026-10-27 · DATA-003 新增实践作品上传演示测评

**类型**：新增演示数据

**涉及文件**

- `Art_assessment_backend/apps/exams/management/commands/seed_all_portals.py`

**更改内容**

1. 每个教学组合新增 1 张「实践作品上传体验」自动组卷：
   - 2 道单选题 + 1 道简答题 + 1 道实践题；
   - 美术使用 `image_upload`，音乐使用 `audio_upload`；
   - 试卷类型 `PRACTICE`，考试时长 30 分钟，自动审核通过并发布。
2. 测评时间从当前时间前 1 小时到 14 天后，作答次数上限 3 次，
   学生可在「我的测评」中直接进入并上传作品。
3. 移除演示自动组卷中已失效的 `scorePerQuestion` 字段，统一由后端按 100 分制计算。

**原因**

需要为图片上传、音频上传和「保存并退出」提供可直接演示的进行中测评。

**影响**

- 新增 4 张实践卷、4 场进行中测评（两个班级 × 音乐/美术）；
- `seed_all_portals` 总计生成 22 张试卷、20 场测评；
- 演示账号无需等待即可体验完整上传与评分流程。

**验证**

```bash
python manage.py seed_all_portals
```

实际输出新增试卷 4 张、测评 4 场；
测评 30–33 分别为音乐/美术两个班级的实践作品上传体验，均为 100 分、进行中状态。

---

### 2026-10-27 · DOC-002 更新 README 与更改记录

**类型**：文档

**涉及文件**

- `Art_assessment_backend/README.md`
- `Art_assessment_frontend/README.md`
- `CHANGELOG.md`

**更改内容**

1. 后端 README 增加 `seed_question_bank` 命令、3500 道题的学科/题型分布、
   自动组卷 100 分规则、上传与「保存并退出」说明；
   更新 `seed_all_portals` 的试卷与测评数量。
2. 前端 README 增加 `/media` 代理、作答题型、上传限制、自动保存与断点续答说明。
3. 本文件新增 DATA-002、BE-004、FE-002、FE-003、BE-005、DATA-003、DOC-002 记录。

**验证**

- 文档中的命令均已在本地执行；
- 文档描述与实际页面、接口行为一致。

---

### 2026-10-27 · DOC-001 创建更改记录

- 新增本文件，汇总前后端联调、演示数据、音乐模型导入等更改；
- 在 `Art_assessment_backend/README.md` 补充 `seed_all_portals` 命令与数据覆盖说明；
- 在前后端 README 顶部增加本文件的入口链接；
- 修正 `seed_rich_demo` 文档中的题目状态数量与重复导入。

后续更改请按模板追加到本节之上。
