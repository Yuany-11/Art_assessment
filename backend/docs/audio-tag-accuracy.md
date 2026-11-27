# 音频标签准确度：排查与回归（2026-11-16）

本条针对教师评分页「音频标签分析结果」（曲风/情绪/调式/BPM）的准确度，
与「音乐参考分偏低」是两条独立的链路。

## 1. 已完成

### 1.1 标签顺序自检

`arteval-v4/training/infer.py` 的 `GENRES` / `EMOTIONS` 与 checkpoint 内的
`genre_labels` / `emotion_labels` 已逐项核对，顺序一致（13 类曲风、4 类情绪）。
`service.py` 启动时新增自检：长度或顺序不一致直接报错，避免标签错位导致
“准确率突然变低”却继续静默输出。

### 1.2 长音频分段聚合

原逻辑只取音频**中间 30 秒**（`score_file` 的 `offset`），长作品的前奏/结尾
信息会丢失。现改为：

- 时长 ≤ 30 秒：单窗口；
- 时长 > 30 秒：取开头、中间、结尾各 30 秒，对曲风/情绪/调式概率取平均，
  BPM 取均值，并在结果中返回 `segments` 和 `segment_offsets`；
- 结果仍写入同一套 rubric，参考分计算口径不变。

### 1.3 低置信与估计值展示

- 教师端标签卡在任一置信度 < 0.4 时显示「不确定，建议人工判断」；
- BPM 标注「估计值」，避免把倍频歧义当成模型错误；
- 多窗口结果展示「N 段聚合」。

### 1.4 回归工具

[`tools/music_calibration/evaluate_tags.py`](../../tools/music_calibration/evaluate_tags.py)
对比「中间 30 秒」与「多段聚合」的曲风/情绪/BPM：

```bash
cd 终/tools/music_calibration
../../arteval-v4/.venv/Scripts/python.exe evaluate_tags.py \
  --samples tag_samples.csv --mode both --out tag_regression.json
```

CSV 列为 `id,path,genre,emotion,mode,bpm`，有标注的列才计算准确率/BPM MAE；
没有标注时只输出预测，**不能据此声称准确率**。

合成样例可直接复现：

```bash
cd 终/tools/music_calibration
../../arteval-v4/.venv/Scripts/python.exe make_synthetic_samples.py --out synthetic
../../arteval-v4/.venv/Scripts/python.exe evaluate_tags.py \
  --samples synthetic/synthetic_samples.csv --mode both --out synthetic/regression.json
```

## 2. 本次回归结果与限制

### 2.1 训练集指标（checkpoint 自带，作参考）

`metrics.json` 记录该 checkpoint 在测试集上的表现：

| 指标 | 测试集 |
| --- | --- |
| 曲风准确率 / F1 | 0.6326 / 0.4792 |
| 情绪准确率 / F1 | 0.6860 / 0.6830 |
| 调式准确率 / F1 | 0.7596 / 0.7543 |
| BPM MAE | 9.73 |

这是训练时的整体指标，不是本次改动的 before/after 对比。

### 2.2 合成样例回归（BPM/调式有精确真值）

`make_synthetic_samples.py` 生成 6 段 45 秒、节拍与大小调精确已知的音频，
用于验证分段聚合是否破坏 BPM/调式判断：

| 样例 | 真值 BPM | 真值调式 | 旧逻辑 BPM | 多段聚合 BPM | 片段数 |
| --- | --- | --- | --- | --- | --- |
| synth-060-major | 60 | 大调 | 117.7 | 118.7 | 3 |
| synth-090-minor | 90 | 小调 | 91.1 | 90.9 | 3 |
| synth-120-major | 120 | 大调 | 117.5 | 117.5 | 3 |
| synth-150-minor | 150 | 小调 | 151.7 | 151.7 | 3 |
| synth-075-major | 75 | 大调 | 78.7 | 78.6 | 3 |
| synth-110-minor | 110 | 小调 | 110.8 | 110.8 | 3 |

- 调式准确率：旧逻辑 **6/6**，多段聚合 **6/6**；
- BPM MAE：旧逻辑 **11.24**，多段聚合 **11.38**；
- 60 BPM 样例被判成约 118 BPM，是典型的倍频（double-time）歧义，也是
  BPM MAE 的主要来源；模型本身的 BPM 估计只应作为参考。

结论：分段聚合没有改善也没有明显破坏 BPM/调式结果；它主要解决长音频只
看中间 30 秒的信息缺失。合成样例不能代表真实音乐的曲风/情绪。

### 2.3 真实学生作品

现有 `tag_samples.csv` 的 6 份学生作品全部短于 30 秒，单窗口与多段聚合
结果相同（曲风/情绪/BPM 完全一致），只能证明改动未破坏现有结果：

| 样例 | 曲风 | 情绪 | BPM | 片段数 |
| --- | --- | --- | --- | --- |
| s52 | Experimental | sad | 123 | 1 |
| s44 | Experimental | tense | 130 | 1 |
| s33 | Experimental | tense | 120 | 1 |
| s42 | Experimental | sad | 119 | 1 |
| s41 | Hip-Hop | tense | 118 | 1 |
| s35 | Rock | tense | 108 | 1 |

这批样例没有曲风/情绪人工标签，因此不能计算真实音乐的准确率。要完成这部分
验收，需要把人工标签填入 `tag_samples.csv` 的 `genre/emotion/mode/bpm` 列
后重跑 `evaluate_tags.py`。

## 3. 已知限制

- 模型训练数据以欧美独立音乐为主，中文流行/民乐/戏曲会被映射到最近类别；
- 曲风 top-1 约 63%，只适合预筛和检索；
- BPM 存在倍频歧义，典型误差约 ±10 BPM；
- 情绪只有平静/欢快/悲伤/紧张四类；
- 若需要进一步提高准确率，应补充标注数据微调模型，而不是用规则硬编码
  冒充模型标签。
