# 模型B 出题服务 · 对接说明（2026-11-14）

服务定位：按目录生成题卡、按题库组卷、判分；**不写数据库**。后端拿到题卡后映射到 `qbank.Question`，状态置 `pending`，人工审核后转 `approved`。

## 一、分工

| 角色 | 负责 |
|---|---|
| 模型B侧 | 出题服务、接口与字段、图题库与配图 URL 规则、评测与验收材料 |
| 后端A | 调用 8002 服务、题卡入库、图片上传/媒体前缀配置、审核流转 |
| 前端 | 题卡渲染；题目配图只渲染 `role=question` 的资源 |
| 项目组 | 验收口径：答案唯一、图文对应、难度/题型符合目录 |

## 二、启动

```bash
cd <仓库根>/repo
uvicorn model_b_qgen.app:app --host 0.0.0.0 --port 8002
```

权重路径与 4bit 加载见同包 `README_部署.md`（也可用 `QGEN_MODEL` / `QGEN_ADAPTER` 指定）。最低建议：Python 3.10+、NVIDIA GPU 显存 ≥6GB、磁盘 ≥15GB（权重 6.1G + 依赖）。无 GPU 时设 `QGEN_LOAD_4BIT=0` 用 CPU 可跑，但单题明显变慢，不建议生产。

**调用约束**：

- 首次生成加载模型 1–2 分钟；后端放流量前先调 `/health`，`model_loaded=true` 再调用。
- 生成接口在服务内串行执行（有锁），后端不要并发打满；建议单题超时 ≥60 秒，批量 16 题 ≥180 秒。
- 后端与 8002 同机用 `127.0.0.1:8002`；后端若在 Docker 内，用 `host.docker.internal:8002` 或放进同一网络。
- 返回里的 `raw_output` 是模型原始输出，可忽略不存；`card.id` 只作展示/追溯，入库请用你们自己的主键。

## 三、接口

### GET /health

```json
{"status":"ok","model_loaded":false,"model_path":"...","adapter":"..."}
```

### GET /catalog

返回 1–9 年级目录：`grades.{1..9}.units[]`，每单元含 `unit_id`、`unit_name`、`knowledge_points`、`allowed_types`、`difficulty_range`。

### GET /paper

从待审题库组卷，秒级，不调用模型。参数：`grade`（必填）、`unit_id`、`difficulty`、`single_choice`、`true_false`、`fill_blank`、`short_answer`、`with_answer`。题型默认 5/5/4/2，可传 0 关闭；某题型不够时 `shortfalls` 会返回缺口数，`with_answer=false` 去掉 `answer` 与 `analysis`。

> 组卷只抽文字题库，**不产生图题**；图题走 `/generate` 或 `/generate_batch`。

### POST /grade

交卷判分。请求：

```json
{"items":[{"id":"<组卷返回的 card.id>","response":"B"}]}
```

选择传选项 key，判断传布尔值，填空传文本或数组；解答题返回 `needs_manual=true`，不计分。仅支持题库内题卡（组卷返回的题），实时生成的题入库后才能判分。注意：`/paper` 默认带答案，学生端务必传 `with_answer=false`；交卷后答案与解析由 `/grade` 返回。

### POST /generate

单题生成。请求：

```json
{"unit_id":"g4-u1","knowledge_point":"纯度初步","type":"single_choice",
 "difficulty":1,"with_image":true,"request_id":"backend-0001"}
```

### POST /generate_batch

一次生成多题（整卷推荐）。请求：

```json
{"requests":[
  {"unit_id":"g4-u1","knowledge_point":"纯度初步","type":"single_choice","difficulty":1,"with_image":true,"request_id":"p-01"},
  {"unit_id":"g4-u2","knowledge_point":"均衡","type":"short_answer","difficulty":2,"with_image":true,"request_id":"p-02"}
]}
```

返回：

```json
{"count":2,"ok":2,"items":[
  {"request":{...},"card":{...},"errors":[],"answer_errors":[],
   "resources":[{"type":"image","file":"teaching/10_value_gradient.png",
                 "name":"明度渐变","role":"question","url":"/resources/teaching/10_value_gradient.png"}],
   "ok":true,"needs_fact_review":false}
]}
```

