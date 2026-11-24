"""Checkpoint loading + inference used by ``training/score.py``.

The public surface is intentionally identical to the previous implementation:

    tagger = Tagger()                       # latest training/runs/*/best_model.pt
    out = tagger.predict_arrays(mel, chroma)
    tagger = Tagger("training/runs/.../best_model.pt")

Old (v1) checkpoints, v2 and the current v3 architecture are all supported; the
architecture is read from the checkpoint when present.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import torch

try:
    from .features import (
        HOP_LENGTH,
        N_CHROMA,
        N_MELS,
        SR,
        compute_features,
        crop_or_pad,
        load_audio,
        normalize_features,
    )
    from .model import build_model, load_weights
except ImportError:  # executed as a top-level module from training/
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from features import (  # type: ignore
        HOP_LENGTH,
        N_CHROMA,
        N_MELS,
        SR,
        compute_features,
        crop_or_pad,
        load_audio,
        normalize_features,
    )
    from model import build_model, load_weights  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = PROJECT_ROOT / "training" / "runs"

GENRES = [
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
EMOTIONS = ["calm", "happy", "sad", "tense"]
EMOTION_CN = {"calm": "平静", "happy": "欢快", "sad": "悲伤", "tense": "紧张"}
MODE_CN = {"major": "大调", "minor": "小调"}


def latest_checkpoint(runs_dir: Path = RUNS_DIR) -> Optional[Path]:
    candidates = sorted(
        runs_dir.glob("*/best_model.pt"), key=lambda p: p.stat().st_mtime
    )
    return candidates[-1] if candidates else None


def _strip_prefixes(state: Dict[str, Any]) -> Dict[str, Any]:
    if not state:
        return state
    keys = list(state.keys())
    for prefix in ("module.", "model."):
        if all(isinstance(key, str) and key.startswith(prefix) for key in keys):
            keys = [key[len(prefix) :] for key in keys]
            state = {key[len(prefix) :]: value for key, value in state.items()}
    return state


def _detect_arch(state: Dict[str, Any]) -> str:
    if any(str(key).startswith("tempo_branch.") for key in state):
        return "v4"
    if any(str(key).startswith("mel_pool.att.") for key in state):
        return "v3"
    if any(str(key).startswith("mel_branch.0.conv1.") for key in state):
        return "v2"
    return "v1"


class Tagger:
    def __init__(
        self,
        weights: Optional[str | Path] = None,
        *,
        device: Optional[str] = None,
        verbose: bool = False,
    ):
        path = Path(weights) if weights else latest_checkpoint()
        if path is None:
            raise FileNotFoundError(
                "No checkpoint found. Train one first: "
                "python training/train.py --manifest training/data/manifest.jsonl"
            )
        if path.is_dir():
            path = path / "best_model.pt"
        if not path.is_file():
            raise FileNotFoundError(f"checkpoint not found: {path}")

        payload = torch.load(str(path), map_location="cpu", weights_only=False)
        state = payload.get("model") or payload.get("state_dict") or payload
        if not isinstance(state, dict):
            raise ValueError(f"unrecognised checkpoint payload: {path}")
        state = _strip_prefixes(state)

        self.weights = str(path)
        self.payload = payload
        self.arch = str(payload.get("arch") or _detect_arch(state))
        self.config = dict(payload.get("config") or {})
        self.genres: List[str] = list(payload.get("genre_labels") or GENRES)
        self.emotions: List[str] = list(payload.get("emotion_labels") or EMOTIONS)
        self.emotion_cn = dict(payload.get("emotion_cn") or EMOTION_CN)
        self.mode_cn = dict(payload.get("mode_cn") or MODE_CN)
        self.modes = ["major", "minor"]

        self.n_mels = int(self.config.get("n_mels", N_MELS))
        self.n_chroma = int(self.config.get("n_chroma", N_CHROMA))
        self.clip_seconds = float(self.config.get("clip_seconds", 30.0))
        self.tta_crops = max(1, int(self.config.get("tta_crops", 3)))
        self.bpm_mean = float(payload.get("bpm_mean", 120.0))
        self.bpm_std = float(payload.get("bpm_std", 30.0) or 30.0)
        self.model_epoch = int(payload.get("epoch", 0))

        self.device = torch.device(
            device or ("cuda" if torch.cuda.is_available() else "cpu")
        )
        self.model = build_model(
            self.arch,
            n_genres=len(self.genres),
            n_emotions=len(self.emotions),
            n_modes=2,
        )
        load_weights(self.model, state, verbose=verbose)
        self.model.to(self.device).eval()

    # -- helpers -------------------------------------------------------
    def _crop_frames(self) -> int:
        return max(32, int(round(self.clip_seconds * SR / HOP_LENGTH)))

    def _crops(self, mel: np.ndarray, chroma: np.ndarray):
        n = min(mel.shape[1], chroma.shape[1])
        mel, chroma = mel[:, :n], chroma[:, :n]
        frames = self._crop_frames()
        if n <= frames:
            yield mel, chroma
            return
        count = max(1, self.tta_crops)
        starts = np.linspace(0, n - frames, num=count).astype(int)
        for start in starts:
            yield mel[:, start : start + frames], chroma[:, start : start + frames]

    def _forward(self, mel: np.ndarray, chroma: np.ndarray) -> Dict[str, np.ndarray]:
        mel, chroma = crop_or_pad(
            np.asarray(mel, dtype=np.float32),
            np.asarray(chroma, dtype=np.float32),
            self._crop_frames(),
            random_crop=False,
        )
        mel, chroma = normalize_features(mel, chroma)
        mel_t = torch.from_numpy(mel[None, None, :, :]).to(self.device)
        chroma_t = torch.from_numpy(chroma[None, None, :, :]).to(self.device)
        with torch.no_grad():
            logits = self.model(mel_t, chroma_t)
            probs = {
                "genre": torch.softmax(logits["genre"], dim=-1)[0].cpu().numpy(),
                "emotion": torch.softmax(logits["emotion"], dim=-1)[0].cpu().numpy(),
                "mode": torch.softmax(logits["mode"], dim=-1)[0].cpu().numpy(),
                "bpm": float(logits["bpm"][0].cpu().item()),
            }
        return probs

    # -- public --------------------------------------------------------
    def predict_arrays(
        self, mel: np.ndarray, chroma: np.ndarray
    ) -> Dict[str, Any]:
        mel = np.asarray(mel, dtype=np.float32)
        chroma = np.asarray(chroma, dtype=np.float32)
        if mel.ndim != 2 or chroma.ndim != 2:
            raise ValueError("mel/chroma must be 2-D (bins x frames)")
        if mel.shape[0] != self.n_mels:
            raise ValueError(f"mel has {mel.shape[0]} bins, model expects {self.n_mels}")

        genre_prob = np.zeros(len(self.genres), dtype=np.float64)
        emotion_prob = np.zeros(len(self.emotions), dtype=np.float64)
        mode_prob = np.zeros(2, dtype=np.float64)
        bpm_values: List[float] = []
        n = 0
        for crop_mel, crop_chroma in self._crops(mel, chroma):
            out = self._forward(crop_mel, crop_chroma)
            genre_prob += out["genre"]
            emotion_prob += out["emotion"]
            mode_prob += out["mode"]
            bpm_values.append(out["bpm"] * self.bpm_std + self.bpm_mean)
            n += 1
        if n:
            genre_prob /= n
            emotion_prob /= n
            mode_prob /= n

        genre_index = int(np.argmax(genre_prob))
        emotion_index = int(np.argmax(emotion_prob))
        mode_index = int(np.argmax(mode_prob))
        bpm = float(np.mean(bpm_values)) if bpm_values else 0.0
        bpm = float(np.clip(bpm, 30.0, 300.0))

        genre_dict = {
            name: round(float(genre_prob[i]), 6)
            for i, name in enumerate(self.genres)
        }
        emotion_dict = {
            name: round(float(emotion_prob[i]), 6)
            for i, name in enumerate(self.emotions)
        }
        mode_dict = {
            name: round(float(mode_prob[i]), 6)
            for i, name in enumerate(self.modes)
        }
        emotion_label = self.emotions[emotion_index]
        mode_label = self.modes[mode_index]
        return {
            "genre": genre_dict,
            "genre_probs": genre_dict,
            "genre_top1": self.genres[genre_index],
            "genre_confidence": round(float(genre_prob[genre_index]), 6),
            "emotion": emotion_label,
            "emotion_cn": self.emotion_cn.get(emotion_label, emotion_label),
            "emotion_confidence": round(float(emotion_prob[emotion_index]), 6),
            "emotion_probs": emotion_dict,
            "mode": mode_label,
            "mode_cn": self.mode_cn.get(mode_label, mode_label),
            "mode_confidence": round(float(mode_prob[mode_index]), 6),
            "mode_probs": mode_dict,
            "bpm": round(bpm, 2),
            "weights": self.weights,
            "model_epoch": self.model_epoch,
            "arch": self.arch,
        }

    def predict_file(self, path: str | Path, seconds: float = 120.0) -> Dict[str, Any]:
        y = load_audio(Path(path), sr=SR, seconds=seconds)
        mel, chroma = compute_features(
            y, sr=SR, n_mels=self.n_mels, n_chroma=self.n_chroma
        )
        return self.predict_arrays(mel, chroma)


def features_from_audio(y: np.ndarray, sr: int = SR):
    """Re-exported for ``training/score.py``."""
    return compute_features(y, sr=sr)
