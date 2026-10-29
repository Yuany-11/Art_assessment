"""初中/小学画域偏差检查：用当前 v4.0 集成给 KIDO 的 Primary/Secondary 作品打分，看分布。

KIDO 没有美术质量标注，这里只看"现有模型给初中生画打多少分"，不做任何真值对比。
用法（CPU，避免占训练 GPU）：
  CUDA_VISIBLE_DEVICES= ART_WEIGHT=<seed1.pt>,<seed2.pt> python check_domain_kido.py --n 300
"""
from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ROOT = REPO.parents[1]
KIDO = ROOT / "data" / "09_kido" / "Dataset" / "Images" / "Education"

if "requests" not in sys.modules:
    try:
        import requests  # noqa: F401
    except Exception:
        stub = types.ModuleType("requests")

        class _Err(Exception):
            pass

        stub.Timeout = _Err
        stub.RequestException = _Err
        stub.get = lambda *a, k=None: (_ for _ in ()).throw(_Err())
        sys.modules["requests"] = stub

sys.path.insert(0, str(REPO))
import model_runtime  # noqa: E402

DIMS = ("composition", "color", "modeling", "creativity")


def sample(group: str, n: int):
    paths = sorted(p for p in KIDO.rglob("*.jpg") if p.parent.name == group)
    if n and len(paths) > n:
        step = len(paths) / n
        paths = [paths[int(i * step)] for i in range(n)]
    return paths


def summarize(scores):
    arr = np.asarray([[s[d] for d in DIMS] + [float(np.mean([s[d] for d in DIMS]))] for s in scores])
    out = {}
    for i, name in enumerate(DIMS + ("total",)):
        col = arr[:, i]
        out[name] = {
            "mean": round(float(col.mean()), 2),
            "std": round(float(col.std()), 2),
            "p05": round(float(np.percentile(col, 5)), 1),
            "p50": round(float(np.percentile(col, 50)), 1),
            "p95": round(float(np.percentile(col, 95)), 1),
            "fail_rate": round(float((col < 60).mean()), 3),
            "excellent_rate": round(float((col >= 90).mean()), 3),
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300, help="每组最多几张")
    ap.add_argument("--out", default=str(ROOT / "logs" / "domain_kido" / "report.json"))
    args = ap.parse_args()

    model_runtime.preload()
    model_version = model_runtime.loaded_version()
    print("model:", model_version, flush=True)

    report = {"model_version": model_version, "n_per_group": args.n, "groups": {}}
    for group in ("Primary", "Secondary"):
        paths = sample(group, args.n)
        scores = []
        for p in paths:
            try:
                scores.append(model_runtime.predict(Image.open(p).convert("RGB"))["scores"])
            except Exception:
                continue
        report["groups"][group] = {"n": len(scores), **summarize(scores)}
        print(group, report["groups"][group], flush=True)

    if len(report["groups"]) == 2:
        a = report["groups"]["Secondary"]["total"]["mean"]
        b = report["groups"]["Primary"]["total"]["mean"]
        report["gap_secondary_minus_primary"] = round(a - b, 2)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", out, flush=True)


if __name__ == "__main__":
    main()
