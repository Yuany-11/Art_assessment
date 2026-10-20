# 艺术素质测评系统 API 接口与前端技术文档

> 版本：v1.1.0  
> 基础路径：`/api/v1`  
> 后端技术栈：Python 3.11 + FastAPI + Pydantic v2 + SQLAlchemy 2.0 + Alembic + MySQL 8.0 + Redis 7 + APScheduler + RQ + MinIO  
> 前端技术栈：Vue 3 + TypeScript + Vite + Pinia + Element Plus + Vant（详见第 8 章）  
> 运行方式：Nginx + Uvicorn，Docker Compose 编排  
> 文档更新时间：2026-10-20  
> 维护分工：模块一、模块二（后端 B 柴国继）；模块三（后端 A 万逸恒）；模块四（模型 A 赖轩、模型 B 张馨月）  
> 资料依据：`人员安排.xlsx` 中的团队分工、7 天排期与 268 项功能验收清单

## 目录

- [1. 全局规范](#1-全局规范)
- [2. 模块一：账号与权限](#2-模块一账号与权限)
- [3. 模块二：题库管理](#3-模块二题库管理)
- [4. 模块三：测评核心业务](#4-模块三测评核心业务)
- [5. 模块四：AI 模型接口](#5-模块四ai-模型接口)
- [6. 前端页面与接口速查](#6-前端页面与接口速查)
- [7. 前后端联调与实现约定](#7-前后端联调与实现约定)
- [8. 前端技术方案](#8-前端技术方案)
- [附录 A：268 项功能与接口映射](#附录-a268-项功能与接口映射)

## 1. 全局规范

### 1.0 技术基线

本项目的技术基线不是“可选建议”，而是 7 天排期内前后端、模型、测试和部署共同依赖的约束。未列出的技术不得在开发中临时替换；确需替换时，必须同步更新本文档和 `docker-compose.yml`。

| 层次 | 选型 | 版本/配置 | 使用边界 |
|---|---|---|---|
| 语言 | Python | 3.11 | 后端、定时任务、RQ Worker 共用同一镜像 |
| Web 框架 | FastAPI | 0.115+ | 同步路由为主，AI/文件等长任务进入 RQ；统一异常处理与 OpenAPI |
| 数据校验 | Pydantic | 2.x | 请求/响应模型；禁止裸 `dict` 作为接口出入参 |
| ORM | SQLAlchemy | 2.0 | 同步 Session + `select()` 风格；事务边界在 Service 层 |
| 迁移 | Alembic | 当前稳定版 | 所有表结构变更必须提交迁移脚本，禁止启动时 `create_all()` |
| 数据库 | MySQL | 8.0 | `utf8mb4` / `utf8mb4_0900_ai_ci`；连接参数固定 `time_zone='+08:00'` |
| 数据库驱动 | PyMySQL | 1.1+ | 同步驱动，配合 SQLAlchemy 2.0；连接池 `pool_pre_ping=True` |
| 缓存/状态 | Redis | 7.x | Token 黑名单、Refresh Token 轮换、幂等键、统计缓存、分布式锁 |
| 定时任务 | APScheduler | 3.x | 自动交卷、测评结束、证书补偿；单实例部署，使用 Redis 锁防重复执行 |
| 任务队列 | RQ | 当前稳定版 | 导入解析、证书生成、AI 批量评分；任务状态写 Redis，前端轮询业务接口 |
| 文件存储 | MinIO | 当前稳定版 | 私有 Bucket；S3 兼容；通过预签名 URL 或后端代理下载 |
| 反向代理 | Nginx | 1.24+ | TLS、静态资源、`/api` 反代、上传大小限制、gzip |
| 应用服务器 | Uvicorn | 当前稳定版 | 单容器 2 个 Worker；调度器单独进程，避免多 Worker 重复触发 |
| 容器编排 | Docker Compose | 2.x | `api`、`worker`、`scheduler`、`mysql`、`redis`、`minio`、`nginx` |
| 前端 | Vue 3 + TypeScript + Vite | Vue 3.5+ / TS 5.x / Vite 7.x | 学生 H5 与管理控制台双应用 |
| 前端状态/路由 | Pinia + Vue Router | Pinia 3.x / Router 4.x | 登录态、权限、菜单、答题草稿 |
| 前端 UI | Element Plus + Vant | Element Plus 2.x / Vant 4.x | 管理端桌面表格；学生端移动表单 |
| 图表/音频 | ECharts + Howler.js + Wavesurfer.js | 当前稳定版 | 统计图表、音频播放、波形与错误点 |

关键运行约束：

1. **时区统一**：MySQL 连接、应用进程、容器、日志统一 `Asia/Shanghai`；数据库存 `DATETIME(3)`，接口输出 `+08:00`。
2. **令牌存储**：Access Token 30 分钟，Refresh Token 7 天；Refresh Token 每次刷新轮换，旧 Token 立即加入 Redis 黑名单。
3. **幂等存储**：`Idempotency-Key` 与响应摘要写入 Redis，TTL 24 小时；交卷、导入、补录、证书生成必须使用。
4. **任务边界**：请求线程内只做校验和落库；超过 3 秒的 AI、PDF、批量导入进入 RQ，接口返回 `taskId`。
5. **调度边界**：APScheduler 只负责“扫描到期对象并投递 RQ 任务”，不在调度进程内执行长任务。
6. **文件边界**：Bucket 不公开；数据库只存对象 Key，不存公网 URL；下载时生成 5 分钟签名 URL。
7. **配置边界**：数据库、Redis、MinIO、JWT 密钥只来自环境变量；禁止写入代码、镜像或本文档。

### 1.1 基础信息

| 项目 | 说明 |
|---|---|
| 接口风格 | RESTful |
| 基础路径 | `/api/v1`，例如 `https://api.example.com/api/v1` |
| 请求编码 | UTF-8 |
| 请求体格式 | 除文件上传、文件下载外，统一使用 `application/json` |
| 时间格式 | ISO 8601，带时区，例如 `2026-10-20T09:30:00+08:00` |
| 日期格式 | `YYYY-MM-DD`，例如 `2026-10-20` |
| 时区 | Asia/Shanghai（UTC+8） |
| 分数精度 | 保留 2 位小数 |
| 字段命名 | 小驼峰 `camelCase` |
| 接口版本 | 通过 URL 中的 `/v1` 控制，不兼容变更升级为 `/v2` |

### 1.2 统一响应格式

所有 JSON 接口统一返回以下结构：

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| code | number | 业务状态码，与 HTTP 状态码保持一致 |
| message | string | 结果说明；成功固定为 `success`，失败为可读错误信息 |
| data | object / array / null | 业务数据；失败时为 `null` |

成功示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 1001,
    "name": "七年级（1）班"
  }
}
```

失败示例：

```json
{
  "code": 403,
  "message": "无权访问该班级数据",
  "data": null
}
```

> 文件下载接口是唯一例外：成功时直接返回二进制文件流，不使用 JSON 包装；失败时仍返回上述 JSON 错误结构。

### 1.3 错误码

| code | HTTP 状态 | 含义 | 典型场景 |
|---|---|---|---|
| 200 | 200 | 成功 | 查询、创建、修改、删除成功 |
| 400 | 400 | 参数错误 | 缺少必填项、类型错误、分数超出范围、可空字段传空字符串 |
| 401 | 401 | 未登录或登录失效 | 未携带 Token、Access Token 过期、Token 被注销 |
| 403 | 403 | 无权限 | 角色不允许、越级访问、超出数据范围 |
| 404 | 404 | 资源不存在 | 账号、班级、试卷、测评、答卷、成绩、证书不存在 |
| 409 | 409 | 资源状态冲突 | 重复创建、重复交卷、并发修改、唯一键冲突 |
| 422 | 422 | 语义校验失败 | 路径参数类型正确但业务语义不成立；响应仍使用统一 JSON |
| 500 | 500 | 服务器错误 | 未捕获异常、数据库故障、AI 服务不可用且无降级结果 |

约定：

- **资源不存在统一返回 `404`**，不得用 `400` 代替；列表查询无结果返回 `200` + 空数组。
- **重复创建、重复提交、状态冲突返回 `409`**；交卷接口对同一答卷重复调用属于幂等成功，不返回 409。
- FastAPI 默认的请求体校验错误 `422` 必须由全局异常处理器转换为 `400`，并保留字段级错误；`422` 仅用于业务语义校验失败。
- 表单字段错误时，`message` 返回可读摘要，`data.errors` 返回逐字段错误：`{"errors": {"field": "错误说明"}}`。
- 不向前端暴露堆栈、SQL、内部服务地址等敏感信息。
- 所有异常必须经过全局异常处理器输出 `{code,message,data}`，禁止 FastAPI 默认的纯文本 `Internal Server Error` 或裸 `{"detail": ...}`。

### 1.4 鉴权规范

除登录接口外，所有接口必须携带请求头：

```http
Authorization: Bearer <token>
Content-Type: application/json
```

鉴权规则：

1. 后端使用 JWT 解析用户身份，并校验令牌有效期、签名、`jti` 是否在 Redis 黑名单中。
2. Access Token 有效期 **30 分钟**，Refresh Token 有效期 **7 天**；Refresh Token 每次刷新后轮换，旧 Refresh Token 立即失效。
3. 答题、自动保存、交卷遇到 Access Token 过期时，前端必须使用 Refresh Token 静默刷新并重放原请求；不得因 30 分钟过期丢失答题状态。
4. 后端必须根据数据库中的用户角色和所属组织重新校验权限，不能只信任 Token 中的角色字段。
5. 角色权限校验通过后，还必须执行数据范围校验，防止越权访问其他学校、区县、市州的数据。
6. 账号被禁用、密码被管理员重置后，将该账号的 `tokenVersion` 加 1，并注销其全部 Refresh Token；已有 Access Token 在剩余有效期内也必须校验 `tokenVersion` 并拒绝。
7. 文件访问 URL 使用 5 分钟签名地址；不得通过可猜测的路径直接暴露学生材料。
8. 生产环境必须使用 HTTPS；Refresh Token 只允许通过 HTTPS 请求体传输，不得放入 URL。

### 1.5 角色枚举

| 枚举值 | 中文名称 | 典型使用端 |
|---|---|---|
| student | 学生 | 学生端 |
| teacher | 教师 | 教师端 |
| school_admin | 学校管理员 | 学校管理端 |
| district_admin | 区县管理员 | 区县管理端 |
| city_admin | 市州管理员 | 市州管理端 |
| province_admin | 省级管理员 | 省级管理端 |
| question_admin | 题库管理员 | 题库管理端 |

一个账号只能拥有一个主角色。需要额外职责时，应通过班级任课关系、班主任关系等业务关系表达，不建议在同一账号上叠加多角色。

### 1.6 数据权限规则

| 角色 | 默认数据范围 | 说明 |
|---|---|---|
| student | 本人 | 仅可访问自己的班级、测评、答卷、成绩、证书、成长数据 |
| teacher | 任教班级及本人创建的数据 | 可管理任教班级学生、组卷、发布班级测评、查看班级成绩；仅可修改本人创建且未进入审核/发布流程的题目和试卷 |
| school_admin | 本校 | 可管理本校教师、学生、班级、校级试卷、校级测评与统计 |
| district_admin | 本区县 | 可管理区县直属学校、区县账号、区县级试卷与测评、区县统计 |
| city_admin | 本市州 | 可管理市州直属学校、区县账号、市州级试卷与测评、市州统计 |
| province_admin | 全省 | 可管理市州账号、省级试卷与测评、全省统计、全省参与率 |
| question_admin | 题库全域 | 可管理课程、章节、试题、审核与题库日志；不得访问学生成绩、答卷与证书 |

通用规则：

- 上级角色可查看下级汇总数据，但“查看汇总”不等于“可修改下级业务数据”；写操作默认仅允许直接管理范围。
- 客户端传入的 `schoolId`、`districtId`、`cityId` 等组织字段只能作为筛选条件，最终范围以当前登录账号为准。
- 跨范围访问返回 `403`，不得返回目标数据是否存在。
- 教师调离班级、学生转班后，历史答卷与成绩仍保留在原班级/原测评记录中，不随关系变化而迁移。

### 1.7 分页规范

请求参数：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| pageNum | number | 否 | 1 | 页码，从 1 开始 |
| pageSize | number | 否 | 10 | 每页条数，最大 100 |

分页响应中的 `data` 固定为 `Page<T>`：

| 字段 | 类型 | 说明 |
|---|---|---|
| total | number | 总条数 |
| pages | number | 总页数，`ceil(total / pageSize)` |
| list | T[] | 当前页数据列表，元素类型由具体接口声明 |

`Page<T>` 是本文档的泛型简写，FastAPI 中必须实现为可生成 OpenAPI Schema 的泛型模型，不能只在文字里约定：

```python
from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")

class Page(BaseModel, Generic[T]):
    total: int
    pages: int
    list: list[T]
```

```ts
export interface Page<T> {
  total: number
  pages: number
  list: T[]
}
```

示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 52,
    "pages": 6,
    "list": []
  }
}
```

### 1.8 通用约定

- 所有业务主键 `id` 使用 `number` 类型；接口参数中的路径 ID 必须为正整数。
- 删除操作默认使用逻辑删除；已发布测评、已产生成绩的试卷、已生成证书不得物理删除。
- 创建类接口成功返回 `200`，不强制使用 `201`；删除成功返回 `200` 和 `data.deleted = true`。
- 提交答卷、批量导入等可能重复触发的接口支持请求头 `Idempotency-Key: <uuid>`，服务端在 Redis 中保存 24 小时，保证幂等。
- 列表接口默认按创建时间倒序，除非接口另有说明。
- **局部更新统一使用 `PATCH`**，语义为“只修改请求体中出现的字段”；省略字段 = 不修改。本文档所有更新接口均使用 `PATCH`，不提供整资源覆盖；答题答案批量保存也使用 `PATCH`，并通过版本号保证幂等。
- **空值规则**：可空字段只用 `null` 表示“无值”；空字符串 `""` 不是合法的无值表达，服务端对可空字段收到 `""` 时按 `400` 拒绝（字符串必填字段同样不得为空白）。响应中的可空字段返回 `null`，不返回 `""`；数组无元素返回 `[]`。
- 涉及金额以外的分数、比率均使用 `number`；比率范围为 `0~1`，百分数展示由前端完成。
- 下拉筛选的枚举值统一使用小写英文，展示名称由前端映射或使用接口返回的 `xxxName` 字段。
- AI 分析结果属于辅助评分，正式测评的最终成绩以教师确认或系统评分规则为准；需在业务层保留原始模型结果与人工修改痕迹。
- 文档中的响应示例用于展示字段结构；分页列表、题目数组等长列表可能只保留少量元素，实际以字段说明和接口定义为完整依据。

### 1.9 通用枚举

#### 1.9.1 学科与教学

| 枚举 | 值 | 说明 |
|---|---|---|
| subject | `music` / `art` | 音乐 / 美术 |
| grade | `1` ~ `12` | 年级，1~6 小学、7~9 初中、10~12 高中 |
| difficulty | `1` ~ `5` | 难度，1 最简单，5 最难 |
| questionType | `single_choice` / `multiple_choice` / `true_false` / `fill_blank` / `short_answer` / `listening` / `image_upload` / `audio_upload` | 单选 / 多选 / 判断 / 填空 / 简答 / 听赏 / 图片作品 / 音频作品 |
| scoringMode | `auto` / `manual` / `ai` | 自动判分 / 人工评分 / AI 辅助评分 |
| questionStatus | `draft` / `pending` / `approved` / `rejected` / `offline` | 草稿 / 待审核 / 已通过 / 已驳回 / 已下架 |
| reviewAction | `approve` / `reject` | 通过 / 驳回 |

#### 1.9.2 测评业务

| 枚举 | 值 | 说明 |
|---|---|---|
| paperType | `practice` / `formal` | 练习卷 / 正式测评卷 |
| generateMode | `manual` / `auto` | 手动组卷 / 自动随机组卷 |
| scopeType | `class` / `school` / `district` / `city` / `province` | 班级 / 学校 / 区县 / 市州 / 省 |
| paperStatus | `draft` / `ready` / `published` / `archived` | 草稿 / 已就绪 / 已用于发布 / 已归档 |
| assessmentStatus | `published` / `withdrawn` / `finished` | 已发布 / 已撤回 / 已结束 |
| attemptStatus | `in_progress` / `submitted` / `graded` / `invalid` | 答题中 / 已提交 / 已评分 / 无效 |
| submitType | `manual` / `auto` | 学生主动交卷 / 到时自动交卷 |
| gradingStatus | `pending` / `grading` / `graded` / `failed` | 待判分 / 判分中 / 已完成 / 判分失败 |
| scoreSource | `online` / `manual` / `import` | 线上测评 / 教师补录 / 线下成绩导入 |
| showAnswerMode | `never` / `after_submit` / `after_end` | 不展示 / 交卷后展示 / 测评结束后展示 |
| certificateStatus | `generating` / `ready` / `failed` | 生成中 / 可下载 / 生成失败 |
| joinRequestType | `join` / `change` / `leave` | 加入 / 转班 / 退出 |
| joinRequestStatus | `pending` / `approved` / `rejected` / `cancelled` | 待审核 / 已通过 / 已驳回 / 已取消 |

#### 1.9.3 账号与文件

| 枚举 | 值 | 说明 |
|---|---|---|
| accountStatus | `active` / `disabled` | 正常 / 禁用 |
| gender | `male` / `female` / `unknown` | 男 / 女 / 未填写 |
| fileCategory | `avatar` / `question_image` / `question_audio` / `student_work` / `certificate` / `import` / `other` | 头像 / 试题图片 / 试题音频 / 学生作品 / 证书 / 导入文件 / 其他 |
| scoreLevel | `excellent` / `good` / `pass` / `fail` | 优秀 / 良好 / 合格 / 待提升 |

### 1.10 FastAPI 实现约束

#### 1.10.1 路由注册顺序

FastAPI 按注册顺序匹配路由；静态路径必须注册在参数化路径之前，否则 `statistics`、`me`、`search`、`import` 会被当成路径 ID。后端必须按以下顺序组织 Router：

```python
# 正确：静态路径在前
router.add_api_route("/scores/me", get_my_scores, methods=["GET"])
router.add_api_route("/scores/statistics", get_statistics, methods=["GET"])
router.add_api_route("/scores/statistics/list", get_statistics_list, methods=["GET"])
router.add_api_route("/scores/statistics/export", export_statistics, methods=["GET"])
router.add_api_route("/scores/{score_id:int}", get_score, methods=["GET"])

router.add_api_route("/classes/search", search_class, methods=["GET"])
router.add_api_route("/classes/{class_id:int}", get_class, methods=["GET"])

router.add_api_route("/papers/manual", create_manual_paper, methods=["POST"])
router.add_api_route("/papers/auto", create_auto_paper, methods=["POST"])
router.add_api_route("/papers/practice/random", create_practice, methods=["POST"])
router.add_api_route("/papers/{paper_id:int}", get_paper, methods=["GET"])
```

约定：

- 路径参数统一声明为 `int`（如 `{score_id:int}`），从框架层阻止 `statistics` 被解析为 ID。
- `GET /scores/statistics`、`GET /scores/statistics/list`、`GET /scores/statistics/export` 三个静态路由必须先于 `GET /scores/{scoreId}` 注册。
- `GET /classes/search` 必须先于 `GET /classes/{classId}` 注册。
- `/papers/manual`、`/papers/auto`、`/papers/practice/random` 必须先于 `/papers/{paperId}` 注册。
- 路由顺序必须写入后端路由文件，不能只依赖本文档阅读顺序。

#### 1.10.2 全局异常与统一响应

后端必须注册以下异常处理器，保证所有响应符合 `{code,message,data}`：

| 异常 | HTTP | code | 处理 |
|---|---|---|---|
| `RequestValidationError` | 400 | 400 | 将 Pydantic 字段错误映射为 `data.errors` |
| 自定义 `BusinessError` | 对应状态 | 400/403/404/409/422 | 返回可读 `message`，不暴露内部细节 |
| `HTTPException` | 原状态 | 原状态 | 包装为统一结构 |
| `starlette.exceptions.HTTPException(404)` | 404 | 404 | 未匹配路由也返回 JSON |
| `Exception` | 500 | 500 | 记录 `requestId` 与堆栈到服务端日志，响应只返回“服务器内部错误” |

```python
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
app = FastAPI()

@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    errors = {
        ".".join(str(x) for x in e["loc"][1:]): e["msg"]
        for e in exc.errors()
    }
    return JSONResponse(
        status_code=400,
        content={"code": 400, "message": "请求参数校验失败", "data": {"errors": errors}},
    )

@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logger.exception("unhandled error request_id=%s", request_id)
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": "服务器内部错误", "data": {"requestId": request_id}},
    )
```

#### 1.10.3 数据与事务约束

- 所有响应必须声明 `response_model`，并统一包裹 `ApiResponse[T]`；文件下载接口除外。
- 创建/更新使用 Pydantic `model_config = ConfigDict(extra="forbid")`，拒绝前端传入未声明字段。
- 时间统一使用带时区 `datetime`；数据库连接执行 `SET time_zone = '+08:00'`。
- 交卷、导入、补录、证书生成在 Service 层使用显式事务；AI 调用不得持有数据库事务。
- 统计查询使用只读事务或独立只读连接，避免长查询阻塞写入。
- 逻辑删除统一使用 `deleted_at`；唯一键冲突转换为 `409`，不直接抛出数据库异常。

## 2. 模块一：账号与权限

> 后端负责人：柴国继（后端 B）  
> 覆盖：登录认证、当前用户、多级账号、班级、学生批量导入、通用文件上传。

### 2.1 数据模型

#### UserProfile（当前用户信息）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | number | 用户 ID |
| username | string | 登录账号 |
| realName | string | 真实姓名 |
| role | string | 角色枚举 |
| roleName | string | 角色中文名 |
| permissions | array<string> | 权限码列表，如 `question.review`、`score.import`、`grading.submit`；前端按钮级权限使用 |
| avatarUrl | string / null | 头像地址；无头像时为 `null` |
| gender | string | `male` / `female` / `unknown` |
| phone | string / null | 手机号；未填写时为 `null` |
| email | string / null | 邮箱；未填写时为 `null` |
| studentNo | string / null | 学籍号，仅学生 |
| teacherNo | string / null | 教师工号，仅教师 |
| schoolId | number / null | 学校 ID |
| schoolName | string / null | 学校名称 |
| districtId | number / null | 区县 ID |
| districtName | string / null | 区县名称 |
| cityId | number / null | 市州 ID |
| cityName | string / null | 市州名称 |
| grade | number / null | 年级，仅学生 |
| classId | number / null | 当前班级 ID，仅学生 |
| className | string / null | 当前班级名称，仅学生 |
| status | string | `active` / `disabled` |
| lastLoginAt | string | 最后登录时间 |
| createdAt | string | 创建时间 |

#### MenuItem（角色菜单）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 菜单编码，如 `teacher.papers` |
| parentId | string / null | 父菜单编码；顶级为 `null` |
| name | string | 菜单名称 |
| path | string | 前端路由路径 |
| icon | string / null | 图标名称；无图标为 `null` |
| sortOrder | number | 排序值，升序 |
| permission | string / null | 访问该菜单所需权限码；仅做展示控制，后端仍需鉴权 |
| children | array<MenuItem> | 子菜单；无子菜单为 `[]` |

#### AccountItem（账号列表项）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | number | 账号 ID |
| username | string | 登录账号 |
| realName | string | 姓名 |
| role | string | 角色枚举 |
| roleName | string | 角色中文名 |
| orgId | number | 所属组织 ID（学校/区县/市州/省） |
| orgName | string | 所属组织名称 |
| phone | string / null | 手机号；未填写时为 `null` |
| email | string / null | 邮箱；未填写时为 `null` |
| subject | string / null | 任教学科，仅教师 |
| title | string / null | 职称，仅教师 |
| studentNo | string / null | 学籍号，仅学生 |
| classId | number / null | 班级 ID，仅学生 |
| className | string / null | 班级名称，仅学生 |
| status | string | `active` / `disabled` |
| createdAt | string | 创建时间 |

#### OrgCreateResult（组织创建结果）

| 字段 | 类型 | 说明 |
|---|---|---|
| orgId | number | 新建学校/区县/市州的组织 ID |
| orgName | string | 组织名称 |
| adminAccount | AccountItem | 同时创建的管理员账号 |

#### StudentItem（班级学生）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | number | 学生账号 ID |
| username | string | 登录账号 |
| studentNo | string | 学籍号 |
| realName | string | 姓名 |
| gender | string | 性别枚举 |
| grade | number | 年级 |
| classId | number | 班级 ID |
| className | string | 班级名称 |
| status | string | 账号状态 |
| joinedAt | string | 加入班级时间 |

#### ClassItem（班级列表项）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | number | 班级 ID |
| classCode | string | 班级号，学生加入时使用 |
| name | string | 班级名称 |
| grade | number | 年级 |
| schoolId | number | 学校 ID |
| schoolName | string | 学校名称 |
| headTeacherId | number / null | 班主任账号 ID |
| headTeacherName | string / null | 班主任姓名 |
| studentCount | number | 学生人数 |
| status | string | `active` / `archived` |
| createdAt | string | 创建时间 |

#### ClassDetail（班级详情）

包含 `ClassItem` 全部字段，并增加：

| 字段 | 类型 | 说明 |
|---|---|---|
| description | string / null | 班级简介；未填写时为 `null` |
| subjectTeachers | array | 科任教师列表，元素为 `{id:number, realName:string, subject:string}` |
| createdBy | number | 创建人 ID |
| updatedAt | string | 更新时间 |

#### JoinRequestItem（班级申请）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | number | 申请 ID |
| classId | number | 目标班级 ID |
| className | string | 目标班级名称 |
| requesterId | number | 申请人 ID |
| requesterName | string | 申请人姓名 |
| requesterRole | string | `student` / `teacher` |
| type | string | `join` / `change` / `leave` |
| targetClassId | number / null | 转班时的目标班级 ID |
| targetClassName | string / null | 转班时的目标班级名称 |
| status | string | 申请状态 |
| reason | string | 申请理由 |
| reviewerId | number / null | 审核人 ID |
| reviewerName | string / null | 审核人姓名 |
| reviewComment | string / null | 审核意见；未审核或未填写时为 `null` |
| reviewedAt | string / null | 审核时间 |
| createdAt | string | 申请时间 |

#### FileObject（文件对象）

| 字段 | 类型 | 说明 |
|---|---|---|
| fileId | number | 文件 ID |
| url | string | 可访问地址 |
| name | string | 原始文件名 |
| mimeType | string | MIME 类型 |
| size | number | 文件字节数 |
| category | string | 文件分类枚举 |
| createdAt | string | 上传时间 |

#### ImportResult（导入结果）

| 字段 | 类型 | 说明 |
|---|---|---|
| total | number | 总行数 |
| successCount | number | 成功条数 |
| failCount | number | 失败条数 |
| errors | array | 失败明细，元素为 `{row:number, studentNo:string, message:string}` |

### 2.2 登录认证

#### 2.2.1 用户登录

**接口**：`POST /api/v1/auth/login`  
**权限**：公开（无需登录）  
**Content-Type**：`application/json`  
**说明**：账号密码登录，成功后返回访问令牌与用户信息。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| username | body | string | 是 | 登录账号或学籍号 |
| password | body | string | 是 | 密码，明文仅用于本次传输，必须 HTTPS |
| role | body | string | 否 | 期望登录角色；传入时必须与账号角色一致，避免登录到错误端口 |

请求示例：

```json
{
  "username": "teacher1001",
  "password": "Abc@123456",
  "role": "teacher"
}
```

**响应数据（data）**

| 字段 | 类型 | 说明 |
|---|---|---|
| token | string | Access Token，有效期 30 分钟 |
| refreshToken | string | Refresh Token，有效期 7 天；每次刷新后轮换 |
| tokenType | string | 固定为 `Bearer` |
| expiresIn | number | Access Token 有效期，固定 `1800` 秒 |
| refreshExpiresIn | number | Refresh Token 有效期，固定 `604800` 秒 |
| user | UserProfile | 当前用户信息，含 `permissions` |

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refreshToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...refresh...",
    "tokenType": "Bearer",
    "expiresIn": 1800,
    "refreshExpiresIn": 604800,
    "user": {
      "id": 2001,
      "username": "teacher1001",
      "realName": "李老师",
      "role": "teacher",
      "roleName": "教师",
      "permissions": ["paper.create", "assessment.publish", "score.view", "grading.submit"],
      "avatarUrl": "https://cdn.example.com/avatar/2001.jpg",
      "gender": "female",
      "phone": "13800000001",
      "email": "teacher1001@example.com",
      "studentNo": null,
      "teacherNo": "T1001",
      "schoolId": 301,
      "schoolName": "示范中学",
      "districtId": 22,
      "districtName": "示例区",
      "cityId": 3,
      "cityName": "示例市",
      "grade": null,
      "classId": null,
      "className": null,
      "status": "active",
      "lastLoginAt": "2026-10-20T09:30:00+08:00",
      "createdAt": "2026-09-01T10:00:00+08:00"
    }
  }
}
```

#### 2.2.2 刷新访问令牌

**接口**：`POST /api/v1/auth/refresh`  
**权限**：公开（需有效 Refresh Token）  
**说明**：Access Token 过期前或收到 `401 TOKEN_EXPIRED` 时调用。服务端校验 Refresh Token 的签名、有效期、`jti` 黑名单和 `tokenVersion`，签发新的 Access Token 与 Refresh Token，并将旧 Refresh Token 加入 Redis 黑名单。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| refreshToken | body | string | 是 | 登录或上次刷新返回的 Refresh Token |

请求示例：

```json
{
  "refreshToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...refresh..."
}
```

**响应数据（data）**

| 字段 | 类型 | 说明 |
|---|---|---|
| token | string | 新的 Access Token |
| refreshToken | string | 轮换后的 Refresh Token |
| tokenType | string | 固定 `Bearer` |
| expiresIn | number | 新 Access Token 有效期，`1800` 秒 |
| refreshExpiresIn | number | 新 Refresh Token 有效期，`604800` 秒 |

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...new...",
    "refreshToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...rotated...",
    "tokenType": "Bearer",
    "expiresIn": 1800,
    "refreshExpiresIn": 604800
  }
}
```

刷新失败统一返回：

```json
{
  "code": 401,
  "message": "登录状态已失效，请重新登录",
  "data": null
}
```

#### 2.2.3 退出登录

**接口**：`POST /api/v1/auth/logout`  
**权限**：[student, teacher, school_admin, district_admin, city_admin, province_admin, question_admin]  
**说明**：注销当前 Access Token；若传入 Refresh Token，则同时注销该 Refresh Token。前端随后清除本地令牌并跳转登录页。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| refreshToken | body | string | 否 | 需要同时注销的 Refresh Token；不传则只注销当前 Access Token |

请求示例：

```json
{
  "refreshToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...refresh..."
}
```

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "loggedOut": true
  }
}
```

#### 2.2.4 获取当前用户信息

**接口**：`GET /api/v1/auth/me`  
**权限**：[student, teacher, school_admin, district_admin, city_admin, province_admin, question_admin]  
**说明**：登录后加载用户资料、权限码和所属组织信息；角色菜单由 `GET /auth/menus` 单独加载。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| 无 | - | - | - | 从 token 获取当前用户 |

**响应数据（data）**：`UserProfile`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 1001,
    "username": "student2026001",
    "realName": "王小明",
    "role": "student",
    "roleName": "学生",
    "permissions": ["assessment.attempt", "score.self.view", "certificate.self.view"],
    "avatarUrl": null,
    "gender": "male",
    "phone": "13900000001",
    "email": null,
    "studentNo": "S20260001",
    "teacherNo": null,
    "schoolId": 301,
    "schoolName": "示范中学",
    "districtId": 22,
    "districtName": "示例区",
    "cityId": 3,
    "cityName": "示例市",
    "grade": 7,
    "classId": 5001,
    "className": "七年级（1）班",
    "status": "active",
    "lastLoginAt": "2026-10-20T08:00:00+08:00",
    "createdAt": "2026-09-01T10:00:00+08:00"
  }
}
```

#### 2.2.5 修改个人信息

**接口**：`PATCH /api/v1/auth/me`  
**权限**：[student, teacher, school_admin, district_admin, city_admin, province_admin, question_admin]  
**说明**：当前用户修改本人可编辑资料；只修改请求体中出现的字段。角色、组织、学籍号等关键字段不可自行修改。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| realName | body | string | 否 | 姓名，2~30 字 |
| gender | body | string | 否 | `male` / `female` / `unknown` |
| phone | body | string | 否 | 手机号 |
| email | body | string | 否 | 邮箱 |
| avatarUrl | body | string | 否 | 头像地址，建议使用 `/files` 上传后的 URL |

**响应数据（data）**：`UserProfile`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 2001,
    "username": "teacher1001",
    "realName": "李老师",
    "role": "teacher",
    "roleName": "教师",
    "permissions": ["paper.create", "assessment.publish", "score.view", "grading.submit"],
    "avatarUrl": "https://cdn.example.com/avatar/2001-new.jpg",
    "gender": "female",
    "phone": "13800000002",
    "email": "teacher1001@example.com",
    "studentNo": null,
    "teacherNo": "T1001",
    "schoolId": 301,
    "schoolName": "示范中学",
    "districtId": 22,
    "districtName": "示例区",
    "cityId": 3,
    "cityName": "示例市",
    "grade": null,
    "classId": null,
    "className": null,
    "status": "active",
    "lastLoginAt": "2026-10-20T09:30:00+08:00",
    "createdAt": "2026-09-01T10:00:00+08:00"
  }
}
```

#### 2.2.6 修改本人密码

**接口**：`PATCH /api/v1/auth/password`  
**权限**：[student, teacher, school_admin, district_admin, city_admin, province_admin, question_admin]  
**说明**：校验旧密码后修改本人密码；成功后 `tokenVersion` 加 1，当前所有 Access Token 与 Refresh Token 全部失效，必须重新登录。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| oldPassword | body | string | 是 | 旧密码 |
| newPassword | body | string | 是 | 新密码，8~32 位，至少包含字母和数字 |

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "changed": true,
    "reloginRequired": true
  }
}
```

#### 2.2.7 查询当前角色菜单

**接口**：`GET /api/v1/auth/menus`  
**权限**：[student, teacher, school_admin, district_admin, city_admin, province_admin, question_admin]  
**说明**：返回当前角色可见的菜单树。菜单由后端按角色和维护配置生成，前端不得硬编码；菜单隐藏不等于接口授权，后端仍需逐接口鉴权。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| 无 | - | - | - | 从当前登录用户推导角色 |

**响应数据（data）**：`MenuItem[]`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "id": "teacher.papers",
      "parentId": null,
      "name": "组卷管理",
      "path": "/teacher/papers",
      "icon": "EditPen",
      "sortOrder": 10,
      "permission": "paper.create",
      "children": []
    },
    {
      "id": "teacher.grading",
      "parentId": null,
      "name": "人工评分",
      "path": "/teacher/grading",
      "icon": "Checked",
      "sortOrder": 20,
      "permission": "grading.submit",
      "children": []
    }
  ]
}
```

### 2.3 多级账号管理

> 账号创建权限按行政层级与数据范围双重控制：学校创建本校教师和学生；区县、市州、省可管理权限范围内的学校/区县/市州账号，也可为下级学校创建学生账号（必须显式指定 `schoolId`）。上级只可管理直接和间接下级，不得修改同级或上级账号。

#### 2.3.1 查询下级账号列表

**接口**：`GET /api/v1/accounts`  
**权限**：[school_admin, district_admin, city_admin, province_admin]  
**说明**：按角色筛选并分页查询权限范围内的下级账号。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| role | query | string | 否 | 目标角色；只能查询可管理的下级角色 |
| keyword | query | string | 否 | 账号/姓名/手机号/学籍号模糊搜索 |
| status | query | string | 否 | `active` / `disabled` |
| orgId | query | number | 否 | 组织 ID 筛选，必须在当前账号数据范围内 |
| classId | query | number | 否 | 班级 ID 筛选，仅学生账号 |
| pageNum | query | number | 否 | 页码，默认 1 |
| pageSize | query | number | 否 | 每页条数，默认 10 |

**响应数据（data）**：`Page<AccountItem>`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 2,
    "pages": 1,
    "list": [
      {
        "id": 2001,
        "username": "teacher1001",
        "realName": "李老师",
        "role": "teacher",
        "roleName": "教师",
        "orgId": 301,
        "orgName": "示范中学",
        "phone": "13800000001",
        "email": "teacher1001@example.com",
        "subject": "music",
        "title": "一级教师",
        "studentNo": null,
        "classId": null,
        "className": null,
        "status": "active",
        "createdAt": "2026-09-01T10:00:00+08:00"
      },
      {
        "id": 2002,
        "username": "teacher1002",
        "realName": "赵老师",
        "role": "teacher",
        "roleName": "教师",
        "orgId": 301,
        "orgName": "示范中学",
        "phone": "13800000003",
        "email": null,
        "subject": "art",
        "title": "二级教师",
        "studentNo": null,
        "classId": null,
        "className": null,
        "status": "active",
        "createdAt": "2026-09-02T11:00:00+08:00"
      }
    ]
  }
}
```

