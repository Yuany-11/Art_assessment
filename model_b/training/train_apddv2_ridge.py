"""APDDv2 四维评分 v2.0：冻结 ResNet18 特征 + 每维岭回归。

与 v1.0（train_apddv2.py）的区别：
- 默认全量数据，按类别分层切 80% 训练 / 20% 独立测试
- 不跑 SGD；用闭式岭回归训练 512->4 的线性头，结果确定、可复现
- alpha 在训练集内做 5 折交叉验证选择，测试集只在最后评估一次
- 同时计算常数基线（每维预测训练集均值），输出达标/未达标结论
- 不覆盖 v1.0 的 weights/apddv2 和 logs/apddv2

用法：
    python train_apddv2_ridge.py --yes                    # 全量
    python train_apddv2_ridge.py --subset 300 --yes       # 冒烟测试
"""
import argparse
import hashlib
import json
import os
import platform
import sys
import time
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import transforms
from torchvision.models import ResNet18_Weights, resnet18

HERE = Path(__file__).resolve().parent
ROOT = Path(os.getenv("ART_ROOT", HERE.parents[2]))
DATA = Path(os.getenv("ART_DATA", ROOT / "data")) / "05_apddv2"
RUNS = Path(os.getenv("ART_WEIGHTS", ROOT / "weights")) / "apddv2_v2"
LOGS = Path(os.getenv("ART_LOGS", ROOT / "logs")) / "apddv2_v2"
VERSION = "art-probe-apddv2-v2.0"
ACCEPT_MAE = 8.5
SEED = 42

