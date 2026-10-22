# 艺术素质测评系统 · 模块三（测评业务与成绩服务）

后端 A（万逸恒）负责的测评核心业务实现：组卷、测评发布、在线答题、自动判分、人工评分、成绩统计与排名、证书、成长曲线与学情报告。

- 技术栈：Python 3.12 / Django 5.2 / DRF 3.16 / drf-spectacular / SQLite（默认，可切 MySQL 8.0）
- 接口前缀：`/api/v1`
- 统一响应：`{"code": 200, "message": "success", "data": ...}`（`code` 与 HTTP 状态码一致）
- OpenAPI 文档：[docs/openapi.yaml](../docs/openapi.yaml)（在项目根目录用 `python manage.py runserver` 后访问 `/api/schema/swagger-ui/`）

---

## 1. 快速开始

```bash
cd backend

# 依赖（本机 Python 在 D:\python）
D:/python/python.exe -m pip install -r requirements.txt

# 建表
D:/python/python.exe manage.py migrate

# 初始化演示组织、账号、题库、试卷、测评，并打印演示 Token
D:/python/python.exe manage.py seed_demo

# 启动
D:/python/python.exe manage.py runserver 0.0.0.0:8000
```

演示账号密码均为 `Demo@123456`，`seed_demo` 会直接打印 `teacher` / `student` / `student2` / `school_admin` 的 Bearer Token，便于前端联调。

重新初始化：`python manage.py seed_demo --reset`（只清演示账号与 `[演示]` 题库数据，不动其他数据）。

生成接口文档：

```bash
D:/python/python.exe manage.py spectacular --file ../docs/openapi.yaml
```

---

## 2. 目录结构

```
backend/
├── config/            # settings / urls / wsgi
├── accounts/          # 用户与组织模型（模块一提供，本模块只读）
├── questionbank/      # 题库模型（模块二提供，本模块只读）
├── common/            # 响应封装、异常、JWT、分页、数据范围、审计、枚举
│   ├── authentication.py   # HS256 JWT，校验 token_version + Redis 黑名单
│   ├── scope.py            # DataScope：按角色收敛到本人/班级/学校/区/市/省
│   ├── exceptions.py       # BusinessError + 全局异常处理
│   └── schema.py           # OpenAPI Bearer 认证声明
└── exams/
    ├── models.py           # 试卷/测评/答卷/答案/成绩/证书/评分日志/导入任务等
    ├── serializers.py      # 所有写接口的入参校验
    ├── presenters.py       # 所有响应字段组装（与 api.md 字段名一致）
    ├── services/           # 业务规则：paper/assessment/attempt/grading/score/
    │                       #          statistics/ranking/certificate/growth/ai
    ├── views/              # 36 个接口
    ├── urls.py             # 路由（静态路径先于 <int:...>）
    ├── management/commands/ # 定时任务、演示数据
    └── tests/              # 73 个接口/业务测试
```

分层约定：**view 只做鉴权、序列化、调用 service**；业务规则全部在 `services/`；响应字段全部由 `presenters.py` 输出，避免模型字段名直接泄漏到接口。

---

## 3. 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | 开发用固定值 | 生产必须替换 |
| `DJANGO_DEBUG` | `1` | 生产设 `0` |
| `DJANGO_ALLOWED_HOSTS` | `*` | 逗号分隔 |
| `DB_ENGINE` | `sqlite` | 设 `mysql` 切换 MySQL |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | — | MySQL 连接信息 |
| `SQLITE_PATH` | `backend/db.sqlite3` | SQLite 文件路径 |
| `JWT_SECRET` | 同 `SECRET_KEY` | **必须与模块一一致** |
| `JWT_ACCESS_TTL_MINUTES` | `30` | Access Token 有效期 |
| `REDIS_URL` | 空 | 配置后使用 Redis 缓存；为空用 LocMem（仅单进程） |
| `LATE_SUBMIT_GRACE_MINUTES` | `10` | 允许迟交时的宽限分钟数 |
| `IDEMPOTENCY_TTL_SECONDS` | `86400` | `Idempotency-Key` 结果缓存时长 |
| `SCORE_IMPORT_ASYNC_THRESHOLD` | `500` | 导入行数超过则转异步任务 |
| `AI_PROVIDER` | `none` | `none` 时不伪造 AI 分数，主观题保持待人工评分 |
| `AI_BASE_URL` / `AI_TIMEOUT_SECONDS` | 空 / `20` | AI 服务地址与超时 |
| `RESOURCE_ALLOWED_HOSTS` | 空 | 试卷材料下载允许回源的域名（防 SSRF） |
| `MEDIA_ROOT` / `CERTIFICATE_ROOT` | `backend/media`、`media/certificates` | 上传与证书文件目录 |
| `LOG_LEVEL` | `INFO` | 日志级别 |

