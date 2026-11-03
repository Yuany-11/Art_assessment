# 音乐标签模型：数据准备、训练与推理

本目录包含一条完整可复现的训练链路：

```text
下载开放数据 -> 特征缓存 + 伪标签 -> 训练四头模型 -> 评估 / 打分
download_datasets.py   label_dataset.py   train.py        score.py
```

模型仍然输出平台现有的四类结果，标签严格对应模型输出：

| 输出 | 类别 / 范围 | 标签来源 |
| --- | --- | --- |
| genre | 13 类（Blues … World） | FMA `genre_top` + 标签关键词 / Jamendo genre 标签 |
| emotion | calm / happy / sad / tense | MERGE 的效价/唤醒评分；Jamendo / ManyMusic mood 标签投影到 Russell 四象限；FMA mood 标签 |
| mode | major / minor | Krumhansl-Schmuckler 调性估计（带置信度） |
| bpm | 实数（70–180 折叠） | librosa 节拍跟踪 + 自相关置信度 |

所有标签都带置信度或软分布；低置信度的 mode/BPM 会被 mask 掉，不参与损失。
训练/验证/测试按 **artist** 分组切分，避免同一作者跨集合泄漏。

---

## 0. 环境

本机已建好虚拟环境 `D:\Art_assessment\.venv`（Python 3.10），依赖全部装在里面，
系统 Python 未改动。已安装并验证：

```text
torch 2.11.0+cu128   cuda available: True   GPU: NVIDIA GeForce RTX 3080 (sm_86)
numpy 2.2.6   pandas 2.3.3   scikit-learn 1.7.2   librosa 0.11.0   soundfile 0.14.0
```

使用前先激活（或直接调用解释器）：

```powershell
.venv\Scripts\Activate.ps1
# 或者不激活：
.venv\Scripts\python.exe training/train.py --help
```

注意本机 `python` 可能指向 Microsoft Store 的占位程序，激活虚拟环境后
`python` 才会指向 `.venv`。

需要重装时：

```powershell
py -3.10 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install torch --index-url https://download.pytorch.org/whl/cu128
python -m pip install -r requirements-train.txt
```

> 本机 Windows 系统代理 `127.0.0.1:7897` 会被 requests 误判成 HTTPS 代理，导致
> pip 报 `check_hostname requires server_hostname`。已在 `.venv\pip.ini` 中显式
> 声明为 HTTP 代理；如果代理端口变了，同步改这个文件即可。

---

## 1. 下载约 32 GB 数据

```powershell
python training/download_datasets.py --root data --target-gb 32 --remove-archives
```

如果磁盘充足（> 80 GB）且希望保留压缩包以便续传，可以去掉 `--remove-archives`。

默认组成：

* **FMA-medium**：25,000 条 30 秒 CC 音频，约 23.8 GB；
* **MTG-Jamendo mood/theme**：低码率整曲，脚本按目标大小下载约 15–17 个
  shard（约 3,000 首、8 GB），带 59 个情绪/主题标签和 94 个流派标签。

磁盘空间要按“压缩包 + 解压音频 + 特征缓存”估算：完整流程峰值约 70 GB，
最稳妥是预留 80 GB。加 `--remove-archives` 在解压后删除压缩包，可把峰值降到
约 50 GB、最终占用约 42 GB；代价是中断后需要重新下载对应压缩包。
`--min-free-gb` 默认 60，磁盘更小时可显式调低，但要自行承担中途写满的风险。

其他常用参数：

```powershell
# 只下 FMA
python training/download_datasets.py --root data --no-jamendo

# 指定 Jamendo 分片数（每个约 500 MB）
python training/download_datasets.py --root data --jamendo-shards 8

# 磁盘紧张时降低总量
python training/download_datasets.py --root data --target-gb 16
```

完成后会生成 `data/download_report.json`。下载是断点续传的，重跑会跳过已完成文件。

### 1.1 情绪数据补充（重要）

FMA 只有极少数曲目带 mood 标签，仅有 FMA 时 emotion 头几乎是空的。当前工作区
额外补了两份情绪语料，`label_dataset.py` 会自动识别并一起打标签：

