#!/usr/bin/env python3
"""Download openly licensed music for local model testing / evaluation.

Sources
-------
* Incompetech (Kevin MacLeod) -- CC BY 4.0, catalog JSON + direct MP3 files.
* Free Music Archive -- Creative Commons licensed tracks, scraped from
  genre listing pages; direct file URLs are read from each track page.

Only openly licensed material is fetched. No paywalled or DRM content is
accessed. Every downloaded file is recorded in ``manifest.jsonl`` together
with its license and source URL so the corpus can be filtered later.

Usage
-----
    python scripts/fetch_open_music.py --output "E:/测试音乐文档"
    python scripts/fetch_open_music.py --output DIR --sources fma --fma-per-genre 40
    python scripts/fetch_open_music.py --output DIR --sources incompetech --limit 100
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

INCOMPETECH_BASE = "https://incompetech.com/music/royalty-free/"
INCOMPETECH_MP3 = INCOMPETECH_BASE + "mp3-royaltyfree/"

FMA_BASE = "https://freemusicarchive.org"
FMA_GENRES = [
    "Blues",
    "Classical",
    "Country",
    "Electronic",
    "Experimental",
    "Folk",
    "Hip-Hop",
    "Instrumental",
    "International",
    "Jazz",
    "Old-Time__Historic",
    "Pop",
    "Rock",
    "Soul-RB",
    "novelty",
]

# Audio containers we are willing to store.
_AUDIO_MAGIC = (b"ID3", b"fLaC", b"OggS", b"RIFF", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xf1", b"ftyp")
_BAD_MAGIC = (b"<!DOCTYPE", b"<html", b"<HTML", b"{", b"[")

_FMA_TRACK_RE = re.compile(r"data-track-info='(\{.*?\})'")
_FMA_FILE_RE = re.compile(r'"fileUrl":"(https:(?:\\/\\/|\/\/)[^"]+)"')
_CC_RE = re.compile(r"creativecommons\.org/licenses/([a-z\-]+)/([0-9.]+)")
_BAD_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize(name: str, max_len: int = 120) -> str:
    """Make a string safe as a Windows file name."""
    name = _BAD_NAME.sub("_", name).strip().strip(".")
    name = re.sub(r"\s+", " ", name)
    name = name[:max_len].strip().strip(".")
    return name or "untitled"


def http_get(url: str, timeout: int = 30, retries: int = 3) -> bytes:
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "*/*",
                    "Accept-Language": "en-US,en;q=0.8,zh-CN;q=0.6",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            # 404/410 are permanent - retrying only wastes time.
            if exc.code in (404, 410):
                raise RuntimeError(f"GET failed: {url} (HTTP {exc.code})") from exc
            last = exc
            time.sleep(1.0 * (attempt + 1) + random.random())
        except Exception as exc:  # noqa: BLE001 - retry transport errors
            last = exc
            time.sleep(1.0 * (attempt + 1) + random.random())
    raise RuntimeError(f"GET failed: {url} ({last})")


def http_head_length(url: str, timeout: int = 20) -> Optional[int]:
    """Return Content-Length for ``url`` if the server reports one."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            value = resp.headers.get("Content-Length")
            return int(value) if value and value.isdigit() else None
    except Exception:  # noqa: BLE001 - HEAD is best-effort
        return None