#### 2.3.2 查询账号详情

**接口**：`GET /api/v1/accounts/{accountId}`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：查询权限范围内单个账号详情；教师仅可查看本人任教班级的学生账号，不能查看其他教师或管理员账号。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| accountId | path | number | 是 | 账号 ID |

**响应数据（data）**：`AccountItem`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 1001,
    "username": "student2026001",
    "realName": "王小明",
    "role": "student",
    "roleName": "学生",
    "orgId": 301,
    "orgName": "示范中学",
    "phone": "13900000001",
    "email": null,
    "subject": null,
    "title": null,
    "studentNo": "S20260001",
    "classId": 5001,
    "className": "七年级（1）班",
    "status": "active",
    "createdAt": "2026-09-01T10:00:00+08:00"
  }
}
```

#### 2.3.3 创建教师账号

**接口**：`POST /api/v1/accounts/teachers`  
**权限**：[school_admin]  
**说明**：学校管理员在本校创建教师账号；所属学校由登录身份推导，前端不得指定其他学校。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| username | body | string | 是 | 登录账号，校内唯一 |
| realName | body | string | 是 | 教师姓名 |
| phone | body | string | 是 | 手机号 |
| email | body | string | 否 | 邮箱 |
| subject | body | string | 是 | `music` / `art` |
| title | body | string | 否 | 职称 |
| classIds | body | array | 否 | 任教班级 ID 数组 |
| initialPassword | body | string | 否 | 初始密码；不传时由服务端生成 |
| status | body | string | 否 | 默认 `active` |

请求示例：

```json
{
  "username": "teacher1003",
  "realName": "周老师",
  "phone": "13800000004",
  "email": "teacher1003@example.com",
  "subject": "music",
  "title": "一级教师",
  "classIds": [5001, 5002],
  "initialPassword": "Art@2026",
  "status": "active"
}
```

**响应数据（data）**：`AccountItem`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 2003,
    "username": "teacher1003",
    "realName": "周老师",
    "role": "teacher",
    "roleName": "教师",
    "orgId": 301,
    "orgName": "示范中学",
    "phone": "13800000004",
    "email": "teacher1003@example.com",
    "subject": "music",
    "title": "一级教师",
    "studentNo": null,
    "classId": null,
    "className": null,
    "status": "active",
    "createdAt": "2026-10-20T10:00:00+08:00"
  }
}
```

#### 2.3.4 批量导入教师账号

**接口**：`POST /api/v1/accounts/teachers/import`  
**权限**：[school_admin]  
**Content-Type**：`multipart/form-data`  
**说明**：学校管理员通过 CSV/XLSX 批量创建本校教师账号。逐行校验，支持部分成功；超过 200 行进入 RQ 异步处理，返回 `taskId` 供轮询。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| file | formData | file | 是 | CSV/XLSX，最大 5 MB |
| defaultPassword | formData | string | 否 | 未填写初始密码时使用；不传则逐行随机生成 |
| overwrite | formData | boolean | 否 | 已存在账号是否覆盖资料，默认 `false` |

模板列：`登录账号,姓名,手机号,邮箱,任教学科,职称,班级号（多个用/分隔）,初始密码`。

**响应数据（data）**

| 字段 | 类型 | 说明 |
|---|---|---|
| taskId | string | 导入任务 ID |
| status | string | `completed` / `queued` / `failed` |
| total | number | 总行数 |
| successCount | number | 成功条数 |
| failCount | number | 失败条数 |
| errors | array | 失败明细 `{row:number,username:string,message:string}` |

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "taskId": "TIMP202610200001",
    "status": "completed",
    "total": 12,
    "successCount": 11,
    "failCount": 1,
    "errors": [
      { "row": 6, "username": "teacher1006", "message": "登录账号已存在" }
    ]
  }
}
```

#### 2.3.5 创建学生账号

**接口**：`POST /api/v1/accounts/students`  
**权限**：[school_admin, district_admin, city_admin, province_admin]  
**说明**：创建单个学生账号。学校管理员固定在本校创建；区县、市州、省管理员可在权限范围内的下级学校创建，必须显式传入 `schoolId`。批量场景优先使用班级学生批量导入接口。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| username | body | string | 是 | 登录账号，校内唯一 |
| studentNo | body | string | 是 | 学籍号，全局唯一 |
| realName | body | string | 是 | 学生姓名 |
| gender | body | string | 是 | `male` / `female` / `unknown` |
| grade | body | number | 是 | 年级，1~12 |
| schoolId | body | number | 条件必填 | 目标学校 ID；`school_admin` 不传（由登录身份推导），其他管理员必传且必须在数据范围内 |
| classId | body | number | 否 | 班级 ID；必须属于 `schoolId`，后续也可通过加入班级流程处理 |
| phone | body | string | 否 | 学生手机号；未填写时为 `null` |
| guardianPhone | body | string | 否 | 监护人手机号；未填写时为 `null` |
| initialPassword | body | string | 否 | 初始密码；不传时由服务端生成 |

**响应数据（data）**：`AccountItem`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 1002,
    "username": "student2026002",
    "realName": "陈小雨",
    "role": "student",
    "roleName": "学生",
    "orgId": 301,
    "orgName": "示范中学",
    "phone": null,
    "email": null,
    "subject": null,
    "title": null,
    "studentNo": "S20260002",
    "classId": 5001,
    "className": "七年级（1）班",
    "status": "active",
    "createdAt": "2026-10-20T10:10:00+08:00"
  }
}
```

#### 2.3.6 创建学校账号

**接口**：`POST /api/v1/accounts/schools`  
**权限**：[district_admin, city_admin, province_admin]  
**说明**：区县管理员在本区县创建学校；市州管理员仅可创建市直属学校；省级管理员可指定区县或市州创建学校。创建学校时同时创建该校学校管理员账号。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| districtId | body | number | 条件必填 | 学校所属区县 ID；区县管理员可不传（取本人范围），市州/省级管理员必须传；市直属学校改传 `cityId` |
| cityId | body | number | 条件必填 | 市直属学校所属市州 ID；创建市直属学校时必填 |
| schoolCode | body | string | 是 | 学校编码，区县内唯一 |
| schoolName | body | string | 是 | 学校名称 |
| schoolType | body | string | 是 | `primary` / `middle` / `high` / `combined` |
| address | body | string | 否 | 学校地址 |
| adminUsername | body | string | 是 | 学校管理员登录账号 |
| adminRealName | body | string | 是 | 学校管理员姓名 |
| adminPhone | body | string | 是 | 学校管理员手机号 |
| initialPassword | body | string | 否 | 管理员初始密码 |

请求示例：

```json
{
  "schoolCode": "SCH00301",
  "schoolName": "示范中学",
  "schoolType": "combined",
  "address": "示例市示例区教育路 1 号",
  "adminUsername": "school301",
  "adminRealName": "孙校长",
  "adminPhone": "13700000001",
  "initialPassword": "School@2026"
}
```

**响应数据（data）**：`OrgCreateResult`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "orgId": 301,
    "orgName": "示范中学",
    "adminAccount": {
      "id": 3001,
      "username": "school301",
      "realName": "孙校长",
      "role": "school_admin",
      "roleName": "学校管理员",
      "orgId": 301,
      "orgName": "示范中学",
      "phone": "13700000001",
      "email": null,
      "subject": null,
      "title": null,
      "studentNo": null,
      "classId": null,
      "className": null,
      "status": "active",
      "createdAt": "2026-10-20T10:20:00+08:00"
    }
  }
}
```

#### 2.3.7 创建区县账号

**接口**：`POST /api/v1/accounts/districts`  
**权限**：[city_admin, province_admin]  
**说明**：市州管理员在本市州创建区县及区县管理员账号；省级管理员可指定市州创建区县。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| cityId | body | number | 条件必填 | 区县所属市州 ID；市州管理员可不传（取本人范围），省级管理员必须传 |
| districtCode | body | string | 是 | 区县编码，市州内唯一 |
| districtName | body | string | 是 | 区县名称 |
| adminUsername | body | string | 是 | 区县管理员登录账号 |
| adminRealName | body | string | 是 | 区县管理员姓名 |
| adminPhone | body | string | 是 | 区县管理员手机号 |
| initialPassword | body | string | 否 | 初始密码 |

**响应数据（data）**：`OrgCreateResult`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "orgId": 22,
    "orgName": "示例区",
    "adminAccount": {
      "id": 2201,
      "username": "district22",
      "realName": "刘主任",
      "role": "district_admin",
      "roleName": "区县管理员",
      "orgId": 22,
      "orgName": "示例区",
      "phone": "13600000001",
      "email": null,
      "subject": null,
      "title": null,
      "studentNo": null,
      "classId": null,
      "className": null,
      "status": "active",
      "createdAt": "2026-10-20T10:30:00+08:00"
    }
  }
}
```

#### 2.3.8 创建市州账号

**接口**：`POST /api/v1/accounts/cities`  
**权限**：[province_admin]  
**说明**：省级管理员创建市州及市州管理员账号。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| cityCode | body | string | 是 | 市州编码，全省唯一 |
| cityName | body | string | 是 | 市州名称 |
| adminUsername | body | string | 是 | 市州管理员登录账号 |
| adminRealName | body | string | 是 | 市州管理员姓名 |
| adminPhone | body | string | 是 | 市州管理员手机号 |
| initialPassword | body | string | 否 | 初始密码 |

**响应数据（data）**：`OrgCreateResult`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "orgId": 3,
    "orgName": "示例市",
    "adminAccount": {
      "id": 3011,
      "username": "city03",
      "realName": "周局长",
      "role": "city_admin",
      "roleName": "市州管理员",
      "orgId": 3,
      "orgName": "示例市",
      "phone": "13500000001",
      "email": null,
      "subject": null,
      "title": null,
      "studentNo": null,
      "classId": null,
      "className": null,
      "status": "active",
      "createdAt": "2026-10-20T10:40:00+08:00"
    }
  }
}
```

#### 2.3.9 修改账号信息

**接口**：`PATCH /api/v1/accounts/{accountId}`  
**权限**：[school_admin, district_admin, city_admin, province_admin]  
**说明**：修改权限范围内账号的非敏感资料。角色、学籍号、所属组织默认不可修改；禁止修改本人以外的同级或上级账号。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| accountId | path | number | 是 | 账号 ID |
| realName | body | string | 否 | 姓名 |
| phone | body | string | 否 | 手机号 |
| email | body | string | 否 | 邮箱 |
| subject | body | string | 否 | 教师任教学科 |
| title | body | string | 否 | 教师职称 |
| classId | body | number | 否 | 学生班级，仅本校范围内 |
| status | body | string | 否 | `active` / `disabled` |

**响应数据（data）**：`AccountItem`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 2003,
    "username": "teacher1003",
    "realName": "周老师",
    "role": "teacher",
    "roleName": "教师",
    "orgId": 301,
    "orgName": "示范中学",
    "phone": "13800000005",
    "email": "teacher1003@example.com",
    "subject": "art",
    "title": "一级教师",
    "studentNo": null,
    "classId": null,
    "className": null,
    "status": "active",
    "createdAt": "2026-10-20T10:00:00+08:00"
  }
}
```

#### 2.3.10 删除账号

**接口**：`DELETE /api/v1/accounts/{accountId}`  
**权限**：[school_admin, district_admin, city_admin, province_admin]  
**说明**：逻辑删除权限范围内账号。存在未完成测评、有效成绩或下属组织时，应拒绝删除并返回 `409`。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| accountId | path | number | 是 | 账号 ID |

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "deleted": true,
    "accountId": 2003
  }
}
```

#### 2.3.11 重置账号密码

**接口**：`POST /api/v1/accounts/{accountId}/reset-password`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：管理员重置权限范围内账号密码；教师仅可重置本人任教班级学生的密码。不传新密码时生成临时密码，并强制下次登录修改。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| accountId | path | number | 是 | 账号 ID |
| newPassword | body | string | 否 | 指定新密码；不传则随机生成 |
| forceChange | body | boolean | 否 | 是否强制下次登录修改，默认 `true` |

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "accountId": 2003,
    "temporaryPassword": "Tmp#8kQ2p",
    "forceChange": true
  }
}
```

### 2.4 班级管理

#### 2.4.1 查询班级列表

**接口**：`GET /api/v1/classes`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：按权限范围分页查询班级，教师仅返回任教班级。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| keyword | query | string | 否 | 班级名称或班级号模糊搜索 |
| grade | query | number | 否 | 年级 |
| schoolId | query | number | 否 | 学校 ID，必须在数据范围内 |
| status | query | string | 否 | `active` / `archived` |
| pageNum | query | number | 否 | 页码，默认 1 |
| pageSize | query | number | 否 | 每页条数，默认 10 |

**响应数据（data）**：`Page<ClassItem>`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 1,
    "pages": 1,
    "list": [
      {
        "id": 5001,
        "classCode": "C20260701",
        "name": "七年级（1）班",
        "grade": 7,
        "schoolId": 301,
        "schoolName": "示范中学",
        "headTeacherId": 2001,
        "headTeacherName": "李老师",
        "studentCount": 42,
        "status": "active",
        "createdAt": "2026-09-01T10:00:00+08:00"
      }
    ]
  }
}
```

#### 2.4.2 创建班级

**接口**：`POST /api/v1/classes`  
**权限**：[teacher, school_admin]  
**说明**：学校管理员在本校创建班级；教师创建班级后自动成为班主任，仅可管理本人班级。班级号全局唯一，可由服务端生成。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| name | body | string | 是 | 班级名称 |
| grade | body | number | 是 | 年级，1~12 |
| classCode | body | string | 否 | 班级号；不传则自动生成 |
| headTeacherId | body | number | 否 | 班主任账号 ID，必须是本校教师 |
| description | body | string | 否 | 班级简介 |

**响应数据（data）**：`ClassDetail`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 5002,
    "classCode": "C20260702",
    "name": "七年级（2）班",
    "grade": 7,
    "schoolId": 301,
    "schoolName": "示范中学",
    "headTeacherId": 2001,
    "headTeacherName": "李老师",
    "studentCount": 0,
    "status": "active",
    "createdAt": "2026-10-20T11:00:00+08:00",
    "description": "2026 级七年级二班",
    "subjectTeachers": [
      {
        "id": 2001,
        "realName": "李老师",
        "subject": "music"
      }
    ],
    "createdBy": 3001,
    "updatedAt": "2026-10-20T11:00:00+08:00"
  }
}
```

#### 2.4.3 按班级号查询班级

**接口**：`GET /api/v1/classes/search`  
**权限**：[student, teacher, school_admin]  
**说明**：学生输入班级号查找班级，用于申请加入；只返回加入所需的公开信息。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| classCode | query | string | 是 | 班级号，精确匹配 |

**响应数据（data）**：`ClassDetail`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 5001,
    "classCode": "C20260701",
    "name": "七年级（1）班",
    "grade": 7,
    "schoolId": 301,
    "schoolName": "示范中学",
    "headTeacherId": 2001,
    "headTeacherName": "李老师",
    "studentCount": 42,
    "status": "active",
    "createdAt": "2026-09-01T10:00:00+08:00",
    "description": "2026 级七年级一班",
    "subjectTeachers": [
      {
        "id": 2001,
        "realName": "李老师",
        "subject": "music"
      },
      {
        "id": 2002,
        "realName": "赵老师",
        "subject": "art"
      }
    ],
    "createdBy": 3001,
    "updatedAt": "2026-10-01T08:00:00+08:00"
  }
}
```

#### 2.4.4 查询班级详情

**接口**：`GET /api/v1/classes/{classId}`  
**权限**：[student, teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：学生仅可查看本人当前班级；教师和管理员按数据范围查看。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| classId | path | number | 是 | 班级 ID |

**响应数据（data）**：`ClassDetail`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 5001,
    "classCode": "C20260701",
    "name": "七年级（1）班",
    "grade": 7,
    "schoolId": 301,
    "schoolName": "示范中学",
    "headTeacherId": 2001,
    "headTeacherName": "李老师",
    "studentCount": 42,
    "status": "active",
    "createdAt": "2026-09-01T10:00:00+08:00",
    "description": "2026 级七年级一班",
    "subjectTeachers": [
      {
        "id": 2001,
        "realName": "李老师",
        "subject": "music"
      }
    ],
    "createdBy": 3001,
    "updatedAt": "2026-10-01T08:00:00+08:00"
  }
}
```

#### 2.4.5 修改班级

**接口**：`PATCH /api/v1/classes/{classId}`  
**权限**：[teacher, school_admin]  
**说明**：修改本校班级基础信息；教师仅可修改本人担任班主任的班级。班级号如需变更必须保持全局唯一。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| classId | path | number | 是 | 班级 ID |
| name | body | string | 否 | 班级名称 |
| grade | body | number | 否 | 年级 |
| headTeacherId | body | number | 否 | 班主任账号 ID |
| description | body | string | 否 | 班级简介 |
| status | body | string | 否 | `active` / `archived` |

**响应数据（data）**：`ClassDetail`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 5001,
    "classCode": "C20260701",
    "name": "七年级（1）班",
    "grade": 7,
    "schoolId": 301,
    "schoolName": "示范中学",
    "headTeacherId": 2002,
    "headTeacherName": "赵老师",
    "studentCount": 42,
    "status": "active",
    "createdAt": "2026-09-01T10:00:00+08:00",
    "description": "2026 级七年级一班（更新）",
    "subjectTeachers": [],
    "createdBy": 3001,
    "updatedAt": "2026-10-20T11:20:00+08:00"
  }
}
```

#### 2.4.6 解散班级

**接口**：`DELETE /api/v1/classes/{classId}`  
**权限**：[teacher, school_admin]  
**说明**：逻辑归档班级；教师仅可解散本人担任班主任的班级。班级仍有在班学生、未结束测评或有效成绩时，返回 `409`，需先转班或完成测评。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| classId | path | number | 是 | 班级 ID |

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "deleted": true,
    "classId": 5002
  }
}
```

#### 2.4.7 申请加入班级（学生/教师）

**接口**：`POST /api/v1/classes/{classId}/join`  
**权限**：[student, teacher]  
**说明**：学生通过班级号提交加入申请；教师提交成为该班科任教师的申请。两类申请均由班主任或学校管理员审核，`requesterRole` 由服务端按当前账号填写，前端不得伪造。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| classId | path | number | 是 | 目标班级 ID |
| reason | body | string | 否 | 申请理由，最多 200 字 |
| subject | body | string | 条件必填 | 教师申请时必填：`music` / `art` |

**响应数据（data）**：`JoinRequestItem`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 7001,
    "classId": 5001,
    "className": "七年级（1）班",
    "requesterId": 1001,
    "requesterName": "王小明",
    "requesterRole": "student",
    "type": "join",
    "targetClassId": null,
    "targetClassName": null,
    "status": "pending",
    "reason": "本人为该班学生",
    "reviewerId": null,
    "reviewerName": null,
    "reviewComment": null,
    "reviewedAt": null,
    "createdAt": "2026-10-20T11:30:00+08:00"
  }
}
```

#### 2.4.8 学生申请退出班级

**接口**：`POST /api/v1/classes/{classId}/leave`  
**权限**：[student]  
**说明**：提交退出班级申请，审核通过后学生不再属于该班；历史成绩保留。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| classId | path | number | 是 | 当前班级 ID |
| reason | body | string | 否 | 退出原因，最多 200 字 |

**响应数据（data）**：`JoinRequestItem`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 7002,
    "classId": 5001,
    "className": "七年级（1）班",
    "requesterId": 1001,
    "requesterName": "王小明",
    "requesterRole": "student",
    "type": "leave",
    "targetClassId": null,
    "targetClassName": null,
    "status": "pending",
    "reason": "随家庭搬迁转学",
    "reviewerId": null,
    "reviewerName": null,
    "reviewComment": null,
    "reviewedAt": null,
    "createdAt": "2026-10-20T11:35:00+08:00"
  }
}
```

#### 2.4.9 学生申请更换班级

**接口**：`POST /api/v1/classes/{classId}/change`  
**权限**：[student]  
**说明**：提交转班申请；原班级和目标班级均须审核通过后生效。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| classId | path | number | 是 | 当前班级 ID |
| targetClassId | body | number | 是 | 目标班级 ID，必须为同校班级 |
| reason | body | string | 是 | 转班原因 |

**响应数据（data）**：`JoinRequestItem`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 7003,
    "classId": 5001,
    "className": "七年级（1）班",
    "requesterId": 1001,
    "requesterName": "王小明",
    "requesterRole": "student",
    "type": "change",
    "targetClassId": 5002,
    "targetClassName": "七年级（2）班",
    "status": "pending",
    "reason": "课程安排调整",
    "reviewerId": null,
    "reviewerName": null,
    "reviewComment": null,
    "reviewedAt": null,
    "createdAt": "2026-10-20T11:40:00+08:00"
  }
}
```

#### 2.4.10 查询班级申请列表

**接口**：`GET /api/v1/classes/{classId}/requests`  
**权限**：[teacher, school_admin]  
**说明**：班主任、科任教师或学校管理员查看加入、退出、转班申请。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| classId | path | number | 是 | 班级 ID |
| type | query | string | 否 | `join` / `change` / `leave` |
| status | query | string | 否 | 申请状态，默认 `pending` |
| pageNum | query | number | 否 | 页码，默认 1 |
| pageSize | query | number | 否 | 每页条数，默认 10 |

**响应数据（data）**：`Page<JoinRequestItem>`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 1,
    "pages": 1,
    "list": [
      {
        "id": 7001,
        "classId": 5001,
        "className": "七年级（1）班",
        "requesterId": 1001,
        "requesterName": "王小明",
        "requesterRole": "student",
        "type": "join",
        "targetClassId": null,
        "targetClassName": null,
        "status": "pending",
        "reason": "本人为该班学生",
        "reviewerId": null,
        "reviewerName": null,
        "reviewComment": null,
        "reviewedAt": null,
        "createdAt": "2026-10-20T11:30:00+08:00"
      }
    ]
  }
}
```

#### 2.4.11 审核班级申请

**接口**：`POST /api/v1/classes/{classId}/requests/{requestId}/review`  
**权限**：[teacher, school_admin]  
**说明**：通过或驳回加入、退出、转班申请；转班申请需校验目标班级容量与同校限制。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| classId | path | number | 是 | 班级 ID |
| requestId | path | number | 是 | 申请 ID |
| action | body | string | 是 | `approve` / `reject` |
| comment | body | string | 否 | 审核意见 |

请求示例：

```json
{
  "action": "approve",
  "comment": "信息核对无误，同意加入"
}
```

**响应数据（data）**：`JoinRequestItem`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 7001,
    "classId": 5001,
    "className": "七年级（1）班",
    "requesterId": 1001,
    "requesterName": "王小明",
    "requesterRole": "student",
    "type": "join",
    "targetClassId": null,
    "targetClassName": null,
    "status": "approved",
    "reason": "本人为该班学生",
    "reviewerId": 2001,
    "reviewerName": "李老师",
    "reviewComment": "信息核对无误，同意加入",
    "reviewedAt": "2026-10-20T11:50:00+08:00",
    "createdAt": "2026-10-20T11:30:00+08:00"
  }
}
```

#### 2.4.12 查询班级学生

**接口**：`GET /api/v1/classes/{classId}/students`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：分页查询班级学生；教师仅限任教班级。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| classId | path | number | 是 | 班级 ID |
| keyword | query | string | 否 | 姓名/账号/学籍号模糊搜索 |
| status | query | string | 否 | 学生账号状态 |
| pageNum | query | number | 否 | 页码，默认 1 |
| pageSize | query | number | 否 | 每页条数，默认 10 |

**响应数据（data）**：`Page<StudentItem>`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 1,
    "pages": 1,
    "list": [
      {
        "id": 1001,
        "username": "student2026001",
        "studentNo": "S20260001",
        "realName": "王小明",
        "gender": "male",
        "grade": 7,
        "classId": 5001,
        "className": "七年级（1）班",
        "status": "active",
        "joinedAt": "2026-09-02T08:00:00+08:00"
      }
    ]
  }
}
```

#### 2.4.13 移除班级学生

**接口**：`DELETE /api/v1/classes/{classId}/students/{studentId}`  
**权限**：[teacher, school_admin]  
**说明**：将学生移出班级，不删除学生账号；需保留历史测评与成绩关联。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| classId | path | number | 是 | 班级 ID |
| studentId | path | number | 是 | 学生账号 ID |

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "removed": true,
    "classId": 5001,
    "studentId": 1001
  }
}
```

#### 2.4.14 批量导入班级学生

**接口**：`POST /api/v1/classes/{classId}/students/import`  
**权限**：[teacher, school_admin]  
**Content-Type**：`multipart/form-data`  
**说明**：通过 CSV/XLSX 批量创建学生账号并加入当前班级。导入需整行校验，支持部分成功。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| classId | path | number | 是 | 班级 ID |
| file | formData | file | 是 | CSV/XLSX 文件，最大 10 MB |
| mode | formData | string | 否 | `append` 仅新增 / `upsert` 存在则更新，默认 `append` |

模板列：`学籍号,姓名,性别,年级,登录账号,手机号,监护人手机号`。  
校验规则：学籍号全局唯一；登录账号校内唯一；年级必须与班级年级一致；性别使用“男/女/未知”。

请求示例（curl）：

```bash
curl -X POST "https://api.example.com/api/v1/classes/5001/students/import" \
  -H "Authorization: Bearer <token>" \
  -F "file=@students.xlsx" \
  -F "mode=append"
```

**响应数据（data）**：`ImportResult`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 45,
    "successCount": 43,
    "failCount": 2,
    "errors": [
      {
        "row": 12,
        "studentNo": "S20260045",
        "message": "学籍号已存在"
      },
      {
        "row": 30,
        "studentNo": "S20260063",
        "message": "性别必须为男/女/未知"
      }
    ]
  }
}
```

### 2.5 文件上传

#### 2.5.1 通用文件上传

**接口**：`POST /api/v1/files`  
**权限**：[student, teacher, school_admin, district_admin, city_admin, province_admin, question_admin]  
**Content-Type**：`multipart/form-data`  
**说明**：上传头像、试题图片/音频、学生作品、导入文件等。服务端必须校验扩展名、MIME 类型、文件大小与文件头。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| file | formData | file | 是 | 文件本体 |
| category | formData | string | 是 | 文件分类枚举 |
| bizId | formData | number | 否 | 关联业务 ID，例如试题 ID、测评 ID |

限制建议：

- 图片：`jpg`、`jpeg`、`png`、`webp`，单文件 ≤ 10 MB。
- 音频：`mp3`、`wav`、`m4a`，单文件 ≤ 50 MB。
- 导入文件：`csv`、`xlsx`，单文件 ≤ 10 MB。
- 证书：`pdf`，单文件 ≤ 20 MB。
- 禁止可执行文件、脚本、压缩包和双扩展名文件。
- 上传后应进行病毒扫描或至少进行文件头校验；存储路径使用随机 ID，不使用原始文件名。

请求示例（curl）：

```bash
curl -X POST "https://api.example.com/api/v1/files" \
  -H "Authorization: Bearer <token>" \
  -F "file=@artwork.jpg" \
  -F "category=student_work" \
  -F "bizId=9001"
```

**响应数据（data）**：`FileObject`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "fileId": 88001,
    "url": "https://cdn.example.com/student_work/88001.jpg",
    "name": "artwork.jpg",
    "mimeType": "image/jpeg",
    "size": 2457600,
    "category": "student_work",
    "createdAt": "2026-10-20T12:00:00+08:00"
  }
}
```

#### 2.5.2 删除文件

**接口**：`DELETE /api/v1/files/{fileId}`  
**权限**：[student, teacher, school_admin, district_admin, city_admin, province_admin, question_admin]  
**说明**：仅文件上传者或权限范围内管理员可删除；已被题目、答卷、证书引用的文件应拒绝删除。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| fileId | path | number | 是 | 文件 ID |

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "deleted": true,
    "fileId": 88001
  }
}
```

## 3. 模块二：题库管理

> 后端负责人：柴国继（后端 B）  
> 覆盖：试题 CRUD、试题审核、多条件筛选、课程/章节 CRUD、试题资源上传删除、操作日志查询。

### 3.1 数据模型

#### QuestionOption（试题选项）

| 字段 | 类型 | 说明 |
|---|---|---|
| key | string | 选项标识，如 `A`、`B` |
| text | string | 选项文本 |
| mediaUrl | string / null | 选项附带的图片或音频地址 |

#### QuestionResource（试题资源）

| 字段 | 类型 | 说明 |
|---|---|---|
| resourceId | number | 资源关联 ID |
| fileId | number | 文件 ID |
| type | string | `image` / `audio` |
| url | string | 资源访问地址 |
| name | string | 文件名 |
| mimeType | string | MIME 类型 |
| size | number | 文件字节数 |
| createdAt | string | 上传时间 |

#### QuestionItem（试题列表项）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | number | 试题 ID |
| subject | string | `music` / `art` |
| grade | number | 年级 |
| courseId | number | 课程 ID |
| courseName | string | 课程名称 |
| chapterId | number / null | 章节 ID |
| chapterName | string / null | 章节名称 |
| type | string | 题型枚举 |
| difficulty | number | 难度 1~5 |
| stem | string | 题干 |
| score | number | 默认分值 |
| status | string | 试题状态 |
| creatorId | number | 创建人 ID |
| creatorName | string | 创建人姓名 |
| reviewerId | number / null | 审核人 ID |
| reviewerName | string / null | 审核人姓名 |
| reviewComment | string / null | 审核意见；未审核或未填写时为 `null` |
| resourceCount | number | 资源数量 |
| createdAt | string | 创建时间 |
| updatedAt | string | 更新时间 |

