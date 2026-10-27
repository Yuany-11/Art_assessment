"""APDDv2 数据核查（只读，不训练、不改文件）。

用法：
    python check_apddv2.py
    python check_apddv2.py --root E:\\Lab_Files\\Project\\Art_assessment\\data\\05_apddv2

检查内容：CSV 编码、列名、每维有效/缺失数量、分数范围、类别分布、
图片能否对上、四维映射后的有效样本数。
"""
import argparse
import csv
import os
import random
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = Path(os.getenv("ART_ROOT", HERE.parents[2]))
DEFAULT_ROOT = Path(os.getenv("ART_DATA", ROOT / "data")) / "05_apddv2"
CSV_NAME = "APDDv2-10023.csv"
ENCODINGS = ("utf-8-sig", "gb18030", "latin-1")
DIMS = ("构图", "色彩", "造型", "创意")
COLS = {
    "构图": "Layout and composition",
    "色彩": "Color",
    "造型_空间": "Space and perspective",
    "造型_细节": "Details and texture",
    "创意": "Creativity",
    "总分": "The overall",
}
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def num(row, col):
    v = (row.get(col) or "").strip()
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def read_csv(path):
    last = None
    for enc in ENCODINGS:
        try:
            with open(path, encoding=enc, newline="") as f:
                return list(csv.DictReader(f)), enc
        except UnicodeDecodeError as e:
            last = e
    raise SystemExit(f"CSV 编码无法识别（试过 {ENCODINGS}）：{last}")


def find_csv(root):
    direct = root / CSV_NAME
    if direct.exists():
        return direct
    hits = sorted(root.rglob(CSV_NAME))
    if not hits:
        raise SystemExit(f"没找到 {CSV_NAME}，请确认解压目录：{root}")
    return hits[0]


def build_index(root):
    idx, dup = {}, 0
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMG_EXTS:
            if p.name in idx:
                dup += 1
            idx[p.name] = p
    return idx, dup


def map_dims(row):
    """四维标签，已换算到 0-100；缺失返回 None。"""
    lc = num(row, COLS["构图"])
    co = num(row, COLS["色彩"])
    sp = num(row, COLS["造型_空间"])
    dt = num(row, COLS["造型_细节"])
    cr = num(row, COLS["创意"])
    mo = (sp + dt) / 2 if sp is not None and dt is not None else None
    raw = {"构图": lc, "色彩": co, "造型": mo, "创意": cr}
    return {k: (None if v is None else round(v * 10, 2)) for k, v in raw.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    args = ap.parse_args()
    root = Path(args.root)

    print(f"数据目录: {root}")
    if not root.exists():
        raise SystemExit("目录不存在，先把 APDDv2 解压到这里")
    rows, enc = read_csv(find_csv(root))
    print(f"CSV 编码: {enc}")
    print(f"CSV 行数: {len(rows)}")
    print(f"列名: {list(rows[0].keys())}")

    print("\n原始属性有效/缺失/范围:")
    for name, col in COLS.items():
        vals = [v for v in (num(r, col) for r in rows) if v is not None]
        if vals:
            print(f"  {name:6s} {col:24s} 有效={len(vals):5d} 缺失={len(rows)-len(vals):5d} "
                  f"范围=[{min(vals):.2f}, {max(vals):.2f}]")
        else:
            print(f"  {name:6s} {col:24s} 全部缺失")

    mapped = [map_dims(r) for r in rows]
    print("\n四维映射（已换算 0-100）:")
    for d in DIMS:
        vals = [m[d] for m in mapped if m[d] is not None]
        print(f"  {d}: 有效={len(vals):5d} 缺失={len(rows)-len(vals):5d} "
              f"范围=[{min(vals):.2f}, {max(vals):.2f}] 均值={sum(vals)/len(vals):.2f}")

    four = sum(1 for m in mapped if all(m[d] is not None for d in DIMS))
    at_least_two = sum(1 for m in mapped if sum(m[d] is not None for d in DIMS) >= 2)
    print(f"\n四维齐全: {four}   至少两维有效: {at_least_two}")

    pat = Counter(tuple(m[d] is not None for d in DIMS) for m in mapped)
    print("缺失模式（构图,色彩,造型,创意 → 数量）:")
    for k, v in pat.most_common():
        print(f"  {k} → {v}")

    cats = Counter(r["Artistic Categories"] for r in rows)
    print(f"\n类别数: {len(cats)}（前 5）")
    for k, v in cats.most_common(5):
        print(f"  {v:5d}  {k}")

    idx, dup = build_index(root)
    print(f"\n图片文件: {len(idx)}  重名文件: {dup}")
    sample = random.Random(0).sample(list(idx.values()), min(50, len(idx)))
    bad = []
    for p in sample:
        try:
            with Image.open(p) as im:
                im.verify()
        except Exception as e:
            bad.append((p.name, str(e)))
    print(f"随机打开 {len(sample)} 张校验: 损坏 {len(bad)}")
    for name, err in bad[:3]:
        print(f"  坏图: {name} ({err})")
    missing = [r["filename"] for r in rows if r["filename"] not in idx]
    print(f"CSV 里对不上的图片: {len(missing)}")
    if missing:
        for f in missing[:5]:
            print(f"  缺: {f}")
        if len(missing) > 5:
            print(f"  ...另外 {len(missing)-5} 个")

    kind = defaultdict(Counter)
    for r, m in zip(rows, mapped):
        k = r["Artistic Categories"].split("*")[0]
        kind[k]["n"] += 1
        for d in DIMS:
            kind[k][d] += m[d] is not None
    print("\n分画种的维度有效数:")
    for k, c in kind.items():
        print(f"  {k:28s} n={c['n']:4d} " + " ".join(f"{d}={c[d]}" for d in DIMS))


if __name__ == "__main__":
    main()
