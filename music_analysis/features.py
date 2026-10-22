"""低层音乐特征提取与启发式映射。

设计原则：
- 纯 CPU、离线、确定性（不依赖随机初始化）；
- 每个数值特征都可追溯到具体 DSP 指标；
- 情绪/调式等高层结论明确标注为启发式，不作为事实性判断。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import librosa
import numpy as np

HOP_LENGTH = 512
FRAME_LENGTH = 2048
EPS = 1e-10

KEY_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

# Krumhansl-Schmuckler 调性轮廓（C 为主音）
MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
    dtype=float,
)
MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17],
    dtype=float,
)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    if value is None or not np.isfinite(value):
        return low
    return float(min(high, max(low, value)))


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a = a - a.mean()
    b = b - b.mean()
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom < EPS:
        return 0.0
    return float(np.dot(a, b) / denom)


def _db(amplitude: float) -> float:
    return float(20.0 * np.log10(max(float(amplitude), EPS)))


def frame_db(rms: np.ndarray) -> np.ndarray:
    return 20.0 * np.log10(np.maximum(rms, EPS))


# ---------------------------------------------------------------------------
# 节奏
# ---------------------------------------------------------------------------
def estimate_rhythm(y: np.ndarray, sr: int, duration_sec: float) -> Dict[str, Any]:
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP_LENGTH, aggregate=np.median)
    if onset_env.size == 0:
        return {
            "tempo_bpm": None,
            "tempo_confidence": None,
            "beat_frames": np.array([], dtype=int),
            "beat_regularity": None,
            "onset_rate_per_sec": None,
            "offbeat_energy_ratio": None,
        }

    tempo_raw, beat_frames = librosa.beat.beat_track(
        onset_envelope=onset_env,
        sr=sr,
        hop_length=HOP_LENGTH,
        trim=False,
        units="frames",
    )
    tempo = float(np.atleast_1d(tempo_raw)[0]) if np.size(tempo_raw) else 0.0
    beat_frames = np.asarray(beat_frames, dtype=int)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=HOP_LENGTH)

    beat_regularity: Optional[float] = None
    if beat_times.size >= 3:
        intervals = np.diff(beat_times)
        intervals = intervals[intervals > 0]
        if intervals.size >= 2 and intervals.mean() > EPS:
            beat_regularity = clamp(1.0 - float(intervals.std() / intervals.mean()))

    onset_frames = librosa.onset.onset_detect(
        onset_envelope=onset_env, sr=sr, hop_length=HOP_LENGTH, units="frames", backtrack=False
    )
    onset_rate = float(onset_frames.size / duration_sec) if duration_sec > 0 else None

    offbeat_ratio: Optional[float] = None
    if beat_frames.size >= 2:
        beats = beat_frames[(beat_frames >= 0) & (beat_frames < onset_env.size)]
        if beats.size >= 2:
            offbeat = ((beats[:-1] + beats[1:]) // 2).astype(int)
            offbeat = offbeat[(offbeat >= 0) & (offbeat < onset_env.size)]
            if offbeat.size:
                beat_strength = float(np.mean(onset_env[beats]))
                off_strength = float(np.mean(onset_env[offbeat]))
                offbeat_ratio = clamp(off_strength / (beat_strength + EPS))

    tempo_confidence: Optional[float] = None
    if tempo > 0:
        autocorr = librosa.autocorrelate(onset_env, max_size=max(2, int(4.0 * sr / HOP_LENGTH)))
        lag = int(round((60.0 / tempo) * sr / HOP_LENGTH))
        clarity = 0.0
        if 0 < lag < autocorr.size and autocorr[0] > EPS:
            clarity = clamp(float(autocorr[lag] / autocorr[0]) / 0.4)
        tempo_confidence = clamp(0.6 * clarity + 0.4 * (beat_regularity or 0.0))

    return {
        "tempo_bpm": tempo if tempo > 0 else None,
        "tempo_confidence": tempo_confidence if tempo > 0 else None,
        "beat_frames": beat_frames,
        "beat_regularity": beat_regularity,
        "onset_rate_per_sec": onset_rate,
        "offbeat_energy_ratio": offbeat_ratio,
    }


# ---------------------------------------------------------------------------
# 调性
# ---------------------------------------------------------------------------
def estimate_tonality(y: np.ndarray, sr: int) -> Dict[str, Any]:
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP_LENGTH, bins_per_octave=36)
    chroma_mean = chroma.mean(axis=1) if chroma.size else np.zeros(12)
    total = float(chroma_mean.sum())
    profile = chroma_mean / total if total > EPS else np.ones(12) / 12.0

    scores: List[Tuple[float, int, str]] = []
    for tonic in range(12):
        scores.append((_pearson(profile, np.roll(MAJOR_PROFILE, tonic)), tonic, "major"))
        scores.append((_pearson(profile, np.roll(MINOR_PROFILE, tonic)), tonic, "minor"))
    scores.sort(key=lambda item: item[0], reverse=True)
    best_corr, tonic, mode = scores[0]
    second_corr = scores[1][0]
    margin = max(0.0, best_corr - second_corr)

    confidence = clamp(
        0.65 * clamp((best_corr - 0.35) / 0.55) + 0.35 * clamp(margin / 0.25)
    )

    try:
        tuning_cents = float(librosa.estimate_tuning(y=y, sr=sr)) * 100.0
    except Exception:
        tuning_cents = None

    chroma_profile = {
        name: round(float(profile[i]), 6) for i, name in enumerate(KEY_NAMES)
    }

    return {
        "key": KEY_NAMES[tonic],
        "mode": mode,
        "key_confidence": round(confidence, 4),
        "tuning_cents": round(tuning_cents, 2) if tuning_cents is not None else None,
        "chroma_profile": chroma_profile,
    }


# ---------------------------------------------------------------------------
# 动态
# ---------------------------------------------------------------------------
def estimate_dynamics(y: np.ndarray, sr: int) -> Dict[str, Any]:
    rms = librosa.feature.rms(y=y, frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH)[0]
    rms_db = frame_db(rms)
    active = rms_db[rms_db > -60.0]
    if active.size == 0:
        active = rms_db

    loudness = float(np.mean(active))
    dynamic_range = float(np.percentile(active, 95) - np.percentile(active, 10))
    peak = _db(float(np.max(np.abs(y))) if y.size else 0.0)
    silence_ratio = clamp(float(np.mean(rms_db < -60.0)))
    clipping_ratio = clamp(float(np.mean(np.abs(y) >= 0.999))) if y.size else 0.0

    return {
        "loudness_db": round(loudness, 2),
        "dynamic_range_db": round(max(0.0, dynamic_range), 2),
        "peak_dbfs": round(peak, 2),
        "silence_ratio": round(silence_ratio, 4),
        "clipping_ratio": round(clipping_ratio, 6),
        "rms_db_frames": rms_db,
    }


# ---------------------------------------------------------------------------
# 音色
# ---------------------------------------------------------------------------
def estimate_timbre(y: np.ndarray, sr: int) -> Dict[str, Any]:
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=HOP_LENGTH)[0]
    rolloff = librosa.feature.spectral_rolloff(
        y=y, sr=sr, hop_length=HOP_LENGTH, roll_percent=0.85
    )[0]
    flatness = librosa.feature.spectral_flatness(y=y, hop_length=HOP_LENGTH)[0]
    zcr = librosa.feature.zero_crossing_rate(
        y=y, frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH
    )[0]

    centroid_hz = float(np.mean(centroid))
    rolloff_hz = float(np.mean(rolloff))
    flatness_mean = clamp(float(np.mean(flatness)))
    zcr_mean = clamp(float(np.mean(zcr)))

    y_harmonic, y_percussive = librosa.effects.hpss(y)
    harmonic_energy = float(np.sum(y_harmonic ** 2))
    percussive_energy = float(np.sum(y_percussive ** 2))
    harmonic_ratio = clamp(harmonic_energy / (harmonic_energy + percussive_energy + EPS))

    if centroid_hz < 1200.0:
        brightness = "dark"
    elif centroid_hz < 2600.0:
        brightness = "balanced"
    else:
        brightness = "bright"

    if harmonic_ratio >= 0.70:
        texture = "harmonic"
    elif harmonic_ratio <= 0.45:
        texture = "percussive"
    else:
        texture = "mixed"

    return {
        "brightness": brightness,
        "spectral_centroid_hz": round(centroid_hz, 2),
        "spectral_rolloff_hz": round(rolloff_hz, 2),
        "spectral_flatness": round(flatness_mean, 6),
        "zero_crossing_rate": round(zcr_mean, 6),
        "harmonic_ratio": round(harmonic_ratio, 4),
        "texture": texture,
    }


# ---------------------------------------------------------------------------
# 情绪（Russell 环形模型启发式）
# ---------------------------------------------------------------------------
def estimate_mood(
    *,
    tempo_bpm: Optional[float],
    loudness_db: Optional[float],
    onset_rate_per_sec: Optional[float],
    spectral_centroid_hz: Optional[float],
    spectral_flatness: Optional[float],
    mode: Optional[str],
    beat_regularity: Optional[float],
) -> Dict[str, Any]:
    # 唤醒度校准：速度权重更高；50–140 BPM 覆盖慢歌到快歌的常见区间
    tempo_norm = clamp(((tempo_bpm or 50.0) - 50.0) / 90.0)
    loud_norm = clamp(((loudness_db if loudness_db is not None else -40.0) + 40.0) / 30.0)
    onset_norm = clamp((onset_rate_per_sec or 0.0) / 6.0)
    centroid_norm = clamp(((spectral_centroid_hz or 800.0) - 800.0) / 3200.0)
    flatness_norm = clamp((spectral_flatness or 0.0) / 0.15)

    arousal = clamp(
        0.40 * tempo_norm + 0.25 * loud_norm + 0.20 * onset_norm + 0.15 * centroid_norm
    )
    mode_score = 0.75 if mode == "major" else (0.25 if mode == "minor" else 0.5)
    valence = clamp(
        0.55 * mode_score
        + 0.20 * centroid_norm
        + 0.15 * (1.0 - flatness_norm)
        + 0.10 * (beat_regularity if beat_regularity is not None else 0.5)
    )

    if abs(valence - 0.5) < 0.06 and abs(arousal - 0.5) < 0.08:
        label = "neutral"
    elif arousal >= 0.5 and valence >= 0.5:
        label = "happy"
    elif arousal >= 0.5 and valence < 0.5:
        label = "tense"
    elif arousal < 0.5 and valence >= 0.5:
        label = "calm"
    else:
        label = "sad"

    strength = float(np.hypot(valence - 0.5, arousal - 0.5))
    confidence = clamp(0.5 + strength)

    return {
        "valence": round(valence, 4),
        "arousal": round(arousal, 4),
        "label": label,
        "confidence": round(confidence, 4),
    }


def energy_label(
    arousal: Optional[float],
    loudness_db: Optional[float],
    onset_rate_per_sec: Optional[float],
) -> str:
    loud_norm = clamp(((loudness_db if loudness_db is not None else -40.0) + 40.0) / 30.0)
    onset_norm = clamp((onset_rate_per_sec or 0.0) / 6.0)
    score = 0.45 * (arousal if arousal is not None else 0.5) + 0.30 * loud_norm + 0.25 * onset_norm
    if score < 0.33:
        return "low"
    if score < 0.52:
        return "medium"
    return "high"


def build_tags(
    *,
    mode: Optional[str],
    tempo_bpm: Optional[float],
    texture: Optional[str],
    brightness: Optional[str],
    energy: Optional[str],
    spectral_flatness: Optional[float],
) -> List[str]:
    tags: List[str] = []
    if mode:
        tags.append(mode)
    if tempo_bpm is not None:
        if tempo_bpm < 90:
            tags.append("slow")
        elif tempo_bpm < 140:
            tags.append("mid_tempo")
        else:
            tags.append("fast")
    if texture:
        tags.append(texture)
    if brightness:
        tags.append(brightness)
    if energy:
        tags.append(f"{energy}_energy")
    if spectral_flatness is not None and spectral_flatness > 0.10:
        tags.append("noisy")
    else:
        tags.append("tonal")
    return tags


# ---------------------------------------------------------------------------
# 曲式结构
# ---------------------------------------------------------------------------
def estimate_structure(
    *,
    y: np.ndarray,
    sr: int,
    beat_frames: Sequence[int],
    duration_sec: float,
    rms_db_frames: np.ndarray,
    loudness_db: float,
    max_sections: int = 6,
    min_section_sec: float = 2.0,
) -> List[Dict[str, Any]]:
    """基于小节级 chroma/MFCC/RMS 特征的递归变点检测。

    假设 4/4 拍、每 4 拍为一小节。返回
    ``[{start_sec, end_sec, energy_db, energy}, ...]``；证据不足时返回单段，
    避免“编造结构”。
    """
    beat_frames = np.asarray([b for b in beat_frames if b >= 0], dtype=int)
    if beat_frames.size < 16 or duration_sec < min_section_sec * 2:
        return _whole_track_section(duration_sec, rms_db_frames, loudness_db)

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP_LENGTH, bins_per_octave=36)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=HOP_LENGTH)
    rms = librosa.feature.rms(y=y, frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH)[0]

    n_features = min(chroma.shape[1], mfcc.shape[1], rms.size)
    beat_frames = beat_frames[beat_frames < n_features]

    bar_features: List[np.ndarray] = []
    bar_start_frames: List[int] = []
    for i in range(0, len(beat_frames) - 4, 4):
        start, end = int(beat_frames[i]), int(beat_frames[i + 4])
        if end <= start:
            continue
        log_rms = float(np.log(rms[start:end].mean() + EPS))
        bar_features.append(
            np.concatenate(
                [
                    chroma[:, start:end].mean(axis=1),
                    mfcc[:, start:end].mean(axis=1),
                    # 响度变化是分段最可靠的线索之一，重复三次提高权重
                    np.array([log_rms, log_rms, log_rms]),
                ]
            )
        )
        bar_start_frames.append(start)

    if len(bar_features) < 4:
        return _whole_track_section(duration_sec, rms_db_frames, loudness_db)

    X = np.asarray(bar_features, dtype=float)
    std = X.std(axis=0)
    std[std < EPS] = 1.0
    X = (X - X.mean(axis=0)) / std

    segments = _recursive_segment_bars(
        X, max_sections=max_sections, min_bars=2, gain_threshold=0.15
    )

    sections: List[Dict[str, Any]] = []
    for start_bar, end_bar in segments:
        start_sec = (
            0.0
            if start_bar == 0
            else float(
                librosa.frames_to_time(
                    bar_start_frames[start_bar], sr=sr, hop_length=HOP_LENGTH
                )
            )
        )
        end_sec = (
            duration_sec
            if end_bar >= len(bar_start_frames)
            else float(
                librosa.frames_to_time(
                    bar_start_frames[end_bar], sr=sr, hop_length=HOP_LENGTH
                )
            )
        )
        start_frame = int(round(start_sec * sr / HOP_LENGTH))
        end_frame = int(round(end_sec * sr / HOP_LENGTH))
        segment_db = rms_db_frames[start_frame:end_frame]
        section_db = float(np.mean(segment_db)) if segment_db.size else loudness_db
        offset = section_db - loudness_db
        energy = "high" if offset >= 1.5 else ("low" if offset <= -1.5 else "medium")
        sections.append(
            {
                "start_sec": round(max(0.0, start_sec), 3),
                "end_sec": round(min(duration_sec, end_sec), 3),
                "energy_db": round(section_db, 2),
                "energy": energy,
            }
        )
    return sections


def _recursive_segment_bars(
    X: np.ndarray,
    *,
    max_sections: int,
    min_bars: int = 2,
    gain_threshold: float = 0.15,
) -> List[Tuple[int, int]]:
    """自顶向下二分变点检测；仅当组间平方和占比超过阈值时切分。"""
    segments: List[Tuple[int, int]] = [(0, len(X))]
    while len(segments) < max_sections:
        best: Optional[Tuple[float, int, int]] = None
        for index, (start, end) in enumerate(segments):
            length = end - start
            if length < 2 * min_bars:
                continue
            window = X[start:end]
            total = float(np.sum((window - window.mean(axis=0)) ** 2))
            if total <= EPS:
                continue
            for split in range(min_bars, length - min_bars + 1):
                left, right = window[:split], window[split:]
                between = (split * (length - split) / length) * float(
                    np.sum((left.mean(axis=0) - right.mean(axis=0)) ** 2)
                )
                gain = between / total
                if best is None or gain > best[0]:
                    best = (gain, index, start + split)
        if best is None or best[0] < gain_threshold:
            break
        _, index, split = best
        start, end = segments[index]
        segments[index : index + 1] = [(start, split), (split, end)]
    return segments


def _whole_track_section(
    duration_sec: float, rms_db_frames: np.ndarray, loudness_db: float
) -> List[Dict[str, Any]]:
    return [
        {
            "start_sec": 0.0,
            "end_sec": round(duration_sec, 3),
            "energy_db": round(float(loudness_db), 2),
            "energy": "medium",
        }
    ]