#### QuestionDetail（试题详情）

包含 `QuestionItem` 全部字段，并增加：

| 字段 | 类型 | 说明 |
|---|---|---|
| options | array | 选项列表，元素为 `QuestionOption`；非选择题为空数组 |
| answer | object | 标准答案；不同题型结构见 3.2 说明 |
| analysis | string / null | 答案解析；未填写时为 `null` |
| scoringMode | string | `auto` / `manual` / `ai` |
| resources | array | 资源列表，元素为 `QuestionResource` |

#### CourseItem（课程）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | number | 课程 ID |
| name | string | 课程名称 |
| subject | string | 学科 |
| grade | number | 适用年级 |
| description | string / null | 课程简介；未填写时为 `null` |
| chapterCount | number | 章节数量 |
| sortOrder | number | 排序值，越小越靠前 |
| status | string | `active` / `disabled` |
| createdAt | string | 创建时间 |
| updatedAt | string | 更新时间 |

#### ChapterItem（章节）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | number | 章节 ID |
| courseId | number | 所属课程 ID |
| courseName | string | 所属课程名称 |
| name | string | 章节名称 |
| description | string / null | 章节简介；未填写时为 `null` |
| questionCount | number | 题目数量 |
| sortOrder | number | 排序值 |
| createdAt | string | 创建时间 |
| updatedAt | string | 更新时间 |

#### OperationLogItem（操作日志）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | number | 日志 ID |
| operatorId | number | 操作人 ID |
| operatorName | string | 操作人姓名 |
| role | string | 操作人角色 |
| action | string | 操作类型，如 `question.create`、`question.review`、`resource.delete` |
| resourceType | string | `question` / `course` / `chapter` / `resource` / `account` / `system` |
| resourceId | number / null | 目标资源 ID |
| description | string | 操作说明 |
| ip | string | 客户端 IP |
| userAgent | string | 客户端标识 |
| result | string | `success` / `failed` |
| createdAt | string | 操作时间 |

> 标准答案 `answer` 的结构：`single_choice` / `listening` 为 `{"value":"A"}`；`multiple_choice` 为 `{"values":["A","C"]}`；`true_false` 为 `{"value":true}`；`fill_blank` 为 `{"values":["答案1","答案2"]}`；`short_answer` 为 `{"text":"参考答案"}`；`image_upload` / `audio_upload` 为 `{"rubric":{...}}`，具体评分维度由评分规则定义。

### 3.2 试题管理

#### 3.2.1 查询试题列表

**接口**：`GET /api/v1/questions`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin, question_admin]  
**说明**：按学科、难度、题型、年级、课程、章节、状态筛选试题。教师默认只能查看“已通过题目 + 本人创建题目”。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| subject | query | string | 否 | `music` / `art` |
| difficulty | query | number | 否 | 难度 1~5，支持传单值 |
| type | query | string | 否 | 题型枚举，支持单值 |
| grade | query | number | 否 | 年级 1~12 |
| courseId | query | number | 否 | 课程 ID |
| chapterId | query | number | 否 | 章节 ID |
| keyword | query | string | 否 | 题干关键词 |
| status | query | string | 否 | 试题状态；教师只能筛选本人题目的非公开状态 |
| scope | query | string | 否 | `all` 公共题库 / `mine` 我的题目，默认 `all` |
| pageNum | query | number | 否 | 页码，默认 1 |
| pageSize | query | number | 否 | 每页条数，默认 10 |

**响应数据（data）**：`Page<QuestionItem>`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 1,
    "pages": 1,
    "list": [
      {
        "id": 9001,
        "subject": "music",
        "grade": 7,
        "courseId": 6001,
        "courseName": "七年级音乐鉴赏",
        "chapterId": 6101,
        "chapterName": "第一单元 节奏与节拍",
        "type": "single_choice",
        "difficulty": 2,
        "stem": "聆听音频，判断这段旋律的拍号。",
        "score": 5,
        "status": "approved",
        "creatorId": 2001,
        "creatorName": "李老师",
        "reviewerId": 7001,
        "reviewerName": "题库管理员",
        "reviewComment": "题目规范，审核通过",
        "resourceCount": 1,
        "createdAt": "2026-10-01T09:00:00+08:00",
        "updatedAt": "2026-10-02T09:00:00+08:00"
      }
    ]
  }
}
```

#### 3.2.2 创建试题

**接口**：`POST /api/v1/questions`  
**权限**：[teacher, question_admin]  
**说明**：教师创建后进入待审核状态；题库管理员可直接创建为已通过题目。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| subject | body | string | 是 | `music` / `art` |
| grade | body | number | 是 | 年级 1~12 |
| courseId | body | number | 是 | 课程 ID |
| chapterId | body | number | 否 | 章节 ID，必须属于该课程 |
| type | body | string | 是 | 题型枚举 |
| difficulty | body | number | 是 | 难度 1~5 |
| stem | body | string | 是 | 题干，1~5000 字 |
| score | body | number | 是 | 默认分值，0.5~100 |
| options | body | array | 条件必填 | 选择题选项，元素为 `{key,text,mediaUrl}` |
| answer | body | object | 条件必填 | 标准答案，按题型传入；AI 评分题可传评分量表 |
| analysis | body | string | 否 | 答案解析 |
| scoringMode | body | string | 是 | `auto` / `manual` / `ai` |
| resourceFileIds | body | array | 否 | 已上传的图片/音频文件 ID 数组 |
| publishNow | body | boolean | 否 | 仅题库管理员有效；`true` 时直接发布为 `approved` |

请求示例：

```json
{
  "subject": "music",
  "grade": 7,
  "courseId": 6001,
  "chapterId": 6101,
  "type": "single_choice",
  "difficulty": 2,
  "stem": "聆听音频，判断这段旋律的拍号。",
  "score": 5,
  "options": [
    { "key": "A", "text": "2/4", "mediaUrl": null },
    { "key": "B", "text": "3/4", "mediaUrl": null },
    { "key": "C", "text": "4/4", "mediaUrl": null },
    { "key": "D", "text": "6/8", "mediaUrl": null }
  ],
  "answer": { "value": "B" },
  "analysis": "旋律呈现强弱弱的周期性规律，因此为三拍子。",
  "scoringMode": "auto",
  "resourceFileIds": [88002],
  "publishNow": false
}
```

**响应数据（data）**：`QuestionDetail`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 9001,
    "subject": "music",
    "grade": 7,
    "courseId": 6001,
    "courseName": "七年级音乐鉴赏",
    "chapterId": 6101,
    "chapterName": "第一单元 节奏与节拍",
    "type": "single_choice",
    "difficulty": 2,
    "stem": "聆听音频，判断这段旋律的拍号。",
    "score": 5,
    "status": "pending",
    "creatorId": 2001,
    "creatorName": "李老师",
    "reviewerId": null,
    "reviewerName": null,
    "reviewComment": null,
    "resourceCount": 1,
    "createdAt": "2026-10-20T13:00:00+08:00",
    "updatedAt": "2026-10-20T13:00:00+08:00",
    "options": [
      { "key": "A", "text": "2/4", "mediaUrl": null },
      { "key": "B", "text": "3/4", "mediaUrl": null },
      { "key": "C", "text": "4/4", "mediaUrl": null },
      { "key": "D", "text": "6/8", "mediaUrl": null }
    ],
    "answer": { "value": "B" },
    "analysis": "旋律呈现强弱弱的周期性规律，因此为三拍子。",
    "scoringMode": "auto",
    "resources": [
      {
        "resourceId": 9101,
        "fileId": 88002,
        "type": "audio",
        "url": "https://cdn.example.com/question_audio/88002.mp3",
        "name": "question-9001.mp3",
        "mimeType": "audio/mpeg",
        "size": 1048576,
        "createdAt": "2026-10-20T13:00:00+08:00"
      }
    ]
  }
}
```

#### 3.2.3 查询试题详情

**接口**：`GET /api/v1/questions/{questionId}`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin, question_admin]  
**说明**：返回题干、选项、答案、解析与资源。学生端不得直接调用该接口获取标准答案。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| questionId | path | number | 是 | 试题 ID |

**响应数据（data）**：`QuestionDetail`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 9001,
    "subject": "music",
    "grade": 7,
    "courseId": 6001,
    "courseName": "七年级音乐鉴赏",
    "chapterId": 6101,
    "chapterName": "第一单元 节奏与节拍",
    "type": "single_choice",
    "difficulty": 2,
    "stem": "聆听音频，判断这段旋律的拍号。",
    "score": 5,
    "status": "approved",
    "creatorId": 2001,
    "creatorName": "李老师",
    "reviewerId": 7001,
    "reviewerName": "题库管理员",
    "reviewComment": "题目规范，审核通过",
    "resourceCount": 1,
    "createdAt": "2026-10-01T09:00:00+08:00",
    "updatedAt": "2026-10-02T09:00:00+08:00",
    "options": [
      { "key": "A", "text": "2/4", "mediaUrl": null },
      { "key": "B", "text": "3/4", "mediaUrl": null },
      { "key": "C", "text": "4/4", "mediaUrl": null },
      { "key": "D", "text": "6/8", "mediaUrl": null }
    ],
    "answer": { "value": "B" },
    "analysis": "旋律呈现强弱弱的周期性规律，因此为三拍子。",
    "scoringMode": "auto",
    "resources": []
  }
}
```

#### 3.2.4 修改试题

**接口**：`PATCH /api/v1/questions/{questionId}`  
**权限**：[teacher, question_admin]  
**说明**：教师只能修改本人创建且状态为 `draft` / `rejected` 的试题；题库管理员可修改全部试题。试题被已发布试卷引用时，修改应生成新版本，不直接覆盖历史快照。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| questionId | path | number | 是 | 试题 ID |
| 其余字段 | body | - | 否 | 同“创建试题”，按需传入；`subject` 与题型变更需重新校验 |

**响应数据（data）**：`QuestionDetail`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 9001,
    "subject": "music",
    "grade": 7,
    "courseId": 6001,
    "courseName": "七年级音乐鉴赏",
    "chapterId": 6101,
    "chapterName": "第一单元 节奏与节拍",
    "type": "single_choice",
    "difficulty": 3,
    "stem": "聆听音频，判断这段旋律的拍号。",
    "score": 5,
    "status": "draft",
    "creatorId": 2001,
    "creatorName": "李老师",
    "reviewerId": null,
    "reviewerName": null,
    "reviewComment": null,
    "resourceCount": 1,
    "createdAt": "2026-10-01T09:00:00+08:00",
    "updatedAt": "2026-10-20T13:10:00+08:00",
    "options": [],
    "answer": { "value": "B" },
    "analysis": "旋律呈现强弱弱的周期性规律，因此为三拍子。",
    "scoringMode": "auto",
    "resources": []
  }
}
```

#### 3.2.5 删除试题

**接口**：`DELETE /api/v1/questions/{questionId}`  
**权限**：[teacher, question_admin]  
**说明**：教师仅可删除本人草稿/被驳回试题；题库管理员可逻辑删除任意未被有效试卷引用的试题。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| questionId | path | number | 是 | 试题 ID |

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "deleted": true,
    "questionId": 9001
  }
}
```

#### 3.2.6 提交试题审核

**接口**：`POST /api/v1/questions/{questionId}/submit-review`  
**权限**：[teacher]  
**说明**：教师将本人草稿或被驳回试题提交审核，状态变为 `pending`。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| questionId | path | number | 是 | 试题 ID |
| remark | body | string | 否 | 提交说明 |

**响应数据（data）**：`QuestionDetail`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 9001,
    "subject": "music",
    "grade": 7,
    "courseId": 6001,
    "courseName": "七年级音乐鉴赏",
    "chapterId": 6101,
    "chapterName": "第一单元 节奏与节拍",
    "type": "single_choice",
    "difficulty": 2,
    "stem": "聆听音频，判断这段旋律的拍号。",
    "score": 5,
    "status": "pending",
    "creatorId": 2001,
    "creatorName": "李老师",
    "reviewerId": null,
    "reviewerName": null,
    "reviewComment": null,
    "resourceCount": 1,
    "createdAt": "2026-10-01T09:00:00+08:00",
    "updatedAt": "2026-10-20T13:20:00+08:00",
    "options": [],
    "answer": { "value": "B" },
    "analysis": null,
    "scoringMode": "auto",
    "resources": []
  }
}
```

#### 3.2.7 审核试题

**接口**：`POST /api/v1/questions/{questionId}/review`  
**权限**：[question_admin]  
**说明**：题库管理员审核教师试题。通过后进入公共题库；驳回时必须填写意见。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| questionId | path | number | 是 | 试题 ID |
| action | body | string | 是 | `approve` / `reject` |
| comment | body | string | 条件必填 | 驳回时必填；通过时可选 |

请求示例：

```json
{
  "action": "reject",
  "comment": "音频资源与题干不匹配，请重新上传"
}
```

**响应数据（data）**：`QuestionDetail`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 9001,
    "subject": "music",
    "grade": 7,
    "courseId": 6001,
    "courseName": "七年级音乐鉴赏",
    "chapterId": 6101,
    "chapterName": "第一单元 节奏与节拍",
    "type": "single_choice",
    "difficulty": 2,
    "stem": "聆听音频，判断这段旋律的拍号。",
    "score": 5,
    "status": "rejected",
    "creatorId": 2001,
    "creatorName": "李老师",
    "reviewerId": 7001,
    "reviewerName": "题库管理员",
    "reviewComment": "音频资源与题干不匹配，请重新上传",
    "resourceCount": 1,
    "createdAt": "2026-10-01T09:00:00+08:00",
    "updatedAt": "2026-10-20T13:30:00+08:00",
    "options": [],
    "answer": { "value": "B" },
    "analysis": null,
    "scoringMode": "auto",
    "resources": []
  }
}
```

### 3.3 课程管理

#### 3.3.1 查询课程列表

**接口**：`GET /api/v1/courses`  
**权限**：[student, teacher, school_admin, district_admin, city_admin, province_admin, question_admin]  
**说明**：按学科、年级和关键词查询课程；学生仅可查看已发布课程，并按本人年级过滤。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| subject | query | string | 否 | 学科 |
| grade | query | number | 否 | 年级 |
| keyword | query | string | 否 | 课程名称模糊搜索 |
| status | query | string | 否 | `active` / `disabled` |
| pageNum | query | number | 否 | 页码，默认 1 |
| pageSize | query | number | 否 | 每页条数，默认 10 |

**响应数据（data）**：`Page<CourseItem>`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 1,
    "pages": 1,
    "list": [
      {
        "id": 6001,
        "name": "七年级音乐鉴赏",
        "subject": "music",
        "grade": 7,
        "description": "依据义务教育艺术课程标准设置",
        "chapterCount": 6,
        "sortOrder": 1,
        "status": "active",
        "createdAt": "2026-09-01T09:00:00+08:00",
        "updatedAt": "2026-09-01T09:00:00+08:00"
      }
    ]
  }
}
```

#### 3.3.2 创建课程

**接口**：`POST /api/v1/courses`  
**权限**：[question_admin]  
**说明**：题库管理员创建课程。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| name | body | string | 是 | 课程名称 |
| subject | body | string | 是 | 学科 |
| grade | body | number | 是 | 年级 |
| description | body | string | 否 | 课程简介 |
| sortOrder | body | number | 否 | 排序值，默认 0 |
| status | body | string | 否 | 默认 `active` |

**响应数据（data）**：`CourseItem`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 6002,
    "name": "七年级美术鉴赏",
    "subject": "art",
    "grade": 7,
    "description": "美术鉴赏基础课程",
    "chapterCount": 0,
    "sortOrder": 2,
    "status": "active",
    "createdAt": "2026-10-20T14:00:00+08:00",
    "updatedAt": "2026-10-20T14:00:00+08:00"
  }
}
```

#### 3.3.3 查询课程详情

**接口**：`GET /api/v1/courses/{courseId}`  
**权限**：[student, teacher, school_admin, district_admin, city_admin, province_admin, question_admin]  
**说明**：查询课程详情及章节数量；学生仅可查看已发布课程。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| courseId | path | number | 是 | 课程 ID |

**响应数据（data）**：`CourseItem`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 6001,
    "name": "七年级音乐鉴赏",
    "subject": "music",
    "grade": 7,
    "description": "依据义务教育艺术课程标准设置",
    "chapterCount": 6,
    "sortOrder": 1,
    "status": "active",
    "createdAt": "2026-09-01T09:00:00+08:00",
    "updatedAt": "2026-09-01T09:00:00+08:00"
  }
}
```

#### 3.3.4 修改课程

**接口**：`PATCH /api/v1/courses/{courseId}`  
**权限**：[question_admin]  
**说明**：修改课程信息；修改学科/年级前需校验已关联试题是否仍匹配。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| courseId | path | number | 是 | 课程 ID |
| name | body | string | 否 | 课程名称 |
| subject | body | string | 否 | 学科 |
| grade | body | number | 否 | 年级 |
| description | body | string | 否 | 课程简介 |
| sortOrder | body | number | 否 | 排序值 |
| status | body | string | 否 | `active` / `disabled` |

**响应数据（data）**：`CourseItem`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 6001,
    "name": "七年级音乐鉴赏（2026 修订）",
    "subject": "music",
    "grade": 7,
    "description": "依据义务教育艺术课程标准设置",
    "chapterCount": 6,
    "sortOrder": 1,
    "status": "active",
    "createdAt": "2026-09-01T09:00:00+08:00",
    "updatedAt": "2026-10-20T14:10:00+08:00"
  }
}
```

#### 3.3.5 删除课程

**接口**：`DELETE /api/v1/courses/{courseId}`  
**权限**：[question_admin]  
**说明**：课程下存在章节或试题时拒绝删除，返回 `409`；可先停用课程。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| courseId | path | number | 是 | 课程 ID |

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "deleted": true,
    "courseId": 6002
  }
}
```

### 3.4 章节管理

#### 3.4.1 查询课程章节

**接口**：`GET /api/v1/courses/{courseId}/chapters`  
**权限**：[student, teacher, school_admin, district_admin, city_admin, province_admin, question_admin]  
**说明**：按 `sortOrder` 升序返回课程全部章节，不分页；学生仅可查看已发布课程的章节。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| courseId | path | number | 是 | 课程 ID |

**响应数据（data）**：`array<ChapterItem>`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "id": 6101,
      "courseId": 6001,
      "courseName": "七年级音乐鉴赏",
      "name": "第一单元 节奏与节拍",
      "description": "认识常见拍号与节拍规律",
      "questionCount": 18,
      "sortOrder": 1,
      "createdAt": "2026-09-01T09:10:00+08:00",
      "updatedAt": "2026-09-10T09:10:00+08:00"
    },
    {
      "id": 6102,
      "courseId": 6001,
      "courseName": "七年级音乐鉴赏",
      "name": "第二单元 旋律与音色",
      "description": "感受旋律走向与乐器音色",
      "questionCount": 22,
      "sortOrder": 2,
      "createdAt": "2026-09-01T09:20:00+08:00",
      "updatedAt": "2026-09-10T09:20:00+08:00"
    }
  ]
}
```

#### 3.4.2 创建章节

**接口**：`POST /api/v1/courses/{courseId}/chapters`  
**权限**：[question_admin]  
**说明**：在指定课程下创建章节。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| courseId | path | number | 是 | 课程 ID |
| name | body | string | 是 | 章节名称 |
| description | body | string | 否 | 章节简介 |
| sortOrder | body | number | 否 | 排序值，默认 0 |

**响应数据（data）**：`ChapterItem`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 6103,
    "courseId": 6001,
    "courseName": "七年级音乐鉴赏",
    "name": "第三单元 民族音乐",
    "description": "中国民族音乐赏析",
    "questionCount": 0,
    "sortOrder": 3,
    "createdAt": "2026-10-20T14:20:00+08:00",
    "updatedAt": "2026-10-20T14:20:00+08:00"
  }
}
```

#### 3.4.3 查询章节详情

**接口**：`GET /api/v1/chapters/{chapterId}`  
**权限**：[student, teacher, school_admin, district_admin, city_admin, province_admin, question_admin]  
**说明**：查询章节详情；学生仅可查看已发布章节。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| chapterId | path | number | 是 | 章节 ID |

**响应数据（data）**：`ChapterItem`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 6101,
    "courseId": 6001,
    "courseName": "七年级音乐鉴赏",
    "name": "第一单元 节奏与节拍",
    "description": "认识常见拍号与节拍规律",
    "questionCount": 18,
    "sortOrder": 1,
    "createdAt": "2026-09-01T09:10:00+08:00",
    "updatedAt": "2026-09-10T09:10:00+08:00"
  }
}
```

#### 3.4.4 修改章节

**接口**：`PATCH /api/v1/chapters/{chapterId}`  
**权限**：[question_admin]  
**说明**：修改章节名称、简介和排序。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| chapterId | path | number | 是 | 章节 ID |
| name | body | string | 否 | 章节名称 |
| description | body | string | 否 | 章节简介 |
| sortOrder | body | number | 否 | 排序值 |

**响应数据（data）**：`ChapterItem`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 6101,
    "courseId": 6001,
    "courseName": "七年级音乐鉴赏",
    "name": "第一单元 节奏、节拍与拍号",
    "description": "认识常见拍号与节拍规律",
    "questionCount": 18,
    "sortOrder": 1,
    "createdAt": "2026-09-01T09:10:00+08:00",
    "updatedAt": "2026-10-20T14:30:00+08:00"
  }
}
```

#### 3.4.5 删除章节

**接口**：`DELETE /api/v1/chapters/{chapterId}`  
**权限**：[question_admin]  
**说明**：章节下存在试题时拒绝删除，返回 `409`。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| chapterId | path | number | 是 | 章节 ID |

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "deleted": true,
    "chapterId": 6103
  }
}
```

### 3.5 试题资源管理

#### 3.5.1 上传试题资源

**接口**：`POST /api/v1/questions/{questionId}/resources`  
**权限**：[teacher, question_admin]  
**Content-Type**：`multipart/form-data`  
**说明**：为试题上传图片或音频。教师仅可为本人创建且未发布试题上传；单题建议最多 5 个图片、3 个音频。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| questionId | path | number | 是 | 试题 ID |
| files | formData | array<file> | 是 | 图片或音频文件，可多选 |
| type | formData | string | 是 | `image` / `audio` |

请求示例（curl）：

```bash
curl -X POST "https://api.example.com/api/v1/questions/9001/resources" \
  -H "Authorization: Bearer <token>" \
  -F "files=@melody.mp3" \
  -F "type=audio"
```

**响应数据（data）**：`array<QuestionResource>`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "resourceId": 9102,
      "fileId": 88010,
      "type": "audio",
      "url": "https://cdn.example.com/question_audio/88010.mp3",
      "name": "melody.mp3",
      "mimeType": "audio/mpeg",
      "size": 2097152,
      "createdAt": "2026-10-20T14:40:00+08:00"
    }
  ]
}
```

#### 3.5.2 删除试题资源

**接口**：`DELETE /api/v1/questions/{questionId}/resources/{resourceId}`  
**权限**：[teacher, question_admin]  
**说明**：删除试题资源关联；被已发布试卷快照引用的资源不得删除。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| questionId | path | number | 是 | 试题 ID |
| resourceId | path | number | 是 | 资源关联 ID |

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "deleted": true,
    "questionId": 9001,
    "resourceId": 9102
  }
}
```

### 3.6 操作日志查询

#### 3.6.1 查询操作日志列表

**接口**：`GET /api/v1/logs`  
**权限**：[question_admin, province_admin]  
**说明**：查询账号、题库、课程、章节、资源等操作日志。题库管理员默认仅查看题库域日志；省级管理员可查看全省管理日志。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| operatorId | query | number | 否 | 操作人 ID |
| action | query | string | 否 | 操作类型，如 `question.review` |
| resourceType | query | string | 否 | 资源类型 |
| resourceId | query | number | 否 | 资源 ID |
| result | query | string | 否 | `success` / `failed` |
| keyword | query | string | 否 | 操作说明关键词 |
| startTime | query | string | 否 | 开始时间，ISO 8601 |
| endTime | query | string | 否 | 结束时间，ISO 8601 |
| pageNum | query | number | 否 | 页码，默认 1 |
| pageSize | query | number | 否 | 每页条数，默认 10 |

**响应数据（data）**：`Page<OperationLogItem>`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 1,
    "pages": 1,
    "list": [
      {
        "id": 12001,
        "operatorId": 7001,
        "operatorName": "题库管理员",
        "role": "question_admin",
        "action": "question.review",
        "resourceType": "question",
        "resourceId": 9001,
        "description": "审核试题 9001：通过",
        "ip": "10.0.0.15",
        "userAgent": "Mozilla/5.0",
        "result": "success",
        "createdAt": "2026-10-20T15:00:00+08:00"
      }
    ]
  }
}
```

#### 3.6.2 查询操作日志详情

**接口**：`GET /api/v1/logs/{logId}`  
**权限**：[question_admin, province_admin]  
**说明**：查询单条操作日志。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| logId | path | number | 是 | 日志 ID |

**响应数据（data）**：`OperationLogItem`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 12001,
    "operatorId": 7001,
    "operatorName": "题库管理员",
    "role": "question_admin",
    "action": "question.review",
    "resourceType": "question",
    "resourceId": 9001,
    "description": "审核试题 9001：通过",
    "ip": "10.0.0.15",
    "userAgent": "Mozilla/5.0",
    "result": "success",
    "createdAt": "2026-10-20T15:00:00+08:00"
  }
}
```

## 4. 模块三：测评核心业务

> 后端负责人：万逸恒（后端 A）  
> 覆盖：组卷、测评发布与撤回、答题与自动提交、自动判分、成绩统计与补录导入、证书、成长曲线。

### 4.1 数据模型

#### PaperQuestion（试卷题目快照）

| 字段 | 类型 | 说明 |
|---|---|---|
| questionId | number | 试题 ID |
| order | number | 题目顺序，从 1 开始 |
| sectionName | string | 大题/分区名称，如“听力选择” |
| type | string | 题型 |
| stem | string | 题干快照 |
| score | number | 本卷中该题分值 |

#### PaperItem（试卷列表项）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | number | 试卷 ID |
| title | string | 试卷名称 |
| subject | string | 学科 |
| paperType | string | `practice` / `formal` |
| grade | number | 年级 |
| scopeType | string | 组卷归属层级 |
| scopeId | number | 归属组织或班级 ID |
| scopeName | string | 归属名称 |
| totalScore | number | 总分 |
| questionCount | number | 题目数量 |
| duration | number | 建议时长，单位分钟 |
| generateMode | string | `manual` / `auto` |
| status | string | 试卷状态 |
| creatorId | number | 创建人 ID |
| creatorName | string | 创建人姓名 |
| createdAt | string | 创建时间 |
| updatedAt | string | 更新时间 |

#### PaperDetail（试卷详情）

包含 `PaperItem` 全部字段，并增加：

| 字段 | 类型 | 说明 |
|---|---|---|
| instructions | string / null | 考试说明；未填写时为 `null` |
| questions | array<PaperQuestion> | 题目快照列表 |

#### AssessmentItem（测评任务）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | number | 测评 ID |
| title | string | 测评名称 |
| paperId | number | 试卷 ID |
| paperTitle | string | 试卷名称 |
| subject | string | 学科 |
| paperType | string | `practice` / `formal` |
| targetType | string | `class` / `school` / `district` / `city` / `province` |
| targetIds | array<number> | 发布目标 ID 列表 |
| targetNames | array<string> | 发布目标名称列表 |
| targetGrades | array<number> | 目标年级；空数组表示不限年级 |
| startTime | string | 开始时间 |
| endTime | string | 结束时间 |
| duration | number | 单次答题时长，单位分钟 |
| attemptLimit | number | 允许作答次数 |
| showAnswerMode | string | `never` / `after_submit` / `after_end` |
| status | string | `published` / `withdrawn` / `finished` |
| publisherId | number | 发布人 ID |
| publisherName | string | 发布人姓名 |
| publishedAt | string | 发布时间 |
| participantCount | number | 应参与人数 |
| submittedCount | number | 已提交人数 |

#### AttemptQuestion（答题题目）

| 字段 | 类型 | 说明 |
|---|---|---|
| questionId | number | 试题 ID |
| order | number | 顺序 |
| type | string | 题型 |
| stem | string | 题干 |
| score | number | 分值 |
| options | array | 选项；元素为 `{key:string, text:string, mediaUrl:string/null}`；非选择题为空数组 |
| resources | array | 资源；元素为 `{type:string, url:string, name:string}` |
| answerConfig | object | 作答配置，如 `{blankCount:2, maxLength:500}` |

> 答题接口绝不下发 `answer`、`analysis` 等标准答案字段；`serverTime` 与 `deadline` 用于前端倒计时，服务器时间为唯一权威。

#### AttemptDetail（答卷详情）

| 字段 | 类型 | 说明 |
|---|---|---|
| attemptId | number | 答题记录 ID |
| assessmentId | number | 测评 ID |
| paperId | number | 试卷 ID |
| title | string | 测评名称 |
| subject | string | 学科 |
| attemptNo | number | 第几次作答 |
| status | string | `in_progress` / `submitted` / `graded` / `invalid` |
| startedAt | string | 开始作答时间 |
| deadline | string | 本次作答截止时间 |
| serverTime | string | 服务器当前时间 |
| remainingSeconds | number | 剩余秒数 |
| totalScore | number | 试卷总分 |
| questions | array<AttemptQuestion> | 题目列表 |
| savedAnswers | array<AnswerItem> | 已保存答案 |

#### AnswerItem（答案）

| 字段 | 类型 | 说明 |
|---|---|---|
| questionId | number | 试题 ID |
| answer | object | 按题型提交的答案对象 |
| updatedAt | string | 最后保存时间 |

#### SubmitResult（交卷结果）

| 字段 | 类型 | 说明 |
|---|---|---|
| attemptId | number | 答题记录 ID |
| status | string | 答卷状态 |
| submittedAt | string | 交卷时间 |
| autoSubmitted | boolean | 是否为到时自动交卷 |
| objectiveScore | number | 客观题得分 |
| subjectiveScore | number | 主观题得分 |
| aiScore | number | AI 辅助评分 |
| totalScore | number | 当前总分 |
| gradingStatus | string | 判分状态 |
| message | string | 结果提示 |

#### ScoreItem（成绩列表项）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | number | 成绩 ID |
| attemptId | number / null | 关联答题记录；补录/导入时可为空 |
| assessmentId | number | 测评 ID |
| assessmentTitle | string | 测评名称 |
| subject | string | 学科 |
| studentId | number | 学生 ID |
| studentName | string | 学生姓名 |
| studentNo | string | 学籍号 |
| classId | number | 班级 ID |
| className | string | 班级名称 |
| schoolId | number | 学校 ID |
| schoolName | string | 学校名称 |
| objectiveScore | number | 客观题得分 |
| subjectiveScore | number | 主观题得分 |
| aiScore | number | AI 辅助评分 |
| totalScore | number | 总分 |
| level | string | `excellent` / `good` / `pass` / `fail` |
| classRank | number / null | 班级排名 |
| gradeRank | number / null | 年级排名 |
| status | string | `pending` / `grading` / `graded` / `failed` |
| source | string | `online` / `manual` / `import` |
| gradedAt | string / null | 完成判分时间 |
| createdAt | string | 创建时间 |

#### ScoreDetail（成绩详情）

包含 `ScoreItem` 全部字段，并增加：

| 字段 | 类型 | 说明 |
|---|---|---|
| answerDetails | array | 逐题明细，元素为 `{questionId,order,stem,studentAnswer,correctAnswer,score,maxScore,comment,aiAnalysis}` |
| answerVisible | boolean | 当前用户当前时点是否允许查看标准答案与解析 |
| certificateId | number / null | 对应证书 ID |

#### GradingTaskItem（待评分任务）

| 字段 | 类型 | 说明 |
|---|---|---|
| attemptId | number | 答卷 ID |
| assessmentId | number | 测评 ID |
| assessmentTitle | string | 测评名称 |
| subject | string | 学科 |
| studentId | number | 学生 ID |
| studentName | string | 学生姓名 |
| studentNo | string | 学籍号 |
| classId | number | 班级 ID |
| className | string | 班级名称 |
| submittedAt | string | 交卷时间 |
| gradingStatus | string | `pending` / `grading` / `failed` |
| objectiveScore | number | 客观题得分 |
| currentScore | number | 当前主观题/AI 合计得分 |
| maxScore | number | 试卷总分 |
| subjectiveCount | number | 待人工评分题数 |
| aiCount | number | AI 评分待确认题数 |
| pendingCount | number | 尚未完成评分的题目总数 |

#### GradingQuestionItem（人工评分题目）

| 字段 | 类型 | 说明 |
|---|---|---|
| questionId | number | 试题 ID |
| order | number | 题目顺序 |
| type | string | 题型 |
| stem | string | 题干 |
| studentAnswer | object | 学生答案；未作答为 `null` |
| correctAnswer | object / null | 参考答案；无标准答案时为 `null` |
| rubric | string / null | 评分要点/量规 |
| maxScore | number | 本题满分 |
| currentScore | number / null | 当前已记录得分；未评分为 `null` |
| aiScore | number / null | AI 辅助分；无 AI 结果为 `null` |
| aiAnalysis | string / null | AI 评语 |
| comment | string / null | 教师评语；未填写为 `null` |

#### GradingAttemptDetail（人工评分详情）

| 字段 | 类型 | 说明 |
|---|---|---|
| attemptId | number | 答卷 ID |
| assessmentId | number | 测评 ID |
| assessmentTitle | string | 测评名称 |
| subject | string | 学科 |
| studentId | number | 学生 ID |
| studentName | string | 学生姓名 |
| studentNo | string | 学籍号 |
| classId | number | 班级 ID |
| className | string | 班级名称 |
| submittedAt | string | 交卷时间 |
| status | string | 答卷状态 |
| gradingStatus | string | 判分状态 |
| objectiveScore | number | 客观题得分 |
| subjectiveScore | number | 主观题当前得分 |
| aiScore | number | AI 辅助得分 |
| totalScore | number | 当前总分 |
| maxScore | number | 试卷总分 |
| version | number | 评分版本号，用于并发控制 |
| canFinalize | boolean | 是否所有主观题均已评分，可以提交终评 |
| questions | array<GradingQuestionItem> | 需要人工评分的题目及上下文 |

#### GradingSubmitResult（人工评分提交结果）

| 字段 | 类型 | 说明 |
|---|---|---|
| attemptId | number | 答卷 ID |
| scoreId | number | 成绩 ID |
| gradingStatus | string | `grading` / `graded` / `failed` |
| subjectiveScore | number | 主观题得分 |
| totalScore | number | 更新后的总分 |
| finalized | boolean | 是否已完成终评 |
| updatedAt | string | 更新时间 |

#### StatOverview（成绩统计）

| 字段 | 类型 | 说明 |
|---|---|---|
| dimension | string | 统计维度：`assessment` / `class` / `school` / `district` / `city` / `province` |
| targetId | number | 统计对象 ID |
| targetName | string | 统计对象名称 |
| rank | number / null | 当前排序规则下的名次；单对象汇总时为 `null` |
| assessmentId | number / null | 测评 ID；按测评统计时返回 |
| subject | string | 学科 |
| studentCount | number | 应参与学生数 |
| participantCount | number | 实际参与人数 |
| submittedCount | number | 已提交人数 |
| participationRate | number | 参与率，0~1 |
| avgScore | number | 平均分 |
| highestScore | number | 最高分 |
| lowestScore | number | 最低分 |
| excellentRate | number | 优秀率，0~1 |
| goodRate | number | 良好率，0~1 |
| passRate | number | 合格率，0~1 |
| distribution | array | 分数段分布，元素为 `{range:string,count:number}` |
| bySubject | array | 分学科统计，元素为 `{subject:string,avgScore:number,participationRate:number}` |

#### CertificateItem（证书）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | number | 证书 ID |
| certificateNo | string | 证书编号，全局唯一 |
| studentId | number | 学生 ID |
| studentName | string | 学生姓名 |
| assessmentId | number | 测评 ID |
| assessmentTitle | string | 测评名称 |
| subject | string | 学科 |
| score | number | 测评总分 |
| level | string | 等级 |
| issueDate | string | 发证日期 |
| status | string | `generating` / `ready` / `failed` |
| downloadUrl | string / null | 下载地址；未生成完成时为 null |
| createdAt | string | 创建时间 |

#### GrowthCurve（成长曲线）

| 字段 | 类型 | 说明 |
|---|---|---|
| studentId | number | 学生 ID |
| studentName | string | 学生姓名 |
| subject | string | 学科 |
| range | object | 查询范围 `{startDate:string,endDate:string}` |
| points | array | 趋势点，元素为 `{assessmentId:number,assessmentName:string,date:string,score:number,classAvg:number,schoolAvg:number}` |
| summary | object | 汇总 `{latestScore:number,avgScore:number,bestScore:number,trend:string,changeRate:number}`；`trend` 为 `up/down/stable` |

### 4.2 组卷管理

> 组卷规则：教师只能为任教班级创建练习卷/正式卷；学校及以上管理员可在本级或下级范围组卷。试卷发布后形成题目快照，之后修改题库不会影响已发布测评。

#### 4.2.1 查询试卷列表

**接口**：`GET /api/v1/papers`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：按学科、类型、层级、状态和关键词分页查询权限范围内试卷。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| subject | query | string | 否 | 学科 |
| paperType | query | string | 否 | `practice` / `formal` |
| grade | query | number | 否 | 年级 |
| scopeType | query | string | 否 | 归属层级 |
| status | query | string | 否 | 试卷状态 |
| keyword | query | string | 否 | 试卷名称模糊搜索 |
| pageNum | query | number | 否 | 页码，默认 1 |
| pageSize | query | number | 否 | 每页条数，默认 10 |

**响应数据（data）**：`Page<PaperItem>`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 1,
    "pages": 1,
    "list": [
      {
        "id": 11001,
        "title": "2026 秋季七年级音乐期中测评卷",
        "subject": "music",
        "paperType": "formal",
        "grade": 7,
        "scopeType": "class",
        "scopeId": 5001,
        "scopeName": "七年级（1）班",
        "totalScore": 100,
        "questionCount": 20,
        "duration": 45,
        "generateMode": "manual",
        "status": "ready",
        "creatorId": 2001,
        "creatorName": "李老师",
        "createdAt": "2026-10-21T09:00:00+08:00",
        "updatedAt": "2026-10-21T09:30:00+08:00"
      }
    ]
  }
}
```

