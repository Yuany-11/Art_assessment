"""Pencils to Pixels 创意头训练（5 折交叉验证 + 全量重训）。

背景：v3.0 的创意分在儿童画上是负相关（Pearson -0.10），
但冻结主干特征做线性探针时 5 折 CV 达到 +0.64，
说明信号在特征里，问题出在 APDDv2 训出来的创意输出头。

做法：冻结 ResNet18 主干，只用 Pencils 的专家创意分训练一个线性头。
只替换创意一维，构图/色彩/造型仍用 v3.0 原权重。

用法：
    python train_creativity_pencils.py --groups children --yes
    python train_creativity_pencils.py --groups children,adults --yes
    python train_creativity_pencils.py --smoke          # 快速验证流程
输出：
    weights/pencils_creativity/head.npz   线性头权重与标准化参数
    weights/pencils_creativity/说明.txt
    logs/pencils_creativity/report.json   每折指标与最终选择
"""
import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torchvision import transforms
from torchvision.models import resnet18

HERE = Path(__file__).resolve().parent
ROOT = Path(os.getenv("ART_ROOT", HERE.parents[2]))
PENCILS = Path(os.getenv("ART_PENCILS", ROOT / "_downloads" / "Pencils_to_Pixels"))
CKPT = Path(os.getenv("ART_WEIGHT", ROOT / "weights" / "apddv2_ft" / "best.pt"))
OUT_W = Path(os.getenv("ART_OUT_WEIGHTS", ROOT / "weights" / "pencils_creativity"))
OUT_L = Path(os.getenv("ART_OUT_LOGS", ROOT / "logs" / "pencils_creativity"))
SEED = 42


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    OUT_L.mkdir(parents=True, exist_ok=True)
    with open(OUT_L / "train_log.txt", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def load_backbone():
    ckpt = torch.load(CKPT, map_location="cpu", weights_only=False)
    model = resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, 4)
    model.load_state_dict(ckpt["state_dict"])
    trunk = nn.Sequential(*list(model.children())[:-1])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    trunk.eval().to(device)
    return trunk, device


def build_tf():
    return transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])


def extract(group: str, trunk, device, tf, cache: Path, limit: int = 0):
    rows = list(csv.DictReader(open(PENCILS / f"csvs/{group}_product.csv", encoding="utf-8-sig")))
    if limit:
        rows = rows[:limit]
    X, Y, paths = [], [], []
    with torch.no_grad():
        for r in rows:
            p = PENCILS / r["filepath"].replace("../", "")
            if not p.exists():
                continue
            try:
                img = Image.open(p).convert("RGB")
            except Exception:
                continue
            feat = trunk(tf(img).unsqueeze(0).to(device)).flatten(1).cpu().numpy()[0]
            X.append(feat)
            Y.append(float(r["creativity2"]))
            paths.append(r["filepath"])
    X = np.asarray(X, dtype=np.float64)
    Y = np.asarray(Y, dtype=np.float64)
    return X, Y, paths


def get_features(group, trunk, device, tf, limit=0):
    cache = OUT_L / f"features_{group}.npz"
    if cache.exists() and not limit:
        d = np.load(cache)
        if len(d["Y"]) > 0:
            log(f"使用缓存特征 {cache}")
            return d["X"], d["Y"]
    t0 = time.time()
    X, Y, _ = extract(group, trunk, device, tf, cache, limit)
    log(f"{group}: 提取 {len(Y)} 张，用时 {time.time() - t0:.1f}s")
    if not limit:
        np.savez(cache, X=X, Y=Y)
    return X, Y


def rank(a):
    a = np.asarray(a, dtype=np.float64)
    order = np.argsort(a)
    r = np.empty(len(a), dtype=np.float64)
    r[order] = np.arange(len(a))
    return r


def corr(a, b):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.std() < 1e-9 or b.std() < 1e-9:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def ridge_fit(X, y, alpha):
    mu = X.mean(0)
    sd = X.std(0) + 1e-6
    Xs = (X - mu) / sd
    ym = y.mean()
    A = Xs.T @ Xs + alpha * np.eye(Xs.shape[1])
    w = np.linalg.solve(A, Xs.T @ (y - ym))
    return mu, sd, w, ym


def ridge_predict(X, mu, sd, w, ym):
    return ((X - mu) / sd) @ w + ym


