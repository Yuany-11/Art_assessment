"""命令行入口。

用法：
    python -m music_analysis.cli analyze path/to/audio.wav --out result.json
    python -m music_analysis.cli serve --port 8000
    python -m music_analysis.cli schema
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

from . import __version__
from .analyzer import AnalysisConfig, MusicAnalyzer
from .errors import AudioAnalysisError
from .schema import load_schema


def _cmd_analyze(args: argparse.Namespace) -> int:
    config = AnalysisConfig(
        max_duration_sec=args.max_duration,
        include_structure=not args.no_structure,
    )
    analyzer = MusicAnalyzer(config)
    try:
        result = analyzer.analyze_file(args.audio, filename=args.filename)
    except AudioAnalysisError as exc:
        print(f"错误 [{exc.code}]: {exc.message}", file=sys.stderr)
        return 2

    payload = result.to_json(indent=None if args.compact else args.indent)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload + "\n", encoding="utf-8")
        print(f"已写入 {out_path}")
    else:
        print(payload)

    if result.warnings:
        print(f"警告: {', '.join(result.warnings)}", file=sys.stderr)
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from . import api

    argv = [
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--max-upload-mb",
        str(args.max_upload_mb),
        "--max-duration",
        str(args.max_duration),
    ]
    if args.quiet:
        argv.append("--quiet")
    return api.main(argv)


def _cmd_schema(args: argparse.Namespace) -> int:
    payload = json.dumps(load_schema(), ensure_ascii=False, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload + "\n", encoding="utf-8")
        print(f"已写入 {out_path}")
    else:
        print(payload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="music-analysis",
        description="ArtEval 离线音乐分析模型（节奏/调性/动态/音色/情绪/结构）",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="分析单个音频文件并输出 JSON")
    analyze.add_argument("audio", help="音频文件路径（wav/flac/ogg/mp3）")
    analyze.add_argument("--out", "-o", help="结果 JSON 输出路径；缺省输出到 stdout")
    analyze.add_argument("--filename", help="写入结果中的文件名（默认取路径文件名）")
    analyze.add_argument("--indent", type=int, default=2, help="JSON 缩进（默认 2）")
    analyze.add_argument("--compact", action="store_true", help="输出单行紧凑 JSON")
    analyze.add_argument(
        "--max-duration", type=float, default=120.0, help="最长分析秒数（默认 120）"
    )
    analyze.add_argument("--no-structure", action="store_true", help="跳过曲式结构分析")
    analyze.set_defaults(func=_cmd_analyze)

    serve = sub.add_parser("serve", help="启动 HTTP 推理服务")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--max-upload-mb", type=int, default=50)
    serve.add_argument("--max-duration", type=float, default=120.0)
    serve.add_argument("--quiet", action="store_true")
    serve.set_defaults(func=_cmd_serve)

    schema = sub.add_parser("schema", help="输出结构化结果的 JSON Schema")
    schema.add_argument("--out", "-o", help="Schema 输出路径；缺省输出到 stdout")
    schema.set_defaults(func=_cmd_schema)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