#### 4.2.2 手动组卷

**接口**：`POST /api/v1/papers/manual`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：按指定试题和分值手动创建试卷；题目必须为已通过状态，学科、年级需与试卷一致。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| title | body | string | 是 | 试卷名称 |
| subject | body | string | 是 | 学科 |
| paperType | body | string | 是 | `practice` / `formal` |
| grade | body | number | 是 | 年级 |
| scopeType | body | string | 是 | 归属层级；教师固定为 `class` |
| scopeId | body | number | 是 | 班级/学校/区县/市州/省 ID |
| duration | body | number | 是 | 建议时长，1~300 分钟 |
| instructions | body | string | 否 | 考试说明 |
| status | body | string | 否 | `draft` / `ready`，默认 `draft` |
| questions | body | array | 是 | 题目配置，元素为 `{questionId:number, order:number, sectionName:string, score:number}` |

请求示例：

```json
{
  "title": "2026 秋季七年级音乐期中测评卷",
  "subject": "music",
  "paperType": "formal",
  "grade": 7,
  "scopeType": "class",
  "scopeId": 5001,
  "duration": 45,
  "instructions": "请独立完成，听力题音频播放两遍。",
  "status": "ready",
  "questions": [
    {
      "questionId": 9001,
      "order": 1,
      "sectionName": "听力选择",
      "score": 5
    },
    {
      "questionId": 9002,
      "order": 2,
      "sectionName": "听力选择",
      "score": 5
    }
  ]
}
```

**响应数据（data）**：`PaperDetail`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 11001,
    "title": "2026 秋季七年级音乐期中测评卷",
    "subject": "music",
    "paperType": "formal",
    "grade": 7,
    "scopeType": "class",
    "scopeId": 5001,
    "scopeName": "七年级（1）班",
    "totalScore": 100,
    "questionCount": 20,
    "duration": 45,
    "generateMode": "manual",
    "status": "ready",
    "creatorId": 2001,
    "creatorName": "李老师",
    "createdAt": "2026-10-21T09:00:00+08:00",
    "updatedAt": "2026-10-21T09:00:00+08:00",
    "instructions": "请独立完成，听力题音频播放两遍。",
    "questions": [
      {
        "questionId": 9001,
        "order": 1,
        "sectionName": "听力选择",
        "type": "single_choice",
        "stem": "聆听音频，判断这段旋律的拍号。",
        "score": 5
      },
      {
        "questionId": 9002,
        "order": 2,
        "sectionName": "听力选择",
        "type": "single_choice",
        "stem": "聆听音频，判断主奏乐器。",
        "score": 5
      }
    ]
  }
}
```

#### 4.2.3 自动随机组卷

**接口**：`POST /api/v1/papers/auto`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：按题型、难度、数量、课程/章节范围随机抽题。题库不足时返回 `409`，并说明缺口；同一次抽题不应重复选题。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| title | body | string | 是 | 试卷名称 |
| subject | body | string | 是 | 学科 |
| paperType | body | string | 是 | `practice` / `formal` |
| grade | body | number | 是 | 年级 |
| scopeType | body | string | 是 | 归属层级 |
| scopeId | body | number | 是 | 归属对象 ID |
| duration | body | number | 是 | 时长，分钟 |
| courseIds | body | array | 否 | 限定课程 ID 列表 |
| chapterIds | body | array | 否 | 限定章节 ID 列表 |
| rules | body | array | 是 | 抽题规则，元素为 `{type:string,difficulty:number / null,count:number,scorePerQuestion:number}` |
| status | body | string | 否 | `draft` / `ready`，默认 `draft` |
| instructions | body | string | 否 | 考试说明 |

请求示例：

```json
{
  "title": "七年级音乐节奏专项练习",
  "subject": "music",
  "paperType": "practice",
  "grade": 7,
  "scopeType": "class",
  "scopeId": 5001,
  "duration": 30,
  "courseIds": [6001],
  "chapterIds": [6101],
  "rules": [
    {
      "type": "single_choice",
      "difficulty": 2,
      "count": 10,
      "scorePerQuestion": 4
    },
    {
      "type": "listening",
      "difficulty": null,
      "count": 5,
      "scorePerQuestion": 6
    }
  ],
  "status": "ready",
  "instructions": "系统随机组卷，共 15 题。"
}
```

**响应数据（data）**：`PaperDetail`；`generateMode` 为 `auto`。

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 11002,
    "title": "七年级音乐节奏专项练习",
    "subject": "music",
    "paperType": "practice",
    "grade": 7,
    "scopeType": "class",
    "scopeId": 5001,
    "scopeName": "七年级（1）班",
    "totalScore": 70,
    "questionCount": 15,
    "duration": 30,
    "generateMode": "auto",
    "status": "ready",
    "creatorId": 2001,
    "creatorName": "李老师",
    "createdAt": "2026-10-21T10:00:00+08:00",
    "updatedAt": "2026-10-21T10:00:00+08:00",
    "instructions": "系统随机组卷，共 15 题。",
    "questions": [
      {
        "questionId": 9021,
        "order": 1,
        "sectionName": "选择题",
        "type": "single_choice",
        "stem": "下列哪个拍号表示以四分音符为一拍、每小节三拍？",
        "score": 4
      },
      {
        "questionId": 9022,
        "order": 2,
        "sectionName": "听赏题",
        "type": "listening",
        "stem": "聆听音频，判断乐曲的速度变化。",
        "score": 6
      }
    ]
  }
}
```

#### 4.2.4 查询试卷详情

**接口**：`GET /api/v1/papers/{paperId}`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：查询试卷及题目快照；已发布试卷的题目顺序和分值不可再修改。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| paperId | path | number | 是 | 试卷 ID |

**响应数据（data）**：`PaperDetail`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 11001,
    "title": "2026 秋季七年级音乐期中测评卷",
    "subject": "music",
    "paperType": "formal",
    "grade": 7,
    "scopeType": "class",
    "scopeId": 5001,
    "scopeName": "七年级（1）班",
    "totalScore": 100,
    "questionCount": 20,
    "duration": 45,
    "generateMode": "manual",
    "status": "ready",
    "creatorId": 2001,
    "creatorName": "李老师",
    "createdAt": "2026-10-21T09:00:00+08:00",
    "updatedAt": "2026-10-21T09:30:00+08:00",
    "instructions": "请独立完成，听力题音频播放两遍。",
    "questions": [
      {
        "questionId": 9001,
        "order": 1,
        "sectionName": "听力选择",
        "type": "single_choice",
        "stem": "聆听音频，判断这段旋律的拍号。",
        "score": 5
      }
    ]
  }
}
```

#### 4.2.5 修改试卷

**接口**：`PATCH /api/v1/papers/{paperId}`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：仅允许修改 `draft` / `ready` 且未被测评引用的试卷。已用于发布的试卷只能复制为新试卷后修改。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| paperId | path | number | 是 | 试卷 ID |
| title | body | string | 否 | 试卷名称 |
| duration | body | number | 否 | 时长 |
| instructions | body | string | 否 | 考试说明 |
| questions | body | array | 否 | 完整题目配置；传入时整体替换 |
| status | body | string | 否 | `draft` / `ready` |

**响应数据（data）**：`PaperDetail`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 11001,
    "title": "2026 秋季七年级音乐期中测评卷（修订）",
    "subject": "music",
    "paperType": "formal",
    "grade": 7,
    "scopeType": "class",
    "scopeId": 5001,
    "scopeName": "七年级（1）班",
    "totalScore": 100,
    "questionCount": 20,
    "duration": 50,
    "generateMode": "manual",
    "status": "draft",
    "creatorId": 2001,
    "creatorName": "李老师",
    "createdAt": "2026-10-21T09:00:00+08:00",
    "updatedAt": "2026-10-21T10:20:00+08:00",
    "instructions": "请独立完成，听力题音频播放两遍。",
    "questions": []
  }
}
```

#### 4.2.6 暂存试卷

**接口**：`PATCH /api/v1/papers/{paperId}/draft`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：保存未完成的组卷内容，允许题目不完整、总分暂不平衡；服务端只做基础类型校验，不执行发布校验。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| paperId | path | number | 是 | 试卷 ID |
| title | body | string | 否 | 试卷名称 |
| duration | body | number | 否 | 时长 |
| instructions | body | string | 否 | 考试说明 |
| questions | body | array | 否 | 当前题目配置，可只含部分题目 |

**响应数据（data）**：`PaperDetail`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 11001,
    "title": "2026 秋季七年级音乐期中测评卷",
    "subject": "music",
    "paperType": "formal",
    "grade": 7,
    "scopeType": "class",
    "scopeId": 5001,
    "scopeName": "七年级（1）班",
    "totalScore": 20,
    "questionCount": 4,
    "duration": 45,
    "generateMode": "manual",
    "status": "draft",
    "creatorId": 2001,
    "creatorName": "李老师",
    "createdAt": "2026-10-21T09:00:00+08:00",
    "updatedAt": "2026-10-21T10:30:00+08:00",
    "instructions": "请独立完成，听力题音频播放两遍。",
    "questions": []
  }
}
```

#### 4.2.7 删除试卷

**接口**：`DELETE /api/v1/papers/{paperId}`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：仅可删除 `draft` / `ready` 且未被测评引用的试卷；已发布测评引用的试卷返回 `409`。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| paperId | path | number | 是 | 试卷 ID |

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "deleted": true,
    "paperId": 11002
  }
}
```

#### 4.2.8 下载试卷音频/图片材料

**接口**：`GET /api/v1/papers/{paperId}/materials/download`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：将试卷内听赏音频、图片等资源打包为 ZIP，供教师线下播放、打印或备份。仅返回当前账号数据范围内的试卷；学生不可调用。资源文件从 MinIO 流式读取，不返回 MinIO 内部地址。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| paperId | path | number | 是 | 试卷 ID |
| questionIds | query | string | 否 | 逗号分隔的试题 ID；不传表示全卷 |
| types | query | string | 否 | `audio` / `image`；不传表示全部资源 |

成功响应头示例：

```http
HTTP/1.1 200 OK
Content-Type: application/zip
Content-Disposition: attachment; filename="paper-11001-materials.zip"
X-Resource-Count: 12
```

失败仍返回统一 JSON：试卷不存在 `404`，无权限 `403`，试卷没有可下载资源 `409`。

#### 4.2.9 下载试卷答案与解析

**接口**：`GET /api/v1/papers/{paperId}/answers/download`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：导出试卷标准答案、评分要点和解析，供教师阅卷与讲评。学生端在任何情况下都不可调用；前端不得把下载地址缓存到公共 CDN。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| paperId | path | number | 是 | 试卷 ID |
| format | query | string | 否 | `pdf` / `docx`，默认 `pdf` |
| includeAnalysis | query | boolean | 否 | 是否包含解析，默认 `true` |
| includeRubric | query | boolean | 否 | 是否包含评分量规，默认 `true` |

成功响应头示例：

```http
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Disposition: attachment; filename="paper-11001-answers.pdf"
```

> 答案文件属于敏感数据：必须校验数据范围，下载行为写入操作日志，签名 URL 有效期不超过 5 分钟。

#### 4.2.10 学生随机练习组卷

**接口**：`POST /api/v1/papers/practice/random`  
**权限**：[student]  
**说明**：学生按学科、年级、章节和题型随机生成一套练习卷，并立即创建本人练习答卷。服务端从 `approved` 试题中抽题，题目顺序随机，试卷类型固定为 `practice`，不占用正式测评次数。返回 `AttemptDetail`，后续保存答案、交卷、查看成绩复用答题与成绩接口。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| subject | body | string | 是 | `music` / `art` |
| grade | body | number | 否 | 年级；不传使用学生当前年级 |
| courseId | body | number | 否 | 限定课程 |
| chapterId | body | number | 否 | 限定章节 |
| questionCount | body | number | 否 | 题目数量，默认 10，范围 1~30 |
| difficulty | body | number | 否 | 难度 1~5；不传为混合难度 |
| questionTypes | body | array<string> | 否 | 限定题型；不传为混合题型 |

请求示例：

```json
{
  "subject": "music",
  "grade": 7,
  "chapterId": 3301,
  "questionCount": 10,
  "questionTypes": ["single_choice", "listening"]
}
```

**响应数据（data）**：`AttemptDetail`

响应示例（节选）：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "attemptId": 13088,
    "assessmentId": 12990,
    "paperId": 11990,
    "title": "七年级音乐随机练习",
    "subject": "music",
    "attemptNo": 1,
    "status": "in_progress",
    "startedAt": "2026-10-20T19:00:00+08:00",
    "deadline": "2026-10-20T19:40:00+08:00",
    "serverTime": "2026-10-20T19:00:00+08:00",
    "remainingSeconds": 2400,
    "totalScore": 100,
    "questions": [],
    "savedAnswers": []
  }
}
```

规则：

- 题库中符合条件的试题不足 `questionCount` 时返回 `409`，并给出可用数量。
- 练习卷不进入学校/区域统计，不计入正式测评参与率，不生成证书。
- 提交后按 `showAnswerMode=after_submit` 展示答案与解析。
- 同一学生可多次生成练习卷，每次生成新的 `assessmentId` / `paperId` / `attemptId`。

### 4.3 测评发布与撤回

#### 4.3.1 查询测评列表

**接口**：`GET /api/v1/assessments`  
**权限**：[student, teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：学生只返回发布给本人所在班级/学校且符合年级的测评；教师和管理员按数据范围返回。支持音乐、美术两类测评。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| subject | query | string | 否 | `music` / `art` |
| status | query | string | 否 | `published` / `withdrawn` / `finished` |
| paperType | query | string | 否 | `practice` / `formal` |
| targetType | query | string | 否 | 发布层级 |
| keyword | query | string | 否 | 测评名称模糊搜索 |
| pageNum | query | number | 否 | 页码，默认 1 |
| pageSize | query | number | 否 | 每页条数，默认 10 |

**响应数据（data）**：`Page<AssessmentItem>`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 1,
    "pages": 1,
    "list": [
      {
        "id": 12001,
        "title": "2026 秋季七年级音乐正式测评",
        "paperId": 11001,
        "paperTitle": "2026 秋季七年级音乐期中测评卷",
        "subject": "music",
        "paperType": "formal",
        "targetType": "class",
        "targetIds": [5001],
        "targetNames": ["七年级（1）班"],
        "targetGrades": [7],
        "startTime": "2026-10-25T09:00:00+08:00",
        "endTime": "2026-10-25T18:00:00+08:00",
        "duration": 45,
        "attemptLimit": 1,
        "showAnswerMode": "after_end",
        "status": "published",
        "publisherId": 2001,
        "publisherName": "李老师",
        "publishedAt": "2026-10-21T11:00:00+08:00",
        "participantCount": 42,
        "submittedCount": 0
      }
    ]
  }
}
```

#### 4.3.2 发布测评

**接口**：`POST /api/v1/assessments`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：将试卷发布到班级、学校、区县、市州或省。音乐/美术由试卷的 `subject` 决定，无需单独传学科。发布时对试卷题目生成快照。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| paperId | body | number | 是 | 已就绪的试卷 ID |
| title | body | string | 是 | 测评名称 |
| targetType | body | string | 是 | `class` / `school` / `district` / `city` / `province` |
| targetIds | body | array<number> | 是 | 发布目标 ID 数组；教师只能传任教班级 ID |
| targetGrades | body | array<number> | 否 | 目标年级；学校及以上可用，空数组表示不限 |
| startTime | body | string | 是 | 开始时间 |
| endTime | body | string | 是 | 结束时间，必须晚于开始时间 |
| attemptLimit | body | number | 否 | 允许作答次数，默认 1 |
| shuffleQuestions | body | boolean | 否 | 是否打乱题目顺序，默认 `false` |
| shuffleOptions | body | boolean | 否 | 是否打乱选项顺序，默认 `false` |
| showAnswerMode | body | string | 否 | `never` / `after_submit` / `after_end`，默认 `after_end` |
| allowLateSubmit | body | boolean | 否 | 截止后是否允许宽限提交，默认 `false` |
| instructions | body | string | 否 | 测评说明 |

请求示例：

```json
{
  "paperId": 11001,
  "title": "2026 秋季七年级音乐正式测评",
  "targetType": "class",
  "targetIds": [5001],
  "targetGrades": [7],
  "startTime": "2026-10-25T09:00:00+08:00",
  "endTime": "2026-10-25T18:00:00+08:00",
  "attemptLimit": 1,
  "shuffleQuestions": true,
  "shuffleOptions": true,
  "showAnswerMode": "after_end",
  "allowLateSubmit": false,
  "instructions": "请在规定时间内完成，逾期系统自动交卷。"
}
```

**响应数据（data）**：`AssessmentItem`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 12001,
    "title": "2026 秋季七年级音乐正式测评",
    "paperId": 11001,
    "paperTitle": "2026 秋季七年级音乐期中测评卷",
    "subject": "music",
    "paperType": "formal",
    "targetType": "class",
    "targetIds": [5001],
    "targetNames": ["七年级（1）班"],
    "targetGrades": [7],
    "startTime": "2026-10-25T09:00:00+08:00",
    "endTime": "2026-10-25T18:00:00+08:00",
    "duration": 45,
    "attemptLimit": 1,
    "showAnswerMode": "after_end",
    "status": "published",
    "publisherId": 2001,
    "publisherName": "李老师",
    "publishedAt": "2026-10-21T11:00:00+08:00",
    "participantCount": 42,
    "submittedCount": 0
  }
}
```

#### 4.3.3 查询测评详情

**接口**：`GET /api/v1/assessments/{assessmentId}`  
**权限**：[student, teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：学生只能查看发布给本人的测评；不会返回标准答案。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| assessmentId | path | number | 是 | 测评 ID |

**响应数据（data）**：`AssessmentItem`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 12001,
    "title": "2026 秋季七年级音乐正式测评",
    "paperId": 11001,
    "paperTitle": "2026 秋季七年级音乐期中测评卷",
    "subject": "music",
    "paperType": "formal",
    "targetType": "class",
    "targetIds": [5001],
    "targetNames": ["七年级（1）班"],
    "targetGrades": [7],
    "startTime": "2026-10-25T09:00:00+08:00",
    "endTime": "2026-10-25T18:00:00+08:00",
    "duration": 45,
    "attemptLimit": 1,
    "showAnswerMode": "after_end",
    "status": "published",
    "publisherId": 2001,
    "publisherName": "李老师",
    "publishedAt": "2026-10-21T11:00:00+08:00",
    "participantCount": 42,
    "submittedCount": 18
  }
}
```

#### 4.3.4 撤回测评

**接口**：`POST /api/v1/assessments/{assessmentId}/withdraw`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：撤回尚未结束的测评。撤回后学生不可再开始新作答；已提交答卷有效，已开始未提交的答卷由服务端按规则结束并保存已答内容。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| assessmentId | path | number | 是 | 测评 ID |
| reason | body | string | 是 | 撤回原因，写入审计日志 |

**响应数据（data）**：`AssessmentItem`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 12001,
    "title": "2026 秋季七年级音乐正式测评",
    "paperId": 11001,
    "paperTitle": "2026 秋季七年级音乐期中测评卷",
    "subject": "music",
    "paperType": "formal",
    "targetType": "class",
    "targetIds": [5001],
    "targetNames": ["七年级（1）班"],
    "targetGrades": [7],
    "startTime": "2026-10-25T09:00:00+08:00",
    "endTime": "2026-10-25T18:00:00+08:00",
    "duration": 45,
    "attemptLimit": 1,
    "showAnswerMode": "after_end",
    "status": "withdrawn",
    "publisherId": 2001,
    "publisherName": "李老师",
    "publishedAt": "2026-10-21T11:00:00+08:00",
    "participantCount": 42,
    "submittedCount": 18
  }
}
```

### 4.4 答题与自动提交

#### 4.4.1 开始或继续答题

**接口**：`POST /api/v1/assessments/{assessmentId}/attempts`  
**权限**：[student]  
**说明**：开始一次作答；若存在未提交且未超时的答卷，则直接返回该答卷用于续答。服务端计算 `deadline = min(开始时间 + duration, 测评结束时间)`。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| assessmentId | path | number | 是 | 测评 ID |
| deviceType | body | string | 否 | `web` / `mobile` / `tablet`，用于审计 |

请求示例：

```json
{
  "deviceType": "web"
}
```

**响应数据（data）**：`AttemptDetail`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "attemptId": 13001,
    "assessmentId": 12001,
    "paperId": 11001,
    "title": "2026 秋季七年级音乐正式测评",
    "subject": "music",
    "attemptNo": 1,
    "status": "in_progress",
    "startedAt": "2026-10-25T09:05:00+08:00",
    "deadline": "2026-10-25T09:50:00+08:00",
    "serverTime": "2026-10-25T09:05:00+08:00",
    "remainingSeconds": 2700,
    "totalScore": 100,
    "questions": [
      {
        "questionId": 9001,
        "order": 1,
        "type": "single_choice",
        "stem": "聆听音频，判断这段旋律的拍号。",
        "score": 5,
        "options": [
          { "key": "A", "text": "2/4", "mediaUrl": null },
          { "key": "B", "text": "3/4", "mediaUrl": null },
          { "key": "C", "text": "4/4", "mediaUrl": null },
          { "key": "D", "text": "6/8", "mediaUrl": null }
        ],
        "resources": [
          {
            "type": "audio",
            "url": "https://cdn.example.com/question_audio/88002.mp3",
            "name": "question-9001.mp3"
          }
        ],
        "answerConfig": {}
      }
    ],
    "savedAnswers": []
  }
}
```

#### 4.4.2 获取答卷详情

**接口**：`GET /api/v1/attempts/{attemptId}`  
**权限**：[student]  
**说明**：刷新页面、断线重连后恢复题目、已保存答案和剩余时间。不得返回标准答案。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| attemptId | path | number | 是 | 答题记录 ID |

**响应数据（data）**：`AttemptDetail`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "attemptId": 13001,
    "assessmentId": 12001,
    "paperId": 11001,
    "title": "2026 秋季七年级音乐正式测评",
    "subject": "music",
    "attemptNo": 1,
    "status": "in_progress",
    "startedAt": "2026-10-25T09:05:00+08:00",
    "deadline": "2026-10-25T09:50:00+08:00",
    "serverTime": "2026-10-25T09:20:00+08:00",
    "remainingSeconds": 1800,
    "totalScore": 100,
    "questions": [
      {
        "questionId": 9001,
        "order": 1,
        "type": "single_choice",
        "stem": "聆听音频，判断这段旋律的拍号。",
        "score": 5,
        "options": [
          { "key": "A", "text": "2/4", "mediaUrl": null },
          { "key": "B", "text": "3/4", "mediaUrl": null },
          { "key": "C", "text": "4/4", "mediaUrl": null },
          { "key": "D", "text": "6/8", "mediaUrl": null }
        ],
        "resources": [],
        "answerConfig": {}
      }
    ],
    "savedAnswers": [
      {
        "questionId": 9001,
        "answer": { "value": "B" },
        "updatedAt": "2026-10-25T09:12:30+08:00"
      }
    ]
  }
}
```

#### 4.4.3 保存答案

**接口**：`PATCH /api/v1/attempts/{attemptId}/answers`  
**权限**：[student]  
**说明**：自动保存或批量保存答案。建议前端每 10~15 秒调用一次，并在切题时调用；只保存，不判分。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| attemptId | path | number | 是 | 答题记录 ID |
| answers | body | array | 是 | 答案列表，元素为 `{questionId:number, answer:object, clientUpdatedAt:string}` |
| clientUpdatedAt | body | string | 否 | 客户端更新时间，用于冲突审计；服务器时间仍为最终依据 |

请求示例：

```json
{
  "answers": [
    {
      "questionId": 9001,
      "answer": { "value": "B" },
      "clientUpdatedAt": "2026-10-25T09:12:30+08:00"
    },
    {
      "questionId": 9002,
      "answer": { "value": "A" },
      "clientUpdatedAt": "2026-10-25T09:12:30+08:00"
    }
  ]
}
```

**响应数据（data）**

| 字段 | 类型 | 说明 |
|---|---|---|
| savedCount | number | 成功保存的答案数量 |
| savedAt | string | 服务端保存时间 |
| serverTime | string | 服务器当前时间 |
| remainingSeconds | number | 剩余秒数 |

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "savedCount": 2,
    "savedAt": "2026-10-25T09:12:31+08:00",
    "serverTime": "2026-10-25T09:12:31+08:00",
    "remainingSeconds": 2249
  }
}
```

#### 4.4.4 提交答卷

**接口**：`POST /api/v1/attempts/{attemptId}/submit`  
**权限**：[student]  
**说明**：学生主动交卷。服务端同时用于到时自动交卷：定时任务在 `deadline` 触发，使用同一判分与落库流程，前端无需调用自动提交接口。

**自动提交规则**：

1. 服务端定时任务扫描 `in_progress` 且 `deadline <= now` 的答卷，自动提交并标记 `autoSubmitted=true`、`submitType=auto`。
2. 网络中断时，已保存答案不会丢失；未保存的答案以最后成功保存内容为准。
3. 交卷接口必须幂等：重复提交返回第一次交卷结果，不重复生成成绩。
4. 客观题在提交后立即自动判分；主观题、作品题进入人工或 AI 辅助评分，`gradingStatus` 先返回 `grading`。
5. 超过 `deadline` 后默认拒绝学生手动提交；若测评开启 `allowLateSubmit`，仅允许在配置的宽限期内提交。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| attemptId | path | number | 是 | 答题记录 ID |
| finalAnswers | body | array | 否 | 交卷前最后一次答案，可避免与自动保存产生竞态 |
| submitType | body | string | 否 | 学生端固定传 `manual`；服务端内部使用 `auto` |

请求示例：

```json
{
  "submitType": "manual",
  "finalAnswers": [
    {
      "questionId": 9002,
      "answer": { "value": "A" }
    }
  ]
}
```

**响应数据（data）**：`SubmitResult`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "attemptId": 13001,
    "status": "submitted",
    "submittedAt": "2026-10-25T09:44:10+08:00",
    "autoSubmitted": false,
    "objectiveScore": 35,
    "subjectiveScore": 0,
    "aiScore": 0,
    "totalScore": 35,
    "gradingStatus": "grading",
    "message": "交卷成功，主观题评分中"
  }
}
```

### 4.5 成绩管理

> 路由顺序：后端必须把 `/scores/me`、`/scores/statistics`、`/scores/statistics/list`、`/scores/statistics/export` 等静态路由注册在 `/scores/{scoreId}` 之前，并将路径参数声明为 `{score_id:int}`。人工评分接口统一放在本节末尾。

#### 4.5.1 查询本人成绩

**接口**：`GET /api/v1/scores/me`  
**权限**：[student]  
**说明**：分页查询本人音乐/美术测评成绩。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| subject | query | string | 否 | 学科 |
| assessmentId | query | number | 否 | 测评 ID |
| pageNum | query | number | 否 | 页码，默认 1 |
| pageSize | query | number | 否 | 每页条数，默认 10 |

**响应数据（data）**：`Page<ScoreItem>`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 1,
    "pages": 1,
    "list": [
      {
        "id": 14001,
        "attemptId": 13001,
        "assessmentId": 12001,
        "assessmentTitle": "2026 秋季七年级音乐正式测评",
        "subject": "music",
        "studentId": 1001,
        "studentName": "王小明",
        "studentNo": "S20260001",
        "classId": 5001,
        "className": "七年级（1）班",
        "schoolId": 301,
        "schoolName": "示范中学",
        "objectiveScore": 35,
        "subjectiveScore": 48,
        "aiScore": 5,
        "totalScore": 88,
        "level": "good",
        "classRank": 3,
        "gradeRank": 18,
        "status": "graded",
        "source": "online",
        "gradedAt": "2026-10-25T10:30:00+08:00",
        "createdAt": "2026-10-25T09:44:10+08:00"
      }
    ]
  }
}
```

