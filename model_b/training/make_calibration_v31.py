"""生成 v3.1 试评校准：学生代理分布 + 创意头收缩系数。

不训练模型，只做两件事：
1. 用 APDDv2 + Pencils 儿童画的原始预测分位，生成更宽的校准表（候选文件）。
2. 在 Pencils 儿童画上拟合创意收缩系数 k，降低创意分抖动。

输出：
    model_b/calibration_v31.json
    logs/calibration_v31/report.json
"""
from __future__ import annotations

import csv
import json
import random
import sys
import types
from pathlib import Path

import numpy as np

# scoring.py 只在函数内部用 requests；GPU 环境未装时做最小 stub
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

from PIL import Image  # noqa: E402

import model_runtime  # noqa: E402

DIMS = ("composition", "color", "modeling", "creativity")
SEED = 42
TARGETS = {"p05": 40, "p25": 62, "p50": 72, "p75": 82, "p95": 93}
PENCILS = ROOT / "_downloads" / "Pencils_to_Pixels"
APDD_IMG = ROOT / "data" / "05_apddv2" / "images"
APDD_CSV = ROOT / "data" / "05_apddv2" / "APDDv2-10023.csv"
OUT_CAL = REPO / "calibration_v31.json"
OUT_LOG = ROOT / "logs" / "calibration_v31" / "report.json"


def raw_predict(path: Path):
    img = Image.open(path).convert("RGB")
    return model_runtime.predict(img)["rawScores"]


def sample(paths, n, rng):
    paths = list(paths)
    rng.shuffle(paths)
    return paths[:n]


def quantiles(values):
    v = np.asarray(values, dtype=float)
    return {("p05" if q == 5 else f"p{q}"): float(np.percentile(v, q)) for q in (5, 25, 50, 75, 95)}


def apply_cal(raw, calib):
    out = []
    for d in DIMS:
        v = raw[d]
        xs = [calib["dims"][d]["p05" if q == 5 else f"p{q}"] for q in (5, 25, 50, 75, 95)]
        ys = [calib["targets"]["p05" if q == 5 else f"p{q}"] for q in (5, 25, 50, 75, 95)]
        out.append(round(model_runtime._piecewise(v, xs, ys), 1))
    return out


def band(x):
    return "excellent" if x >= 90 else "good" if x >= 75 else "pass" if x >= 60 else "fail"


def load_apdd_labels():
    rows = []
    with open(APDD_CSV, encoding="gbk", errors="ignore") as fh:
        for r in csv.DictReader(fh):
            name = r["filename"]
            vals = {}
            if r.get("Layout and composition"):
                vals["composition"] = float(r["Layout and composition"]) * 10
            if r.get("Color"):
                vals["color"] = float(r["Color"]) * 10
            parts = [float(r[k]) * 10 for k in ("Space and perspective", "Details and texture") if r.get(k)]
            if parts:
                vals["modeling"] = sum(parts) / len(parts)
            if r.get("Creativity"):
                vals["creativity"] = float(r["Creativity"]) * 10
            if vals:
                rows.append((name, vals))
    return rows


