"""模型推理运行时：v3.0 四维 + Pencils 创意头。

懒加载，缺 torch 或权重时抛 ModelUnavailable，由 app.py 回落到启发式基线。
环境变量：
    ART_DISABLE_MODEL=1                            强制走基线（测试用）
    ART_WEIGHT / ART_HEAD / ART_CALIB / ART_ROOT   覆盖路径
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import numpy as np
from PIL import Image

import scoring

HERE = Path(__file__).resolve().parent
ROOT = Path(os.getenv("ART_ROOT", HERE.parents[1]))
CKPT = Path(os.getenv("ART_WEIGHT", ROOT / "weights" / "apddv2_ft" / "best.pt"))
HEAD_PATH = Path(os.getenv("ART_HEAD", ROOT / "weights" / "pencils_creativity" / "head.npz"))
CALIB_PATH = Path(os.getenv("ART_CALIB", HERE / "calibration.json"))
DIMS = scoring.DIMENSIONS


class ModelUnavailable(Exception):
    pass


_lock = threading.Lock()
_state = None


def _disabled() -> bool:
    return os.getenv("ART_DISABLE_MODEL", "").lower() in ("1", "true", "yes")


def loaded_version():
    return _state["version"] if _state else None


def _piecewise(x, xs, ys):
    if x <= xs[0]:
        k = (ys[1] - ys[0]) / (xs[1] - xs[0])
        return max(0.0, ys[0] + (x - xs[0]) * k)
    if x >= xs[-1]:
        k = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
        return min(100.0, ys[-1] + (x - xs[-1]) * k)
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            t = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + t * (ys[i + 1] - ys[i])
    return x


def _calibrate(raw, calib):
    if not calib:
        return list(raw)
    tg = calib["targets"]
    ys = [tg["p05"], tg["p25"], tg["p50"], tg["p75"], tg["p95"]]
    out = []
    for d, v in zip(DIMS, raw):
        a = calib["dims"][d]
        xs = [a["p05"], a["p25"], a["p50"], a["p75"], a["p95"]]
        out.append(round(_piecewise(v, xs, ys), 1))
    return out


def preload() -> bool:
    try:
        _load()
    except ModelUnavailable:
        return False
    return True


def _load():
    global _state
    if _state is not None:
        return _state
    with _lock:
        if _state is not None:
            return _state
        try:
            import torch
            import torch.nn as nn
            from torchvision import transforms
            from torchvision.models import resnet18
        except Exception as exc:
            raise ModelUnavailable(f"torch 不可用: {exc}") from exc
        if not CKPT.exists():
            raise ModelUnavailable(f"缺少权重 {CKPT}")
        ckpt = torch.load(CKPT, map_location="cpu", weights_only=False)
        model = resnet18(weights=None)
        model.fc = nn.Linear(model.fc.in_features, len(DIMS))
        model.load_state_dict(ckpt["state_dict"])
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model.eval().to(device)
        trunk = nn.Sequential(*list(model.children())[:-1]).eval().to(device)

        head = np.load(HEAD_PATH) if HEAD_PATH.exists() else None
        calib = json.loads(CALIB_PATH.read_text(encoding="utf-8")) if CALIB_PATH.exists() else None
        norm = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        tf = transforms.Compose([
            transforms.Resize(int(224 * 1.14)),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            norm,
        ])
        tf_head = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            norm,
        ])
        version = ckpt.get("version", "unknown")
        if head is not None:
            version += "+pencils-creativity-v1"
        _state = {
            "torch": torch, "model": model, "trunk": trunk, "device": device,
            "head": head, "calib": calib, "tf": tf, "tf_head": tf_head, "version": version,
        }
        return _state


def predict(img: Image.Image) -> dict:
    if _disabled():
        raise ModelUnavailable("ART_DISABLE_MODEL")
    st = _load()
    torch = st["torch"]
    with _lock, torch.no_grad():
        x = st["tf"](img).unsqueeze(0).to(st["device"])
        raw = st["model"](x).clamp(0, 100)[0].float().cpu().tolist()
        head = st["head"]
        if head is not None:
            feat = st["trunk"](st["tf_head"](img).unsqueeze(0).to(st["device"])).flatten(1).cpu().numpy()[0]
            creat = float(((feat - head["mu"]) / head["sd"]) @ head["w"] + float(head["ym"][0])) * 25.0
            raw[3] = float(np.clip(creat, 0.0, 100.0))
    raw = [round(float(v), 1) for v in raw]
    cal = _calibrate(raw, st["calib"])
    return {
        "scores": dict(zip(DIMS, cal)),
        "rawScores": dict(zip(DIMS, raw)),
        "flags": scoring.detect_content_flags(img),
        "modelVersion": st["version"],
    }
