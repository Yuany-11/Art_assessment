"""用 Pencils 儿童特征重算创意维校准锚点。

创意头输出的是 0-4 尺度，乘 25 到 0-100 后分布与 v3 四维不同，
所以不能沿用 calibration.json 里原来的 creativity 锚点。
这里用 444 张儿童特征的 5 折折外预测（不重训、不碰主干）取分位数，
只替换 creativity 一项，其余三维保持不动。

用法：
    python make_creativity_calib.py            # 只打印，不写文件
    python make_creativity_calib.py --write    # 写回 calibration.json
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = Path(os.getenv("ART_ROOT", HERE.parents[2]))
LOGS = Path(os.getenv("ART_OUT_LOGS", ROOT / "logs" / "pencils_creativity"))
HEAD = Path(os.getenv("ART_OUT_WEIGHTS", ROOT / "weights" / "pencils_creativity")) / "head.npz"
CALIB = ROOT / "repo" / "model_b" / "calibration.json"
SEED = 42
K = 5
QS = (5, 25, 50, 75, 95)


def ridge_fit(X, y, alpha):
    mu = X.mean(0)
    sd = X.std(0) + 1e-6
    Xs = (X - mu) / sd
    ym = y.mean()
    A = Xs.T @ Xs + alpha * np.eye(Xs.shape[1])
    w = np.linalg.solve(A, Xs.T @ (y - ym))
    return mu, sd, w, ym


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    d = np.load(LOGS / "features_children.npz")
    X, y = d["X"], d["Y"]
    h = np.load(HEAD)
    alpha = float(h["alpha"])
    if str(h["groups"][0]) != "children":
        raise SystemExit(f"期望 children 版创意头，实际 {h['groups']}")

    rng = np.random.default_rng(SEED)
    idx = rng.permutation(len(y))
    folds = np.array_split(idx, K)
    pred = np.zeros(len(y))
    for f in folds:
        tr = np.setdiff1d(idx, f)
        mu, sd, w, ym = ridge_fit(X[tr], y[tr], alpha)
        pred[f] = ((X[f] - mu) / sd) @ w + ym

    raw = np.clip(pred * 25.0, 0.0, 100.0)
    anchors = {f"p{q:02d}": round(float(np.percentile(raw, q)), 2) for q in QS}
    print(f"样本 {len(y)}  折外预测(0-4) 均值={pred.mean():.3f} std={pred.std():.3f} "
          f"范围=[{pred.min():.3f}, {pred.max():.3f}]")
    print(f"×25 后 均值={raw.mean():.2f} 范围=[{raw.min():.1f}, {raw.max():.1f}]")
    print(json.dumps(anchors, ensure_ascii=False))
    print(f"现有 anchors: {json.dumps(json.loads(CALIB.read_text(encoding='utf-8'))['dims']['creativity'], ensure_ascii=False)}")

    if not args.write:
        print("未写文件。加 --write 生效。")
        return

    calib = json.loads(CALIB.read_text(encoding="utf-8"))
    calib["dims"]["creativity"] = anchors
    calib["creativity_head"] = {
        "source": "Pencils to Pixels 儿童 444 张，5 折折外预测 ×25 到 0-100",
        "report": "logs/pencils_creativity/report.json",
        "alpha": alpha,
        "cv_pearson": 0.650,
        "note": "只替换创意维锚点；目标分档与其他三维共用",
    }
    CALIB.write_text(json.dumps(calib, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已写 {CALIB}")


if __name__ == "__main__":
    main()