多进程部署时 **必须配置 Redis**：JWT 黑名单、幂等缓存、导入任务状态都依赖共享缓存。

---

## 4. 接口清单（36 个）

权限说明：`学生`=student；`教师/管理员`=teacher + school/district/city/province_admin；`全部角色`=上两者并集。所有接口均需 `Authorization: Bearer <token>`。

### 4.1 试卷 PAP-01 ~ PAP-10

| 编号 | 方法 | 路径 | 说明 | 权限 |
| --- | --- | --- | --- | --- |
| PAP-01 | GET | `/api/v1/papers` | 试卷列表（分页、学科/类型/状态/关键词筛选） | 教师/管理员 |
| PAP-02 | POST | `/api/v1/papers/manual` | 手动组卷 | 教师/管理员 |
| PAP-03 | POST | `/api/v1/papers/auto` | 按题型/难度规则自动组卷，题目不足返回 422 | 教师/管理员 |
| PAP-04 | GET | `/api/v1/papers/{paperId}` | 试卷详情（含题目快照） | 教师/管理员 |
| PAP-05 | PATCH | `/api/v1/papers/{paperId}` | 修改试卷（已发布测评引用的试卷不可改题） | 教师/管理员 |
| PAP-06 | PATCH | `/api/v1/papers/{paperId}/draft` | 暂存试卷（允许空题目） | 教师/管理员 |
| PAP-07 | DELETE | `/api/v1/papers/{paperId}` | 删除试卷（被测评引用返回 409） | 教师/管理员 |
| PAP-08 | GET | `/api/v1/papers/{paperId}/materials/download` | 打包下载音频/图片材料（ZIP） | 教师/管理员 |
| PAP-09 | GET | `/api/v1/papers/{paperId}/answers/download` | 下载答案与解析（PDF/DOCX） | 教师/管理员 |
| PAP-10 | POST | `/api/v1/papers/practice/random` | 学生随机练习组卷，直接生成答卷 | 学生 |

### 4.2 测评 ASM-01 ~ ASM-04

| 编号 | 方法 | 路径 | 说明 | 权限 |
| --- | --- | --- | --- | --- |
| ASM-01 | GET | `/api/v1/assessments` | 测评列表（按数据范围过滤） | 全部角色 |
| ASM-02 | POST | `/api/v1/assessments` | 发布测评（支持 `Idempotency-Key`） | 教师/管理员 |
| ASM-03 | GET | `/api/v1/assessments/{assessmentId}` | 测评详情 | 全部角色 |
| ASM-04 | POST | `/api/v1/assessments/{assessmentId}/withdraw` | 撤回测评，同时自动交卷未提交答卷 | 教师/管理员 |

### 4.3 答卷 ATT-01 ~ ATT-04

| 编号 | 方法 | 路径 | 说明 | 权限 |
| --- | --- | --- | --- | --- |
| ATT-01 | POST | `/api/v1/assessments/{assessmentId}/attempts` | 开始或继续答题（校验发布范围、时间窗、次数） | 学生 |
| ATT-02 | GET | `/api/v1/attempts/{attemptId}` | 答卷详情，**不含答案/解析/评分标准** | 学生本人 |
| ATT-03 | PATCH | `/api/v1/attempts/{attemptId}/answers` | 保存答案（增量、乐观锁、截止自动交卷） | 学生本人 |
| ATT-04 | POST | `/api/v1/attempts/{attemptId}/submit` | 提交答卷并自动判客观题（幂等） | 学生本人 |

