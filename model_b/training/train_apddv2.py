"""APDDv2 四维评分训练：冻结 ResNet18 主干，只训输出层，缺失维度用掩码跳过。

用法：
    python train_apddv2.py              # 先打印统计，输入 y 再开训
    python train_apddv2.py --yes        # 直接开训
    python train_apddv2.py --subset 0   # 0 = 用全部数据

产出：weights/apddv2/ 只放权重和模型卡（best.pt、last.pt、说明.txt）；
      logs/apddv2/ 放训练记录（train_log.txt、history.json、curves.png）
"""
import argparse
import json
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
import torch
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from torchvision.models import ResNet18_Weights, resnet18
from tqdm import tqdm

HERE = Path(__file__).resolve().parent
ROOT = Path(os.getenv("ART_ROOT", HERE.parents[2]))
DATA = Path(os.getenv("ART_DATA", ROOT / "data")) / "05_apddv2"
RUNS = Path(os.getenv("ART_WEIGHTS", ROOT / "weights")) / "apddv2"
LOGS = Path(os.getenv("ART_LOGS", ROOT / "logs")) / "apddv2"
DIMS = ("composition", "color", "modeling", "creativity")
DIM_CN = {"composition": "构图", "color": "色彩", "modeling": "造型", "creativity": "创意"}
VERSION = "art-cnn-apddv2-v1.1"
SEED = 42

sys.path.insert(0, str(HERE))
from check_apddv2 import build_index, find_csv, map_dims, read_csv  # noqa: E402


def log(msg, fh=None):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    if fh:
        fh.write(line + "\n")
        fh.flush()


def to_sample(row, idx):
    path = idx.get(row["filename"])
    if path is None:
        return None
    m = map_dims(row)
    labels = [m[DIM_CN[d]] for d in DIMS]
    if not any(v is not None for v in labels):
        return None
    mask = [0 if v is None else 1 for v in labels]
    return (str(path), [0.0 if v is None else float(v) for v in labels], mask,
            row["Artistic Categories"])


def stratified_pick(samples, subset, seed):
    if subset <= 0 or subset >= len(samples):
        return list(samples)
    rng = random.Random(seed)
    groups = defaultdict(list)
    for s in samples:
        groups[s[3]].append(s)
    picked = []
    total = len(samples)
    for items in groups.values():
        k = max(1, round(subset * len(items) / total))
        picked.extend(rng.sample(items, min(k, len(items))))
    rng.shuffle(picked)
    return picked


def split(samples, val_ratio, seed):
    rng = random.Random(seed)
    groups = defaultdict(list)
    for s in samples:
        groups[s[3]].append(s)
    train, val = [], []
    for items in groups.values():
        items = list(items)
        rng.shuffle(items)
        cut = max(1, int(len(items) * val_ratio))
        val.extend(items[:cut])
        train.extend(items[cut:])
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


class APDDDataset(Dataset):
    def __init__(self, samples, tf):
        self.samples = samples
        self.tf = tf

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, i):
        path, labels, mask, _ = self.samples[i]
        img = Image.open(path).convert("RGB")
        return (
            self.tf(img),
            torch.tensor(labels, dtype=torch.float32),
            torch.tensor(mask, dtype=torch.float32),
        )


