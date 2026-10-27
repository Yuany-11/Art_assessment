"""四维误差诊断：只读 v2 缓存特征，不训练主干，不重新提取图片。

回答三个问题，决定明天该换特征、加权、还是补标注：
1. 误差是"往均值收缩"（预测分布比标签窄）还是均匀分布？
2. 创意标签是否混了其他维度（与其他三维相关性过高）？
3. 是不是某几个画种特别差？

用法：
    python diagnose_dims.py                # 用 v2 缓存，全量
    python diagnose_dims.py --no-cache     # 缓存对不上时强制重提取（慢）
输出：logs/apddv2_v2/diagnose.json + diagnose.png
"""
import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = Path(os.getenv("ART_ROOT", HERE.parents[2]))
DATA = Path(os.getenv("ART_DATA", ROOT / "data")) / "05_apddv2"
LOGS = Path(os.getenv("ART_LOGS", ROOT / "logs")) / "apddv2_v2"
SEED = 42

sys.path.insert(0, str(HERE))
from check_apddv2 import build_index, find_csv, read_csv  # noqa: E402
from train_apddv2 import DIMS, DIM_CN, split, stratified_pick, to_sample  # noqa: E402
from train_apddv2_ridge import (  # noqa: E402
    dedupe_by_content,
    extract_features,
    fit_ridge,
    predict_ridge,
    select_alpha,
)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

BINS = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 101)]
ALPHAS = [0.1, 1, 10, 100, 300, 1000, 3000, 10000]


def build_split(root):
    rows, enc = read_csv(find_csv(Path(root)))
    idx, _ = build_index(Path(root))
    samples = [s for s in (to_sample(r, idx) for r in rows) if s]
    if not samples:
        raise SystemExit("没有可用样本：检查图片是否解压到 data\\05_apddv2 下")
    samples, dropped = dedupe_by_content(samples)
    picked = stratified_pick(samples, 0, SEED)
    train_s, test_s = split(picked, 0.2, SEED)
    print(f"CSV 编码={enc} 行数={len(rows)} 内容去重丢弃={dropped} "
          f"train={len(train_s)} test={len(test_s)}")
    return train_s, test_s, dropped


def load_features(train_s, test_s, args):
    ordered = train_s + test_s
    expected = [s[0] for s in ordered]
    cache = Path(os.getenv("ART_LOGS", ROOT / "logs")) / "apddv2_v2" / "features.npz"
    if cache.exists() and not args.no_cache:
        d = np.load(cache, allow_pickle=False)
        if [str(f) for f in d["files"]] == expected:
            print(f"使用缓存 {cache}")
            return d["X"], d["Y"], d["M"]
        print("缓存与当前切分不一致，重新提取特征")
    LOGS.mkdir(parents=True, exist_ok=True)
    X, Y, M = extract_features(ordered, args.img, args.batch, args.workers)
    np.savez(cache, X=X, Y=Y, M=M, files=np.array(expected))
    print(f"已缓存到 {cache}")
    return X, Y, M