### 4.4 成绩 SCR-01 ~ SCR-09

| 编号 | 方法 | 路径 | 说明 | 权限 |
| --- | --- | --- | --- | --- |
| SCR-01 | GET | `/api/v1/scores/me` | 本人成绩 | 学生 |
| SCR-02 | GET | `/api/v1/scores` | 成绩列表（班级/学校/区域范围） | 教师/管理员 |
| SCR-03 | GET | `/api/v1/scores/statistics` | 统计概览（平均/最高/最低/及格率/优秀率/分布） | 教师/管理员 |
| SCR-04 | GET | `/api/v1/scores/statistics/list` | 分维度统计列表与排名 | 教师/管理员 |
| SCR-05 | GET | `/api/v1/scores/{scoreId}` | 成绩详情（答案可见性由 `showAnswerMode` 控制） | 全部角色（按范围） |
| SCR-06 | POST | `/api/v1/scores/manual` | 线下成绩补录（重复需 `overwrite`） | 教师/管理员 |
| SCR-07 | POST | `/api/v1/scores/import` | CSV/XLSX 批量导入线下成绩（超阈值异步） | 教师/管理员 |
| SCR-08 | POST | `/api/v1/scores/{scoreId}/regrade` | 重新判分（重算客观题，可触发 AI 复核） | 教师/管理员 |
| SCR-09 | GET | `/api/v1/scores/statistics/export` | 导出统计 XLSX | 教师/管理员 |

### 4.5 人工评分 GRD-01 ~ GRD-03

| 编号 | 方法 | 路径 | 说明 | 权限 |
| --- | --- | --- | --- | --- |
| GRD-01 | GET | `/api/v1/grading/tasks` | 待人工评分任务（教师限任教班级，校级限本校） | 教师/学校管理员 |
| GRD-02 | GET | `/api/v1/grading/attempts/{attemptId}` | 评分详情（含参考答案、评分标准） | 教师/学校管理员 |
| GRD-03 | PATCH | `/api/v1/grading/attempts/{attemptId}/scores` | 提交逐题评分，可终评 | 教师/学校管理员 |

### 4.6 证书 CRT-01 ~ CRT-04

| 编号 | 方法 | 路径 | 说明 | 权限 |
| --- | --- | --- | --- | --- |
| CRT-01 | POST | `/api/v1/certificates/generate` | 生成证书（默认跳过已生成，`forceRegenerate` 覆盖） | 教师/管理员 |
| CRT-02 | GET | `/api/v1/certificates` | 证书列表（学生仅本人） | 全部角色（按范围） |
| CRT-03 | GET | `/api/v1/certificates/{certificateId}` | 证书详情 | 全部角色（按范围） |
| CRT-04 | GET | `/api/v1/certificates/{certificateId}/download` | 下载 PDF 证书 | 全部角色（按范围） |

### 4.7 成长与报告 GRW-01 ~ GRW-02

| 编号 | 方法 | 路径 | 说明 | 权限 |
| --- | --- | --- | --- | --- |
| GRW-01 | GET | `/api/v1/students/{studentId}/growth-curve` | 历史成绩趋势（按学科，含汇总） | 全部角色（按范围） |
| GRW-02 | GET | `/api/v1/students/{studentId}/learning-report` | 学情报告读取 | 全部角色（按范围） |

---

## 5. 关键业务规则

### 5.1 快照与可追溯

- 组卷时写入 `PaperQuestion`（题目内容、分值、顺序、分区快照）。
- 发布测评时固化 `Assessment.question_snapshot`；试卷后续修改不影响已发布测评。
- 开始答题时固化 `Attempt.questions_snapshot`，并生成逐题 `AttemptAnswer`。
- 提交、评分、重新判分都写 `GradingLog` + `AuditLog`，成绩可追溯到操作人、原因、前后值。

