# 2026-10-29 归档：未采用的实验产物

这些文件从 `model_b/` 主目录移出，**没有删除**，仅作为留痕。最终交付不使用它们。

| 文件 | 原用途 | 为什么归档 |
|---|---|---|
| `test_ui_compare.html` | `/compare` 新旧页面并排 | 左右两个 iframe 指向同一进程、同一模型，分数完全相同，容易误读成“两个模型对比” |
| `calibration_student.json` | 学生域校准表实验 | 未接入最终链路，`calibration_v32.json` 才是正式校准 |
| `pairwise_vote.py` / `pairwise_template.html` | 教师成对投票实验页 | 没跑完、无有效投票数据，不进入交付 |
| `app_exp.py` | 监测页实验版本 | 主监测用 `monitor.py` 与 `start_monitor.bat` |
| `启动模型B新旧对比.bat` | 打开 /compare 并排页 | compare 页已归档，脚本随之失效 |

如需恢复，直接移回 `model_b/` 对应位置即可。
