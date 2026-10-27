"""从 WikiArt 公开分类页下载少量画作，用于画风分类模型训练。

用法：python download_data.py
输出：../data/wikiart/<style>/*.jpg
"""
import csv
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

import requests

BASE = "https://www.wikiart.org/en/paintings-by-style/{style}?json=2&page={page}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ArtClassProject/1.0"}
STYLES = [
    "impressionism",
    "post-impressionism",
    "realism",
    "romanticism",
    "expressionism",
    "cubism",
    "baroque",
    "art-nouveau",
]
PAGES = 2
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "wikiart")


def collect(style: str):
    items = []
    for page in range(1, PAGES + 1):
        try:
            r = requests.get(BASE.format(style=style, page=page), headers=HEADERS, timeout=20)
            r.raise_for_status()
            for p in r.json().get("Paintings") or []:
                if p.get("image") and p.get("id"):
                    items.append((p["id"], p["image"], p.get("artistName", ""), p.get("title", "")))
        except Exception as exc:
            print(f"[warn] {style} page {page}: {exc}")
        time.sleep(0.15)
    return items


def download_one(job):
    style, pid, url, artist, title = job
    folder = os.path.join(OUT, style)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{pid}.jpg")
    if os.path.exists(path) and os.path.getsize(path) > 2000:
        return (style, pid, artist, title, "cached")
    img_url = url if url.endswith(("!Large.jpg", "!PinterestLarge.jpg")) else url + "!Large.jpg"
    try:
        r = requests.get(img_url, headers=HEADERS, timeout=25)
        if r.status_code != 200 or len(r.content) < 2000:
            return (style, pid, artist, title, f"fail:{r.status_code}")
        with open(path, "wb") as f:
            f.write(r.content)
        return (style, pid, artist, title, "ok")
    except Exception as exc:
        return (style, pid, artist, title, f"err:{exc}")


def main():
    os.makedirs(OUT, exist_ok=True)
    jobs, manifest = [], []
    for style in STYLES:
        items = collect(style)
        print(f"{style}: {len(items)} candidates")
        for pid, url, artist, title in items:
            jobs.append((style, pid, url, artist, title))

    stats = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for style, pid, artist, title, status in pool.map(download_one, jobs):
            stats.setdefault(style, {}).setdefault(status, 0)
            stats[style][status] += 1
            manifest.append({"style": style, "id": pid, "artist": artist, "title": title, "status": status})

    os.makedirs(os.path.join(OUT, "..", "..", "training"), exist_ok=True)
    with open(os.path.join(os.path.dirname(__file__), "manifest.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["style", "id", "artist", "title", "status"])
        writer.writeheader()
        writer.writerows(manifest)

    for style, s in stats.items():
        ok = s.get("ok", 0) + s.get("cached", 0)
        print(f"{style:20s} ok={ok:4d}  detail={s}")


if __name__ == "__main__":
    main()
