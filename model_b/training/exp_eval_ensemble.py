"""Evaluate one or more checkpoints, optionally ensemble + TTA.

Writes per-image predictions so baseline/candidate comparisons can be
bootstrapped without re-running inference.

Example:
    python training/exp_eval_ensemble.py \
      --ckpt ../../weights/apddv2_ft/best.pt \
      --head ../../weights/pencils_creativity/head.npz \
      --out ../../logs/e0_baseline --tta base3
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from PIL import Image, ImageOps
from torchvision import transforms
from torchvision.models import resnet18

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ROOT = Path(os.getenv("ART_ROOT", HERE.parents[2]))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

import train_apddv2_finetune as base  # noqa: E402

DIMS = base.DIMS
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]
PENCILS = ROOT / "_downloads" / "Pencils_to_Pixels"


def band(x: float) -> str:
    return "excellent" if x >= 90 else "good" if x >= 75 else "pass" if x >= 60 else "fail"


def load_calib(path: Path):
    if not path or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _piecewise(x, xs, ys):
    if x <= xs[0]:
        j = next((i for i in range(1, len(xs)) if xs[i] != xs[0]), None)
        if j is None:
            return ys[0]
        k = (ys[j] - ys[0]) / (xs[j] - xs[0])
        return max(0.0, ys[0] + (x - xs[0]) * k)
    if x >= xs[-1]:
        j = next((i for i in range(len(xs) - 2, -1, -1) if xs[i] != xs[-1]), None)
        if j is None:
            return ys[-1]
        k = (ys[-1] - ys[j]) / (xs[-1] - xs[j])
        return min(100.0, ys[-1] + (x - xs[-1]) * k)
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            if xs[i + 1] == xs[i]:
                return ys[i + 1]
            t = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + t * (ys[i + 1] - ys[i])
    return x


def calibrate(raw, calib):
    if not calib:
        return [round(float(v), 1) for v in raw]
    tg = calib["targets"]
    ys = [tg["p05"], tg["p25"], tg["p50"], tg["p75"], tg["p95"]]
    out = []
    for d, v in zip(DIMS, raw):
        a = calib["dims"][d]
        xs = [a["p05"], a["p25"], a["p50"], a["p75"], a["p95"]]
        out.append(round(float(_piecewise(v, xs, ys)), 1))
    return out


def load_model(path: Path, device):
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    img = int(ckpt.get("img", 224))
    model = resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, len(DIMS))
    model.load_state_dict(ckpt["state_dict"])
    model.eval().to(device)
    trunk = nn.Sequential(*list(model.children())[:-1]).eval().to(device)
    return model, trunk, img


def load_head(path: Path | None):
    if not path or not path.exists():
        return None
    d = np.load(path)
    return {k: d[k] for k in ("mu", "sd", "w", "ym")}


def head_score(feat, head):
    v = ((feat - head["mu"]) / head["sd"]) @ head["w"] + float(head["ym"][0])
    return float(np.clip(v * 25.0, 0.0, 100.0))


def make_tfs(img_size: int):
    norm = transforms.Normalize(MEAN, STD)
    tf = transforms.Compose([
        transforms.Resize(int(img_size * 1.14)),
        transforms.CenterCrop(img_size),
        transforms.ToTensor(),
        norm,
    ])
    tf_head = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        norm,
    ])
    return tf, tf_head


def variants(img: Image.Image, mode: str):
    out = [img, img.transpose(Image.FLIP_LEFT_RIGHT)]
    w, h = img.size
    dx, dy = int(w * 0.06), int(h * 0.06)
    if dx > 1 and dy > 1:
        out.append(img.crop((dx, dy, w - dx, h - dy)))
    if mode == "crop5" and dx > 1 and dy > 1:
        out.append(img.crop((0, 0, w - dx, h - dy)))
        out.append(img.crop((dx, dy, w, h)))
    return out


@torch.no_grad()
def predict_one(img: Image.Image, models, tta: str):
    """Return ensemble raw 4-dim prediction for one PIL image."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    use_variants = variants(img, tta) if tta != "none" else [img]
    acc = np.zeros(len(DIMS), dtype=np.float64)
    n = 0
    for mi, (model, trunk, tf, tf_head, head) in enumerate(models):
        device = next(model.parameters()).device
        w = ARGS.model_weights[mi]
        for v in use_variants:
            x = tf(v).unsqueeze(0).to(device)
            pred = model(x).clamp(0, 100)[0].float().cpu().numpy()
            if head is not None:
                feat = trunk(tf_head(v).unsqueeze(0).to(device))
                pred[3] = head_score(feat.flatten(1).cpu().numpy()[0], head)
            acc += pred * w
            n += w
    raw = acc / max(n, 1)
    raw[3] = float(np.clip(raw[3], 0, 100))
    return [round(float(v), 1) for v in raw]