def pearson(a, b):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.size < 3 or a.std() < 1e-9 or b.std() < 1e-9:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def bin_mae(y, pred):
    rows = []
    for lo, hi in BINS:
        sel = (y >= lo) & (y < hi)
        if not sel.any():
            rows.append((lo, hi, 0, float("nan"), float("nan")))
            continue
        rows.append((lo, hi, int(sel.sum()),
                     float(np.mean(np.abs(pred[sel] - y[sel]))),
                     float(np.mean(pred[sel]))))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(DATA))
    ap.add_argument("--img", type=int, default=224)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    LOGS.mkdir(parents=True, exist_ok=True)
    train_s, test_s, dropped = build_split(args.root)
    X, Y, M = load_features(train_s, test_s, args)
    n_train = len(train_s)
    Xtr, Ytr, Mtr = X[:n_train].astype(np.float64), Y[:n_train], M[:n_train]
    Xte, Yte, Mte = X[n_train:].astype(np.float64), Y[n_train:], M[n_train:]

    result = {"train": len(train_s), "test": len(test_s), "dedup_dropped": dropped,
              "dims": {}}
    preds = {}
    print("\n=== 1. 分布收缩与误差 ===")
    print(f"{'维度':4s} {'标签std':>8s} {'预测std':>8s} {'收缩比':>7s} "
          f"{'MAE':>6s} {'基线MAE':>8s} {'Pearson':>8s} {'R2':>7s}")
    for i, dim in enumerate(DIMS):
        tr_mask, te_mask = Mtr[:, i] == 1, Mte[:, i] == 1
        y_tr = Ytr[tr_mask, i].astype(np.float64)
        y_te = Yte[te_mask, i].astype(np.float64)
        cv_mae, alpha = select_alpha(Xtr[tr_mask], y_tr, ALPHAS, 5, SEED + i)
        mu, sd, w, ym = fit_ridge(Xtr[tr_mask], y_tr, alpha)
        pred = predict_ridge(Xte[te_mask], mu, sd, w, ym)
        preds[dim] = (te_mask, pred, y_te)
        mae = float(np.mean(np.abs(pred - y_te)))
        base = float(np.mean(np.abs(y_te - y_tr.mean())))
        shrink = float(pred.std() / max(y_te.std(), 1e-9))
        r = pearson(pred, y_te)
        r2 = float(1 - np.sum((pred - y_te) ** 2) / max(np.sum((y_te - y_te.mean()) ** 2), 1e-9))
        result["dims"][dim] = {
            "alpha": alpha, "cv_mae": cv_mae, "mae": mae, "baseline_mae": base,
            "label_std": float(y_te.std()), "pred_std": float(pred.std()),
            "shrink_ratio": shrink, "pearson": r, "r2": r2,
            "n_test": int(te_mask.sum()),
        }
        print(f"{DIM_CN[dim]:4s} {y_te.std():8.2f} {pred.std():8.2f} {shrink:7.2f} "
              f"{mae:6.2f} {base:8.2f} {r:8.3f} {r2:7.3f}")

    print("\n=== 2. 按真实分数段拆 MAE（预测值 vs 真实值）===")
    for dim in DIMS:
        te_mask, pred, y_te = preds[dim]
        rows = bin_mae(y_te, pred)
        result["dims"][dim]["bins"] = [
            {"lo": lo, "hi": hi, "n": n, "mae": m, "pred_mean": p}
            for lo, hi, n, m, p in rows]
        txt = " | ".join(f"[{lo},{hi}) n={n} MAE={m:.1f} 预测均值={p:.1f}"
                         for lo, hi, n, m, p in rows if n)
        print(f"{DIM_CN[dim]}: {txt}")

    print("\n=== 3. 标签间相关性（同时有标注的样本）===")
    corr = np.full((len(DIMS), len(DIMS)), np.nan)
    for i in range(len(DIMS)):
        for j in range(len(DIMS)):
            both = (Mtr[:, i] == 1) & (Mtr[:, j] == 1)
            if both.sum() > 10:
                corr[i, j] = pearson(Ytr[both, i], Ytr[both, j])
    result["label_corr"] = {DIMS[i]: {DIMS[j]: (None if np.isnan(corr[i, j])
                                                else float(corr[i, j]))
                                      for j in range(len(DIMS))}
                            for i in range(len(DIMS))}
    print("        " + " ".join(f"{DIM_CN[d]:>7s}" for d in DIMS))
    for i, dim in enumerate(DIMS):
        print(f"{DIM_CN[dim]:6s} " + " ".join(
            f"{corr[i, j]:7.3f}" if not np.isnan(corr[i, j]) else "    n/a"
            for j in range(len(DIMS))))

    print("\n=== 4. 按画种拆 MAE ===")
    cat_of = {s[0]: s[3].split("*")[0] for s in test_s}
    paths = [s[0] for s in test_s]
    by_cat = {}
    for i, dim in enumerate(DIMS):
        te_mask, pred, y_te = preds[dim]
        sel_paths = [p for p, keep in zip(paths, te_mask) if keep]
        cats = np.array([cat_of.get(p, "?") for p in sel_paths])
        for c in np.unique(cats):
            sel = cats == c
            if sel.sum() < 15:
                continue
            by_cat.setdefault(c, {})[dim] = {
                "n": int(sel.sum()),
                "mae": float(np.mean(np.abs(pred[sel] - y_te[sel]))),
            }
    result["by_category"] = by_cat
    print(f"{'画种':34s} " + " ".join(f"{DIM_CN[d]:>10s}" for d in DIMS))
    for c in sorted(by_cat, key=lambda k: -max(
            (by_cat[k].get(d, {}).get("mae", 0) for d in DIMS), default=0)):
        cells = []
        for d in DIMS:
            v = by_cat[c].get(d)
            cells.append(f"{v['mae']:5.1f}(n={v['n']:3d})" if v else "         -")
        print(f"{c[:34]:34s} " + " ".join(f"{x:>10s}" for x in cells))

    (LOGS / "diagnose.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    plot(result, preds, LOGS / "diagnose.png")
    print(f"\n已写出 {LOGS / 'diagnose.json'} 和 {LOGS / 'diagnose.png'}")


def plot(result, preds, path):
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))

    ax = axes[0]
    x = np.arange(len(DIMS))
    w = 0.36
    lab = [result["dims"][d]["label_std"] for d in DIMS]
    prd = [result["dims"][d]["pred_std"] for d in DIMS]
    ax.bar(x - w / 2, lab, w, label="标签 std")
    ax.bar(x + w / 2, prd, w, label="预测 std")
    ax.set_xticks(x)
    ax.set_xticklabels([DIM_CN[d] for d in DIMS])
    ax.set_ylabel("标准差")
    ax.set_title("分布收缩：预测越窄越像往均值缩")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    ax = axes[1]
    te_mask, pred, y_te = preds["creativity"]
    ax.scatter(y_te, pred, s=5, alpha=0.25, edgecolors="none")
    lims = [0, 100]
    ax.plot(lims, lims, "r--", lw=1, label="完美预测")
    ax.set_xlim(lims)
    ax.set_ylim(lims)
    ax.set_xlabel("真实创意分")
    ax.set_ylabel("预测创意分")
    ax.set_title(f"创意散点（Pearson {result['dims']['creativity']['pearson']:.3f}）")
    ax.legend()
    ax.grid(alpha=0.3)

    ax = axes[2]
    rows = result["dims"]["creativity"]["bins"]
    labels = [f"{lo}-{hi}" for lo, hi, n, m, p in
              [(b['lo'], b['hi'], b['n'], b['mae'], b['pred_mean']) for b in rows] if n]
    maes = [b["mae"] for b in rows if b["n"]]
    ax.bar(range(len(maes)), maes, color="#d67")
    ax.set_xticks(range(len(maes)))
    ax.set_xticklabels(labels)
    ax.set_xlabel("真实创意分区间")
    ax.set_ylabel("MAE")
    ax.set_title("创意分区间误差：两端大=收缩，均匀=噪声")
    ax.grid(axis="y", alpha=0.3)
    for i, v in enumerate(maes):
        ax.annotate(f"{v:.1f}", (i, v), ha="center", va="bottom", fontsize=9)

    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