def download(url: str, dest: Path, timeout: int = 90, retries: int = 3) -> int:
    """Stream ``url`` to ``dest`` atomically. Returns bytes written."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as fh:
                shutil.copyfileobj(resp, fh, length=256 * 1024)
            with open(tmp, "rb") as fh:
                head = fh.read(12)
            if head.startswith(_BAD_MAGIC):
                raise RuntimeError("server returned a non-audio document")
            if not head.startswith(_AUDIO_MAGIC):
                raise RuntimeError(f"unrecognized audio header: {head!r}")
            size = tmp.stat().st_size
            if size < 2048:
                raise RuntimeError(f"suspiciously small file ({size} bytes)")
            tmp.replace(dest)
            return size
        except Exception as exc:  # noqa: BLE001
            last = exc
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            time.sleep(1.5 * (attempt + 1) + random.random())
    raise RuntimeError(f"download failed: {url} ({last})")


def probe_audio(path: Path) -> dict[str, Any]:
    """Cheap local metadata probe; never raises."""
    try:
        import soundfile as sf  # type: ignore

        info = sf.info(str(path))
        return {
            "duration_sec": round(float(info.frames) / float(info.samplerate), 2),
            "sample_rate": int(info.samplerate),
            "channels": int(info.channels),
            "format": info.format,
        }
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Incompetech
# ---------------------------------------------------------------------------


def collect_incompetech(limit: int) -> list[dict[str, Any]]:
    pieces = json.loads(http_get(INCOMPETECH_BASE + "pieces.json", timeout=60))
    genres_raw = json.loads(http_get(INCOMPETECH_BASE + "genre.json"))
    genre_map = {str(g["id"]): g["genre"] for g in genres_raw}
    out = []
    for piece in pieces:
        filename = piece.get("filename") or ""
        if not filename.lower().endswith((".mp3", ".wav", ".flac")):
            continue
        out.append(
            {
                "source": "incompetech",
                "title": piece.get("title") or Path(filename).stem,
                "filename": filename,
                "artist": "Kevin MacLeod",
                "genre": genre_map.get(str(piece.get("genre")), "Unclassified"),
                "bpm": piece.get("bpm"),
                "length": piece.get("length"),
                "instruments": piece.get("instruments"),
                "isrc": piece.get("isrc"),
                "license": "CC BY 4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "source_url": "https://incompetech.com/music/royalty-free/music.html",
                "file_url": INCOMPETECH_MP3 + urllib.parse.quote(filename),
            }
        )
    return out[:limit] if limit else out


# ---------------------------------------------------------------------------
# Free Music Archive
# ---------------------------------------------------------------------------


def collect_fma_track(genre: str, info: dict[str, Any]) -> Optional[dict[str, Any]]:
    page_url = info.get("url")
    handle = info.get("handle")
    if not page_url or not handle:
        return None
    # Some catalog entries have an empty album segment ("/artist//track/"),
    # which 404s on the site. Skip them instead of retrying.
    path = urllib.parse.urlparse(page_url).path
    if "//" in path:
        return None
    html = http_get(page_url, timeout=30).decode("utf-8", "ignore")
    match = _FMA_FILE_RE.search(html)
    if not match:
        return None
    file_url = match.group(1).replace("\\/", "/")
    if not file_url.startswith("http"):
        file_url = "https:" + file_url

    cc = _CC_RE.search(html)
    if not cc:
        return None  # not openly licensed -> skip

    ext = Path(urllib.parse.urlparse(file_url).path).suffix.lower() or ".mp3"
    return {
        "source": "freemusicarchive",
        "title": info.get("title") or handle,
        "artist": info.get("artistName") or "Unknown",
        "genre": genre,
        "license": f"CC {cc.group(1).upper()} {cc.group(2)}",
        "license_url": f"https://creativecommons.org/licenses/{cc.group(1)}/{cc.group(2)}/",
        "source_url": page_url,
        "file_url": file_url,
        "ext": ext,
    }


def collect_fma_genre(genre: str, per_genre: int, workers: int) -> list[dict[str, Any]]:
    infos: list[dict[str, Any]] = []
    page = 1
    while len(infos) < per_genre and page <= max(1, per_genre // 20 + 2):
        url = f"{FMA_BASE}/genre/{urllib.parse.quote(genre)}/?page={page}"
        try:
            html = http_get(url, timeout=30).decode("utf-8", "ignore")
        except RuntimeError as exc:
            print(f"  [fma/{genre}] listing page {page} failed: {exc}", file=sys.stderr)
            break
        found = []
        for raw in _FMA_TRACK_RE.findall(html):
            try:
                found.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        if not found:
            break
        infos.extend(found)
        page += 1
    infos = infos[:per_genre]

    tracks: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(collect_fma_track, genre, info): info for info in infos}
        for fut in as_completed(futures):
            try:
                track = fut.result()
            except Exception as exc:  # noqa: BLE001
                print(f"  [fma/{genre}] track page failed: {exc}", file=sys.stderr)
                continue
            if track:
                tracks.append(track)
    return tracks


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", required=True, help="target directory")
    parser.add_argument("--sources", default="incompetech,fma", help="comma list: incompetech,fma")
    parser.add_argument("--incompetech-limit", type=int, default=0, help="0 = all")
    parser.add_argument("--fma-per-genre", type=int, default=60, help="tracks per FMA genre")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--max-file-mb", type=float, default=30.0,
                        help="skip files larger than this (0 = no limit); avoids hour-long mixes")
    args = parser.parse_args(argv)

    out_dir = Path(args.output).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.jsonl"

    sources = {s.strip().lower() for s in args.sources.split(",") if s.strip()}

    items: list[dict[str, Any]] = []
    if "incompetech" in sources:
        print("Collecting Incompetech catalog ...")
        items.extend(collect_incompetech(args.incompetech_limit))
        print(f"  {len(items)} tracks")
    if "fma" in sources:
        print("Collecting Free Music Archive ...")
        for genre in FMA_GENRES:
            tracks = collect_fma_genre(genre, args.fma_per_genre, args.workers)
            print(f"  {genre}: {len(tracks)} tracks")
            items.extend(tracks)

    # A track can appear under several genres; keep the first occurrence.
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        key = item["file_url"]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    items = unique

    if not items:
        print("Nothing to download.", file=sys.stderr)
        return 1

    max_bytes = int(args.max_file_mb * 1024 * 1024) if args.max_file_mb > 0 else 0
    print(f"\nDownloading {len(items)} tracks to {out_dir} "
          f"with {args.workers} workers ...", flush=True)

    done = 0
    failed = 0
    total_bytes = 0
    started = time.time()

    def task(item: dict[str, Any]) -> tuple[dict[str, Any], int]:
        if item["source"] == "incompetech":
            sub = out_dir / "incompetech" / sanitize(item["genre"])
            dest = sub / (sanitize(item["title"]) + Path(item["filename"]).suffix.lower())
        else:
            sub = out_dir / "fma" / sanitize(item["genre"])
            dest = sub / (sanitize(f"{item['artist']} - {item['title']}") + item["ext"])

        if dest.exists() and dest.stat().st_size > 2048:
            return {**item, "path": str(dest.relative_to(out_dir)), "bytes": dest.stat().st_size,
                    "skipped": True}, 0

        if max_bytes:
            length = http_head_length(item["file_url"])
            if length is not None and length > max_bytes:
                raise RuntimeError(f"skipped: {length / 1024 / 1024:.1f} MB exceeds --max-file-mb")

        size = download(item["file_url"], dest, timeout=args.timeout)
        record = {k: v for k, v in item.items() if k not in ("filename", "ext")}
        record["path"] = str(dest.relative_to(out_dir))
        record["bytes"] = size
        record["downloaded_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        record.update(probe_audio(dest))
        return record, size

    with open(manifest_path, "a", encoding="utf-8") as manifest, \
            ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(task, item): item for item in items}
        for fut in as_completed(futures):
            item = futures[fut]
            try:
                record, size = fut.result()
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"  FAIL {item.get('title')!r}: {exc}", file=sys.stderr)
                continue
            manifest.write(json.dumps(record, ensure_ascii=False) + "\n")
            manifest.flush()
            done += 1
            total_bytes += size
            if done % 25 == 0 or done == len(items):
                elapsed = time.time() - started
                rate = total_bytes / elapsed / 1024 / 1024 if elapsed else 0
                print(f"  {done}/{len(items)} done, {failed} failed, "
                      f"{total_bytes / 1024 / 1024:.0f} MB, {rate:.1f} MB/s")

    elapsed = time.time() - started
    print(f"\nFinished in {elapsed / 60:.1f} min: {done} ok, {failed} failed, "
          f"{total_bytes / 1024 / 1024:.0f} MB")
    print(f"Manifest: {manifest_path}")
    return 0 if done else 1


if __name__ == "__main__":
    raise SystemExit(main())
