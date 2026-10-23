# 艺术素质测评系统 · 模块三（测评业务与成绩服务）

后端 A（万逸恒）负责的测评核心业务实现：组卷、测评发布、在线答题、自动判分、人工评分、成绩统计与排名、证书、成长曲线与学情报告。

- 技术栈：Python 3.12 / Django 5.2 / DRF 3.16 / drf-spectacular / SQLite（默认，可切 MySQL 8.0）
- 接口前缀：`/api/v1`
- 统一响应：`{"code": 200, "message": "success", "data": ...}`（`code` 与 HTTP 状态码一致）
- OpenAPI 文档：[docs/openapi.yaml](../docs/openapi.yaml)（在项目根目录用 `python manage.py runserver` 后访问 `/api/schema/swagger-ui/`）
- 本次 v2 增量变更说明：[docs/修改说明-评分规则库与教师总评.md](../docs/修改说明-评分规则库与教师总评.md)

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
    ├── rules/              # 音乐/美术模型评分规则库（YAML，1-10 级）
    ├── services/           # 业务规则：paper/assessment/attempt/grading/score/
    │                       #          statistics/ranking/certificate/growth/ai/
    │                       #          scoring_rules/total_score
    ├── views/              # 50 个接口（v1.2 36 + v2.0 3 + 评分规则 3 + 教师总评 8）
    ├── urls.py             # 路由（静态路径先于 <int:...>）
    ├── management/commands/ # 定时任务、演示数据
    └── tests/              # 106 个接口/业务测试
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

## 4. 接口清单（50 个）

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

### 4.8 通知中心 v2.0（NT-01 ~ NT-03）

| 编号 | 方法 | 路径 | 说明 | 权限 |
| --- | --- | --- | --- | --- |
| NT-01 | GET | `/api/v1/notifications` | 通知列表（`unreadOnly`/`type` 筛选，返回 `unreadCount`） | 登录用户 |
| NT-02 | PATCH | `/api/v1/notifications/{notificationId}/read` | 标记单条已读（幂等） | 通知接收人 |
| NT-03 | PATCH | `/api/v1/notifications/read-all` | 全部标记已读 | 登录用户 |

通知只由服务端事件写入，不提供公开创建接口；当前仅保留通用系统通知（`type=system`），后续可按需接入其他业务事件。

### 4.9 模型评分规则库（RL-01 ~ RL-03）

| 编号 | 方法 | 路径 | 说明 | 权限 |
| --- | --- | --- | --- | --- |
| RL-01 | GET | `/api/v1/scoring-rules` | 规则库索引（学科、类别、维度、级别） | 全部角色 |
| RL-02 | GET | `/api/v1/scoring-rules/{subject}/{category}?level=` | 单类别规则详情（维度权重、锚点、封顶、级别基线） | 全部角色 |
| RL-03 | POST | `/api/v1/scoring-rules/evaluate` | 按指标值计算规则分（供模型联调/教师核验） | 教师/管理员 |

`subject` 取值 `music` / `art`；`category` 取值见下表。`level` 为 1-10，省略时使用通用基线。规则文件位于 `exams/rules/music.yaml`、`exams/rules/art.yaml`，修改后按文件 mtime 自动生效，无需重启。

| 学科 | 类别 | 说明 |
| --- | --- | --- |
| music | `vocal` / `instrumental` / `solfege` | 声乐、器乐、视唱练耳，模型输出 0-1 指标 |
| music | `theory` | 乐理，以客观题自动判分为主，规则仅作复核参考 |
| art | `sketch` / `color` / `quick_sketch` / `calligraphy` / `children` | 素描、色彩、速写、书法、儿童画 |

### 4.10 教师总评规则（TS-01 ~ TS-08）

