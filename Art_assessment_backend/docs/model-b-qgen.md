# 美术出题模型（Model B）接入说明

## 定位

`01_给后端A(1)` 交付的是 Qwen2.5-3B-Instruct + QLoRA 的美术出题模型。本系统只把它当作
**出题辅助**：

- 生成/导入的题目一律 `pending`，必须由题库管理员审核通过后才进入公共题库；
- 不调用模型的 `/paper`、`/grade`，组卷和判分继续走现有 `exams` 业务；
- 默认只接受单选、判断题；填空题、简答题按现有产品规则丢弃；
- 在线生成默认关闭（`QGEN_ENABLED=false`），服务不可用不影响题库、组卷、测评、成绩。

## 一键启动

项目根目录的 `start_system.bat` 会按顺序启动后端（8000）、前端（5173）、
音频标签模型（8100）和 AI 出题模型（8002），已在运行的端口会自动跳过：

```bat
C:\Users\ter\Desktop\终\start_system.bat
```

8002 需要同时满足两个条件才会自动启动，否则脚本会跳过并提示：

1. 基座模型 `Qwen2.5-3B-Instruct` 存在：读取环境变量 `QGEN_MODEL`，或放在
   `D:\models\Qwen2.5-3B-Instruct` / `%USERPROFILE%\models\Qwen2.5-3B-Instruct`；
2. 独立环境 `01_给后端A(1)\.venv` 已安装 `requirements.txt`。

8002 启动时脚本会给后端设置 `QGEN_ENABLED=1`，无需再手动改 `.env`；
未启动 8002 时保持 `QGEN_ENABLED=0`，前端「AI 出题」按钮会提示服务未启用。

## 两种使用方式

### 方式一：离线导入交付题库（不需要 GPU / 8002 服务）

```bash
# 预览：只统计，不写库
python manage.py import_qgen_bank --dry-run

# 正式导入：全部写为待审题
python manage.py import_qgen_bank
```

默认读取 `QGEN_BANK_PATH`，留空时使用
`../01_给后端A(1)/题库数据/train_clean_2698.jsonl`。常用参数：

| 参数 | 说明 |
| --- | --- |
| `--path` | 指定题卡 jsonl |
| `--dry-run` | 只输出统计 |
| `--limit` | 最多读取多少行 |
| `--grade` | 只处理某个年级 |
| `--allow-fill-blank` | 同时导入填空题（默认关闭） |
| `--actor` | 创建人用户名，默认第一位题库管理员 |
| `--near-threshold` | 近似重复 Jaccard 阈值，默认 0.9 |

导入过程会：

1. 过滤 `short_answer`（系统已取消简答题）和 `fill_blank`（默认关闭）；
2. 按 `apps/qbank/qgen_unit_map.json` 把模型单元映射到系统课程/章节，未映射直接跳过；
3. 清洗题干，拦截「下图 / 以下画作 / 第几幅」等图片依赖题；
4. 拦截「给满分 / 即可得分」等评分话术；
5. 按学科+年级+清洗后题干精确去重，再用 3-gram Jaccard 做近似去重；
6. 写入 `Question(status=pending, creator=题库管理员)`，并记录 `source_meta`。

### 方式二：在线生成（需要 GPU、基座模型和 8002 服务）

```bash
# 基座 Qwen2.5-3B-Instruct 需单独准备（交付包只有 LoRA 适配器）
set QGEN_MODEL=D:\models\Qwen2.5-3B-Instruct
set QGEN_ADAPTER=C:\Users\ter\Desktop\终\01_给后端A(1)\模型权重\qgen_lora_3b_v4
set QGEN_LOAD_4BIT=1

cd C:\Users\ter\Desktop\终\01_给后端A(1)\服务代码
python -m uvicorn model_b_qgen.app:app --host 127.0.0.1 --port 8002
```

然后在 `.env` 中打开：

```bash
QGEN_ENABLED=true
QGEN_URL=http://127.0.0.1:8002
QGEN_TIMEOUT=90
```

题库管理端会出现「AI 出题」按钮；也可用命令批量生成：

```bash
python manage.py generate_qgen_questions --unit g7-u2 --knowledge-point 色相 \
  --type single_choice --difficulty 1 --count 3
```

### 方式二替代：云 API（暂时没有本地模型时）

设置 `QGEN_PROVIDER=api` 后，后端不再调用 8002，改为调用兼容 OpenAI
Chat Completions 的接口，出题结果仍走同一套校验、查重和待审入库流程。

```bash
QGEN_ENABLED=true
QGEN_PROVIDER=api
QGEN_API_BASE=https://api.deepseek.com/v1
QGEN_API_KEY=你的密钥
QGEN_API_MODEL=deepseek-chat
QGEN_API_TIMEOUT=60
```

常见服务商的兼容地址：

| 服务商 | `QGEN_API_BASE` | 模型示例 |
| --- | --- | --- |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| 智谱 | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |

密钥只写在 `.env`，不要提交到仓库。云 API 模式同样只支持单选、判断题；
提示词、图片依赖拦截、评分话术拦截和查重规则与本地模型一致。
接口未配置时「AI 出题」返回 503，不影响题库、组卷和判分。

## 接口

| 方法 | 路径 | 角色 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/v1/questions/qgen/catalog` | 题库管理员 | 已映射到系统章节的出题目录 |
| POST | `/api/v1/questions/qgen/generate` | 题库管理员 | 生成一道题并保存为待审 |

`generate` 请求体：

```json
{"unitId": "g7-u2", "knowledgePoint": "色相", "type": "single_choice", "difficulty": 1}
```

响应包含 `question`（新待审题详情）、`warnings`、`model`（模型与请求元信息）。
服务未启用返回 503，内容重复返回 409，模型输出未通过校验返回 502。

## 图题接入（2026-11-16）

新版 `01_后端A接入包` 的 8002 服务支持图题。系统侧已按契约接入：

1. 在线生成默认带 `with_image: true`（`QGEN_WITH_IMAGE` 可关）；模型只在
   该知识点有同题型图素材时出图题，否则自动退回文字题，不会串题型。
2. `resources` 中只入库 `role=question` 的题干配图；`role=reference` 是教学
   参考图，不入库、不在题干区展示。
3. 配图从 8002 下载后按 `question_image` 存入本地媒体库（或 MinIO），生成
   `QuestionResource`，前端通过 `/media/...` 展示；不依赖 8002 长期在线。
4. 题干出现「下图/如图/第几幅」等图片依赖表述时，必须同时有题干配图，
   否则仍按 `image_dependent` 跳过，避免学生看不到图的残题。
5. `fact_ids`、`generated_by`、配图清单写入 `Question.source_meta`，便于人工
   溯源；不新增数据库字段。
6. 前端「AI 出题」结果预览与审核弹窗会展示题干配图；题库详情、学生作答页
   原本已支持 `resources` 图片渲染。

相关配置：

```env
QGEN_WITH_IMAGE=true
QGEN_RESOURCE_URL_BASE=/resources
QGEN_RESOURCE_TIMEOUT=30
QGEN_RESOURCE_MAX_BYTES=10485760
```

只允许从 `QGEN_URL` 或绝对 `QGEN_RESOURCE_URL_BASE` 下载图片，避免服务返回
任意 URL 造成 SSRF；下载失败会中止入库并返回 502/503，不会留下无图的残题。

## 单元映射

模型目录是 2022 课标草稿的 36 个单元（每年级 4 个），与教材章节不是一一对应。
默认映射在 `apps/qbank/qgen_unit_map.json`，`chapter` 必须与对应年级美术课程下的
章节名完全一致。未映射的单元会被跳过并在导入统计中显示 `unit_not_mapped`。
教材版本调整时只改这个 JSON，不用改代码。

## 字段映射

| Model B | 系统字段 |
| --- | --- |
| `subject=art` | `Question.subject` |
| `grade` | `Question.grade` |
| `unit_id` | `Question.chapter`（经映射） |
| `knowledge_point` | `Question.knowledge_point` |
| `type` | `Question.type`（仅单选/判断） |
| `difficulty` 1~3 | `Question.difficulty` 1~3 |
| `stem` | `Question.stem`（经 `clean_stem`） |
| `options` | `QuestionOption` |
| `answer` | `Question.answer` |
| `analysis` | `Question.analysis` |
| `score` | 丢弃，按系统默认（单选 5、判断 2） |
| `scoringMode` | 固定 `auto` |
| `review_status` | 固定 `pending` |
| `source/created_by` | `Question.source_meta` + 审计日志 |
| `resources[role=question]` | 下载后存 `FileObject(question_image)` + `QuestionResource` |
| `resources[role=reference]` | 丢弃，不进入题干区 |
| `fact_ids/generated_by` | `Question.source_meta`（`factIds` / `generatedBy`） |

## 质量边界

- 官方评测只覆盖 JSON 合法率、字段/题型/知识点/难度一致率（20 题，100%），
  **不覆盖答案事实正确率**；
- 模型仍可能产生事实错误（画家、互补色等）；
- 图题依赖模型侧的图题库素材（约覆盖 86/211 个知识点），没有素材时只能出文字题；
- 所有生成题必须人工审核，禁止批量自动通过；
- 已知 SFT 数据中有 52+1 条坏题且本轮未重训，服务侧靠提示词与校验器拦截。

## 与现有功能的边界

| 不接入 | 原因 |
| --- | --- |
| `POST /grade` | 与 `Attempt/Score` 判分链路重复 |
| `GET /paper` | 分值、题型、总分与现有固定 100 分组卷规则冲突 |
| 多选/音乐题生成 | 模型不支持 |
| 自动审核通过 | 内容正确率未评测 |

详细冲突评估见桌面文档 `ModelB_美术出题模型_冲突与解决方案.md`。