### 5.2 答案隔离

- 学生侧接口（ATT-01/02/03、SCR-01/05）绝不返回 `answer`、`analysis`、`rubric`。
- 成绩详情按测评 `showAnswerMode` 控制：`never` / `after_submit`（已交卷可见）/ `after_end`（测评结束后可见）。
- 人工评分接口仅教师/学校管理员可访问，且限制在任教班级/本校。

### 5.3 幂等、重复提交与超时

- 提交答卷：已提交的答卷再次提交直接返回当前结果，不重复判分。
- 发布、撤回、补录、导入、生成证书支持 `Idempotency-Key` 请求头；同 key 的重复请求返回首次结果。
- 截止时间后：读取/保存答案触发服务端自动交卷；主动提交按规则拒绝（409），仅当 `allowLateSubmit=true` 且在 `LATE_SUBMIT_GRACE_MINUTES` 宽限内允许。
- 后台任务每分钟扫描过期答卷，避免学生不刷新页面导致长期未交卷。

### 5.4 判分规则

| 题型 | 自动判分 |
| --- | --- |
| 单选 / 听力 | 选项完全一致 |
| 多选 | 集合相等（多选、少选均不得分） |
| 判断 | 兼容 `true/false`、`"对"/"错"`、`1/0` 等写法 |
| 填空 | 按空位逐一比对，支持多答案写法，得部分分 |
| 主观/作品 | `manual` 人工评分；`ai` 在配置 AI 服务后给出建议分，最终以人工确认为准 |

- 单题得分上限为题目分值；终评前必须完成全部主观题评分，否则 422。
- 终评后修改需走“重新判分”，重新判分重算客观题并保留已确认的主观/AI 分数。
- 排名使用竞赛排名（1, 1, 3），覆盖在线、人工补录、导入三类成绩，分班级排名与年级排名。

### 5.5 统计口径

- 参考人数 = 有答卷的学生 ∪ 有成绩记录的学生（人工/导入也算）。
- 已提交人数 = 已交卷/已评分的答卷 ∪ 有成绩记录的学生。
- 统计维度：测评、班级、学校、区县、城市、省；指标含平均分、最高/最低分、及格率、优秀率、分数段分布。
- 导出为 XLSX，字段与列表接口一致。

### 5.6 证书

- 证书编号：`YS{年份}-{学科}-{6位序号}`，数据库唯一约束。
- 状态：`generating` → `ready` / `failed`；PDF 使用 reportlab + STSong-Light 中文字体。
- 下载前校验数据范围；证书文件按 `CERTIFICATE_ROOT` 落盘。

---

## 6. 与模块一 / 模块二的集成契约

本模块**不实现**登录、用户管理、题库 CRUD。以下模型为联调所需的最小字段（已在 `accounts/models.py`、`questionbank/models.py` 中提供，后端 B 可替换为正式实现，保持字段一致即可）：

### accounts.User

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | int | 用户 ID |
| `username` / `password` | — | Django 标准字段 |
| `role` | str | `student/teacher/school_admin/district_admin/city_admin/province_admin/question_admin` |
| `real_name` | str | 姓名 |
| `status` | str | `active/disabled` |
| `token_version` | int | 与 Token 内 `token_version` 比对，改密/禁用后旧 Token 失效 |
| `school` / `current_class` / `grade` / `student_no` | — | 数据范围与排名依据 |
| `province/city/district` | FK | 管理员的行政区划 |

### accounts 组织模型

`Province → City → District → School → Class`；`TeacherClass(teacher, classroom, subject)` 表示任教关系，教师数据范围由它推导。

### questionbank.Question / QuestionOption

