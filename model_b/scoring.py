"""美术作品四维启发式评分基线。

无标注数据场景下的客观指标量化，输出不做训练模型声明。
"""
from __future__ import annotations

import io
import ipaddress
import math
import os
import socket
from typing import Dict, Tuple
from urllib.parse import urlparse

import numpy as np
import requests
from PIL import Image, ImageOps

MAX_BYTES = 10 * 1024 * 1024
ALLOW_PRIVATE = os.getenv("ALLOW_PRIVATE_URLS", "false").lower() in ("1", "true", "yes")
DEFAULT_RUBRIC = {"composition": 25.0, "color": 25.0, "modeling": 25.0, "creativity": 25.0}
DIMENSIONS = ("composition", "color", "modeling", "creativity")
MODEL_VERSION = "art-baseline-v0.1.0"
INFER_TIMEOUT_SECONDS = 60
CONTENT_MIN_SIDE = 200


class ScoringError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


def _is_private_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise ScoringError(400, "图片地址无法解析")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return True
    return False


def fetch_image(url: str) -> Image.Image:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ScoringError(400, "imageUrl 必须是 http/https 地址")
    if not ALLOW_PRIVATE and _is_private_host(parsed.hostname):
        raise ScoringError(400, "不允许访问内网地址")

    try:
        with requests.get(url, stream=True, timeout=10, allow_redirects=False) as resp:
            if resp.status_code != 200:
                raise ScoringError(400, f"图片下载失败：HTTP {resp.status_code}")
            content_type = resp.headers.get("Content-Type", "")
            if content_type and not content_type.startswith("image/"):
                raise ScoringError(400, "目标不是图片资源")
            buf = io.BytesIO()
            size = 0
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ScoringError(413, "图片超过 10MB 限制")
                buf.write(chunk)
    except requests.Timeout:
        raise ScoringError(500, "图片下载超时")
    except requests.RequestException:
        raise ScoringError(500, "图片下载失败")
    return load_image(buf.getvalue())


def load_image(raw: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
    except Exception:
        raise ScoringError(400, "无法解析图片内容")
    longest = max(img.size)
    if longest > 1024:
        ratio = 1024 / longest
        img = img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))), Image.BILINEAR)
    return img


def _clip01(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0))