| 数据集 | 内容 | 许可 | 本地路径 |
| --- | --- | --- | --- |
| MERGE（Louro et al., 2024） | 3,554 段 30 秒 AllMusic 片段，逐曲 arousal/valence 评分 + Russell 四象限 | CC BY-NC 4.0 | `data/merge/` + `data/merge_meta/` |
| ManyMusic-Stim（2025） | 2,559 首 Jamendo 曲目（与 MTG-Jamendo mood/theme 标签同词表） | 逐曲 CC | `data/manymusic/` + `data/manymusic_meta/` |

MERGE（约 1.2 GB，比 ManyMusic 小得多，优先下）：

```powershell
curl.exe -L --noproxy "*" -C - -o data/raw/MERGE_Audio_Complete.zip `
  "https://zenodo.org/api/records/13939205/files/MERGE_Audio_Complete.zip/content"
# 解压到 data/merge（zip 内是 MERGE_Audio_Complete/Q1..Q4/<song>.mp3）
```

ManyMusic（约 30.4 GB）：

```powershell
curl.exe -L --noproxy "*" -C - -o data/raw/manymusic.zip `
  "https://zenodo.org/api/records/17425915/files/manymusic-stim-zenodo.zip/content"
```

情绪映射规则（`training/labels/taxonomy.json`）：

* MERGE 的 (arousal, valence) 直接投影到四象限中心，权重 0.85；
* MERGE 的 AllMusic 流派标签经 `merge_genre` 映射到 13 个风格类；
* ManyMusic / Jamendo 的 `mood/theme---*` 标签经 `mood_tags` 锚点投影；
* 没有情绪标注的曲目 emotion 被 mask，不影响其他三个头。

> 当前工作区里已经存在 `data/fma_metadata/`（FMA 元数据），脚本会自动跳过
> 元数据下载；FMA 音频已经下齐（25,000 首），Jamendo 官方源在当前网络下不可达。

---

## 2. 生成特征缓存与标签

```powershell
python training/label_dataset.py --root data --workers 8 --license-policy research
```

输出：

```text
training/data/manifest.jsonl        每首歌一行：路径、split、标签、置信度、许可证
training/data/cache/*.npz           float16 的 log-mel(128) + chroma(12)
training/data/manifest_stats.json   类别/切分/许可证覆盖统计
training/data/label_report.json     本次运行统计
```

这一步会把音频解码成模型实际使用的特征，并计算 DSP 伪标签，通常是整条链路里
最耗时的一步（28k 首、8 进程大约需要数小时）。脚本支持断点续跑：已经写入
manifest 且缓存存在的条目会跳过。

先快速验证流程（只处理 500 首）：

```powershell
python training/label_dataset.py --root data --workers 4 --limit 500
```

注意：

* 默认 `--license-policy research`，保留 CC BY-NC 等仅限研究/评估的音频；
* `--license-policy commercial` 只保留允许商用的曲目，数量会大幅缩水
  （FMA 约 3,000 首）， **无法凑满 32 GB**；
* Jamendo 的元数据是 CC BY-NC-SA，音频逐曲单独授权，默认只用于研究；
* 正式商用前必须逐曲复核 `manifest.jsonl` 里的 `license` 字段。

---

## 3. 启动训练

GPU（本机 RTX 3080 10 GB，推荐）：

```powershell
python training/train.py --manifest training/data/manifest.jsonl `
  --device cuda --epochs 80 --batch-size 64 --workers 8
```

默认使用 v3 主干（见下文“主要优化项”）。本机实测（v2、12 秒裁剪、AMP）：

| batch | 速度 | 峰值显存 |
| --- | --- | --- |
| 32 | 567 samples/s | 2.3 GB |
| 64 | 580 samples/s | 4.6 GB |
| 96 | 601 samples/s | 6.9 GB |
| 128 | 42 samples/s（溢出到共享显存） | 9.0 GB |

所以 64 或 96 最合适，**不要超过 96**：3080 只有 10 GB，且显示器还要占用一部分，
128 开始会触发显存换页，速度掉一个数量级。2.5 万首时每个 epoch 约 45 秒。

v3 与 v2 速度基本一致（batch 64：562 vs 573 samples/s，batch 96：两者均约 584
samples/s），显存占用相当，因此把 batch 继续保持在 64–96 即可。

训练脚本在 CUDA 上会自动开启：AMP（fp16）、TF32、cuDNN benchmark、
`pin_memory` + 持久化 worker。`--device auto`（默认）检测到 GPU 就会用 GPU。

CPU：

```powershell
python training/train.py --manifest training/data/manifest.jsonl --device cpu --workers 4 --epochs 60 --batch-size 32
```

脚本会持续打印每个 epoch 的 genre/emotion/mode 准确率、macro-F1、BPM MAE 和综合分。

显存不足时依次尝试：

```powershell
--batch-size 32
--crop-seconds 10
--arch v1
```

### 从旧检查点热启动

旧模型（v1/v2）的权重可以部分加载到 v3（分支卷积层全部可复用，池化/分类头因
形状不同被跳过）；形状不匹配的张量会被跳过：

```powershell
python training/train.py --manifest training/data/manifest.jsonl --device cuda `
  --init-weights training/runs/20261026-120656/best_model.pt
```

