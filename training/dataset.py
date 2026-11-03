"""Manifest-backed PyTorch dataset and sampling helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import torch
from torch.utils.data import Dataset, WeightedRandomSampler

try:
    from .augment import AugmentConfig, FeatureAugmenter
    from .features import (
        HOP_LENGTH,
        SR,
        crop_or_pad,
        load_cache,
        normalize_features,
        spec_augment,
    )
except ImportError:  # executed as a top-level module from training/
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from augment import AugmentConfig, FeatureAugmenter  # type: ignore
    from features import (  # type: ignore
        HOP_LENGTH,
        SR,
        crop_or_pad,
        load_cache,
        normalize_features,
        spec_augment,
    )

_GENRE_LABELS_FALLBACK = (
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
)
_EMOTION_LABELS_FALLBACK = ("calm", "happy", "sad", "tense")


def load_manifest(path: str | Path) -> List[Dict[str, Any]]:
    path = Path(path)
    records: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def frames_for(seconds: float, sr: int = SR, hop: int = HOP_LENGTH) -> int:
    return max(16, int(round(float(seconds) * sr / hop)))


class MusicDataset(Dataset):
    """Reads cached features; all labels missing on a task are masked."""

    def __init__(
        self,
        records: Sequence[Dict[str, Any]],
        *,
        manifest_dir: str | Path,
        crop_seconds: float = 12.0,
        train: bool = False,
        augment: bool = True,
        seed: int = 42,
        mode_min_confidence: float = 0.35,
        bpm_min_confidence: float = 0.15,
        n_genres: int = len(_GENRE_LABELS_FALLBACK),
        n_emotions: int = len(_EMOTION_LABELS_FALLBACK),
        freq_mask: int = 16,
        time_mask: int = 48,
        augment_config: Optional[AugmentConfig] = None,
    ):
        self.records = list(records)
        self.manifest_dir = Path(manifest_dir)
        self.crop_frames = frames_for(crop_seconds)
        self.train = bool(train)
        self.augment = bool(augment and train)
        self.seed = int(seed)
        self.epoch = 0
        self.mode_min_confidence = float(mode_min_confidence)
        self.bpm_min_confidence = float(bpm_min_confidence)
        self.n_genres = int(n_genres)
        self.n_emotions = int(n_emotions)
        self.freq_mask = int(freq_mask)
        self.time_mask = int(time_mask)
        # 增强配置：未显式给出时保持旧行为（只有 SpecAugment + 轻噪声）
        self.augment_config = augment_config or AugmentConfig(
            freq_mask_width=int(freq_mask), time_mask_width=int(time_mask)
        )
        self.augmenter = FeatureAugmenter(self.augment_config)

    def set_epoch(self, epoch: int) -> None:
        self.epoch = int(epoch)

    def __len__(self) -> int:
        return len(self.records)

    def _cache_path(self, record: Dict[str, Any]) -> Path:
        cache = Path(str(record.get("cache") or ""))
        return cache if cache.is_absolute() else self.manifest_dir / cache

    def __getitem__(self, index: int) -> Dict[str, Any]:
        record = self.records[index]
        mel, chroma = load_cache(self._cache_path(record))
        rng = np.random.default_rng(
            (self.seed + index * 1000003 + self.epoch * 9176) % (2**32)
        )
        mel, chroma = crop_or_pad(
            mel,
            chroma,
            self.crop_frames,
            random_crop=self.train,
            rng=rng,
        )
        mel, chroma = normalize_features(mel, chroma)
        bpm_scale = 1.0
        if self.augment:
            # 变速会改变帧数，增强器内部会再裁剪/补齐回 self.crop_frames
            mel, chroma, bpm_scale = self.augmenter(
                mel, chroma, rng, frames=self.crop_frames
            )

        labels = record.get("labels") or {}

        genre_probs = labels.get("genre_probs")
        if genre_probs is not None:
            genre = np.zeros(self.n_genres, dtype=np.float32)
            values = np.asarray(genre_probs, dtype=np.float32)
            genre[: min(len(values), self.n_genres)] = values[: self.n_genres]
            genre_sum = float(genre.sum())
            genre = genre / genre_sum if genre_sum > 0 else genre
            genre_mask = 1.0 if float(labels.get("genre_weight") or 0) > 0 else 0.0
            genre_weight = float(labels.get("genre_weight") or 1.0)
        else:
            genre = np.zeros(self.n_genres, dtype=np.float32)
            genre_mask = 0.0
            genre_weight = 0.0

        emotion_probs = labels.get("emotion_probs")
        if emotion_probs is not None:
            emotion = np.zeros(self.n_emotions, dtype=np.float32)
            values = np.asarray(emotion_probs, dtype=np.float32)
            emotion[: min(len(values), self.n_emotions)] = values[: self.n_emotions]
            emotion_sum = float(emotion.sum())
            emotion = emotion / emotion_sum if emotion_sum > 0 else emotion
            emotion_mask = 1.0
            emotion_weight = float(labels.get("emotion_weight") or 1.0)
        else:
            emotion = np.zeros(self.n_emotions, dtype=np.float32)
            emotion_mask = 0.0
            emotion_weight = 0.0

        mode_name = labels.get("mode")
        key_conf = float(labels.get("key_confidence") or 0.0)
        if mode_name in ("major", "minor") and key_conf >= self.mode_min_confidence:
            mode = 0 if mode_name == "major" else 1
            mode_mask = 1.0
            mode_weight = min(1.0, max(0.3, (key_conf - 0.2) / 0.8))
        else:
            mode = 0
            mode_mask = 0.0
            mode_weight = 0.0

        bpm_value = labels.get("bpm")
        bpm_conf = float(labels.get("bpm_confidence") or 0.0)
        if bpm_value is not None and bpm_conf >= self.bpm_min_confidence:
            # 变速增强后速度随 rate 缩放，标签同步修正
            bpm = float(bpm_value) * bpm_scale
            bpm_mask = 1.0
            bpm_weight = min(1.0, max(0.3, bpm_conf))
        else:
            bpm = 0.0
            bpm_mask = 0.0
            bpm_weight = 0.0

        return {
            "mel": torch.from_numpy(np.ascontiguousarray(mel[None, :, :])),
            "chroma": torch.from_numpy(np.ascontiguousarray(chroma[None, :, :])),
            "genre": torch.from_numpy(genre),
            "genre_mask": torch.tensor(genre_mask, dtype=torch.float32),
            "genre_weight": torch.tensor(genre_weight, dtype=torch.float32),
            "emotion": torch.from_numpy(emotion),
            "emotion_mask": torch.tensor(emotion_mask, dtype=torch.float32),
            "emotion_weight": torch.tensor(emotion_weight, dtype=torch.float32),
            "mode": torch.tensor(mode, dtype=torch.long),
            "mode_mask": torch.tensor(mode_mask, dtype=torch.float32),
            "mode_weight": torch.tensor(mode_weight, dtype=torch.float32),
            "bpm": torch.tensor(bpm, dtype=torch.float32),
            "bpm_mask": torch.tensor(bpm_mask, dtype=torch.float32),
            "bpm_weight": torch.tensor(bpm_weight, dtype=torch.float32),
            "id": record.get("id", str(index)),
        }


def infer_layout(
    records: Sequence[Dict[str, Any]],
    n_genres: int = len(_GENRE_LABELS_FALLBACK),
    n_emotions: int = len(_EMOTION_LABELS_FALLBACK),
) -> Tuple[int, int]:
    """Validate label vector lengths once, with a clear error."""
    for record in records:
        labels = record.get("labels") or {}
        genre = labels.get("genre_probs")
        if genre is not None and len(genre) != n_genres:
            raise ValueError(
                f"genre_probs length {len(genre)} != expected {n_genres} "
                f"({record.get('id')})"
            )
        emotion = labels.get("emotion_probs")
        if emotion is not None and len(emotion) != n_emotions:
            raise ValueError(
                f"emotion_probs length {len(emotion)} != expected {n_emotions} "
                f"({record.get('id')})"
            )
    return n_genres, n_emotions


def compute_bpm_stats(records: Sequence[Dict[str, Any]]) -> Tuple[float, float]:
    values = [
        float(r["labels"]["bpm"])
        for r in records
        if (r.get("labels") or {}).get("bpm") is not None
        and float((r.get("labels") or {}).get("bpm_confidence") or 0) >= 0.15
    ]
    if not values:
        return 120.0, 30.0
    return float(np.mean(values)), float(np.std(values) or 30.0)


def make_weighted_sampler(
    records: Sequence[Dict[str, Any]],
    *,
    damping: str = "sqrt",
    task: str = "genre+emotion",
    num_samples: Optional[int] = None,
    seed: int = 42,
) -> Optional[WeightedRandomSampler]:
    """Inverse-frequency sampler for imbalanced genre / emotion labels."""
    if damping == "none":
        return None

    tasks = [name for name in ("genre", "emotion") if name in task]
    counters: Dict[str, Dict[str, int]] = {name: {} for name in tasks}
    for record in records:
        labels = record.get("labels") or {}
        for name in tasks:
            value = labels.get(name)
            if value:
                counters[name][value] = counters[name].get(value, 0) + 1

    weights: List[float] = []
    for record in records:
        labels = record.get("labels") or {}
        parts: List[float] = []
        for name in tasks:
            value = labels.get(name)
            if not value:
                continue
            count = max(1, counters[name].get(value, 1))
            value_weight = 1.0 / (count ** (0.5 if damping == "sqrt" else 1.0))
            parts.append(value_weight)
        if not parts:
            parts = [1.0]
        weights.append(float(np.mean(parts)))

    total = float(sum(weights))
    if total <= 0:
        return None
    generator = torch.Generator().manual_seed(int(seed))
    return WeightedRandomSampler(
        weights,
        num_samples=int(num_samples or len(records)),
        replacement=True,
        generator=generator,
    )