def cv_eval(X, y, k, alpha):
    rng = np.random.default_rng(SEED)
    idx = rng.permutation(len(y))
    folds = np.array_split(idx, k)
    pred = np.zeros(len(y))
    for f in folds:
        tr = np.setdiff1d(idx, f)
        mu, sd, w, ym = ridge_fit(X[tr], y[tr], alpha)
        pred[f] = ridge_predict(X[f], mu, sd, w, ym)
    return {
        "alpha": alpha,
        "pearson": corr(pred, y),
        "spearman": corr(rank(pred), rank(y)),
        "mae": float(np.mean(np.abs(pred - y))),
        "pred_std": float(pred.std()),
        "label_std": float(y.std()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--groups", default="children", help="children / adults / children,adults")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--alpha-grid", default="10,30,100,300,1000")
    ap.add_argument("--smoke", action="store_true", help="只取 60 张验证流程")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    OUT_W.mkdir(parents=True, exist_ok=True)
    OUT_L.mkdir(parents=True, exist_ok=True)
    if not args.smoke and not args.yes:
        ans = input("将覆盖 weights/pencils_creativity 下的旧结果，继续？[y/N] ")
        if ans.strip().lower() != "y":
            sys.exit(0)

    groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    trunk, device = load_backbone()
    tf = build_tf()
    log(f"groups={groups} folds={args.folds} device={device} smoke={args.smoke}")

    Xs, Ys = [], []
    for g in groups:
        X, Y = get_features(g, trunk, device, tf, limit=60 if args.smoke else 0)
        log(f"{g}: n={len(Y)} 专家创意均值={Y.mean():.2f}")
        Xs.append(X)
        Ys.append(Y)
    X = np.concatenate(Xs) if len(Xs) > 1 else Xs[0]
    y = np.concatenate(Ys) if len(Ys) > 1 else Ys[0]
    if len(y) < args.folds * 5:
        raise SystemExit("样本太少，无法做交叉验证")

    grid = [float(a) for a in args.alpha_grid.split(",")]
    results = [cv_eval(X, y, args.folds, a) for a in grid]
    for r in results:
        log(f"[CV] alpha={r['alpha']:>7.0f} Pearson={r['pearson']:+.3f} "
            f"Spearman={r['spearman']:+.3f} MAE={r['mae']:.3f} 预测std={r['pred_std']:.3f}")
    best = max(results, key=lambda r: r["pearson"])

    mu, sd, w, ym = ridge_fit(X, y, best["alpha"])
    np.savez(OUT_W / "head.npz", mu=mu, sd=sd, w=w, ym=np.array([ym]),
             alpha=best["alpha"], groups=np.array(groups))
    report = {
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "groups": groups,
        "n": int(len(y)),
        "folds": args.folds,
        "alpha_grid": grid,
        "cv_results": results,
        "selected": best,
        "note": "只替换创意一维；构图/色彩/造型仍用 v3.0 权重。分数乘 25 映射到 0-100。",
    }
    (OUT_L / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    txt = [
        f"版本: pencils-creativity-head-v1",
        f"日期: {report['created']}",
        f"训练组: {','.join(groups)}  样本: {len(y)}  交叉验证: {args.folds} 折",
        f"主干: 冻结 APDDv2 v3.0 best.pt 的 ResNet18（不改动）",
        f"方法: 标准化 + 岭回归线性头，alpha={best['alpha']:.0f}（按 CV Pearson 选）",
        f"5 折 CV: Pearson={best['pearson']:+.3f} Spearman={best['spearman']:+.3f} MAE={best['mae']:.3f}",
        f"用途: 只替换创意维度输出；构图/色彩/造型仍用 v3.0",
        f"分数映射: 头输出 0-4 尺度 × 25 得 0-100",
        f"数据: Pencils to Pixels, 专家 creativity 标注（CC-BY-4.0）",
        f"限制: 线稿/按给定形状画；对彩绘儿童画的外推未验证",
    ]
    (OUT_W / "说明.txt").write_text("\n".join(txt) + "\n", encoding="utf-8")
    log(f"最优 alpha={best['alpha']:.0f} CV Pearson={best['pearson']:+.3f}")
    log(f"已写 {OUT_W / 'head.npz'} 和 {OUT_L / 'report.json'}")


if __name__ == "__main__":
    main()
