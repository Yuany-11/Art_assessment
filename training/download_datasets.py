#!/usr/bin/env python3
"""Download an openly licensed ~32 GB corpus for ArtEval training.

Sources (verified 2026-10)
--------------------------
* FMA-medium  -- 25,000 CC-licensed 30 s clips, ~23.8 GB.
  https://github.com/mdeff/fma  (metadata, checksums)
* MTG-Jamendo mood/theme subset -- full-length Creative Commons tracks with
  59 human mood/theme tags, low-bitrate mono, ~46 GB for all 100 shards.
  https://github.com/MTG/mtg-jamendo-dataset

The default target is 32 GB: all of FMA-medium plus as many Jamendo shards as
needed (usually the first 15-17 shards, ~3,000 tagged tracks).

Licensing
---------
FMA audio is licensed individually by each artist (many CC BY-NC); Jamendo
metadata is CC BY-NC-SA and audio is individually CC-licensed.  **This corpus
is intended for research/evaluation.  Review the per-track licence in the
manifest before any commercial deployment.**  Use ``label_dataset.py
--license-policy commercial`` to keep only tracks whose licence allows
commercial reuse (this filters most of the corpus).

Usage
-----
    python training/download_datasets.py --root data --target-gb 32
    python training/download_datasets.py --root data --no-jamendo
    python training/download_datasets.py --root data --no-fma --jamendo-shards 4
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

FMA_BASE = "https://os.unil.cloud.switch.ch/fma"
FMA_METADATA_URL = f"{FMA_BASE}/fma_metadata.zip"
FMA_MEDIUM_URL = f"{FMA_BASE}/fma_medium.zip"
FMA_MEDIUM_BYTES = 23_825_005_356

JAMENDO_AUDIO_BASE = (
    "https://essentia.upf.edu/documentation/datasets/mtg-jamendo/"
    "autotagging_moodtheme/audio-low"
)
JAMENDO_SHARD_NAME = "autotagging_moodtheme_audio-low-{index:02d}.tar"
JAMENDO_META_BASE = (
    "https://raw.githubusercontent.com/MTG/mtg-jamendo-dataset/master/data"
)
JAMENDO_META_FILES = (
    "autotagging_moodtheme.tsv",
    "autotagging_genre.tsv",
)

USER_AGENT = "ArtEval-dataset-loader/1.0 (+https://arteval.local)"
CHUNK = 4 * 1024 * 1024


def _log(message: str) -> None:
    print(message, flush=True)


def _human(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024.0 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def _head_size(url: str, timeout: int = 30) -> Optional[int]:
    try:
        request = urllib.request.Request(
            url, method="HEAD", headers={"User-Agent": USER_AGENT}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = response.headers.get("Content-Length")
            return int(value) if value and value.isdigit() else None
    except Exception:
        return None


def download_file(
    url: str,
    dest: Path,
    *,
    expected_size: Optional[int] = None,
    retries: int = 4,
) -> int:
    """Resumable download.  Returns the final file size in bytes."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")

    if dest.exists():
        size = dest.stat().st_size
        if expected_size is None or size == expected_size:
            _log(f"  [skip] {dest.name} ({_human(size)})")
            return size
        _log(f"  [size mismatch] {dest.name}: {size} != {expected_size}, re-downloading")
        dest.unlink(missing_ok=True)

    for attempt in range(1, retries + 1):
        offset = part.stat().st_size if part.exists() else 0
        if expected_size is not None and offset == expected_size:
            part.replace(dest)
            return expected_size
        if expected_size is not None and offset > expected_size:
            part.unlink(missing_ok=True)
            offset = 0

        headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
            _log(f"  [resume] {dest.name} at {_human(offset)}")
        else:
            _log(f"  [get] {dest.name}" + (f" ({_human(expected_size)})" if expected_size else ""))

        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status = getattr(response, "status", 200)
                if offset and status != 206:
                    # Server ignored Range: start over.
                    offset = 0
                    part.unlink(missing_ok=True)
                    _log("  [server does not support Range; restarting]")
                total = None
                content_length = response.headers.get("Content-Length")
                if content_length and content_length.isdigit():
                    total = int(content_length) + offset
                started = time.time()
                last_report = 0.0
                with open(part, "ab" if offset else "wb") as handle:
                    while True:
                        block = response.read(CHUNK)
                        if not block:
                            break
                        handle.write(block)
                        offset += len(block)
                        now = time.time()
                        if now - last_report >= 5.0:
                            rate = (offset / max(now - started, 1e-6)) / 1024 / 1024
                            pct = f" ({offset / total * 100:.1f}%)" if total else ""
                            _log(f"    {_human(offset)}{pct} @ {rate:.1f} MB/s")
                            last_report = now
            size = part.stat().st_size if part.exists() else 0
            if expected_size is not None and size != expected_size:
                raise RuntimeError(
                    f"incomplete download: {size} != {expected_size} bytes"
                )
            part.replace(dest)
            _log(f"  [ok] {dest.name} ({_human(size)})")
            return size
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 410):
                raise RuntimeError(f"HTTP {exc.code}: {url}") from exc
            _log(f"  [retry {attempt}/{retries}] HTTP {exc.code} {dest.name}")
            time.sleep(2.0 * attempt)
        except Exception as exc:  # noqa: BLE001 - transport/retry
            _log(f"  [retry {attempt}/{retries}] {dest.name}: {exc}")
            time.sleep(2.0 * attempt)

    raise RuntimeError(f"download failed after {retries} attempts: {url}")


