# 权重说明（不随 Git 上传）

部署需要以下两个目录，放到 `<仓库根>/weights/`：

| 目录 | 体积 | 说明 |
|---|---|---|
| `Qwen2.5-3B-Instruct/` | 5.8G | 基座模型，Qwen2.5-3B-Instruct 原始权重 |
| `qgen_lora_3b_v4/` | 309M | 出题 LoRA 适配器，必须 v4 |

说明：

- 必须使用 **v4** 适配器（训练最终版），不要指向 `qgen_lora_3b` 或 `v6*`。
- 以下目录是训练过程产物，交付不需要：`qgen_lora_3b_v3`、`qgen_lora_3b_v6`、`qgen_lora_3b_v6b`、`qgen_lora_3b_v6c`、`qgen_lora_3b_v6d`。
- 权重不入 Git（体积大），通过内部网盘/移动硬盘单独交接；部署时解压到上述位置即可。
- 目录名必须保持 `Qwen2.5-3B-Instruct` 和 `qgen_lora_3b_v4`，或用 `QGEN_MODEL`、`QGEN_ADAPTER` 指定实际路径。
