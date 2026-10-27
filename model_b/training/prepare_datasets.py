"""从原始画作生成两个训练数据集。

产出：
  data/02_quality/{train,val}/{normal,blur,dark,noisy}/   图片质量分类
  data/03_scoring/{images,train.csv,val.csv}              四维评分回归（规则伪标签）

用法：python prepare_datasets.py
"""
import csv
import os
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

HERE = Path(__file__).resolve().parent
ROOT = Path(os.getenv("ART_ROOT", HERE.parents[2]))
DATA = Path(os.getenv("ART_DATA", ROOT / "data"))
RAW = DATA / "01_raw" / "wikiart"
QUAL = DATA / "02_quality"
SCORE = DATA / "03_scoring"

sys.path.insert(0, str(HERE.parent))
from scoring import score_image  # noqa: E402

SEED = 42
QUALITY_SOURCES = 400
SCORING_SOURCES = 600
RNG = np.random.default_rng(SEED)


def list_images():
    exts = {".jpg", ".jpeg", ".png"}
    return sorted(p for p in RAW.rglob("*") if p.suffix.lower() in exts)


def split(items, ratio=0.8):
    rng = random.Random(SEED)
    items = list(items)
    rng.shuffle(items)
    cut = int(len(items) * ratio)
    return items[:cut], items[cut:]


def quality_variants(img):
    base = img.convert("RGB")
    base.thumbnail((256, 256))
    blur = base.filter(ImageFilter.GaussianBlur(4))
    dark = ImageEnhance.Brightness(base).enhance(0.35)
    arr = np.asarray(base).astype(np.int16)
    noise = RNG.normal(0, 25, arr.shape)
    noisy = Image.fromarray(np.clip(arr + noise, 0, 255).astype(np.uint8))
    return {"normal": base, "blur": blur, "dark": dark, "noisy": noisy}


def build_quality(images):
    for split_name, subset in (("train", images[0]), ("val", images[1])):
        for cls in ("normal", "blur", "dark", "noisy"):
            (QUAL / split_name / cls).mkdir(parents=True, exist_ok=True)
        for i, src in enumerate(subset):
            try:
                img = Image.open(src)
            except Exception:
                continue
            for cls, out in quality_variants(img).items():
                out.save(QUAL / split_name / cls / f"{i:04d}_{src.stem}.jpg", quality=90)
    return {s: len(v) for s, v in (("train", images[0]), ("val", images[1]))}


def build_scoring(images):
    (SCORE / "images").mkdir(parents=True, exist_ok=True)
    rows = []
    for i, src in enumerate(images):
        try:
            img = Image.open(src).convert("RGB")
        except Exception:
            continue
        img.thumbnail((512, 512))
        name = f"{i:04d}_{src.stem}.jpg"
        img.save(SCORE / "images" / name, quality=90)
        res = score_image(img)
        s = res["scores"]
        rows.append({
            "image_path": f"images/{name}",
            "composition": s["composition"],
            "color": s["color"],
            "modeling": s["modeling"],
            "creativity": s["creativity"],
            "total": s["total"],
        })
        if (i + 1) % 100 == 0:
            print(f"scoring: {i + 1}/{len(images)}")
    train, val = split(rows)
    fields = ["image_path", "composition", "color", "modeling", "creativity", "total"]
    for name, part in (("train", train), ("val", val)):
        with open(SCORE / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(part)
    return len(train), len(val)


def main():
    images = list_images()
    if not images:
        raise SystemExit(f"没有找到原图，请先准备 {RAW}")
    print(f"原图 {len(images)} 张，来自 {RAW}")

    q_sources = images[:QUALITY_SOURCES]
    q_train, q_val = split(q_sources)
    print("质量检测数据:", build_quality((q_train, q_val)), "张原图")

    s_sources = images[:SCORING_SOURCES]
    s_train, s_val = split(s_sources)
    print("评分数据:", build_scoring(s_train + s_val), "条")


if __name__ == "__main__":
    main()