def _safe_tar_members(tar: tarfile.TarFile, dest: Path) -> Iterable[tarfile.TarInfo]:
    root = dest.resolve()
    for member in tar.getmembers():
        target = (dest / member.name).resolve()
        if root != target and root not in target.parents:
            _log(f"  [skip unsafe path] {member.name}")
            continue
        if member.issym() or member.islnk():
            continue
        yield member


def extract_archive(path: Path, dest: Path, *, remove: bool = False) -> None:
    """Extract zip/tar, including Windows' deflate64 zip fallback."""
    dest.mkdir(parents=True, exist_ok=True)
    _log(f"  [extract] {path.name} -> {dest}")
    if zipfile.is_zipfile(path):
        try:
            with zipfile.ZipFile(path) as archive:
                archive.extractall(dest)
        except (NotImplementedError, RuntimeError, zipfile.BadZipFile) as exc:
            _log(f"  [zip fallback] {exc}")
            if os.name == "nt":
                subprocess.run(
                    ["tar", "-xf", str(path), "-C", str(dest)], check=True
                )
            else:
                subprocess.run(
                    ["unzip", "-o", "-q", str(path), "-d", str(dest)], check=True
                )
    elif tarfile.is_tarfile(path):
        with tarfile.open(path, "r:*") as archive:
            archive.extractall(dest, members=_safe_tar_members(archive, dest))
    else:
        raise RuntimeError(f"unsupported archive: {path}")

    if remove:
        path.unlink(missing_ok=True)
        _log(f"  [remove] {path.name}")


def directory_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def download_fma(root: Path, args: argparse.Namespace) -> Dict[str, Any]:
    raw = root / "raw"
    meta_zip = raw / "fma_metadata.zip"
    medium_zip = raw / "fma_medium.zip"

    meta_info = {"downloaded": False, "bytes": 0}
    if not (root / "fma_metadata" / "tracks.csv").exists():
        size = download_file(
            FMA_METADATA_URL,
            meta_zip,
            expected_size=_head_size(FMA_METADATA_URL),
        )
        extract_archive(meta_zip, root, remove=args.remove_archives)
        meta_info = {"downloaded": True, "bytes": size}
    else:
        _log("  [skip] fma_metadata already extracted")

    medium_dir = root / "fma_medium"
    audio_info = {"downloaded": False, "bytes": directory_bytes(medium_dir)}
    if not audio_info["bytes"]:
        size = download_file(
            FMA_MEDIUM_URL,
            medium_zip,
            expected_size=_head_size(FMA_MEDIUM_URL) or FMA_MEDIUM_BYTES,
        )
        extract_archive(medium_zip, root, remove=args.remove_archives)
        audio_info = {"downloaded": True, "bytes": directory_bytes(medium_dir) or size}
    else:
        _log(f"  [skip] fma_medium already extracted ({_human(audio_info['bytes'])})")

    return {"metadata": meta_info, "audio": audio_info}


def download_jamendo_metadata(root: Path) -> Dict[str, Any]:
    meta_dir = root / "jamendo_meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    files: Dict[str, int] = {}
    for name in JAMENDO_META_FILES:
        dest = meta_dir / name
        url = f"{JAMENDO_META_BASE}/{name}"
        if dest.exists() and dest.stat().st_size > 1024:
            files[name] = dest.stat().st_size
            continue
        files[name] = download_file(url, dest)
    return files


