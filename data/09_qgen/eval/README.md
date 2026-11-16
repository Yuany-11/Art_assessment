# 固定评测请求集

改代码或换权重后，用同一套请求复跑，结果才可比。

| 文件 | 内容 | 用途 |
|---|---|---|
| `requests_v6_100.jsonl` | 100 条文字题混合请求 | 文字题严格评测（2026-11-14 验收用这套） |
| `requests_image_36.jsonl` | 36 条图题请求（4 题型 × 9 年级） | 图题专项评测 |

在仓库根目录运行：

```bash
KMP_DUPLICATE_LIB_OK=TRUE python -m model_b_qgen.eval_runner \
  --requests data/09_qgen/eval/requests_v6_100.jsonl \
  --out logs/qgen_eval/rerun_100.json

KMP_DUPLICATE_LIB_OK=TRUE python -m model_b_qgen.eval_runner \
  --requests data/09_qgen/eval/requests_image_36.jsonl \
  --out logs/qgen_eval/rerun_image36.json
```

评测报告只统计结构、请求一致性与重复率；答案对错仍需人工抽审。
