"""Paired bootstrap comparison of two preds_test.csv files.

Usage:
    python training/exp_bootstrap.py \
      --base ../../logs/e0_baseline_raw/preds_test.csv \
      --cand ../../logs/exp_ensemble3/preds_test.csv \
      --out ../../logs/exp_ensemble3/bootstrap_vs_baseline.json
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

DIMS = ("composition", "color", "modeling", "creativity")


def band(x: float) -> str:
    return "excellent" if x >= 90 else "good" if x >= 75 else "pass" if x >= 60 else "fail"


def load(path: Path):
    out = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[(r["file"], r["dim"])] = (float(r["cal"]), float(r["label"]))
    return out


def metrics(pred, keys):
    errs = defaultdict(list)
    band_ok = []
    for k in keys:
        cal, label = pred[k]
        errs[k[1]].append(abs(cal - label))
        band_ok.append(band(cal) == band(label))
    per_dim = {d: float(np.mean(errs[d])) if errs[d] else float("nan") for d in DIMS}
    return per_dim, float(np.mean([per_dim[d] for d in DIMS])), float(np.mean(band_ok))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--cand", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    base = load(Path(args.base))
    cand = load(Path(args.cand))
    common = sorted(set(base) & set(cand))
    if not common:
        raise SystemExit("no common (file, dim) rows")
    files = sorted({k[0] for k in common})
    by_file = defaultdict(list)
    for k in common:
        by_file[k[0]].append(k)

    b_dim, b_overall, b_band = metrics(base, common)
    c_dim, c_overall, c_band = metrics(cand, common)
    rng = np.random.default_rng(args.seed)
    deltas = []
    dim_deltas = {d: [] for d in DIMS}
    band_deltas = []
    for _ in range(args.n):
        pick = rng.choice(files, size=len(files), replace=True)
        keys = [k for f in pick for k in by_file[f]]
        bd, bo, bb = metrics(base, keys)
        cd, co, cb = metrics(cand, keys)
        deltas.append(co - bo)
        band_deltas.append(cb - bb)
        for d in DIMS:
            dim_deltas[d].append(cd[d] - bd[d])

    def ci(a):
        a = np.asarray(a, dtype=float)
        return [round(float(np.percentile(a, 2.5)), 4), round(float(np.percentile(a, 97.5)), 4)]

    out = {
        "n_common_rows": len(common),
        "n_files": len(files),
        "base": {"per_dim_mae": {d: round(b_dim[d], 4) for d in DIMS},
                 "overall_mae": round(b_overall, 4), "band_acc": round(b_band, 4)},
        "cand": {"per_dim_mae": {d: round(c_dim[d], 4) for d in DIMS},
                 "overall_mae": round(c_overall, 4), "band_acc": round(c_band, 4)},
        "delta": {
            "overall_mae": round(c_overall - b_overall, 4),
            "overall_ci95": ci(deltas),
            "per_dim": {d: round(c_dim[d] - b_dim[d], 4) for d in DIMS},
            "per_dim_ci95": {d: ci(dim_deltas[d]) for d in DIMS},
            "band_acc": round(c_band - b_band, 4),
            "band_acc_ci95": ci(band_deltas),
        },
        "note": "negative MAE delta = candidate better; positive band delta = candidate better",
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