def _gradients(gray: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    gx = np.zeros_like(gray)
    gy = np.zeros_like(gray)
    gx[:, 1:-1] = gray[:, 2:] - gray[:, :-2]
    gy[1:-1, :] = gray[2:, :] - gray[:-2, :]
    return gx, gy


def _laplacian_var(gray: np.ndarray) -> float:
    lap = (
        -4 * gray
        + np.roll(gray, 1, 0)
        + np.roll(gray, -1, 0)
        + np.roll(gray, 1, 1)
        + np.roll(gray, -1, 1)
    )
    return float(lap.var())


def _hue_entropy(hue: np.ndarray) -> float:
    hist, _ = np.histogram(hue, bins=18, range=(0, 180))
    total = hist.sum()
    if total == 0:
        return 0.0
    p = hist / total
    p = p[p > 0]
    return float(-(p * np.log(p)).sum() / math.log(18))


def analyze(img: Image.Image) -> Dict[str, float]:
    rgb = np.asarray(img, dtype=np.float32)
    gray = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2])
    gx, gy = _gradients(gray)
    mag = np.hypot(gx, gy)

    grad_mean = float(mag.mean())
    edge_density = float((mag > 30).mean())
    lap_var = _laplacian_var(gray)
    content = _clip01(grad_mean / 8.0)

    h, w = gray.shape
    cell_h, cell_w = h // 3, w // 3
    energy = mag * mag
    cells = []
    for i in range(3):
        for j in range(3):
            cells.append(float(energy[i * cell_h:(i + 1) * cell_h, j * cell_w:(j + 1) * cell_w].sum()) + 1e-6)
    left = cells[0] + cells[3] + cells[6]
    right = cells[2] + cells[5] + cells[8]
    top = cells[0] + cells[1] + cells[2]
    bottom = cells[6] + cells[7] + cells[8]
    balance_h = 1 - abs(left - right) / (left + right)
    balance_v = 1 - abs(top - bottom) / (top + bottom)

    flipped = gray[:, ::-1]
    symmetry = _clip01(1 - float(np.abs(gray - flipped).mean()) / 80.0)
    ys, xs = np.nonzero(mag > mag.mean())
    if len(xs):
        cx = float(xs.mean()) / max(1, w - 1)
        cy = float(ys.mean()) / max(1, h - 1)
    else:
        cx = cy = 0.5
    center_score = _clip01(1 - math.hypot(cx - 0.5, cy - 0.5) / 0.707)
    composition_raw = 0.35 * balance_h + 0.25 * balance_v + 0.2 * symmetry + 0.2 * center_score
    composition = 100 * composition_raw * content

    maxc = rgb.max(axis=2)
    minc = rgb.min(axis=2)
    sat = np.where(maxc > 0, (maxc - minc) / np.maximum(maxc, 1e-6), 0.0)
    sat_mean = float(sat.mean())
    contrast = float(gray.std())
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    rg = r - g
    yb = 0.5 * (r + g) - b
    colorfulness = float(
        math.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * math.sqrt(rg.mean() ** 2 + yb.mean() ** 2)
    )
    hue = np.asarray(img.convert("HSV"), dtype=np.uint8)[:, :, 0]
    hue_entropy = _hue_entropy(hue)
    occupied_hues = int((np.bincount(hue.ravel() // 10, minlength=18) > 10).sum())

    color_score = 100 * (
        0.3 * _clip01((sat_mean - 0.02) / 0.55)
        + 0.25 * _clip01((contrast - 5) / 60)
        + 0.25 * _clip01((colorfulness - 3) / 90)
        + 0.2 * _clip01((hue_entropy - 0.1) / 0.85)
    )

    lap_score = _clip01((math.log1p(lap_var) - math.log1p(5)) / (math.log1p(2000) - math.log1p(5)))
    edge_score = _clip01(edge_density / 0.08)
    detail_score = _clip01(grad_mean / 25)
    modeling = 100 * (0.45 * lap_score + 0.3 * edge_score + 0.25 * detail_score)

    hue_div = _clip01((occupied_hues / 18 - 0.05) / 0.85)
    asym = _clip01((1 - symmetry - 0.05) / 0.8)
    complexity = _clip01(edge_density / 0.1)
    creativity = 100 * (0.4 * hue_div + 0.3 * asym + 0.3 * complexity) * content

    return {
        "composition": round(float(np.clip(composition, 0, 100)), 1),
        "color": round(float(np.clip(color_score, 0, 100)), 1),
        "modeling": round(float(np.clip(modeling, 0, 100)), 1),
        "creativity": round(float(np.clip(creativity, 0, 100)), 1),
        "_sat": sat_mean,
        "_contrast": contrast,
        "_colorfulness": colorfulness,
        "_lap_var": lap_var,
        "_edge_density": edge_density,
        "_hue_entropy": hue_entropy,
        "_grad_mean": grad_mean,
        "_content": content,
    }


def detect_content_flags(img: Image.Image) -> list:
    """识别非绘画内容：文字文档、界面截图、空白图、分辨率过低。

    文字与截图共同特征是横竖直线多，用轴对齐强边缘占比判断；
    白底黑字再叠加无彩色 + 大面积近白 + 缺中间灰。
    """
    flags = []
    a = np.asarray(img, dtype=np.uint8)
    if a.size == 0:
        return ["blank"]
    mx = a.max(axis=2).astype(np.int16)
    mn = a.min(axis=2).astype(np.int16)
    sat = float((mx - mn).mean())
    gray = a.mean(axis=2)
    white = float((gray > 240).mean())
    mid = float(((gray > 80) & (gray < 200)).mean())
    if sat < 12 and white > 0.55 and mid < 0.18:
        flags.append("document")
    else:
        g = np.asarray(
            img.convert("L").resize((min(512, img.width), min(512, img.height))),
            dtype=np.float32,
        )
        gx = np.abs(np.diff(g, axis=1))[:, :-1]
        gy = np.abs(np.diff(g, axis=0))[:-1, :]
        h, w = min(gx.shape[0], gy.shape[0]), min(gx.shape[1], gy.shape[1])
        gx, gy = gx[:h, :w], gy[:h, :w]
        strong = (gx + gy) > 24
        if strong.mean() > 0.01:
            axis = (gx > 3 * gy + 1) | (gy > 3 * gx + 1)
            if float(axis[strong].mean()) > 0.78:
                flags.append("screenshot")
    if min(img.size) < CONTENT_MIN_SIDE:
        flags.append("low_res")
    return flags


def sanity_check(metrics: Dict[str, float]) -> list:
    """美术结果校验：分数与图像客观指标严重矛盾时告警，供业务层复核。"""
    out = []
    if metrics["color"] >= 80 and metrics["_sat"] < 0.08:
        out.append("色彩分偏高但画面饱和度很低")
    if metrics["composition"] >= 80 and metrics["_content"] < 0.2:
        out.append("构图分偏高但画面内容强度低")
    if metrics["modeling"] >= 80 and metrics["_lap_var"] < 10:
        out.append("造型分偏高但画面清晰度低")
    if metrics["creativity"] >= 80 and metrics["_hue_entropy"] < 0.3:
        out.append("创意分偏高但色彩与构成变化少")
    if metrics["color"] <= 20 and metrics["_sat"] > 0.5:
        out.append("色彩分偏低但画面饱和度较高")
    return out


def level_of(total: float) -> str:
    if total >= 90:
        return "excellent"
    if total >= 75:
        return "good"
    if total >= 60:
        return "pass"
    return "fail"


def _band(score: float) -> str:
    if score >= 85:
        return "excellent"
    if score >= 75:
        return "good"
    if score >= 60:
        return "pass"
    return "fail"


_COMMENTS = {
    "composition": {
        "excellent": "主体位置明确，画面重心稳定，疏密关系处理得当。",
        "good": "主体较突出，画面整体平衡，局部边缘略显拥挤。",
        "pass": "构图基本成立，画面重心略有偏移，可加强主次关系。",
        "fail": "画面元素分布松散或过于拥挤，主体不够明确。",
    },
    "color": {
        "excellent": "色彩鲜明且层次丰富，冷暖关系协调。",
        "good": "色彩较鲜明，整体色调基本协调。",
        "pass": "色彩表现一般，可增加明暗与饱和层次。",
        "fail": "色彩偏灰或过于单调，缺少层次与对比。",
    },
    "modeling": {
        "excellent": "形体清晰，细节刻画充分，边缘交代明确。",
        "good": "细节清晰度较好，局部结构可再加强。",
        "pass": "细节清晰度一般，形体边缘略模糊。",
        "fail": "画面偏模糊，细节与结构信息不足。",
    },
    "creativity": {
        "excellent": "色彩与构成有较强个人表达，变化丰富。",
        "good": "有一定个人表达，构成较为常规。",
        "pass": "表达方式较常见，可尝试更多变化。",
        "fail": "构成与用色较为单一，创意表现不足。",
    },
}

_IMPROVEMENTS = {
    "composition": "调整主体位置与画面疏密关系",
    "color": "加强色彩层次与冷暖对比",
    "modeling": "加强细节刻画与形体边缘",
    "creativity": "尝试更丰富的构成与用色变化",
}


def score_image(img: Image.Image, rubric: Dict[str, float] | None = None) -> Dict:
    rubric = dict(rubric or DEFAULT_RUBRIC)
    metrics = analyze(img)
    total = sum(metrics[d] * rubric[d] for d in DIMENSIONS) / 100.0
    total = round(float(total), 2)
    flags = detect_content_flags(img)
    warnings = sanity_check(metrics)
    if "low_res" in flags:
        warnings.append(f"图片分辨率偏低（短边 {min(img.size)}px），分数参考性下降")

    if any(f in flags for f in ("document", "screenshot", "blank")):
        level = "not_applicable"
        dimension_comments = {d: "未检测到绘画内容，该维度不适用。" for d in DIMENSIONS}
        strengths: list = []
        improvements: list = []
        summary = "未检测到绘画内容（文字/截图/空白），四维评分不适用，不应作为作品成绩。"
    else:
        level = level_of(total)
        dimension_comments = {d: _COMMENTS[d][_band(metrics[d])] for d in DIMENSIONS}
        ordered = sorted(DIMENSIONS, key=lambda d: metrics[d], reverse=True)
        strengths = [f"{_zh(d)}表现较好" for d in ordered[:2]]
        improvements = [_IMPROVEMENTS[d] for d in reversed(ordered[-2:])]
        band_zh = {"excellent": "优秀", "good": "良好", "pass": "合格", "fail": "待提升"}
        summary = (
            f"作品整体完成度{band_zh[level] if level in band_zh else '待提升'}，"
            f"{_zh(ordered[0])}表现相对突出，{_zh(ordered[-1])}仍有提升空间。"
        )

    return {
        "scores": {**{d: metrics[d] for d in DIMENSIONS}, "total": total},
        "level": level,
        "dimensionComments": dimension_comments,
        "strengths": strengths,
        "improvements": improvements,
        "summary": summary,
        "contentFlags": flags,
        "warnings": warnings,
    }


_ZH = {"composition": "构图", "color": "色彩", "modeling": "造型", "creativity": "创意"}


def _zh(dim: str) -> str:
    return _ZH[dim]


def validate_rubric(rubric: Dict[str, float] | None) -> Dict[str, float]:
    if not rubric:
        return dict(DEFAULT_RUBRIC)
    if set(rubric.keys()) != set(DIMENSIONS):
        raise ScoringError(400, "rubric 必须包含 composition/color/modeling/creativity 四项")
    values = {}
    for key, value in rubric.items():
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise ScoringError(400, f"rubric.{key} 必须是数字")
        if v < 0:
            raise ScoringError(400, f"rubric.{key} 不能为负数")
        values[key] = v
    if abs(sum(values.values()) - 100) > 0.01:
        raise ScoringError(400, "rubric 权重总和必须为 100")
    return values
