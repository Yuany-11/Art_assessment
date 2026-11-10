# Model B 美术出题服务

Qwen2.5-3B-Instruct + QLoRA 适配器，按目录、知识点、题型、难度生成题卡，输出前做字段与答案格式校验。

## 目录

```
model_b_qgen/
├── app.py            FastAPI 入口
├── runtime.py        模型加载与生成
├── prompting.py      提示词组装、JSON 解析
├── validator.py      题卡校验（与后端 qbank 规则对齐）
├── catalog.json      小学一年级至初中三年级单元与知识点目录
├── prompts/          system.txt / user_template.txt
└── tests/            离线测试，不加载模型
```

## 环境

项目使用独立虚拟环境，不共用全局 Python：

```bash
cd E:/Lab_Files/Project/Art_assessment_v2
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r repo/model_b_qgen/requirements.txt
```

依赖版本已锁定，`torch` 使用 CUDA 12.8 构建（RTX 50 系显卡需要）。

## 启动

模型和适配器默认放在项目根的 `weights/`，也可用环境变量指定：

```bash
export QGEN_MODEL=/path/to/Qwen2.5-3B-Instruct
export QGEN_ADAPTER=/path/to/qgen_lora_3b
export QGEN_LOAD_4BIT=1
export QGEN_MAX_NEW_TOKENS=600

cd repo
../.venv/Scripts/python.exe -m uvicorn model_b_qgen.app:app --host 0.0.0.0 --port 8002
```

适配器目录不存在时使用基座模型出题。

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
cd repo
python -m unittest discover -s model_b_qgen/tests -v
```

## 组卷接口（2026-11-10 新增）

`GET /paper` 从交付题库 `02_data/train_clean_2698.jsonl` 抽题组卷，秒级返回，不调用模型。

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
