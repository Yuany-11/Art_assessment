#!/usr/bin/env python3
"""arteval-v4 本地推理服务（仅标准库 HTTP + torch/libsndfile）。

启动：
    python service.py --port 8100

接口：
    GET  /health   -> 模型状态
    POST /analyze  -> 请求体为音频字节，返回曲风/情绪/调式/BPM 与规则参考分

Django 后端通过 ``AUDIO_TAGGER_URL`` 调用本服务；服务不可用时后端会自动降级，
不影响上传、组卷、判分和成绩等功能。
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_WEIGHTS = ROOT / "best_model.pt"
DEFAULT_RUBRIC = ROOT / "scoring" / "rubric.default.json"
MAX_BYTES = 60 * 1024 * 1024

_tagger = None
_tagger_lock = threading.Lock()
_infer_lock = threading.Lock()


def load_tagger(weights: Path):
    global _tagger
    from training.infer import EMOTIONS, GENRES, Tagger

    tagger = Tagger(weights)
    # 标签顺序错位是“准确率突然变低”最常见的原因：启动时直接自检，
    # 不允许带着错位的类别表静默提供结果。
    if list(tagger.genres) != list(GENRES):
        raise RuntimeError(
            f"checkpoint genre_labels 与 infer.GENRES 不一致：{tagger.genres}"
        )
    if list(tagger.emotions) != list(EMOTIONS):
        raise RuntimeError(
            f"checkpoint emotion_labels 与 infer.EMOTIONS 不一致：{tagger.emotions}"
        )
    _tagger = tagger
    return _tagger


def rubric_path() -> Path:
    """默认规则可被环境变量 ARTEVAL_RUBRIC 覆盖，便于换成审定版本。"""
    from training.score import resolve_rubric_path

    return resolve_rubric_path(os.getenv("ARTEVAL_RUBRIC") or DEFAULT_RUBRIC)


def health_payload() -> dict:
    return {
        "status": "ok" if _tagger is not None else "loading",
        "arch": getattr(_tagger, "arch", None),
        "epoch": getattr(_tagger, "model_epoch", None),
        "weights": getattr(_tagger, "weights", None),
        "device": str(getattr(_tagger, "device", "cpu")),
    }


def analyze_bytes(content: bytes, suffix: str) -> dict:
    from training.score import score_file

    handle, path = tempfile.mkstemp(suffix=suffix or ".audio")
    try:
        with os.fdopen(handle, "wb") as output:
            output.write(content)
        # 模型是 eval 模式且无状态，串行化推理可避免 CPU 线程竞争。
        with _infer_lock:
            result = score_file(path, tagger=_tagger, rubric_path=rubric_path())
        result["arch"] = getattr(_tagger, "arch", "v4")
        return result
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


class Handler(BaseHTTPRequestHandler):
    server_version = "arteval-tagger/1.0"

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in {"", "/health"}:
            self._send(200, health_payload())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/analyze":
            self._send(404, {"error": "not found"})
            return
        if _tagger is None:
            self._send(503, {"error": "模型尚未加载完成"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            self._send(400, {"error": "请求体为空"})
            return
        if length > MAX_BYTES:
            self._send(413, {"error": "音频文件超过 60 MB"})
            return

        content = self.rfile.read(length)
        name = self.headers.get("X-File-Name") or "audio"
        suffix = Path(name).suffix.lower() or ".audio"
        try:
            result = analyze_bytes(content, suffix)
        except Exception as exc:  # noqa: BLE001 - 统一返回给后端记录
            traceback.print_exc()
            self._send(500, {"error": f"分析失败：{exc}"})
            return
        self._send(200, result)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[tagger] {self.address_string()} {fmt % args}")


def main() -> int:
    parser = argparse.ArgumentParser(description="arteval-v4 audio tagging service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--weights", default=str(DEFAULT_WEIGHTS))
    args = parser.parse_args()

    weights = Path(args.weights)
    if not weights.is_file():
        raise SystemExit(f"checkpoint not found: {weights}")
    print(f"loading {weights} ...", flush=True)
    load_tagger(weights)
    print(f"ready on http://{args.host}:{args.port} ({health_payload()})", flush=True)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopping", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
