"""APDDv2 四维评分 v3.0：ResNet18 全参数微调。

与 v2.0（冻结特征 + 岭回归）的区别：
- 主干解冻，用 APDDv2 重新训练，让特征从"认物体"转向"评美术"
- 分层学习率：主干小、评分层大，避免把预训练权重冲垮
- 训练集内再切 15% 做验证集，用于早停和选最优轮次
- 测试集与 v2.0 去重后的 1923 张完全相同，结果可直接对比；
  注意 v2.0 早期 8.01 是未去重 1993 张上的旧口径，不可与本次结果直接比
- 输出 loss 曲线和四维 MAE 曲线

用法：
    python train_apddv2_finetune.py --yes
    python train_apddv2_finetune.py --epochs 3 --yes      # 冒烟
"""
import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
from torchvision import transforms
from torchvision.models import ResNet18_Weights, resnet18

HERE = Path(__file__).resolve().parent
ROOT = Path(os.getenv("ART_ROOT", HERE.parents[2]))
DATA = Path(os.getenv("ART_DATA", ROOT / "data")) / "05_apddv2"
RUNS = Path(os.getenv("ART_WEIGHTS", ROOT / "weights")) / "apddv2_ft"
LOGS = Path(os.getenv("ART_LOGS", ROOT / "logs")) / "apddv2_ft"
VERSION = "art-cnn-apddv2-v3.0"
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
from train_apddv2_ridge import dedupe_by_content  # noqa: E402

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    with open(LOGS / "train_log.txt", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()


def load_split(root, test_ratio, val_ratio):
    rows, enc = read_csv(find_csv(Path(root)))
    idx, _ = build_index(Path(root))
    missing = sum(1 for r in rows if r["filename"] not in idx)
    samples = [s for s in (to_sample(r, idx) for r in rows) if s]
    if not samples:
        raise SystemExit("没有可用样本：检查图片是否解压到 data\\05_apddv2 下")
    samples, dropped = dedupe_by_content(samples)
    picked = stratified_pick(samples, 0, SEED)
    train_all, test_s = split(picked, test_ratio, SEED)
    train_s, val_s = split(train_all, val_ratio, SEED)
    print(f"CSV 编码={enc} 行数={len(rows)} 缺图={missing} 可用={len(samples)} "
          f"内容去重丢弃={dropped}")
    print(f"train={len(train_s)} val={len(val_s)} test={len(test_s)}")
    for name, part in (("train", train_s), ("val", val_s), ("test", test_s)):
        counts = [sum(s[2][i] for s in part) for i in range(len(DIMS))]
        print(f"  {name} 各维有效数: " + " ".join(
            f"{DIM_CN[d]}={c}" for d, c in zip(DIMS, counts)))
    return train_s, val_s, test_s, dropped


def build_transforms(img):
    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(img, scale=(0.75, 1.0), ratio=(0.85, 1.18)),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])
    eval_tf = transforms.Compose([
        transforms.Resize(int(img * 1.14)),
        transforms.CenterCrop(img),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])
    return train_tf, eval_tf


def masked_loss(pred, label, mask, weights=None):
    err = F.smooth_l1_loss(pred, label, reduction="none")
    w = mask if weights is None else mask * weights
    return (err * w).sum() / w.sum().clamp(min=1)


def build_model():
    model = resnet18(weights=ResNet18_Weights.DEFAULT)
    model.fc = nn.Linear(model.fc.in_features, len(DIMS))
    return model


def make_optimizer(model, lr_backbone, lr_head):
    head = list(model.fc.parameters())
    head_ids = {id(p) for p in head}
    backbone = [p for p in model.parameters() if id(p) not in head_ids]
    return torch.optim.AdamW(
        [{"params": backbone, "lr": lr_backbone}, {"params": head, "lr": lr_head}],
        weight_decay=1e-4,
    )