也可以写 `--init-weights latest` 自动选择最新的 `best_model.pt`。

### 断点续训

```powershell
python training/train.py --manifest training/data/manifest.jsonl --device cuda `
  --out-dir training/runs/20261027-120000 --resume latest
```

同一条命令重复执行会从该目录的 `last_model.pt` 继续；`--epochs` 可以调大以延长训练。

### 主要优化项

* 默认 v3 主干（约 1.1 M 参数，仍可 CPU 推理）：
  - 注意力统计池化：可学习的时序注意力加权均值 + 加权标准差 + 全局最大值，
    替代 v2 的简单平均/最大池化，能突出副歌、间奏等关键片段；
  - 残差块内加入 stochastic depth（drop-path，逐样本随机丢弃整个残差分支），
    对小样本的情绪/调式标签有正则作用；
  - 分类头改成共享全连接 + 残差细化层（两层等效深度），提升四任务的共享表示；
  - BPM 头改为 64 个 bin 的 soft-argmax 回归（期望值作为输出），对半拍/双拍
    歧义更鲁棒，输出仍是归一化标量，训练/推理接口不变；
  - `--arch v2` / `--arch v1` 仍可选用，检查点里自带 arch 字段，旧权重复用不受影响；
* v2 主干：残差块 + squeeze-and-excitation、平均/最大双池化、dropout；
  约 0.8 M 参数，仍可 CPU 推理；
* 软标签交叉熵（genre/emotion）、label smoothing；
* SpecAugment、mixup、随机时间裁剪；
* 按 genre/emotion 逆频率加权的采样器（`--sampler sqrt|inverse|none`）；
* AdamW + 线性 warmup + cosine 退火、梯度裁剪；
* CUDA 混合精度（`--no-amp` 关闭）、EMA 权重、早停；
* 按 artist 分组的 train/val/test，避免数据泄漏。

### BPM 头失效与 `--arch v4`（重要）

历史训练里 `bpm_mae` 一直卡在 20 左右。诊断结论**不是过拟合，也不是标签噪声**：

| 检查（val 600 首） | 结果 |
| --- | --- |
| 常数预测（全给训练均值 119.1）的 MAE | 21.4 |
| 模型实际 MAE / 预测与标签相关系数 | 21.3 / **0.08**（train 上也只有 0.19）→ 头没在学 |
| 标签落在 mel 能量自相关最强峰上的比例 | **76.6%**（top-2 93.2%）→ 标签本身可靠 |
| 只用自相关峰、限制在 70–180 BPM 估计的 MAE | **9.6**（零训练） |

根因是**时间轴混叠**：`_ResBlock` 每个都做 2 倍时间池化，mel 分支 4 个块后
帧率 43.07 / 16 ≈ **2.7 fps**，Nyquist 上限只有 **81 BPM**。80 BPM 以上的节拍
在进入池化之前就已经被抽没了，BPM 头无论如何只能输出均值。

`--arch v4` = v3 + `_TempoBranch`：在**原始分辨率**的 mel 上算起音自相关，
在 55–200 BPM 的 64 个对数格点上采样，拼进 BPM 头的输入。分支无参数、
用 FFT 实现，显存和速度几乎不变（1.10 M vs 1.10 M 参数）。

```powershell
.venv\Scripts\python.exe training/train.py --manifest training/data/manifest.jsonl `
  --device cuda --epochs 80 --batch-size 64 --workers 8 --arch v4 `
  --init-weights training/runs/<旧v3运行>/best_model.pt `
  --loss-balance uncertainty --label-smoothing 0.08 `
  --stretch-prob 0.25 --roll-prob 0.30 --noise-prob 0.35 --noise-std 0.03 `
  --n-time-masks 3 --patience 12 --early-stop-min-delta 5e-4
```

