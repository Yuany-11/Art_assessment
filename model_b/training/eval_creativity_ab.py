"""创意头 A/B：在 Pencils 真实人工评分上比较「模型创意维」vs「Pencils 创意头」。

用法：
  python eval_creativity_ab.py --out logs/creativity_ab/head_on.json              # 带头
  python eval_creativity_ab.py --out logs/creativity_ab/head_off.json --no-head   # 不带头
权重由 ART_WEIGHT 控制，与线上一致。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ROOT = REPO.parents[1]
PENCILS = ROOT / "_downloads" / "Pencils_to_Pixels"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-head", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="每种 creator 最多几张，0=全部")
    args = ap.parse_args()

    if args.no_head:
        os.environ["ART_HEAD"] = str(ROOT / "_no_head_disabled.npz")
    sys.path.insert(0, str(REPO))
    import types
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
    import model_runtime

    model_runtime.preload()
    print("model:", model_runtime.loaded_version(), flush=True)

    rows = list(csv.DictReader(open(PENCILS / "csvs/all_product.csv", encoding="utf-8-sig")))
    out = {}
    for creator in ("children", "adults"):
        part = [r for r in rows if r["creator"] == creator]
        if args.limit:
            part = part[:args.limit]
        preds, gts = [], []
        for r in part:
            p = PENCILS / "csvs" / r["filepath"]
            if not p.exists():
                continue
            try:
                raw = model_runtime.predict(Image.open(p).convert("RGB"))["rawScores"]
            except Exception:
                continue
            preds.append(float(raw["creativity"]))
            gts.append(float(r["creativity2"]) * 25.0)
        if not preds:
            continue
        x = np.asarray(preds)
        y = np.asarray(gts)
        valid = (y > 0) & (y <= 100)
        x, y = x[valid], y[valid]
        out[creator] = {
            "n": int(len(x)),
            "mae_0_100": round(float(np.mean(np.abs(x - y))), 3),
            "pearson": round(float(np.corrcoef(x, y)[0, 1]), 4) if len(x) > 2 else None,
            "pred_mean": round(float(x.mean()), 2),
            "gt_mean": round(float(y.mean()), 2),
            "pred_std": round(float(x.std()), 2),
            "gt_std": round(float(y.std()), 2),
            "sat_100_rate": round(float((x >= 99.9).mean()), 3),
        }
        print(creator, out[creator], flush=True)

    if "children" in out and "adults" in out:
        out["gap_adult_minus_child"] = round(out["adults"]["pred_mean"] - out["children"]["pred_mean"], 2)
    out["head"] = not args.no_head
    out["model_version"] = model_runtime.loaded_version()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
