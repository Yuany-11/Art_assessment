#!/usr/bin/env python3
"""Turn downloaded audio into a labelled, cached training manifest.

What a "label" means here
-------------------------
Every label is tied to one of the model's four output heads:

* ``genre``   -- FMA top-level genre (human curated) or Jamendo genre tags
* ``emotion`` -- MTG-Jamendo mood/theme tags projected onto Russell's
                 valence/arousal quadrants (calm / happy / sad / tense)
* ``mode``    -- Krumhansl-Schmuckler chroma profile (pseudo-label, confidence
                 weighted)
* ``bpm``     -- librosa beat tracking with octave folding (pseudo-label,
                 confidence weighted)

Missing labels are represented as ``null`` and the trainer masks that task for
the sample, so a track can still teach genre even without a mood annotation.

Outputs
-------
``training/data/manifest.jsonl``       one JSON object per track
``training/data/manifest_stats.json``  class/split/licence coverage
``training/data/label_report.json``    run report
``training/data/cache/*.npz``          float16 mel+chroma features

Usage
-----
    python training/label_dataset.py --root data
    python training/label_dataset.py --root data --workers 8 --license-policy research
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

try:
    from .dsp_labels import estimate_key_mode, estimate_tempo
    from .features import (
        HOP_LENGTH,
        SR,
        compute_features,
        load_audio,
        load_cache,
        save_cache,
    )
    from .taxonomy import Taxonomy, parse_tags
except ImportError:  # direct script execution: python training/label_dataset.py
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from dsp_labels import estimate_key_mode, estimate_tempo  # type: ignore
    from features import (  # type: ignore
        HOP_LENGTH,
        SR,
        compute_features,
        load_audio,
        load_cache,
        save_cache,
    )
    from taxonomy import Taxonomy, parse_tags  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FMA_SUBSETS = {"small", "medium"}
FMA_SPLIT_MAP = {"training": "train", "validation": "val", "test": "test"}

_NC_MARKERS = ("noncommercial", "non-commercial", "noncommercial", " nc ")
_ND_MARKERS = ("noderiv", "no derivative", "no-derivative", "nd ")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _normalise(text: Any) -> str:
    return " ".join(str(text).lower().replace("_", " ").split())


def license_policy_allows(license_text: Optional[str], policy: str) -> bool:
    if policy == "all":
        return True
    text = _normalise(license_text or "")
    if not text:
        return policy == "research"
    has_nc = any(marker in f" {text} " for marker in _NC_MARKERS)
    has_nd = any(marker in f" {text} " for marker in _ND_MARKERS)
    if policy == "commercial":
        return not has_nc and not has_nd
    return True  # research: all Creative Commons / public-domain licences


def probe_duration(path: Path) -> float:
    try:
        import soundfile as sf

        info = sf.info(str(path))
        return float(info.frames) / float(info.samplerate) if info.samplerate else 0.0
    except Exception:
        return 0.0


def audio_fingerprint(y: np.ndarray, sr: int = SR, seconds: float = 20.0) -> str:
    chunk = np.asarray(y[: int(seconds * sr)], dtype=np.float32)
    pcm = np.clip(chunk * 32767.0, -32768, 32767).astype(np.int16)
    return hashlib.sha1(pcm.tobytes()).hexdigest()[:16]


def split_for_artist(artist_id: str, seed: int = 42) -> str:
    digest = hashlib.sha1(f"{seed}:{artist_id}".encode("utf-8")).hexdigest()[:8]
    bucket = int(digest, 16) % 100
    if bucket < 80:
        return "train"
    if bucket < 90:
        return "val"
    return "test"


def _json_list(values: Optional[np.ndarray]) -> Optional[List[float]]:
    if values is None:
        return None
    return [round(float(v), 6) for v in np.asarray(values, dtype=float)]


def _argmax_name(names: Sequence[str], values: Optional[np.ndarray]) -> Optional[str]:
    if values is None or len(values) == 0:
        return None
    return names[int(np.argmax(values))]


# ---------------------------------------------------------------------------
# FMA metadata
# ---------------------------------------------------------------------------
def load_fma_tracks(root: Path) -> Dict[int, Dict[str, Any]]:
    import pandas as pd

    tracks_csv = root / "fma_metadata" / "tracks.csv"
    if not tracks_csv.exists():
        return {}
    frame = pd.read_csv(tracks_csv, index_col=0, header=[0, 1])
    medium = frame[frame[("set", "subset")].isin(FMA_SUBSETS)]
    tracks: Dict[int, Dict[str, Any]] = {}
    for track_id, row in medium.iterrows():
        genre_top = row.get(("track", "genre_top"))
        if isinstance(genre_top, float) and math.isnan(genre_top):
            genre_top = None
        splits = row.get(("set", "split"))
        artist_raw = row.get(("artist", "id"))
        if artist_raw is None or (isinstance(artist_raw, float) and math.isnan(artist_raw)):
            artist_raw = track_id
        tracks[int(track_id)] = {
            "genre_top": genre_top,
            "tags": row.get(("track", "tags")),
            "license": row.get(("track", "license")),
            "split": FMA_SPLIT_MAP.get(str(splits), split_for_artist(f"fma:{track_id}")),
            "artist_id": f"fma:{int(artist_raw)}",
            "title": str(row.get(("track", "title")) or ""),
            "duration_sec": float(row.get(("track", "duration")) or 0.0),
        }
        tag_value = tracks[track_id]["tags"]
        if isinstance(tag_value, float) and math.isnan(tag_value):
            tracks[track_id]["tags"] = []
    return tracks


def find_fma_audio(root: Path) -> Dict[int, Path]:
    audio_dir = root / "fma_medium"
    found: Dict[int, Path] = {}
    if not audio_dir.exists():
        return found
    for path in audio_dir.rglob("*.mp3"):
        try:
            found[int(path.stem)] = path
        except ValueError:
            continue
    return found


# ---------------------------------------------------------------------------
# Jamendo metadata
# ---------------------------------------------------------------------------
def read_jamendo_tsv(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    rows: Dict[str, Dict[str, Any]] = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            track_id = (row.get("TRACK_ID") or "").strip()
            if not track_id:
                continue
            tags = []
            for key in ("TAGS", "tags"):
                value = row.get(key)
                if value:
                    tags.extend(parse_tags(value))
            rows[track_id] = {
                "artist_id": (row.get("ARTIST_ID") or f"unknown:{track_id}").strip(),
                "album_id": (row.get("ALBUM_ID") or "").strip(),
                "path": (row.get("PATH") or "").strip(),
                "duration_sec": float(row.get("DURATION") or 0.0),
                "tags": tags,
            }
    return rows


def find_jamendo_audio(root: Path) -> Dict[str, Path]:
    """Map numeric Jamendo track ids to extracted mp3 files."""
    audio_dir = root / "jamendo"
    found: Dict[str, Path] = {}
    if not audio_dir.exists():
        return found
    for path in audio_dir.rglob("*.mp3"):
        stem = path.stem
        if stem.isdigit():
            found[stem] = path
        elif stem.startswith("track_") and stem[6:].isdigit():
            found[stem[6:]] = path
    return found


def load_manymusic_tracks(root: Path) -> Dict[str, Dict[str, Any]]:
    """ManyMusic's MTG-Jamendo subset, shipped with the same tag vocabulary."""
    tags_csv = root / "manymusic_meta" / "manymusic_tags.csv"
    if not tags_csv.exists():
        return {}
    import pandas as pd

    frame = pd.read_csv(tags_csv)
    rows: Dict[str, Dict[str, Any]] = {}
    for _, row in frame.iterrows():
        try:
            track_id = str(int(row["track_id"]))
        except (TypeError, ValueError):
            continue
        rows[track_id] = {
            "artist_id": str(row.get("artist_id") or f"mm:{track_id}"),
            "duration_sec": float(row.get("duration") or 0.0),
            "tags": parse_tags(str(row.get("tags") or "")),
            "path": str(row.get("path") or ""),
        }
    return rows


