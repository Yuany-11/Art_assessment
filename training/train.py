#!/usr/bin/env python3
"""Train the four-head music tagger on a labelled manifest.

The manifest is produced by ``training/label_dataset.py``.  Every track carries
soft genre/emotion targets, a key-derived mode label and a beat-tracked BPM,
each with a confidence weight; missing labels are masked instead of guessed.

What this script adds over the original trainer
-----------------------------------------------
* v3 backbone by default: attention (mean/std/max) pooling, stochastic depth,
  residual classifier refinement and a soft-argmax BPM head
  (``--arch v3``; ``v4`` adds a tempo autocorrelation branch, ``v2`` and the
  legacy ``v1`` remain available)
* soft-target cross entropy, label smoothing, mixup and SpecAugment
* inverse-frequency weighted sampling for rare genres/emotions
* AdamW + linear warmup + cosine decay, gradient clipping
* mixed precision on CUDA, EMA weights, early stopping
* checkpoint metadata consumed directly by ``training/infer.py`` / ``score.py``
* resumable ``last_model.pt`` and best-only ``best_model.pt``

Usage
-----
    python training/train.py --manifest training/data/manifest.jsonl --device cuda

    # resume
    python training/train.py --manifest training/data/manifest.jsonl \
        --out-dir training/runs/20261027-120000 --resume latest

    # warm-start from an older checkpoint (shape-checked, partial load)
    python training/train.py --manifest training/data/manifest.jsonl \
        --init-weights training/runs/20261026-120656/best_model.pt
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import json
import math
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

try:
    from .augment import AugmentConfig
    from .dataset import (
        MusicDataset,
        compute_bpm_stats,
        infer_layout,
        load_manifest,
        make_weighted_sampler,
    )
    from .early_stopping import EarlyStopping
    from .features import N_CHROMA, N_MELS, load_cache
    from .losses import TASK_NAMES, TaskBalancer
    from .model import build_model, load_weights
except ImportError:  # executed as a top-level module from training/
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from augment import AugmentConfig  # type: ignore
    from dataset import (  # type: ignore
        MusicDataset,
        compute_bpm_stats,
        infer_layout,
        load_manifest,
        make_weighted_sampler,
    )
    from early_stopping import EarlyStopping  # type: ignore
    from features import N_CHROMA, N_MELS, load_cache  # type: ignore
    from losses import TASK_NAMES, TaskBalancer  # type: ignore
    from model import build_model, load_weights  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = PROJECT_ROOT / "training" / "runs"
TAXONOMY_PATH = PROJECT_ROOT / "training" / "labels" / "taxonomy.json"

GENRE_FALLBACK = [
    "Blues",
    "Classical",
    "Electronic",
    "Experimental",
    "Folk",
    "Funk/Soul",
    "Hip-Hop",
    "Horror",
    "Jazz",
    "Pop",
    "Rock",
    "Soundtrack",
    "World",
]
EMOTION_FALLBACK = ["calm", "happy", "sad", "tense"]
EMOTION_CN_FALLBACK = {"calm": "平静", "happy": "欢快", "sad": "悲伤", "tense": "紧张"}
MODE_CN_FALLBACK = {"major": "大调", "minor": "小调"}
SPLIT_ALIASES = {
    "train": "train",
    "training": "train",
    "val": "val",
    "valid": "val",
    "validation": "val",
    "test": "test",
    "testing": "test",
}


# ---------------------------------------------------------------------------
# small utilities
# ---------------------------------------------------------------------------
def _json_default(value: Any) -> Any:
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serialisable: {type(value)!r}")


def write_json(path: Path, payload: Any) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    tmp.replace(path)


def _cpu_state(state: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
    # clone() matters on CPU: .cpu() there returns the live parameter/buffer,
    # which would keep mutating after we snapshot the best epoch.
    return {key: value.detach().to("cpu").clone() for key, value in state.items()}


def _clean_state(state: Dict[str, Any]) -> Dict[str, Any]:
    if not state:
        return state
    for prefix in ("module.", "model."):
        if state and all(str(k).startswith(prefix) for k in state):
            state = {str(k)[len(prefix) :]: v for k, v in state.items()}
    return state


def _load_taxonomy_labels() -> Tuple[List[str], List[str], Dict[str, str], Dict[str, str]]:
    genres, emotions = GENRE_FALLBACK, EMOTION_FALLBACK
    emotion_cn, mode_cn = EMOTION_CN_FALLBACK, MODE_CN_FALLBACK
    try:
        payload = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
        genres = list(payload.get("genres") or genres)
        emotions = list(payload.get("emotions") or emotions)
        emotion_cn = dict(payload.get("emotion_cn") or emotion_cn)
        mode_cn = dict(payload.get("mode_cn") or mode_cn)
    except (OSError, ValueError):
        pass
    return genres, emotions, emotion_cn, mode_cn


def _resolve_cache(record: Dict[str, Any], manifest_dir: Path) -> Path:
    cache = Path(str(record.get("cache") or ""))
    return cache if cache.is_absolute() else manifest_dir / cache


def _split_records(
    records: Sequence[Dict[str, Any]], manifest_dir: Path
) -> Tuple[Dict[str, List[Dict[str, Any]]], int]:
    buckets: Dict[str, List[Dict[str, Any]]] = {"train": [], "val": [], "test": []}
    missing = 0
    for record in records:
        cache = _resolve_cache(record, manifest_dir)
        if not record.get("cache") or not cache.is_file():
            missing += 1
            continue
        raw = str(record.get("split") or "train").lower()
        split = SPLIT_ALIASES.get(raw, "train")
        record["_cache_path"] = str(cache)
        buckets[split].append(record)
    return buckets, missing


def _limit(records: List[Dict[str, Any]], limit: int, seed: int) -> List[Dict[str, Any]]:
    if limit and len(records) > limit:
        rng = random.Random(seed)
        return rng.sample(records, limit)
    return records


def make_loader(
    dataset: MusicDataset,
    *,
    batch_size: int,
    workers: int,
    shuffle: bool,
    sampler=None,
    pin_memory: bool,
    drop_last: bool,
) -> DataLoader:
    kwargs: Dict[str, Any] = {
        "batch_size": batch_size,
        "shuffle": shuffle if sampler is None else False,
        "sampler": sampler,
        "num_workers": workers,
        "pin_memory": pin_memory,
        "drop_last": drop_last,
        "persistent_workers": workers > 0,
    }
    if workers > 0:
        kwargs["prefetch_factor"] = 2
    return DataLoader(dataset, **kwargs)


# ---------------------------------------------------------------------------
# EMA / losses
# ---------------------------------------------------------------------------
class ModelEMA:
    def __init__(self, model: torch.nn.Module, decay: float = 0.999):
        self.decay = float(decay)
        self.module = copy.deepcopy(model).eval()
        for parameter in self.module.parameters():
            parameter.requires_grad_(False)

    @torch.no_grad()
    def update(self, model: torch.nn.Module, step: int) -> None:
        decay = min(self.decay, (1.0 + step) / (10.0 + step))
        source = model.state_dict()
        for key, shadow in self.module.state_dict().items():
            value = source.get(key)
            if value is None or not shadow.dtype.is_floating_point:
                continue
            shadow.mul_(decay).add_(value.detach(), alpha=1.0 - decay)

    def state_dict(self) -> Dict[str, torch.Tensor]:
        return self.module.state_dict()

    def load_state_dict(self, state: Dict[str, torch.Tensor]) -> None:
        self.module.load_state_dict(state, strict=False)


def _soft_ce(
    logits: torch.Tensor,
    target: torch.Tensor,
    mask: torch.Tensor,
    weight: torch.Tensor,
    label_smoothing: float,
) -> torch.Tensor:
    classes = logits.shape[-1]
    if label_smoothing > 0:
        target = target * (1.0 - label_smoothing) + label_smoothing / classes
    log_probs = F.log_softmax(logits, dim=-1)
    per_sample = -(target * log_probs).sum(dim=-1)
    denom = (mask * weight).sum().clamp_min(1e-6)
    return (per_sample * mask * weight).sum() / denom


def _bpm_loss(
    pred: torch.Tensor,
    target: torch.Tensor,
    mask: torch.Tensor,
    weight: torch.Tensor,
) -> torch.Tensor:
    per_sample = F.smooth_l1_loss(pred, target, beta=0.15, reduction="none")
    denom = (mask * weight).sum().clamp_min(1e-6)
    return (per_sample * mask * weight).sum() / denom


def compute_task_losses(
    logits: Dict[str, torch.Tensor],
    batch: Dict[str, Any],
    *,
    bpm_mean: float,
    bpm_std: float,
    label_smoothing: float,
) -> Dict[str, torch.Tensor]:
    """四个任务的**未加权**损失，供动态权重（TaskBalancer）使用。"""
    genre = _soft_ce(
        logits["genre"],
        batch["genre"],
        batch["genre_mask"],
        batch["genre_weight"],
        label_smoothing,
    )
    emotion = _soft_ce(
        logits["emotion"],
        batch["emotion"],
        batch["emotion_mask"],
        batch["emotion_weight"],
        label_smoothing,
    )

    if "mode_soft" in batch:
        mode_target = batch["mode_soft"]
    else:
        mode_target = F.one_hot(batch["mode"], num_classes=logits["mode"].shape[-1]).float()
    mode = _soft_ce(
        logits["mode"],
        mode_target,
        batch["mode_mask"],
        batch["mode_weight"],
        0.0,
    )

    bpm_target = (batch["bpm"] - bpm_mean) / max(bpm_std, 1e-3)
    bpm = _bpm_loss(logits["bpm"], bpm_target, batch["bpm_mask"], batch["bpm_weight"])

    return {"genre": genre, "emotion": emotion, "mode": mode, "bpm": bpm}


def compute_losses(
    logits: Dict[str, torch.Tensor],
    batch: Dict[str, Any],
    *,
    bpm_mean: float,
    bpm_std: float,
    label_smoothing: float,
    loss_weights: Dict[str, float],
) -> Tuple[torch.Tensor, Dict[str, float]]:
    """固定权重总损失 + 各任务数值，验证/测试阶段统一走这里。

    验证 loss 必须用固定权重，否则 “fixed → uncertainty” 之后跨 epoch 不可比，
    早停和日志都会失真。
    """
    tasks = compute_task_losses(
        logits,
        batch,
        bpm_mean=bpm_mean,
        bpm_std=bpm_std,
        label_smoothing=label_smoothing,
    )
    total = (
        loss_weights["genre"] * tasks["genre"]
        + loss_weights["emotion"] * tasks["emotion"]
        + loss_weights["mode"] * tasks["mode"]
        + loss_weights["bpm"] * tasks["bpm"]
    )
    return total, {key: float(value.detach()) for key, value in tasks.items()}


def mixup_batch(
    batch: Dict[str, Any], alpha: float, rng: random.Random
) -> Dict[str, Any]:
    """Mix features and soft targets; masks require both sources to be valid."""
    batch = dict(batch)
    lam = float(rng.betavariate(alpha, alpha))
    size = batch["mel"].shape[0]
    perm = torch.randperm(size, device=batch["mel"].device)

    for key in ("mel", "chroma", "genre", "emotion", "bpm"):
        batch[key] = lam * batch[key] + (1.0 - lam) * batch[key][perm]

    mode_soft = F.one_hot(
        batch["mode"], num_classes=batch["mode_soft_classes"]
    ).float()
    batch["mode_soft"] = lam * mode_soft + (1.0 - lam) * mode_soft[perm]

    for key in ("genre_mask", "emotion_mask", "mode_mask", "bpm_mask"):
        batch[key] = batch[key] * batch[key][perm]
    for key in ("genre_weight", "emotion_weight", "mode_weight", "bpm_weight"):
        batch[key] = 0.5 * (batch[key] + batch[key][perm])
    return batch


# ---------------------------------------------------------------------------
# metrics / evaluation
# ---------------------------------------------------------------------------
def _f1(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    if y_true.size == 0:
        return 0.0
    try:
        from sklearn.metrics import f1_score

        return float(f1_score(y_true, y_pred, average="macro", zero_division=0))
    except ImportError:
        classes = np.unique(y_true)
        scores = []
        for label in classes:
            tp = float(np.sum((y_pred == label) & (y_true == label)))
            fp = float(np.sum((y_pred == label) & (y_true != label)))
            fn = float(np.sum((y_pred != label) & (y_true == label)))
            scores.append(2 * tp / max(2 * tp + fp + fn, 1e-9))
        return float(np.mean(scores)) if scores else 0.0


def _combined(metrics: Dict[str, float]) -> float:
    bpm_score = (
        max(0.0, 1.0 - metrics["bpm_mae"] / 60.0) if metrics.get("n_bpm") else 0.0
    )
    return float(
        0.35 * metrics["genre_f1"]
        + 0.25 * metrics["emotion_f1"]
        + 0.20 * metrics["mode_f1"]
        + 0.20 * bpm_score
    )


@torch.no_grad()
def evaluate(
    model: torch.nn.Module,
    loader: DataLoader,
    device: torch.device,
    *,
    bpm_mean: float,
    bpm_std: float,
    label_smoothing: float,
    loss_weights: Dict[str, float],
    n_genres: int,
    n_emotions: int,
    amp: bool,
    max_batches: int = 0,
) -> Dict[str, Any]:
    model.eval()
    loss_sum = 0.0
    task_sums = {"genre": 0.0, "emotion": 0.0, "mode": 0.0, "bpm": 0.0}
    batches = 0

    genre_true: List[int] = []
    genre_pred: List[int] = []
    emotion_true: List[int] = []
    emotion_pred: List[int] = []
    mode_true: List[int] = []
    mode_pred: List[int] = []
    bpm_true: List[float] = []
    bpm_pred: List[float] = []

    for index, batch in enumerate(loader):
        if max_batches and index >= max_batches:
            break
        mel = batch["mel"].to(device, non_blocking=True)
        chroma = batch["chroma"].to(device, non_blocking=True)
        moved = {key: value.to(device) if torch.is_tensor(value) else value for key, value in batch.items()}
        moved["mel"], moved["chroma"] = mel, chroma
        with (
            torch.autocast(device_type="cuda", dtype=torch.float16)
            if amp
            else contextlib.nullcontext()
        ):
            logits = model(mel, chroma)
            loss, task_losses = compute_losses(
                logits,
                moved,
                bpm_mean=bpm_mean,
                bpm_std=bpm_std,
                label_smoothing=label_smoothing,
                loss_weights=loss_weights,
            )
        loss_sum += float(loss)
        for key in task_sums:
            task_sums[key] += task_losses[key]
        batches += 1

        genre_m = moved["genre_mask"].bool()
        if genre_m.any():
            true_idx = moved["genre"].argmax(dim=-1)[genre_m]
            pred_idx = logits["genre"].argmax(dim=-1)[genre_m]
            genre_true.extend(true_idx.int().cpu().tolist())
            genre_pred.extend(pred_idx.int().cpu().tolist())

        emotion_m = moved["emotion_mask"].bool()
        if emotion_m.any():
            true_idx = moved["emotion"].argmax(dim=-1)[emotion_m]
            pred_idx = logits["emotion"].argmax(dim=-1)[emotion_m]
            emotion_true.extend(true_idx.int().cpu().tolist())
            emotion_pred.extend(pred_idx.int().cpu().tolist())

        mode_m = moved["mode_mask"].bool()
        if mode_m.any():
            target = moved.get("mode_soft")
            if target is None:
                target = F.one_hot(moved["mode"], num_classes=2).float()
            true_idx = target.argmax(dim=-1)[mode_m]
            pred_idx = logits["mode"].argmax(dim=-1)[mode_m]
            mode_true.extend(true_idx.int().cpu().tolist())
            mode_pred.extend(pred_idx.int().cpu().tolist())

        bpm_m = moved["bpm_mask"].bool()
        if bpm_m.any():
            real = logits["bpm"][bpm_m] * bpm_std + bpm_mean
            bpm_true.extend(moved["bpm"][bpm_m].cpu().tolist())
            bpm_pred.extend(real.cpu().tolist())

    count = max(1, batches)
    genre_true_a = np.asarray(genre_true, dtype=np.int64)
    genre_pred_a = np.asarray(genre_pred, dtype=np.int64)
    emotion_true_a = np.asarray(emotion_true, dtype=np.int64)
    emotion_pred_a = np.asarray(emotion_pred, dtype=np.int64)
    mode_true_a = np.asarray(mode_true, dtype=np.int64)
    mode_pred_a = np.asarray(mode_pred, dtype=np.int64)
    bpm_true_a = np.asarray(bpm_true, dtype=np.float64)
    bpm_pred_a = np.asarray(bpm_pred, dtype=np.float64)

    metrics = {
        "loss": round(loss_sum / count, 4),
        "genre_loss": round(task_sums["genre"] / count, 4),
        "emotion_loss": round(task_sums["emotion"] / count, 4),
        "mode_loss": round(task_sums["mode"] / count, 4),
        "bpm_loss": round(task_sums["bpm"] / count, 4),
        "genre_acc": round(float(np.mean(genre_true_a == genre_pred_a)), 4)
        if genre_true_a.size
        else 0.0,
        "genre_f1": round(_f1(genre_true_a, genre_pred_a), 4),
        "emotion_acc": round(float(np.mean(emotion_true_a == emotion_pred_a)), 4)
        if emotion_true_a.size
        else 0.0,
        "emotion_f1": round(_f1(emotion_true_a, emotion_pred_a), 4),
        "mode_acc": round(float(np.mean(mode_true_a == mode_pred_a)), 4)
        if mode_true_a.size
        else 0.0,
        "mode_f1": round(_f1(mode_true_a, mode_pred_a), 4),
        "bpm_mae": round(float(np.mean(np.abs(bpm_true_a - bpm_pred_a))), 2)
        if bpm_true_a.size
        else 0.0,
        "n_genre": int(genre_true_a.size),
        "n_emotion": int(emotion_true_a.size),
        "n_mode": int(mode_true_a.size),
        "n_bpm": int(bpm_true_a.size),
    }
    metrics["combined"] = round(_combined(metrics), 4)
    return metrics


# ---------------------------------------------------------------------------
# checkpoint IO
# ---------------------------------------------------------------------------
def save_checkpoint(
    path: Path,
    state: Dict[str, torch.Tensor],
    *,
    arch: str,
    config: Dict[str, Any],
    genres: Sequence[str],
    emotions: Sequence[str],
    emotion_cn: Dict[str, str],
    mode_cn: Dict[str, str],
    bpm_mean: float,
    bpm_std: float,
    epoch: int,
    metrics: Dict[str, Any],
    ema: bool,
) -> None:
    tmp = path.with_name(path.name + ".tmp")
    torch.save(
        {
            "model": _cpu_state(state),
            "arch": arch,
            "config": config,
            "genre_labels": list(genres),
            "emotion_labels": list(emotions),
            "emotion_cn": dict(emotion_cn),
            "mode_cn": dict(mode_cn),
            "bpm_mean": float(bpm_mean),
            "bpm_std": float(bpm_std),
            "epoch": int(epoch),
            "metrics": metrics,
            "ema": bool(ema),
        },
        tmp,
    )
    tmp.replace(path)


def save_resume(
    path: Path,
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
    scheduler: torch.optim.lr_scheduler.LRScheduler,
    ema: Optional[ModelEMA],
    *,
    arch: str,
    config: Dict[str, Any],
    genres: Sequence[str],
    emotions: Sequence[str],
    emotion_cn: Dict[str, str],
    mode_cn: Dict[str, str],
    bpm_mean: float,
    bpm_std: float,
    epoch: int,
    best: float,
    best_epoch: int,
    stale: int,
    history: List[Dict[str, Any]],
    early_stopping: Optional[Dict[str, Any]] = None,
    balancer: Optional[Dict[str, Any]] = None,
) -> None:
    tmp = path.with_name(path.name + ".tmp")
    torch.save(
        {
            "model": _cpu_state(model.state_dict()),
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(),
            "ema": _cpu_state(ema.state_dict()) if ema is not None else None,
            "arch": arch,
            "config": config,
            "genre_labels": list(genres),
            "emotion_labels": list(emotions),
            "emotion_cn": dict(emotion_cn),
            "mode_cn": dict(mode_cn),
            "bpm_mean": float(bpm_mean),
            "bpm_std": float(bpm_std),
            "epoch": int(epoch),
            "best": float(best),
            "best_epoch": int(best_epoch),
            "stale": int(stale),
            "history": history,
            # 早停计数 + 动态损失权重，断点续训时原样恢复
            "early_stopping": early_stopping,
            "balancer": (
                {
                    key: value.detach().to("cpu").clone()
                    for key, value in balancer.items()
                    if torch.is_tensor(value)
                }
                if balancer
                else None
            ),
        },
        tmp,
    )
    tmp.replace(path)


def _resolve_latest_best() -> Optional[Path]:
    candidates = sorted(
        RUNS_DIR.glob("*/best_model.pt"), key=lambda p: p.stat().st_mtime
    )
    return candidates[-1] if candidates else None


def _resolve_latest_last() -> Optional[Path]:
    candidates = sorted(
        RUNS_DIR.glob("*/last_model.pt"), key=lambda p: p.stat().st_mtime
    )
    return candidates[-1] if candidates else None


def _amp_context(device: torch.device, enabled: bool):
    if not enabled:
        return contextlib.nullcontext()
    return torch.autocast(device_type=device.type, dtype=torch.float16)


def _make_scaler(enabled: bool):
    if not enabled:
        return None
    try:
        return torch.amp.GradScaler("cuda", enabled=True)
    except (AttributeError, TypeError):
        return torch.cuda.amp.GradScaler(enabled=True)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    data = parser.add_argument_group("data")
    data.add_argument("--manifest", required=True, help="training/data/manifest.jsonl")
    data.add_argument("--out-dir", default="", help="run directory (default: training/runs/<timestamp>)")
    data.add_argument(
        "--arch",
        choices=("v1", "v2", "v3", "v4"),
        default="v3",
        help="v3 = attentive pooling + stochastic depth + soft-argmax BPM (default); "
        "v4 = v3 + explicit tempo autocorrelation branch (fixes BPM)",
    )
    data.add_argument("--clip-seconds", type=float, default=30.0, help="validation/test crop length")
    data.add_argument("--crop-seconds", type=float, default=12.0, help="random training crop length")
    data.add_argument("--tta-crops", type=int, default=3, help="stored in checkpoint for inference")
    data.add_argument("--mode-min-confidence", type=float, default=0.35)
    data.add_argument("--bpm-min-confidence", type=float, default=0.15)
    data.add_argument("--limit-train", type=int, default=0, help="debug: cap training tracks")
    data.add_argument("--limit-val", type=int, default=0, help="debug: cap validation tracks")

    optim = parser.add_argument_group("optimisation")
    optim.add_argument("--epochs", type=int, default=80)
    optim.add_argument("--batch-size", type=int, default=64)
    optim.add_argument("--lr", type=float, default=1e-3)
    optim.add_argument("--weight-decay", type=float, default=1e-4)
    optim.add_argument("--warmup-epochs", type=float, default=2.0)
    optim.add_argument("--min-lr-ratio", type=float, default=0.02)
    optim.add_argument("--grad-clip", type=float, default=5.0)
    optim.add_argument("--label-smoothing", type=float, default=0.05)
    optim.add_argument("--loss-genre", type=float, default=1.0)
    optim.add_argument("--loss-emotion", type=float, default=0.6)
    optim.add_argument("--loss-mode", type=float, default=0.4)
    optim.add_argument("--loss-bpm", type=float, default=0.3)
    optim.add_argument("--sampler", choices=("none", "sqrt", "inverse"), default="sqrt")
    optim.add_argument(
        "--loss-balance",
        choices=("fixed", "uncertainty", "dwa"),
        default="fixed",
        help="fixed = --loss-* 给定权重；uncertainty = 学习每任务不确定性；"
        "dwa = 按 loss 下降速度动态加权",
    )
    optim.add_argument(
        "--dwa-temperature", type=float, default=2.0, help="DWA softmax 温度"
    )
    optim.add_argument("--no-augment", dest="augment", action="store_false")
    optim.add_argument("--freq-mask", type=int, default=16)
    optim.add_argument("--time-mask", type=int, default=48)
    optim.add_argument("--n-freq-masks", type=int, default=2)
    optim.add_argument("--n-time-masks", type=int, default=2)
    optim.add_argument(
        "--noise-prob", type=float, default=0.30, help="高斯噪声的概率（0 关闭）"
    )
    optim.add_argument(
        "--noise-std", type=float, default=0.02, help="标准化后特征的噪声标准差"
    )
    optim.add_argument(
        "--roll-prob", type=float, default=0.0, help="时间轴循环平移的概率"
    )
    optim.add_argument(
        "--stretch-prob",
        type=float,
        default=0.0,
        help="变速增强概率（BPM 标签会同步缩放）",
    )
    optim.add_argument(
        "--stretch-min", type=float, default=0.9, help="变速增强的最小倍率"
    )
    optim.add_argument(
        "--stretch-max", type=float, default=1.1, help="变速增强的最大倍率"
    )
    optim.add_argument("--mixup-alpha", type=float, default=0.4)
    optim.add_argument("--mixup-prob", type=float, default=0.5)
    optim.add_argument("--ema-decay", type=float, default=0.999)
    optim.add_argument("--no-ema", dest="ema", action="store_false")
    optim.add_argument("--patience", type=int, default=15)
    optim.add_argument(
        "--early-stop-min-delta",
        type=float,
        default=1e-4,
        help="combined score 提升小于该值也算没有提升",
    )
    optim.add_argument("--device", default="auto")
    optim.add_argument("--workers", type=int, default=4)
    optim.add_argument("--threads", type=int, default=0)
    optim.add_argument("--seed", type=int, default=42)
    optim.add_argument("--amp", dest="amp", action="store_true", default=True)
    optim.add_argument("--no-amp", dest="amp", action="store_false")
    optim.add_argument("--resume", default="", help="last_model.pt path or 'latest'")
    optim.add_argument("--init-weights", default="", help="warm-start checkpoint or 'latest'")
    optim.add_argument("--no-test", dest="test", action="store_false")
    parser.set_defaults(augment=True, ema=True, test=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    start_time = time.time()

    seed = int(args.seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        # Ampere+ (RTX 3080) tensor cores: TF32 for fp32 matmuls/convolutions
        # and the fastest cuDNN kernels for the fixed input shape.
        torch.backends.cudnn.benchmark = True
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        torch.set_float32_matmul_precision("high")
    if args.threads > 0:
        torch.set_num_threads(args.threads)

    manifest = Path(args.manifest).expanduser().resolve()
    if not manifest.is_file():
        raise FileNotFoundError(
            f"manifest not found: {manifest}\n"
            "Run: python training/label_dataset.py --root data --workers 8"
        )
    manifest_dir = manifest.parent

    resume_path: Optional[Path] = None
    if args.resume:
        if args.resume.lower() == "latest":
            # Prefer the run directory the user explicitly pointed at; fall
            # back to the newest run under training/runs/.
            candidate = (
                Path(args.out_dir).expanduser().resolve() / "last_model.pt"
                if args.out_dir
                else None
            )
            if candidate is not None and candidate.is_file():
                resume_path = candidate
            else:
                resume_path = _resolve_latest_last()
        else:
            resume_path = Path(args.resume)
        if resume_path is None or not Path(resume_path).is_file():
            raise FileNotFoundError(f"resume checkpoint not found: {args.resume}")
        resume_path = Path(resume_path).resolve()

    if args.out_dir:
        out_dir = Path(args.out_dir).expanduser().resolve()
    elif resume_path is not None:
        out_dir = resume_path.parent
    else:
        out_dir = RUNS_DIR / time.strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = out_dir.name
    if not args.resume and (out_dir / "last_model.pt").exists():
        raise SystemExit(
            f"{out_dir} already contains a training run.\n"
            "Pass --resume latest to continue it, or choose a new --out-dir."
        )

    genres, emotions, emotion_cn, mode_cn = _load_taxonomy_labels()
    n_genres, n_emotions = len(genres), len(emotions)

    print(f"manifest : {manifest}")
    print(f"run      : {out_dir}")
    records = load_manifest(manifest)
    buckets, missing = _split_records(records, manifest_dir)
    if missing:
        print(f"warning  : skipped {missing} records with a missing feature cache")
    for split in ("train", "val", "test"):
        print(f"  {split:<6}: {len(buckets[split])} tracks")
    if not buckets["train"]:
        raise RuntimeError("no training tracks found (check cache paths / manifest)")
    if not buckets["val"]:
        raise RuntimeError("no validation tracks found; adjust the manifest split")
    if len(buckets["train"]) < 2:
        raise RuntimeError("need at least two training tracks")

    buckets["train"] = _limit(buckets["train"], args.limit_train, seed)
    buckets["val"] = _limit(buckets["val"], args.limit_val, seed + 1)
    if len(buckets["train"]) < 2:
        raise RuntimeError("need at least two training tracks (batch norm)")
    infer_layout(buckets["train"], n_genres, n_emotions)
    infer_layout(buckets["val"], n_genres, n_emotions)
    infer_layout(buckets["test"], n_genres, n_emotions)

    sample_mel, sample_chroma = load_cache(buckets["train"][0]["_cache_path"])
    n_mels, n_chroma = int(sample_mel.shape[0]), int(sample_chroma.shape[0])
    if (n_mels, n_chroma) != (N_MELS, N_CHROMA):
        print(f"warning  : cache layout is {n_mels} mel x {n_chroma} chroma")

    bpm_mean, bpm_std = compute_bpm_stats(buckets["train"])
    bpm_std = max(float(bpm_std), 1.0)
    print(f"bpm prior: mean {bpm_mean:.2f}, std {bpm_std:.2f}")

    augment_config = AugmentConfig(
        freq_mask_width=int(args.freq_mask),
        time_mask_width=int(args.time_mask),
        n_freq_masks=int(args.n_freq_masks),
        n_time_masks=int(args.n_time_masks),
        noise_prob=float(args.noise_prob),
        noise_std=float(args.noise_std),
        roll_prob=float(args.roll_prob),
        stretch_prob=float(args.stretch_prob),
        stretch_range=(float(args.stretch_min), float(args.stretch_max)),
    )
    train_set = MusicDataset(
        buckets["train"],
        manifest_dir=manifest_dir,
        crop_seconds=args.crop_seconds,
        train=True,
        augment=args.augment,
        seed=seed,
        mode_min_confidence=args.mode_min_confidence,
        bpm_min_confidence=args.bpm_min_confidence,
        n_genres=n_genres,
        n_emotions=n_emotions,
        freq_mask=args.freq_mask,
        time_mask=args.time_mask,
        augment_config=augment_config,
    )
    eval_crop = max(float(args.clip_seconds), float(args.crop_seconds))
    val_set = MusicDataset(
        buckets["val"],
        manifest_dir=manifest_dir,
        crop_seconds=eval_crop,
        train=False,
        augment=False,
        mode_min_confidence=args.mode_min_confidence,
        bpm_min_confidence=args.bpm_min_confidence,
        n_genres=n_genres,
        n_emotions=n_emotions,
    )
    test_set = (
        MusicDataset(
            buckets["test"],
            manifest_dir=manifest_dir,
            crop_seconds=eval_crop,
            train=False,
            augment=False,
            mode_min_confidence=args.mode_min_confidence,
            bpm_min_confidence=args.bpm_min_confidence,
            n_genres=n_genres,
            n_emotions=n_emotions,
        )
        if buckets["test"]
        else None
    )

    device = torch.device(
        ("cuda" if torch.cuda.is_available() else "cpu")
        if args.device == "auto"
        else args.device
    )
    use_amp = bool(args.amp and device.type == "cuda")
    print(f"device   : {device}" + (" (AMP)" if use_amp else ""))

    sampler = make_weighted_sampler(
        buckets["train"],
        damping=args.sampler,
        task="genre+emotion",
        seed=seed,
    )
    pin_memory = device.type == "cuda"
    train_loader = make_loader(
        train_set,
        batch_size=args.batch_size,
        workers=max(0, args.workers),
        shuffle=sampler is None,
        sampler=sampler,
        pin_memory=pin_memory,
        drop_last=len(train_set) > args.batch_size,
    )
    val_loader = make_loader(
        val_set,
        batch_size=args.batch_size,
        workers=max(0, args.workers),
        shuffle=False,
        pin_memory=pin_memory,
        drop_last=False,
    )
    test_loader = (
        make_loader(
            test_set,
            batch_size=args.batch_size,
            workers=max(0, args.workers),
            shuffle=False,
            pin_memory=pin_memory,
            drop_last=False,
        )
        if test_set is not None
        else None
    )

    model = build_model(args.arch, n_genres, n_emotions, 2).to(device)
    parameters = sum(p.numel() for p in model.parameters())
    print(f"model    : {args.arch}, {parameters / 1e6:.2f} M parameters")

    loss_weights = {
        "genre": float(args.loss_genre),
        "emotion": float(args.loss_emotion),
        "mode": float(args.loss_mode),
        "bpm": float(args.loss_bpm),
    }
    # 训练用的总损失由 balancer 合成；验证/测试仍用固定权重，保证跨 epoch 可比
    balancer = TaskBalancer(
        mode=args.loss_balance,
        weights=loss_weights,
        task_names=TASK_NAMES,
        dwa_temperature=args.dwa_temperature,
    ).to(device)
    print(f"loss     : {args.loss_balance}")
    config: Dict[str, Any] = {
        "run_id": run_id,
        "manifest": str(manifest),
        "arch": args.arch,
        "epochs": int(args.epochs),
        "batch_size": int(args.batch_size),
        "lr": float(args.lr),
        "weight_decay": float(args.weight_decay),
        "warmup_epochs": float(args.warmup_epochs),
        "min_lr_ratio": float(args.min_lr_ratio),
        "label_smoothing": float(args.label_smoothing),
        "mixup_alpha": float(args.mixup_alpha),
        "mixup_prob": float(args.mixup_prob),
        "sampler": args.sampler,
        "augment": bool(args.augment),
        "freq_mask": int(args.freq_mask),
        "time_mask": int(args.time_mask),
        "n_freq_masks": int(args.n_freq_masks),
        "n_time_masks": int(args.n_time_masks),
        "noise_prob": float(args.noise_prob),
        "noise_std": float(args.noise_std),
        "roll_prob": float(args.roll_prob),
        "stretch_prob": float(args.stretch_prob),
        "stretch_range": [float(args.stretch_min), float(args.stretch_max)],
        "loss_balance": args.loss_balance,
        "ema_decay": float(args.ema_decay) if args.ema else 0.0,
        "amp": use_amp,
        "device": str(device),
        "seed": seed,
        "clip_seconds": eval_crop,
        "train_crop_seconds": float(args.crop_seconds),
        "n_mels": n_mels,
        "n_chroma": n_chroma,
        "tta_crops": int(args.tta_crops),
        "bpm_mean": float(bpm_mean),
        "bpm_std": float(bpm_std),
        "loss_weights": loss_weights,
    }

    def trainable_parameters() -> List[torch.nn.Parameter]:
        params = list(model.parameters())
        # uncertainty 模式的 log 方差也要优化；fixed/dwa 没有可学习参数
        params.extend(p for p in balancer.parameters() if p.requires_grad)
        return params

    optimizer = torch.optim.AdamW(
        trainable_parameters(), lr=args.lr, weight_decay=args.weight_decay
    )
    steps_per_epoch = max(1, len(train_loader))
    total_steps = max(1, steps_per_epoch * int(args.epochs))
    warmup_steps = max(1, int(round(steps_per_epoch * float(args.warmup_epochs))))

    def lr_lambda(step: int) -> float:
        if step < warmup_steps:
            return (step + 1) / float(warmup_steps)
        progress = (step - warmup_steps) / float(max(1, total_steps - warmup_steps))
        progress = min(1.0, max(0.0, progress))
        cosine = 0.5 * (1.0 + math.cos(math.pi * progress))
        return args.min_lr_ratio + (1.0 - args.min_lr_ratio) * cosine

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)
    scaler = _make_scaler(use_amp)
    ema = ModelEMA(model, args.ema_decay) if args.ema and args.ema_decay > 0 else None

    start_epoch = 1
    best = -1.0
    best_epoch = 0
    stale = 0
    history: List[Dict[str, Any]] = []
    global_step = 0
    stopper = EarlyStopping(
        patience=int(args.patience),
        min_delta=float(args.early_stop_min_delta),
        mode="max",
        start_epoch=1,
    )

    if args.resume:
        payload = torch.load(str(resume_path), map_location="cpu", weights_only=False)
        if "optimizer" not in payload:
            raise SystemExit(
                "--resume expects a last_model.pt checkpoint (optimizer state); "
                "use --init-weights to warm-start from best_model.pt"
            )
        saved_arch = payload.get("arch")
        if saved_arch and saved_arch != args.arch:
            print(f"warning  : resume checkpoint arch={saved_arch}; using it")
            config["arch"] = saved_arch
            model = build_model(saved_arch, n_genres, n_emotions, 2).to(device)
            optimizer = torch.optim.AdamW(
                trainable_parameters(), lr=args.lr, weight_decay=args.weight_decay
            )
            scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)
            ema = ModelEMA(model, args.ema_decay) if ema is not None else None
        model.load_state_dict(_clean_state(payload["model"]), strict=False)
        if payload.get("balancer"):
            try:
                balancer.load_state_dict(payload["balancer"], strict=False)
            except (RuntimeError, ValueError) as exc:
                print(f"warning  : loss balancer state skipped ({exc})")
        if payload.get("optimizer"):
            try:
                optimizer.load_state_dict(payload["optimizer"])
            except (ValueError, RuntimeError) as exc:
                # 例如 fixed -> uncertainty：优化器参数组多了一组 log 方差
                print(f"warning  : optimizer state skipped ({exc})")
        if payload.get("scheduler"):
            scheduler.load_state_dict(payload["scheduler"])
        if ema is not None and payload.get("ema"):
            ema.load_state_dict(payload["ema"])
        start_epoch = int(payload.get("epoch", 0)) + 1
        best = float(payload.get("best", -1.0))
        best_epoch = int(payload.get("best_epoch", 0))
        stale = int(payload.get("stale", 0))
        history = list(payload.get("history") or [])
        loss_weights = dict(payload.get("config", {}).get("loss_weights") or loss_weights)
        config["loss_weights"] = loss_weights
        global_step = int(getattr(scheduler, "last_epoch", 0))
        if payload.get("early_stopping"):
            stopper.load_state_dict(payload["early_stopping"])
            best, best_epoch = stopper.best, stopper.best_epoch
            stale = stopper.counter
        else:
            stopper.load_state_dict(
                {"best": best, "best_epoch": best_epoch, "counter": stale}
            )
        print(
            f"resume   : {resume_path} (epoch {start_epoch - 1}, "
            f"best {best:.4f} @ {best_epoch})"
        )

    if start_epoch > int(args.epochs):
        raise SystemExit(
            f"checkpoint is already at epoch {start_epoch - 1}; "
            f"pass --epochs greater than {start_epoch - 1} to continue"
        )

    init_weights = args.init_weights
    if init_weights and not args.resume:
        if init_weights.lower() == "latest":
            init_path = _resolve_latest_best()
            if init_path is None:
                raise FileNotFoundError("no checkpoint found for --init-weights latest")
        else:
            init_path = Path(init_weights).expanduser()
        if not init_path.is_file():
            raise FileNotFoundError(f"init checkpoint not found: {init_path}")
        payload = torch.load(str(init_path), map_location="cpu", weights_only=False)
        state = payload.get("model") or payload.get("state_dict") or payload
        loaded, skipped = load_weights(model, _clean_state(state), verbose=False)
        print(f"warm-start: {init_path} ({loaded} tensors loaded, {skipped} skipped)")

    write_json(out_dir / "config.json", config)
    write_json(
        out_dir / "labels.json",
        {
            "genre": genres,
            "emotion": emotions,
            "mode": ["major", "minor"],
            "emotion_cn": emotion_cn,
            "mode_cn": mode_cn,
        },
    )

    best_state: Optional[Dict[str, torch.Tensor]] = None
    best_metrics: Optional[Dict[str, Any]] = None
    if args.resume and (out_dir / "best_model.pt").is_file():
        # Keep the earlier best checkpoint if the resumed epochs never beat it.
        previous_best = torch.load(
            str(out_dir / "best_model.pt"), map_location="cpu", weights_only=False
        )
        best_state = _cpu_state(previous_best["model"])
        best_metrics = previous_best.get("metrics")
    epochs_run = 0
    start_time = time.time()

    for epoch in range(start_epoch, int(args.epochs) + 1):
        epochs_run = epoch - start_epoch + 1
        train_set.set_epoch(epoch)
        model.train()
        epoch_start = time.time()
        running = 0.0
        running_tasks = {"genre": 0.0, "emotion": 0.0, "mode": 0.0, "bpm": 0.0}
        batches = 0

        try:
            from tqdm.auto import tqdm

            progress = tqdm(
                train_loader,
                desc=f"epoch {epoch}/{args.epochs}",
                dynamic_ncols=True,
                leave=False,
            )
        except ImportError:
            progress = train_loader

        for batch in progress:
            batch = dict(batch)
            batch["mode_soft_classes"] = 2
            mel = batch["mel"].to(device, non_blocking=True)
            chroma = batch["chroma"].to(device, non_blocking=True)
            batch = {
                key: value.to(device) if torch.is_tensor(value) else value
                for key, value in batch.items()
            }
            batch["mel"], batch["chroma"] = mel, chroma

            if args.mixup_prob > 0 and random.random() < args.mixup_prob:
                batch = mixup_batch(batch, args.mixup_alpha, random)

            optimizer.zero_grad(set_to_none=True)
            with _amp_context(device, use_amp):
                logits = model(batch["mel"], batch["chroma"])
                task_losses = compute_task_losses(
                    logits,
                    batch,
                    bpm_mean=bpm_mean,
                    bpm_std=bpm_std,
                    label_smoothing=args.label_smoothing,
                )
                # 有些 batch 可能出现某任务全被 mask（例如整批无情绪标注），
                # 此时该任务不参与总损失，也不产生梯度
                valid_tasks = {
                    "genre": bool(float(batch["genre_mask"].sum()) > 0),
                    "emotion": bool(float(batch["emotion_mask"].sum()) > 0),
                    "mode": bool(float(batch["mode_mask"].sum()) > 0),
                    "bpm": bool(float(batch["bpm_mask"].sum()) > 0),
                }
                loss = balancer(task_losses, valid_tasks)

            applied = True
            if scaler is not None:
                scale_before = scaler.get_scale()
                scaler.scale(loss).backward()
                if args.grad_clip > 0:
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
                scaler.step(optimizer)
                scaler.update()
                # GradScaler lowers its scale when a step is skipped for
                # inf/nan gradients; keep the LR schedule in sync with the
                # steps that were actually applied.
                applied = scaler.get_scale() >= scale_before
            else:
                loss.backward()
                if args.grad_clip > 0:
                    torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
                optimizer.step()

            if applied:
                scheduler.step()
            global_step += 1
            if ema is not None:
                ema.update(model, global_step)

            running += float(loss.detach())
            for key in running_tasks:
                running_tasks[key] += float(task_losses[key].detach().float())
            batches += 1
            if hasattr(progress, "set_postfix"):
                progress.set_postfix(
                    loss=f"{running / batches:.3f}",
                    lr=f"{scheduler.get_last_lr()[0]:.2e}",
                )

        eval_model = ema.module if ema is not None else model
        val_metrics = evaluate(
            eval_model,
            val_loader,
            device,
            bpm_mean=bpm_mean,
            bpm_std=bpm_std,
            label_smoothing=args.label_smoothing,
            loss_weights=loss_weights,
            n_genres=n_genres,
            n_emotions=n_emotions,
            amp=use_amp,
        )
        train_loss = running / max(1, batches)
        epoch_tasks = {
            key: value / max(1, batches) for key, value in running_tasks.items()
        }
        # DWA 用本 epoch 的平均任务 loss 决定下一轮的权重
        balancer.update_dwa(epoch_tasks)
        entry = {
            "epoch": epoch,
            "train_loss": round(train_loss, 4),
            "train_tasks": {key: round(value, 4) for key, value in epoch_tasks.items()},
            "task_weights": balancer.current_weights(),
            "lr": float(scheduler.get_last_lr()[0]),
            "seconds": round(time.time() - epoch_start, 1),
            **val_metrics,
        }
        history.append(entry)

        print(
            f"epoch {epoch:>3}/{args.epochs}  "
            f"train {train_loss:.4f}  val {val_metrics['loss']:.4f}  "
            f"genre {val_metrics['genre_acc']:.3f}/{val_metrics['genre_f1']:.3f}  "
            f"emotion {val_metrics['emotion_acc']:.3f}/{val_metrics['emotion_f1']:.3f}  "
            f"mode {val_metrics['mode_acc']:.3f}/{val_metrics['mode_f1']:.3f}  "
            f"bpm {val_metrics['bpm_mae']:.1f}  "
            f"score {val_metrics['combined']:.4f}  "
            f"({entry['seconds']:.0f}s)"
        )

        improved = stopper.step(float(val_metrics["combined"]), epoch)
        best = float(stopper.best)
        best_epoch = int(stopper.best_epoch)
        stale = int(stopper.counter)
        if improved:
            best_metrics = dict(val_metrics)
            best_state = _cpu_state(eval_model.state_dict())
            save_checkpoint(
                out_dir / "best_model.pt",
                eval_model.state_dict(),
                arch=config["arch"],
                config=config,
                genres=genres,
                emotions=emotions,
                emotion_cn=emotion_cn,
                mode_cn=mode_cn,
                bpm_mean=bpm_mean,
                bpm_std=bpm_std,
                epoch=epoch,
                metrics=best_metrics,
                ema=ema is not None,
            )
            print(f"  saved best (combined {best:.4f})")

        write_json(
            out_dir / "state.json",
            {
                "run_id": run_id,
                "epoch": epoch,
                "best_combined": best,
                "best_epoch": best_epoch,
                "stale_epochs": stale,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        )

        save_resume(
            out_dir / "last_model.pt",
            model,
            optimizer,
            scheduler,
            ema,
            arch=config["arch"],
            config=config,
            genres=genres,
            emotions=emotions,
            emotion_cn=emotion_cn,
            mode_cn=mode_cn,
            bpm_mean=bpm_mean,
            bpm_std=bpm_std,
            epoch=epoch,
            best=best,
            best_epoch=best_epoch,
            stale=stale,
            history=history,
            early_stopping=stopper.state_dict(),
            balancer=balancer.state_dict(),
        )

        if stopper.triggered:
            print(
                f"early stop: no improvement for {stale} epochs "
                f"(best {best:.4f} @ epoch {best_epoch})"
            )
            break

    if best_state is None:
        best_state = _cpu_state(model.state_dict())
        best_metrics = evaluate(
            model,
            val_loader,
            device,
            bpm_mean=bpm_mean,
            bpm_std=bpm_std,
            label_smoothing=args.label_smoothing,
            loss_weights=loss_weights,
            n_genres=n_genres,
            n_emotions=n_emotions,
            amp=use_amp,
        )
        save_checkpoint(
            out_dir / "best_model.pt",
            model.state_dict(),
            arch=config["arch"],
            config=config,
            genres=genres,
            emotions=emotions,
            emotion_cn=emotion_cn,
            mode_cn=mode_cn,
            bpm_mean=bpm_mean,
            bpm_std=bpm_std,
            epoch=int(args.epochs),
            metrics=best_metrics,
            ema=False,
        )

    test_metrics: Optional[Dict[str, Any]] = None
    if args.test and test_loader is not None and best_state is not None:
        test_model = build_model(config["arch"], n_genres, n_emotions, 2).to(device)
        test_model.load_state_dict(best_state, strict=False)
        test_metrics = evaluate(
            test_model,
            test_loader,
            device,
            bpm_mean=bpm_mean,
            bpm_std=bpm_std,
            label_smoothing=args.label_smoothing,
            loss_weights=loss_weights,
            n_genres=n_genres,
            n_emotions=n_emotions,
            amp=use_amp,
        )
        print(
            "test     : "
            f"genre {test_metrics['genre_acc']:.3f}/{test_metrics['genre_f1']:.3f}  "
            f"emotion {test_metrics['emotion_acc']:.3f}/{test_metrics['emotion_f1']:.3f}  "
            f"mode {test_metrics['mode_acc']:.3f}/{test_metrics['mode_f1']:.3f}  "
            f"bpm {test_metrics['bpm_mae']:.1f}  score {test_metrics['combined']:.4f}"
        )

    best_payload = torch.load(
        str(out_dir / "best_model.pt"), map_location="cpu", weights_only=False
    )
    best_ckpt_metrics = best_payload.get("metrics") or best_metrics or {}
    result = {
        "run_id": run_id,
        "device": str(device),
        "arch": config["arch"],
        "amp": use_amp,
        "train_seconds": round(time.time() - start_time, 1),
        "epochs_run": epochs_run,
        "epochs_planned": int(args.epochs),
        "best_epoch": int(best_payload.get("epoch", best_epoch)),
        "best_combined": round(float(best), 4),
        "validation": best_ckpt_metrics,
        "test": test_metrics,
        "history": history,
        "config": config,
        "dataset": {
            "total": len(records),
            "train": len(buckets["train"]),
            "val": len(buckets["val"]),
            "test": len(buckets["test"]),
            "genres": genres,
            "emotions": emotions,
        },
    }
    write_json(out_dir / "metrics.json", result)

    print(f"\ncheckpoint: {out_dir / 'best_model.pt'}")
    print(f"metrics   : {out_dir / 'metrics.json'}")
    print('score it  : python training/score.py "song.mp3" '
          f'--weights "{out_dir / "best_model.pt"}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