def loaders(args):
    data_dir = Path(args.root)
    rows, enc = read_csv(find_csv(data_dir))
    idx, _ = build_index(data_dir)
    missing = sum(1 for r in rows if r["filename"] not in idx)
    samples = [s for s in (to_sample(r, idx) for r in rows) if s]
    if not samples:
        raise SystemExit("没有可用样本：检查图片是否解压到 data\\05_apddv2 下")

    picked = stratified_pick(samples, args.subset, SEED)
    train_s, val_s = split(picked, args.val_ratio, SEED)

    print(f"CSV 编码={enc} 行数={len(rows)} 缺图={missing} 可用={len(samples)}")
    print(f"抽样后={len(picked)} train={len(train_s)} val={len(val_s)}")
    for name, part in (("train", train_s), ("val", val_s)):
        cnt = [sum(s[2][i] for s in part) for i in range(len(DIMS))]
        print(f"  {name} 各维有效数: " + " ".join(
            f"{DIM_CN[d]}={c}" for d, c in zip(DIMS, cnt)))

    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(args.img, scale=(0.7, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(0.1, 0.1, 0.1),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    val_tf = transforms.Compose([
        transforms.Resize(int(args.img * 1.14)),
        transforms.CenterCrop(args.img),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    return (
        DataLoader(APDDDataset(train_s, train_tf), batch_size=args.batch, shuffle=True),
        DataLoader(APDDDataset(val_s, val_tf), batch_size=args.batch, shuffle=False),
        len(picked),
    )


def masked_loss(pred, label, mask):
    return (F.smooth_l1_loss(pred, label, reduction="none") * mask).sum() / mask.sum().clamp(min=1)


@torch.no_grad()
def evaluate(model, loader, device):
    model.eval()
    err = torch.zeros(len(DIMS))
    cnt = torch.zeros(len(DIMS))
    loss_sum, total = 0.0, 0
    for x, y, m in loader:
        x, y, m = x.to(device), y.to(device), m.to(device)
        out = model(x).clamp(0, 100)
        loss_sum += masked_loss(out, y, m).item() * x.size(0)
        err += ((out - y).abs() * m).sum(dim=0).cpu()
        cnt += m.sum(dim=0).cpu()
        total += x.size(0)
    per_dim = (err / cnt.clamp(min=1)).numpy()
    valid = cnt > 0
    mae = float(per_dim[valid].mean()) if valid.any() else float("nan")
    return loss_sum / max(total, 1), mae, per_dim, cnt.numpy()


def plot(history, path):
    from matplotlib.ticker import MaxNLocator

    ep = [h["epoch"] for h in history]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    for ax in axes:
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    axes[0].plot(ep, [h["train_loss"] for h in history], "o-", label="train")
    axes[0].plot(ep, [h["val_loss"] for h in history], "s-", label="val")
    axes[0].set_title("Masked SmoothL1 loss")
    axes[0].legend()
    axes[0].grid(alpha=0.3)
    for d in DIMS:
        axes[1].plot(ep, [h["per_dim_mae"][d] for h in history], "o-", label=DIM_CN[d])
    axes[1].set_title("Validation MAE per dimension (0-100)")
    axes[1].legend()
    axes[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def write_readme(best_mae, per_dim, counts, n_train, n_val, args):
    lines = [
        f"版本: {VERSION}",
        f"日期: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "数据: APDDv2 (NeurIPS 2024), 艺术家标注",
        "许可证: 仓库 README 声明 CC BY-NC-ND 4.0, 仓库 LICENSE 文件为 CC BY 4.0 (两者不一致, 本项目按更严格的执行)",
        "用法: 仅用于课程/竞赛等非商业演示; 不对外分发数据集和权重",
        "",
        f"训练样本: {n_train}  验证样本: {n_val}  子集: {args.subset or '全部'}",
        f"模型: ResNet18 预训练主干冻结, 只训最后一层; 输入 {args.img}px; 输出四维 0-100",
        f"维度映射: 构图=Layout and composition, 色彩=Color, "
        f"造型=(Space and perspective + Details and texture)/2, 创意=Creativity",
        "缺失维度: 掩码跳过, 未用 0 填充",
        "总分: 本模型不输出, 由服务端按评分权重对四维加权计算",
        "",
        f"最佳验证 MAE(有效维平均): {best_mae:.2f}",
    ]
    for d in DIMS:
        lines.append(f"  {DIM_CN[d]}: MAE={per_dim[DIMS.index(d)]:.2f}  有效验证数={int(counts[DIMS.index(d)])}")
    lines += ["", f"训练命令: python train_apddv2.py --subset {args.subset} --epochs {args.epochs}"]
    (RUNS / "说明.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(DATA))
    ap.add_argument("--subset", type=int, default=2000, help="0 表示用全部")
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--img", type=int, default=224)
    ap.add_argument("--val-ratio", type=float, default=0.2)
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--no-resume", action="store_true", help="忽略断点，从头训练")
    args = ap.parse_args()

    torch.manual_seed(SEED)
    np.random.seed(SEED)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.set_num_threads(os.cpu_count() or 4)

    train_loader, val_loader, n_all = loaders(args)
    est = n_all * 0.05 / 60
    print(f"\n设备={device} 预计 CPU 训练约 {est * args.epochs:.0f} 分钟（只训输出层）")
    if not args.yes:
        if input("确认开始训练？输入 y 继续: ").strip().lower() != "y":
            print("已取消")
            return

    RUNS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / "train_log.txt"
    fh = open(log_path, "a", encoding="utf-8")
    log(f"version={VERSION} device={device} " +
        f"config epochs={args.epochs} batch={args.batch} lr={args.lr} img={args.img} "
        f"train={len(train_loader.dataset)} val={len(val_loader.dataset)}", fh)

    model = resnet18(weights=ResNet18_Weights.DEFAULT)
    for p in model.parameters():
        p.requires_grad = False
    model.fc = torch.nn.Linear(model.fc.in_features, len(DIMS))
    model = model.to(device)
    bn_layers = [m for m in model.modules() if isinstance(m, torch.nn.BatchNorm2d)]

    optimizer = torch.optim.AdamW(model.fc.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    last_path = RUNS / "last.pt"
    start_epoch, history, best_mae = 0, [], 1e9
    if last_path.exists() and not args.no_resume:
        ckpt = torch.load(last_path, map_location=device)
        prev = ckpt.get("args", {})
        if prev.get("subset") == args.subset and prev.get("img") == args.img:
            model.load_state_dict(ckpt["model"])
            optimizer.load_state_dict(ckpt["optimizer"])
            scheduler.load_state_dict(ckpt["scheduler"])
            start_epoch = ckpt["epoch"]
            history = ckpt.get("history", [])
            best_mae = ckpt.get("best_mae", 1e9)
            log(f"发现断点：已完成 {start_epoch} 轮，从第 {start_epoch + 1} 轮继续", fh)
        else:
            log(f"上次训练参数不同（subset={prev.get('subset')} img={prev.get('img')}），"
                f"忽略断点从头开始", fh)

    for epoch in range(start_epoch + 1, args.epochs + 1):
        started = time.time()
        model.train()
        for bn in bn_layers:
            bn.eval()
        running, total = 0.0, 0
        bar = tqdm(train_loader, desc=f"epoch {epoch}/{args.epochs}",
                   unit="batch", leave=False, dynamic_ncols=True)
        for x, y, m in bar:
            x, y, m = x.to(device), y.to(device), m.to(device)
            optimizer.zero_grad()
            out = model(x).clamp(0, 100)
            loss = masked_loss(out, y, m)
            loss.backward()
            optimizer.step()
            running += loss.item() * x.size(0)
            total += x.size(0)
            bar.set_postfix(loss=f"{running / max(total, 1):.3f}")
        scheduler.step()
        val_loss, mae, per_dim, counts = evaluate(model, val_loader, device)
        history.append({
            "epoch": epoch,
            "train_loss": round(running / max(total, 1), 4),
            "val_loss": round(val_loss, 4),
            "val_mae": round(mae, 2),
            "per_dim_mae": {d: round(float(per_dim[i]), 2) for i, d in enumerate(DIMS)},
            "seconds": round(time.time() - started, 1),
        })
        log(f"epoch {epoch}: train_loss={running/max(total,1):.4f} val_loss={val_loss:.4f} "
            f"MAE={mae:.2f} " + " ".join(
                f"{DIM_CN[d]}={per_dim[i]:.2f}" for i, d in enumerate(DIMS)), fh)
        (LOGS / "history.json").write_text(
            json.dumps({"version": VERSION, "dims": DIMS, "history": history},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        if mae <= best_mae:
            best_mae = mae
            torch.save({"state_dict": model.state_dict(), "dims": DIMS,
                        "version": VERSION, "img": args.img}, RUNS / "best.pt")
            write_readme(best_mae, per_dim, counts, len(train_loader.dataset),
                         len(val_loader.dataset), args)
            log(f"saved best checkpoint, val_MAE={mae:.2f}", fh)
        torch.save({
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(),
            "epoch": epoch,
            "best_mae": best_mae,
            "history": history,
            "args": vars(args),
            "dims": DIMS,
            "version": VERSION,
        }, last_path)

    plot(history, LOGS / "curves.png")
    log(f"finished. best_val_MAE={best_mae:.2f}", fh)
    fh.close()


if __name__ == "__main__":
    main()
