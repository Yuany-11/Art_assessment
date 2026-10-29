"""诊断：排序头到底能不能区分 Pencils 成人/儿童（真正留出验证）。"""
from __future__ import annotations

import csv
import json
import random
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
OUT = ROOT / "logs" / "rank_v1"
SEED = 42
DIMS = ("composition", "color", "modeling", "creativity")
NORM = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
TF = transforms.Compose([transforms.Resize(255), transforms.CenterCrop(224),
                         transforms.ToTensor(), NORM])


def main():
    rng = random.Random(SEED)
    ckpt = torch.load(CKPT, map_location="cpu", weights_only=False)
    m = resnet18(weights=None)
    m.fc = nn.Linear(m.fc.in_features, len(DIMS))
    m.load_state_dict(ckpt["state_dict"])
    trunk = nn.Sequential(*list(m.children())[:-1]).eval()
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    trunk = trunk.to(dev)

    rows = list(csv.DictReader(open(PENCILS / "csvs/all_product.csv", encoding="utf-8-sig")))
    adults = [PENCILS / "csvs" / r["filepath"] for r in rows if r["creator"] == "adults"]
    children = [PENCILS / "csvs" / r["filepath"] for r in rows if r["creator"] == "children"]
    adults = [p for p in adults if p.exists()]
    children = [p for p in children if p.exists()]

    feats = {}
    with torch.no_grad():
        for p in adults + children:
            try:
                x = TF(Image.open(p).convert("RGB")).unsqueeze(0).to(dev)
            except Exception:
                continue
            feats[p] = trunk(x).flatten(1).cpu().numpy()[0].astype(np.float32)

    rng.shuffle(adults)
    rng.shuffle(children)
    a_tr, a_te = adults[: int(len(adults) * 0.7)], adults[int(len(adults) * 0.7):]
    c_tr, c_te = children[: int(len(children) * 0.7)], children[int(len(children) * 0.7):]

    def make(pos, neg, n):
        X, y = [], []
        for _ in range(n):
            a, b = rng.choice(pos), rng.choice(neg)
            if a in feats and b in feats:
                X.append(feats[a] - feats[b])
                y.append(1)
        return np.stack(X), np.array(y, dtype=np.float32)

    def fit(X, y, iters=400, lr=0.5, l2=1e-3):
        X = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-6)
        w = np.zeros(X.shape[1], dtype=np.float32)
        for _ in range(iters):
            p = 1.0 / (1.0 + np.exp(-np.clip(X @ w, -30, 30)))
            w -= lr * (X.T @ (p - y) / len(y) + l2 * w)
        return w

    Xtr, ytr = make(a_tr, c_tr, 20000)
    w = fit(Xtr, ytr)

    def acc(pos, neg, n=5000):
        win = ok = 0
        for _ in range(n):
            a, b = rng.choice(pos), rng.choice(neg)
            if a not in feats or b not in feats:
                continue
            fa, fb = feats[a], feats[b]
            sa = float((fa / (np.linalg.norm(fa) + 1e-6)) @ w)
            sb = float((fb / (np.linalg.norm(fb) + 1e-6)) @ w)
            ok += 1
            win += sa > sb
        return round(win / max(ok, 1), 4)

    res = {
        "n_train": len(a_tr) + len(c_tr),
        "n_test": len(a_te) + len(c_te),
        "train_acc": acc(a_tr, c_tr, 2000),
        "test_adult_gt_child": acc(a_te, c_te),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez(OUT / "head_pencils_only.npz", w=w)
    (OUT / "metrics_pencils_only.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