#### 4.5.2 查询成绩列表

**接口**：`GET /api/v1/scores`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：按测评、班级、学校、区域、学科等条件查询成绩；教师仅能查询任教班级。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| assessmentId | query | number | 否 | 测评 ID |
| subject | query | string | 否 | 学科 |
| studentKeyword | query | string | 否 | 学生姓名/学号/账号 |
| classId | query | number | 否 | 班级 ID |
| schoolId | query | number | 否 | 学校 ID |
| districtId | query | number | 否 | 区县 ID |
| cityId | query | number | 否 | 市州 ID |
| grade | query | number | 否 | 年级 |
| level | query | string | 否 | 成绩等级 |
| source | query | string | 否 | `online` / `manual` / `import` |
| startTime | query | string | 否 | 创建时间起 |
| endTime | query | string | 否 | 创建时间止 |
| pageNum | query | number | 否 | 页码，默认 1 |
| pageSize | query | number | 否 | 每页条数，默认 10 |

**响应数据（data）**：`Page<ScoreItem>`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 1,
    "pages": 1,
    "list": [
      {
        "id": 14001,
        "attemptId": 13001,
        "assessmentId": 12001,
        "assessmentTitle": "2026 秋季七年级音乐正式测评",
        "subject": "music",
        "studentId": 1001,
        "studentName": "王小明",
        "studentNo": "S20260001",
        "classId": 5001,
        "className": "七年级（1）班",
        "schoolId": 301,
        "schoolName": "示范中学",
        "objectiveScore": 35,
        "subjectiveScore": 48,
        "aiScore": 5,
        "totalScore": 88,
        "level": "good",
        "classRank": 3,
        "gradeRank": 18,
        "status": "graded",
        "source": "online",
        "gradedAt": "2026-10-25T10:30:00+08:00",
        "createdAt": "2026-10-25T09:44:10+08:00"
      }
    ]
  }
}
```

#### 4.5.3 查询班级/区域成绩统计

**接口**：`GET /api/v1/scores/statistics`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：按班级、学校、区县、市州、省或单个测评统计平均分、参与率、优秀率、合格率和分数段分布。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| dimension | query | string | 是 | `assessment` / `class` / `school` / `district` / `city` / `province` |
| targetId | query | number | 条件必填 | 统计对象 ID；`province` 可传本省 ID，`assessment` 必传测评 ID |
| assessmentId | query | number | 否 | 测评 ID |
| subject | query | string | 否 | 学科 |
| grade | query | number | 否 | 年级 |
| startDate | query | string | 否 | 统计开始日期 |
| endDate | query | string | 否 | 统计结束日期 |

**响应数据（data）**：`StatOverview`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "dimension": "class",
    "targetId": 5001,
    "targetName": "七年级（1）班",
    "assessmentId": 12001,
    "subject": "music",
    "studentCount": 42,
    "participantCount": 40,
    "submittedCount": 39,
    "participationRate": 0.9524,
    "avgScore": 82.36,
    "highestScore": 96,
    "lowestScore": 58,
    "excellentRate": 0.2308,
    "goodRate": 0.5128,
    "passRate": 0.9231,
    "distribution": [
      { "range": "90-100", "count": 9 },
      { "range": "80-89", "count": 20 },
      { "range": "70-79", "count": 7 },
      { "range": "60-69", "count": 3 },
      { "range": "0-59", "count": 1 }
    ],
    "bySubject": [
      {
        "subject": "music",
        "avgScore": 82.36,
        "participationRate": 0.9524
      }
    ]
  }
}
```

#### 4.5.4 分页查询区域统计列表/排名

**接口**：`GET /api/v1/scores/statistics/list`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：按指定维度返回**多行**统计数据，用于管理端表格、区域对比和排名。单对象汇总使用 `GET /scores/statistics`；本接口用于“一个父节点下的多个子节点”。省级“全省各地区参与率”使用 `groupBy=city`，市级使用 `groupBy=district`，区县使用 `groupBy=school`。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| groupBy | query | string | 是 | 分组维度：`class` / `school` / `district` / `city`；返回每行一个对象 |
| parentId | query | number | 条件必填 | 父级 ID：区县查学校传 `districtId`，市州查区县传 `cityId`，省查市州不传或传省 ID；必须在数据范围内 |
| assessmentId | query | number | 否 | 限定某个测评；不传表示时间范围内全部测评 |
| subject | query | string | 否 | 学科 |
| grade | query | number | 否 | 年级 |
| keyword | query | string | 否 | 目标名称模糊搜索，如学校名、区县名 |
| startDate | query | string | 否 | 统计开始日期 |
| endDate | query | string | 否 | 统计结束日期 |
| sortBy | query | string | 否 | `avgScore` / `participationRate` / `passRate` / `excellentRate` / `studentCount`，默认 `avgScore` |
| sortOrder | query | string | 否 | `asc` / `desc`，默认 `desc` |
| pageNum | query | number | 否 | 页码，默认 1 |
| pageSize | query | number | 否 | 每页条数，默认 10，最大 100 |

权限与分组约束：

| 角色 | 允许的 groupBy | 说明 |
|---|---|---|
| teacher | `class` | 仅任教班级 |
| school_admin | `class` / `school` | 本校班级或本校汇总 |
| district_admin | `class` / `school` / `district` | 本区县及下级 |
| city_admin | `class` / `school` / `district` / `city` | 本市州及下级 |
| province_admin | `class` / `school` / `district` / `city` | 全省及下级 |

**响应数据（data）**：`Page<StatOverview>`，每行必须包含 `rank`。`rank` 按排序字段全局计算，不受分页影响；排序字段相同时按 `targetId` 升序稳定排序。

请求示例：

```http
GET /api/v1/scores/statistics/list?groupBy=city&assessmentId=12001&subject=music&sortBy=participationRate&sortOrder=desc&pageNum=1&pageSize=10
```

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 2,
    "pages": 1,
    "list": [
      {
        "rank": 1,
        "dimension": "city",
        "targetId": 3,
        "targetName": "示例市",
        "assessmentId": 12001,
        "subject": "music",
        "studentCount": 12600,
        "participantCount": 11970,
        "submittedCount": 11880,
        "participationRate": 0.95,
        "avgScore": 81.42,
        "highestScore": 98,
        "lowestScore": 41,
        "excellentRate": 0.21,
        "goodRate": 0.47,
        "passRate": 0.91,
        "distribution": [
          { "range": "90-100", "count": 2514 },
          { "range": "80-89", "count": 5922 },
          { "range": "70-79", "count": 2079 },
          { "range": "60-69", "count": 891 },
          { "range": "0-59", "count": 474 }
        ],
        "bySubject": [
          { "subject": "music", "avgScore": 81.42, "participationRate": 0.95 }
        ]
      },
      {
        "rank": 2,
        "dimension": "city",
        "targetId": 4,
        "targetName": "示例第二市",
        "assessmentId": 12001,
        "subject": "music",
        "studentCount": 9800,
        "participantCount": 9016,
        "submittedCount": 8930,
        "participationRate": 0.92,
        "avgScore": 79.86,
        "highestScore": 96,
        "lowestScore": 38,
        "excellentRate": 0.17,
        "goodRate": 0.44,
        "passRate": 0.88,
        "distribution": [
          { "range": "90-100", "count": 1533 },
          { "range": "80-89", "count": 4340 },
          { "range": "70-79", "count": 1787 },
          { "range": "60-69", "count": 803 },
          { "range": "0-59", "count": 467 }
        ],
        "bySubject": [
          { "subject": "music", "avgScore": 79.86, "participationRate": 0.92 }
        ]
      }
    ]
  }
}
```

#### 4.5.5 查询成绩详情

**接口**：`GET /api/v1/scores/{scoreId}`  
**权限**：[student, teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：查询逐题得分与解析。学生是否可见标准答案由 `showAnswerMode` 和 `answerVisible` 控制。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| scoreId | path | number | 是 | 成绩 ID |

**响应数据（data）**：`ScoreDetail`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 14001,
    "attemptId": 13001,
    "assessmentId": 12001,
    "assessmentTitle": "2026 秋季七年级音乐正式测评",
    "subject": "music",
    "studentId": 1001,
    "studentName": "王小明",
    "studentNo": "S20260001",
    "classId": 5001,
    "className": "七年级（1）班",
    "schoolId": 301,
    "schoolName": "示范中学",
    "objectiveScore": 35,
    "subjectiveScore": 48,
    "aiScore": 5,
    "totalScore": 88,
    "level": "good",
    "classRank": 3,
    "gradeRank": 18,
    "status": "graded",
    "source": "online",
    "gradedAt": "2026-10-25T10:30:00+08:00",
    "createdAt": "2026-10-25T09:44:10+08:00",
    "answerVisible": true,
    "certificateId": 15001,
    "answerDetails": [
      {
        "questionId": 9001,
        "order": 1,
        "stem": "聆听音频，判断这段旋律的拍号。",
        "studentAnswer": { "value": "B" },
        "correctAnswer": { "value": "B" },
        "score": 5,
        "maxScore": 5,
        "comment": "回答正确",
        "aiAnalysis": null
      },
      {
        "questionId": 9010,
        "order": 10,
        "stem": "分析乐曲的情绪与节奏特点。",
        "studentAnswer": { "text": "乐曲节奏明快，情绪热烈。" },
        "correctAnswer": { "text": "旋律跳跃、节奏鲜明，整体情绪欢快热烈。" },
        "score": 12,
        "maxScore": 15,
        "comment": "要点基本完整，可补充力度变化。",
        "aiAnalysis": "答案覆盖节奏与情绪，但未提及力度层次。"
      }
    ]
  }
}
```

#### 4.5.6 成绩补录

**接口**：`POST /api/v1/scores/manual`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：教师或各级管理员在权限范围内为学生补录线下测评成绩。补录必须填写原因并保存操作日志；同一学生同一测评重复补录时默认返回 `409`，只有显式 `overwrite=true` 才覆盖。`studentId` 必须属于当前账号数据范围。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| studentId | body | number | 是 | 学生 ID |
| assessmentId | body | number | 是 | 测评 ID |
| subject | body | string | 是 | 学科，必须与测评一致 |
| scoreItems | body | array | 是 | 分项得分，元素为 `{name:string,score:number,maxScore:number}` |
| totalScore | body | number | 否 | 总分；不传则按分项求和 |
| reason | body | string | 是 | 补录原因 |
| evidenceFileIds | body | array | 否 | 佐证材料文件 ID |
| overwrite | body | boolean | 否 | 是否覆盖已有成绩，默认 `false` |

请求示例：

```json
{
  "studentId": 1001,
  "assessmentId": 12001,
  "subject": "music",
  "scoreItems": [
    { "name": "演唱", "score": 36, "maxScore": 40 },
    { "name": "课堂表现", "score": 18, "maxScore": 20 }
  ],
  "totalScore": 54,
  "reason": "学生因病参加线下补测",
  "evidenceFileIds": [88020],
  "overwrite": false
}
```

**响应数据（data）**：`ScoreItem`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 14002,
    "attemptId": null,
    "assessmentId": 12001,
    "assessmentTitle": "2026 秋季七年级音乐正式测评",
    "subject": "music",
    "studentId": 1001,
    "studentName": "王小明",
    "studentNo": "S20260001",
    "classId": 5001,
    "className": "七年级（1）班",
    "schoolId": 301,
    "schoolName": "示范中学",
    "objectiveScore": 0,
    "subjectiveScore": 54,
    "aiScore": 0,
    "totalScore": 54,
    "level": "pass",
    "classRank": null,
    "gradeRank": null,
    "status": "graded",
    "source": "manual",
    "gradedAt": "2026-10-26T09:00:00+08:00",
    "createdAt": "2026-10-26T09:00:00+08:00"
  }
}
```

#### 4.5.7 批量导入线下成绩

**接口**：`POST /api/v1/scores/import`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**Content-Type**：`multipart/form-data`  
**说明**：在权限范围内导入同一测评的线下成绩，按学籍号匹配学生。逐行校验并支持部分成功；超过 500 行时进入 RQ 异步处理，前端通过返回的 `taskId` 轮询导入结果。所有学生必须属于当前账号数据范围，否则该行失败。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| file | formData | file | 是 | CSV/XLSX，最大 10 MB |
| assessmentId | formData | number | 是 | 测评 ID |
| subject | formData | string | 是 | 学科，必须与测评一致 |
| overwrite | formData | boolean | 否 | 是否覆盖已有成绩，默认 `false` |

模板列：`学籍号,姓名,客观题得分,主观题得分,AI得分,总分,备注`。  
校验规则：学籍号必须属于测评目标范围；总分不得超过试卷总分；同一文件内学籍号不可重复。

请求示例（curl）：

```bash
curl -X POST "https://api.example.com/api/v1/scores/import" \
  -H "Authorization: Bearer <token>" \
  -F "file=@offline_scores.xlsx" \
  -F "assessmentId=12001" \
  -F "subject=music" \
  -F "overwrite=false"
```

**响应数据（data）**

| 字段 | 类型 | 说明 |
|---|---|---|
| taskId | string | 导入任务 ID |
| status | string | `completed` / `queued` / `failed`；小文件同步完成，大文件排队 |
| total | number | 总行数 |
| successCount | number | 成功条数 |
| failCount | number | 失败条数 |
| errors | array | 失败明细 `{row:number,studentNo:string,message:string}` |

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "taskId": "IMP202610260001",
    "status": "completed",
    "total": 40,
    "successCount": 38,
    "failCount": 2,
    "errors": [
      {
        "row": 9,
        "studentNo": "S20260009",
        "message": "该学生不属于本测评目标范围"
      },
      {
        "row": 21,
        "studentNo": "S20260021",
        "message": "总分超过试卷满分"
      }
    ]
  }
}
```

#### 4.5.8 重新判分

**接口**：`POST /api/v1/scores/{scoreId}/regrade`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：用于 AI 评分失败或评分规则调整后重新计算总分。**重新判分不等于人工逐题打分**；教师逐题改分使用 `PATCH /grading/attempts/{attemptId}/scores`。重新判分需记录操作人、原因和原分数，并只允许在数据范围内操作。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| scoreId | path | number | 是 | 成绩 ID |
| reason | body | string | 是 | 重新判分原因 |
| aiReevaluate | body | boolean | 否 | 是否重新调用 AI，默认 `false` |

**响应数据（data）**：`ScoreItem`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 14001,
    "attemptId": 13001,
    "assessmentId": 12001,
    "assessmentTitle": "2026 秋季七年级音乐正式测评",
    "subject": "music",
    "studentId": 1001,
    "studentName": "王小明",
    "studentNo": "S20260001",
    "classId": 5001,
    "className": "七年级（1）班",
    "schoolId": 301,
    "schoolName": "示范中学",
    "objectiveScore": 35,
    "subjectiveScore": 50,
    "aiScore": 5,
    "totalScore": 90,
    "level": "excellent",
    "classRank": 2,
    "gradeRank": 12,
    "status": "graded",
    "source": "online",
    "gradedAt": "2026-10-26T10:00:00+08:00",
    "createdAt": "2026-10-25T09:44:10+08:00"
  }
}
```

#### 4.5.9 导出成绩统计

**接口**：`GET /api/v1/scores/statistics/export`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：导出 XLSX。`groupBy` 有值时，按 `GET /scores/statistics/list` 的多行结果导出，用于省级“全省各地区参与率”等表格；不传 `groupBy` 时，按 `dimension + targetId` 导出单对象汇总。`dimension=student` 时导出该学生全部正式测评成绩明细，供教师端“导出学生所有成绩”使用。成功响应为二进制流，不使用统一 JSON 包装。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| groupBy | query | string | 否 | `class` / `school` / `district` / `city`；传入时导出多行统计列表 |
| parentId | query | number | 条件必填 | `groupBy` 的父级 ID，规则同统计列表接口 |
| dimension | query | string | 条件必填 | 单对象导出时的统计维度；`assessment` / `class` / `school` / `district` / `city` / `province` / `student`；与 `groupBy` 二选一 |
| targetId | query | number | 条件必填 | 单对象导出时的统计对象 ID |
| assessmentId | query | number | 否 | 测评 ID |
| subject | query | string | 否 | 学科 |
| grade | query | number | 否 | 年级 |
| startDate | query | string | 否 | 开始日期 |
| endDate | query | string | 否 | 结束日期 |
| sortBy | query | string | 否 | 多行导出排序字段 |
| sortOrder | query | string | 否 | `asc` / `desc` |

成功响应头示例：

```http
HTTP/1.1 200 OK
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="score-statistics-20261020.xlsx"
```

失败响应示例（JSON）：

```json
{
  "code": 403,
  "message": "无权导出该范围数据",
  "data": null
}
```


#### 4.5.10 查询待人工评分任务

**接口**：`GET /api/v1/grading/tasks`  
**权限**：[teacher, school_admin]  
**说明**：查询权限范围内已交卷、但仍存在主观题或 AI 评分待确认的答卷。教师仅能看到任教班级；学校管理员可看本校。任务按交卷时间升序排列，优先处理等待最久的答卷。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| assessmentId | query | number | 否 | 测评 ID |
| classId | query | number | 否 | 班级 ID |
| subject | query | string | 否 | 学科 |
| gradingStatus | query | string | 否 | `pending` / `grading` / `failed`；默认全部未完成 |
| keyword | query | string | 否 | 学生姓名/学号 |
| pageNum | query | number | 否 | 页码，默认 1 |
| pageSize | query | number | 否 | 每页条数，默认 10 |

**响应数据（data）**：`Page<GradingTaskItem>`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 1,
    "pages": 1,
    "list": [
      {
        "attemptId": 13001,
        "assessmentId": 12001,
        "assessmentTitle": "2026 秋季七年级音乐正式测评",
        "subject": "music",
        "studentId": 1001,
        "studentName": "王小明",
        "studentNo": "S20260001",
        "classId": 5001,
        "className": "七年级（1）班",
        "submittedAt": "2026-10-25T09:44:10+08:00",
        "gradingStatus": "grading",
        "objectiveScore": 35,
        "currentScore": 53,
        "maxScore": 100,
        "subjectiveCount": 2,
        "aiCount": 1,
        "pendingCount": 2
      }
    ]
  }
}
```

#### 4.5.11 查询人工评分详情

**接口**：`GET /api/v1/grading/attempts/{attemptId}`  
**权限**：[teacher, school_admin]  
**说明**：返回学生答案、参考答案、评分要点、AI 辅助分和当前得分，供教师逐题打分。与 `GET /attempts/{attemptId}` 不同，本接口用于评分，允许在教师权限范围内返回标准答案；学生永远不可访问。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| attemptId | path | number | 是 | 答卷 ID，必须处于已交卷状态且在数据范围内 |

**响应数据（data）**：`GradingAttemptDetail`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "attemptId": 13001,
    "assessmentId": 12001,
    "assessmentTitle": "2026 秋季七年级音乐正式测评",
    "subject": "music",
    "studentId": 1001,
    "studentName": "王小明",
    "studentNo": "S20260001",
    "classId": 5001,
    "className": "七年级（1）班",
    "submittedAt": "2026-10-25T09:44:10+08:00",
    "status": "submitted",
    "gradingStatus": "grading",
    "objectiveScore": 35,
    "subjectiveScore": 5,
    "aiScore": 0,
    "totalScore": 40,
    "maxScore": 100,
    "version": 3,
    "canFinalize": false,
    "questions": [
      {
        "questionId": 9010,
        "order": 10,
        "type": "short_answer",
        "stem": "分析乐曲的情绪与节奏特点。",
        "studentAnswer": { "text": "乐曲节奏明快，情绪热烈。" },
        "correctAnswer": { "text": "旋律跳跃、节奏鲜明，整体情绪欢快热烈。" },
        "rubric": "情绪 5 分；节奏 5 分；力度/音色 5 分。",
        "maxScore": 15,
        "currentScore": null,
        "aiScore": 12,
        "aiAnalysis": "答案覆盖节奏与情绪，但未提及力度层次。",
        "comment": null
      },
      {
        "questionId": 9011,
        "order": 11,
        "type": "audio_upload",
        "stem": "上传一段 60 秒的歌曲演唱音频。",
        "studentAnswer": {
          "fileId": 88030,
          "url": "https://minio.example.com/student-work/88030.mp3"
        },
        "correctAnswer": null,
        "rubric": "音准 10 分；节奏 10 分；表现力 5 分。",
        "maxScore": 25,
        "currentScore": 5,
        "aiScore": 21,
        "aiAnalysis": "音准较好，高音区略有偏差，节奏稳定。",
        "comment": "待教师确认"
      }
    ]
  }
}
```

#### 4.5.12 提交人工评分

**接口**：`PATCH /api/v1/grading/attempts/{attemptId}/scores`  
**权限**：[teacher, school_admin]  
**说明**：教师逐题或批量提交主观题得分。只允许修改需要人工评分的题目；分值必须在 `0~maxScore` 之间。`finalize=true` 时要求所有待评分题目都已给分，服务端重新汇总客观题、主观题和 AI 辅助分，写入最终成绩并记录评分日志。该接口与“重新判分”不同，是正式测评人工评分的唯一入口。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| attemptId | path | number | 是 | 答卷 ID |
| items | body | array | 是 | 评分项，元素为 `{questionId:number, score:number, comment:string/null}`；至少 1 项 |
| finalize | body | boolean | 否 | 是否完成终评，默认 `false`；为 `true` 时必须覆盖全部待评分题目 |
| reason | body | string | 否 | 终评说明；`finalize=true` 时建议填写 |
| version | body | number | 否 | 评分版本号；传入时用于并发控制，不一致返回 `409` |

请求示例：

```json
{
  "items": [
    {
      "questionId": 9010,
      "score": 13,
      "comment": "情绪与节奏概括准确，补充力度变化可得满分。"
    },
    {
      "questionId": 9011,
      "score": 22,
      "comment": "音准和节奏稳定，高音区仍需气息支撑。"
    }
  ],
  "finalize": true,
  "reason": "完成主观题与作品题人工评分",
  "version": 3
}
```

**响应数据（data）**：`GradingSubmitResult`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "attemptId": 13001,
    "scoreId": 14001,
    "gradingStatus": "graded",
    "subjectiveScore": 35,
    "totalScore": 90,
    "finalized": true,
    "updatedAt": "2026-10-25T10:30:00+08:00"
  }
}
```

> 并发与权限：两名教师同时评分时，`version` 不一致的一方返回 `409` 并提示刷新；教师不得给非任教班级评分，学校管理员不得跨校评分。终评后再次修改必须走“重新判分”并填写原因，保留原评分记录。

### 4.6 证书管理

#### 4.6.1 生成测评证书

**接口**：`POST /api/v1/certificates/generate`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：为已完成判分的学生批量生成证书。未判分、缺考或成绩无效的学生跳过。可由定时任务在正式测评结束后自动触发，也可手动重试。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| assessmentId | body | number | 是 | 测评 ID |
| subject | body | string | 是 | 学科，必须与测评一致 |
| studentIds | body | array | 否 | 指定学生；为空表示全部符合条件学生 |
| templateId | body | number | 否 | 证书模板 ID |
| forceRegenerate | body | boolean | 否 | 是否已存在时重新生成，默认 `false` |

请求示例：

```json
{
  "assessmentId": 12001,
  "subject": "music",
  "studentIds": [1001, 1002],
  "templateId": 1,
  "forceRegenerate": false
}
```

**响应数据（data）**

| 字段 | 类型 | 说明 |
|---|---|---|
| taskId | string | 生成任务 ID |
| status | string | `generating` / `ready` / `failed` |
| generatedCount | number | 已生成数量 |
| skippedCount | number | 跳过数量 |

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "taskId": "CERT202610260001",
    "status": "generating",
    "generatedCount": 0,
    "skippedCount": 1
  }
}
```

#### 4.6.2 查询证书列表

**接口**：`GET /api/v1/certificates`  
**权限**：[student, teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：学生只能查询本人证书；教师和管理员按权限范围查询。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| assessmentId | query | number | 否 | 测评 ID |
| subject | query | string | 否 | 学科 |
| studentKeyword | query | string | 否 | 学生姓名/学号 |
| status | query | string | 否 | 证书状态 |
| pageNum | query | number | 否 | 页码，默认 1 |
| pageSize | query | number | 否 | 每页条数，默认 10 |

**响应数据（data）**：`Page<CertificateItem>`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 1,
    "pages": 1,
    "list": [
      {
        "id": 15001,
        "certificateNo": "YS2026-MUSIC-000001",
        "studentId": 1001,
        "studentName": "王小明",
        "assessmentId": 12001,
        "assessmentTitle": "2026 秋季七年级音乐正式测评",
        "subject": "music",
        "score": 88,
        "level": "good",
        "issueDate": "2026-10-26",
        "status": "ready",
        "downloadUrl": "https://cdn.example.com/certificates/15001.pdf",
        "createdAt": "2026-10-26T11:00:00+08:00"
      }
    ]
  }
}
```

#### 4.6.3 查询证书详情

**接口**：`GET /api/v1/certificates/{certificateId}`  
**权限**：[student, teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：查询证书编号、成绩、等级与下载状态。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| certificateId | path | number | 是 | 证书 ID |

**响应数据（data）**：`CertificateItem`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 15001,
    "certificateNo": "YS2026-MUSIC-000001",
    "studentId": 1001,
    "studentName": "王小明",
    "assessmentId": 12001,
    "assessmentTitle": "2026 秋季七年级音乐正式测评",
    "subject": "music",
    "score": 88,
    "level": "good",
    "issueDate": "2026-10-26",
    "status": "ready",
    "downloadUrl": "https://cdn.example.com/certificates/15001.pdf",
    "createdAt": "2026-10-26T11:00:00+08:00"
  }
}
```

#### 4.6.4 下载证书

**接口**：`GET /api/v1/certificates/{certificateId}/download`  
**权限**：[student, teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：下载 PDF 证书。学生仅能下载本人证书；证书未生成完成时返回 `409`。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| certificateId | path | number | 是 | 证书 ID |

成功响应头示例：

```http
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Disposition: attachment; filename="certificate-YS2026-MUSIC-000001.pdf"
```

失败响应示例（JSON）：

```json
{
  "code": 400,
  "message": "证书尚未生成完成",
  "data": null
}
```

### 4.7 学生成长曲线

#### 4.7.1 查询学生历史成绩趋势

**接口**：`GET /api/v1/students/{studentId}/growth-curve`  
**权限**：[student, teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：返回学生音乐或美术正式测评成绩趋势、班级均分与学校均分。学生只能查询本人；教师和管理员按数据范围查询。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| studentId | path | number | 是 | 学生 ID |
| subject | query | string | 是 | `music` / `art` |
| startDate | query | string | 否 | 开始日期 |
| endDate | query | string | 否 | 结束日期 |
| includePractice | query | boolean | 否 | 是否包含练习测评，默认 `false` |

**响应数据（data）**：`GrowthCurve`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "studentId": 1001,
    "studentName": "王小明",
    "subject": "music",
    "range": {
      "startDate": "2026-01-01",
      "endDate": "2026-10-20"
    },
    "points": [
      {
        "assessmentId": 11001,
        "assessmentName": "2026 春季音乐测评",
        "date": "2026-04-15",
        "score": 76,
        "classAvg": 74.2,
        "schoolAvg": 73.8
      },
      {
        "assessmentId": 12001,
        "assessmentName": "2026 秋季七年级音乐正式测评",
        "date": "2026-10-25",
        "score": 88,
        "classAvg": 82.36,
        "schoolAvg": 80.91
      }
    ],
    "summary": {
      "latestScore": 88,
      "avgScore": 82,
      "bestScore": 88,
      "trend": "up",
      "changeRate": 0.1579
    }
  }
}
```

#### 4.7.2 查询学生学情报告

**接口**：`GET /api/v1/students/{studentId}/learning-report`  
**权限**：[student, teacher, school_admin, district_admin, city_admin, province_admin]  
**说明**：读取已生成并落库的学情报告，不在请求线程内调用模型。学生只能读取本人报告；教师和管理员只能读取权限范围内学生。报告不存在时返回 `404`，需要先在后台生成。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| studentId | path | number | 是 | 学生 ID |
| subject | query | string | 否 | `music` / `art`；不传返回最近一份报告 |
| reportId | query | string | 否 | 指定报告 ID；不传返回最新报告 |

**响应数据（data）**：`LearningReportResult`

响应示例（节选）：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "reportId": "LR202610250001",
    "studentId": 1001,
    "subject": "music",
    "generatedAt": "2026-10-25T12:00:00+08:00",
    "summary": "本学年音乐成绩稳步提升，节奏与听辨表现较好，乐曲分析和音准稳定性仍需加强。",
    "strengths": ["节拍识别准确", "听辨题正确率较高"],
    "weaknesses": ["高音区音准波动", "乐曲分析缺少力度与音色维度"],
    "suggestions": ["每周进行 2 次高音区模唱", "使用四步分析框架完成主观题"],
    "scoreTrend": [
      { "date": "2026-04-15", "score": 76 },
      { "date": "2026-10-25", "score": 88 }
    ],
    "rawText": "王小明同学在 2026 学年音乐学习中表现出稳步提升的趋势……",
    "modelVersion": "learning-report-v1.0.0"
  }
}
```

## 5. 模块四：AI 模型接口

> 模型负责人：赖轩（模型 A：音乐分析）、张馨月（模型 B：美术评分与报告分析）  
> 后端接入：万逸恒（后端 A）  
> 定位：模型服务接口，返回结构化分析结果，由测评业务服务负责权限、评分合并与结果留痕。

### 5.1 AI 接口通用约定

- 所有接口前缀为 `/api/v1/ai`，统一使用 JSON 请求/响应。
- **AI 接口不向学生端开放**。学生作品分析、报告生成由后端在提交、评分、报告任务中代理调用；学生只能通过成绩、报告等业务接口查看已落库结果。教师和管理员只能分析权限范围内学生，且必须显式传入 `studentId`，服务端再次校验数据范围。
- 服务间调用使用独立 `X-Internal-Token`，该 Token 不进入浏览器；不得把模型服务地址、内部 Token 或原始推理接口暴露给学生端。
- 文件 URL 必须来自系统 `/files` 上传结果或受信任的对象存储域名；服务端下载文件时必须防 SSRF、限制大小和超时。
- 单次推理同步超时 60 秒；超时或模型不可用时返回 500，不得返回伪造分数。批量评分进入 RQ，接口返回 `taskId`。
- 模型有降级基线可用时，可返回 `status=degraded` 与 `fallbackUsed=true`，并在业务层标记“AI 辅助结果”。
- 返回结果必须包含 `modelVersion`，便于追溯与回归测试。
- AI 评分仅作为辅助评分。正式测评最终成绩需要经过评分规则合并；人工修改必须保留原 AI 结果和修改人。
- 对 AI 接口按调用方和 IP 限流，例如教师 30 次/分钟、内部批量任务 100 次/分钟；学生端不直接调用。
- 正式环境由后端测评服务通过内部服务令牌代理调用 AI，不直接向前端暴露模型服务地址。

#### MusicAnalysisResult（音乐分析结果）

| 字段 | 类型 | 说明 |
|---|---|---|
| requestId | string | 本次推理请求 ID |
| status | string | `success` / `degraded` |
| audioDuration | number | 音频时长，单位秒 |
| scores | object | `{pitch:number, rhythm:number, beat:number, overall:number}`，均为 0~100 |
| estimatedTempo | number | 估计速度，BPM |
| level | string | `excellent` / `good` / `pass` / `fail` |
| errorPoints | array | 错误点，元素为 `{startTime:number,endTime:number,type:string,severity:string,description:string,expected:string,actual:string}` |
| summary | string | 总体评价 |
| fallbackUsed | boolean | 是否使用降级基线 |
| modelVersion | string | 模型版本 |
| costMs | number | 推理耗时，毫秒 |

#### ArtScoreResult（美术评分结果）

| 字段 | 类型 | 说明 |
|---|---|---|
| requestId | string | 本次推理请求 ID |
| status | string | `success` / `degraded` |
| workType | string | `painting` / `sketch` / `design` / `craft` / `other` |
| scores | object | `{composition:number,color:number,modeling:number,creativity:number,total:number}` |
| level | string | 等级枚举 |
| dimensionComments | object | 四个维度的文字评价，键为 `composition` / `color` / `modeling` / `creativity` |
| strengths | array<string> | 作品优点 |
| improvements | array<string> | 改进建议 |
| summary | string | 总体评价 |
| fallbackUsed | boolean | 是否使用降级基线 |
| modelVersion | string | 模型版本 |
| costMs | number | 推理耗时，毫秒 |

#### LearningReportResult（学情报告结果）

| 字段 | 类型 | 说明 |
|---|---|---|
| reportId | string | 报告 ID |
| studentId | number | 学生 ID |
| subject | string | 学科 |
| generatedAt | string | 生成时间 |
| summary | string | 总体学情概述 |
| strengths | array<string> | 优势 |
| weaknesses | array<string> | 薄弱点 |
| suggestions | array<string> | 个性化建议 |
| scoreTrend | array | 成绩趋势，元素为 `{date:string,score:number}` |
| rawText | string | 完整报告正文，可直接用于报告页面 |
| modelVersion | string | 模型版本 |

### 5.2 音乐分析接口

#### 5.2.1 分析音乐演唱/演奏音频

**接口**：`POST /api/v1/ai/music/analyze`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]；服务间调用需 `X-Internal-Token`  
**说明**：输入学生演唱、演奏或练习音频，返回音准、节奏、节拍评分及错误点标注。学生端不直接调用；教师和管理员只能分析权限范围内学生。服务端以 `studentId` 为审计对象，并从测评/试题/班级关系校验范围，禁止仅凭请求体越权。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| audioUrl | body | string | 是 | 学生音频 URL，建议时长 ≤ 5 分钟 |
| referenceAudioUrl | body | string | 否 | 标准音频 URL；传入时进行对齐比较，不传时使用绝对音高与节拍估计 |
| analysisType | body | string | 否 | `full` / `pitch` / `rhythm` / `beat`，默认 `full` |
| studentId | body | number | 是 | 被分析学生 ID；必须在当前账号数据范围内，服务端不得信任前端角色 |
| assessmentId | body | number | 否 | 关联测评 ID |
| questionId | body | number | 否 | 关联试题 ID |
| requestId | body | string | 否 | 幂等请求 ID，建议使用 UUID |

请求示例：

```json
{
  "audioUrl": "https://cdn.example.com/student_work/88030.mp3",
  "referenceAudioUrl": "https://cdn.example.com/reference/9001-standard.mp3",
  "analysisType": "full",
  "assessmentId": 12001,
  "questionId": 9001,
  "studentId": 1001,
  "requestId": "ai-music-20261020-0001"
}
```

**响应数据（data）**：`MusicAnalysisResult`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "requestId": "ai-music-20261020-0001",
    "status": "success",
    "audioDuration": 93.5,
    "scores": {
      "pitch": 86.5,
      "rhythm": 90,
      "beat": 88,
      "overall": 88.2
    },
    "estimatedTempo": 92,
    "level": "good",
    "errorPoints": [
      {
        "startTime": 12.4,
        "endTime": 13.1,
        "type": "pitch",
        "severity": "minor",
        "description": "第 12 小节高音区音准偏低",
        "expected": "A4",
        "actual": "G#4"
      },
      {
        "startTime": 47.8,
        "endTime": 48.6,
        "type": "beat",
        "severity": "minor",
        "description": "第 48 秒处抢拍约 120ms",
        "expected": "第 3 拍强拍",
        "actual": "提前进入"
      }
    ],
    "summary": "整体节奏稳定、节拍感较好，音准在中高音区有少量偏差，建议加强气息支撑与高音区模唱练习。",
    "fallbackUsed": false,
    "modelVersion": "music-analyzer-v1.2.0",
    "costMs": 2140
  }
}
```

