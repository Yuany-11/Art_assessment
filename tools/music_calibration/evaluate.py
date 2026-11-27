#!/usr/bin/env python3
"""音乐参考分校准工具：用同一批样例音频跑指定 rubric，输出逐样本分数。

用法（在 终/arteval-v4/arteval-v4 目录下）：
    ../.venv/Scripts/python.exe ../../tools/music_calibration/evaluate.py \
        --rubric scoring/rubric.default.json \
        --samples ../../tools/music_calibration/samples.json \
        --out ../../tools/music_calibration/before.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rubric", required=True)
    parser.add_argument("--samples", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--weights", default="best_model.pt")
    args = parser.parse_args()

    root = Path.cwd()  # 终/arteval-v4/arteval-v4
    sys.path.insert(0, str(root))

    from training.infer import Tagger
    from training.score import score_file

    tagger = Tagger(Path(args.weights))
    samples = json.loads(Path(args.samples).read_text(encoding="utf-8"))
    results = []
    for sample in samples:
        path = Path(sample["path"])
        if not path.is_absolute():
            path = (root / path).resolve()
        row = {
            "id": sample["id"],
            "label": sample.get("label", ""),
            "human_score": sample.get("humanScore"),
            "human_max": sample.get("humanMax"),
            "file": str(path),
        }
        try:
            result = score_file(
                path, tagger=tagger, rubric_path=Path(args.rubric).resolve()
            )
            row["total"] = result["score"]["total"]
            row["raw_total"] = result["score"].get("rawTotal", result["score"]["total"])
            row["calibrated"] = bool(result["score"].get("calibrated"))
            row["grade"] = result["score"]["grade"]
            row["dimensions"] = {
                d["key"]: d["score"] for d in result["score"]["dimensions"]
            }
            row["penalties"] = [p["reason"] for p in result["score"]["penalties"]]
            row["genre"] = result["predictions"]["genre"]
            row["emotion"] = result["predictions"]["emotion"]
            row["mode"] = result["predictions"]["mode"]
            row["bpm"] = result["predictions"]["bpm"]
            row["dsp"] = {
                k: result["dsp"][k]
                for k in (
                    "duration_s",
                    "key_confidence",
                    "tempo_regularity",
                    "dynamic_range_db",
                    "silence_ratio",
                    "clipping_ratio",
                )
                if k in result["dsp"]
            }
        except Exception as exc:  # noqa: BLE001
            row["error"] = str(exc)
        results.append(row)
        print(f"[{row['id']}] {row.get('total')} {row.get('grade')} {row.get('error', '')}")

    Path(args.out).write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"written {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