def main():
    rng = random.Random(SEED)
    model_runtime.preload()
    print("model version:", model_runtime.loaded_version(), flush=True)

    pencils_rows = list(csv.DictReader(open(PENCILS / "csvs/all_product.csv", encoding="utf-8-sig")))
    ch = [r for r in pencils_rows if r["creator"] == "children"]
    ad = [r for r in pencils_rows if r["creator"] == "adults"]
    ch_paths = [PENCILS / "csvs" / r["filepath"] for r in ch]
    ad_paths = [PENCILS / "csvs" / r["filepath"] for r in ad]

    apdd_paths = sample(APDD_IMG.glob("*.png"), 300, rng)
    apdd_paths += sample(APDD_IMG.glob("*.jpg"), 200, rng)
    ref_raw = {d: [] for d in DIMS}
    for p in apdd_paths + sample(ch_paths, 300, rng):
        if not p.exists():
            continue
        try:
            raw = raw_predict(p)
        except Exception:
            continue
        for d in DIMS:
            ref_raw[d].append(raw[d])

    dims = {d: quantiles(v) for d, v in ref_raw.items()}
    calib = {
        "source": "v3.1 试评口径：APDDv2 500 张 + Pencils 儿童画 300 张的 v3.0 原始预测分位",
        "target_basis": "目标分布为试评假设，不是官方规定；等级线 90/75/60 按教育部 2015 办法",
        "targets": TARGETS,
        "dims": dims,
        "creativity_shrink": 1.0,
    }
    OUT_CAL.write_text(json.dumps(calib, ensure_ascii=False, indent=2), encoding="utf-8")
    print("calibration written:", OUT_CAL, flush=True)

    # 创意收缩系数：在 Pencils 儿童画上拟合 pred -> y 的最优缩放
    xs, ys = [], []
    for p, r in zip(ch_paths, ch):
        if not p.exists():
            continue
        try:
            raw = raw_predict(p)
        except Exception:
            continue
        xs.append(raw["creativity"])
        ys.append(float(r["creativity2"]))
    xs = np.asarray(xs); ys = np.asarray(ys) * 25.0
    k_opt = float(np.cov(ys, xs)[0, 1] / np.var(xs)) if np.var(xs) > 0 else 1.0
    mean_pred = float(xs.mean())
    sweep = {}
    for k in (0.3, 0.5, 0.7, 1.0, round(k_opt, 3)):
        pred = np.clip(mean_pred + k * (xs - mean_pred), 0, 100)
        sweep[str(k)] = round(float(np.mean(np.abs(pred - ys))), 3)
    pred_opt = np.clip(mean_pred + k_opt * (xs - mean_pred), 0, 100)
    report = {
        "n_pencils_children": int(len(xs)),
        "creativity_raw_std": float(xs.std()),
        "creativity_target_std": float(ys.std()),
        "k_opt": k_opt,
        "mae_by_k_0_100": sweep,
        "mae_before_0_100": float(np.mean(np.abs(xs - ys))),
        "mae_opt_0_100": float(np.mean(np.abs(pred_opt - ys))),
        "pearson_before": float(np.corrcoef(xs, ys)[0, 1]),
        "npz": str(OUT_LOG.parent / "creativity_arrays.npz"),
    }
    OUT_LOG.parent.mkdir(parents=True, exist_ok=True)
    np.savez(OUT_LOG.parent / "creativity_arrays.npz", xs=xs, ys=ys)
    calib["creativity_shrink"] = round(k_opt, 4)
    OUT_CAL.write_text(json.dumps(calib, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_LOG.parent.mkdir(parents=True, exist_ok=True)

    # ---- 校准效果评估：APDDv2 标注 + Pencils 成人/儿童排序 ----
    old_calib = json.loads((REPO / "calibration.json").read_text(encoding="utf-8"))
    labels = load_apdd_labels()
    rng2 = random.Random(SEED + 1)
    rng2.shuffle(labels)
    evals = []
    for name, lab in labels:
        p = APDD_IMG / name
        if not p.exists():
            continue
        try:
            raw = raw_predict(p)
        except Exception:
            continue
        evals.append((raw, lab))
        if len(evals) >= 300:
            break

    def metrics(calib_obj, shrink_k):
        errs, bands, n = [], [], 0
        for raw, lab in evals:
            pred = apply_cal(raw, calib_obj)
            n += 1
            for d, v in zip(DIMS, pred):
                if d in lab:
                    errs.append(abs(v - lab[d]))
                    bands.append(band(v) == band(lab[d]))
        return {
            "mae": round(float(np.mean(errs)), 3),
            "band_acc": round(float(np.mean(bands)), 4),
            "n": n,
        }

    eval_report = {
        "apddv2": {"old": metrics(old_calib, 1.0), "v31": metrics(calib, k_opt)},
    }

    def overall(raw, calib_obj):
        p = apply_cal(raw, calib_obj)
        return float(np.mean(p))

    def pairwise(calib_obj, n=100):
        a, c = [], []
        for paths, out in ((sample(ad_paths, n, rng), a), (sample(ch_paths, n, rng), c)):
            for p in paths:
                if not p.exists():
                    continue
                try:
                    out.append(overall(raw_predict(p), calib_obj))
                except Exception:
                    pass
        if not a or not c:
            return None
        wins = sum(1 for x in a for y in c if x > y) + 0.5 * sum(1 for x in a for y in c if x == y)
        return round(wins / (len(a) * len(c)), 3)

    eval_report["pencils_adult_gt_child"] = {
        "old": pairwise(old_calib),
        "v31": pairwise(calib),
    }
    report["eval"] = eval_report
    OUT_LOG.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