| 字段 | 说明 |
| --- | --- |
| `type` | `single_choice/multiple_choice/true_false/fill_blank/short_answer/listening/artwork` |
| `subject` / `grade` / `difficulty` | 组卷筛选条件 |
| `stem` / `answer`(JSON) / `analysis` / `rubric` | 题干、答案、解析、评分标准 |
| `score` / `scoring_mode` | 默认分值与判分方式（`auto/ai/manual`） |
| `audio_url` / `image_urls` / `course` / `chapter` | 材料与章节筛选 |
| `QuestionOption(question, key, text, sort_order)` | 选项 |

### 鉴权约定

- Token：HS256，载荷 `{user_id, role, token_version, jti, token_type:"access", iat, exp}`，`JWT_SECRET` 与模块一共享。
- 本模块每次请求重新读库获取角色，不信任 Token 中的 `role`。
- 登出/黑名单键：`jwt:blacklist:<jti>`（Redis），本模块与模块一共用。
- 未登录/Token 失效统一 401，响应体仍为 `{code, message, data}` 信封。

---

## 7. 后台任务与运维命令

| 命令 | 说明 | 建议频率 |
| --- | --- | --- |
| `python manage.py auto_submit_attempts` | 扫描到期未交卷答卷并自动交卷 | 每 30 秒 |
| `python manage.py finish_assessments` | 结束到期测评、刷新状态 | 每 1 分钟 |
| `python manage.py process_score_imports` | 处理异步导入任务 | 每 1 分钟 |
| `python manage.py generate_certificates` | 批量生成待生成证书 | 按需 |
| `python manage.py run_scheduler` | 内置 APScheduler，一次启动上述定时任务 | 常驻进程 |
| `python manage.py seed_demo` | 初始化演示数据并打印 Token | 联调时 |

生产建议由系统计划任务（Windows 任务计划 / cron / supervisor）分别调度前四个命令；`run_scheduler` 适合单实例联调或演示环境。

---

## 8. 测试

```bash
cd backend
D:/python/python.exe manage.py test
```

当前 **73 个测试全部通过**（约 25 秒），覆盖：

- 鉴权：缺失/无效 Token、黑名单、`token_version`、禁用账号、角色越权、404 信封
- 试卷：手动/自动组卷、题目不足、暂存、已发布冲突、跨教师 403、练习组卷
- 测评：发布、可见性、快照冻结、重复发布幂等、撤回自动交卷、时间窗校验
- 答卷：答案隔离、增量保存、非法题目、客观题判分、重复提交、次数限制、超时自动交卷、迟交宽限
- 评分：任务范围、逐题评分、终评校验、版本冲突、超满分 422、重新判分、区县管理员权限
- 成绩：本人/列表范围、答案可见性、补录重复/覆盖/勾稽校验、CSV 部分成功与错误行
- 统计：参考人数口径、并列排名、维度越权、XLSX 导出、省级概览
- 证书：生成/列表/详情/PDF 下载、跳过与强制重生成、学科不匹配、跨学生 403
- 成长：曲线数据点、学情报告、缺失学科/报告 404

---

## 9. 已知边界

1. 登录、注册、用户管理、题库管理不在本模块范围，联调时由模块一/二提供；当前 `seed_demo` 可直接签发 Token。
2. `AI_PROVIDER=none` 时 AI 评分不会产生分数，主观题保持待人工评分；接入模型服务后由 `exams/services/ai.py` 统一调用。
3. 异步导入任务依赖缓存中的任务状态，生产必须配置 Redis，否则多进程间状态不共享。
4. 证书 PDF 使用 STSong-Light 内置中文字体，未引入外部字体文件；如需更精细排版可扩展 `certificate.py` 模板。
5. `db.sqlite3` 仅用于本地开发/演示；生产按第 3 节切换 MySQL。

---

## 10. 备份

本轮修改前已对后端源码做快照：

- 备份目录：`D:\claude\backups\20261021-153713\backend`
- 清单位置：`D:\claude\backups\20261021-153713\manifest.md`
- 备份范围：`backend/` 源码（排除 `__pycache__`、`*.pyc`、`db.sqlite3`、`media`），共 80 个文件。

恢复方式见清单文件。