### 5.3 美术作品评分接口

#### 5.3.1 分析美术作品图片

**接口**：`POST /api/v1/ai/art/score`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]；服务间调用需 `X-Internal-Token`  
**说明**：输入学生美术作品图片，返回构图、色彩、造型、创意和总分的结构化评分。学生端不直接调用；教师和管理员只能分析权限范围内学生。服务端以 `studentId` 校验数据范围，评分维度权重可由评分量表指定。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| imageUrl | body | string | 是 | 作品图片 URL，建议 JPG/PNG，≤ 10 MB |
| workType | body | string | 否 | `painting` / `sketch` / `design` / `craft` / `other`，默认 `painting` |
| studentId | body | number | 是 | 被分析学生 ID；必须在当前账号数据范围内 |
| assessmentId | body | number | 否 | 关联测评 ID |
| questionId | body | number | 否 | 关联试题 ID |
| rubric | body | object | 否 | 评分量表权重，如 `{composition:25,color:25,modeling:25,creativity:25}`，总和须为 100 |
| requestId | body | string | 否 | 幂等请求 ID |

请求示例：

```json
{
  "imageUrl": "https://cdn.example.com/student_work/88031.jpg",
  "workType": "painting",
  "assessmentId": 12002,
  "questionId": 9101,
  "studentId": 1001,
  "rubric": {
    "composition": 25,
    "color": 25,
    "modeling": 25,
    "creativity": 25
  },
  "requestId": "ai-art-20261020-0001"
}
```

**响应数据（data）**：`ArtScoreResult`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "requestId": "ai-art-20261020-0001",
    "status": "success",
    "workType": "painting",
    "scores": {
      "composition": 88,
      "color": 91,
      "modeling": 84,
      "creativity": 86,
      "total": 87.25
    },
    "level": "good",
    "dimensionComments": {
      "composition": "主体突出，视觉中心明确，背景层次略有拥挤。",
      "color": "冷暖对比鲜明，色调统一，色彩情绪表达较好。",
      "modeling": "人物比例基本准确，手部结构可进一步刻画。",
      "creativity": "构思有个人表达，细节想象力较丰富。"
    },
    "strengths": [
      "色彩关系协调",
      "画面主体明确",
      "具有较好的叙事性"
    ],
    "improvements": [
      "加强手部与关节结构练习",
      "适当留白，减少背景元素干扰"
    ],
    "summary": "作品整体完成度较高，色彩表现突出，造型细节和画面疏密关系仍有提升空间。",
    "fallbackUsed": false,
    "modelVersion": "art-scorer-v1.1.0",
    "costMs": 1860
  }
}
```

### 5.4 学情报告生成接口

#### 5.4.1 生成学生个性化学情报告

**接口**：`POST /api/v1/ai/learning-report`  
**权限**：[teacher, school_admin, district_admin, city_admin, province_admin]；服务间调用需 `X-Internal-Token`  
**说明**：输入学生答题记录、评分数据与关注维度，生成个性化音乐/美术学业分析报告。学生端不直接生成；报告由后端任务生成并落库，学生通过业务报告接口查看。`studentId` 必须在当前账号数据范围内。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| studentId | body | number | 是 | 学生 ID；服务端校验数据范围，不得由学生端传入 |
| subject | body | string | 是 | `music` / `art` |
| assessmentIds | body | array<number> | 否 | 参与分析的测评 ID 列表 |
| records | body | array | 是 | 答题与评分记录，元素结构见下 |
| timeRange | body | object | 否 | `{startDate:string,endDate:string}` |
| focus | body | array<string> | 否 | 关注维度，如 `["音准","节奏","创意"]` |
| language | body | string | 否 | 报告语言，默认 `zh-CN` |

`records` 元素字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| assessmentId | number | 是 | 测评 ID |
| assessmentName | string | 否 | 测评名称 |
| totalScore | number | 是 | 总分 |
| objectiveScore | number | 否 | 客观题得分 |
| subjectiveScore | number | 否 | 主观题得分 |
| aiScore | number | 否 | AI 辅助得分 |
| answers | array | 否 | 答题摘要，元素为 `{questionId:number,type:string,score:number,maxScore:number,knowledgePoint:string,comment:string}` |

请求示例：

```json
{
  "studentId": 1001,
  "subject": "music",
  "assessmentIds": [11001, 12001],
  "records": [
    {
      "assessmentId": 11001,
      "assessmentName": "2026 春季音乐测评",
      "totalScore": 76,
      "objectiveScore": 30,
      "subjectiveScore": 40,
      "aiScore": 6,
      "answers": [
        {
          "questionId": 9001,
          "type": "single_choice",
          "score": 5,
          "maxScore": 5,
          "knowledgePoint": "节拍识别",
          "comment": "回答正确"
        },
        {
          "questionId": 9010,
          "type": "short_answer",
          "score": 10,
          "maxScore": 15,
          "knowledgePoint": "乐曲情绪分析",
          "comment": "要点不完整"
        }
      ]
    },
    {
      "assessmentId": 12001,
      "assessmentName": "2026 秋季七年级音乐正式测评",
      "totalScore": 88,
      "objectiveScore": 35,
      "subjectiveScore": 48,
      "aiScore": 5,
      "answers": [
        {
          "questionId": 9001,
          "type": "single_choice",
          "score": 5,
          "maxScore": 5,
          "knowledgePoint": "节拍识别",
          "comment": "回答正确"
        },
        {
          "questionId": 9010,
          "type": "short_answer",
          "score": 12,
          "maxScore": 15,
          "knowledgePoint": "乐曲情绪分析",
          "comment": "要点基本完整"
        }
      ]
    }
  ],
  "timeRange": {
    "startDate": "2026-01-01",
    "endDate": "2026-10-20"
  },
  "focus": ["音准", "节奏", "乐曲分析"],
  "language": "zh-CN"
}
```

**响应数据（data）**：`LearningReportResult`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "reportId": "LR202610200001",
    "studentId": 1001,
    "subject": "music",
    "generatedAt": "2026-10-20T16:00:00+08:00",
    "summary": "该生音乐测评成绩呈稳步上升趋势，节拍识别与基础听辨表现稳定，乐曲分析题的要点覆盖度较春季明显提升；音准稳定性和高音区控制仍是主要提升方向。",
    "strengths": [
      "节拍识别准确率较高",
      "听辨题答题稳定性好",
      "能够结合旋律与节奏分析乐曲情绪"
    ],
    "weaknesses": [
      "高音区音准偶有偏低",
      "乐曲分析中对力度、音色等要素关注不足",
      "复杂节奏型的速度控制不够稳定"
    ],
    "suggestions": [
      "每天进行 10 分钟高音区模唱与气息练习",
      "使用“情绪—节奏—力度—音色”四步法整理乐曲分析提纲",
      "针对附点与切分节奏进行慢速跟拍训练"
    ],
    "scoreTrend": [
      {
        "date": "2026-04-15",
        "score": 76
      },
      {
        "date": "2026-10-25",
        "score": 88
      }
    ],
    "rawText": "王小明同学在 2026 学年音乐学习中表现出稳步提升的趋势。春季测评得分 76 分，秋季测评提升至 88 分，增幅约 15.8%。从答题情况看，节拍识别类题目掌握扎实，听辨题正确率较高；乐曲分析题能够抓住情绪与节奏两个核心维度，但力度变化和音色辨识仍有遗漏。建议后续加强高音区音准训练，并用四步分析框架完善主观题作答。",
    "modelVersion": "learning-report-v1.0.0"
  }
}
```

## 6. 前端页面与接口速查

> 下列为主流程调用顺序，具体筛选参数以对应接口章节为准。所有上传先调用 `/files`，再将返回的 `url` 或 `fileId` 传给业务接口。

### 6.1 学生端

| 页面/场景 | 主要接口 | 说明 |
|---|---|---|
| 登录 | `POST /auth/login` → `GET /auth/me` → `GET /auth/menus` | 登录成功后缓存用户、权限码和角色菜单 |
| 令牌续期 | `POST /auth/refresh` | Access Token 过期时单飞刷新，答题保存请求自动重放 |
| 个人中心 | `GET /auth/me`、`PATCH /auth/me`、`PATCH /auth/password` | 修改资料与密码；改密后强制重新登录 |
| 我的班级 | `GET /classes/{classId}`、`GET /classes/search` | 查看班级、班主任、科任教师 |
| 加入/退出/转班 | `POST /classes/{classId}/join`、`POST /classes/{classId}/leave`、`POST /classes/{classId}/change` | 提交后等待审核 |
| 测评列表 | `GET /assessments`、`GET /assessments/{assessmentId}` | 只显示发布给本人的测评 |
| 随机练习 | `POST /papers/practice/random` | 按学科/章节/题型生成练习卷并创建答卷 |
| 开始答题 | `POST /assessments/{assessmentId}/attempts` | 返回题目、截止时间、已保存答案 |
| 答题页 | `GET /attempts/{attemptId}`、`PATCH /attempts/{attemptId}/answers` | 定时自动保存；剩余时间以服务器为准 |
| 交卷 | `POST /attempts/{attemptId}/submit` | 到期由服务端自动交卷，前端无需额外调用 |
| 我的成绩 | `GET /scores/me`、`GET /scores/{scoreId}` | 按 `answerVisible` 决定是否展示解析 |
| 我的证书 | `GET /certificates`、`GET /certificates/{certificateId}/download` | 证书未就绪时禁用下载 |
| 成长曲线 | `GET /students/{studentId}/growth-curve` | `studentId` 取当前用户 ID |
| 学情报告 | `GET /students/{studentId}/learning-report` | 读取已生成报告；学生不可直接调用 AI 接口 |
| 课外作品上传 | `POST /files` | 返回 URL，由后端在提交/评分流程中调用 AI 分析 |

### 6.2 教师端

| 页面/场景 | 主要接口 | 说明 |
|---|---|---|
| 任教班级 | `GET /classes`、`GET /classes/{classId}` | 仅返回任教班级 |
| 班级学生 | `GET /classes/{classId}/students`、`DELETE /classes/{classId}/students/{studentId}` | 查看与移除学生 |
| 入班/转班审核 | `GET /classes/{classId}/requests`、`POST /classes/{classId}/requests/{requestId}/review` | 审核加入、退出、转班 |
| 题库选题 | `GET /questions`、`GET /questions/{questionId}` | 按学科、难度、题型、年级筛选 |
| 手动组卷 | `POST /papers/manual` | 选择题目并分配分值 |
| 自动组卷 | `POST /papers/auto` | 配置题型、难度、数量 |
| 暂存/修改/删除试卷 | `PATCH /papers/{paperId}/draft`、`PATCH /papers/{paperId}`、`DELETE /papers/{paperId}` | 已发布试卷不可修改 |
| 试卷材料/答案下载 | `GET /papers/{paperId}/materials/download`、`GET /papers/{paperId}/answers/download` | 下载音频图片 ZIP、答案 PDF/DOCX |
| 发布测评 | `POST /assessments` | `targetType=class`，`targetIds` 为任教班级 |
| 撤回测评 | `POST /assessments/{assessmentId}/withdraw` | 需填写原因 |
| 人工评分 | `GET /grading/tasks`、`GET /grading/attempts/{attemptId}`、`PATCH /grading/attempts/{attemptId}/scores` | 逐题打分并终评；与重新判分不同 |
| 成绩查询 | `GET /scores`、`GET /scores/{scoreId}` | 按测评、班级、学生筛选 |
| 成绩补录/导入 | `POST /scores/manual`、`POST /scores/import` | 补录需原因和佐证材料 |
| 重新判分 | `POST /scores/{scoreId}/regrade` | AI 失败或评分规则调整后使用 |
| 班级统计 | `GET /scores/statistics`、`GET /scores/statistics/list`、`GET /scores/statistics/export` | 单班汇总、班级列表/排名与导出 |
| 证书 | `POST /certificates/generate`、`GET /certificates` | 生成并查看学生证书 |

### 6.3 学校管理端

| 页面/场景 | 主要接口 | 说明 |
|---|---|---|
| 教师账号 | `GET /accounts?role=teacher`、`POST /accounts/teachers`、`PATCH /accounts/{accountId}`、`DELETE /accounts/{accountId}` | 本校教师 CRUD |
| 教师密码重置 | `POST /accounts/{accountId}/reset-password` | 返回临时密码 |
| 学生账号 | `GET /accounts?role=student`、`POST /accounts/students`、`PATCH /accounts/{accountId}` | 本校学生账号 |
| 班级管理 | `GET /classes`、`POST /classes`、`PATCH /classes/{classId}`、`DELETE /classes/{classId}` | 本校班级 CRUD |
| 学生批量导入 | `POST /classes/{classId}/students/import` | 按接口说明中的模板列整理 CSV/XLSX 后导入 |
| 校级组卷 | `POST /papers/manual`、`POST /papers/auto` | `scopeType=school` |
| 校级发布 | `POST /assessments` | `targetType=school`，可按年级筛选 |
| 校级统计 | `GET /scores/statistics`、`GET /scores/statistics/list`、`GET /scores/statistics/export` | 本校汇总、班级列表/排名与导出 |
| 成绩补录 | `POST /scores/manual`、`POST /scores/import` | 本校范围 |
| 证书管理 | `POST /certificates/generate`、`GET /certificates` | 本校范围 |

### 6.4 区县管理端

| 页面/场景 | 主要接口 | 说明 |
|---|---|---|
| 学校账号 | `GET /accounts?role=school_admin`、`POST /accounts/schools`、`PATCH /accounts/{accountId}`、`DELETE /accounts/{accountId}` | 创建/管理本区县学校 |
| 学校密码重置 | `POST /accounts/{accountId}/reset-password` | 重置学校管理员密码 |
| 班级查询 | `GET /classes` | 本区县范围 |
| 区县级组卷 | `POST /papers/manual`、`POST /papers/auto` | `scopeType=district` |
| 区县级发布 | `POST /assessments` | `targetType=district`，可指定学校/年级 |
| 区县统计 | `GET /scores/statistics`、`GET /scores/statistics/list`、`GET /scores/statistics/export` | 区县汇总、学校列表/排名与导出 |
| 学校统计 | `GET /scores/statistics/list?groupBy=school` | 返回本区县各学校多行统计与排名 |
| 测评补录 | `POST /scores/manual`、`POST /scores/import` | 本区县范围 |
| 证书查询 | `GET /certificates` | 本区县范围 |

### 6.5 市州管理端

| 页面/场景 | 主要接口 | 说明 |
|---|---|---|
| 区县账号 | `GET /accounts?role=district_admin`、`POST /accounts/districts`、`PATCH /accounts/{accountId}`、`DELETE /accounts/{accountId}` | 创建/管理本市区县 |
| 市直属学校账号 | `GET /accounts?role=school_admin&orgId=...`、`POST /accounts/schools` | 按本市权限处理直属学校 |
| 市州级组卷 | `POST /papers/manual`、`POST /papers/auto` | `scopeType=city` |
| 市州级发布 | `POST /assessments` | `targetType=city` 或 `school` |
| 市州/区县/学校统计 | `GET /scores/statistics`、`GET /scores/statistics/list` | 单对象汇总；`groupBy=district` 查看区县排名 |
| 统计导出 | `GET /scores/statistics/export` | 按市州/区县/学校导出，支持 `groupBy` 多行导出 |
| 测评补录 | `POST /scores/manual`、`POST /scores/import` | 本市范围 |
| 证书查询 | `GET /certificates` | 本市范围 |

### 6.6 省级管理端

| 页面/场景 | 主要接口 | 说明 |
|---|---|---|
| 市州账号 | `GET /accounts?role=city_admin`、`POST /accounts/cities`、`PATCH /accounts/{accountId}`、`DELETE /accounts/{accountId}` | 创建/管理市州 |
| 省级组卷 | `POST /papers/manual`、`POST /papers/auto` | `scopeType=province` |
| 省级发布 | `POST /assessments` | `targetType=province` 或下级 |
| 全省统计 | `GET /scores/statistics`、`GET /scores/statistics/list` | 单对象汇总；`groupBy=city/district/school` 查看多行排名 |
| 全省参与率 | `GET /scores/statistics/list?groupBy=city` | 每行返回 `participationRate`、`participantCount`、`studentCount` |
| 统计导出 | `GET /scores/statistics/export?groupBy=city` | 导出全省各地区参与率/成绩多行表格 |
| 省级补录 | `POST /scores/manual`、`POST /scores/import` | 全省范围 |
| 系统日志 | `GET /logs` | 查看全省管理操作日志 |

### 6.7 题库管理端

| 页面/场景 | 主要接口 | 说明 |
|---|---|---|
| 试题列表 | `GET /questions` | 多条件筛选 |
| 创建/修改试题 | `POST /questions`、`PATCH /questions/{questionId}` | 管理员可直接发布 |
| 试题详情 | `GET /questions/{questionId}` | 查看答案、解析、资源 |
| 试题审核 | `GET /questions?status=pending`、`POST /questions/{questionId}/review` | 通过或驳回 |
| 删除试题 | `DELETE /questions/{questionId}` | 被有效试卷引用时拒绝 |
| 课程管理 | `GET /courses`、`POST /courses`、`PATCH /courses/{courseId}`、`DELETE /courses/{courseId}` | 课程 CRUD |
| 章节管理 | `GET /courses/{courseId}/chapters`、`POST /courses/{courseId}/chapters`、`PATCH /chapters/{chapterId}`、`DELETE /chapters/{chapterId}` | 章节 CRUD |
| 试题资源 | `POST /questions/{questionId}/resources`、`DELETE /questions/{questionId}/resources/{resourceId}` | 图片/音频上传删除 |
| 通用上传 | `POST /files` | 上传后关联试题资源 |
| 操作日志 | `GET /logs`、`GET /logs/{logId}` | 审核、创建、删除等审计 |

## 7. 前后端联调与实现约定

### 7.1 核心业务链路

1. **组卷链路**：题库选题 → 创建试卷（`draft` / `ready`）→ 校验分值、题型、学科、年级 → 发布测评。
2. **发布链路**：试卷快照 → 创建测评 → 生成目标学生名单 → 学生端可见。
3. **答题链路**：开始答题 → 获取题目与服务器截止时间 → 自动保存 → 提交/到时自动提交 → 判分。
4. **成绩链路**：客观题即时判分 → 主观题/AI 评分 → 汇总成绩 → 统计与排名 → 证书。
5. **成长链路**：正式测评成绩 → 按时间排序 → 生成成长曲线 → 学情报告。

### 7.2 状态流转

| 对象 | 允许流转 |
|---|---|
| 试题 | `draft` → `pending` → `approved` / `rejected`；`approved` → `offline` |
| 试卷 | `draft` ↔ `ready` → `published` → `archived` |
| 测评 | `published` → `withdrawn` / `finished` |
| 答卷 | `in_progress` → `submitted`（手动/自动）→ `graded`；异常时 → `invalid` |
| 成绩 | `pending` → `grading` → `graded` / `failed` |
| 证书 | `generating` → `ready` / `failed` |

### 7.3 关键实现要求

1. **服务器时间为准**：答题截止、自动交卷、统计时间范围全部以服务器时间为准，前端倒计时仅作展示。
2. **幂等交卷**：交卷接口必须防止重复提交；重复调用返回同一成绩，不重复写入。
3. **试卷快照**：测评发布时保存题目、选项、分值、资源快照，避免题库后续修改影响历史测评。
4. **AI 异步化**：正式测评中的 AI 评分建议异步执行；成绩先返回 `grading`，完成后通过轮询成绩接口获取。
5. **答案隔离**：答题接口不得返回 `answer`、`analysis`；交卷后依据 `showAnswerMode` 控制解析展示。
6. **数据范围优先**：任何列表、详情、导出、AI 接口都先做角色校验，再做组织/班级范围校验。
7. **导入事务**：批量导入采用逐行校验、部分成功策略；每行写入使用独立事务或保存点，避免整批回滚。
8. **证书异步生成**：证书生成可能耗时，前端轮询证书列表或详情，`status=ready` 后再下载。
9. **文件安全**：只允许白名单类型，服务端校验文件头，存储随机文件名，下载使用签名 URL 或鉴权代理。
10. **审计留痕**：成绩补录、重新判分、测评撤回、账号重置、试题审核必须写操作日志。
11. **统计缓存**：区域统计可缓存 1~5 分钟，但补录、重新判分、导入后必须主动失效缓存。
12. **AI 降级**：模型超时或失败时不得伪造分数；有降级基线时需返回 `degraded` 并在前端标注。

### 7.4 前端通用处理建议

- 统一封装请求：自动附加 `Authorization`；遇到 `401` 先单飞调用 `POST /auth/refresh`，成功则重放原请求，刷新失败才清除令牌并跳转登录。
- 统一处理 `403`：展示“无权限访问”，不要暴露目标资源详情。
- 统一处理 `404`：展示“资源不存在或已删除”；`409` 展示后端返回的状态冲突原因，不自动重试。
- 列表页统一使用 `pageNum`、`pageSize`，响应读取 `total`、`pages`、`list`。
- 文件上传单独使用 `multipart/form-data`，成功后把 `fileId`/`url` 写入业务表单。
- 答题页每 10~15 秒调用 `PATCH /attempts/{attemptId}/answers`，并在 `visibilitychange`、切题、交卷前强制保存。
- 倒计时以 `serverTime` 校正客户端时间，剩余 1 分钟提示，归零后等待服务端自动交卷结果。
- 成绩页依据 `gradingStatus` 展示“判分中”，不要将未完成 AI 评分显示为最终成绩。
- 更新请求统一使用 `PATCH`，只提交发生变化的字段；不要把整个表单对象回传导致未编辑字段被覆盖。
- 所有枚举值使用小写英文，中文文案由前端统一映射，避免各页面自行翻译。

### 7.5 接口责任与联调

| 模块 | 后端责任人 | 主要联调对象 |
|---|---|---|
| 账号与权限 | 柴国继（后端 B） | 前端 A/B、后端 A |
| 题库管理 | 柴国继（后端 B） | 前端 B、模型 A/B |
| 测评核心业务 | 万逸恒（后端 A） | 前端 A/B、后端 B、模型 A/B |
| 音乐分析 | 赖轩（模型 A） | 后端 A、前端 A |
| 美术评分/学情报告 | 张馨月（模型 B） | 后端 A、前端 A |

### 7.6 建议落地顺序

按“先契约、再主链路、后统计与 AI、最后联调验收”的顺序推进。每个阶段结束时冻结对应 OpenAPI 片段并补契约测试，避免前端在接口未稳定时反复返工。

| 阶段 | 目标 | 前置依赖 | 本阶段接口 |
|---|---|---|---|
| P0 基础契约 | 技术基线、数据库迁移、统一响应/异常、`Page<T>`、枚举、数据范围模型 | 无 | 无新增接口，先定 `1.1`～`1.10` 的公共规则 |
| P1 认证与权限 | 登录、刷新、退出、`/auth/me`、菜单、角色与数据范围 | P0 | AUTH-01～AUTH-07 |
| P2 组织与班级 | 省/市/区县/学校/教师/学生账号、班级与学生关系 | P1 | ACC-01～ACC-11、CLS-01～CLS-14 |
| P3 题库与课程 | 试题、课程、章节、资源、文件、日志 | P1、P2 | QST-01～QST-07、CRS-01～CRS-05、CHP-01～CHP-05、RES-01～RES-02、FILE-01～FILE-02、LOG-01～LOG-02 |
| P4 测评主链路 | 组卷、发布、答题、保存、提交、自动交卷 | P2、P3 | PAP-01～PAP-10、ASM-01～ASM-04、ATT-01～ATT-04 |
| P5 评分与统计 | 人工逐题评分、重新判分、补录、导入、单对象统计、列表统计、排名、导出 | P4 | SCR-01～SCR-09、GRD-01～GRD-03 |
| P6 结果与报告 | 证书、成长曲线、学情报告读取、AI 内部代理与异步任务 | P5 | CRT-01～CRT-04、GRW-01～GRW-02、AI-01～AI-03 |
| P7 前端联调 | 学生 H5、管理控制台、共享 API 层、401 单飞刷新、答题自动保存 | P1～P6 | 按 `6. 前端页面与接口速查` 联调 |
| P8 验收与压测 | 268 项逐项验收、权限矩阵回归、300 分钟考试、导出与统计性能 | P7 | 按 `附录 A` 逐项核对 |

关键顺序约束：

1. **先做数据范围，再做业务接口**。账号、班级、成绩、统计、AI 都必须复用同一套 scope 校验，不能各接口各写一套。
2. **先做答题主链路，再做统计**。成绩、排名、证书、成长曲线都依赖答卷和评分结果，提前做统计只会反复改口径。
3. **人工评分必须先于自动统计验收**。主观题和作品题没有正式评分入口时，成绩统计和证书数据不完整。
4. **AI 接口最后接入**。AI 只作为评分辅助和报告生成，不能阻塞 P4/P5 的联调；必须有超时、重试、降级和原始结果留痕。
5. **每个阶段都跑权限矩阵**。至少覆盖 7 个角色 × 列表/详情/导出/写操作，防止学生或低层级管理员越权。

## 8. 前端技术方案

> 说明：现有功能设计表与人员分工表未指定前端技术栈。本章给出与本项目 7 个端口、94 个接口、限时答题、音频播放、作品上传、AI 结果展示和统计图表相匹配的落地选型。实际开发时可结合团队熟悉度替换框架，但应保留“双应用、共享 API 层、服务端权限为准”的架构原则。

### 8.1 建设目标与约束

| 约束 | 对前端的要求 |
|---|---|
| 7 类角色 | 按角色动态生成菜单和路由，前端不能只靠隐藏按钮做安全控制 |
| 学生/教师 + 五级管理 + 题库 | 不建议为 7 个端各建一个工程；按使用形态拆成学生 H5 与管理控制台两个应用 |
| 限时答题 | 服务器时间为准，自动保存、断线恢复、重复提交防护、到时自动交卷状态确认 |
| 音乐测评 | 音频预加载、播放控制、听赏题资源展示、音乐错误点可视化 |
| 美术测评 | 图片上传、预览、压缩、进度、AI 维度评分展示 |
| 多级统计 | 表格分页筛选、区域下钻、成绩分布、成长曲线、证书下载 |
| 7 天交付 | 复用 API 类型、权限、上传、分页、图表和表单能力，避免重复造轮子 |
| 安全 | Bearer Token、路由守卫、CSP、文件类型校验；标准答案绝不下发到前端 |

前端设计原则：

1. **API First**：接口契约以本文档和 FastAPI OpenAPI 为准，前端类型自动生成。
2. **两个应用，一个 API 层**：学生端与管理端分别构建，共享请求、类型、权限和工具包。
3. **服务端权威**：倒计时、判分、数据范围、正确答案均由后端控制，前端只负责展示和交互。
4. **移动优先但不做原生 App**：学生端采用响应式 H5，管理端采用桌面 Web。
5. **先完成主链路**：登录 → 班级 → 组卷 → 发布 → 答题 → 交卷 → 成绩 → 统计 → 证书。

### 8.2 技术选型

| 层次 | 技术 | 版本建议 | 用途 |
|---|---|---|---|
| 开发语言 | TypeScript | 5.x | 全项目类型安全，禁止核心模块使用 `any` |
| 前端框架 | Vue | 3.5+ | Composition API + `<script setup>` |
| 构建工具 | Vite | 7.x | 开发服务器、构建、代码分割 |
| 包管理 | pnpm | 9+ | Monorepo 与依赖复用 |
| 路由 | Vue Router | 4.x | 角色路由、懒加载、导航守卫 |
| 状态管理 | Pinia | 3.x | 登录态、用户信息、字典、答题状态 |
| HTTP | Axios | 1.x | 请求拦截、统一错误、文件上传下载 |
| 学生端 UI | Vant | 4.x | 移动端表单、弹窗、列表、上传 |
| 管理端 UI | Element Plus | 2.x | 表格、表单、树、分页、弹窗 |
| 图表 | ECharts | 5+ | 成绩分布、区域对比、成长曲线、美术雷达图 |
| 音频播放 | Howler.js | 2.x | 音乐题音频播放、预加载、播放次数控制 |
| 音频可视化 | Wavesurfer.js | 7.x | 波形展示、音乐错误点时间轴标注 |
| 日期处理 | Day.js | 1.x | 时间格式化、时区展示、倒计时辅助 |
| API 类型 | openapi-typescript | 7.x | 从 FastAPI `/openapi.json` 生成 TypeScript 类型 |
| 工具库 | VueUse | 当前稳定版 | 防抖、节流、可见性、网络状态、存储 |
| 图片压缩 | browser-image-compression | 当前稳定版 | 学生作品上传前压缩预览图，原图另行上传 |
| PDF 预览 | pdfjs-dist | 可选 | 证书在线预览；不预览时直接下载 |
| 单元测试 | Vitest + Vue Test Utils | 当前稳定版 | 组件、工具函数、状态逻辑测试 |
| E2E 测试 | Playwright | 当前稳定版 | 登录、答题、交卷、审核、统计主链路 |
| API Mock | MSW | 当前稳定版 | 前后端并行开发与异常场景模拟 |
| 代码质量 | ESLint + Prettier + Stylelint | 当前稳定版 | 统一代码与样式规范 |
| Git 规范 | Husky + lint-staged + commitlint | 当前稳定版 | 提交前检查、约定式提交 |
| 监控 | Sentry | 可选 | 生产错误采集；不得上报 Token 和学生敏感信息 |

不建议引入的技术：

- 不需要 Nuxt/SSR：系统是登录后的管理/答题应用，SEO 无价值，SSR 会增加部署复杂度。
- 不需要 7 个独立前端工程：会重复实现登录、权限、分页、上传和图表。
- 不需要微前端：6 人团队、7 天周期内，微前端带来的治理成本大于收益。
- 不需要 WebSocket：判分、证书生成使用轮询即可，避免额外长连接运维。
- 不需要在前端做自动判分：分数必须以服务端为准，前端不得持有标准答案。

### 8.3 应用架构

#### 8.3.1 双应用划分

| 应用 | 使用角色 | UI 形态 | 主要模块 |
|---|---|---|---|
| `student-h5` | student | 移动端 H5，适配 375~430px，兼容平板 | 登录、班级、测评列表、答题、成绩、证书、成长曲线 |
| `console` | teacher、school_admin、district_admin、city_admin、province_admin、question_admin | 桌面管理后台，建议最小宽度 1280px | 教师工作台、五级管理、题库管理、统计导出 |

说明：

