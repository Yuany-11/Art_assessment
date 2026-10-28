# 艺术素质测评系统 · 更改记录

> 记录范围：`C:\Users\ter\Desktop\终` 下的 `Art_assessment_backend`（Django）与
> `Art_assessment_frontend`（Vue 3）两个工程。
>
> 记录方式：按时间顺序记录，最新更改追加到文末「最新更改」区域顶部；每次更改注明编号、
> 类型、涉及文件、原因、影响和验证方式。
> 未特别说明时，所有验证均在本地环境完成：后端 `127.0.0.1:8000`，前端 `127.0.0.1:5173`，
> 数据库 SQLite，缓存 LocMem，文件存储本地 `media/`。
>
> 最后更新：2026-10-28
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
python manage.py seed_rich_demo
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
| `seed_rich_demo` | 分类题库、自动组卷、历史测评、报告、证书、作品 | 是 |
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
| 音乐 | 七年级音乐（人教版） | 4 | 1805 |
| 美术 | 七年级美术（人美版） | 5 | 1795 |
| 合计 | — | 9 | 3600 |

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

> 时间说明：从本条记录起，每条记录在标题与正文中标注修改时间（精确到分钟）；
> 更早的记录原只有日期，本次补记时保留原日期，并在正文补充记录时间。

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
