#!/usr/bin/env python3
"""Score a music file with the trained model + an explicit, editable rubric.

Pipeline
--------
1. The neural model predicts genre / emotion / mode / BPM (training/infer.py).
2. DSP metrics (tonality confidence, beat regularity, dynamics, clipping, ...)
   are measured from the audio.
3. Each rubric metric is mapped to 0-100 through anchor points stored in JSON,
   weighted per dimension, penalised for quality problems, and graded.

The rubric is data, not weights: swap ``scoring/rubric.default.json`` for an
official rules file with the same schema and re-run. No retraining needed.

Usage
-----
    python training/score.py "song.mp3"
    python training/score.py "song.mp3" --rubric scoring/official.json --json out.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from features import SR
from infer import Tagger, features_from_audio

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUBRIC = PROJECT_ROOT / "scoring" / "rubric.default.json"

MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
PITCHES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _interp(anchors: list[list[float]], value: float) -> float:
    xs = [float(a[0]) for a in anchors]
    ys = [float(a[1]) for a in anchors]
    return float(np.clip(np.interp(float(value), xs, ys), 0.0, 100.0))


def estimate_key(chroma: np.ndarray) -> tuple[str, str, float]:
    profile = chroma.mean(axis=1).astype(np.float64)
    profile = profile - profile.mean()
    scores = []
    for root in range(12):
        for mode, base in (("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)):
            rolled = np.roll(base, root)
            rolled = rolled - rolled.mean()
            denom = np.linalg.norm(profile) * np.linalg.norm(rolled)
            corr = float(np.dot(profile, rolled) / denom) if denom else 0.0
            scores.append((corr, root, mode))
    scores.sort(reverse=True)
    best, root, mode = scores[0]
    confidence = round(float(best - scores[1][0]), 4)
    return f"{PITCHES[root]} {mode}", mode, confidence


def _section_count(y: np.ndarray, sr: int) -> int:
    """Crude energy-based section count (2 s windows, 3 dB change)."""
    win, hop = int(2.0 * sr), int(1.0 * sr)
    energies = []
    for start in range(0, max(1, len(y) - win), hop):
        chunk = y[start:start + win]
        energies.append(20.0 * np.log10(float(np.sqrt(np.mean(chunk ** 2))) + 1e-9))
    if len(energies) < 2:
        return 1
    changes = 0
    last = -10
    for i in range(1, len(energies)):
        if abs(energies[i] - energies[i - 1]) > 3.0 and i - last >= 4:
            changes += 1
            last = i
    return int(min(8, changes + 1))


def dsp_metrics(path: str | Path, max_seconds: float = 60.0) -> dict:
    import librosa
    import soundfile as sf

    try:
        info = sf.info(str(path))
        duration = float(info.duration)
        offset = max(0.0, (duration - max_seconds) / 2.0)
    except Exception:
        duration, offset = 0.0, 0.0

    y, sr = librosa.load(str(path), sr=SR, mono=True, offset=offset or None, duration=max_seconds)
    if y.size < sr // 2:
        raise ValueError("audio shorter than 0.5 s")

    rms = librosa.feature.rms(y=y)[0]
    rms_db = 20.0 * np.log10(rms + 1e-9)
    peak = float(np.max(np.abs(y)))
    clipping_ratio = float(np.mean(np.abs(y) >= 0.995))
    silence_ratio = float(np.mean(rms < 1e-4))
    dynamic_range = float(np.percentile(rms_db, 95) - np.percentile(rms_db, 5))
    centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    flatness = float(np.mean(librosa.feature.spectral_flatness(y=y)))

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr)
    dur = len(y) / sr
    onset_rate = float(len(onsets) / dur) if dur else 0.0
    tempo = float(np.atleast_1d(librosa.feature.tempo(onset_envelope=onset_env, sr=sr))[0])

    try:
        _, beats = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
        if len(beats) >= 3:
            intervals = np.diff(beats).astype(np.float64)
            cv = float(np.std(intervals) / (np.mean(intervals) + 1e-9))
            tempo_regularity = float(max(0.0, 1.0 - min(1.0, cv)))
        else:
            tempo_regularity = 0.5
    except Exception:
        tempo_regularity = 0.5

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=512)
    key, key_mode, key_conf = estimate_key(chroma)
    frame_sums = chroma.sum(axis=0) + 1e-9
    probs = chroma / frame_sums
    entropy = -np.sum(probs * np.log(probs + 1e-12), axis=0) / np.log(12)
    chroma_entropy = float(np.mean(entropy))

    return {
        "duration_s": round(duration or dur, 2),
        "peak": round(peak, 4),
        "clipping_ratio": round(clipping_ratio, 6),
        "silence_ratio": round(silence_ratio, 4),
        "dynamic_range_db": round(dynamic_range, 2),
        "spectral_centroid_hz": round(centroid, 1),
        "spectral_flatness": round(flatness, 5),
        "tempo": round(tempo, 1),
        "tempo_regularity": round(tempo_regularity, 4),
        "onset_rate": round(onset_rate, 3),
        "onset_density": round(onset_rate, 3),
        "section_count": _section_count(y, sr),
        "chroma_entropy": round(chroma_entropy, 4),
        "key": key,
        "key_mode": key_mode,
        "key_confidence": key_conf,
        "usable": bool(silence_ratio < 0.9 and dur >= 0.5),
    }


def _metric_value(metric: str, metrics: dict) -> float | bool | None:
    return metrics.get(metric)


def apply_rubric(metrics: dict, predictions: dict, rubric: dict) -> dict:
    metrics = dict(metrics)
    metrics["mode_margin"] = round(
        float(sorted(predictions["mode_probs"].values(), reverse=True)[0]
              - sorted(predictions["mode_probs"].values(), reverse=True)[1]), 4
    )
    metrics["emotion_confidence"] = float(predictions["emotion_confidence"])
    probs = sorted(predictions["emotion_probs"].values(), reverse=True)
    metrics["emotion_margin"] = round(float(probs[0] - probs[1]), 4)

    dimensions = []
    total = 0.0
    weight_sum = 0.0
    for dim in rubric["dimensions"]:
        parts = []
        dim_score = 0.0
        wsum = 0.0
        for m in dim["metrics"]:
            raw = _metric_value(m["key"], metrics)
            if raw is None:
                continue
            if isinstance(raw, bool):
                score = 100.0 if raw else 0.0
            else:
                score = _interp(m["anchors"], float(raw))
            parts.append({
                "key": m["key"],
                "name": m["name"],
                "value": raw,
                "score": round(score, 1),
                "weight": m["weight"],
            })
            dim_score += score * m["weight"]
            wsum += m["weight"]
        score = dim_score / wsum if wsum else 0.0
        dimensions.append({
            "key": dim["key"],
            "name": dim["name"],
            "weight": dim["weight"],
            "score": round(score, 1),
            "metrics": parts,
        })
        total += score * dim["weight"]
        weight_sum += dim["weight"]

    total = total / weight_sum if weight_sum else 0.0

    penalties = []
    cap = None
    for rule in rubric.get("penalties", []):
        raw = metrics.get(rule["metric"])
        if raw is None:
            continue
        op, value = rule["op"], rule["value"]
        hit = (
            (op == ">" and float(raw) > float(value))
            or (op == "<" and float(raw) < float(value))
            or (op == "==" and raw == value)
            or (op == ">=" and float(raw) >= float(value))
        )
        if hit:
            penalties.append({"reason": rule["reason"], "delta": rule.get("delta", 0)})
            total += rule.get("delta", 0)
            if "cap" in rule:
                cap = rule["cap"] if cap is None else min(cap, rule["cap"])

    if cap is not None:
        total = min(total, cap)
    total = float(np.clip(total, 0.0, 100.0))

    grade = "待改进"
    for threshold, label in rubric["grade_bands"]:
        if total >= threshold:
            grade = label
            break

    return {
        "total": round(total, 1),
        "grade": grade,
        "dimensions": dimensions,
        "penalties": penalties,
    }


def score_file(
    path: str | Path,
    weights: str | Path | None = None,
    rubric_path: str | Path = DEFAULT_RUBRIC,
    tagger: Tagger | None = None,
) -> dict:
    import librosa

    rubric = json.loads(Path(rubric_path).read_text(encoding="utf-8"))
    if tagger is None:
        tagger = Tagger(weights) if weights else Tagger()

    info = None
    try:
        import soundfile as sf

        info = sf.info(str(path))
    except Exception:
        pass

    duration = float(info.duration) if info else 0.0
    offset = max(0.0, (duration - 30.0) / 2.0) if duration > 30.0 else 0.0
    y, _ = librosa.load(str(path), sr=SR, mono=True, offset=offset or None, duration=30.0)
    if y.size < SR // 2:
        raise ValueError("audio shorter than 0.5 s")

    mel, chroma = features_from_audio(y)
    predictions = tagger.predict_arrays(mel, chroma)
    metrics = dsp_metrics(path)
    scored = apply_rubric(metrics, predictions, rubric)

    return {
        "file": str(path),
        "analyzed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "duration_s": metrics["duration_s"],
        "predictions": {
            "genre": predictions["genre_top1"],
            "genre_confidence": predictions["genre_confidence"],
            "genre_probs": predictions["genre"],
            "emotion": predictions["emotion"],
            "emotion_cn": predictions["emotion_cn"],
            "emotion_confidence": predictions["emotion_confidence"],
            "mode": predictions["mode"],
            "mode_cn": predictions["mode_cn"],
            "mode_confidence": predictions["mode_confidence"],
            "bpm": predictions["bpm"],
            "key": metrics["key"],
            "key_confidence": metrics["key_confidence"],
        },
        "score": {
            "total": scored["total"],
            "grade": scored["grade"],
            "dimensions": scored["dimensions"],
            "penalties": scored["penalties"],
        },
        "dsp": metrics,
        "rubric": {
            "id": rubric["id"],
            "name": rubric["name"],
            "official": rubric.get("official", False),
            "note": rubric.get("note", ""),
        },
        "model": {
            "weights": predictions["weights"],
            "epoch": predictions["model_epoch"],
        },
        "disclaimer": "分数由可配置规则计算，默认规则非官方版本；情绪/调式为音频伪标签训练所得，不能替代人工评审。",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio", help="audio file (wav/flac/ogg/mp3)")
    parser.add_argument("--weights", default="", help="checkpoint path (default: latest known run)")
    parser.add_argument("--rubric", default=str(DEFAULT_RUBRIC))
    parser.add_argument("--json", default="", help="write full result to this JSON file")
    args = parser.parse_args(argv)

    result = score_file(args.audio, args.weights or None, args.rubric)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json:
        Path(args.json).write_text(payload, encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
