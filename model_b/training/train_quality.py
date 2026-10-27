"""图片质量分类训练：normal / blur / dark / noisy。

标签由程序自动生成（模糊、调暗、加噪），不需要人工标注。
用法：python train_quality.py
产出：weights/quality/ 下的 best.pt、curves.png、confusion_matrix.png、history.json、train_log.txt
"""
import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import json
import time
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import datasets, transforms
from torchvision.models import ResNet18_Weights, resnet18

HERE = Path(__file__).resolve().parent
ROOT = Path(os.getenv("ART_ROOT", HERE.parents[2]))
DATA = Path(os.getenv("ART_DATA", ROOT / "data")) / "02_quality"
RUNS = Path(os.getenv("ART_WEIGHTS", ROOT / "weights")) / "quality"
EPOCHS = 8
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


def loaders():
    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(IMG, scale=(0.6, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(0.15, 0.15, 0.1),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    val_tf = transforms.Compose([
        transforms.Resize(int(IMG * 1.15)),
        transforms.CenterCrop(IMG),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    train_ds = datasets.ImageFolder(DATA / "train", transform=train_tf)
    val_ds = datasets.ImageFolder(DATA / "val", transform=val_tf)
    return (
        DataLoader(train_ds, batch_size=BATCH, shuffle=True, num_workers=0),
        DataLoader(val_ds, batch_size=BATCH, shuffle=False, num_workers=0),
        train_ds.classes,
        [s[1] for s in train_ds.samples],
        [s[1] for s in val_ds.samples],
    )


def evaluate(model, loader, criterion):
    model.eval()
    loss_sum, correct, total = 0.0, 0, 0
    preds, labels = [], []
    with torch.no_grad():
        for x, y in loader:
            out = model(x)
            loss_sum += criterion(out, y).item() * x.size(0)
            p = out.argmax(1)
            correct += (p == y).sum().item()
            total += x.size(0)
            preds.extend(p.tolist())
            labels.extend(y.tolist())
    return loss_sum / total, correct / total, preds, labels


def plot(history, classes, cm):
    ep = [h["epoch"] for h in history]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    axes[0].plot(ep, [h["train_loss"] for h in history], "o-", label="train")
    axes[0].plot(ep, [h["val_loss"] for h in history], "s-", label="val")
    axes[0].set_title("Loss")
    axes[0].legend()
    axes[0].grid(alpha=0.3)
    axes[1].plot(ep, [h["train_acc"] for h in history], "o-", label="train")
    axes[1].plot(ep, [h["val_acc"] for h in history], "s-", label="val")
    axes[1].set_ylim(0, 1.02)
    axes[1].set_title("Accuracy")
    axes[1].legend()
    axes[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(RUNS / "curves.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(classes)))
    ax.set_yticks(range(len(classes)))
    ax.set_xticklabels(classes, rotation=30, ha="right")
    ax.set_yticklabels(classes)
    ax.set_xlabel("predicted")
    ax.set_ylabel("true")
    ax.set_title("Confusion Matrix (val)")
    for i in range(len(classes)):
        for j in range(len(classes)):
            if cm[i, j]:
                ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=9)
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig.savefig(RUNS / "confusion_matrix.png", dpi=150)
    plt.close(fig)


def main():
    train_loader, val_loader, classes, train_y, val_y = loaders()
    log(f"classes={classes}")
    log(f"train={dict(Counter(train_y))} val={dict(Counter(val_y))}")
    log(f"config epochs={EPOCHS} batch={BATCH} lr={LR} img={IMG} device=cpu")

    model = resnet18(weights=ResNet18_Weights.DEFAULT)
    model.fc = nn.Linear(model.fc.in_features, len(classes))
    criterion = nn.CrossEntropyLoss(label_smoothing=0.05)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)

    history, best_acc, preds, labels = [], 0.0, [], []
    for epoch in range(1, EPOCHS + 1):
        started = time.time()
        model.train()
        running, correct, total = 0.0, 0, 0
        for x, y in train_loader:
            optimizer.zero_grad()
            out = model(x)
            loss = criterion(out, y)
            loss.backward()
            optimizer.step()
            running += loss.item() * x.size(0)
            correct += (out.argmax(1) == y).sum().item()
            total += x.size(0)
        scheduler.step()
        val_loss, val_acc, preds, labels = evaluate(model, val_loader, criterion)
        history.append({
            "epoch": epoch,
            "train_loss": round(running / total, 4),
            "train_acc": round(correct / total, 4),
            "val_loss": round(val_loss, 4),
            "val_acc": round(val_acc, 4),
            "seconds": round(time.time() - started, 1),
        })
        log(f"epoch {epoch}: train_loss={running / total:.4f} train_acc={correct / total:.4f} "
            f"val_loss={val_loss:.4f} val_acc={val_acc:.4f}")
        with open(RUNS / "history.json", "w", encoding="utf-8") as f:
            json.dump({"classes": classes, "history": history}, f, ensure_ascii=False, indent=2)
        if val_acc >= best_acc:
            best_acc = val_acc
            torch.save({"state_dict": model.state_dict(), "classes": classes}, RUNS / "best.pt")
            log(f"saved best checkpoint, val_acc={val_acc:.4f}")

    cm = np.zeros((len(classes), len(classes)), dtype=int)
    for t, p in zip(labels, preds):
        cm[t, p] += 1
    plot(history, classes, cm)
    log(f"finished. best_val_acc={best_acc:.4f}")
    LOG.close()


if __name__ == "__main__":
    main()