| 编号 | 方法 | 路径 | 说明 | 权限 |
| --- | --- | --- | --- | --- |
| TS-01 | GET | `/api/v1/total-score-rules/defaults` | 默认权重与折算方式 | 教师 |
| TS-02 | GET | `/api/v1/total-score-rules` | 我的总评规则列表（学科/班级/学期/状态筛选） | 教师本人 |
| TS-03 | POST | `/api/v1/total-score-rules` | 新建总评规则 | 教师本人 |
| TS-04 | GET | `/api/v1/total-score-rules/{ruleId}` | 规则详情 | 规则创建人 |
| TS-05 | PATCH | `/api/v1/total-score-rules/{ruleId}` | 修改权重/折线/聚合方式（版本 +1） | 规则创建人 |
| TS-06 | DELETE | `/api/v1/total-score-rules/{ruleId}` | 归档规则（幂等） | 规则创建人 |
| TS-07 | POST | `/api/v1/total-score-rules/{ruleId}/publish` | 发布规则；同班同学科同学期旧规则自动归档 | 规则创建人 |
| TS-08 | GET | `/api/v1/total-score-rules/{ruleId}/results` | 按规则计算全班总评（可筛学生） | 规则创建人 |

总评由三部分构成：`usual` 平时测试（练习卷成绩）、`formal` 正式测评（正式卷成绩）、`certificate` 证书（按等级折算）。三项权重之和必须为 1，默认 `0.4 / 0.4 / 0.2`；每项可选 `average` / `latest` / `best` 聚合。成绩统一按“得分/满分”折算成 0-100，避免不同卷面满分不可比。

示例：

```json
{
  "name": "七年级音乐学期总评",
  "subject": "music",
  "classId": 3,
  "term": "2026-2027-1",
  "startDate": "2026-09-01",
  "endDate": "2027-01-20",
  "usualWeight": 0.4,
  "formalWeight": 0.4,
  "certificateWeight": 0.2,
  "usualAggregation": "average",
  "formalAggregation": "average",
  "certificateAggregation": "best",
  "certificateLevelScores": {
    "excellent": 95, "good": 85, "pass": 70, "fail": 50
  },
  "missingPolicy": "renormalize",
  "excellentLine": 90,
  "goodLine": 80,
  "passLine": 60
}
```

`missingPolicy=renormalize`：某学生没有证书/某项成绩时，从分母剔除该项权重；`zero`：缺项按 0 分计入。计算结果返回每个学生的分项得分、贡献、证据明细、等级和汇总（平均分、及格率、等级分布）。

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

### 5.7 模型评分规则库

规则库把“模型指标”翻译成“考级分”，后端保留最终计分权：

1. 规则按 `学科/类别/级别` 组织，`level` 缺省时用通用基线；每级有独立的 `excellent/good/pass` 分数线。
2. 每个维度声明 `metric`（模型输出名）、`weight`（权重和恒为 1）、`anchor`（指标值 → 得分比例的分段锚点）和 `required`。
3. 模型只需返回 `metrics`（0-1）；后端做锚点插值、加权汇总、硬性封顶（如音准 < 0.5 总分封顶 50%）。
4. 必填指标缺失时 `totalScore=null`、`needsManualReview=true`；置信度 < 0.6 同样转人工复核。
5. `POST /scoring-rules/evaluate` 与 AI 适配层共用同一套计算逻辑，避免“模型说的分”和“系统算的分”不一致。

题目可在 `answer._ruleContext` 中声明 `{category, level}`（例如 `{"category": "vocal", "level": 5}`），组卷/发布/答题快照会自动带出；未声明时按题干关键词推断，仍无法判断则把整科规则下发给模型自行选择类别。

> 标准说明：本规则库是“社会艺术水平考级”1-10 级的**通用评分基线**，不是任何考级机构的官方大纲。上线前应按实际选用的机构大纲校准 `weights`、`anchors`、`bandCutoffs`，并在教研侧完成抽样复评。

### 5.8 教师总评规则

