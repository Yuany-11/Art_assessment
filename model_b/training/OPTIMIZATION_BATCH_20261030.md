# 2026-10-30 模型优化批次

## 目标

在不影响 8010 当前服务的前提下，比较 3 个候选方案，回答两个问题：

1. APDDv2 测试 MAE 能不能从 **7.21** 再降 0.15 以上？
2. 成人 > 儿童、同图稳定性、档位命中能不能变好？

## 红线

- 当前模型备份：`weights/backup_current_20261029_v3.0_pencils_v31/`
- 不覆盖 `weights/apddv2_ft`、`weights/pencils_creativity`、`calibration_v31.json`
- 不改 `app.py`，不切 8010
- 不改等级线 90/75/60
- 不动 `data/03_scoring` 伪标签、`data/02_quality`、APDDv2 原始标签
- 所有实验用独立目录和独立端口 8011
- 固定 split seed=42，只改模型初始化 / DataLoader seed；测试集必须仍是同一批 1923 张

## 基线

| 指标 | 当前 |
|---|---:|
| APDDv2 test MAE | 7.21 |
| 成人 > 儿童 | 0.801 |
| APDD > 儿童 | 0.741 |
| 同图扰动稳定性 | 0.469 |
| 五档命中 | 0.246 |
| 单张 1001 总分 | 65.8 |

## 实验顺序

| 顺序 | 实验 | 目的 | 预计耗时 | 是否必做 |
|---|---|---|---:|---|
| E0 | 评估脚手架 | 固定测试集、保存逐图预测、paired bootstrap | 1 h | 必做 |
| E1 | 3-seed ResNet18 集成 | 最稳的 MAE 提升 | 90 min | 必做 |
| E2 | 3-seed + 多裁/多尺度 TTA | 看稳定性与排序是否再加分 | 30 min | 必做 |
| E3 | 冻结主干 + 序数/CORAL 头 | 档位命中，不改主干 | 30 min | 必做 |
| E4 | 320px 单模型 | 看分辨率是否值得 | 60-75 min | 看时间 |
| E5 | 创意校准 A/B | 修 p75/p95 重复导致的压缩 | 30 min | 看时间 |
| E6 | KidsArtBench 映射/评测 | 真正学生域，需图片授权 | 1-2 h | 图片到了再做 |

## E0：评估脚手架

新建，不改现有训练脚本：

- `training/exp_train_seed.py`：复制 `train_apddv2_finetune.py`，增加 `--seed`、`--out`、`--tag`；固定 split seed=42
- `training/exp_eval_ensemble.py`：读多个 checkpoint，平均 raw 四维，再校准；输出逐图预测
- `training/exp_ordinal_head.py`：冻结 v3.0 主干，只训四维 ordinal/CORAL 头

每个实验保存：

```text
weights/exp_<name>/best.pt
weights/exp_<name>/head.npz
logs/exp_<name>/history.json
logs/exp_<name>/test_metrics.json
logs/exp_<name>/preds_test.csv
logs/exp_<name>/config.json
```

`preds_test.csv` 至少包含：`file, dim, raw, cal, label`。后面 ensemble / TTA / bootstrap 都复用，不重复推理。

验收：

- 同一 test split，1923 张
- paired bootstrap 1000 次
- MAE 降低 ≥0.15 且 95% CI 不跨 0，才算有效
- 或档位命中 +2pp 且 MAE 不明显变差

## E1：3-seed 集成

做法：

- 3 个 seed（1/2/3），同一 split、同一超参、同一 epoch/早停
- 每个 seed 单独训四维模型
- 每个 seed 用 `train_creativity_pencils.py` 重训创意头：

```bash
ART_WEIGHT=weights/exp_seed1/apddv2_ft/best.pt \
ART_OUT_WEIGHTS=weights/exp_seed1/pencils_creativity \
ART_OUT_LOGS=logs/exp_seed1/pencils_creativity \
python training/train_creativity_pencils.py --yes
```

- 推理时对 3 个模型的 raw 四维取平均，再走 v3.1 校准
- 版本名示例：`ensemble3+calib-v31`

预计：MAE 6.9-7.1，成人>儿童 +1-2pp；推理约 3 倍。

## E2：多裁/多尺度 TTA

在 E1 的 3 个模型上做：

- 原图
- 水平翻转
- 中心裁 6%
- 四角裁 4 个（或 2 个对角）
- 可选尺度 0.9 / 1.0 / 1.1

先只评估，不改 8010。看：

- APDDv2 MAE
- 成人>儿童
- 同图扰动稳定性
- 单张推理时间（必须 < 2 s，API 超时 10 s）

预计：MAE 再降 0.05-0.15，稳定性明显改善；若 MAE 不降但稳定性 ≥15%，可作为“稳定版”候选。

## E3：序数/CORAL 头

冻结 v3.0 主干，只训四维 ordinal 头：

- 输入：主干 pooled feature
- 输出：每维 5 个档位（或 CORAL 4 个阈值）
- loss：ordinal/CORAL + 少量回归辅助
- 创意头不动

预计：MAE 持平或 +0.1，档位命中 +2-5pp。适合“等级更准”，不适合替代总分。

## E4：320px（看时间）

```bash
ART_WEIGHTS=weights/exp_320 ART_LOGS=logs/exp_320 \
python training/train_apddv2_finetune.py --img 320 --yes
```

注意：

- 需要给创意头也改用 320 输入，否则特征尺度不匹配
- 推理时间约 2 倍
- 只有 E1/E2 收益 <0.15 时才值得做

预计：MAE 再降 0.1-0.3，不保证。

## E5：创意校准 A/B

现状：`calibration_v31.json` 的创意 `p75=p95=100`，高分段被压到约 77-82，目标 93 没达到。

只做离线 A/B，不默认切换：

- 当前 v3.1 校准
- 儿童分布单独校准（p05/p25/p50/p75/p95 = 14.95/36.95/49.45/62.02/81.1 → 40/62/72/82/93）
- 看 Pencils 创意 MAE、Pearson、分数分布

注意：这是显示口径，不是模型精度；会明显改分数，需产品确认。

## E6：KidsArtBench

本地只有 CSV/grade.xlsx，没有图片。需要按数据使用协议拿图。

拿到后：

1. 先评测现有模型在 101 张 test 上的 9 维映射表现
2. 再决定是否多任务微调
3. 9 维到四维的映射只当辅助/弱标签，不冒充官方四维

## 决策规则

- E1 有效、E2 再加分：采用 `ensemble3 + TTA + v3.1`，切 8011 试跑
- E1 有效、E2 只稳不降 MAE：采用 `ensemble3`，TTA 作为可选稳定模式
- E1 无效（MAE 降 <0.15 或 CI 跨 0）：停，不堆 seed；转 E4 320px
- E3 档位 +2pp 但 MAE 变差：只作为“等级头”候选，不替换总分
- 所有方案都不如基线：保留当前模型，不切 8010

## 明天结束要交的东西

- 一张对比表：baseline / ensemble3 / ensemble3+TTA / ordinal / 320
- 每个方案的 MAE、成人>儿童、稳定性、档位命中、推理时间
- 是否建议切换 8010 的明确结论
- 新权重和回滚路径
