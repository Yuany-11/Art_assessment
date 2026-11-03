"""Label taxonomy and tag -> target mappings.

The JSON file next to this module is deliberately data, not code: edit
``labels/taxonomy.json`` to change genre mappings or mood anchors without
touching the training pipeline.  The 13 model genres are kept identical to the
previous checkpoints so old runs remain loadable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

TAXONOMY_PATH = Path(__file__).resolve().parent / "labels" / "taxonomy.json"

GENRE_PREFIX = "genre---"
MOOD_PREFIX = "mood/theme---"
EPS = 1e-9


def _strip_prefix(tag: str) -> Tuple[str, str]:
    tag = str(tag).strip().lower()
    if tag.startswith(GENRE_PREFIX):
        return "genre", tag[len(GENRE_PREFIX) :]
    if tag.startswith(MOOD_PREFIX):
        return "mood", tag[len(MOOD_PREFIX) :]
    if "---" in tag:
        return tag.split("---", 1)[0], tag.split("---", 1)[1]
    return "raw", tag


def parse_tags(tags: Any) -> List[str]:
    """Normalise FMA lists / Jamendo comma strings into lower-case tags."""
    if tags is None:
        return []
    if isinstance(tags, str):
        text = tags.strip()
        if not text:
            return []
        if "," in text:
            parts = text.split(",")
        else:
            parts = [text]
    elif isinstance(tags, (list, tuple, set)):
        parts = list(tags)
    else:
        parts = [tags]
    out: List[str] = []
    for part in parts:
        value = str(part).strip().lower()
        if value:
            out.append(value)
    return out


class Taxonomy:
    def __init__(self, path: Optional[str | Path] = None):
        self.path = Path(path) if path else TAXONOMY_PATH
        with open(self.path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.data = data
        self.genres: List[str] = list(data["genres"])
        self.emotions: List[str] = list(data["emotions"])
        self.genre_index = {name: i for i, name in enumerate(self.genres)}
        self.emotion_index = {name: i for i, name in enumerate(self.emotions)}
        self.fma_genre_top = data.get("fma_genre_top", {})
        self.fma_tag_genres = {
            str(k).lower(): v for k, v in data.get("fma_tag_genres", {}).items()
        }
        self.jamendo_genre_tags = {
            str(k).lower(): v for k, v in data.get("jamendo_genre", {}).items()
        }
        self.mood_tags = {
            str(k).lower(): v for k, v in data.get("mood_tags", {}).items()
        }
        self.fma_mood_tags = {
            str(k).lower(): v for k, v in data.get("fma_mood_tags", {}).items()
        }
        self.merge_genre_tags = {
            str(k).lower(): list(v) for k, v in data.get("merge_genre", {}).items()
        }
        self.centers = np.asarray(
            [data["quadrant_centers"][name] for name in self.emotions],
            dtype=np.float32,
        )
        self.emotion_temperature = float(data.get("emotion_temperature", 0.22))

    # -- genre ---------------------------------------------------------
    def _genre_dist(self, counts: Dict[str, float]) -> Optional[np.ndarray]:
        total = float(sum(counts.values()))
        if total <= EPS:
            return None
        dist = np.zeros(len(self.genres), dtype=np.float32)
        for name, value in counts.items():
            index = self.genre_index.get(name)
            if index is not None and value > 0:
                dist[index] += float(value)
        total = float(dist.sum())
        if total <= EPS:
            return None
        return dist / total

    def fma_genre(
        self, genre_top: Any, tags: Any = None
    ) -> Tuple[Optional[np.ndarray], str, float]:
        """Return ``(distribution, source, sample_weight)`` for an FMA track."""
        top = str(genre_top).strip() if genre_top is not None else ""
        mapped = self.fma_genre_top.get(top)
        if mapped:
            dist = np.zeros(len(self.genres), dtype=np.float32)
            dist[self.genre_index[mapped]] = 1.0
            return dist, "fma_genre_top", 1.0

        counts: Dict[str, float] = {}
        for tag in parse_tags(tags):
            genre = self.fma_tag_genres.get(tag)
            if genre is None:
                # allow "horror film" -> horror etc. only for exact curated
                # prefixes to avoid accidental matches
                for key, value in self.fma_tag_genres.items():
                    if len(key) >= 4 and (tag.startswith(key) or tag.endswith(key)):
                        genre = value
                        break
            if genre:
                counts[genre] = counts.get(genre, 0.0) + 1.0
        dist = self._genre_dist(counts)
        if dist is None:
            return None, "none", 0.0
        weight = min(1.0, 0.55 + 0.08 * sum(counts.values()))
        return dist, "fma_tags", round(weight, 3)

    def jamendo_genre(self, tags: Any) -> Tuple[Optional[np.ndarray], str, float]:
        counts: Dict[str, float] = {}
        for raw in parse_tags(tags):
            kind, tag = _strip_prefix(raw)
            if kind not in ("genre", "raw"):
                continue
            genre = self.jamendo_genre_tags.get(tag)
            if genre:
                counts[genre] = counts.get(genre, 0.0) + 1.0
        dist = self._genre_dist(counts)
        if dist is None:
            return None, "none", 0.0
        weight = min(1.0, 0.55 + 0.08 * sum(counts.values()))
        return dist, "jamendo_genre_tags", round(weight, 3)

    def merge_genre(self, tags: Any) -> Tuple[Optional[np.ndarray], str, float]:
        """AllMusic genre tags (MERGE) -> the 13 model genres."""
        counts: Dict[str, float] = {}
        for tag in parse_tags(tags):
            for genre in self.merge_genre_tags.get(tag, ()):  # type: ignore[arg-type]
                counts[genre] = counts.get(genre, 0.0) + 1.0
        dist = self._genre_dist(counts)
        if dist is None:
            return None, "none", 0.0
        weight = min(1.0, 0.55 + 0.08 * sum(counts.values()))
        return dist, "merge_genre_tags", round(weight, 3)

    # -- mood ----------------------------------------------------------
    def _mood_distribution(
        self, anchors: Sequence[Sequence[float]], source: str, base_weight: float
    ) -> Tuple[Optional[np.ndarray], Optional[str], float, str]:
        if not anchors:
            return None, None, 0.0, "none"
        points = np.asarray(anchors, dtype=np.float32)
        valence = float(points[:, 0].mean())
        arousal = float(points[:, 1].mean())
        # Soft assignment to the four circumplex quadrants.
        distances = np.sum((self.centers - np.array([valence, arousal])) ** 2, axis=1)
        logits = -distances / (2.0 * max(self.emotion_temperature, 1e-3) ** 2)
        logits = logits - float(logits.max())
        probs = np.exp(logits)
        probs = probs / max(float(probs.sum()), EPS)
        label = self.emotions[int(np.argmax(probs))]
        confidence = float(np.max(probs))
        weight = min(1.0, base_weight + 0.10 * len(anchors))
        return probs.astype(np.float32), label, round(weight, 3), source

    def jamendo_mood(
        self, tags: Any
    ) -> Tuple[Optional[np.ndarray], Optional[str], float, str]:
        anchors: List[Sequence[float]] = []
        for raw in parse_tags(tags):
            kind, tag = _strip_prefix(raw)
            if kind != "mood":
                continue
            anchor = self.mood_tags.get(tag)
            if anchor:
                anchors.append(anchor)
        return self._mood_distribution(
            anchors, "jamendo_mood_tags", base_weight=0.45
        )

    def merge_mood(
        self, valence: Any, arousal: Any
    ) -> Tuple[Optional[np.ndarray], Optional[str], float, str]:
        """MERGE arousal/valence ratings (both 0..1) -> quadrant distribution."""
        try:
            point = [float(valence), float(arousal)]
        except (TypeError, ValueError):
            return None, None, 0.0, "none"
        if not all(np.isfinite(point)):
            return None, None, 0.0, "none"
        return self._mood_distribution([point], "merge_av", base_weight=0.75)

    def fma_mood(
        self, tags: Any
    ) -> Tuple[Optional[np.ndarray], Optional[str], float, str]:
        anchors: List[Sequence[float]] = []
        for raw in parse_tags(tags):
            kind, tag = _strip_prefix(raw)
            anchor = self.fma_mood_tags.get(tag)
            if anchor:
                anchors.append(anchor)
        return self._mood_distribution(anchors, "fma_tags", base_weight=0.35)

    # -- convenience ---------------------------------------------------
    def one_hot(self, name: str) -> Optional[np.ndarray]:
        index = self.genre_index.get(name)
        if index is None:
            return None
        dist = np.zeros(len(self.genres), dtype=np.float32)
        dist[index] = 1.0
        return dist


_DEFAULT: Optional[Taxonomy] = None


def default_taxonomy() -> Taxonomy:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Taxonomy()
    return _DEFAULT
