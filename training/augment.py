"""特征域数据增强：作用在缓存好的 log-mel / chroma 上，不重新解码音频。

为什么在特征域做
----------------
训练集的特征已经预先算好（``training/data/cache/*.npz``），如果回到原始音频
做增益/噪声/变速，每个 epoch 都要重新 STFT，8 进程也追不上 GPU。特征域的增强
只做矩阵运算，单样本开销在百微秒量级，所以本模块全部在 ``mel/chroma`` 上实现。

注意：**增益增强在本流程里是恒等变换**。``features.normalize_features`` 会对每个
样本做逐样本标准化（减均值、除标准差），所以乘一个常数音量增益会被完全抵消。
想模拟“不同录音电平”，只能改动态范围压缩，而不是简单加 dB —— 这里不做。

支持的增强
----------
* ``time_stretch``：沿时间轴重采样，等价于变速不变调。**同时缩放 BPM 标签**
  （``bpm *= rate``），所以它既是对抗过拟合的正则，也是 BPM 头的数据扩充。
* ``time_roll``：时间轴循环平移，模拟从不同位置开始切一段，标签不变。
* ``spec_augment``：频率/时间掩码（SpecAugment），复用 ``features.spec_augment``。
* ``noise``：加高斯白噪声，放在标准化之后（此时特征量级约 N(0,1)）。

如果以后要加“真实录音”类增强（房间混响、码率压缩、变速变调），那必须回到波形
域做，参考文末的 torchaudio 示例。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

try:
    from .features import crop_or_pad, spec_augment
except ImportError:  # executed as a top-level module from training/
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from features import crop_or_pad, spec_augment  # type: ignore

Features = Tuple[np.ndarray, np.ndarray]


@dataclass(frozen=True)
class AugmentConfig:
    """增强强度。默认值与旧版 ``MusicDataset`` 的行为一致（只开 SpecAugment + 轻噪声）。"""

    freq_mask_width: int = 16
    time_mask_width: int = 48
    n_freq_masks: int = 2
    n_time_masks: int = 2
    noise_prob: float = 0.30
    noise_std: float = 0.02
    roll_prob: float = 0.0
    stretch_prob: float = 0.0
    stretch_range: Tuple[float, float] = (0.9, 1.1)


def time_stretch(
    mel: np.ndarray,
    chroma: np.ndarray,
    rate: float,
) -> Tuple[np.ndarray, np.ndarray, float]:
    """沿时间轴线性插值重采样。

    ``rate > 1`` 表示“播放更快”（帧数变少、速度变快、BPM 变大）。
    返回 ``(mel, chroma, bpm_scale)``，调用方需要把 BPM 标签乘以 ``bpm_scale``。

    用左右邻帧的加权和实现，避免 ``np.interp`` 的逐行 Python 循环
    （128 行 × 每行一次插值，在 8 个 worker 里会明显拖慢数据加载）。
    """
    rate = float(np.clip(rate, 0.5, 2.0))
    n_frames = mel.shape[1]
    if n_frames < 4 or abs(rate - 1.0) < 1e-3:
        return mel, chroma, 1.0

    target = max(4, int(round(n_frames / rate)))
    pos = np.linspace(0.0, n_frames - 1, target, dtype=np.float32)
    left = np.floor(pos).astype(np.int64)
    right = np.minimum(left + 1, n_frames - 1)
    frac = (pos - left)[None, :]

    def _resample(array: np.ndarray) -> np.ndarray:
        return (array[:, left] * (1.0 - frac) + array[:, right] * frac).astype(
            np.float32
        )

    return _resample(mel), _resample(chroma), rate


def time_roll(
    mel: np.ndarray, chroma: np.ndarray, rng: np.random.Generator
) -> Features:
    """时间轴循环平移（帧数不变，标签不变）。"""
    n_frames = mel.shape[1]
    if n_frames < 2:
        return mel, chroma
    shift = int(rng.integers(0, n_frames))
    if shift == 0:
        return mel, chroma
    return np.roll(mel, shift, axis=1), np.roll(chroma, shift, axis=1)


class FeatureAugmenter:
    """把上面几种增强按概率串起来；可调用对象，便于 DataLoader 多进程 pickle。"""

    def __init__(self, config: Optional[AugmentConfig] = None):
        self.config = config or AugmentConfig()

    def __call__(
        self,
        mel: np.ndarray,
        chroma: np.ndarray,
        rng: np.random.Generator,
        frames: Optional[int] = None,
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        """返回 ``(mel, chroma, bpm_scale)``。

        ``frames`` 给定时会在变速后重新裁剪/补齐到固定帧数（模型要求定长输入）。
        """
        cfg = self.config
        bpm_scale = 1.0

        if cfg.stretch_prob > 0 and rng.random() < cfg.stretch_prob:
            low, high = cfg.stretch_range
            rate = float(rng.uniform(low, high))
            mel, chroma, bpm_scale = time_stretch(mel, chroma, rate)
            if frames:
                mel, chroma = crop_or_pad(
                    mel, chroma, frames, random_crop=False, rng=rng
                )

        if cfg.roll_prob > 0 and rng.random() < cfg.roll_prob:
            mel, chroma = time_roll(mel, chroma, rng)

        mel, chroma = spec_augment(
            mel,
            chroma,
            rng,
            n_freq_masks=cfg.n_freq_masks,
            freq_mask_width=cfg.freq_mask_width,
            n_time_masks=cfg.n_time_masks,
            time_mask_width=cfg.time_mask_width,
        )

        if cfg.noise_prob > 0 and rng.random() < cfg.noise_prob:
            mel = mel + rng.normal(0.0, cfg.noise_std, size=mel.shape).astype(
                np.float32
            )

        return mel, chroma, bpm_scale


# ---------------------------------------------------------------------------
# 参考：波形域增强（当前训练流程不用，仅用于需要“真实录音退化”的场景）
# ---------------------------------------------------------------------------
def waveform_augment_reference(y: np.ndarray, sr: int, rng: np.random.Generator):
    """波形域增强示例，需要 torchaudio / librosa 且必须在特征提取之前调用。

    ``y`` 是单声道 float32 波形；返回增强后的波形。

    * 音量：``y * 10 ** (db / 20)``，随机 -6～+3 dB；
    * 噪声：按 SNR 注入白噪声，而不是固定幅度（固定幅度在大音量段落会失效）；
    * 变速不变调：``librosa.effects.time_stretch`` 用相位声码器，
      变速后同样要把 BPM 标签乘以 rate；
    * 变速变调（更自然但会改变调式/音高）：``librosa.effects.pitch_shift``。
    """
    import librosa

    # 1) 随机增益（波形域才有意义；特征域会被标准化抵消）
    gain_db = float(rng.uniform(-6.0, 3.0))
    y = y * np.float32(10.0 ** (gain_db / 20.0))

    # 2) 按 SNR 加噪
    if rng.random() < 0.3:
        snr_db = float(rng.uniform(15.0, 30.0))
        noise = rng.normal(0.0, 1.0, size=y.shape).astype(np.float32)
        signal_power = float(np.mean(y**2)) + 1e-9
        noise_power = signal_power / (10.0 ** (snr_db / 10.0))
        y = y + noise * np.sqrt(noise_power / (float(np.mean(noise**2)) + 1e-9))

    # 3) 变速不变调（BPM 标签需要同步乘以 rate）
    if rng.random() < 0.2:
        rate = float(rng.uniform(0.9, 1.1))
        y = librosa.effects.time_stretch(y, rate=rate)

    # 4) 轻微变调：会改变调式，训练调式头时建议关掉
    if rng.random() < 0.1:
        y = librosa.effects.pitch_shift(y, sr=sr, n_steps=float(rng.uniform(-1, 1)))

    return y
