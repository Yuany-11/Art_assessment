"""Deterministic DSP labels used to supervise mode and BPM.

These labels are *pseudo-labels*: they come from the same signal-processing
techniques the product already uses (Krumhansl profiles, beat tracking).  They
are filtered by confidence so the model is never trained on low-evidence
targets, and the confidence is carried into the manifest so the loss can be
weighted per sample.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

import librosa
import numpy as np

try:
    from .features import HOP_LENGTH
except ImportError:  # executed as a top-level module from training/
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from features import HOP_LENGTH  # type: ignore

KEY_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
    dtype=float,
)
MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17],
    dtype=float,
)
EPS = 1e-10


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    if value is None or not np.isfinite(value):
        return low
    return float(min(high, max(low, value)))


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=float) - float(np.mean(a))
    b = np.asarray(b, dtype=float) - float(np.mean(b))
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom < EPS:
        return 0.0
    return float(np.dot(a, b) / denom)


def estimate_key_mode(chroma: np.ndarray) -> Dict[str, Any]:
    """Krumhansl-Schmuckler key/mode estimate with a confidence margin."""
    if chroma.size == 0:
        return {
            "key": None,
            "mode": None,
            "key_confidence": 0.0,
            "chroma_profile": None,
        }
    profile = np.asarray(chroma, dtype=float).mean(axis=1)
    total = float(profile.sum())
    profile = profile / total if total > EPS else np.ones(12) / 12.0
    profile = profile - profile.mean()

    candidates = []
    for tonic in range(12):
        for mode, base in (("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)):
            corr = _pearson(profile, np.roll(base, tonic))
            candidates.append((corr, tonic, mode))
    candidates.sort(key=lambda item: item[0], reverse=True)
    best_corr, tonic, mode = candidates[0]
    margin = max(0.0, best_corr - candidates[1][0])

    # Map correlation + margin to [0, 1]; values below 0.35 are weak evidence.
    confidence = _clamp(
        0.65 * _clamp((best_corr - 0.30) / 0.60) + 0.35 * _clamp(margin / 0.25)
    )
    chroma_profile = np.asarray(chroma, dtype=float).mean(axis=1)
    return {
        "key": KEY_NAMES[tonic],
        "mode": mode,
        "key_confidence": round(confidence, 4),
        "chroma_profile": [round(float(v), 6) for v in chroma_profile],
    }


def _fold_tempo(bpm: float, low: float = 70.0, high: float = 180.0) -> float:
    """Move an octave-ambiguous tempo into the perceptually common range."""
    if not np.isfinite(bpm) or bpm <= 0:
        return 0.0
    while bpm < low:
        bpm *= 2.0
    while bpm > high:
        bpm /= 2.0
    return float(bpm)


def estimate_tempo(y: np.ndarray, sr: int, hop_length: int = HOP_LENGTH) -> Dict[str, Any]:
    """Beat-track tempo with octave folding + autocorrelation confidence."""
    if y.size < sr // 2:
        return {
            "bpm": None,
            "bpm_confidence": 0.0,
            "beat_count": 0,
            "beat_regularity": None,
        }

    onset_env = librosa.onset.onset_strength(
        y=y, sr=sr, hop_length=hop_length, aggregate=np.median
    )
    if onset_env.size < 4:
        return {
            "bpm": None,
            "bpm_confidence": 0.0,
            "beat_count": 0,
            "beat_regularity": None,
        }

    tempo_raw, beat_frames = librosa.beat.beat_track(
        onset_envelope=onset_env,
        sr=sr,
        hop_length=hop_length,
        trim=False,
        units="frames",
    )
    bpm_raw = float(np.atleast_1d(tempo_raw)[0]) if np.size(tempo_raw) else 0.0
    bpm = _fold_tempo(bpm_raw)
    if bpm < 40.0 or bpm > 220.0:
        return {
            "bpm": None,
            "bpm_confidence": 0.0,
            "beat_count": int(np.asarray(beat_frames).size),
            "beat_regularity": None,
        }

    beat_frames = np.asarray(beat_frames, dtype=int)
    regularity = 0.0
    if beat_frames.size >= 3:
        beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop_length)
        intervals = np.diff(beat_times)
        intervals = intervals[intervals > 0]
        if intervals.size >= 2 and float(intervals.mean()) > EPS:
            cv = float(intervals.std() / intervals.mean())
            regularity = _clamp(1.0 - cv)

    clarity = 0.0
    if onset_env.size > 8 and float(onset_env[0]) > 0:
        autocorr = librosa.autocorrelate(
            onset_env, max_size=max(8, int(4.0 * sr / hop_length))
        )
        lag = int(round((60.0 / bpm) * sr / hop_length))
        if 0 < lag < autocorr.size:
            clarity = _clamp(float(autocorr[lag] / (autocorr[0] + EPS)) / 0.4)

    confidence = _clamp(0.55 * regularity + 0.45 * clarity)
    return {
        "bpm": round(float(bpm), 2),
        "bpm_confidence": round(float(confidence), 4),
        "beat_count": int(beat_frames.size),
        "beat_regularity": round(float(regularity), 4),
    }


def estimate_key_mode_from_cache(chroma: np.ndarray) -> Dict[str, Any]:
    return estimate_key_mode(chroma)


def estimate_tempo_from_audio(
    y: np.ndarray, sr: int, hop_length: int = HOP_LENGTH
) -> Dict[str, Any]:
    return estimate_tempo(y, sr=sr, hop_length=hop_length)