- 总评 = `平时测试 × usualWeight + 正式测评 × formalWeight + 证书 × certificateWeight`，三项权重之和必须为 1。
- 平时/正式成绩只统计状态为 `graded` 的成绩，按 `Score.total_score / Score.max_score` 折算成 0-100 后聚合；聚合方式按项独立配置。
- 证书只统计 `ready` 状态，按 `certificateLevelScores` 将等级映射成分数；同一学生多张证书按 `best/average/latest` 聚合。
- `startDate/endDate` 按成绩记录创建时间、证书发证日期过滤，用于限定学期。
- 缺项策略默认 `renormalize`，避免没有证书的学生被直接扣掉 20 分；需要严格口径时改为 `zero`。
- 发布后同教师、同班级、同学科、同学期只保留一条 `published` 规则，旧规则自动归档；规则每次修改 `version + 1`，便于追溯。
- 总评计算不落库，按当前规则实时计算，避免规则调整后历史结果不一致；如后续需要归档成绩，可在此基础上增加快照表。

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

当前 **106 个测试全部通过**（约 56 秒），覆盖：

- 鉴权：缺失/无效 Token、黑名单、`token_version`、禁用账号、角色越权、404 信封
- 试卷：手动/自动组卷、题目不足、暂存、已发布冲突、跨教师 403、练习组卷
- 测评：发布、可见性、快照冻结、重复发布幂等、撤回自动交卷、时间窗校验
- 答卷：答案隔离、增量保存、非法题目、客观题判分、重复提交、次数限制、超时自动交卷、迟交宽限
- 评分：任务范围、逐题评分、终评校验、版本冲突、超满分 422、重新判分、区县管理员权限
- 成绩：本人/列表范围、答案可见性、补录重复/覆盖/勾稽校验、CSV 部分成功与错误行
- 统计：参考人数口径、并列排名、维度越权、XLSX 导出、省级概览
- 证书：生成/列表/详情/PDF 下载、跳过与强制重生成、学科不匹配、跨学生 403
- 成长：曲线数据点、学情报告、缺失学科/报告 404
- v2.0 通知：列表与未读数、单条/全部已读、重复已读幂等、跨用户 404
- 评分规则库：规则加载与权重校验、索引/详情/级别基线、类别不存在 404、级别越界 400、教师/学生权限、缺项转人工、封顶生效、同分不同级、低置信度复核、AI 适配层注入规则与指标覆盖原始分
- 教师总评：默认权重、权重和校验、任教班级校验、仅本人可读写、发布归档旧规则、版本递增、总评加权计算、缺项折算/按 0 分、最高分/最近一次聚合、自定义分数线、证书等级映射、学生筛选

---

## 9. 已知边界

1. 登录、注册、用户管理、题库管理不在本模块范围，联调时由模块一/二提供；当前 `seed_demo` 可直接签发 Token。
2. `AI_PROVIDER=none` 时 AI 评分不会产生分数，主观题保持待人工评分；接入模型服务后由 `exams/services/ai.py` 统一调用。
3. 异步导入任务依赖缓存中的任务状态，生产必须配置 Redis，否则多进程间状态不共享。
4. 证书 PDF 使用 STSong-Light 内置中文字体，未引入外部字体文件；如需更精细排版可扩展 `certificate.py` 模板。
5. `db.sqlite3` 仅用于本地开发/演示；生产按第 3 节切换 MySQL。
6. 评分规则库是通用考级基线，不含各机构曲目/命题范围；上线前需教研按选用机构大纲校准，并用真实样本做一致性复评。
7. 模型服务需按 `scoringRules.outputSchema` 返回 `category/level/confidence/metrics`；只返回总分时后端无法套用规则，仍以模型分为建议值。
8. 教师总评按当前规则实时计算，不保存历史快照；修改规则后重新查询会得到新结果。如需“发布即冻结”，应在 `publish` 时另存结果快照。
9. 总评只聚合状态为 `graded` 的成绩和 `ready` 的证书；生成中/失败证书不计入，未完成评分的答卷也不计入。

---

## 10. 备份

本轮修改前已对后端源码做快照：

- 备份目录：`D:\claude\backups\20261021-153713\backend`
- 清单位置：`D:\claude\backups\20261021-153713\manifest.md`
- 备份范围：`backend/` 源码（排除 `__pycache__`、`*.pyc`、`db.sqlite3`、`media`），共 80 个文件。

恢复方式见清单文件。