sys.path.insert(0, str(HERE))
from check_apddv2 import build_index, find_csv, read_csv  # noqa: E402
from train_apddv2 import (  # noqa: E402
    APDDDataset,
    DIMS,
    DIM_CN,
    split,
    stratified_pick,
    to_sample,
)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    with open(LOGS / "train_log.txt", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()


DEDUP = {"dropped": 0}


def _md5(path, chunk=1 << 20):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def dedupe_by_content(samples):
    """同一张画可能有多个文件名，只保留一份，避免训练集与测试集之间泄漏。"""
    by_size = defaultdict(list)
    for s in samples:
        by_size[Path(str(s[0])).stat().st_size].append(s)
    drop = set()
    for group in by_size.values():
        if len(group) < 2:
            continue
        seen = set()
        for s in group:
            digest = _md5(str(s[0]))
            if digest in seen:
                drop.add(str(s[0]))
            else:
                seen.add(digest)
    return [s for s in samples if str(s[0]) not in drop], len(drop)


def load_samples(root, subset):
    rows, enc = read_csv(find_csv(Path(root)))
    idx, _ = build_index(Path(root))
    missing = sum(1 for r in rows if r["filename"] not in idx)
    samples = [s for s in (to_sample(r, idx) for r in rows) if s]
    if not samples:
        raise SystemExit("没有可用样本：检查图片是否解压到 data\\05_apddv2 下")
    samples, dropped = dedupe_by_content(samples)
    DEDUP["dropped"] = dropped
    picked = stratified_pick(samples, subset, SEED)
    print(f"CSV 编码={enc} 行数={len(rows)} 缺图={missing} 可用={len(samples)} "
          f"内容去重丢弃={dropped} 抽样后={len(picked)}")
    return picked


def val_transform(img):
    return transforms.Compose([
        transforms.Resize(int(img * 1.14)),
        transforms.CenterCrop(img),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])


def build_extractor():
    model = resnet18(weights=ResNet18_Weights.DEFAULT)
    model.fc = nn.Identity()
    model.eval()
    for p in model.parameters():
        p.requires_grad = False
    return model


def extract_features(samples, img, batch, workers):
    tf = val_transform(img)
    loader = DataLoader(APDDDataset(samples, tf), batch_size=batch, shuffle=False,
                        num_workers=workers)
    extractor = build_extractor()
    total = len(samples)
    started = time.time()
    xs, ys, ms = [], [], []
    done = 0
    with torch.no_grad():
        for step, (x, y, m) in enumerate(loader, 1):
            xs.append(extractor(x).numpy().astype(np.float32))
            ys.append(y.numpy())
            ms.append(m.numpy())
            done += x.size(0)
            if step % 10 == 0 or done == total:
                elapsed = max(time.time() - started, 1e-6)
                rate = done / elapsed
                eta = (total - done) / rate / 60
                log(f"[特征提取] {done}/{total} ({done / total * 100:.1f}%) "
                    f"{rate:.1f} 张/秒，预计剩余 {eta:.1f} 分钟")
    return np.vstack(xs), np.vstack(ys), np.vstack(ms)


def load_or_extract(samples, args):
    expected = [s[0] for s in samples]
    cache = LOGS / "features.npz"
    if cache.exists() and not args.no_cache:
        data = np.load(cache, allow_pickle=False)
        if [str(f) for f in data["files"]] == expected:
            log(f"[特征提取] 使用缓存 {cache}")
            return data["X"], data["Y"], data["M"]
        log("[特征提取] 缓存与当前样本不一致，重新提取")
    X, Y, M = extract_features(samples, args.img, args.batch, args.workers)
    np.savez(cache, X=X, Y=Y, M=M, files=np.array(expected))
    log(f"[特征提取] 完成，已缓存到 {cache}")
    return X, Y, M


def fit_ridge(X, y, alpha):
    mu = X.mean(axis=0)
    sd = X.std(axis=0) + 1e-6
    Xs = (X - mu) / sd
    ym = float(y.mean())
    eye = np.eye(X.shape[1])
    w = np.linalg.solve(Xs.T @ Xs + alpha * eye, Xs.T @ (y - ym))
    return mu, sd, w, ym


def predict_ridge(X, mu, sd, w, ym):
    return np.clip(((X - mu) / sd) @ w + ym, 0.0, 100.0)


def select_alpha(X, y, alphas, folds, seed):
    rng = np.random.default_rng(seed)
    parts = np.array_split(rng.permutation(len(y)), folds)
    best_mae, best_alpha = float("inf"), alphas[0]
    for alpha in alphas:
        err, cnt = 0.0, 0
        for k in range(folds):
            test_idx = parts[k]
            train_idx = np.concatenate([parts[j] for j in range(folds) if j != k])
            mu, sd, w, ym = fit_ridge(X[train_idx], y[train_idx], alpha)
            pred = predict_ridge(X[test_idx], mu, sd, w, ym)
            err += np.abs(pred - y[test_idx]).sum()
            cnt += len(test_idx)
        mae = err / max(cnt, 1)
        if mae < best_mae:
            best_mae, best_alpha = mae, alpha
    return best_mae, best_alpha


def evaluate_model(model, samples, img, batch):
    tf = val_transform(img)
    loader = DataLoader(APDDDataset(samples, tf), batch_size=batch, shuffle=False)
    preds = []
    model.eval()
    with torch.no_grad():
        for x, _, _ in loader:
            preds.append(model(x).clamp(0, 100).numpy())
    return np.vstack(preds)


def plot_compare(model_maes, base_maes, path):
    x = np.arange(len(DIMS))
    width = 0.36
    fig, ax = plt.subplots(figsize=(8, 4.6))
    bars1 = ax.bar(x - width / 2, model_maes, width, label="模型")
    bars2 = ax.bar(x + width / 2, base_maes, width, label="常数基线")
    ax.set_xticks(x)
    ax.set_xticklabels([DIM_CN[d] for d in DIMS])
    ax.set_ylabel("测试集 MAE（0-100，越低越好）")
    ax.set_title("模型 vs 常数基线")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    for bars in (bars1, bars2):
        for b in bars:
            ax.annotate(f"{b.get_height():.2f}", (b.get_x() + b.get_width() / 2, b.get_height()),
                        ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(DATA))
    ap.add_argument("--subset", type=int, default=0, help="0 表示全量")
    ap.add_argument("--test-ratio", type=float, default=0.2)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--img", type=int, default=224)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--alphas", default="0.1,1,10,100,300,1000,3000,10000")
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()
    alphas = [float(a) for a in args.alphas.split(",")]

    LOGS.mkdir(parents=True, exist_ok=True)
    RUNS.mkdir(parents=True, exist_ok=True)
    log(f"version={VERSION} method=frozen-resnet18+ridge "
        f"config subset={args.subset or '全部'} test_ratio={args.test_ratio} "
        f"folds={args.folds} img={args.img}")

    picked = load_samples(args.root, args.subset)
    train_s, test_s = split(picked, args.test_ratio, SEED)
    print(f"train={len(train_s)} test={len(test_s)}")
    for name, part in (("train", train_s), ("test", test_s)):
        counts = [sum(s[2][i] for s in part) for i in range(len(DIMS))]
        print(f"  {name} 各维有效数: " + " ".join(
            f"{DIM_CN[d]}={c}" for d, c in zip(DIMS, counts)))

    if not args.yes:
        if input("确认开始？输入 y 继续: ").strip().lower() != "y":
            print("已取消")
            return

    started = time.time()
    X, Y, M = load_or_extract(train_s + test_s, args)
    n_train = len(train_s)
    Xtr, Ytr, Mtr = X[:n_train], Y[:n_train], M[:n_train]
    Xte, Yte, Mte = X[n_train:], Y[n_train:], M[n_train:]
    Xtr = Xtr.astype(np.float64)
    Xte = Xte.astype(np.float64)

    params, model_maes, base_maes, cv_maes, chosen = [], [], [], [], []
    test_counts = []
    for i, dim in enumerate(DIMS):
        tr_mask = Mtr[:, i] == 1
        te_mask = Mte[:, i] == 1
        y_tr = Ytr[tr_mask, i].astype(np.float64)
        y_te = Yte[te_mask, i].astype(np.float64)

        cv_mae, alpha = select_alpha(Xtr[tr_mask], y_tr, alphas, args.folds, SEED + i)
        mu, sd, w, ym = fit_ridge(Xtr[tr_mask], y_tr, alpha)
        pred_te = predict_ridge(Xte[te_mask], mu, sd, w, ym)
        mae = float(np.mean(np.abs(pred_te - y_te)))
        base = float(np.mean(np.abs(y_te - y_tr.mean())))

        params.append((mu, sd, w, ym))
        model_maes.append(mae)
        base_maes.append(base)
        cv_maes.append(cv_mae)
        chosen.append(alpha)
        test_counts.append(int(te_mask.sum()))
        flag = "低于基线" if mae < base else "未低于基线"
        log(f"[{DIM_CN[dim]}] alpha={alpha:g} 交叉验证 MAE={cv_mae:.2f} "
            f"测试 MAE={mae:.2f} 基线={base:.2f} {flag}")

    W = np.stack([params[i][2] / params[i][1] for i in range(len(DIMS))], axis=1)
    b = np.array([params[i][3] - params[i][0] @ (params[i][2] / params[i][1])
                  for i in range(len(DIMS))])

    model = resnet18(weights=ResNet18_Weights.DEFAULT)
    model.fc = nn.Linear(model.fc.in_features, len(DIMS))
    model.load_state_dict(
        {k: v for k, v in build_extractor().state_dict().items() if not k.startswith("fc.")},
        strict=False)
    with torch.no_grad():
        model.fc.weight.copy_(torch.tensor(W.T, dtype=torch.float32))
        model.fc.bias.copy_(torch.tensor(b, dtype=torch.float32))

    log("[验证] 用保存后的模型重新跑测试集，确认与岭回归结果一致")
    folded_pred = evaluate_model(model, test_s, args.img, args.batch)
    folded_maes = []
    for i in range(len(DIMS)):
        te_mask = Mte[:, i] == 1
        mae = float(np.mean(np.abs(folded_pred[te_mask, i] - Yte[te_mask, i])))
        folded_maes.append(mae)
        if abs(mae - model_maes[i]) > 1e-3:
            raise SystemExit(f"折叠权重校验失败：{DIM_CN[DIMS[i]]} {mae} vs {model_maes[i]}")
    log("[验证] 通过")

    overall = float(np.mean(model_maes))
    overall_base = float(np.mean(base_maes))
    passed = overall <= ACCEPT_MAE and all(
        model_maes[i] < base_maes[i] for i in range(len(DIMS)))
    elapsed = time.time() - started

    torch.save({
        "state_dict": model.state_dict(),
        "dims": DIMS,
        "version": VERSION,
        "img": args.img,
        "method": "frozen-resnet18+ridge",
        "alphas": {DIMS[i]: chosen[i] for i in range(len(DIMS))},
        "test_mae": {DIMS[i]: model_maes[i] for i in range(len(DIMS))},
    }, RUNS / "best.pt")

    readme = [
        f"版本: {VERSION}",
        f"日期: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"环境: Python {platform.python_version()}, torch {torch.__version__}, numpy {np.__version__}",
        "数据: APDDv2 (NeurIPS 2024), 艺术家标注",
        "许可证: README 声明 CC BY-NC-ND 4.0, LICENSE 文件为 CC BY 4.0, 本项目按更严格的执行",
        "用法: 仅用于课程/竞赛等非商业演示; 不对外分发数据集和权重",
        "",
        f"样本: 训练 {len(train_s)} / 测试 {len(test_s)}（按类别分层，测试集只在最后评估一次）",
        f"内容去重: 丢弃 {DEDUP['dropped']} 张同图异名副本，训练/测试无内容重叠",
        f"模型: ResNet18 ImageNet 主干冻结，512 维特征 + 每维岭回归；输入 {args.img}px，输出四维 0-100",
        "维度映射: 构图=Layout and composition, 色彩=Color, "
        "造型=(Space and perspective + Details and texture)/2, 创意=Creativity",
        "缺失维度: 掩码跳过, 未用 0 填充",
        "总分: 本模型不输出, 由服务端按 rubric 权重对四维加权计算",
        "",
        f"测试集整体 MAE: {overall:.2f}（阈值 {ACCEPT_MAE}）",
        f"常数基线整体 MAE: {overall_base:.2f}（每维预测训练集均值）",
        f"结论: {'达标' if passed else '未达标，不作为评分模型'}",
        "",
    ]
    for i, dim in enumerate(DIMS):
        readme.append(f"{DIM_CN[dim]}: MAE={model_maes[i]:.2f} 基线={base_maes[i]:.2f} "
                      f"alpha={chosen[i]:g} 有效测试数={test_counts[i]}")
    readme += ["", f"训练命令: python train_apddv2_ridge.py --subset {args.subset} --yes"]
    (RUNS / "说明.txt").write_text("\n".join(readme) + "\n", encoding="utf-8")

    history = {
        "version": VERSION,
        "method": "frozen-resnet18+ridge",
        "env": {"python": platform.python_version(), "torch": torch.__version__,
                "numpy": np.__version__},
        "split": {"train": len(train_s), "test": len(test_s),
                  "test_ratio": args.test_ratio},
        "dedup_dropped": DEDUP["dropped"],
        "alphas": {DIMS[i]: chosen[i] for i in range(len(DIMS))},
        "cv_mae": {DIMS[i]: float(cv_maes[i]) for i in range(len(DIMS))},
        "test_mae": {DIMS[i]: float(model_maes[i]) for i in range(len(DIMS))},
        "baseline_mae": {DIMS[i]: float(base_maes[i]) for i in range(len(DIMS))},
        "test_counts": {DIMS[i]: test_counts[i] for i in range(len(DIMS))},
        "overall_mae": overall,
        "overall_baseline_mae": overall_base,
        "passed": bool(passed),
        "seconds": round(elapsed, 1),
    }
    (LOGS / "history.json").write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    plot_compare(model_maes, base_maes, LOGS / "compare.png")

    log(f"完成：整体 MAE={overall:.2f} 基线={overall_base:.2f} "
        f"{'达标' if passed else '未达标'}，耗时 {elapsed / 60:.1f} 分钟")
    print("\n模型 vs 基线：")
    for i, dim in enumerate(DIMS):
        print(f"  {DIM_CN[dim]}: {model_maes[i]:.2f} vs {base_maes[i]:.2f}")
    print(f"  整体: {overall:.2f} vs {overall_base:.2f}")
    print(f"  结论: {'达标' if passed else '未达标'}")
    if not passed:
        print("未达标：不要接入服务，报告按实际数字写。")


if __name__ == "__main__":
    main()
