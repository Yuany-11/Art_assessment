"""画风分类模型训练：ImageNet 预训练 ResNet18 微调。

用法：python train.py
产出：runs/ 下的 train_log.txt、history.json、curves.png、confusion_matrix.png、best.pt
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
from torch.utils.data import DataLoader, Subset
from torchvision import datasets, transforms
from torchvision.models import ResNet18_Weights, resnet18

HERE = Path(__file__).resolve().parent
ROOT = Path(os.getenv("ART_ROOT", HERE.parents[2]))
DATA = str(Path(os.getenv("ART_DATA", ROOT / "data")) / "01_raw" / "wikiart")
RUNS = str(Path(os.getenv("ART_WEIGHTS", ROOT / "weights")) / "style")
EPOCHS = 10
BATCH = 32
LR = 3e-4
SEED = 42
IMG = 160
PATIENCE = 3

torch.manual_seed(SEED)
np.random.seed(SEED)
torch.set_num_threads(os.cpu_count() or 4)
os.makedirs(RUNS, exist_ok=True)
LOG = open(os.path.join(RUNS, "train_log.txt"), "a", encoding="utf-8")


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    LOG.write(line + "\n")
    LOG.flush()


def build():
    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(IMG, scale=(0.6, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(10),
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
    full = datasets.ImageFolder(DATA, transform=train_tf)
    targets = np.array([s[1] for s in full.samples])
    rng = np.random.default_rng(SEED)
    train_idx, val_idx = [], []
    for cls in np.unique(targets):
        cls_idx = rng.permutation(np.where(targets == cls)[0])
        cut = max(1, int(len(cls_idx) * 0.2))
        val_idx.extend(cls_idx[:cut].tolist())
        train_idx.extend(cls_idx[cut:].tolist())
    train_ds = Subset(full, train_idx)
    val_base = datasets.ImageFolder(DATA, transform=val_tf)
    val_ds = Subset(val_base, val_idx)
    return train_ds, val_ds, full.classes, targets, val_idx


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


def plot_curves(history, classes, cm):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    epochs = [h["epoch"] for h in history]
    axes[0].plot(epochs, [h["train_loss"] for h in history], "o-", label="train loss")
    axes[0].plot(epochs, [h["val_loss"] for h in history], "s-", label="val loss")
    axes[0].set_xlabel("epoch")
    axes[0].set_ylabel("loss")
    axes[0].set_title("Loss")
    axes[0].grid(alpha=0.3)
    axes[0].legend()

    axes[1].plot(epochs, [h["train_acc"] for h in history], "o-", label="train acc")
    axes[1].plot(epochs, [h["val_acc"] for h in history], "s-", label="val acc")
    axes[1].set_ylim(0, 1.02)
    axes[1].set_xlabel("epoch")
    axes[1].set_ylabel("accuracy")
    axes[1].set_title("Accuracy")
    axes[1].grid(alpha=0.3)
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(os.path.join(RUNS, "curves.png"), dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(classes)))
    ax.set_yticks(range(len(classes)))
    ax.set_xticklabels(classes, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(classes, fontsize=8)
    ax.set_xlabel("predicted")
    ax.set_ylabel("true")
    ax.set_title("Confusion Matrix (val)")
    for i in range(len(classes)):
        for j in range(len(classes)):
            if cm[i, j]:
                ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig.savefig(os.path.join(RUNS, "confusion_matrix.png"), dpi=150)
    plt.close(fig)


def main():
    train_ds, val_ds, classes, targets, val_idx = build()
    log(f"dataset: {len(train_ds)} train / {len(val_ds)} val, classes={classes}")
    log(f"class counts(all)={dict(Counter(targets.tolist()))}")
    log(f"config: epochs={EPOCHS} batch={BATCH} lr={LR} img={IMG} device=cpu threads={torch.get_num_threads()}")

    train_loader = DataLoader(train_ds, batch_size=BATCH, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=BATCH, shuffle=False, num_workers=0)

    model = resnet18(weights=ResNet18_Weights.DEFAULT)
    model.fc = nn.Linear(model.fc.in_features, len(classes))
    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)

    history, best_acc, stale = [], 0.0, 0
    for epoch in range(1, EPOCHS + 1):
        started = time.time()
        model.train()
        running, correct, total = 0.0, 0, 0
        for step, (x, y) in enumerate(train_loader, 1):
            optimizer.zero_grad()
            out = model(x)
            loss = criterion(out, y)
            loss.backward()
            optimizer.step()
            running += loss.item() * x.size(0)
            correct += (out.argmax(1) == y).sum().item()
            total += x.size(0)
            if step % 10 == 0:
                log(f"epoch {epoch} step {step}/{len(train_loader)} loss={running / total:.4f} acc={correct / total:.4f}")
        scheduler.step()
        train_loss, train_acc = running / total, correct / total
        val_loss, val_acc, preds, labels = evaluate(model, val_loader, criterion)
        elapsed = time.time() - started
        history.append({
            "epoch": epoch,
            "train_loss": round(train_loss, 4),
            "train_acc": round(train_acc, 4),
            "val_loss": round(val_loss, 4),
            "val_acc": round(val_acc, 4),
            "seconds": round(elapsed, 1),
        })
        log(f"epoch {epoch} done: train_loss={train_loss:.4f} train_acc={train_acc:.4f} "
            f"val_loss={val_loss:.4f} val_acc={val_acc:.4f} time={elapsed:.1f}s")
        with open(os.path.join(RUNS, "history.json"), "w", encoding="utf-8") as f:
            json.dump({"classes": classes, "history": history}, f, ensure_ascii=False, indent=2)
        if val_acc > best_acc:
            best_acc = val_acc
            stale = 0
            torch.save({"state_dict": model.state_dict(), "classes": classes}, os.path.join(RUNS, "best.pt"))
            log(f"saved best checkpoint, val_acc={val_acc:.4f}")
        else:
            stale += 1
            if stale >= PATIENCE:
                log(f"early stop: no improvement for {PATIENCE} epochs")
                break

    cm = np.zeros((len(classes), len(classes)), dtype=int)
    for t, p in zip(labels, preds):
        cm[t, p] += 1
    plot_curves(history, classes, cm)
    log(f"finished. best_val_acc={best_acc:.4f}. curves -> runs/curves.png, cm -> runs/confusion_matrix.png")
    LOG.close()


if __name__ == "__main__":
    main()
