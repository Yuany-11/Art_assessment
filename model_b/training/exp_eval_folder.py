"""Evaluate an arbitrary folder of images with one or more checkpoints.

Read-only w.r.t. weights. Writes a CSV of raw/calibrated 4-dim scores and bands.
This is a diagnostic tool for out-of-domain student artwork; it does not train.

Example:
    python training/exp_eval_folder.py \
      --ckpt ../../weights/exp_seed2/best.pt \
      --folder ../../data/06_middle_school_web/pilot/raw \
      --out ../../logs/edu_web_pilot/seed2
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import exp_eval_ensemble as ee  # noqa: E402

EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def band(x: float) -> str:
    return "excellent" if x >= 90 else "good" if x >= 75 else "pass" if x >= 60 else "fail"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", nargs="+", required=True)
    ap.add_argument("--weights", nargs="*", type=float, default=[])
    ap.add_argument("--folder", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--calib", default=str(HERE.parent / "calibration_v31.json"))
    ap.add_argument("--no-calib", action="store_true")
    ap.add_argument("--tta", choices=("none", "base3", "crop5"), default="base3")
    args = ap.parse_args()

    if args.weights:
        if len(args.weights) != len(args.ckpt):
            raise SystemExit("--weights 数量必须与 --ckpt 相同，或全部省略")
        w = np.array(args.weights, dtype=np.float64)
        if np.any(w < 0) or w.sum() <= 0:
            raise SystemExit("--weights 必须非负且总和大于 0")
        model_weights = (w / w.sum()).tolist()
    else:
        model_weights = [1.0 / len(args.ckpt)] * len(args.ckpt)

    ee.ARGS = argparse.Namespace(model_weights=model_weights, tta=args.tta)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    models = []
    for ckpt in args.ckpt:
        model, trunk, img_size = ee.load_model(Path(ckpt), device)
        tf, tf_head = ee.make_tfs(img_size)
        models.append((model, trunk, tf, tf_head, None))
        print(f"loaded {ckpt} img={img_size}", flush=True)

    calib = None if args.no_calib else ee.load_calib(Path(args.calib))
    folder = Path(args.folder)
    files = sorted(p for p in folder.rglob("*") if p.suffix.lower() in EXTS)
    if not files:
        raise SystemExit(f"no images under {folder}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, p in enumerate(files, 1):
        try:
            img = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
            raw = ee.predict_one(img, models, args.tta)
            cal = ee.calibrate(raw, calib)
            rows.append({
                "file": str(p.relative_to(folder)),
                "raw1": raw[0], "raw2": raw[1], "raw3": raw[2], "raw4": raw[3],
                "cal1": cal[0], "cal2": cal[1], "cal3": cal[2], "cal4": cal[3],
                "raw_total": round(float(np.mean(raw)), 2),
                "cal_total": round(float(np.mean(cal)), 2),
                "band": band(float(np.mean(cal))),
                "w": img.width, "h": img.height,
            })
        except Exception as exc:  # noqa: BLE001
            rows.append({"file": str(p.relative_to(folder)), "error": str(exc)[:200]})
        if i % 20 == 0:
            print(f"  {i}/{len(files)}", flush=True)

    fields = ["file", "raw1", "raw2", "raw3", "raw4",
              "cal1", "cal2", "cal3", "cal4", "raw_total", "cal_total", "band",
              "w", "h", "error"]
    with open(out / "preds_folder.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    ok = [r for r in rows if "error" not in r]
    if ok:
        totals = np.array([r["cal_total"] for r in ok])
        summary = {
            "n_images": len(rows),
            "n_ok": len(ok),
            "cal_total": {
                "min": round(float(totals.min()), 2),
                "p05": round(float(np.percentile(totals, 5)), 2),
                "p25": round(float(np.percentile(totals, 25)), 2),
                "median": round(float(np.median(totals)), 2),
                "p75": round(float(np.percentile(totals, 75)), 2),
                "p95": round(float(np.percentile(totals, 95)), 2),
                "max": round(float(totals.max()), 2),
                "mean": round(float(totals.mean()), 2),
            },
            "band_counts": {b: sum(1 for r in ok if r["band"] == b)
                            for b in ("fail", "pass", "good", "excellent")},
            "pass_rate": round(float(np.mean(totals >= 60)), 4),
            "model_weights": model_weights,
            "tta": args.tta,
            "calib": None if args.no_calib else str(args.calib),
        }
        (out / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print("written:", out / "preds_folder.csv", flush=True)


if __name__ == "__main__":
    main()
