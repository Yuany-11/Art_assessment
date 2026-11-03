"""Audio feature extraction shared by dataset labeling, training and inference.

The feature contract is intentionally small:

* ``mel``    -- log-mel spectrogram in dB, shape ``(n_mels, T)``
* ``chroma`` -- CQT chroma, L2-normalised per frame, shape ``(n_chroma, T)``

Both arrays are aligned to the same number of frames and are stored as
float16 in the feature cache (see :func:`save_cache`).  Normalisation is
applied at load time so cached values stay dataset independent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import librosa
import numpy as np
import soundfile as sf

SR = 22050
HOP_LENGTH = 512
N_FFT = 2048
N_MELS = 128
N_CHROMA = 12
FMIN = 20.0
EPS = 1e-8

__all__ = [
    "SR",
    "HOP_LENGTH",
    "N_FFT",
    "N_MELS",
    "N_CHROMA",
    "load_audio",
    "compute_features",
    "features_from_audio",
    "normalize_features",
    "save_cache",
    "load_cache",
    "crop_or_pad",
    "spec_augment",
]


def load_audio(
    path: str | Path,
    sr: int = SR,
    seconds: Optional[float] = None,
    offset: float = 0.0,
) -> np.ndarray:
    """Read a segment of an audio file as mono float32 at ``sr``.

    ``soundfile`` handles wav/flac/ogg and (libsndfile >= 1.1) mp3.  When the
    container is unsupported we fall back to ``librosa.load``, which can use
    audioread/ffmpeg.
    """
    path = str(path)
    offset = max(0.0, float(offset))
    try:
        with sf.SoundFile(path) as handle:
            native_sr = int(handle.samplerate)
            start = min(int(round(offset * native_sr)), len(handle))
            handle.seek(start)
            frames = -1 if seconds is None else max(1, int(round(seconds * native_sr)))
            data = handle.read(frames=frames, dtype="float32", always_2d=True)
    except Exception:
        y, _ = librosa.load(
            path, sr=sr, mono=True, offset=offset or None, duration=seconds
        )
        return np.ascontiguousarray(y, dtype=np.float32)

    if data.size == 0:
        return np.zeros(0, dtype=np.float32)
    mono = data.mean(axis=1, dtype=np.float32) if data.shape[1] > 1 else data[:, 0]
    if native_sr != sr:
        mono = librosa.resample(mono, orig_sr=native_sr, target_sr=sr).astype(np.float32)
    if seconds is not None:
        mono = mono[: int(round(seconds * sr))]
    return np.ascontiguousarray(mono, dtype=np.float32)


def _pad_short(y: np.ndarray, sr: int) -> np.ndarray:
    if y.size >= sr // 20:  # 50 ms is enough for feature extraction
        return y
    return np.pad(y, (0, max(0, sr // 4 - y.size)), mode="constant")


def compute_features(
    y: np.ndarray,
    sr: int = SR,
    n_mels: int = N_MELS,
    n_chroma: int = N_CHROMA,
) -> Tuple[np.ndarray, np.ndarray]:
    """Return aligned ``(log_mel_db, chroma)`` float32 arrays."""
    y = _pad_short(np.asarray(y, dtype=np.float32), sr)
    mel = librosa.feature.melspectrogram(
        y=y,
        sr=sr,
        n_fft=N_FFT,
        hop_length=HOP_LENGTH,
        n_mels=n_mels,
        fmin=FMIN,
        fmax=sr / 2.0,
        power=2.0,
    )
    mel_db = librosa.power_to_db(mel, ref=np.max, top_db=80.0).astype(np.float32)

    chroma = librosa.feature.chroma_cqt(
        y=y,
        sr=sr,
        hop_length=HOP_LENGTH,
        n_chroma=n_chroma,
        bins_per_octave=36,
    )
    if chroma.size:
        norms = np.linalg.norm(chroma, axis=0, keepdims=True)
        chroma = chroma / np.maximum(norms, EPS)
    chroma = chroma.astype(np.float32)

    n_frames = min(mel_db.shape[1], chroma.shape[1])
    if n_frames <= 0:
        n_frames = 1
        mel_db = np.zeros((n_mels, 1), dtype=np.float32)
        chroma = np.zeros((n_chroma, 1), dtype=np.float32)
    return mel_db[:, :n_frames], chroma[:, :n_frames]


def features_from_audio(
    y: np.ndarray,
    sr: int = SR,
    n_mels: int = N_MELS,
    n_chroma: int = N_CHROMA,
) -> Tuple[np.ndarray, np.ndarray]:
    """Backwards-compatible entry point used by ``training/score.py``."""
    return compute_features(y, sr=sr, n_mels=n_mels, n_chroma=n_chroma)


def normalize_features(
    mel: np.ndarray, chroma: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """Per-sample standardisation; removes gain/production level differences."""
    mel = np.asarray(mel, dtype=np.float32)
    chroma = np.asarray(chroma, dtype=np.float32)
    mel = (mel - float(mel.mean())) / (float(mel.std()) + 1e-5)
    chroma = (chroma - float(chroma.mean())) / (float(chroma.std()) + 1e-5)
    return mel, chroma


def save_cache(
    path: str | Path,
    mel: np.ndarray,
    chroma: np.ndarray,
    *,
    seconds: float,
    sr: int = SR,
) -> None:
    """Store raw (unnormalised) features as float16 to keep the cache small."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    # np.savez appends ".npz" when given a path that does not already end in
    # ".npz"; passing a file object writes exactly to ``tmp``.
    with open(tmp, "wb") as handle:
        np.savez(
            handle,
            mel=np.asarray(mel, dtype=np.float16),
            chroma=np.asarray(chroma, dtype=np.float16),
            seconds=np.float32(seconds),
            sr=np.int32(sr),
            hop=np.int32(HOP_LENGTH),
        )
    tmp.replace(path)