def evaluate(model, loader, device, weights=None):
    model.eval()
    abs_sum = np.zeros(len(DIMS))
    cnt = np.zeros(len(DIMS))
    loss_sum, seen = 0.0, 0
    with torch.no_grad():
        for x, y, m in loader:
            x, y, m = x.to(device), y.to(device), m.to(device)
            pred = model(x)
            loss_sum += masked_loss(pred, y, m, weights).item() * x.size(0)
            seen += x.size(0)
            abs_sum += ((pred - y).abs() * m).sum(0).cpu().numpy()
            cnt += m.sum(0).cpu().numpy()
    return loss_sum / max(seen, 1), abs_sum / np.maximum(cnt, 1)


def plot_curves(history, path):
    epochs = [h["epoch"] for h in history]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    ax = axes[0]
    ax.plot(epochs, [h["train_loss"] for h in history], label="train")
    ax.plot(epochs, [h["val_loss"] for h in history], label="val")
    ax.set_xlabel("epoch")
    ax.set_ylabel("Masked SmoothL1 loss")
    ax.set_title("Loss")
    ax.legend()
    ax.grid(alpha=0.3)

    ax = axes[1]
    for d in DIMS:
        ax.plot(epochs, [h["val_mae"][d] for h in history], label=DIM_CN[d])
    ax.set_xlabel("epoch")
    ax.set_ylabel("Val MAE (0-100)")
    ax.set_title("四维验证集 MAE")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def baseline_mae(train_s, test_s):
    """每维用训练集均值预测测试集。"""
    out = []
    for i in range(len(DIMS)):
        tr = [s[1][i] for s in train_s if s[2][i] == 1]
        te = [s[1][i] for s in test_s if s[2][i] == 1]
        if not tr or not te:
            out.append(float("nan"))
            continue
        mean = float(np.mean(tr))
        out.append(float(np.mean(np.abs(np.array(te) - mean))))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(DATA))
    ap.add_argument("--test-ratio", type=float, default=0.2)
    ap.add_argument("--val-ratio", type=float, default=0.15)
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--img", type=int, default=224)
    ap.add_argument("--lr-backbone", type=float, default=2e-4)
    ap.add_argument("--lr-head", type=float, default=1e-3)
    ap.add_argument("--patience", type=int, default=4)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dim-weights", default="1,1,1,1",
                    help="四维 loss 权重，顺序同 DIMS（构图,色彩,造型,创意）")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()
    dim_w = [float(x) for x in args.dim_weights.split(",")]
    if len(dim_w) != len(DIMS):
        raise SystemExit(f"--dim-weights 需要 {len(DIMS)} 个数，例如 1,1,1,2")

    LOGS.mkdir(parents=True, exist_ok=True)
    RUNS.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log(f"version={VERSION} method=finetune config epochs={args.epochs} batch={args.batch} "
        f"img={args.img} lr_backbone={args.lr_backbone} lr_head={args.lr_head} device={device}")
    if device.type == "cuda":
        log(f"GPU: {torch.cuda.get_device_name(0)}")

    train_s, val_s, test_s, dropped = load_split(args.root, args.test_ratio, args.val_ratio)

    if not args.yes:
        if input("确认开始？输入 y 继续: ").strip().lower() != "y":
            print("已取消")
            return

    started = time.time()
    train_tf, eval_tf = build_transforms(args.img)
    train_loader = DataLoader(APDDDataset(train_s, train_tf), batch_size=args.batch,
                              shuffle=True, num_workers=args.workers, drop_last=True)
    val_loader = DataLoader(APDDDataset(val_s, eval_tf), batch_size=args.batch,
                            shuffle=False, num_workers=args.workers)
    test_loader = DataLoader(APDDDataset(test_s, eval_tf), batch_size=args.batch,
                             shuffle=False, num_workers=args.workers)

    model = build_model().to(device)
    opt = make_optimizer(model, args.lr_backbone, args.lr_head)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    dim_weights = torch.tensor(dim_w, dtype=torch.float32, device=device)
    if any(w != 1.0 for w in dim_w):
        log("四维 loss 权重: " + " ".join(f"{DIM_CN[d]}={w:g}" for d, w in zip(DIMS, dim_w)))

    history = []
    best_mae, best_epoch, patience = float("inf"), 0, 0
    for epoch in range(1, args.epochs + 1):
        model.train()
        loss_sum, seen = 0.0, 0
        ep_start = time.time()
        for x, y, m in train_loader:
            x, y, m = x.to(device), y.to(device), m.to(device)
            opt.zero_grad()
            pred = model(x)
            loss = masked_loss(pred, y, m, dim_weights)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            loss_sum += loss.item() * x.size(0)
            seen += x.size(0)
        sched.step()

        tr_loss = loss_sum / max(seen, 1)
        va_loss, va_mae = evaluate(model, val_loader, device, dim_weights)
        overall = float(np.mean(va_mae))
        record = {
            "epoch": epoch,
            "train_loss": round(tr_loss, 4),
            "val_loss": round(va_loss, 4),
            "val_mae": {d: round(float(va_mae[i]), 4) for i, d in enumerate(DIMS)},
            "val_mae_mean": round(overall, 4),
            "lr_backbone": round(opt.param_groups[0]["lr"], 8),
            "seconds": round(time.time() - ep_start, 1),
        }
        history.append(record)

        if overall < best_mae:
            best_mae, best_epoch, patience = overall, epoch, 0
            torch.save({
                "state_dict": model.state_dict(),
                "dims": DIMS,
                "version": VERSION,
                "img": args.img,
                "method": "finetune-resnet18",
                "epoch": epoch,
                "val_mae": record["val_mae"],
            }, RUNS / "best.pt")
            mark = " *"
        else:
            patience += 1
            mark = ""
        torch.save({
            "state_dict": model.state_dict(),
            "dims": DIMS,
            "version": VERSION,
            "img": args.img,
            "method": "finetune-resnet18",
            "epoch": epoch,
        }, RUNS / "last.pt")

        log(f"[第 {epoch}/{args.epochs} 轮] train_loss={tr_loss:.3f} val_loss={va_loss:.3f} "
            f"val_MAE=" + " ".join(f"{DIM_CN[d]}={va_mae[i]:.2f}" for i, d in enumerate(DIMS))
            + f" 整体={overall:.2f} 用时={record['seconds']}s{mark}")

        if patience >= args.patience:
            log(f"[早停] 验证集整体 MAE 连续 {args.patience} 轮未改善，停止训练")
            break

    plot_curves(history, LOGS / "curves.png")

    log(f"[测试] 载入第 {best_epoch} 轮的最优权重，测试集只评估一次")
    model.load_state_dict(torch.load(RUNS / "best.pt", map_location=device)["state_dict"])
    test_loss, test_mae = evaluate(model, test_loader, device, dim_weights)
    base_maes = baseline_mae(train_s, test_s)
    test_counts = [sum(s[2][i] for s in test_s) for i in range(len(DIMS))]

    for i, dim in enumerate(DIMS):
        flag = "低于基线" if test_mae[i] < base_maes[i] else "未低于基线"
        log(f"[{DIM_CN[dim]}] 测试 MAE={test_mae[i]:.2f} 基线={base_maes[i]:.2f} {flag}")

    overall = float(np.mean(test_mae))
    overall_base = float(np.mean(base_maes))
    passed = overall <= ACCEPT_MAE and all(
        test_mae[i] < base_maes[i] for i in range(len(DIMS)))
    elapsed = time.time() - started

    readme = [
        f"版本: {VERSION}",
        f"日期: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"环境: Python {platform.python_version()}, torch {torch.__version__}, numpy {np.__version__}",
        f"设备: {device}" + (f" ({torch.cuda.get_device_name(0)})" if device.type == "cuda" else ""),
        "数据: APDDv2 (NeurIPS 2024), 艺术家标注",
        "许可证: README 声明 CC BY-NC-ND 4.0, LICENSE 文件为 CC BY 4.0, 本项目按更严格的执行",
        "用法: 仅用于课程/竞赛等非商业演示; 不对外分发数据集和权重",
        "",
        f"样本: 训练 {len(train_s)} / 验证 {len(val_s)} / 测试 {len(test_s)}"
        "（测试集与 v2.0 去重后的 1923 张一致，只在最后评估一次；"
        "v2.0 早期 8.01 为未去重 1993 张旧口径，不可直接比较）",
        f"内容去重: 丢弃 {dropped} 张同图异名副本，训练/测试无内容重叠",
        f"模型: ResNet18 全参数微调，分层学习率（主干 {args.lr_backbone} / 评分层 {args.lr_head}），"
        f"输入 {args.img}px，输出四维 0-100",
        "增强: 随机裁剪(0.75-1.0)+水平翻转；未用颜色抖动，避免干扰色彩维度",
        "四维 loss 权重: " + " ".join(f"{DIM_CN[d]}={w:g}" for d, w in zip(DIMS, dim_w)),
        "维度映射: 构图=Layout and composition, 色彩=Color, "
        "造型=(Space and perspective + Details and texture)/2, 创意=Creativity",
        "缺失维度: 掩码跳过, 未用 0 填充",
        "总分: 本模型不输出, 由服务端按 rubric 权重对四维加权计算",
        "",
        f"最优轮次: 第 {best_epoch} 轮（验证集整体 MAE {best_mae:.2f}）",
        f"测试集整体 MAE: {overall:.2f}（阈值 {ACCEPT_MAE}）",
        f"常数基线整体 MAE: {overall_base:.2f}（每维预测训练集均值）",
        f"结论: {'达标' if passed else '未达标，不作为评分模型'}",
        "",
    ]
    for i, dim in enumerate(DIMS):
        readme.append(f"{DIM_CN[dim]}: 测试MAE={test_mae[i]:.2f} 基线={base_maes[i]:.2f} "
                      f"有效测试数={test_counts[i]}")
    readme += ["", f"训练命令: python train_apddv2_finetune.py --yes"]
    (RUNS / "说明.txt").write_text("\n".join(readme) + "\n", encoding="utf-8")

    hist = {
        "version": VERSION,
        "method": "finetune-resnet18",
        "env": {"python": platform.python_version(), "torch": torch.__version__,
                "numpy": np.__version__, "device": str(device)},
        "config": {"epochs": args.epochs, "batch": args.batch, "img": args.img,
                   "lr_backbone": args.lr_backbone, "lr_head": args.lr_head,
                   "patience": args.patience, "dim_weights": dim_w},
        "split": {"train": len(train_s), "val": len(val_s), "test": len(test_s),
                  "test_ratio": args.test_ratio, "val_ratio": args.val_ratio},
        "dedup_dropped": dropped,
        "best_epoch": best_epoch,
        "test_mae": {d: float(test_mae[i]) for i, d in enumerate(DIMS)},
        "baseline_mae": {d: float(base_maes[i]) for i, d in enumerate(DIMS)},
        "test_counts": {d: int(test_counts[i]) for i, d in enumerate(DIMS)},
        "overall_mae": overall,
        "overall_baseline_mae": overall_base,
        "passed": bool(passed),
        "seconds": round(elapsed, 1),
        "epochs_run": len(history),
        "history": history,
    }
    (LOGS / "history.json").write_text(
        json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")

    log(f"完成：测试集整体 MAE={overall:.2f} 基线={overall_base:.2f} "
        f"{'达标' if passed else '未达标'}，耗时 {elapsed / 60:.1f} 分钟")
    print("\n模型 vs 基线（测试集）：")
    for i, dim in enumerate(DIMS):
        print(f"  {DIM_CN[dim]}: {test_mae[i]:.2f} vs {base_maes[i]:.2f}")
    print(f"  整体: {overall:.2f} vs {overall_base:.2f}")
    print(f"  对比 v2.0 岭回归: 8.01（同一测试集）")
    print(f"  结论: {'达标' if passed else '未达标'}")
    if not passed:
        print("未达标：不要接入服务，报告按实际数字写。")


if __name__ == "__main__":
    main()