def find_manymusic_audio(root: Path) -> Dict[str, Path]:
    audio_dir = root / "manymusic"
    found: Dict[str, Path] = {}
    if not audio_dir.exists():
        return found
    for path in audio_dir.rglob("*.mp3"):
        if path.stem.isdigit():
            found[path.stem] = path
    return found


def load_merge_tracks(root: Path) -> Dict[str, Dict[str, Any]]:
    """MERGE (Louro et al., 2024): AllMusic 30 s excerpts with arousal/valence.

    The archive ships one metadata CSV (quadrant, AllMusic tags) plus an
    ``av_values`` CSV keyed by the same song identifiers.
    """
    candidates = (root / "merge_meta", root / "merge" / "MERGE_Audio_Complete")
    meta_csv = av_csv = None
    for folder in candidates:
        meta = folder / "merge_audio_complete_metadata.csv"
        if meta.exists():
            meta_csv = meta
            av_csv = folder / "merge_audio_complete_av_values.csv"
            break
    if meta_csv is None or av_csv is None or not av_csv.exists():
        return {}
    import pandas as pd

    def _text(value: Any) -> str:
        if value is None or (isinstance(value, float) and value != value):
            return ""
        return str(value).strip()

    av = pd.read_csv(av_csv)
    values: Dict[str, Tuple[float, float]] = {}
    for _, row in av.iterrows():
        song = _text(row.get("Song"))
        try:
            values[song] = (float(row["Valence"]), float(row["Arousal"]))
        except (TypeError, ValueError):
            continue

    frame = pd.read_csv(meta_csv, low_memory=False)
    rows: Dict[str, Dict[str, Any]] = {}
    for _, row in frame.iterrows():
        song = _text(row.get("Song"))
        if not song or song not in values:
            continue
        try:
            duration = float(row.get("Duration") or 0.0)
        except (TypeError, ValueError):
            duration = 0.0
        valence, arousal = values[song]
        rows[song] = {
            "artist_id": _text(row.get("Artist")) or f"merge:{song}",
            "title": _text(row.get("Title")),
            "duration_sec": duration,
            "quadrant": _text(row.get("Quadrant")).upper(),
            "valence": valence,
            "arousal": arousal,
            "genres": parse_tags(_text(row.get("Genres"))),
            "moods": parse_tags(_text(row.get("Moods"))),
        }
    return rows


