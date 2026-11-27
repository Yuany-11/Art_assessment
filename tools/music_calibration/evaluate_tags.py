#!/usr/bin/env python3
"""音频标签回归：对比“中间 30 秒”与“多段聚合”的曲风/情绪/BPM 结果。

CSV 列：id,path,genre,emotion,mode,bpm
- genre/emotion 可留空；bpm 可留空。
- 有标签时输出准确率/误差；没有标签时只输出预测，不能声称准确率。

示例：
    python evaluate_tags.py --samples tag_samples.csv --mode both --out tags.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "arteval-v4" / "arteval-v4"
sys.path.insert(0, str(ROOT))

import librosa  # noqa: E402
import numpy as np  # noqa: E402

from training.infer import Tagger  # noqa: E402
from training.score import predict_windows  # noqa: E402
from training.features import SR, features_from_audio  # noqa: E402


def legacy_predict(tagger: Tagger, path: Path) -> dict:
    """旧逻辑：只取中间 30 秒。"""
    duration = float(librosa.get_duration(path=str(path)))
    offset = max(0.0, (duration - 30.0) / 2.0) if duration > 30.0 else 0.0
    y, _ = librosa.load(str(path), sr=SR, mono=True, offset=offset, duration=30.0)
    mel, chroma = features_from_audio(y)
    out = tagger.predict_arrays(mel, chroma)
    return {
        "genre": out["genre_top1"],
        "emotion": out["emotion"],
        "mode": out["mode"],
        "bpm": out["bpm"],
        "genreConfidence": out["genre_confidence"],
        "emotionConfidence": out["emotion_confidence"],
        "segments": 1,
    }


def windows_predict(tagger: Tagger, path: Path) -> dict:
    duration = float(librosa.get_duration(path=str(path)))
    out = predict_windows(tagger, path, duration)
    return {
        "genre": out["genre_top1"],
        "emotion": out["emotion"],
        "mode": out["mode"],
        "bpm": out["bpm"],
        "genreConfidence": out["genre_confidence"],
        "emotionConfidence": out["emotion_confidence"],
        "segments": out.get("segments", 1),
    }


def summarize(rows: list[dict], key: str) -> dict:
    labeled = [row for row in rows if row.get(f"human_{key}")]
    if not labeled:
        return {"labeled": 0, "note": "无人工标签，无法计算准确率"}
    if key == "bpm":
        errors = [
            abs(float(row["prediction"][key]) - float(row["human_bpm"]))
            for row in labeled
            if row["prediction"].get(key) is not None
        ]
        return {
            "labeled": len(labeled),
            "bpmMAE": round(float(np.mean(errors)), 2) if errors else None,
        }
    hits = sum(
        1
        for row in labeled
        if str(row["prediction"].get(key)).lower()
        == str(row.get(f"human_{key}")).lower()
    )
    return {"labeled": len(labeled), "accuracy": round(hits / len(labeled), 4)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", required=True, help="CSV: id,path,genre,emotion,mode,bpm")
    parser.add_argument("--weights", default=str(ROOT / "best_model.pt"))
    parser.add_argument("--mode", choices=["legacy", "windows", "both"], default="both")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    tagger = Tagger(args.weights)
    rows = []
    with Path(args.samples).open(encoding="utf-8-sig", newline="") as handle:
        for item in csv.DictReader(handle):
            path = Path(item["path"])
            if not path.is_absolute():
                path = Path(args.samples).resolve().parent / path
            record = {
                "id": item.get("id") or path.stem,
                "path": str(path),
                "human_genre": (item.get("genre") or "").strip(),
                "human_emotion": (item.get("emotion") or "").strip(),
                "human_mode": (item.get("mode") or "").strip(),
                "human_bpm": (item.get("bpm") or "").strip(),
                "duration": round(float(librosa.get_duration(path=str(path))), 2),
            }
            if args.mode in {"legacy", "both"}:
                record["legacy"] = legacy_predict(tagger, path)
            if args.mode in {"windows", "both"}:
                record["windows"] = windows_predict(tagger, path)
            rows.append(record)

    report = {"samples": rows, "mode": args.mode}
    for mode in ("legacy", "windows"):
        subset = [
            {**row, "prediction": row[mode]}
            for row in rows
            if mode in row
        ]
        if subset:
            report[mode] = {
                "genre": summarize(subset, "genre"),
                "emotion": summarize(subset, "emotion"),
                "mode": summarize(subset, "mode"),
                "bpm": summarize(subset, "bpm"),
            }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