- 教师组卷、成绩导入、统计等操作更适合桌面端，因此教师端放入 `console`，学生端单独使用 Vant。
- `console` 内按 `/teacher`、`/school`、`/district`、`/city`、`/province`、`/qbank` 划分路由模块，前端 A/B 可按目录分工，减少代码冲突。
- 两个应用共享登录协议、API 客户端、类型定义、字典和基础工具，不共享强业务页面组件。

#### 8.3.2 推荐目录结构

```text
art-assessment-web/
├─ apps/
│  ├─ student-h5/                 # 学生移动端
│  │  ├─ src/
│  │  │  ├─ api/                 # 学生业务 API 封装
│  │  │  ├─ views/
│  │  │  │  ├─ auth/
│  │  │  │  ├─ class/
│  │  │  │  ├─ assessment/
│  │  │  │  ├─ exam/             # 答题核心页
│  │  │  │  ├─ score/
│  │  │  │  ├─ certificate/
│  │  │  │  └─ growth/
│  │  │  ├─ stores/
│  │  │  ├─ router/
│  │  │  └─ main.ts
│  │  └─ vite.config.ts
│  └─ console/                    # 教师 + 五级管理 + 题库
│     ├─ src/
│     │  ├─ api/
│     │  ├─ layouts/
│     │  ├─ views/
│     │  │  ├─ teacher/
│     │  │  ├─ school/
│     │  │  ├─ district/
│     │  │  ├─ city/
│     │  │  ├─ province/
│     │  │  └─ qbank/
│     │  ├─ stores/
│     │  └─ router/
│     └─ vite.config.ts
├─ packages/
│  ├─ api/                        # Axios 实例、拦截器、分页、上传、下载
│  ├─ types/                      # OpenAPI 生成类型与业务类型
│  ├─ ui/                         # 设计令牌、空状态、错误页、业务小组件
│  ├─ utils/                      # 时间、分数、文件、权限、格式化工具
│  └─ config/                     # ESLint、TypeScript、Vite 公共配置
├─ pnpm-workspace.yaml
└─ package.json
```

#### 8.3.3 共享包职责

| 包 | 职责 | 禁止内容 |
|---|---|---|
| `packages/api` | Axios 实例、Token 注入、统一错误处理、上传下载、分页参数 | 具体页面业务状态 |
| `packages/types` | OpenAPI 生成类型、枚举、`ApiResponse<T>`、`PageResult<T>` | 运行时代码 |
| `packages/ui` | 设计令牌、空状态、加载状态、403/404、通用确认弹窗 | 直接依赖某一端路由 |
| `packages/utils` | 时间偏移、分数格式化、文件大小、文件名解析、防抖封装 | 接口请求 |
| `packages/config` | TS、ESLint、Vite 基础配置 | 业务配置 |

### 8.4 角色路由与菜单

#### 8.4.1 路由划分

| 角色 | 应用 | 路由前缀 | 首页 |
|---|---|---|---|
| student | student-h5 | `/student` | `/student/home` |
| teacher | console | `/teacher` | `/teacher/workbench` |
| school_admin | console | `/school` | `/school/dashboard` |
| district_admin | console | `/district` | `/district/dashboard` |
| city_admin | console | `/city` | `/city/dashboard` |
| province_admin | console | `/province` | `/province/dashboard` |
| question_admin | console | `/qbank` | `/qbank/dashboard` |

公共路由：`/login`、`/403`、`/404`、`/500`。

#### 8.4.2 路由守卫

守卫顺序固定为：

1. 无 Token 且无 Refresh Token：跳转 `/login`，并记录原始目标路由。
2. 有 Token 但无用户信息：调用 `GET /auth/me` 恢复登录态。
3. Access Token 即将过期或已过期：先调用 `POST /auth/refresh`；刷新失败才清除登录态并跳转登录。
4. 校验 `route.meta.roles` 是否包含当前角色；不匹配跳转 `/403`。
5. 调用 `GET /auth/menus` 加载角色菜单，缓存到 Pinia；菜单只负责展示，后端仍执行真实权限校验。
6. 页面级权限不足时统一展示 403，不查询目标数据。

路由示例：

```ts
{
  path: '/teacher/papers',
  name: 'TeacherPaperList',
  component: () => import('@/views/teacher/papers/index.vue'),
  meta: {
    title: '教师组卷',
    roles: ['teacher'],
    menu: true,
    icon: 'EditPen'
  }
}
```

#### 8.4.3 权限控制边界

- 前端路由与菜单按角色控制，减少误操作；**不能替代后端鉴权**。
- 菜单树从 `GET /auth/menus` 加载，不硬编码在路由文件；菜单只负责展示，接口权限仍由后端校验。
- 数据范围（本校、本区县、本市州、全省）由后端按登录身份计算，前端不传可信组织 ID。
- 按钮级权限使用 `GET /auth/me` 返回的 `permissions: string[]`，例如 `question.review`、`score.import`、`grading.submit`；前端隐藏按钮不能替代后端校验。
- 修改他人数据、撤回测评、补录成绩、人工终评等高风险操作必须二次确认并展示操作原因输入框。

### 8.5 API 接入层

#### 8.5.1 类型自动生成

后端 FastAPI 启动后，通过 OpenAPI 生成前端类型：

```bash
pnpm dlx openapi-typescript http://localhost:8000/openapi.json \
  -o packages/types/src/openapi.d.ts
```

约束：

- 将生成文件纳入版本管理，接口变更后重新生成并提交。
- 业务代码只引用生成类型或 `packages/types` 中的别名，不手写重复接口类型。
- CI 可增加 OpenAPI 变更检查，避免后端改字段但前端未更新。

#### 8.5.2 统一响应与分页类型

```ts
export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export interface PageResult<T> {
  total: number
  pages: number
  list: T[]
}

export interface PageQuery {
  pageNum?: number
  pageSize?: number
}
```

请求层统一解包：

- `code === 200`：返回 `data`。
- `401`：先单飞调用 `POST /auth/refresh`，成功则重放原请求；刷新失败才清除 Token 并跳转登录，多个并发请求共享同一个刷新 Promise。
- `403`：展示无权限页或 Toast，不展示目标数据。
- `404`：展示“资源不存在或已删除”，不自动重试。
- `409`：展示后端 `message`（如“已交卷”“版本冲突”），提示刷新或联系管理员。
- `400`：优先展示后端 `message`；`data.errors` 映射到表单项。
- `500`：展示统一错误页或“服务暂不可用”，允许重试；请求头携带 `X-Request-Id` 便于排查。

#### 8.5.3 Axios 实例要求

```ts
const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 60_000
})

http.interceptors.request.use((config) => {
  const token = useAuthStore().token
  if (token) config.headers.Authorization = `Bearer ${token}`
  config.headers['X-Request-Id'] = crypto.randomUUID()
  return config
})

let refreshPromise: Promise<string> | null = null

http.interceptors.response.use(
  (res) => res,
  async (error) => {
    const { config, response } = error
    if (response?.status !== 401 || config._retried) throw error
    config._retried = true

    // 单飞：并发 401 只发起一次刷新
    refreshPromise ??= authApi.refresh(useAuthStore().refreshToken)
      .then((data) => {
        useAuthStore().setTokens(data.token, data.refreshToken)
        return data.token
      })
      .finally(() => { refreshPromise = null })

    const token = await refreshPromise
    config.headers.Authorization = `Bearer ${token}`
    return http(config)
  }
)
```

必须实现：

- 自动附加 `Authorization: Bearer <token>` 和 `X-Request-Id`。
- `401` 单飞刷新并重放原请求；刷新失败才退出登录。答题自动保存、交卷、上传同样适用。
- 上传请求自动切换 `multipart/form-data`，不手动设置错误的 `Content-Type`。
- 文件下载使用 `responseType: 'blob'`，从 `Content-Disposition` 解析文件名；不能直接用 `<a href>` 访问需要 Bearer Token 的下载接口。
- 交卷、导入、补录、证书生成生成 `Idempotency-Key`，防止网络重试导致重复提交。
- 列表筛选变化时取消上一请求（`AbortController`），避免旧响应覆盖新结果。
- 仅对可重试的 GET/上传超时做一次自动重试；交卷、补录、审核等写操作不得自动重试，必须依赖幂等键。

#### 8.5.4 Token 与登录态

- `POST /auth/login` 返回 `token`、`refreshToken`、`expiresIn=1800`、`refreshExpiresIn=604800` 和 `UserProfile`。
- Access Token 存入内存或 `sessionStorage`；Refresh Token 存入 `httpOnly` Cookie 或 `sessionStorage`。若使用 `localStorage`，必须配合严格 CSP、短有效期和 XSS 防护。
- Token 不得放入 URL、日志、埋点或错误上报；Refresh Token 只能通过 HTTPS 请求体或 `httpOnly` Cookie 传输。
- `401` 时使用单飞刷新，成功后重放原请求；刷新失败、Refresh Token 过期或账号被禁用时，清除所有令牌并跳转登录。
- 答题过程中 Access Token 过期不得中断作答：自动保存请求触发静默刷新，刷新期间保持本地答题状态。
- 账号被禁用、密码被重置或管理员强制下线后，后端 `tokenVersion` 变化，前端下一次请求收到 `401` 并退出。

### 8.6 答题端关键技术

答题页是项目风险最高的页面，必须单独设计。

#### 8.6.1 倒计时与服务器时间

- 开始答题接口返回 `serverTime`、`deadline`、`remainingSeconds`。
- 前端计算 `offset = serverTime - Date.now()`，倒计时使用 `Date.now() + offset`。
- 每次保存答案返回的 `serverTime` 可用于校准偏移。
- 倒计时归零后立即锁定输入并展示“已到时间，正在确认交卷结果”；**自动交卷由服务端定时任务完成**。
- 若产品要求客户端兜底，可调用一次交卷接口并依赖幂等；成功或失败都以服务端答卷状态为准，不重复提示。

#### 8.6.2 自动保存队列

- 每 10~15 秒批量调用 `PATCH /attempts/{attemptId}/answers`。
- 切题、页面隐藏（`visibilitychange`）、网络恢复、点击交卷前强制保存一次。
- 维护串行保存队列，避免并发保存导致后发请求覆盖先发答案。
- 保存失败时指数退避重试，并在页面顶部提示“答案尚未同步，请检查网络”。
- 在 `localStorage` 保存临时草稿，键名包含 `attemptId`；服务端 `savedAnswers` 始终优先。
- 交卷成功后清除本地草稿，防止下次答题误恢复。

#### 8.6.3 防重复提交与离开保护

- 点击交卷后按钮进入 `submitting` 状态，禁止再次点击。
- 交卷请求携带 `Idempotency-Key`，重复响应按成功处理。
- 答题中监听 `beforeunload`，提示用户尚未交卷。
- 路由离开守卫提示“离开后倒计时仍继续”，确认后才允许离开。
- 网络断开不阻止本地作答，但要显著提示答案未同步。

#### 8.6.4 音频题

- 使用 Howler.js 统一管理音频实例，支持预加载、播放、暂停、重播次数限制。
- 浏览器禁止自动播放：首次播放必须由用户点击触发，并给出“点击播放音频”的明确按钮。
- 听赏题若要求不可拖动进度，应禁用进度条；是否有播放次数限制由后端题目配置下发。
- 同一页面只保留一个主音频播放器，切题时停止上一题音频。
- 音频资源需支持 CORS 和 Range 请求，否则移动端拖动/重播可能失败。

#### 8.6.5 答题页状态

| 状态 | 界面行为 |
|---|---|
| loading | 骨架屏，禁止作答 |
| in_progress | 显示题目、倒计时、保存状态 |
| saving | 显示“保存中”，不阻塞作答 |
| save_failed | 顶部警告，继续本地作答并重试 |
| submitted | 禁止修改，展示交卷成功与判分状态 |
| grading | 展示“判分中”，可离开页面，稍后查成绩 |
| timeout | 展示“已自动交卷”，只读 |
| invalid | 展示无效原因，引导联系教师 |

### 8.7 音乐、美术与 AI 结果展示

#### 8.7.1 音乐分析可视化

- 使用 Wavesurfer.js 展示音频波形。
- 将 `errorPoints` 按 `startTime/endTime` 映射为波形标记；点击标记可跳转到对应时间段。
- 音准、节奏、节拍分别用进度条或仪表盘展示，总分单独突出。
- 对 `status=degraded` 明确标注“降级分析结果”，不得伪装成正式模型结果。
- 错误点列表至少展示：时间段、类型、严重程度、问题描述、期望值与实际值。

#### 8.7.2 美术评分可视化

- 上传前校验类型、大小和分辨率；展示压缩后的预览图，但 AI 评分上传原图。
- 使用 ECharts 雷达图展示构图、色彩、造型、创意四个维度。
- 总分、等级、维度评语、优点、改进建议分区展示。
- 作品图片支持缩放预览；不得在图片 URL 中携带 Token。
- AI 结果旁标注 `modelVersion` 和“AI 辅助评分”说明。

#### 8.7.3 学情报告

- 报告由后端生成并落库，学生端通过 `GET /students/{studentId}/learning-report` 读取；不得直接调用 `/ai/learning-report`。
- `rawText` 用于报告正文，`summary`、`strengths`、`weaknesses`、`suggestions` 用于卡片式摘要。
- 报告正文如使用 Markdown 渲染，必须使用可信渲染器并过滤 HTML，禁止直接 `v-html` 渲染模型输出。
- 提供打印样式和“导出/打印”入口；打印时隐藏导航和操作按钮。

### 8.8 表格、表单与统计图表

#### 8.8.1 列表页规范

- 筛选条件同步到 URL query，刷新页面后保持筛选状态。
- 修改筛选条件时重置 `pageNum = 1`。
- 统一展示加载中、空数据、请求失败、无权限四种状态。
- 分页参数固定为 `pageNum`、`pageSize`，读取 `total`、`pages`、`list`。
- 大列表使用 Element Plus `el-table-v2` 或分页控制，避免一次性渲染数千行。
- 批量操作必须二次确认，并展示成功/失败数量。

#### 8.8.2 表单规范

- 前端校验只做即时提示，最终以后端校验为准。
- 必填、长度、枚举、分数范围、时间范围与接口文档保持一致。
- 表单提交时禁用按钮，防止重复创建。
- 编辑页先加载详情，避免用户修改未加载完成的空表单。
- 成绩补录、撤回测评、删除账号等操作必须填写原因并二次确认。

#### 8.8.3 图表规范

- ECharts 按需引入并懒加载，避免进入首屏即加载全部图表。
- 成绩分布使用柱状图；区域对比使用柱状/条形图；成长曲线使用折线图；美术评分使用雷达图。
- 图表容器监听尺寸变化并调用 `resize()`。
- 无数据时展示空状态，不展示空白坐标轴。
- 图表颜色使用统一设计令牌，保证打印和深浅背景下可读。

#### 8.8.4 导入导出

- 导入文件由后端解析，前端只负责上传和展示 `ImportResult.errors`。
- 失败明细以表格展示行号、学籍号、失败原因，支持复制或导出。
- 导出接口返回二进制文件，前端使用 Blob 下载并解析文件名。
- 下载失败时解析 JSON 错误体，不能把错误 JSON 当成文件保存。

### 8.9 工程化与部署

#### 8.9.1 环境变量

| 变量 | 示例 | 说明 |
|---|---|---|
| `VITE_API_BASE_URL` | `/api/v1` | API 基础路径 |
| `VITE_APP_TITLE` | `艺术素质测评系统` | 浏览器标题 |
| `VITE_APP_ENV` | `production` | 环境标识 |
| `VITE_ENABLE_MOCK` | `false` | 是否启用 MSW |
| `VITE_POLL_INTERVAL_MS` | `3000` | 判分/证书轮询间隔 |
| `VITE_IMAGE_MAX_MB` | `10` | 图片上传大小限制 |
| `VITE_AUDIO_MAX_MB` | `50` | 音频上传大小限制 |

#### 8.9.2 代码质量

- TypeScript 开启 `strict`，核心 API 与答题逻辑禁止 `any`。
- ESLint + Prettier 统一代码风格，Stylelint 统一 SCSS。
- 提交前执行 lint、类型检查和单元测试。
- 使用 Conventional Commits，例如 `feat(exam): add auto save`。
- 枚举、状态文案、分数等级集中维护，禁止页面内散落魔法字符串。
- 关键工具函数（服务器时间偏移、分数计算、文件名解析）必须有单元测试。

#### 8.9.3 构建与部署

