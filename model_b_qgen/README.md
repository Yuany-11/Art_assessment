# Model B 美术出题服务

Qwen2.5-3B-Instruct + QLoRA 适配器，按目录、知识点、题型、难度生成题卡，输出前做字段与答案格式校验。

## 目录

```
model_b_qgen/
├── app.py            FastAPI 入口
├── runtime.py        模型加载与生成
├── prompting.py      提示词组装、JSON 解析
├── validator.py      题卡校验（与后端 qbank 规则对齐）
├── factcheck.py      答案级事实校验
├── fallback.py       模板兜底出题
├── image_bank.py     图题库直出
├── resources.py      配图映射与 URL
├── test_page.py      服务自带可视化测试页
├── eval_runner.py    离线评测
├── eval_monitor.py   评测进度页
├── prompts/          提示词模板（目录在 data/09_qgen/catalog_v2.json）
└── tests/            离线测试，不加载模型
```

## 环境

项目使用独立虚拟环境，不共用全局 Python：

```bash
cd <仓库根>
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r model_b_qgen/requirements.txt
```

依赖版本已锁定，`torch` 使用 CUDA 12.8 构建；服务器驱动需支持 CUDA 12.8（RTX 50 系需要）。无 GPU 时设 `QGEN_LOAD_4BIT=0` 走 CPU，能跑但很慢。

## 启动

模型和适配器默认放在项目根的 `weights/`，也可用环境变量指定：

```bash
export QGEN_MODEL=/path/to/Qwen2.5-3B-Instruct
export QGEN_ADAPTER=/path/to/qgen_lora_3b_v4
export QGEN_LOAD_4BIT=1
export QGEN_MAX_NEW_TOKENS=600

cd <仓库根>
.venv/Scripts/python.exe -m uvicorn model_b_qgen.app:app --host 0.0.0.0 --port 8002
```

**交付必须使用 `qgen_lora_3b_v4`**；适配器缺失时会退回基座模型，出题质量不达验收口径。

## 接口

启动后浏览器打开 `http://127.0.0.1:8002/docs` 可查看交互式接口文档（OpenAPI schema 在 `/openapi.json`）；`http://127.0.0.1:8002/` 是可视化测试页。

- `GET /health`：服务与模型加载状态
- `GET /catalog`：年级、单元、知识点、允许题型
- `POST /generate`：生成一道题

```bash
curl -X POST http://127.0.0.1:8002/generate \
  -H "Content-Type: application/json" \
  -d '{"unit_id":"g7-u2","knowledge_point":"冷暖色","type":"single_choice","difficulty":1}'
```

返回：

```json
{
  "ok": true,
  "request": {"unit_id": "g7-u2", "unit_name": "色彩基础", "grade": 7, "...": "..."},
  "raw_output": "...",
  "parse_ok": true,
  "card": {"id": "gen-...", "subject": "art", "stem": "...", "answer": {"value": "B"}, "...": "..."},
  "errors": []
}
```

`ok` 为 true 仅表示 JSON 可解析且通过字段/答案格式校验，不代表内容正确；入库前仍需人工审核。

## 测试

```bash
cd <仓库根>
python -m unittest discover -s model_b_qgen/tests -v
```

## 组卷接口（2026-11-10 新增）

`GET /paper` 从交付题库 `data/09_qgen/final/train_clean.jsonl` 抽题组卷，秒级返回，不调用模型。

参数：`grade`（1–9，必填）、`unit_id`（可选）、`difficulty`（可选）、`single_choice`/`true_false`/`fill_blank`/`short_answer`（各题型数量，默认 5/5/4/2）。
返回：`count`、`total_score`、`shortfalls`（某题型不够时的缺额）、`cards`。
题库路径可用环境变量 `QGEN_BANK` 覆盖。

注意：抽题只保证结构与格式，不保证内容；演示或入库前必须逐条人工复核。

## 学生答题与判分（2026-11-11 新增）