### GET /image_coverage

返回有同题型图素材的 `[年级, unit_id, 知识点, 题型]` 列表。后端排卷时可据此决定哪些题适合出图题；测试页用它优先抽图题。

## 四、图题规则（重点）

- `with_image` 默认 `true`。传 `false` 一律出文字题。
- 图题来自图题库（218 道：原有 176 + 低年级 24 + 题型覆盖 18），不经过模型生成。
- **同题型约束**：该知识点没有同题型图素材时退回文字题，绝不串题型。
- 批量请求按「年级 × 题型」目标占比分配，最大余额法；单题请求命中素材即出图。
- 图题占比受素材限制：163 张可用图覆盖 86/211 个知识点。代表性 100 条请求实测图题约 10%；素材补足后可提升。
- `resources` 角色：
  - `role="question"`：题目配图，必须渲染；
  - `role="reference"`：知识点映射的教学参考图，不是题干配图，前端不要当题目图渲染。
- `url` 由 `file` 推导，前缀可用 `QGEN_RESOURCE_URL_BASE` 配成后端媒体地址（如 `/media/question_image`），并保证该地址可访问。
- 图片文件随包在 `data/12_image_assets/`（`images/` 名画、`teaching/` 示意图，共 198 个文件）。入库时按 `resources[].file` 同步到你们的媒体库，或直接把 8002 的 `/resources` 暴露给前端；`file` 是稳定标识，不要改名。
- `fact_ids` 是知识卡 ID（`data/09_qgen/knowledge/kb_v1.jsonl`），存字符串数组即可，不要求后端建表。

## 五、题卡字段（相对旧规范的增补）

沿用同包 `题卡字段规范_v1_参考.md`，新增/例外字段：

| 字段 | 说明 |
|---|---|
| `generated_by` | `model` / `template` / `image_bank`，来源标识 |
| `source` | 可能取值：`self_instruct`（模型生成）、`knowledge_template`（模板兜底）、`image_template`（图题库卡）。现有 `qbank.Question` 没有该字段，要溯源需后端新增，否则丢弃；不影响做题 |
| `resources` | 图题配图列表，`[{type,file,name,role,url}]`；文字题可能为空或仅 `reference` |
| `fact_ids` | 支撑该题的事实卡 ID，便于人工溯源 |
| `review_status` | 默认 `pending`，未审不得用于正式测评 |

选择题答案在 `answer.value`，必须命中 `options[].key`；填空题 `answer.values` 与题干空格数一致；判断题 `answer.value` 为布尔值。

单元与题库的对应：`unit_id`/`unit_name` 需映射到 `Course`（年级+美术）和 `Chapter`（单元名），对照见同包 `课程章节映射_美术1-9年级.csv`（36 个单元）。

## 六、联调检查清单

- [ ] `/health` 返回 `status=ok`，`adapter` 指向 v4。
- [ ] `/catalog` 年级、单元、知识点、题型与后端目录一致。
- [ ] 单题：4 个题型各出 1 道，`ok=true`，答案/解析非空。
- [ ] 图题：请求带 `with_image=true`，`resources` 出现 `role=question`，图片 URL 能打开。
- [ ] 文字题：不显示任何题目配图；`role=reference` 不在题干区渲染。
- [ ] 批量：10–16 题整套，题型数量符合请求，无重复题干。
- [ ] 入库：`resources` 存到题目资源表并保留 `role`；`source`/`fact_ids` 若新增字段则允许三种来源值，不加则丢弃。
- [ ] 判分：组卷题交卷后选择/判断/填空得分正确，解答题 `needs_manual=true`。
- [ ] 审核：新题 `review_status=pending`，人工通过前不进正式测评。

## 七、验收依据

- 100 条严格评测：100/100、结构错 0、扫描硬伤 0、重复 0、首轮 91%。
- 人工抽审：文字题 10/10 通过；图题 36 道抽看无图文错配、无答案不唯一。
- 单测 99 passed；复现命令见 GitHub 包 `data/09_qgen/eval/README.md`（固定 100 条与图题 36 条请求集）。
