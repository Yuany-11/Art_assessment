"""四维评分回归训练（标签来自规则基线，属于蒸馏）。

注意：这里学习的是规则基线的打分方式，不是美术老师的判断。
用法：python prepare_datasets.py && python train_scoring.py
产出：weights/scoring/ 下的 best.pt、curves.png、history.json、train_log.txt
"""
import csv
import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import json
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from torchvision.models import ResNet18_Weights, resnet18

HERE = Path(__file__).resolve().parent
ROOT = Path(os.getenv("ART_ROOT", HERE.parents[2]))
DATA = Path(os.getenv("ART_DATA", ROOT / "data")) / "03_scoring"
RUNS = Path(os.getenv("ART_WEIGHTS", ROOT / "weights")) / "scoring"
DIMS = ("composition", "color", "modeling", "creativity")
EPOCHS = 10
BATCH = 32
LR = 3e-4
IMG = 160
SEED = 42

torch.manual_seed(SEED)
np.random.seed(SEED)
torch.set_num_threads(os.cpu_count() or 4)
RUNS.mkdir(parents=True, exist_ok=True)
LOG = open(RUNS / "train_log.txt", "a", encoding="utf-8")


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    LOG.write(line + "\n")
    LOG.flush()


class ScoreDataset(Dataset):
    def __init__(self, csv_path, tf):
        with open(csv_path, encoding="utf-8") as f:
            self.rows = list(csv.DictReader(f))
        self.tf = tf

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        row = self.rows[i]
        img = Image.open(DATA / row["image_path"]).convert("RGB")
        labels = torch.tensor([float(row[d]) for d in DIMS], dtype=torch.float32)
        return self.tf(img), labels


def loaders():
    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(IMG, scale=(0.7, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(0.1, 0.1, 0.1),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    val_tf = transforms.Compose([
        transforms.Resize(int(IMG * 1.15)),
        transforms.CenterCrop(IMG),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    return (
        DataLoader(ScoreDataset(DATA / "train.csv", train_tf), batch_size=BATCH, shuffle=True),
        DataLoader(ScoreDataset(DATA / "val.csv", val_tf), batch_size=BATCH, shuffle=False),
    )


def evaluate(model, loader, criterion):
    model.eval()
    loss_sum, total = 0.0, 0
    abs_sum = np.zeros(len(DIMS))
    with torch.no_grad():
        for x, y in loader:
            out = model(x).clamp(0, 100)
            loss_sum += criterion(out, y).item() * x.size(0)
            abs_sum += (out - y).abs().sum(dim=0).numpy()
            total += x.size(0)
    return loss_sum / total, abs_sum / total


def plot(history):
    ep = [h["epoch"] for h in history]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    axes[0].plot(ep, [h["train_loss"] for h in history], "o-", label="train")
    axes[0].plot(ep, [h["val_loss"] for h in history], "s-", label="val")
    axes[0].set_title("SmoothL1 loss")
    axes[0].legend()
    axes[0].grid(alpha=0.3)
    axes[1].plot(ep, [h["val_mae"] for h in history], "o-", label="val MAE")
    axes[1].set_title("Mean Absolute Error (0-100)")
    axes[1].legend()
    axes[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(RUNS / "curves.png", dpi=150)
    plt.close(fig)


def main():
    train_loader, val_loader = loaders()
    log("labels=rule-based pseudo labels (distillation), NOT human scores")
    log(f"config epochs={EPOCHS} batch={BATCH} lr={LR} img={IMG} device=cpu")
    log(f"train={len(train_loader.dataset)} val={len(val_loader.dataset)} dims={list(DIMS)}")

    model = resnet18(weights=ResNet18_Weights.DEFAULT)
    model.fc = nn.Linear(model.fc.in_features, len(DIMS))
    criterion = nn.SmoothL1Loss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)

    history, best_mae = [], 1e9
    for epoch in range(1, EPOCHS + 1):
        started = time.time()
        model.train()
        running, total = 0.0, 0
        for x, y in train_loader:
            optimizer.zero_grad()
            loss = criterion(model(x), y)
            loss.backward()
            optimizer.step()
            running += loss.item() * x.size(0)
            total += x.size(0)
        scheduler.step()
        val_loss, per_dim = evaluate(model, val_loader, criterion)
        mae = float(per_dim.mean())
        history.append({
            "epoch": epoch,
            "train_loss": round(running / total, 4),
            "val_loss": round(val_loss, 4),
            "val_mae": round(mae, 2),
            "per_dim_mae": {d: round(float(v), 2) for d, v in zip(DIMS, per_dim)},
            "seconds": round(time.time() - started, 1),
        })
        log(f"epoch {epoch}: train_loss={running / total:.4f} val_loss={val_loss:.4f} "
            f"MAE={mae:.2f} " + " ".join(f"{d}={v:.2f}" for d, v in zip(DIMS, per_dim)))
        with open(RUNS / "history.json", "w", encoding="utf-8") as f:
            json.dump({"dims": DIMS, "history": history}, f, ensure_ascii=False, indent=2)
        if mae <= best_mae:
            best_mae = mae
            torch.save({"state_dict": model.state_dict(), "dims": DIMS}, RUNS / "best.pt")
            log(f"saved best checkpoint, val_MAE={mae:.2f}")

    plot(history)
    log(f"finished. best_val_MAE={best_mae:.2f}")
    LOG.close()


if __name__ == "__main__":
    main()
