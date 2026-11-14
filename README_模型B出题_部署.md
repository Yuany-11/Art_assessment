# 艺术素质测评系统 + 模型B出题服务 · 部署说明

本说明对应项目仓库（不含权重）。拉取后目录结构如下：

```
<仓库根>/
  backend/              # Django 后端
  src/                  # Vue 3 前端
  model_b_qgen/         # 模型B出题服务源码
  data/                 # 运行时数据（目录、知识卡、题库、图题库、配图）
  scripts/              # 评测/质量扫描脚本（可选，依赖同目录 validate_questions.py）
  weights/              # 权重占位，部署时按 README_权重说明.md 放入
```

## 一、整体结构

- `backend/`：Django 后端（MySQL + Redis + MinIO），接口契约见 `docs/api*.md`。
- `src/`：Vue 3 前端，默认 Mock 数据，接真实后端需 `.env.local`。
- `model_b_qgen/`：模型B出题服务（FastAPI，端口 8002），后端通过 HTTP 调用。
- `data/09_qgen`：目录 `catalog_v2.json`、知识卡 `knowledge/kb_v1.jsonl`、待审题库 `final/train_clean.jsonl`、图题库 `image_questions/`、演示卷 `demo/`。
- `data/12_image_assets`：静态配图（`images/` 名画、`teaching/` 示意图），由服务挂载到 `/resources`。

## 二、准备权重

```text
<仓库根>/weights/
  Qwen2.5-3B-Instruct/      # 5.8G，基座模型
  qgen_lora_3b_v4/          # 309M，必须 v4 适配器
```

也可用环境变量指定：

```bash
export QGEN_MODEL=/path/to/Qwen2.5-3B-Instruct
export QGEN_ADAPTER=/path/to/qgen_lora_3b_v4
```

## 三、启动主系统（后端 + 前端）

```bash
cd <仓库根>
cp .env.example .env          # 修改数据库、JWT、MinIO、端口；正式部署必须把 DJANGO_SECRET_KEY、JWT_SECRET 和默认密码换成随机值
docker compose up -d --build  # MySQL / Redis / MinIO / 后端 / Nginx
```

前端本地开发：

```bash
pnpm install
cp .env.example .env.local    # 设置 VITE_API_BASE_URL、VITE_USE_MOCK=false
pnpm dev
```

## 四、启动模型B出题服务

Python 3.10+，建议独立虚拟环境：

```bash
cd <仓库根>
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r model_b_qgen/requirements.txt
uvicorn model_b_qgen.app:app --host 0.0.0.0 --port 8002
```

Windows 下如遇 `OMP: Error #15`（libiomp5md 冲突），启动前设置：

```bash
set KMP_DUPLICATE_LIB_OK=TRUE   # PowerShell: $env:KMP_DUPLICATE_LIB_OK="TRUE"
```

权重是 4bit 加载（默认 `QGEN_LOAD_4BIT=1`），显存不足时保留默认；可选环境变量：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `QGEN_MODEL` | `<根>/weights/Qwen2.5-3B-Instruct` | 基座模型路径 |
| `QGEN_ADAPTER` | `<根>/weights/qgen_lora_3b_v4` | LoRA 适配器 |
| `QGEN_LOAD_4BIT` | `1` | 4bit 量化加载 |
| `QGEN_MAX_NEW_TOKENS` | `600` | 单题最大生成长度 |
| `QGEN_IMAGE_ROOT` | `<根>/data/12_image_assets` | 配图静态目录 |
| `QGEN_RESOURCE_URL_BASE` | `/resources` | 返回给前端的图片 URL 前缀 |
| `QGEN_BANK` | `<根>/data/09_qgen/final/train_clean.jsonl` | 组卷/判分题库 |
| `QGEN_DEMO` | `<根>/data/09_qgen/demo/fixed_demo_grade3.json` | 固定演示卷 |

> 注意：代码按「仓库根/model_b_qgen」与「仓库根/data」的相对位置找数据，请保持仓库目录结构，不要单独挪动 `model_b_qgen` 或 `data`。

## 五、验证

```bash
curl http://127.0.0.1:8002/health
curl http://127.0.0.1:8002/catalog
curl "http://127.0.0.1:8002/paper?grade=4&single_choice=5&true_false=5&fill_blank=4&short_answer=2"
```

单题出题：

```bash
curl -X POST http://127.0.0.1:8002/generate -H "Content-Type: application/json" \
  -d '{"unit_id":"g4-u1","knowledge_point":"纯度初步","type":"single_choice","difficulty":1,"with_image":true}'
```

接口与字段说明见 `model_b_qgen/README.md`；完整对接说明另行发送给后端与前端。

## 六、注意事项

- 权重、`.venv`、`__pycache__`、依赖目录不要提交 Git（`.gitignore` 已配置）。
- 图题素材来自公开名画与自制示意图，随仓库分发；新增素材请同步 `data/09_qgen/image_questions/mapping_20261114.json`。
- 生成题卡状态均为 `pending`，入库后必须人工审核再用于正式测评。