v3 的权重可以热启动到 v4（只有 `bpm_trunk` 形状不同会被跳过）。训练时盯
日志的 `bpm` 列：正常情况下 5 个 epoch 内就应该从 20 掉到 10 左右。

### 过拟合 / 任务不平衡：新增开关

训练日志里 train/val 差距大、emotion 接近随机、bpm 掉不动时，用下面这组开关：

```powershell
.venv\Scripts\python.exe training/train.py --manifest training/data/manifest.jsonl `
  --device cuda --epochs 80 --batch-size 64 --workers 8 `
  --loss-balance uncertainty `
  --label-smoothing 0.08 `
  --stretch-prob 0.25 --roll-prob 0.30 --noise-prob 0.35 --noise-std 0.03 `
  --n-freq-masks 2 --n-time-masks 3 `
  --patience 12 --early-stop-min-delta 5e-4
```

| 开关 | 作用 |
| --- | --- |
| `--loss-balance uncertainty` | Kendall 不确定性加权，每个任务学一个 `log σ²`，`L = Σ exp(-s)L_i + s`；不再需要手调 `--loss-*` |
| `--loss-balance dwa` | 按各任务 loss 的下降速度动态加权（`r = L(t-1)/L(t-2)`），无新增参数 |
| `--stretch-prob` | 特征域变速（0.9–1.1 倍），**BPM 标签同步缩放**，是 BPM 头唯一的有效增广 |
| `--roll-prob` | 时间轴循环平移，模拟从不同位置切 12 秒 |
| `--noise-prob/--noise-std` | 标准化之后加高斯噪声（默认 0.3 / 0.02） |
| `--n-freq-masks/--n-time-masks` | SpecAugment 掩码条数（默认 2/2） |
| `--early-stop-min-delta` | combined score 提升小于该值视为没提升，避免早停在噪声波动上 |

两点注意：

* **增益增强无效**：`normalize_features` 做逐样本标准化，乘音量增益会被完全抵消，
  所以 `training/augment.py` 不提供 gain 增广；要模拟录音电平差异只能改动态范围。
* **验证 loss 始终用固定权重**，与训练态的动态权重解耦，早停看的是
  `combined score`，不是训练 loss。`metrics.json` 的 `history[*].task_weights`
  记录了每轮实际生效的权重。

### 产物

```text
training/runs/<run_id>/
  best_model.pt     验证集综合分最好的权重（含标签、BPM 均值/方差、配置）
  last_model.pt     最新权重 + 优化器 + 调度器 + EMA，用于续训
  config.json       本次超参数
  labels.json       类别顺序与中文名
  metrics.json      完整历史 + 验证/测试指标
  state.json        最近 epoch、最佳分数
```

选模综合分：

```text
0.35 * genre_f1 + 0.25 * emotion_f1 + 0.20 * mode_f1 + 0.20 * (1 - bpm_mae/60)
```

---

## 4. 评估与打分

```powershell
python training/score.py "D:\music\demo.mp3" `
  --weights training/runs/<run_id>/best_model.pt
```

输出包含模型预测（genre/emotion/mode/BPM）、DSP 指标、可配置规则评分和免责声明。
更换 `scoring/rubric.default.json` 即可调整评分规则，无需重训。

`training/infer.py` 提供 `Tagger`，供 API / 脚本直接调用：

```python
from training.infer import Tagger

tagger = Tagger()  # 默认取最新 best_model.pt
result = tagger.predict_file("demo.mp3")
```

推理默认对 30 秒窗口做 3 段 TTA（checkpoint 中的 `tta_crops`），并自动兼容旧 v1 检查点。

---

## 5. 已知限制

* emotion 与 mode/BPM 是 **伪标签**（DSP 或人工 mood 标签投影），不是人工逐曲标注；
  分数只能作为辅助参考，不能替代评审。
* FMA-medium 是 30 秒片段，Jamendo 是低码率整曲，两者的响度/编曲分布不同；
  跨数据集评估时不要直接比较绝对分数。
* genre 的 `Horror` 类主要来自 darkwave/gothic 等标签，样本较少，F1 通常偏低。
* 训练集类别不均衡，因此默认开启 sqrt 逆频率采样；关闭后整体准确率可能更高，
  但少数类会更差。
* 数据许可证以逐曲字段为准；默认语料仅适合研究/评估，商用请使用
  `--license-policy commercial` 并自行复核。