def evaluate_apdd(models, test_s, calib):
    rows = []
    abs_sum = np.zeros(len(DIMS))
    cnt = np.zeros(len(DIMS))
    raw_abs_sum = np.zeros(len(DIMS))
    band_ok = []
    for k, (path, labels, mask, _) in enumerate(test_s, 1):
        img = Image.open(path).convert("RGB")
        raw = predict_one(img, models, ARGS.tta)
        cal = calibrate(raw, calib)
        for i, d in enumerate(DIMS):
            if not mask[i]:
                if ARGS.save_all:
                    rows.append({
                        "file": Path(path).name,
                        "dim": d,
                        "raw": raw[i],
                        "cal": cal[i],
                        "label": "",
                        "mask": 0,
                    })
                continue
            err = abs(cal[i] - labels[i])
            abs_sum[i] += err
            cnt[i] += 1
            raw_abs_sum[i] += abs(raw[i] - labels[i])
            band_ok.append(band(cal[i]) == band(labels[i]))
            rows.append({
                "file": Path(path).name,
                "dim": d,
                "raw": raw[i],
                "cal": cal[i],
                "label": labels[i],
                "mask": 1,
            })
        if k % 200 == 0:
            print(f"  APDD {k}/{len(test_s)}", flush=True)
    per_dim = (abs_sum / np.maximum(cnt, 1)).tolist()
    raw_per_dim = (raw_abs_sum / np.maximum(cnt, 1)).tolist()
    metrics = {
        "n_images": len(test_s),
        "n_per_dim": {d: int(cnt[i]) for i, d in enumerate(DIMS)},
        "per_dim_mae": {d: round(per_dim[i], 4) for i, d in enumerate(DIMS)},
        "overall_mae": round(float(np.mean(per_dim)), 4),
        "raw_per_dim_mae": {d: round(raw_per_dim[i], 4) for i, d in enumerate(DIMS)},
        "raw_overall_mae": round(float(np.mean(raw_per_dim)), 4),
        "band_acc": round(float(np.mean(band_ok)), 4),
        "tta": ARGS.tta,
        "checkpoints": [str(p) for p in ARGS.ckpt],
        "model_weights": [round(w, 6) for w in ARGS.model_weights],
        "ensemble_space": "raw",  # average raw dims, then optional calibration
        "calib": None if ARGS.no_calib else str(ARGS.calib),
    }
    return rows, metrics


def evaluate_pencils(models, calib, limit: int):
    rows = list(csv.DictReader(open(PENCILS / "csvs/all_product.csv", encoding="utf-8-sig")))
    ch = [r for r in rows if r["creator"] == "children"]
    ad = [r for r in rows if r["creator"] == "adults"]
    rng = random.Random(42)
    rng.shuffle(ch)
    rng.shuffle(ad)
    ch, ad = ch[:limit], ad[:limit]
    totals = {"children": [], "adults": []}
    for key, part in (("children", ch), ("adults", ad)):
        for r in part:
            p = PENCILS / "csvs" / r["filepath"]
            if not p.exists():
                continue
            try:
                raw = predict_one(Image.open(p), models, ARGS.tta)
                totals[key].append(float(np.mean(calibrate(raw, calib))))
            except Exception:
                pass
        print(f"  Pencils {key}: {len(totals[key])}", flush=True)
    if not totals["children"] or not totals["adults"]:
        return None
    wins = 0.0
    for a in totals["adults"]:
        for c in totals["children"]:
            wins += 1.0 if a > c else 0.5 if a == c else 0.0
    return {
        "n_children": len(totals["children"]),
        "n_adults": len(totals["adults"]),
        "adult_gt_child": round(wins / (len(totals["children"]) * len(totals["adults"])), 4),
        "mean_children": round(float(np.mean(totals["children"])), 2),
        "mean_adults": round(float(np.mean(totals["adults"])), 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", nargs="+", required=True)
    ap.add_argument("--weights", nargs="*", type=float, default=[],
                    help="per-checkpoint weights on RAW predictions; default equal. "
                         "Applied after each model's TTA average, before calibration.")
    ap.add_argument("--head", nargs="*", default=[])
    ap.add_argument("--out", required=True)
    ap.add_argument("--calib", default=str(REPO / "calibration_v31.json"))
    ap.add_argument("--data-root", default=str(ROOT / "data" / "05_apddv2"))
    ap.add_argument("--tta", choices=("none", "base3", "crop5"), default="base3")
    ap.add_argument("--pencils-limit", type=int, default=100)
    ap.add_argument("--no-pencils", action="store_true")
    ap.add_argument("--no-head", action="store_true")
    ap.add_argument("--no-calib", action="store_true")
    ap.add_argument("--save-all", action="store_true",
                    help="save all 4 dims; invalid labels get mask=0 and blank label")
    global ARGS
    ARGS = ap.parse_args()

    if ARGS.head and len(ARGS.head) != len(ARGS.ckpt):
        raise SystemExit("--head 数量必须与 --ckpt 相同，或全部省略")
    if ARGS.weights:
        if len(ARGS.weights) != len(ARGS.ckpt):
            raise SystemExit("--weights 数量必须与 --ckpt 相同，或全部省略")
        if any(w < 0 for w in ARGS.weights) or sum(ARGS.weights) <= 0:
            raise SystemExit("--weights 必须非负且总和大于 0")
        total_w = sum(ARGS.weights)
        ARGS.model_weights = [w / total_w for w in ARGS.weights]
    else:
        ARGS.model_weights = [1.0 / len(ARGS.ckpt)] * len(ARGS.ckpt)

    out = Path(ARGS.out)
    out.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    models = []
    for i, ckpt in enumerate(ARGS.ckpt):
        model, trunk, img_size = load_model(Path(ckpt), device)
        head = None if ARGS.no_head else (load_head(Path(ARGS.head[i])) if ARGS.head else None)
        tf, tf_head = make_tfs(img_size)
        models.append((model, trunk, tf, tf_head, head))
        print(f"loaded {ckpt} img={img_size} head={'yes' if head else 'no'}", flush=True)

    calib = None if ARGS.no_calib else load_calib(Path(ARGS.calib))
    _, _, test_s, _ = base.load_split(Path(ARGS.data_root), 0.2, 0.15)
    rows, metrics = evaluate_apdd(models, test_s, calib)
    with open(out / "preds_test.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "dim", "raw", "cal", "label", "mask"])
        w.writeheader()
        w.writerows(rows)
    (out / "test_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2), flush=True)

    if not ARGS.no_pencils:
        rank = evaluate_pencils(models, calib, ARGS.pencils_limit)
        (out / "pencils_ranking.json").write_text(
            json.dumps(rank, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(rank, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
