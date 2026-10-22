"""测试用的最小合成音频。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

SR = 22050


def synth_chord_with_beats(path: Path, duration: float = 8.0, bpm: float = 120.0) -> Path:
    """C 大调三和弦 + 每拍低频 click，便于稳定地检测速度与调性。"""
    rng = np.random.default_rng(7)
    t = np.arange(int(SR * duration)) / SR
    y = np.zeros_like(t, dtype=np.float32)
    for freq in (261.63, 329.63, 392.00):  # C4 E4 G4
        y += (0.14 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
        y += (0.04 * np.sin(2 * np.pi * freq * 2 * t)).astype(np.float32)

    beat_interval = 60.0 / bpm
    beat = 0.0
    while beat < duration:
        n = int(0.12 * SR)
        local = np.arange(n) / SR
        freq = 45.0 + 85.0 * np.exp(-local * 25.0)
        phase = 2 * np.pi * np.cumsum(freq) / SR
        click = (0.5 * np.sin(phase) * np.exp(-local * 18.0)).astype(np.float32)
        start = int(beat * SR)
        end = min(len(y), start + n)
        if end > start:
            y[start:end] += click[: end - start]
        beat += beat_interval

    # 极轻噪声底，避免完全无噪信号
    y += (0.0005 * rng.standard_normal(len(y))).astype(np.float32)
    peak = float(np.max(np.abs(y)))
    if peak > 0:
        y *= 0.5 / peak

    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, y, SR, subtype="PCM_16")
    return path


def write_silence(path: Path, duration: float = 2.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.zeros(int(SR * duration), dtype=np.float32), SR, subtype="PCM_16")
    return path
