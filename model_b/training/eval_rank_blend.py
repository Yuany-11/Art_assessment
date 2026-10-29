"""把排序头接到现有分数上，扫描混合强度 alpha，测成对排序是否真的变好。"""
from __future__ import annotations

import csv
import json
import os
import random
import sys
import types
from pathlib import Path

import numpy as np

if "requests" not in sys.modules:
    try:
        import requests  # noqa: F401
    except Exception:
        stub = types.ModuleType("requests")

        class _Err(Exception):
            pass

        stub.Timeout = _Err
        stub.RequestException = _Err
        stub.get = lambda *a, **k: (_ for _ in ()).throw(_Err())
        sys.modules["requests"] = stub

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ROOT = REPO.parents[1]
sys.path.insert(0, str(REPO))

import torch
import torch.nn as nn
from PIL import Image
from torchvision import transforms
from torchvision.models import resnet18

import model_runtime

PENCILS = ROOT / "_downloads" / "Pencils_to_Pixels"
APDD_IMG = ROOT / "data" / "05_apddv2" / "images"
HEAD = ROOT / "logs" / "rank_v1" / "head_pencils_only.npz"
OUT = ROOT / "logs" / "rank_v1" / "blend.json"
SEED = 42
DIMS = ("composition", "color", "modeling", "creativity")
NORM = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
TF = transforms.Compose([transforms.Resize(255), transforms.CenterCrop(224),
                         transforms.ToTensor(), NORM])


def trunk_of():
    st = model_runtime._load()
    return st["trunk"], st["device"]


def feat(trunk, dev, p):
    x = TF(Image.open(p).convert("RGB")).unsqueeze(0).to(dev)
    with torch.no_grad():
        return trunk(x).flatten(1).cpu().numpy()[0].astype(np.float32)


def pairwise(a, c):
    if not a or not c:
        return None
    win = sum(1 for x in a for y in c if x > y) + 0.5 * sum(1 for x in a for y in c if x == y)
    return round(win / (len(a) * len(c)), 3)


def main():
    rng = random.Random(SEED)
    st = model_runtime._load()
    trunk, dev = st["trunk"], st["device"]
    w = np.load(HEAD)["w"]

    rows = list(csv.DictReader(open(PENCILS / "csvs/all_product.csv", encoding="utf-8-sig")))
    ch = [PENCILS / "csvs" / r["filepath"] for r in rows if r["creator"] == "children"]
    ad = [PENCILS / "csvs" / r["filepath"] for r in rows if r["creator"] == "adults"]
    masks = list(APDD_IMG.glob("*.png")) + list(APDD_IMG.glob("*.jpg"))
    rng.shuffle(ch)
    rng.shuffle(ad)
    rng.shuffle(masks)

    # 用全部 Pencils 标定排序分的均值/标准差
    s_all = []
    for p in ch + ad:
        if p.exists():
            f = feat(trunk, dev, p)
            s_all.append(float((f / (np.linalg.norm(f) + 1e-6)) @ w))
    mu, sd = float(np.mean(s_all)), float(np.std(s_all))

    sets = {"children": [p for p in ch[:40] if p.exists()],
            "adults": [p for p in ad[:40] if p.exists()],
            "apdd": [p for p in masks[:40] if p.exists()]}

    uniq = {p for v in sets.values() for p in v}
    ranks = {}
    for p in uniq:
        f = feat(trunk, dev, p)
        ranks[p] = float(np.clip(((f / (np.linalg.norm(f) + 1e-6)) @ w - mu) / (sd + 1e-6), -2.5, 2.5))

    base = {k: [float(np.mean(list(model_runtime.predict(Image.open(p).convert("RGB"))["scores"].values())))
                for p in v] for k, v in sets.items()}

    report = {"head_mu": round(mu, 4), "head_sd": round(sd, 4),
              "head_only_adult_gt_child": pairwise([ranks[p] for p in sets["adults"]],
                                                   [ranks[p] for p in sets["children"]]),
              "head_only_apdd_gt_child": pairwise([ranks[p] for p in sets["apdd"]],
                                                  [ranks[p] for p in sets["children"]]),
              "alpha": {}}
    for alpha in (0.0, 6.0, 10.0, 15.0, 20.0, 30.0):
        adj = {}
        for k, paths in sets.items():
            adj[k] = [float(np.clip(base[k][i] + alpha * ranks[p], 0, 100)) for i, p in enumerate(paths)]
        report["alpha"][str(alpha)] = {
            "adult_gt_child": pairwise(adj["adults"], adj["children"]),
            "apdd_gt_child": pairwise(adj["apdd"], adj["children"]),
            "children_mean": round(float(np.mean(adj["children"])), 1),
            "children_std": round(float(np.std(adj["children"])), 1),
            "apdd_mean": round(float(np.mean(adj["apdd"])), 1),
            "apdd_std": round(float(np.std(adj["apdd"])), 1),
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
