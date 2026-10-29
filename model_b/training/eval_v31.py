"""评估 v3.1 接入效果：区分度、成人/儿童排序、TTA 稳定性。

只读权重做推理，不改任何产物；输出 logs/calibration_v31/eval_v31.json
"""
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

from PIL import Image, ImageEnhance  # noqa: E402

import model_runtime  # noqa: E402

DIMS = ("composition", "color", "modeling", "creativity")
SEED = 42
PENCILS = ROOT / "_downloads" / "Pencils_to_Pixels"
APDD_IMG = ROOT / "data" / "05_apddv2" / "images"
OUT = ROOT / "logs" / "calibration_v31" / "eval_v31.json"
OLD_CAL = json.loads((REPO / "calibration.json").read_text(encoding="utf-8"))
NEW_CAL = json.loads((REPO / "calibration_v31.json").read_text(encoding="utf-8"))


def apply_cal(raw, calib):
    tg = calib["targets"]
    ys = [tg["p05"], tg["p25"], tg["p50"], tg["p75"], tg["p95"]]
    out = []
    for d in DIMS:
        a = calib["dims"][d]
        xs = [a["p05"], a["p25"], a["p50"], a["p75"], a["p95"]]
        out.append(model_runtime._piecewise(raw[d], xs, ys))
    return out


def raw_of(path):
    return model_runtime.predict(Image.open(path).convert("RGB"))["rawScores"]


def mean_total(raw, calib):
    return float(np.mean(apply_cal(raw, calib)))


def pairwise(a, c):
    if not a or not c:
        return None
    wins = sum(1 for x in a for y in c if x > y) + 0.5 * sum(1 for x in a for y in c if x == y)
    return round(wins / (len(a) * len(c)), 3)


def set_tta(on):
    os.environ["ART_TTA"] = "1" if on else "0"


def main():
    rng = random.Random(SEED)
    model_runtime.preload()
    rows = list(csv.DictReader(open(PENCILS / "csvs/all_product.csv", encoding="utf-8-sig")))
    ch = [PENCILS / "csvs" / r["filepath"] for r in rows if r["creator"] == "children"]
    ad = [PENCILS / "csvs" / r["filepath"] for r in rows if r["creator"] == "adults"]
    masks = list(APDD_IMG.glob("*.png")) + list(APDD_IMG.glob("*.jpg"))
    rng.shuffle(ch)
    rng.shuffle(ad)
    rng.shuffle(masks)
    ch, ad, masks = ch[:40], ad[:40], masks[:40]

    report = {"n": {"children": len(ch), "adults": len(ad), "apdd": len(masks)}, "modes": {}}
    for mode, tta in (("tta_off", False), ("tta_on", True)):
        set_tta(tta)
        raws = {"children": [], "adults": [], "apdd": []}
        for key, paths in (("children", ch), ("adults", ad), ("apdd", masks)):
            for p in paths:
                if p.exists():
                    try:
                        raws[key].append(raw_of(p))
                    except Exception:
                        pass
        block = {}
        for calib_name, calib in (("old", OLD_CAL), ("v31", NEW_CAL)):
            totals = {k: [mean_total(r, calib) for r in v] for k, v in raws.items()}
            block[calib_name] = {
                "mean": {k: round(float(np.mean(v)), 2) for k, v in totals.items()},
                "std": {k: round(float(np.std(v)), 2) for k, v in totals.items()},
                "adult_gt_child": pairwise(totals["adults"], totals["children"]),
                "apdd_gt_child": pairwise(totals["apdd"], totals["children"]),
                "dim_std_children": {
                    d: round(float(np.std([apply_cal(r, calib)[i] for r in raws["children"]])), 2)
                    for i, d in enumerate(DIMS)
                },
            }
        block["raw_dim_std_children"] = {
            d: round(float(np.std([r[d] for r in raws["children"]])), 2) for d in DIMS
        }
        report["modes"][mode] = block

    # 稳定性：同一张图做轻微扰动，看总分歧标准差
    set_tta(False)
    probe = (ch[:3] + ad[:3])
    probe = [p for p in probe if p.exists()]
    perturbed = []
    for p in probe:
        img = Image.open(p).convert("RGB")
        w, h = img.size
        for i in range(5):
            v = img
            if i == 1:
                v = img.rotate(3, resample=Image.BILINEAR, fillcolor="white")
            elif i == 2:
                v = img.rotate(-3, resample=Image.BILINEAR, fillcolor="white")
            elif i == 3:
                v = ImageEnhance.Brightness(img).enhance(0.95)
            elif i == 4:
                v = img.crop((int(w * 0.03), int(h * 0.03), w - int(w * 0.03), h - int(h * 0.03)))
            perturbed.append((p.name, v))
    stability = {}
    for mode, tta in (("tta_off", False), ("tta_on", True)):
        set_tta(tta)
        by_img = {}
        for name, img in perturbed:
            try:
                by_img.setdefault(name, []).append(mean_total(model_runtime.predict(img)["rawScores"], NEW_CAL))
            except Exception:
                pass
        stds = [float(np.std(v)) for v in by_img.values() if len(v) > 1]
        stability[mode] = round(float(np.mean(stds)), 3) if stds else None
    report["stability_std_same_image"] = stability

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
