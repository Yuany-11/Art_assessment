"""训练轻量排序头（M2-lite）：冻结 v3.0 主干特征，只学“谁更好”。

数据：Pencils 成人 vs 儿童（真分组）+ APDDv2 官方高分 vs 低分（真分数）。
产物：weights/rank_v1/head.npz、logs/rank_v1/metrics.json，不覆盖任何现有权重。
"""
from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ROOT = REPO.parents[1]

import torch
import torch.nn as nn
from PIL import Image
from torchvision import transforms
from torchvision.models import resnet18

CKPT = ROOT / "weights" / "apddv2_ft" / "best.pt"
PENCILS = ROOT / "_downloads" / "Pencils_to_Pixels"
APDD_IMG = ROOT / "data" / "05_apddv2" / "images"
APDD_CSV = ROOT / "data" / "05_apddv2" / "APDDv2-10023.csv"
OUT_DIR = ROOT / "weights" / "rank_v1"
LOG_DIR = ROOT / "logs" / "rank_v1"
SEED = 42

DIMS = ("composition", "color", "modeling", "creativity")
NORM = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
TF = transforms.Compose([transforms.Resize(255), transforms.CenterCrop(224),
                         transforms.ToTensor(), NORM])


def build_backbone():
    ckpt = torch.load(CKPT, map_location="cpu", weights_only=False)
    m = resnet18(weights=None)
    m.fc = nn.Linear(m.fc.in_features, len(DIMS))
    m.load_state_dict(ckpt["state_dict"])
    trunk = nn.Sequential(*list(m.children())[:-1]).eval()
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return trunk.to(dev), dev


def feats(trunk, dev, paths):
    out = {}
    with torch.no_grad():
        for p in paths:
            try:
                img = Image.open(p).convert("RGB")
            except Exception:
                continue
            x = TF(img).unsqueeze(0).to(dev)
            out[p] = trunk(x).flatten(1).cpu().numpy()[0].astype(np.float32)
    return out


def main():
    rng = random.Random(SEED)
    trunk, dev = build_backbone()

    rows = list(csv.DictReader(open(PENCILS / "csvs/all_product.csv", encoding="utf-8-sig")))
    adults = [PENCILS / "csvs" / r["filepath"] for r in rows if r["creator"] == "adults"]
    children = [PENCILS / "csvs" / r["filepath"] for r in rows if r["creator"] == "children"]
    adults = [p for p in adults if p.exists()]
    children = [p for p in children if p.exists()]
    rng.shuffle(adults)
    rng.shuffle(children)

    apdd_high, apdd_low = [], []
    for r in csv.DictReader(open(APDD_CSV, encoding="gbk", errors="ignore")):
        p = APDD_IMG / r["filename"]
        if not p.exists():
            continue
        try:
            t = float(r["Total aesthetic score"])
        except (TypeError, ValueError):
            continue
        if t >= 80:
            apdd_high.append(p)
        elif t < 50:
            apdd_low.append(p)
    rng.shuffle(apdd_high)
    rng.shuffle(apdd_low)
    apdd_high, apdd_low = apdd_high[:400], apdd_low[:400]

    all_paths = adults + children + apdd_high + apdd_low
    print(f"images: pencils {len(adults)}+{len(children)}, apdd {len(apdd_high)}+{len(apdd_low)}", flush=True)
    F = feats(trunk, dev, all_paths)
    print(f"features: {len(F)}", flush=True)

    def pairs(pos, neg, n):
        pos = [p for p in pos if p in F]
        neg = [p for p in neg if p in F]
        out = []
        for _ in range(n):
            out.append((F[rng.choice(pos)] - F[rng.choice(neg)], 1))
        return out

    data = pairs(adults, children, 12000) + pairs(apdd_high, apdd_low, 12000)
    rng.shuffle(data)
    X = np.stack([d[0] for d in data])
    y = np.array([d[1] for d in data])
    X = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-6)

    # 简单逻辑回归（numpy 实现，避免额外依赖）：P(y=1|x) = sigmoid(w·x)
    w = np.zeros(X.shape[1], dtype=np.float32)
    lr, l2 = 0.5, 1e-3
    for _ in range(300):
        z = X @ w
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
        g = X.T @ (p - y) / len(y) + l2 * w
        w -= lr * g
    acc = float(((X @ w > 0) == (y == 1)).mean())

    # 留出评估：按图片分组，不参与训练的半边
    hold_ad = adults[len(adults) // 2:]
    hold_ch = children[len(children) // 2:]
    hold_hi = apdd_high[len(apdd_high) // 2:]
    hold_lo = apdd_low[len(apdd_low) // 2:]
    Fh = feats(trunk, dev, [p for p in hold_ad + hold_ch + hold_hi + hold_lo if p not in F])

    def pw(pos, neg, n=3000):
        pos = [p for p in pos if p in F or p in Fh]
        neg = [p for p in neg if p in F or p in Fh]
        if not pos or not neg:
            return None
        win = 0
        for _ in range(n):
            a, b = rng.choice(pos), rng.choice(neg)
            fa = F.get(a, Fh.get(a))
            fb = F.get(b, Fh.get(b))
            if fa is None or fb is None:
                continue
            da = float(((fa / (np.linalg.norm(fa) + 1e-6)) @ w))
            db = float(((fb / (np.linalg.norm(fb) + 1e-6)) @ w))
            win += da > db
        return round(win / n, 4)

    metrics = {
        "train_pairs": int(len(y)),
        "train_acc": round(acc, 4),
        "heldout_adult_gt_child": pw(hold_ad, hold_ch),
        "heldout_apdd_high_gt_low": pw(hold_hi, hold_lo),
        "images": {"pencils": len(adults) + len(children), "apdd": len(apdd_high) + len(apdd_low)},
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    np.savez(OUT_DIR / "head.npz", w=w.astype(np.float32))
    (OUT_DIR / "说明.txt").write_text(
        "rank-v1：冻结 v3.0 主干特征的线性排序头（成人>儿童、APDD 高分>低分）。\n"
        "输出为相对质量分 w·f，不是 0-100 绝对分；只用于排序/修正，需 ART_RANK=1 启用。\n",
        encoding="utf-8")
    (LOG_DIR / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    sys.exit(main())