```nginx
location /student/ {
    alias /var/www/art-assessment/student/;
    try_files $uri $uri/ /student/index.html;
}

location /console/ {
    alias /var/www/art-assessment/console/;
    try_files $uri $uri/ /console/index.html;
}

location /api/ {
    proxy_pass http://backend:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

部署要求：

- 两个应用分别构建，Vite `base` 分别为 `/student/`、`/console/`。
- 静态资源使用内容哈希文件名，开启长期缓存；`index.html` 不缓存。
- 开启 gzip 或 brotli；生产环境关闭公开 Source Map。
- 同域部署时无需额外 CORS；跨域部署时后端必须配置允许的来源、方法和请求头。
- 配置 CSP，至少限制 `script-src`、`img-src`、`media-src`、`connect-src`。
- HTTPS 必须启用；音频、图片、证书 CDN 同样使用 HTTPS。
- 生产构建后执行一次冒烟测试：登录、答题保存、交卷、成绩查看、文件下载。

#### 8.9.4 测试策略

| 层级 | 工具 | 覆盖重点 |
|---|---|---|
| 单元测试 | Vitest | 时间偏移、答案结构转换、分页参数、文件名校验 |
| 组件测试 | Vue Test Utils | 登录表单、题目组件、成绩卡片、筛选表格 |
| API Mock | MSW | 401/403/400/500、超时、空数据、AI 降级 |
| E2E | Playwright | 7 角色登录、组卷发布、答题交卷、成绩统计、题库审核 |
| 兼容性 | 真机/浏览器 | iOS Safari、Android Chrome、微信内置浏览器、桌面 Edge/Chrome |

E2E 必测链路：

1. 学校管理员创建教师 → 教师登录。
2. 教师创建试卷 → 发布班级测评。
3. 学生登录 → 开始答题 → 自动保存 → 交卷。
4. 教师查看成绩 → 补录/导入 → 查看统计。
5. 学生查看成绩、证书、成长曲线。
6. 题库管理员审核教师试题。
7. 越权访问返回 403；Token 过期返回 401。

### 8.10 浏览器与设备兼容

| 环境 | 支持范围 |
|---|---|
| 桌面浏览器 | Chrome、Edge 最近两个大版本；Firefox 最近两个大版本 |
| macOS 浏览器 | Safari 15+ |
| 移动端 | iOS Safari 15+、Android Chrome 100+ |
| 微信内置浏览器 | 微信当前主流版本，重点测试音频播放和文件上传 |
| 学生端屏幕 | 375px~430px 为主，兼容 768px 平板 |
| 管理端屏幕 | 1366×768 起，最低可用宽度 1280px |

兼容注意事项：

- 移动端音频播放必须由用户手势触发，不能依赖自动播放。
- iOS 对音频格式和音量控制有限制，优先提供 MP3。
- 低带宽环境下，答题页只预加载当前题音频，不批量加载全部资源。
- 微信 WebView 对下载行为限制较多，证书下载需提供“复制链接到浏览器打开”的兜底提示。
- 管理端表格和图表在 1366px 下不得出现横向遮挡关键操作。

### 8.11 7 天前端落地安排

| 天数 | 前端 A（何静媛） | 前端 B（董昂） | 共同交付 |
|---|---|---|---|
| 第 1 天 | 学生 H5 骨架、登录、路由、设计令牌 | 管理控制台骨架、角色菜单、题库页面框架 | Monorepo、Axios、OpenAPI 类型、403/404 |
| 第 2 天 | 学生班级、测评列表、教师班级/学生页面 | 账号管理、班级管理、题库与课程章节页面 | 分页、表单、上传组件 |
| 第 3 天 | 答题页、自动保存、音频播放 | 组卷、发布、撤回、题库审核页面 | 组卷发布联调 |
| 第 4 天 | 成绩、证书、成长曲线、AI 结果展示 | 五级统计、图表、成绩补录/导入页面 | 判分轮询、图表主题 |
| 第 5 天 | 学生/教师端缺项、异常状态、移动适配 | 管理端缺项、导出、批量操作、日志页面 | 全功能覆盖 |
| 第 6 天 | 学生答题全链路 E2E、真机测试 | 多角色菜单、数据范围、管理端 E2E | 缺陷修复、兼容性测试 |
| 第 7 天 | 学生端生产构建、演示数据检查 | 管理端生产构建、路由与权限检查 | 部署、演示、验收 |

前端代码所有权建议：

- 前端 A 负责 `apps/student-h5` 和 `apps/console/src/views/teacher`。
- 前端 B 负责 `apps/console/src/views/school|district|city|province|qbank`。
- `packages/api`、`packages/types` 由两人共同评审，接口变更必须同步更新。
- 公共布局、登录页、403/404 由前端 A 先完成，前端 B 直接复用。

### 8.12 前端验收清单

- [ ] 7 类角色登录后进入正确首页，菜单与角色匹配
- [ ] 未登录访问业务页跳转登录；越权访问展示 403
- [ ] 账号、班级、题库、试卷列表支持筛选、分页、空状态和错误重试
- [ ] 学校创建教师、区县创建学校、市州创建区县、省创建市州页面可操作
- [ ] 学生可通过班级号查询、申请加入、退出、转班
- [ ] 教师可手动组卷、自动组卷、暂存、修改、删除和发布
- [ ] 学生答题可自动保存、断线恢复、倒计时校准、交卷防重复
- [ ] 到时自动交卷后页面正确展示只读状态
- [ ] 音乐题音频可播放，错误点可定位到时间段
- [ ] 美术作品可上传、预览、展示四维评分与雷达图
- [ ] 成绩列表、详情、统计、成长曲线和证书下载可用
- [ ] 导入失败明细可查看，导出文件可正确下载
- [ ] 管理端 1366px 下表格、图表、弹窗无关键内容遮挡
- [ ] 生产构建通过，Source Map 未公开，CSP 与 HTTPS 已配置
- [ ] 核心 E2E 用例通过，401/403、空数据、超时、AI 降级有测试记录

### 8.13 边界与非目标

- 不为 7 个角色分别建设 7 个前端工程。
- 不使用前端计算最终成绩，不把标准答案、评分密钥放入前端代码。
- 不依赖前端倒计时触发自动交卷，自动交卷以服务端定时任务为准。
- 不在前端做跨组织数据过滤，所有数据范围由后端强制执行。
- 不引入 WebSocket、微前端、SSR 等超出 7 天交付目标的复杂架构。
- 不将 Token 放入 URL、图片地址、日志或第三方监控。
- 不以“隐藏按钮”替代接口鉴权。


## 附录 A：268 项功能与接口映射

本附录把 `人员安排.xlsx` 的 268 项验收功能逐项映射到接口编号。接口编号可在“A.1 接口索引”中查到具体方法与路径；一个功能由多个接口协作完成时，按调用顺序列出。

说明：

- `—` 表示纯前端展示/交互，没有独立后端接口；对应数据来自同页其他接口。
- `AI-01` / `AI-02` / `AI-03` 为后端代理或内部调用，不对学生端开放；学生通过成绩、报告等业务接口查看结果。
- `GRD-01`～`GRD-03` 是人工逐题评分能力，源功能清单没有单独列出，但主观题、作品题评分必须使用，不能再用“重新判分”代替。
- 接口编号是稳定契约；后续新增功能时新增编号，不复用或重排已有编号。

### A.1 接口索引

| 接口编号 | 方法 | 路径 | 文档章节 |
|---|---|---|---|
| AUTH-01 | `POST` | `/api/v1/auth/login` | 2.2.1 用户登录 |
| AUTH-02 | `POST` | `/api/v1/auth/refresh` | 2.2.2 刷新访问令牌 |
| AUTH-03 | `POST` | `/api/v1/auth/logout` | 2.2.3 退出登录 |
| AUTH-04 | `GET` | `/api/v1/auth/me` | 2.2.4 获取当前用户信息 |
| AUTH-05 | `PATCH` | `/api/v1/auth/me` | 2.2.5 修改个人信息 |
| AUTH-06 | `PATCH` | `/api/v1/auth/password` | 2.2.6 修改本人密码 |
| AUTH-07 | `GET` | `/api/v1/auth/menus` | 2.2.7 查询当前角色菜单 |
| ACC-01 | `GET` | `/api/v1/accounts` | 2.3.1 查询下级账号列表 |
| ACC-02 | `GET` | `/api/v1/accounts/{accountId}` | 2.3.2 查询账号详情 |
| ACC-03 | `POST` | `/api/v1/accounts/teachers` | 2.3.3 创建教师账号 |
| ACC-04 | `POST` | `/api/v1/accounts/teachers/import` | 2.3.4 批量导入教师账号 |
| ACC-05 | `POST` | `/api/v1/accounts/students` | 2.3.5 创建学生账号 |
| ACC-06 | `POST` | `/api/v1/accounts/schools` | 2.3.6 创建学校账号 |
| ACC-07 | `POST` | `/api/v1/accounts/districts` | 2.3.7 创建区县账号 |
| ACC-08 | `POST` | `/api/v1/accounts/cities` | 2.3.8 创建市州账号 |
| ACC-09 | `PATCH` | `/api/v1/accounts/{accountId}` | 2.3.9 修改账号信息 |
| ACC-10 | `DELETE` | `/api/v1/accounts/{accountId}` | 2.3.10 删除账号 |
| ACC-11 | `POST` | `/api/v1/accounts/{accountId}/reset-password` | 2.3.11 重置账号密码 |
| CLS-01 | `GET` | `/api/v1/classes` | 2.4.1 查询班级列表 |
| CLS-02 | `POST` | `/api/v1/classes` | 2.4.2 创建班级 |
| CLS-03 | `GET` | `/api/v1/classes/search` | 2.4.3 按班级号查询班级 |
| CLS-04 | `GET` | `/api/v1/classes/{classId}` | 2.4.4 查询班级详情 |
| CLS-05 | `PATCH` | `/api/v1/classes/{classId}` | 2.4.5 修改班级 |
| CLS-06 | `DELETE` | `/api/v1/classes/{classId}` | 2.4.6 解散班级 |
| CLS-07 | `POST` | `/api/v1/classes/{classId}/join` | 2.4.7 申请加入班级（学生/教师） |
| CLS-08 | `POST` | `/api/v1/classes/{classId}/leave` | 2.4.8 学生申请退出班级 |
| CLS-09 | `POST` | `/api/v1/classes/{classId}/change` | 2.4.9 学生申请更换班级 |
| CLS-10 | `GET` | `/api/v1/classes/{classId}/requests` | 2.4.10 查询班级申请列表 |
| CLS-11 | `POST` | `/api/v1/classes/{classId}/requests/{requestId}/review` | 2.4.11 审核班级申请 |
| CLS-12 | `GET` | `/api/v1/classes/{classId}/students` | 2.4.12 查询班级学生 |
| CLS-13 | `DELETE` | `/api/v1/classes/{classId}/students/{studentId}` | 2.4.13 移除班级学生 |
| CLS-14 | `POST` | `/api/v1/classes/{classId}/students/import` | 2.4.14 批量导入班级学生 |
| FILE-01 | `POST` | `/api/v1/files` | 2.5.1 通用文件上传 |
| FILE-02 | `DELETE` | `/api/v1/files/{fileId}` | 2.5.2 删除文件 |
| QST-01 | `GET` | `/api/v1/questions` | 3.2.1 查询试题列表 |
| QST-02 | `POST` | `/api/v1/questions` | 3.2.2 创建试题 |
| QST-03 | `GET` | `/api/v1/questions/{questionId}` | 3.2.3 查询试题详情 |
| QST-04 | `PATCH` | `/api/v1/questions/{questionId}` | 3.2.4 修改试题 |
| QST-05 | `DELETE` | `/api/v1/questions/{questionId}` | 3.2.5 删除试题 |
| QST-06 | `POST` | `/api/v1/questions/{questionId}/submit-review` | 3.2.6 提交试题审核 |
| QST-07 | `POST` | `/api/v1/questions/{questionId}/review` | 3.2.7 审核试题 |
| CRS-01 | `GET` | `/api/v1/courses` | 3.3.1 查询课程列表 |
| CRS-02 | `POST` | `/api/v1/courses` | 3.3.2 创建课程 |
| CRS-03 | `GET` | `/api/v1/courses/{courseId}` | 3.3.3 查询课程详情 |
| CRS-04 | `PATCH` | `/api/v1/courses/{courseId}` | 3.3.4 修改课程 |
| CRS-05 | `DELETE` | `/api/v1/courses/{courseId}` | 3.3.5 删除课程 |
| CHP-01 | `GET` | `/api/v1/courses/{courseId}/chapters` | 3.4.1 查询课程章节 |
| CHP-02 | `POST` | `/api/v1/courses/{courseId}/chapters` | 3.4.2 创建章节 |
| CHP-03 | `GET` | `/api/v1/chapters/{chapterId}` | 3.4.3 查询章节详情 |
| CHP-04 | `PATCH` | `/api/v1/chapters/{chapterId}` | 3.4.4 修改章节 |
| CHP-05 | `DELETE` | `/api/v1/chapters/{chapterId}` | 3.4.5 删除章节 |
| RES-01 | `POST` | `/api/v1/questions/{questionId}/resources` | 3.5.1 上传试题资源 |
| RES-02 | `DELETE` | `/api/v1/questions/{questionId}/resources/{resourceId}` | 3.5.2 删除试题资源 |
| LOG-01 | `GET` | `/api/v1/logs` | 3.6.1 查询操作日志列表 |
| LOG-02 | `GET` | `/api/v1/logs/{logId}` | 3.6.2 查询操作日志详情 |
| PAP-01 | `GET` | `/api/v1/papers` | 4.2.1 查询试卷列表 |
| PAP-02 | `POST` | `/api/v1/papers/manual` | 4.2.2 手动组卷 |
| PAP-03 | `POST` | `/api/v1/papers/auto` | 4.2.3 自动随机组卷 |
| PAP-04 | `GET` | `/api/v1/papers/{paperId}` | 4.2.4 查询试卷详情 |
| PAP-05 | `PATCH` | `/api/v1/papers/{paperId}` | 4.2.5 修改试卷 |
| PAP-06 | `PATCH` | `/api/v1/papers/{paperId}/draft` | 4.2.6 暂存试卷 |
| PAP-07 | `DELETE` | `/api/v1/papers/{paperId}` | 4.2.7 删除试卷 |
| PAP-08 | `GET` | `/api/v1/papers/{paperId}/materials/download` | 4.2.8 下载试卷音频/图片材料 |
| PAP-09 | `GET` | `/api/v1/papers/{paperId}/answers/download` | 4.2.9 下载试卷答案与解析 |
| PAP-10 | `POST` | `/api/v1/papers/practice/random` | 4.2.10 学生随机练习组卷 |
| ASM-01 | `GET` | `/api/v1/assessments` | 4.3.1 查询测评列表 |
| ASM-02 | `POST` | `/api/v1/assessments` | 4.3.2 发布测评 |
| ASM-03 | `GET` | `/api/v1/assessments/{assessmentId}` | 4.3.3 查询测评详情 |
| ASM-04 | `POST` | `/api/v1/assessments/{assessmentId}/withdraw` | 4.3.4 撤回测评 |
| ATT-01 | `POST` | `/api/v1/assessments/{assessmentId}/attempts` | 4.4.1 开始或继续答题 |
| ATT-02 | `GET` | `/api/v1/attempts/{attemptId}` | 4.4.2 获取答卷详情 |
| ATT-03 | `PATCH` | `/api/v1/attempts/{attemptId}/answers` | 4.4.3 保存答案 |
| ATT-04 | `POST` | `/api/v1/attempts/{attemptId}/submit` | 4.4.4 提交答卷 |
| SCR-01 | `GET` | `/api/v1/scores/me` | 4.5.1 查询本人成绩 |
| SCR-02 | `GET` | `/api/v1/scores` | 4.5.2 查询成绩列表 |
| SCR-03 | `GET` | `/api/v1/scores/statistics` | 4.5.3 查询班级/区域成绩统计 |
| SCR-04 | `GET` | `/api/v1/scores/statistics/list` | 4.5.4 分页查询区域统计列表/排名 |
| SCR-05 | `GET` | `/api/v1/scores/{scoreId}` | 4.5.5 查询成绩详情 |
| SCR-06 | `POST` | `/api/v1/scores/manual` | 4.5.6 成绩补录 |
| SCR-07 | `POST` | `/api/v1/scores/import` | 4.5.7 批量导入线下成绩 |
| SCR-08 | `POST` | `/api/v1/scores/{scoreId}/regrade` | 4.5.8 重新判分 |
| SCR-09 | `GET` | `/api/v1/scores/statistics/export` | 4.5.9 导出成绩统计 |
| GRD-01 | `GET` | `/api/v1/grading/tasks` | 4.5.10 查询待人工评分任务 |
| GRD-02 | `GET` | `/api/v1/grading/attempts/{attemptId}` | 4.5.11 查询人工评分详情 |
| GRD-03 | `PATCH` | `/api/v1/grading/attempts/{attemptId}/scores` | 4.5.12 提交人工评分 |
| CRT-01 | `POST` | `/api/v1/certificates/generate` | 4.6.1 生成测评证书 |
| CRT-02 | `GET` | `/api/v1/certificates` | 4.6.2 查询证书列表 |
| CRT-03 | `GET` | `/api/v1/certificates/{certificateId}` | 4.6.3 查询证书详情 |
| CRT-04 | `GET` | `/api/v1/certificates/{certificateId}/download` | 4.6.4 下载证书 |
| GRW-01 | `GET` | `/api/v1/students/{studentId}/growth-curve` | 4.7.1 查询学生历史成绩趋势 |
| GRW-02 | `GET` | `/api/v1/students/{studentId}/learning-report` | 4.7.2 查询学生学情报告 |
| AI-01 | `POST` | `/api/v1/ai/music/analyze` | 5.2.1 分析音乐演唱/演奏音频 |
| AI-02 | `POST` | `/api/v1/ai/art/score` | 5.3.1 分析美术作品图片 |
| AI-03 | `POST` | `/api/v1/ai/learning-report` | 5.4.1 生成学生个性化学情报告 |

### A.2 功能逐项映射

| 功能编号 | 一级模块 | 二级模块 | 具体功能 | 接口编号 | 映射说明 |
|---|---|---|---|---|---|
| F001 | 艺术素质测评系统 | 学生班级管理 | 通过班级号查询班级 | CLS-03 |  |
| F002 | 艺术素质测评系统 | 学生班级管理 | 加入班级 | CLS-07 |  |
| F003 | 艺术素质测评系统 | 学生班级管理 | 退出班级 | CLS-08 |  |
| F004 | 艺术素质测评系统 | 学生班级管理 | 更换班级 | CLS-09 |  |
| F005 | 艺术素质测评系统 | 学生素质教育展示 | 趣味课堂知识展示 | CRS-01、CRS-03 | 课程/章节内容展示；当前无独立知识点接口 |
| F006 | 艺术素质测评系统 | 班级信息查询 | 查看班级信息 | CLS-04 |  |
| F007 | 艺术素质测评系统 | 班级信息查询 | 查看班主任信息 | CLS-04 |  |
| F008 | 艺术素质测评系统 | 班级信息查询 | 操作提示 | — | 纯前端操作提示，无独立接口 |
| F009 | 艺术素质测评系统 | 音乐测评练习 | 音乐测评练习随机组卷 | PAP-10 |  |
| F010 | 艺术素质测评系统 | 音乐测评练习 | 音乐测评练习试卷信息 | PAP-10、ATT-02 |  |
| F011 | 艺术素质测评系统 | 音乐测评练习 | 音乐测评练习试题列表 | PAP-10、ATT-01、ATT-02 |  |
| F012 | 艺术素质测评系统 | 音乐测评练习 | 音乐测评练习答案查看 | SCR-05 |  |
| F013 | 艺术素质测评系统 | 音乐测评练习 | 音乐测评练习正确率数据分析 | SCR-01、SCR-05 | 练习交卷后按成绩详情统计正确率 |
| F014 | 艺术素质测评系统 | 音乐测评练习 | 音乐测评练习答案解析 | SCR-05 |  |
| F015 | 艺术素质测评系统 | 美术测评练习 | 美术测评练习随机组卷 | PAP-10 |  |
| F016 | 艺术素质测评系统 | 美术测评练习 | 美术测评练习试卷信息 | PAP-10、ATT-02 |  |
| F017 | 艺术素质测评系统 | 美术测评练习 | 美术测评练习试题列表 | PAP-10、ATT-01、ATT-02 |  |
| F018 | 艺术素质测评系统 | 美术测评练习 | 美术测评练习正确率数据分析 | SCR-01、SCR-05 | 练习交卷后按成绩详情统计正确率 |
| F019 | 艺术素质测评系统 | 美术测评练习 | 美术测评练习答案查看 | SCR-05 |  |
| F020 | 艺术素质测评系统 | 美术测评练习 | 美术测评练习答案解析 | SCR-05 |  |
| F021 | 艺术素质测评系统 | 音乐正式测评 | 音乐正式测评 | ASM-01、ASM-03、ATT-01 |  |
| F022 | 艺术素质测评系统 | 音乐正式测评 | 音乐正式测评试卷信息 | ASM-03、ATT-01、ATT-02 |  |
| F023 | 艺术素质测评系统 | 音乐正式测评 | 音乐测评试题列表 | ATT-01、ATT-02 |  |
| F024 | 艺术素质测评系统 | 音乐正式测评 | 音乐测评正确率数据分析 | SCR-01、SCR-05 |  |
| F025 | 艺术素质测评系统 | 音乐正式测评 | 音乐正式测评答案查看 | SCR-05 |  |
| F026 | 艺术素质测评系统 | 音乐正式测评 | 音乐正式测评答案解析 | SCR-05 |  |
| F027 | 艺术素质测评系统 | 美术正式测评 | 美术正式测评 | ASM-01、ASM-03、ATT-01 |  |
| F028 | 艺术素质测评系统 | 美术正式测评 | 音乐正式测评试卷信息 | ASM-03、ATT-01、ATT-02 |  |
| F029 | 艺术素质测评系统 | 美术正式测评 | 美术测评试题列表 | ATT-01、ATT-02 |  |
| F030 | 艺术素质测评系统 | 美术正式测评 | 美术测评正确率数据分析 | SCR-01、SCR-05 |  |
| F031 | 艺术素质测评系统 | 美术正式测评 | 美术正式测评答案查看 | SCR-05 |  |
| F032 | 艺术素质测评系统 | 美术正式测评 | 美术正式测评答案解析 | SCR-05 |  |
| F033 | 艺术素质测评系统 | 测评资源查看 | 播放艺术正式测评试题音频 | ATT-01、ATT-02 |  |
| F034 | 艺术素质测评系统 | 测评资源查看 | 查看艺术正式测评试题图片 | ATT-01、ATT-02 |  |
| F035 | 艺术素质测评系统 | 测评自动提交 | 艺术正式测评限时自动提交 | ATT-04 | 服务端 APScheduler 扫描到期答卷并调用交卷逻辑 |
| F036 | 艺术素质测评系统 | 课外自主学习 | 上传课外自主学习图片 | FILE-01 |  |
| F037 | 艺术素质测评系统 | 测评结果查看 | 查看艺术正式测评统计分析报告 | SCR-05、GRW-02 | 成绩详情 + 已落库学情报告 |
| F038 | 艺术素质测评系统 | 测评结果查看 | 查看艺术正式测评记录 | ASM-01、SCR-01 |  |
| F039 | 艺术素质测评系统 | 测评结果查看 | 查看成绩曲线 | GRW-01 |  |
| F040 | 艺术素质测评系统 | 测评结果查看 | 成绩曲线评估报告 | GRW-01、GRW-02、AI-03 | 成长曲线 + 学情报告；AI-03 由后端生成 |
| F041 | 艺术素质测评系统 | 测评结果查看 | 查看艺术正式测评成绩 | SCR-01、SCR-05 |  |
| F042 | 艺术素质测评系统 | 个人证书管理 | 查看音乐正式测评证书 | CRT-02、CRT-03 |  |
| F043 | 艺术素质测评系统 | 个人证书管理 | 下载音乐正式测评证书 | CRT-04 |  |
| F044 | 艺术素质测评系统 | 个人证书管理 | 查看美术正式测评证书 | CRT-02、CRT-03 |  |
| F045 | 艺术素质测评系统 | 个人证书管理 | 下载美术正式测评证书 | CRT-04 |  |
| F046 | 艺术素质测评系统 | 查看班级测评信息 | 查看测评成绩 | ASM-01、SCR-01 |  |
| F047 | 艺术素质测评系统 | 查看班级测评信息 | 按学科查看班级测评成绩 | ASM-01、SCR-01 |  |
| F048 | 艺术素质测评系统 | 查看班级测评信息 | 按编码搜索班级测评 | CLS-03、ASM-01 | 班级号查询 + 测评列表筛选 |
| F049 | 艺术素质测评系统 | 查看班级测评信息 | 按名称搜索班级测评 | ASM-01 |  |
| F050 | 艺术素质测评系统 | 个人信息管理 | 查看个人信息 | AUTH-04 |  |
| F051 | 艺术素质测评系统 | 个人信息管理 | 个人成长曲线 | GRW-01 |  |
| F052 | 艺术素质测评系统 | 个人信息管理 | 查看美术个人成长曲线 | GRW-01 |  |
| F053 | 艺术素质测评系统 | 个人信息管理 | 查看音乐个人成长曲线 | GRW-01 |  |
| F054 | 艺术素质测评系统 | 个人信息管理 | 修改个人信息 | AUTH-05 |  |
| F055 | 教师端 | 班级管理 | 按编号搜索班级 | CLS-01、CLS-03 |  |
| F056 | 教师端 | 班级管理 | 按名称搜索班级 | CLS-01 |  |
| F057 | 教师端 | 班级管理 | 班级信息 | CLS-04 |  |
| F058 | 教师端 | 班级管理 | 创建班级 | CLS-02 |  |
| F059 | 教师端 | 班级管理 | 修改班级 | CLS-05 |  |
| F060 | 教师端 | 班级管理 | 解散班级 | CLS-06 |  |
| F061 | 教师端 | 班级管理 | 加入班级 | CLS-07 | 教师申请成为科任教师，与学生加入共用申请接口 |
| F062 | 教师端 | 班级管理 | 班级学生批量导入 | CLS-14 |  |
| F063 | 教师端 | 班级管理 | 审核通过班级学生申请 | CLS-10、CLS-11 |  |
| F064 | 教师端 | 班级管理 | 审核更换班级学生 | CLS-10、CLS-11 |  |
| F065 | 教师端 | 班级管理 | 审核更换班级学生 | CLS-10、CLS-11 |  |
| F066 | 教师端 | 科任教师管理 | 审核科任教师加入申请 | CLS-07、CLS-10、CLS-11 | 教师申请 + 申请列表 + 审核 |
| F067 | 教师端 | 学生管理 | 查看学生信息 | CLS-12 |  |
| F068 | 教师端 | 学生管理 | 通过账号搜索学生 | CLS-12 |  |
| F069 | 教师端 | 学生管理 | 通过学籍搜索学生 | CLS-12 |  |
| F070 | 教师端 | 学生管理 | 重置学生密码 | ACC-11 |  |
| F071 | 教师端 | 学生管理 | 查看学生学籍 | CLS-12、ACC-02 |  |
| F072 | 教师端 | 学生管理 | 下载学生身份材料 | ACC-02、FILE-01 | 账号详情返回材料签名 URL，文件由 FILE-01 上传 |
| F073 | 教师端 | 学生管理 | 外校学生导入 | CLS-14、ACC-05 |  |
| F074 | 教师端 | 试题查询 | 试题库信息 | QST-01 |  |
| F075 | 教师端 | 试题查询 | 按学科查看试题库 | QST-01 |  |
| F076 | 教师端 | 试题查询 | 按难度查看试题库 | QST-01 |  |
| F077 | 教师端 | 试题查询 | 按题目类型查看试题库 | QST-01 |  |
| F078 | 教师端 | 试题查询 | 按年级查看试题库 | QST-01 |  |
| F079 | 教师端 | 教师组卷管理 | 手动创建试卷表单 | PAP-02 |  |
| F080 | 教师端 | 教师组卷管理 | 创建班级测评试卷 | PAP-02 |  |
| F081 | 教师端 | 教师组卷管理 | 暂存班级测评试卷 | PAP-06 |  |
| F082 | 教师端 | 教师组卷管理 | 修改班级测评试卷 | PAP-05 |  |
| F083 | 教师端 | 教师组卷管理 | 删除班级测评试卷 | PAP-07 |  |
| F084 | 教师端 | 教师组卷管理 | 查看班级测评试卷 | PAP-04 |  |
| F085 | 教师端 | 教师组卷管理 | 查看班级测评试题解析 | PAP-04、QST-03 | 试卷详情 + 试题详情查看解析 |
| F086 | 教师端 | 教师组卷管理 | 自动生成试卷表单 | PAP-03 |  |
| F087 | 教师端 | 教师组卷管理 | 自动生成班级测评试卷 | PAP-03 |  |
| F088 | 教师端 | 教师试题下载 | 下载班级测评试卷音频图片材料 | PAP-08 |  |
| F089 | 教师端 | 教师试题下载 | 下载班级测评试卷答案 | PAP-09 |  |
| F090 | 教师端 | 音乐测评发布 | 发布音乐测评表单 | ASM-02 |  |
| F091 | 教师端 | 音乐测评发布 | 发布音乐测评试卷到班级 | ASM-02 |  |
| F092 | 教师端 | 音乐测评发布 | 撤回已发布音乐测评试卷 | ASM-04 |  |
| F093 | 教师端 | 美术测评发布 | 发布美术测评表单 | ASM-02 |  |
| F094 | 教师端 | 美术测评发布 | 发布美术测评试卷到班级 | ASM-02 |  |
| F095 | 教师端 | 美术测评发布 | 撤回已发布美术测评试卷 | ASM-04 |  |
| F096 | 教师端 | 学生评分 | 查看学生课外学习材料 | GRD-02、FILE-01 | 人工评分详情含学生作品/材料，文件由 FILE-01 上传 |
| F097 | 教师端 | 学生评分 | 查看学生测评成绩 | SCR-02、SCR-05 |  |
| F098 | 教师端 | 学生评分 | 为学生平时表现评分 | SCR-06 | 平时表现分走成绩补录，需填写原因 |
| F099 | 教师端 | 学生评分 | 成绩导入模板 | SCR-07 | 模板列在 SCR-07 中定义 |
| F100 | 教师端 | 学生评分 | 导入学生线下成绩 | SCR-07 |  |
| F101 | 教师端 | 学生证书管理 | 查看学生证书 | CRT-02、CRT-03 |  |
| F102 | 教师端 | 学生证书管理 | 导出学生所有成绩 | SCR-09 | dimension=student 导出该生全部正式测评成绩 |
| F103 | 教师端 | 学生证书管理 | 导出学生证书 | CRT-04 |  |
| F104 | 教师端 | 个人信息管理 | 查看个人资料 | AUTH-04 |  |
| F105 | 教师端 | 个人信息管理 | 修改个人资料 | AUTH-05 |  |
| F106 | 学校端 | 教师账号管理 | 教师账号表单 | ACC-03 |  |
| F107 | 学校端 | 教师账号管理 | 创建教师账号 | ACC-03 |  |
| F108 | 学校端 | 教师账号管理 | 重置教师账号密码 | ACC-11 |  |
| F109 | 学校端 | 教师账号管理 | 批量创建教师账号 | ACC-04 |  |
| F110 | 学校端 | 教师账号管理 | 修改教师账号信息 | ACC-09 |  |
| F111 | 学校端 | 教师账号管理 | 删除教师账号信息 | ACC-10 |  |
| F112 | 学校端 | 教师账号管理 | 查询教师账号信息 | ACC-01、ACC-02 |  |
| F113 | 学校端 | 学生账号管理 | 学生账号表单 | ACC-05 |  |
| F114 | 学校端 | 学生账号管理 | 修改学生账号信息 | ACC-09 |  |
| F115 | 学校端 | 学生账号管理 | 删除学生账号信息 | ACC-10 |  |
| F116 | 学校端 | 学生账号管理 | 重置学生账号密码 | ACC-11 |  |
| F117 | 学校端 | 学生账号管理 | 查询学生账号信息 | ACC-01、ACC-02 |  |
| F118 | 学校端 | 学校组卷管理 | 创建学校测评试卷 | PAP-02 |  |
| F119 | 学校端 | 学校组卷管理 | 学校测评试卷表单信息 | PAP-02、PAP-04 |  |
| F120 | 学校端 | 学校组卷管理 | 暂存学校测评试卷 | PAP-06 |  |
| F121 | 学校端 | 学校组卷管理 | 修改学校测评试卷 | PAP-05 |  |
| F122 | 学校端 | 学校组卷管理 | 按难度查看试题库 | QST-01 |  |
| F123 | 学校端 | 学校组卷管理 | 按题目类型查看试题库 | QST-01 |  |
| F124 | 学校端 | 学校组卷管理 | 查看学校测评试题解析 | PAP-04、QST-03 | 试卷详情 + 试题详情查看解析 |
| F125 | 学校端 | 学校组卷管理 | 删除学校测评试卷 | PAP-07 |  |
| F126 | 学校端 | 学校组卷管理 | 查看学校测评试卷 | PAP-04 |  |
| F127 | 学校端 | 学校试题下载 | 下载学校测评试卷音频图片材料 | PAP-08 |  |
| F128 | 学校端 | 学校试题下载 | 下载学校测评试卷答案 | PAP-09 |  |
| F129 | 学校端 | 学校音乐测评发布 | 按年级发布音乐测评试卷 | ASM-02 |  |
| F130 | 学校端 | 学校音乐测评发布 | 查看学校音乐测评数据统计 | SCR-03、SCR-04 |  |
| F131 | 学校端 | 学校美术测评发布 | 按年级发布美术测评试卷 | ASM-02 |  |
| F132 | 学校端 | 学校美术测评发布 | 查看学校美术测评数据统计 | SCR-03、SCR-04 |  |
| F133 | 学校端 | 测评成绩补录 | 测评补录表单 | SCR-06 |  |
| F134 | 学校端 | 测评成绩补录 | 学校测评补录 | SCR-06 |  |
| F135 | 学校端 | 测评数据统计 | 学校年级测评数据统计 | SCR-03、SCR-04 |  |
| F136 | 学校端 | 测评数据统计 | 导出学校年级测评数据统计 | SCR-09 |  |
| F137 | 区县端 | 学校测评数据查询 统计 | 按学校查看艺术测评数据统计 | SCR-04 |  |
| F138 | 区县端 | 学校测评数据查询 统计 | 按地区查看艺术测评数据统计 | SCR-03、SCR-04 |  |
| F139 | 区县端 | 学校测评数据查询 统计 | 按学校导出艺术测评数据统计 | SCR-09 |  |
| F140 | 区县端 | 学校测评数据查询 统计 | 按地区导出艺术测评数据统计 | SCR-09 |  |
| F141 | 区县端 | 学校账号管理 | 学校账号表单信息 | ACC-06 |  |
| F142 | 区县端 | 学校账号管理 | 创建学校账号 | ACC-06 |  |
| F143 | 区县端 | 学校账号管理 | 修改学校账号 | ACC-09 |  |
| F144 | 区县端 | 学校账号管理 | 删除学校账号 | ACC-10 |  |
| F145 | 区县端 | 学校账号管理 | 查询学校账号 | ACC-01、ACC-02 |  |
| F146 | 区县端 | 学校账号管理 | 重置学校账号密码 | ACC-11 |  |
| F147 | 区县端 | 区县组卷管理 | 创建区县测评试卷 | PAP-02 |  |
| F148 | 区县端 | 区县组卷管理 | 区县测评试卷信息 | PAP-02、PAP-04 |  |
| F149 | 区县端 | 区县组卷管理 | 按难度查看试题库 | QST-01 |  |
| F150 | 区县端 | 区县组卷管理 | 按题目类型查看试题库 | QST-01 |  |
| F151 | 区县端 | 区县组卷管理 | 查看区县测评试题解析 | PAP-04、QST-03 | 试卷详情 + 试题详情查看解析 |
| F152 | 区县端 | 区县组卷管理 | 修改区县测评试卷 | PAP-05 |  |
| F153 | 区县端 | 区县组卷管理 | 删除区县测评试卷 | PAP-07 |  |
| F154 | 区县端 | 区县组卷管理 | 查看区县测评试卷 | PAP-04 |  |
| F155 | 区县端 | 区县试题下载 | 下载区县测评试卷音频图片材料 | PAP-08 |  |
| F156 | 区县端 | 区县试题下载 | 下载区县测评试卷答案 | PAP-09 |  |
| F157 | 区县端 | 区县测评发布 | 按学校发布区县测评试卷 | ASM-02 |  |
| F158 | 区县端 | 区县测评数据统计 | 查看区县测评数据统计 | SCR-03、SCR-04 |  |
| F159 | 区县端 | 区县测评数据统计 | 查看学校测评数据统计 | SCR-04 |  |
| F160 | 区县端 | 区县测评数据统计 | 导出区县测评数据统计 | SCR-09 |  |
| F161 | 区县端 | 区县测评数据统计 | 导出学校测评数据统计 | SCR-09 |  |
| F162 | 区县端 | 区县测评补录 | 区县测评补录 | SCR-06、SCR-07 |  |
| F163 | 市州端 | 区县测评数据查询 统计 | 按学校查看艺术测评数据统计 | SCR-04 |  |
| F164 | 市州端 | 区县测评数据查询 统计 | 按地区查看艺术测评数据统计 | SCR-04 |  |
| F165 | 市州端 | 区县测评数据查询 统计 | 按学校导出艺术测评数据统计 | SCR-09 |  |
| F166 | 市州端 | 区县测评数据查询 统计 | 按地区导出艺术测评数据统计 | SCR-09 |  |
| F167 | 市州端 | 区县账号管理 | 学校账号表单信息 | ACC-06 |  |
| F168 | 市州端 | 区县账号管理 | 创建市直属学校账号 | ACC-06 |  |
| F169 | 市州端 | 区县账号管理 | 修改市直属学校账号 | ACC-09 |  |
| F170 | 市州端 | 区县账号管理 | 删除市直属学校账号 | ACC-10 |  |
| F171 | 市州端 | 区县账号管理 | 查询市直属学校账号 | ACC-01、ACC-02 |  |
| F172 | 市州端 | 区县账号管理 | 创建区县账号 | ACC-07 |  |
| F173 | 市州端 | 区县账号管理 | 修改区县账号信息 | ACC-09 |  |
| F174 | 市州端 | 区县账号管理 | 删除区县账号 | ACC-10 |  |
| F175 | 市州端 | 区县账号管理 | 查询区县账号 | ACC-01、ACC-02 |  |
| F176 | 市州端 | 区县账号管理 | 重置学校账号密码 | ACC-11 |  |
| F177 | 市州端 | 市州组卷管理 | 创建市州测评试卷 | PAP-02 |  |
| F178 | 市州端 | 市州组卷管理 | 市州测评试卷表单信息 | PAP-02 |  |
| F179 | 市州端 | 市州组卷管理 | 按难度查看试题库 | QST-01 |  |
| F180 | 市州端 | 市州组卷管理 | 按题目类型查看试题库 | QST-01 |  |
| F181 | 市州端 | 市州组卷管理 | 查看市州测评试题解析 | PAP-04、QST-03 | 试卷详情 + 试题详情查看解析 |
| F182 | 市州端 | 市州组卷管理 | 修改市州测评试卷 | PAP-05 |  |
| F183 | 市州端 | 市州组卷管理 | 删除市州测评试卷 | PAP-07 |  |
| F184 | 市州端 | 市州组卷管理 | 查看市州测评试卷 | PAP-04 |  |
| F185 | 市州端 | 市州试题下载 | 下载市州测评试卷音频图片材料 | PAP-08 |  |
| F186 | 市州端 | 市州试题下载 | 下载市州测评试卷答案 | PAP-09 |  |
| F187 | 市州端 | 市州测评发布 | 按地区发布市州测评试卷 | ASM-02 |  |
| F188 | 市州端 | 市州测评发布 | 按学校发布市州测评试卷 | ASM-02 |  |
| F189 | 市州端 | 市州测评数据统计 | 查看市州测评数据统计 | SCR-03、SCR-04 |  |
| F190 | 市州端 | 市州测评数据统计 | 查看区县测评数据统计 | SCR-04 |  |
| F191 | 市州端 | 市州测评数据统计 | 查看学校测评数据统计 | SCR-04 |  |
| F192 | 市州端 | 市州测评数据统计 | 导出市州测评数据统计 | SCR-09 |  |
| F193 | 市州端 | 市州测评数据统计 | 导出区县测评数据统计 | SCR-09 |  |
| F194 | 市州端 | 市州测评数据统计 | 导出学校测评数据统计 | SCR-09 |  |
| F195 | 市州端 | 市州测评补录 | 市州测评补录 | SCR-06、SCR-07 |  |
| F196 | 省级管理员端 | 市州测评数据查询 统计 | 按学校查看艺术测评数据统计 | SCR-04 |  |
| F197 | 省级管理员端 | 市州测评数据查询 统计 | 按市州查看艺术测评数据统计 | SCR-04 |  |
| F198 | 省级管理员端 | 市州测评数据查询 统计 | 按学校导出艺术测评数据统计 | SCR-09 |  |
| F199 | 省级管理员端 | 市州测评数据查询 统计 | 按市州导出艺术测评数据统计 | SCR-09 |  |
| F200 | 省级管理员端 | 省级组卷管理 | 省级测评试卷表单信息 | PAP-02 |  |
| F201 | 省级管理员端 | 省级组卷管理 | 创建省级测评试卷 | PAP-02 |  |
| F202 | 省级管理员端 | 省级组卷管理 | 按难度查看试题库 | QST-01 |  |
| F203 | 省级管理员端 | 省级组卷管理 | 按题目类型查看试题库 | QST-01 |  |
| F204 | 省级管理员端 | 省级组卷管理 | 查看市州测评试题解析 | PAP-04、QST-03 | 试卷详情 + 试题详情查看解析 |
| F205 | 省级管理员端 | 省级组卷管理 | 修改省级测评试卷 | PAP-05 |  |
| F206 | 省级管理员端 | 省级组卷管理 | 删除省级测评试卷 | PAP-07 |  |
| F207 | 省级管理员端 | 省级组卷管理 | 查看省级测评试卷 | PAP-04 |  |
| F208 | 省级管理员端 | 省级试题下载 | 下载省级测评试卷音频图片材料 | PAP-08 |  |
| F209 | 省级管理员端 | 省级试题下载 | 下载省级测评试卷答案 | PAP-09 |  |
| F210 | 省级管理员端 | 省级测评发布 | 按市州发布省级测评试卷 | ASM-02 |  |
| F211 | 省级管理员端 | 省级测评发布 | 按学校发布省级测评试卷 | ASM-02 |  |
| F212 | 省级管理员端 | 省级测评发布 | 查看省级测评试卷 | PAP-04 |  |
| F213 | 省级管理员端 | 省级测评数据统计 | 省级测评数据统计 | SCR-03、SCR-04 |  |
| F214 | 省级管理员端 | 学生账号管理 | 学生账号表单信息 | ACC-05 |  |
| F215 | 省级管理员端 | 学生账号管理 | 增加学生账号信息 | ACC-05 |  |
| F216 | 省级管理员端 | 学生账号管理 | 修改学生账号信息 | ACC-09 |  |
| F217 | 省级管理员端 | 学生账号管理 | 删除学生账号信息 | ACC-10 |  |
| F218 | 省级管理员端 | 学生账号管理 | 重置学生账号密码 | ACC-11 |  |
| F219 | 省级管理员端 | 学生账号管理 | 按学籍查询学生信息 | ACC-01 |  |
| F220 | 省级管理员端 | 学生账号管理 | 按账号查询学生信息 | ACC-01 |  |
| F221 | 省级管理员端 | 学校账号管理 | 学校账号表单信息 | ACC-06 |  |
| F222 | 省级管理员端 | 学校账号管理 | 创建学校账号 | ACC-06 |  |
| F223 | 省级管理员端 | 学校账号管理 | 修改学校账号 | ACC-09 |  |
| F224 | 省级管理员端 | 学校账号管理 | 删除学校账号 | ACC-10 |  |
| F225 | 省级管理员端 | 学校账号管理 | 查询学校账号 | ACC-01、ACC-02 |  |
| F226 | 省级管理员端 | 学校账号管理 | 重置学校账号密码 | ACC-11 |  |
| F227 | 省级管理员端 | 区县账号管理 | 区县账号表单信息 | ACC-07 |  |
| F228 | 省级管理员端 | 区县账号管理 | 创建区县账号 | ACC-07 |  |
| F229 | 省级管理员端 | 区县账号管理 | 修改区县账号 | ACC-09 |  |
| F230 | 省级管理员端 | 区县账号管理 | 删除区县账号 | ACC-10 |  |
| F231 | 省级管理员端 | 区县账号管理 | 查询区县账号 | ACC-01、ACC-02 |  |
| F232 | 省级管理员端 | 区县账号管理 | 重置区县账号密码 | ACC-11 |  |
| F233 | 省级管理员端 | 市级账号管理 | 市级账号表单信息 | ACC-08 |  |
| F234 | 省级管理员端 | 市级账号管理 | 创建市州账号 | ACC-08 |  |
| F235 | 省级管理员端 | 市级账号管理 | 修改市州账号 | ACC-09 |  |
| F236 | 省级管理员端 | 市级账号管理 | 删除市州账号 | ACC-10 |  |
| F237 | 省级管理员端 | 市级账号管理 | 查询市州账号 | ACC-01、ACC-02 |  |
| F238 | 省级管理员端 | 市级账号管理 | 重置市州账号密码 | ACC-11 |  |
| F239 | 省级管理员端 | 测评率导出 | 导出全省地区测评参与率 | SCR-04、SCR-09 | groupBy=city 导出全省各地区参与率 |
| F240 | 省级管理员端 | 系统日志管理 | 用户操作日志表单信息 | LOG-01 | 操作日志列表 |
| F241 | 省级管理员端 | 系统日志管理 | 查看用户操作日志信息 | LOG-01、LOG-02 |  |
| F242 | 题库管理端 | 试题管理 | 试题表单信息 | QST-02 |  |
| F243 | 题库管理端 | 试题管理 | 管理员试题查询 | QST-01 |  |
| F244 | 题库管理端 | 试题管理 | 管理员试题创建 | QST-02 |  |
| F245 | 题库管理端 | 试题管理 | 管理员修改试题 | QST-04 |  |
| F246 | 题库管理端 | 试题管理 | 管理员删除试题 | QST-05 |  |
| F247 | 题库管理端 | 试题管理 | 教师试题查询 | QST-01 |  |
| F248 | 题库管理端 | 试题管理 | 教师试题创建 | QST-02 |  |
| F249 | 题库管理端 | 试题管理 | 教师修改试题 | QST-04 |  |
| F250 | 题库管理端 | 试题管理 | 教师删除试题 | QST-05 |  |
| F251 | 题库管理端 | 试题审核 | 管理员审核教师试题 | QST-07 |  |
| F252 | 题库管理端 | 试题审核 | 管理员修改教师试题 | QST-04 |  |
| F253 | 题库管理端 | 试题审核 | 管理员删除教师试题 | QST-05 |  |
| F254 | 题库管理端 | 试题资源管理 | 试题图片上传 | RES-01 |  |
| F255 | 题库管理端 | 试题资源管理 | 试题图片删除 | RES-02 |  |
| F256 | 题库管理端 | 试题资源管理 | 试题音频上传 | RES-01 |  |
| F257 | 题库管理端 | 试题资源管理 | 试题音频删除 | RES-02 |  |
| F258 | 题库管理端 | 课程管理 | 课程表单信息 | CRS-02 |  |
| F259 | 题库管理端 | 课程管理 | 课程查询 | CRS-01、CRS-03 |  |
| F260 | 题库管理端 | 课程管理 | 课程创建 | CRS-02 |  |
| F261 | 题库管理端 | 课程管理 | 课程修改 | CRS-04 |  |
| F262 | 题库管理端 | 课程管理 | 课程删除 | CRS-05 |  |
| F263 | 题库管理端 | 章节管理 | 章节查询 | CHP-01、CHP-03 |  |
| F264 | 题库管理端 | 章节管理 | 章节创建 | CHP-02 |  |
| F265 | 题库管理端 | 章节管理 | 章节修改 | CHP-04 |  |
| F266 | 题库管理端 | 章节管理 | 章节删除 | CHP-05 |  |
| F267 | 题库管理端 | 题库日志管理 | 用户操作日志表单信息 | LOG-01 | 操作日志列表 |
| F268 | 题库管理端 | 题库日志管理 | 查看用户操作日志信息 | LOG-01、LOG-02 |  |

### A.3 源清单未单列但必须实现的接口

| 接口编号 | 能力 | 为什么必须存在 |
|---|---|---|
| AUTH-02 | Refresh Token 刷新 | Access Token 30 分钟，正式测评最长 300 分钟，自动保存必须能静默续期 |
| AUTH-07 | 角色菜单 | `/auth/me` 只返回用户资料和权限码，菜单必须有独立数据源 |
| ACC-04 | 教师批量导入 | 学校端存在“批量创建教师账号”验收项，单条创建无法满足 |
| PAP-08 / PAP-09 | 试卷材料/答案下载 | 教师端、学校端、区县端、市州端、省端均有对应下载验收项 |
| PAP-10 | 学生随机练习 | 音乐/美术练习随机组卷是 P0，原 `/papers/auto` 不向学生开放 |
| SCR-04 | 区域统计列表/排名 | 管理端需要多行表格和排名，单对象统计无法渲染 |
| GRD-01～GRD-03 | 人工逐题评分 | 主观题、作品题必须有正式评分入口；重新判分只重算总分 |
| GRW-02 | 学情报告读取 | AI 生成接口不向学生开放，学生需要业务接口读取已落库报告 |

---

**文档结束**  
本文档覆盖账号与权限、题库管理、测评核心业务、AI 模型接口四个后端模块，并补充了学生 H5、管理控制台的前端技术方案、94 个接口索引和 268 项功能映射，可直接用于开发排期、联调与验收。