def load_cache(path: str | Path) -> Tuple[np.ndarray, np.ndarray]:
    with np.load(str(path)) as data:
        mel = np.asarray(data["mel"], dtype=np.float32)
        chroma = np.asarray(data["chroma"], dtype=np.float32)
    return mel, chroma


def crop_or_pad(
    mel: np.ndarray,
    chroma: np.ndarray,
    frames: int,
    *,
    random_crop: bool = False,
    rng: Optional[np.random.Generator] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Crop (or repeat-pad) aligned features to exactly ``frames`` columns."""
    frames = max(1, int(frames))
    n = min(mel.shape[1], chroma.shape[1])
    if n == 0:
        mel = np.zeros((mel.shape[0], frames), dtype=np.float32)
        chroma = np.zeros((chroma.shape[0], frames), dtype=np.float32)
        return mel, chroma

    if n >= frames:
        if random_crop:
            rng = rng or np.random.default_rng()
            start = int(rng.integers(0, n - frames + 1))
        else:
            start = (n - frames) // 2
        return mel[:, start : start + frames], chroma[:, start : start + frames]

    # Repeat-pad very short clips (rare after the 10 s filtering step).
    reps = int(np.ceil(frames / n))
    mel_p = np.tile(mel[:, :n], (1, reps))[:, :frames]
    chroma_p = np.tile(chroma[:, :n], (1, reps))[:, :frames]
    return mel_p, chroma_p


def spec_augment(
    mel: np.ndarray,
    chroma: np.ndarray,
    rng: np.random.Generator,
    *,
    n_freq_masks: int = 2,
    freq_mask_width: int = 16,
    n_time_masks: int = 2,
    time_mask_width: int = 48,
) -> Tuple[np.ndarray, np.ndarray]:
    """In-place SpecAugment on a copy of the features (time masks shared)."""
    mel = mel.copy()
    chroma = chroma.copy()
    n_mels, n_frames = mel.shape
    for _ in range(n_freq_masks):
        width = int(rng.integers(0, max(1, freq_mask_width) + 1))
        if width and n_mels > width:
            start = int(rng.integers(0, n_mels - width))
            mel[start : start + width, :] = 0.0
    for _ in range(n_time_masks):
        width = int(rng.integers(0, max(1, time_mask_width) + 1))
        if width and n_frames > width:
            start = int(rng.integers(0, n_frames - width))
            mel[:, start : start + width] = 0.0
            chroma[:, start : start + width] = 0.0
    return mel, chroma
