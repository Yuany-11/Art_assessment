"""在带 ground truth 的清单上评测音乐分析模型。

用法：
    python examples/generate_test_samples.py --out examples/samples
    python scripts/evaluate.py --manifest examples/samples/labels.json --out-dir reports

输出：
    reports/evaluation_report.json
    reports/evaluation_report.md

说明：默认清单是**合成数据**，只用于回归与管线自检；真实模型选型请使用
公开数据集或自有标注集，并保持同一评测协议。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from music_analysis.analyzer import AnalysisConfig, MusicAnalyzer  # noqa: E402
from music_analysis.schema import validate_result  # noqa: E402


def tempo_octave_error(predicted: Optional[float], truth: Optional[float]) -> Optional[float]:
    """返回八度等价意义下的最小相对误差（0.04 = 4%）。"""
    if not predicted or not truth:
        return None
    candidates = [predicted, predicted * 2.0, predicted / 2.0]
    return min(abs(candidate - truth) / truth for candidate in candidates)


def summarize(records: List[Dict[str, Any]], latencies: List[float]) -> Dict[str, Any]:
    usable = [r for r in records if r["usable"]]
    musical = [r for r in usable if not r["silence_case"]]

    def rate(key: str, subset: Optional[List[Dict[str, Any]]] = None) -> Optional[float]:
        rows = subset if subset is not None else musical
        values = [r[key] for r in rows if r.get(key) is not None]
        return round(float(np.mean(values)), 4) if values else None

    tempo_errors = [r["tempo_rel_error"] for r in musical if r["tempo_rel_error"] is not None]
    boundary_errors = [
        r["boundary_error_sec"] for r in musical if r["boundary_error_sec"] is not None
    ]
    schema_ok = [r["schema_valid"] for r in records]
    quality_ok = [r["quality_check"] for r in records]

    return {
        "n_records": len(records),
        "n_usable": len(usable),
        "schema_valid_rate": round(float(np.mean(schema_ok)), 4) if schema_ok else None,
        "tempo_accuracy_4pct": rate("tempo_ok"),
        "tempo_median_rel_error": round(float(np.median(tempo_errors)), 4) if tempo_errors else None,
        "key_accuracy": rate("key_ok"),
        "mode_accuracy": rate("mode_ok"),
        "mood_accuracy": rate("mood_ok"),
        "energy_accuracy": rate("energy_ok"),
        "structure_count_accuracy": rate("sections_ok"),
        "structure_boundary_accuracy_2_5s": rate("boundary_ok"),
        "structure_median_boundary_error_sec": (
            round(float(np.median(boundary_errors)), 3) if boundary_errors else None
        ),
        "quality_case_accuracy": round(float(np.mean(quality_ok)), 4) if quality_ok else None,
        "latency_ms_p50": round(float(np.percentile(latencies, 50)), 1) if latencies else None,
        "latency_ms_p95": round(float(np.percentile(latencies, 95)), 1) if latencies else None,
        "latency_ms_mean": round(float(np.mean(latencies)), 1) if latencies else None,
    }


def evaluate(manifest_path: Path, out_dir: Path, max_duration: float) -> Dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    samples_dir = manifest_path.parent
    analyzer = MusicAnalyzer(AnalysisConfig(max_duration_sec=max_duration))

    records: List[Dict[str, Any]] = []
    latencies: List[float] = []

    for entry in manifest.get("samples", []):
        path = samples_dir / entry["file"]
        result = analyzer.analyze_file(path)
        payload = result.to_dict()
        schema_errors = validate_result(payload)
        latency_ms = float(payload["model"]["runtime_ms"])
        latencies.append(latency_ms)

        summary = payload["summary"]
        structure = payload["structure"]
        usable = bool(payload["quality"]["usable"])
        silence_case = not bool(entry.get("usable", True))
        predicted_key = f"{payload['tonality']['key']} {payload['tonality']['mode']}" if payload["tonality"]["key"] else None
        expected_key = (
            f"{entry['key']} {entry['mode']}" if entry.get("key") and entry.get("mode") else None
        )
        tempo_error = tempo_octave_error(summary["tempo_bpm"], entry.get("bpm"))

        expected_sections = entry.get("sections")
        sections_ok = structure["section_count"] == expected_sections

        boundary_error = None
        boundary_ok = None
        expected_boundary = entry.get("section_boundary_sec")
        if expected_boundary is not None and structure["section_count"] >= 2:
            internal = [section["start_sec"] for section in structure["sections"][1:]]
            boundary_error = min(abs(value - expected_boundary) for value in internal)
            boundary_ok = boundary_error <= 2.5

        expected_flags = set(entry.get("flags", []))
        actual_flags = set(payload["quality"]["flags"])
        quality_check = (
            usable == bool(entry.get("usable", True)) and expected_flags.issubset(actual_flags)
        )

        energy_evaluable = usable and "clipped_audio" not in actual_flags
        records.append(
            {
                "file": entry["file"],
                "duration_sec": payload["audio"]["duration_sec"],
                "usable": usable,
                "silence_case": silence_case,
                "expected": {
                    "key": expected_key,
                    "tempo_bpm": entry.get("bpm"),
                    "mood": entry.get("mood"),
                    "energy": entry.get("energy"),
                    "sections": expected_sections,
                    "section_boundary_sec": expected_boundary,
                },
                "predicted": {
                    "key": predicted_key,
                    "tempo_bpm": summary["tempo_bpm"],
                    "mood": summary["mood"],
                    "energy": summary["energy"],
                    "sections": structure["section_count"],
                    "warnings": payload["warnings"],
                    "quality_flags": payload["quality"]["flags"],
                },
                "tempo_rel_error": round(tempo_error, 4) if tempo_error is not None else None,
                "tempo_ok": (tempo_error is not None and tempo_error <= 0.04),
                "key_ok": predicted_key == expected_key if expected_key else None,
                "mode_ok": (
                    payload["tonality"]["mode"] == entry.get("mode")
                    if entry.get("mode")
                    else None
                ),
                "mood_ok": (
                    summary["mood"] == entry.get("mood") if entry.get("mood") else None
                ),
                "energy_ok": (
                    summary["energy"] == entry.get("energy")
                    if entry.get("energy") and energy_evaluable
                    else None
                ),
                "sections_ok": sections_ok,
                "boundary_error_sec": round(boundary_error, 3) if boundary_error is not None else None,
                "boundary_ok": boundary_ok,
                "schema_valid": not schema_errors,
                "schema_errors": schema_errors,
                "quality_check": quality_check,
                "runtime_ms": round(latency_ms, 1),
            }
        )

    summary = summarize(records, latencies)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "model": {
            "name": "ArtEval Music Analyzer",
            "backend": "dsp-librosa-v1",
            "max_duration_sec": max_duration,
        },
        "dataset": manifest.get("dataset"),
        "manifest": str(manifest_path),
        "disclaimer": manifest.get("notes"),
        "summary": summary,
        "per_sample": records,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "evaluation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "evaluation_report.md").write_text(render_markdown(report), encoding="utf-8")
    return report


def render_markdown(report: Dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# 音乐分析模型评测报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 数据集：{report['dataset']}（{s['n_records']} 个样例）",
        f"- 模型：{report['model']['name']} / {report['model']['backend']}",
        f"- 声明：{report['disclaimer']}",
        "",
        "## 汇总指标",
        "",
        "| 指标 | 结果 |",
        "| --- | --- |",
        f"| Schema 合法率 | {_pct(s['schema_valid_rate'])} |",
        f"| 速度准确率（±4%，允许八度） | {_pct(s['tempo_accuracy_4pct'])} |",
        f"| 速度中位相对误差 | {_pct(s['tempo_median_rel_error'])} |",
        f"| 调性准确率 | {_pct(s['key_accuracy'])} |",
        f"| 调式准确率 | {_pct(s['mode_accuracy'])} |",
        f"| 情绪准确率 | {_pct(s['mood_accuracy'])} |",
        f"| 能量准确率（排除削波样例） | {_pct(s['energy_accuracy'])} |",
        f"| 段落数准确率 | {_pct(s['structure_count_accuracy'])} |",
        f"| 段落边界准确率（±2.5s） | {_pct(s['structure_boundary_accuracy_2_5s'])} |",
        f"| 边界中位误差 | {s['structure_median_boundary_error_sec']} s |",
        f"| 质量标记命中率 | {_pct(s['quality_case_accuracy'])} |",
        f"| 推理延迟 P50 / P95 | {s['latency_ms_p50']} / {s['latency_ms_p95']} ms |",
        "",
        "## 逐样例结果",
        "",
        "| 文件 | 期望（调性/速度/情绪/能量） | 预测（调性/速度/情绪/能量） | 段落 | 边界误差 | Schema |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for record in report["per_sample"]:
        expected = record["expected"]
        predicted = record["predicted"]
        lines.append(
            "| {file} | {ek} / {et} / {em} / {ee} | {pk} / {pt} / {pm} / {pe} | {ps} | {be} | {sv} |".format(
                file=record["file"],
                ek=expected["key"] or "—",
                et=_num(expected["tempo_bpm"]),
                em=expected["mood"] or "—",
                ee=expected["energy"] or "—",
                pk=predicted["key"] or "—",
                pt=_num(predicted["tempo_bpm"]),
                pm=predicted["mood"] or "—",
                pe=predicted["energy"] or "—",
                ps=predicted["sections"],
                be="—" if record["boundary_error_sec"] is None else f"{record['boundary_error_sec']}s",
                sv="✓" if record["schema_valid"] else "✗",
            )
        )
    lines.extend(
        [
            "",
            "## 解读与限制",
            "",
            "- 样例为程序合成的可控音乐片段，**不能**代表真实音乐分布；绝对指标仅用于回归。",
            "- 速度指标允许 ±4% 与八度等价（60↔120 BPM 的常见歧义）。",
            "- 情绪/能量是启发式估计，不是医疗或心理测量结论；真实场景需人工标注校准。",
            "- 结构分段假设 4/4 拍、小节对齐；自由速度、复合拍号与无鼓音乐可能失效。",
            "- 削波样例不参与能量准确率统计（削波会抬高响度，干扰能量判断）。",
        ]
    )
    return "\n".join(lines) + "\n"


def _pct(value: Optional[float]) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _num(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:g}"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="评测音乐分析模型")
    parser.add_argument(
        "--manifest", default="examples/samples/labels.json", help="带 ground truth 的 JSON 清单"
    )
    parser.add_argument("--out-dir", default="reports", help="报告输出目录")
    parser.add_argument("--max-duration", type=float, default=120.0)
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        print(
            f"找不到清单 {manifest_path}。请先运行：\n"
            "  python examples/generate_test_samples.py --out examples/samples",
            file=sys.stderr,
        )
        return 2

    report = evaluate(manifest_path, Path(args.out_dir), args.max_duration)
    s = report["summary"]
    print("评测完成：")
    for key in (
        "schema_valid_rate",
        "tempo_accuracy_4pct",
        "key_accuracy",
        "mode_accuracy",
        "mood_accuracy",
        "energy_accuracy",
        "structure_count_accuracy",
        "structure_boundary_accuracy_2_5s",
        "quality_case_accuracy",
        "latency_ms_p50",
        "latency_ms_p95",
    ):
        print(f"  {key}: {s[key]}")
    print(f"报告：{Path(args.out_dir) / 'evaluation_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