- 组卷加 `with_answer=0` 时，题卡不返回 `answer` / `analysis`，学生端拿不到答案。
- `POST /grade` 交卷判分，答案与解析只在判分响应里返回。
  ```
  {"items": [{"id": "题卡 id", "response": "A"}, {"id": "...", "response": true}, {"id": "...", "response": ["红","黄","蓝"]}]}
  ```
  响应含 `earned_score`、`total_score`、`items[].correct`、`items[].answer`、`items[].analysis`。
- 选择、判断、填空自动判分；解答题不自动给分，`needs_manual=true`，留待教师评分。

## 配图与资源（2026-11-14 新增）

`POST /generate` 与 `POST /generate_batch` 的每条记录带 `resources` 字段，格式与
`data/09_qgen/image_questions/img_questions.jsonl` 一致，返回时由后端补 `url`：

```json
"resources": [
  {"type": "image", "file": "images/53577.jpg", "name": "Landscape Painting …",
   "role": "reference", "url": "/resources/images/53577.jpg"}
]
```

- 映射来源：`data/09_qgen/image_questions/mapping_20261114.json` 的 `map` 段，键为 `"unit_id||knowledge_point"`，一个知识点 8 张图。
- `file` 原样保留（入库、留档、换 URL 都靠它），`url` 只由 `file` 推导，规则是 `QGEN_RESOURCE_URL_BASE + "/" + file`。
- 映射表里没有的知识点返回 `[]`，不会凭空生成图片地址。
- 映射图 `role="reference"`（教学参考图），图题库卡的配图 `role="question"`（题目配图）；前端只渲染 `question`。

本地开发（默认值，无需配环境变量）：

| 环境变量 | 默认值 | 作用 |
|---|---|---|
| `QGEN_RESOURCE_MAP` | `data/09_qgen/image_questions/mapping_20261114.json` | 映射表路径 |
| `QGEN_IMAGE_ROOT` | `data/12_image_assets` | 静态目录根，挂在 `/resources` |
| `QGEN_RESOURCE_URL_BASE` | `/resources` | 图片 URL 前缀 |

```bash
cd <仓库根>
.venv/Scripts/python.exe -m uvicorn model_b_qgen.app:app --host 127.0.0.1 --port 8002
# 浏览器直接打开 http://127.0.0.1:8002/resources/images/437428.jpg
```

> Git Bash 下不要用 `export QGEN_RESOURCE_URL_BASE=/resources`，MSYS 会把 `/resources`
> 转成 `D:/…/Git/resources`；要么不设（用默认值），要么加 `export MSYS_NO_PATHCONV=1`。

## 图题直出（2026-11-14）

- `POST /generate` / `generate_batch` 默认 `with_image=true`，先查图题库（218 道：176 原有 + 24 低年级 + 18 题型覆盖）；命中则直接返回图题卡，不经过模型。
- 同题型约束：该知识点没有同题型图题时退回文字题，绝不串成别的题型。
- 批量接口按「年级 × 题型」目标占比（单选 0.30–0.50、判断 0.25–0.45、填空 0.10–0.25、解答 0.15–0.30，随学段递减）用最大余额法分配；传 `with_image=false` 的请求不参与。
- **实际占比受素材限制**：163 张可用配图只覆盖 86/211 个知识点；按代表性 100 条请求实测，仅 17 条有同题型图素材，混合输出中图题约 10%，低于目标区间。按决策不硬凑，后续补素材再提升占比。
- 资源角色：卡自带配图 `role="question"`；来自知识点映射的图 `role="reference"`（教学参考图，非题干配图），前端只渲染 `question`。

生产对接（前端 5173、后端 8000）：把 `QGEN_RESOURCE_URL_BASE` 设成后端媒体前缀
（如 `/media/question_image`），`url` 自动变成 `/media/question_image/images/xxx.jpg`；
图片按现有 176 道图题同样方式走 `/files` 上传拿到 fileId/URL，映射表里仍存 `file`，
**不改前端资源类型**。前端 5173 直接引用 8000 的媒体地址时，后端需开媒体目录静态服务并放行跨域。