def find_merge_audio(root: Path) -> Dict[str, Path]:
    audio_dir = root / "merge"
    found: Dict[str, Path] = {}
    if not audio_dir.exists():
        return found
    for path in audio_dir.rglob("*.mp3"):
        found[path.stem] = path
    return found


def merge_jamendo_metadata(root: Path) -> Dict[str, Dict[str, Any]]:
    meta_dir = root / "jamendo_meta"
    mood = read_jamendo_tsv(meta_dir / "autotagging_moodtheme.tsv")
    genre = read_jamendo_tsv(meta_dir / "autotagging_genre.tsv")
    merged: Dict[str, Dict[str, Any]] = {}
    for track_id, row in mood.items():
        merged[track_id] = dict(row)
    for track_id, row in genre.items():
        if track_id in merged:
            merged[track_id]["tags"] = list(merged[track_id]["tags"]) + list(row["tags"])
            if not merged[track_id]["path"]:
                merged[track_id]["path"] = row["path"]
            if not merged[track_id]["duration_sec"]:
                merged[track_id]["duration_sec"] = row["duration_sec"]
        else:
            merged[track_id] = dict(row)
    return merged


# ---------------------------------------------------------------------------
# task construction
# ---------------------------------------------------------------------------
def _as_tags(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return parse_tags(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            try:
                return parse_tags(ast.literal_eval(text))
            except (ValueError, SyntaxError):
                pass
        return parse_tags(text)
    return parse_tags(value)


def build_tasks(
    root: Path,
    cache_dir: Path,
    taxonomy: Taxonomy,
    args: argparse.Namespace,
) -> List[Dict[str, Any]]:
    tasks: List[Dict[str, Any]] = []

    if not args.no_fma:
        fma_tracks = load_fma_tracks(root)
        fma_audio = find_fma_audio(root)
        for track_id, path in sorted(fma_audio.items()):
            meta = fma_tracks.get(track_id)
            if meta is None:
                continue
            if not license_policy_allows(meta.get("license"), args.license_policy):
                continue
            tasks.append(
                {
                    "id": f"fma:{track_id:06d}",
                    "dataset": "fma",
                    "audio": str(path.resolve()),
                    "cache": str((cache_dir / f"fma_{track_id:06d}.npz").resolve()),
                    "cache_seconds": args.fma_cache_seconds,
                    "min_duration": args.min_duration,
                    "duration_hint": meta.get("duration_sec", 0.0),
                    "artist_id": meta["artist_id"],
                    "title": meta.get("title", ""),
                    "license": meta.get("license", ""),
                    "split": meta["split"],
                    "genre_top": meta.get("genre_top"),
                    "tags": _as_tags(meta.get("tags")),
                }
            )

    if not args.no_jamendo:
        jamendo = merge_jamendo_metadata(root)
        audio_root = root / "jamendo"
        audio_map = find_jamendo_audio(root)
        for track_id, meta in sorted(jamendo.items()):
            numeric = track_id.split("_")[-1]
            numeric_key = str(int(numeric)) if numeric.isdigit() else numeric
            rel = meta.get("path") or (
                f"{int(numeric) % 100:02d}/{numeric}.mp3"
            )
            path = audio_root / rel
            if not path.exists():
                path = audio_map.get(numeric_key, path)
            if not path.exists():
                continue
            if args.license_policy == "commercial":
                # Metadata is CC BY-NC-SA and per-track licences are not in the
                # release files, so commercial use cannot be verified here.
                continue
            tasks.append(
                {
                    "id": f"jamendo:{track_id}",
                    "dataset": "jamendo",
                    "audio": str(path.resolve()),
                    "cache": str((cache_dir / f"jamendo_{track_id}.npz").resolve()),
                    "cache_seconds": args.jamendo_cache_seconds,
                    "min_duration": args.min_duration,
                    "duration_hint": meta.get("duration_sec", 0.0),
                    "artist_id": f"jamendo:{meta['artist_id']}",
                    "title": "",
                    "license": "Jamendo individual CC (metadata CC BY-NC-SA 4.0)",
                    "split": split_for_artist(f"jamendo:{meta['artist_id']}"),
                    "genre_top": None,
                    "tags": list(meta.get("tags") or []),
                }
            )

    if not args.no_manymusic:
        mm_tracks = load_manymusic_tracks(root)
        for track_id, path in sorted(find_manymusic_audio(root).items()):
            meta = mm_tracks.get(track_id)
            if meta is None:
                continue
            if args.license_policy == "commercial":
                # Per-track licences live in the release's audio_licenses.txt;
                # they cannot be verified for commercial use here.
                continue
            tasks.append(
                {
                    "id": f"manymusic:{track_id}",
                    "dataset": "manymusic",
                    "audio": str(path.resolve()),
                    "cache": str((cache_dir / f"manymusic_{track_id}.npz").resolve()),
                    "cache_seconds": args.jamendo_cache_seconds,
                    "min_duration": args.min_duration,
                    "duration_hint": meta.get("duration_sec", 0.0),
                    "artist_id": f"manymusic:{meta['artist_id']}",
                    "title": "",
                    "license": "ManyMusic / Jamendo individual CC",
                    "split": split_for_artist(f"manymusic:{meta['artist_id']}"),
                    "genre_top": None,
                    "tags": list(meta.get("tags") or []),
                }
            )

    if not args.no_merge:
        merge_tracks = load_merge_tracks(root)
        for song, path in sorted(find_merge_audio(root).items()):
            meta = merge_tracks.get(song)
            if meta is None:
                continue
            if args.license_policy == "commercial":
                # MERGE audio comes from AllMusic and is CC BY-NC 4.0.
                continue
            tasks.append(
                {
                    "id": f"merge:{song}",
                    "dataset": "merge",
                    "audio": str(path.resolve()),
                    "cache": str((cache_dir / f"merge_{song}.npz").resolve()),
                    "cache_seconds": args.merge_cache_seconds,
                    "min_duration": args.min_duration,
                    "duration_hint": meta.get("duration_sec", 0.0),
                    "artist_id": f"merge:{meta['artist_id']}",
                    "title": meta.get("title", ""),
                    "license": "MERGE / AllMusic excerpt (CC BY-NC 4.0)",
                    "split": split_for_artist(f"merge:{meta['artist_id']}"),
                    "genre_top": None,
                    "valence": meta["valence"],
                    "arousal": meta["arousal"],
                    "quadrant": meta.get("quadrant", ""),
                    "tags": list(meta.get("genres") or []) + list(meta.get("moods") or []),
                }
            )

    if args.limit:
        tasks = tasks[: args.limit]
    return tasks


# ---------------------------------------------------------------------------
# per-track worker
# ---------------------------------------------------------------------------
def process_track(task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Compute DSP labels + feature cache for one audio file."""
    path = Path(task["audio"])
    if not path.is_file():
        return None

    duration = probe_duration(path)
    if duration < float(task.get("min_duration") or 1.0):
        return None

    cache_seconds = float(task.get("cache_seconds") or 30.0)
    offset = max(0.0, (duration - cache_seconds) / 2.0)
    try:
        y = load_audio(path, sr=SR, seconds=cache_seconds, offset=offset)
    except Exception:
        return None
    if y.size < SR // 2:
        return None

    cache_path = Path(task["cache"])
    if not cache_path.exists() or task.get("overwrite_cache"):
        try:
            mel, chroma = compute_features(y, sr=SR)
            save_cache(cache_path, mel, chroma, seconds=len(y) / SR, sr=SR)
        except Exception:
            return None
    else:
        try:
            _, chroma = load_cache(cache_path)
        except Exception:
            try:
                mel, chroma = compute_features(y, sr=SR)
                save_cache(cache_path, mel, chroma, seconds=len(y) / SR, sr=SR)
            except Exception:
                return None

    key_info = estimate_key_mode(chroma)
    tempo_info = estimate_tempo(y, sr=SR, hop_length=HOP_LENGTH)
    taxonomy: Taxonomy = _WORKER_TAXONOMY

    dataset = task["dataset"]
    if dataset == "fma":
        genre_dist, genre_source, genre_weight = taxonomy.fma_genre(
            task.get("genre_top"), task.get("tags")
        )
        emotion_dist, emotion_label, emotion_weight, emotion_source = taxonomy.fma_mood(
            task.get("tags")
        )
    elif dataset == "merge":
        genre_dist, genre_source, genre_weight = taxonomy.merge_genre(task.get("tags"))
        (
            emotion_dist,
            emotion_label,
            emotion_weight,
            emotion_source,
        ) = taxonomy.merge_mood(task.get("valence"), task.get("arousal"))
    else:
        genre_dist, genre_source, genre_weight = taxonomy.jamendo_genre(
            task.get("tags")
        )
        (
            emotion_dist,
            emotion_label,
            emotion_weight,
            emotion_source,
        ) = taxonomy.jamendo_mood(task.get("tags"))

    genre_label = _argmax_name(taxonomy.genres, genre_dist)
    if emotion_dist is not None:
        emotion_label = _argmax_name(taxonomy.emotions, emotion_dist)

    record = {
        "id": task["id"],
        "dataset": dataset,
        "audio": task.get("audio_relative", task["audio"]),
        "cache": task["cache_relative"],
        "artist_id": task["artist_id"],
        "title": task.get("title", ""),
        "license": task.get("license", ""),
        "split": task["split"],
        "duration_sec": round(float(duration), 3),
        "cached_sec": round(min(cache_seconds, duration), 3),
        "labels": {
            "genre": genre_label,
            "genre_probs": _json_list(genre_dist),
            "genre_weight": float(genre_weight),
            "genre_source": genre_source,
            "emotion": emotion_label,
            "emotion_probs": _json_list(emotion_dist),
            "emotion_weight": float(emotion_weight),
            "emotion_source": emotion_source,
            "mode": key_info.get("mode"),
            "key": key_info.get("key"),
            "key_confidence": key_info.get("key_confidence"),
            "bpm": tempo_info.get("bpm"),
            "bpm_confidence": tempo_info.get("bpm_confidence"),
            "beat_count": tempo_info.get("beat_count"),
            "beat_regularity": tempo_info.get("beat_regularity"),
        },
        "tags": {
            "genre_top": task.get("genre_top"),
            "tags": list(task.get("tags") or [])[:60],
        },
        "audio_hash": audio_fingerprint(y),
    }
    return record


_WORKER_TAXONOMY: Taxonomy


def _init_worker(taxonomy_path: str) -> None:
    global _WORKER_TAXONOMY
    _WORKER_TAXONOMY = Taxonomy(taxonomy_path)
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")


# ---------------------------------------------------------------------------
# manifest IO / stats
# ---------------------------------------------------------------------------
def load_existing_manifest(path: Path) -> Dict[str, Dict[str, Any]]:
    records: Dict[str, Dict[str, Any]] = {}
    if not path.exists():
        return records
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("id"):
                records[record["id"]] = record
    return records


def write_manifest(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    rows = sorted(records, key=lambda item: item["id"])
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        for record in rows:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    tmp.replace(path)


def build_stats(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    genre_counts = Counter()
    emotion_counts = Counter()
    mode_counts = Counter()
    dataset_counts = Counter()
    split_counts = Counter()
    license_counts = Counter()
    bpm_values: List[float] = []
    hours = 0.0
    labeled = {"genre": 0, "emotion": 0, "mode": 0, "bpm": 0}

    for record in records:
        labels = record.get("labels") or {}
        dataset_counts[record.get("dataset", "?")] += 1
        split_counts[record.get("split", "?")] += 1
        license_counts[str(record.get("license") or "unknown")] += 1
        hours += float(record.get("duration_sec") or 0.0) / 3600.0
        if labels.get("genre"):
            genre_counts[labels["genre"]] += 1
            labeled["genre"] += 1
        if labels.get("emotion"):
            emotion_counts[labels["emotion"]] += 1
            labeled["emotion"] += 1
        if labels.get("mode") and float(labels.get("key_confidence") or 0) >= 0.35:
            mode_counts[labels["mode"]] += 1
            labeled["mode"] += 1
        if labels.get("bpm") and float(labels.get("bpm_confidence") or 0) >= 0.15:
            bpm_values.append(float(labels["bpm"]))
            labeled["bpm"] += 1

    return {
        "tracks": len(records),
        "hours": round(hours, 2),
        "by_dataset": dict(dataset_counts),
        "by_split": dict(split_counts),
        "labeled_tracks": labeled,
        "genre": dict(genre_counts.most_common()),
        "emotion": dict(emotion_counts.most_common()),
        "mode": dict(mode_counts.most_common()),
        "bpm_mean": round(float(np.mean(bpm_values)), 2) if bpm_values else None,
        "bpm_median": round(float(np.median(bpm_values)), 2) if bpm_values else None,
        "bpm_std": round(float(np.std(bpm_values)), 2) if bpm_values else None,
        "licenses": dict(license_counts.most_common(20)),
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", default="data", help="dataset root (default: data)")
    parser.add_argument(
        "--out-dir", default="training/data", help="manifest + cache output directory"
    )
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 4))
    parser.add_argument(
        "--fma-cache-seconds", type=float, default=30.0, help="FMA clips are 30 s"
    )
    parser.add_argument(
        "--jamendo-cache-seconds",
        type=float,
        default=90.0,
        help="centre segment cached for full-length Jamendo tracks",
    )
    parser.add_argument("--min-duration", type=float, default=10.0)
    parser.add_argument(
        "--license-policy",
        choices=("research", "commercial", "all"),
        default="research",
        help="research keeps CC BY-NC; commercial excludes NC/ND and all Jamendo",
    )
    parser.add_argument("--limit", type=int, default=0, help="debug: limit tracks")
    parser.add_argument("--no-fma", action="store_true")
    parser.add_argument("--no-jamendo", action="store_true")
    parser.add_argument(
        "--no-manymusic",
        action="store_true",
        help="skip the ManyMusic MTG-Jamendo subset (data/manymusic)",
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="skip the MERGE emotion corpus (data/merge)",
    )
    parser.add_argument(
        "--merge-cache-seconds",
        type=float,
        default=30.0,
        help="MERGE excerpts are 30 s long",
    )
    parser.add_argument(
        "--overwrite-cache", action="store_true", help="recompute existing caches"
    )
    parser.add_argument(
        "--flush-every", type=int, default=200, help="checkpoint manifest every N tracks"
    )
    parser.add_argument(
        "--taxonomy",
        default=str(Path(__file__).resolve().parent / "labels" / "taxonomy.json"),
    )
    args = parser.parse_args(argv)

    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")

    root = Path(args.root).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    cache_dir = out_dir / "cache"
    manifest_path = out_dir / "manifest.jsonl"
    if not out_dir.exists():
        out_dir.mkdir(parents=True, exist_ok=True)

    taxonomy = Taxonomy(args.taxonomy)
    tasks = build_tasks(root, cache_dir, taxonomy, args)
    if not tasks:
        print("No audio found. Run download_datasets.py first.", file=sys.stderr)
        return 2

    for task in tasks:
        audio_path = Path(task["audio"])
        try:
            task["audio_relative"] = audio_path.resolve().relative_to(root).as_posix()
        except ValueError:
            task["audio_relative"] = task["audio"]
        task["cache_relative"] = Path(task["cache"]).relative_to(out_dir).as_posix()
        if args.overwrite_cache:
            task["overwrite_cache"] = True

    existing = load_existing_manifest(manifest_path)
    pending = [
        task
        for task in tasks
        if not (
            not args.overwrite_cache
            and task["id"] in existing
            and Path(existing[task["id"]].get("cache", "")).name
            and (out_dir / existing[task["id"]]["cache"]).exists()
        )
    ]

    print(f"Tracks discovered : {len(tasks)}")
    print(f"Already labelled  : {len(tasks) - len(pending)}")
    print(f"To process        : {len(pending)}")
    print(f"Workers           : {args.workers}")
    print(f"Cache directory   : {cache_dir}")
    print(f"Licence policy    : {args.license_policy}")

    results: Dict[str, Dict[str, Any]] = dict(existing)
    started = time.time()
    done = 0
    failed = 0

    if pending:
        with ProcessPoolExecutor(
            max_workers=max(1, args.workers),
            initializer=_init_worker,
            initargs=(args.taxonomy,),
        ) as pool:
            futures = {pool.submit(process_track, task): task for task in pending}
            for future in as_completed(futures):
                task = futures[future]
                try:
                    record = future.result()
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    print(f"  FAIL {task['id']}: {exc}", file=sys.stderr)
                    continue
                if record is None:
                    failed += 1
                    continue
                results[record["id"]] = record
                done += 1
                if done % args.flush_every == 0:
                    write_manifest(manifest_path, results.values())
                    elapsed = time.time() - started
                    rate = done / max(elapsed, 1e-6)
                    print(
                        f"  {done}/{len(pending)} processed, {failed} failed, "
                        f"{rate:.2f} tracks/s",
                        flush=True,
                    )

    # Drop exact duplicates (same decoded audio) but keep the first by id.
    unique: Dict[str, Dict[str, Any]] = {}
    seen_hashes: Dict[str, str] = {}
    for record in sorted(results.values(), key=lambda item: item["id"]):
        fingerprint = record.get("audio_hash")
        if fingerprint and fingerprint in seen_hashes:
            continue
        if fingerprint:
            seen_hashes[fingerprint] = record["id"]
        unique[record["id"]] = record

    write_manifest(manifest_path, unique.values())
    stats = build_stats(list(unique.values()))
    stats_path = out_dir / "manifest_stats.json"
    stats_path.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    report = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "root": str(root),
        "manifest": str(manifest_path),
        "split_policy": {"train": 0.8, "val": 0.1, "test": 0.1},
        "license_policy": args.license_policy,
        "discovered": len(tasks),
        "labelled_total": len(unique),
        "processed_now": done,
        "failed": failed,
        "seconds": round(time.time() - started, 1),
        "stats": stats,
    }
    (out_dir / "label_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print("\nLabel summary")
    print(f"  tracks     : {stats['tracks']} ({stats['hours']} h)")
    print(f"  genre      : {stats['labeled_tracks']['genre']}")
    print(f"  emotion    : {stats['labeled_tracks']['emotion']}")
    print(f"  mode       : {stats['labeled_tracks']['mode']}")
    print(f"  bpm        : {stats['labeled_tracks']['bpm']}")
    print(f"  splits     : {stats['by_split']}")
    print(f"  manifest   : {manifest_path}")
    print(f"  stats      : {stats_path}")
    print("\nNext: python training/train.py --manifest training/data/manifest.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
