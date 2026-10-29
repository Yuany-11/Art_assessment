"""对比 7B 档位打分与 CNN 模型的排序/档位一致性。

读 logs/vlm_grade_pilot/<mode>/results.json 和 logs/edu_web_pilot/*/preds_folder.csv。
只做诊断，不训练、不写权重。

用法：
    python -I training/vlm_compare.py --pilot ../logs/vlm_grade_pilot
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np

BANDS = ("excellent", "good", "pass", "fail")


def rankdata(x: np.ndarray) -> np.ndarray:
    """平均秩，处理并列。"""
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x), dtype=np.float64)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and x[order[j + 1]] == x[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        ranks[order[i:j + 1]] = avg
        i = j + 1
    return ranks


def spearman(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3 or a.std() == 0 or b.std() == 0:
        return float("nan")
    ra, rb = rankdata(a), rankdata(b)
    ra -= ra.mean()
    rb -= rb.mean()
    return float((ra @ rb) / math.sqrt((ra @ ra) * (rb @ rb)))


def load_preds(p: Path) -> dict:
    out = {}
    with open(p, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("error"):
                continue
            out[r["file"]] = {
                "cal_total": float(r["cal_total"]),
                "band": r["band"],
                "dims": [float(r[f"cal{i}"]) for i in (1, 2, 3, 4)],
            }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", default="../../logs/vlm_grade_pilot")
    ap.add_argument("--preds", default="../../logs/edu_web_pilot")
    ap.add_argument("--mode", default="band")
    ap.add_argument("--nonart", nargs="*", default=["santai_00.jpg", "santai_01.jpg", "santai_02.jpg"])
    args = ap.parse_args()

    pilot = Path(args.pilot)
    preds_root = Path(args.preds)

    res = json.loads((pilot / args.mode / "results.json").read_text(encoding="utf-8"))
    per_img = res["per_image"]

    models = {}
    for name, sub in (("baseline", "baseline_santai"), ("seed2", "seed2_santai"), ("ens2", "ens2_santai")):
        f = preds_root / sub / "preds_folder.csv"
        if f.exists():
            models[name] = load_preds(f)

    files = [f for f, e in per_img.items() if "mean_total" in e]
    art = [f for f in files if f not in args.nonart]
    print(f"7B mode={args.mode}  images={len(files)}  artworks={len(art)}"
          f"  flagged_not_artwork={res['summary']['not_artwork_flagged']}")

    # 1) 非作品是否被 7B 识别
    print("\n== 非作品照片 ==")
    for f in args.nonart:
        e = per_img.get(f)
        if not e:
            continue
        v7 = e.get("mean_total")
        nb = {m: (models[m][f]["cal_total"] if f in models.get(m, {}) else None) for m in models}
        print(f"  {f}  7B={v7} ({e.get('band')})  flagged={e['not_artwork']}  "
              + "  ".join(f"{m}={v}" for m, v in nb.items() if v is not None))

    # 2) 排序一致性（只在作品上）
    print("\n== 与 CNN 的 Spearman（仅单件作品） ==")
    v7 = [per_img[f]["mean_total"] for f in art]
    rows = []
    for m, pred in models.items():
        common = [f for f in art if f in pred]
        if len(common) < 5:
            continue
        rho = spearman([per_img[f]["mean_total"] for f in common],
                       [pred[f]["cal_total"] for f in common])
        # 逐维度
        dim_rho = []
        for i, d in enumerate(("composition", "color", "modeling", "creativity")):
            dv = [per_img[f]["median"][d] for f in common]
            dc = [pred[f]["dims"][i] for f in common]
            dim_rho.append(spearman(dv, dc))
        same = sum(1 for f in common if per_img[f]["band"] == pred[f]["band"])
        rows.append((m, len(common), rho, same / len(common), dim_rho))
        print(f"  {m:9s} n={len(common):3d}  rho_total={rho:+.3f}  "
              f"band_agree={same/len(common):.2f}  "
              f"dims={['%+.2f' % x for x in dim_rho]}")

    # 3) 7B 内部：均值 vs 档位分布
    print("\n== 档位分布 ==")
    print(f"  7B      {[sum(1 for f in art if per_img[f]['band'] == b) for b in BANDS]}  {BANDS}")
    for m, pred in models.items():
        print(f"  {m:8s}"
              f"{[sum(1 for f in art if pred.get(f, {}).get('band') == b) for b in BANDS]}")

    # 4) 分歧最大的对
    if "seed2" in models:
        print("\n== 与 seed2 分歧最大的 8 张（7B 高 / seed2 低 或 反之） ==")
        d = [(f, per_img[f]["mean_total"], models["seed2"][f]["cal_total"])
             for f in art if f in models["seed2"]]
        d.sort(key=lambda t: t[1] - t[2])
        for f, a, b in d[:4]:
            print(f"  7B高 {f}  7B={a:6.1f}  seed2={b:6.1f}  差={a-b:+.1f}")
        for f, a, b in d[-4:]:
            print(f"  7B低 {f}  7B={a:6.1f}  seed2={b:6.1f}  差={a-b:+.1f}")


if __name__ == "__main__":
    main()
