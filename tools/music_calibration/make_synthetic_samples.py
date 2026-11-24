#!/usr/bin/env python3
"""生成带精确 BPM/调式标签的合成样例，用于音频标签回归。

只用于验证 BPM 误差和大小调判断，**不能**代表真实音乐的曲风/情绪准确率；
曲风/情绪仍需要人工标注的真实作品。

    python make_synthetic_samples.py --out synthetic
"""
from __future__ import annotations

import argparse
import csv
import wave
from pathlib import Path

import numpy as np

SR = 22050
DURATION = 45.0


def _write_wav(path: Path, samples: np.ndarray) -> None:
    data = np.clip(samples, -1.0, 1.0)
    pcm = (data * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SR)
        handle.writeframes(pcm.tobytes())


def _chord(mode: str) -> list[float]:
    # C 大调：C4/E4/G4；A 小调：A3/C4/E4。
    if mode == "major":
        return [261.63, 329.63, 392.00]
    return [220.00, 261.63, 329.63]


def make_track(path: Path, bpm: float, mode: str) -> None:
    t = np.arange(int(SR * DURATION), dtype=np.float32) / SR
    signal = np.zeros_like(t)

    # 和弦铺底，带缓慢起伏，避免完全静态。
    for index, freq in enumerate(_chord(mode)):
        envelope = 0.12 + 0.03 * np.sin(2 * np.pi * 0.1 * t + index)
        signal += 0.10 * envelope * np.sin(2 * np.pi * freq * t)

    # 节拍点击：每拍一个短促脉冲，BPM 真值精确。
    beat = 60.0 / bpm
    for start in np.arange(0, DURATION, beat):
        length = int(0.03 * SR)
        local = np.arange(length) / SR
        click = 0.35 * np.exp(-local * 60) * np.sin(2 * np.pi * 1200 * local)
        offset = int(start * SR)
        end = min(offset + length, len(signal))
        signal[offset:end] += click[: end - offset]

    # 极轻的白噪声，避免静音帧导致动态范围异常。
    rng = np.random.default_rng(int(bpm))
    signal += 0.002 * rng.standard_normal(len(signal))
    _write_wav(path, signal)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="synthetic")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    cases = [
        ("synth-060-major", 60, "major"),
        ("synth-090-minor", 90, "minor"),
        ("synth-120-major", 120, "major"),
        ("synth-150-minor", 150, "minor"),
        ("synth-075-major", 75, "major"),
        ("synth-110-minor", 110, "minor"),
    ]
    rows = []
    for name, bpm, mode in cases:
        path = out / f"{name}.wav"
        make_track(path, bpm, mode)
        # CSV 内的相对路径以 CSV 所在目录为基准。
        rows.append({"id": name, "path": path.name, "genre": "", "emotion": "", "mode": mode, "bpm": bpm})

    csv_path = out / "synthetic_samples.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "path", "genre", "emotion", "mode", "bpm"])
        writer.writeheader()
        writer.writerows(rows)
    print(csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
