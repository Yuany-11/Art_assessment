# 音乐标签模型 v4（tempo 分支）

单文件权重 + 推理代码，可直接对 MP3/WAV/FLAC 等音频输出流派、情绪、调式、BPM，
并可选地按规则打一个参考分。

## 模型信息

| 项目 | 值 |
| --- | --- |
| 架构 | `ArtEvalNetV4`（v3 主干 + 起音自相关 tempo 分支），约 1.10 M 参数 |
| 权重 | `best_model.pt`（验证集综合分最高一轮，第 40 轮） |
| 训练数据 | FMA-medium 25,000 首 + MERGE 3,554 段 |
| 输入 | 30 秒音频窗口，log-mel 128 + chroma 12，3 段 TTA |
| 运行环境 | CPU 即可，Python 3.10，`torch >= 2.0` |

测试集（2,900 首，按 artist 分组切分，无泄漏）：

| 任务 | 指标 |
| --- | --- |
| genre（13 类） | top-1 63.3%，macro-F1 0.479 |
| emotion（calm/happy/sad/tense） | 准确率 68.6%，F1 0.683 |
| mode（大调/小调） | 准确率 76.0%，F1 0.754 |
| BPM | MAE 9.7（标签折叠在 70–180 BPM） |

## 安装依赖

```powershell
pip install torch numpy librosa soundfile
```

## 用法一：命令行打分

在解压目录下执行：

```powershell
python training/score.py "你的音频.mp3"
```

输出包含模型预测（流派/情绪/调式/BPM）、DSP 指标、规则评分和免责声明。
加 `--json out.json` 可把结果存成 JSON。

## 用法二：Python 调用

```python
from training.infer import Tagger

tagger = Tagger("best_model.pt")
result = tagger.predict_file("demo.mp3")

print(result["genre_top1"], result["genre_confidence"])
print(result["emotion_cn"], result["emotion_confidence"])
print(result["mode_cn"], result["mode_confidence"])
print(result["bpm"])
```

`result["genre"]` 是 13 类的完整概率字典，其余头也带 `*_probs`。

## 评分规则

`scoring/rubric.default.json` 是**数据不是权重**：维度权重、锚点、扣分项、等级区间
都写在里面，改完直接重跑，不需要重新训练。默认规则权重为
调性 0.3 / 节奏 0.2 / 音色 0.2 / 结构 0.2 / 可用性 0.1。

注意评分是**规则产出的参考分**，不是模型学出来的分数。

## 已知限制

- genre 13 类 63% 准确率，适合预筛和检索，不适合直接当最终分类；
  `Horror`、`Experimental` 等小类尤其弱。
- 训练数据以欧美独立音乐为主，中文流行、民乐、戏曲等未覆盖，会被强行映射到最近的类。
- BPM 有倍频歧义（80↔160、90↔180），典型误差约 ±10 BPM。
- emotion 只有四象限，测不出"怀旧""燃"这类细分情绪；有标注的样本仅 3,000 余首。
- 不输出调性主音、不做乐器/人声检测。
- 模型权重为研究用途训练所得，商用前请自行评估。
