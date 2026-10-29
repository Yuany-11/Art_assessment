"""模型推理运行时：v4.0 四维（2-seed 集成）。

懒加载，缺 torch 或权重时抛 ModelUnavailable，由 app.py 回落到启发式基线。
环境变量：
    ART_DISABLE_MODEL=1                            强制走基线（测试用）
    ART_WEIGHT / ART_HEAD / ART_CALIB / ART_ROOT   覆盖路径；ART_WEIGHT 支持逗号分隔多权重做集成
    ART_HEAD=...                                   只有显式设置才启用创意头；默认不加载
    ART_TTA=0                                      关闭三路 TTA（默认开）
    ART_SHRINK=1                                   开启创意缩放（默认关）
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
_ckpt_env = os.getenv("ART_WEIGHT", "").strip()
CKPT_PATHS = ([Path(x.strip()) for x in _ckpt_env.split(",") if x.strip()]
              if _ckpt_env else [ROOT / "weights" / "apddv2_ft" / "best.pt"])
_head_env = os.getenv("ART_HEAD", "").strip()
HEAD_PATH = Path(_head_env) if _head_env else None
CALIB_PATH = Path(os.getenv("ART_CALIB", HERE / "calibration_v32.json"))
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
    # 分位点可能重复（如创意头饱和打满），跳过零宽区间避免除零
    if x <= xs[0]:
        j = next((i for i in range(1, len(xs)) if xs[i] != xs[0]), None)
        if j is None:
            return ys[0]
        k = (ys[j] - ys[0]) / (xs[j] - xs[0])
        return max(0.0, ys[0] + (x - xs[0]) * k)
    if x >= xs[-1]:
        j = next((i for i in range(len(xs) - 2, -1, -1) if xs[i] != xs[-1]), None)
        if j is None:
            return ys[-1]
        k = (ys[-1] - ys[j]) / (xs[-1] - xs[j])
        return min(100.0, ys[-1] + (x - xs[-1]) * k)
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            if xs[i + 1] == xs[i]:
                return ys[i + 1]
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
            from torchvision.models import resnet18, resnet34, resnet50
        except Exception as exc:
            raise ModelUnavailable(f"torch 不可用: {exc}") from exc
        missing = [p for p in CKPT_PATHS if not p.exists()]
        if missing:
            raise ModelUnavailable(f"缺少权重 {missing[0]}")
        ckpts = [torch.load(p, map_location="cpu", weights_only=False) for p in CKPT_PATHS]
        builders = {"resnet18": resnet18, "resnet34": resnet34, "resnet50": resnet50}
        backbones = {c.get("backbone", "resnet18") for c in ckpts}
        sizes = {int(c.get("img", 224)) for c in ckpts}
        if len(backbones) != 1 or len(sizes) != 1:
            raise ModelUnavailable("集成要求骨干与输入尺寸一致")
        backbone = backbones.pop()
        if backbone not in builders:
            raise ModelUnavailable(f"不支持的骨干 {backbone}")
        img_size = sizes.pop()
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        models = []
        for c in ckpts:
            m = builders[backbone](weights=None)
            m.fc = nn.Linear(m.fc.in_features, len(DIMS))
            m.load_state_dict(c["state_dict"])
            models.append(m.eval().to(device))
        model = models[0]
        trunks = [nn.Sequential(*list(m.children())[:-1]).eval().to(device) for m in models]
        trunk = trunks[0]

        head = np.load(HEAD_PATH) if HEAD_PATH and HEAD_PATH.exists() else None
        calib = json.loads(CALIB_PATH.read_text(encoding="utf-8")) if CALIB_PATH.exists() else None
        norm = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        tf = transforms.Compose([
            transforms.Resize(int(img_size * 1.14)),
            transforms.CenterCrop(img_size),
            transforms.ToTensor(),
            norm,
        ])
        tf_head = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            norm,
        ])
        # 创意头基于 v3.0 的 ResNet18 512 维特征训练，换骨干后维度不兼容，改用模型自身创意维
        if head is not None and backbone != "resnet18":
            head = None
        version = ckpts[0].get("version", "unknown")
        if len(ckpts) > 1:
            version += f"+ens{len(ckpts)}"
        if head is not None:
            version += "+pencils-creativity-v1"
        calib_src = str(calib.get("source", "")) if calib else ""
        if calib_src.startswith("v3.2"):
            version += "+calib-v32"
        elif calib_src.startswith("v3.1"):
            version += "+calib-v31"
        _state = {
            "torch": torch, "model": model, "models": models,
            "trunk": trunk, "trunks": trunks, "device": device,
            "head": head, "calib": calib, "tf": tf, "tf_head": tf_head, "version": version,
        }
        return _state


def _tta_on() -> bool:
    return os.getenv("ART_TTA", "1").lower() not in ("0", "false", "no")


def _variants(img: Image.Image):
    w, h = img.size
    out = [img, img.transpose(Image.FLIP_LEFT_RIGHT)]
    dx, dy = int(w * 0.06), int(h * 0.06)
    if dx > 1 and dy > 1:
        out.append(img.crop((dx, dy, w - dx, h - dy)))
    return out


def predict(img: Image.Image) -> dict:
    if _disabled():
        raise ModelUnavailable("ART_DISABLE_MODEL")
    st = _load()
    torch = st["torch"]
    variants = _variants(img) if _tta_on() else [img]
    with _lock, torch.no_grad():
        acc = None
        acc_creat = 0.0
        head = st["head"]
        models, trunks = st["models"], st["trunks"]
        for v in variants:
            x = st["tf"](v).unsqueeze(0).to(st["device"])
            for m in models:
                pred = m(x).clamp(0, 100)[0].float().cpu().numpy()
                acc = pred if acc is None else acc + pred
            if head is not None:
                xh = st["tf_head"](v).unsqueeze(0).to(st["device"])
                for tr in trunks:
                    feat = tr(xh).flatten(1).cpu().numpy()[0]
                    acc_creat += float(((feat - head["mu"]) / head["sd"]) @ head["w"] + float(head["ym"][0])) * 25.0
        n = len(variants) * len(models)
        raw = (acc / n).tolist()
        if head is not None:
            raw[3] = float(np.clip(acc_creat / n, 0.0, 100.0))
    calib = st["calib"]
    if calib and os.getenv("ART_SHRINK", "0").lower() in ("1", "true", "yes"):
        k, m = calib.get("creativity_shrink"), calib.get("creativity_mean")
        if k and m is not None:
            raw[3] = float(np.clip(m + k * (raw[3] - m), 0.0, 100.0))
    raw = [round(float(v), 1) for v in raw]
    cal = _calibrate(raw, calib)
    return {
        "scores": dict(zip(DIMS, cal)),
        "rawScores": dict(zip(DIMS, raw)),
        "flags": scoring.detect_content_flags(img),
        "modelVersion": st["version"],
    }
