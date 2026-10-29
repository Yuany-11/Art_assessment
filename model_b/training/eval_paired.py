"""独立复核：读两份逐图预测文件，重算 MAE 与配对 bootstrap（不依赖训练侧代码）。

支持两种格式：
1. 长表：file,dim,raw,cal,label,mask（训练侧 preds_test.csv 用的就是这种）
2. 宽表：uid + gt_composition/pred_composition 等每维一列

用法：
    python eval_paired.py --a logs/e0_baseline_raw/preds_test.csv \
                          --b logs/exp_ensemble2/preds_test.csv --boot 1000
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

import numpy as np

DIMS = ["composition", "color", "modeling", "creativity"]
ID_KEYS = ["file", "uid", "filename", "name", "path", "image"]
GT_PREFIX = ["gt_", "true_", "label_", "target_"]


def key_of(v):
    return Path(v).name if ("/" in v or "\\" in v) else v


def load(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    if not rows:
        raise SystemExit(f"空文件: {path}")
    cols = list(rows[0].keys())
    idc = next((c for c in cols if c.lower() in ID_KEYS), None)
    if idc is None:
        raise SystemExit(f"{path}: 找不到图片标识列，现有列 {cols}")

    data = {}
    if "dim" in cols and "raw" in cols:
        for r in rows:
            d = r["dim"].strip()
            if d not in DIMS:
                continue
            if r.get("mask", "1") not in ("1", "1.0", "", None):
                continue
            try:
                gt, pr = float(r["label"]), float(r["raw"])
            except (KeyError, ValueError):
                continue
            data.setdefault(key_of(r[idc]), {})[d] = (gt, pr)
        return data

    pairs = {}
    for d in DIMS:
        gt = next((f"{p}{d}" for p in GT_PREFIX if f"{p}{d}" in cols), None)
        if gt is None and d in cols:
            gt = d
        pr = next((c for c in (f"pred_{d}", f"p_{d}") if c in cols), None)
        if pr is None:
            pr = next((c for c in cols if d in c and c != gt), None)
        pairs[d] = (gt, pr)
    for r in rows:
        rec = {}
        for d, (gtc, prc) in pairs.items():
            if gtc is None or prc is None:
                continue
            try:
                rec[d] = (float(r[gtc]), float(r[prc]))
            except (KeyError, ValueError):
                continue
        data[key_of(r[idc])] = rec
    return data


def mae_table(a, b):
    keys = sorted(set(a) & set(b))
    per_dim = {d: [0.0, 0.0, 0] for d in DIMS}
    per_img = {}
    for k in keys:
        ea, eb = [], []
        for d in DIMS:
            if d not in a[k] or d not in b[k]:
                continue
            gt, pa = a[k][d]
            _, pb = b[k][d]
            per_dim[d][0] += abs(pa - gt)
            per_dim[d][1] += abs(pb - gt)
            per_dim[d][2] += 1
            ea.append(abs(pa - gt))
            eb.append(abs(pb - gt))
        if ea:
            per_img[k] = (float(np.mean(ea)), float(np.mean(eb)))
    dims = {}
    for d in DIMS:
        sa, sb, n = per_dim[d]
        dims[d] = {"mae_a": round(sa / n, 4) if n else None,
                   "mae_b": round(sb / n, 4) if n else None, "n": n}
    return dims, per_img, len(keys)


def bootstrap(per_img, rounds, seed):
    arr = np.array(list(per_img.values()), dtype=np.float64)
    a, b = arr[:, 0], arr[:, 1]
    diffs = a - b
    n = len(diffs)
    rng = random.Random(seed)
    means = np.array([diffs[rng.choices(range(n), k=n)].mean() for _ in range(rounds)])
    return {
        "n_images": n,
        "mae_a": round(float(a.mean()), 4),
        "mae_b": round(float(b.mean()), 4),
        "mean_diff_a_minus_b": round(float(diffs.mean()), 4),
        "ci95": [round(float(np.percentile(means, 2.5)), 4),
                 round(float(np.percentile(means, 97.5)), 4)],
        "p_a_worse_than_b": round(float((means > 0).mean()), 3),
        "rounds": rounds,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True, help="基线文件")
    ap.add_argument("--b", required=True, help="待比较文件")
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    a, b = load(args.a), load(args.b)
    dims, per_img, overlap = mae_table(a, b)
    diffs = [x - y for x, y in per_img.values()]
    report = {
        "a": str(args.a), "b": str(args.b),
        "overlap_images": overlap,
        "dims": dims,
        "overall_mae_a": round(float(np.mean([v[0] for v in per_img.values()])), 4) if per_img else None,
        "overall_mae_b": round(float(np.mean([v[1] for v in per_img.values()])), 4) if per_img else None,
        "bootstrap": bootstrap(per_img, args.boot, args.seed) if per_img else None,
        "win_rate_b_better": round(float(np.mean([d > 0 for d in diffs])), 3) if diffs else None,
        "note": "mean_diff = MAE(a) - MAE(b)，正值表示 b 更好；CI 不跨 0 才算显著",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                  encoding="utf-8")


if __name__ == "__main__":
    main()
