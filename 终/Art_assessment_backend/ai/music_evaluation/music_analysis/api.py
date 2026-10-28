"""零依赖 HTTP 推理接口（Python 标准库实现）。

端点
----
GET  /               服务信息
GET  /ui/            测试前端（静态页面）
GET  /samples/*      内置合成样例与真值清单（供测试前端使用）
GET  /health         健康检查
GET  /schema         返回 JSON Schema
GET  /v1/models      模型能力声明
POST /v1/analyze     音乐分析（raw audio / JSON base64 / multipart）
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import logging
import mimetypes
import re
import uuid
from email.parser import BytesParser
from email.policy import default as email_policy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlsplit

from . import __version__
from .analyzer import (
    BACKEND_NAME,
    MODEL_NAME,
    AnalysisConfig,
    MusicAnalyzer,
)
from .errors import AudioAnalysisError
from .schema import SCHEMA_VERSION, load_schema

LOGGER = logging.getLogger("music_analysis.api")

DEFAULT_MAX_UPLOAD_MB = 50
RAW_AUDIO_TYPES = (
    "application/octet-stream",
    "binary/octet-stream",
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
SAMPLES_DIR = PROJECT_ROOT / "examples" / "samples"
UI_ASSETS = {
    "index.html": "text/html; charset=utf-8",
    "styles.css": "text/css; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
}
SAMPLE_FILE_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*\.(?:wav|wave|flac|ogg|mp3)$", re.IGNORECASE
)


class MusicAnalysisServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address: Tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        analyzer: MusicAnalyzer,
        max_upload_bytes: int,
    ):
        super().__init__(address, handler)
        self.analyzer = analyzer
        self.max_upload_bytes = max_upload_bytes


class MusicAnalysisHandler(BaseHTTPRequestHandler):
    server_version = f"ArtEvalMusic/{__version__}"
    protocol_version = "HTTP/1.1"
    timeout = 60

    # -- HTTP 方法 --------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        accept = self.headers.get("Accept") or ""
        if parsed.path == "/" and "text/html" in accept:
            self._send_redirect("/ui/")
        elif parsed.path == "/ui":
            self._send_redirect("/ui/")
        elif parsed.path == "/ui/":
            self._send_file(FRONTEND_DIR / "index.html", UI_ASSETS["index.html"])
        elif parsed.path.startswith("/ui/"):
            self._send_ui_asset(unquote(parsed.path[len("/ui/"):]))
        elif parsed.path == "/samples/labels.json":
            self._send_file(SAMPLES_DIR / "labels.json", "application/json; charset=utf-8")
        elif parsed.path.startswith("/samples/"):
            self._send_sample(unquote(parsed.path[len("/samples/"):]))
        elif parsed.path == "/":
            self._send_json(
                HTTPStatus.OK,
                {
                    "service": MODEL_NAME,
                    "version": __version__,
                    "endpoints": ["/ui/", "/health", "/schema", "/v1/models", "/v1/analyze"],
                    "ui": "/ui/",
                    "docs": "docs/03_api.md",
                },
            )
        elif parsed.path == "/health":
            self._send_json(
                HTTPStatus.OK,
                {"status": "ok", "model": MODEL_NAME, "version": __version__, "backend": BACKEND_NAME},
            )
        elif parsed.path == "/schema":
            self._send_json(HTTPStatus.OK, load_schema(), content_type="application/schema+json")
        elif parsed.path in ("/v1/models", "/models"):
            self._send_json(
                HTTPStatus.OK,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": "arteval-music-analyzer",
                            "name": MODEL_NAME,
                            "version": __version__,
                            "backend": BACKEND_NAME,
                            "tasks": [
                                "tempo_estimation",
                                "key_detection",
                                "dynamics_analysis",
                                "timbre_analysis",
                                "mood_estimation",
                                "structure_segmentation",
                            ],
                            "output_schema": f"/schema",
                            "schema_version": SCHEMA_VERSION,
                            "input_formats": ["wav", "flac", "ogg", "mp3"],
                        }
                    ],
                },
            )
        else:
            self._send_error_json(HTTPStatus.NOT_FOUND, "not_found", f"未知路径: {parsed.path}")

    # -- 静态资源 ---------------------------------------------------------
    def _send_ui_asset(self, name: str) -> None:
        content_type = UI_ASSETS.get(name)
        path = FRONTEND_DIR / name
        if content_type is None or not path.is_file():
            self._send_error_json(HTTPStatus.NOT_FOUND, "not_found", f"前端资源不存在: {name}")
            return
        self._send_file(path, content_type)

    def _send_sample(self, name: str) -> None:
        if not SAMPLE_FILE_RE.fullmatch(name):
            self._send_error_json(HTTPStatus.NOT_FOUND, "not_found", f"样例不存在: {name}")
            return
        path = (SAMPLES_DIR / name).resolve()
        if path.parent != SAMPLES_DIR.resolve() or not path.is_file():
            self._send_error_json(HTTPStatus.NOT_FOUND, "not_found", f"样例不存在: {name}")
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._send_file(path, content_type)

    def _send_redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("X-Request-Id", getattr(self, "_request_id", "-"))
        self._send_cors_headers()
        self.end_headers()

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self._send_error_json(HTTPStatus.NOT_FOUND, "not_found", f"资源不存在: {path.name}")
            return
        try:
            body = path.read_bytes()
        except OSError:
            LOGGER.exception("读取静态资源失败: %s", path)
            self._send_error_json(
                HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", "静态资源读取失败"
            )
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Request-Id", getattr(self, "_request_id", "-"))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        if parsed.path not in ("/v1/analyze", "/analyze"):
            self._send_error_json(HTTPStatus.NOT_FOUND, "not_found", f"未知路径: {parsed.path}")
            return

        try:
            filename, audio_bytes = self._read_audio_request()
            self._check_size(len(audio_bytes))
            result = self.server.analyzer.analyze_bytes(audio_bytes, filename=filename)  # type: ignore[attr-defined]
        except AudioAnalysisError as exc:
            self._send_error_json(
                HTTPStatus(exc.http_status), exc.code, exc.message
            )
            return
        except Exception:
            LOGGER.exception("分析请求失败")
            self._send_error_json(
                HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", "分析过程发生内部错误"
            )
            return

        pretty = parse_qs(parsed.query).get("pretty", ["0"])[0].lower() in ("1", "true", "yes")
        self._send_json(HTTPStatus.OK, result.to_dict(), pretty=pretty)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_PUT(self) -> None:  # noqa: N802
        self._send_error_json(HTTPStatus.METHOD_NOT_ALLOWED, "method_not_allowed", "仅支持 GET/POST/OPTIONS")

    do_DELETE = do_PUT  # type: ignore[assignment]
    do_PATCH = do_PUT  # type: ignore[assignment]

    # -- 请求解析 ---------------------------------------------------------
    def _read_audio_request(self) -> Tuple[str, bytes]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise AudioAnalysisError("length_required", "缺少 Content-Length", http_status=411)
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise AudioAnalysisError("bad_request", "Content-Length 非法", http_status=400) from exc
        if length <= 0:
            raise AudioAnalysisError("empty_audio", "请求体为空", http_status=422)
        self._check_size(length)

        body = self.rfile.read(length)
        if len(body) != length:
            raise AudioAnalysisError("incomplete_body", "请求体读取不完整", http_status=400)

        content_type = (self.headers.get("Content-Type") or "").strip()
        mime = content_type.split(";")[0].strip().lower()
        query = parse_qs(urlsplit(self.path).query)
        filename = query.get("filename", ["upload"])[0]

        if mime == "application/json":
            return self._parse_json_body(body, filename)
        if mime == "multipart/form-data":
            return self._parse_multipart(content_type, body)
        if mime.startswith("audio/") or mime in RAW_AUDIO_TYPES:
            return filename, body
        raise AudioAnalysisError(
            "unsupported_media_type",
            f"不支持的 Content-Type: {mime or '(空)'}；请使用 audio/*、application/json 或 multipart/form-data",
            http_status=415,
        )

    def _parse_json_body(self, body: bytes, fallback_filename: str) -> Tuple[str, bytes]:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AudioAnalysisError("invalid_json", "请求体不是合法 JSON", http_status=400) from exc
        if not isinstance(payload, dict):
            raise AudioAnalysisError("invalid_json", "JSON 顶层必须是对象", http_status=400)

        encoded = payload.get("audio_base64")
        if not isinstance(encoded, str) or not encoded.strip():
            raise AudioAnalysisError(
                "missing_audio", "缺少 audio_base64 字段", http_status=400
            )
        encoded = encoded.strip()
        if encoded.startswith("data:") and ";base64," in encoded:
            encoded = encoded.split(";base64,", 1)[1]
        try:
            audio = base64.b64decode("".join(encoded.split()), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise AudioAnalysisError("invalid_base64", "audio_base64 不是合法 Base64", http_status=400) from exc

        filename = payload.get("filename") or fallback_filename
        if not isinstance(filename, str):
            raise AudioAnalysisError("bad_request", "filename 必须是字符串", http_status=400)
        return filename, audio

    def _parse_multipart(self, content_type: str, body: bytes) -> Tuple[str, bytes]:
        try:
            header_block = (
                b"Content-Type: "
                + content_type.encode("latin-1", errors="replace")
                + b"\r\nMIME-Version: 1.0\r\n\r\n"
            )
            message = BytesParser(policy=email_policy).parsebytes(header_block + body)
            if not message.is_multipart():
                raise ValueError("不是 multipart 消息")
            fallback: Optional[Tuple[str, bytes]] = None
            for part in message.iter_parts():
                field_name = part.get_param("name", header="content-disposition")
                data = part.get_payload(decode=True)
                if not isinstance(data, bytes):
                    continue
                part_filename = part.get_filename()
                if part_filename is None:
                    continue  # 忽略普通表单字段，只接受文件
                if field_name in ("file", "audio", "audio_file"):
                    return part_filename, data
                if fallback is None:
                    fallback = (part_filename, data)
            if fallback is not None:
                return fallback
        except Exception as exc:  # 解析失败统一转为 400
            raise AudioAnalysisError("invalid_multipart", f"multipart 解析失败: {exc}", http_status=400) from exc
        raise AudioAnalysisError(
            "missing_audio", "multipart 请求中未找到文件字段（file/audio）", http_status=400
        )

    def _check_size(self, size: int) -> None:
        max_bytes = self.server.max_upload_bytes  # type: ignore[attr-defined]
        if size > max_bytes:
            raise AudioAnalysisError(
                "payload_too_large",
                f"请求体 {size} 字节，超过上限 {max_bytes} 字节",
                http_status=413,
            )

    # -- 响应 -------------------------------------------------------------
    def _send_json(
        self,
        status: HTTPStatus,
        payload: Any,
        *,
        pretty: bool = False,
        content_type: str = "application/json",
    ) -> None:
        body = json.dumps(
            payload, ensure_ascii=False, indent=2 if pretty else None, allow_nan=False
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Request-Id", getattr(self, "_request_id", "-"))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(
        self, status: HTTPStatus, code: str, message: str, request_id: Optional[str] = None
    ) -> None:
        self.close_connection = True  # 错误响应后不复用连接，避免未读请求体污染下一请求
        payload = {
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id or getattr(self, "_request_id", "-"),
            }
        }
        self._send_json(status, payload)

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Content-Length")
        self.send_header("Access-Control-Expose-Headers", "X-Request-Id")

    def handle_one_request(self) -> None:
        self._request_id = uuid.uuid4().hex[:16]
        super().handle_one_request()

    def log_message(self, fmt: str, *args: Any) -> None:
        LOGGER.info("%s - %s", self.address_string(), fmt % args)


def create_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    *,
    config: Optional[AnalysisConfig] = None,
    max_upload_mb: int = DEFAULT_MAX_UPLOAD_MB,
) -> MusicAnalysisServer:
    analyzer = MusicAnalyzer(config)
    return MusicAnalysisServer(
        (host, port),
        MusicAnalysisHandler,
        analyzer=analyzer,
        max_upload_bytes=max(1, max_upload_mb) * 1024 * 1024,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ArtEval 音乐分析推理服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8000, help="监听端口（默认 8000）")
    parser.add_argument(
        "--max-upload-mb", type=int, default=DEFAULT_MAX_UPLOAD_MB, help="上传大小上限（MB）"
    )
    parser.add_argument(
        "--max-duration", type=float, default=120.0, help="参与分析的最长音频秒数"
    )
    parser.add_argument("--quiet", action="store_true", help="关闭访问日志")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = AnalysisConfig(max_duration_sec=args.max_duration)
    server = create_server(
        args.host, args.port, config=config, max_upload_mb=args.max_upload_mb
    )
    host, port = server.server_address[:2]
    LOGGER.info("音乐分析服务已启动: http://%s:%s", host, port)
    LOGGER.info("测试前端: http://%s:%s/ui/", host, port)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        LOGGER.info("收到中断信号，正在关闭…")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