def download_jamendo(root: Path, args: argparse.Namespace) -> Dict[str, Any]:
    raw = root / "raw" / "jamendo"
    audio_dir = root / "jamendo"
    metadata = download_jamendo_metadata(root)

    if args.jamendo_shards is not None and args.jamendo_shards >= 0:
        shard_indices = list(range(args.jamendo_shards))
    else:
        shard_indices = list(range(100))

    report = {"metadata": metadata, "shards": [], "bytes": directory_bytes(audio_dir)}
    target_bytes = int(args.target_gb * 1e9) if args.target_gb > 0 else 0
    fma_bytes = directory_bytes(root / "fma_medium")
    if not fma_bytes:
        medium_zip = root / "raw" / "fma_medium.zip"
        fma_bytes = medium_zip.stat().st_size if medium_zip.exists() else 0

    for index in shard_indices:
        if target_bytes and fma_bytes + report["bytes"] >= target_bytes:
            _log(f"  [done] target {args.target_gb} GB reached")
            break
        name = JAMENDO_SHARD_NAME.format(index=index)
        url = f"{JAMENDO_AUDIO_BASE}/{name}"
        dest = raw / name
        if not dest.exists():
            expected = _head_size(url)
            if expected is None:
                _log(f"  [skip] shard {index:02d} unavailable")
                continue
            size = download_file(url, dest, expected_size=expected)
        else:
            size = dest.stat().st_size

        # Extract only if this shard has not been unpacked yet.
        marker = audio_dir / f".shard-{index:02d}.done"
        if not marker.exists():
            extract_archive(dest, audio_dir)
            if args.remove_archives:
                dest.unlink(missing_ok=True)
            marker.write_text(str(size), encoding="utf-8")
        report["shards"].append({"index": index, "bytes": size})
        report["bytes"] = directory_bytes(audio_dir)
        _log(
            f"  shard {index:02d}: {_human(size)}; "
            f"corpus {_human(report['bytes'])} (+FMA {_human(fma_bytes)})"
        )

    return report


def _disk_free_gb(path: Path) -> float:
    try:
        return shutil.disk_usage(path).free / 1e9
    except OSError:
        return 0.0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", default="data", help="dataset root (default: data)")
    parser.add_argument(
        "--target-gb",
        type=float,
        default=32.0,
        help="stop downloading Jamendo shards once the corpus reaches this size (0 = all)",
    )
    parser.add_argument("--no-fma", action="store_true", help="skip FMA-medium")
    parser.add_argument("--no-jamendo", action="store_true", help="skip MTG-Jamendo")
    parser.add_argument(
        "--jamendo-shards",
        type=int,
        default=None,
        help="exact number of Jamendo tar shards (default: enough for --target-gb)",
    )
    parser.add_argument(
        "--remove-archives",
        action="store_true",
        help="delete archives after extraction to save disk space",
    )
    parser.add_argument(
        "--min-free-gb",
        type=float,
        default=60.0,
        help="abort if free disk is below this threshold (default 60; use "
        "--remove-archives and ~50 GB, or override for smaller runs)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    free = _disk_free_gb(root)
    _log(f"Dataset root: {root}")
    _log(f"Free disk: {free:.1f} GB")
    if free < args.min_free_gb:
        _log(
            f"ERROR: need at least {args.min_free_gb} GB free for archives, audio "
            "and the feature cache. Use --min-free-gb to override."
        )
        return 2

    _log("\nLicensing: research/evaluation corpus. FMA audio is individually "
         "licensed (many CC BY-NC); Jamendo is CC BY-NC-SA. Review licences "
         "before commercial use.\n")

    report: Dict[str, Any] = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "root": str(root),
        "target_gb": args.target_gb,
    }
    if not args.no_fma:
        _log("== FMA-medium ==")
        report["fma"] = download_fma(root, args)
    if not args.no_jamendo:
        _log("\n== MTG-Jamendo mood/theme ==")
        report["jamendo"] = download_jamendo(root, args)

    total = (
        directory_bytes(root / "fma_medium")
        + directory_bytes(root / "jamendo")
        + directory_bytes(root / "fma_metadata")
    )
    report["corpus_bytes"] = total
    report["corpus_gb"] = round(total / 1e9, 2)
    report_path = root / "download_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    _log(f"\nCorpus on disk: {_human(total)} ({report['corpus_gb']} GB)")
    _log(f"Report: {report_path}")
    _log("\nNext: python training/label_dataset.py --root data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
