"""生成成对比较样本：同题目(stimuli)+同年龄的儿童画，避免跨题、跨年龄不可比。"""
from __future__ import annotations

import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ROOT = REPO.parents[1]
PENCILS = ROOT / "_downloads" / "Pencils_to_Pixels"
CSV = PENCILS / "csvs" / "all_product.csv"
OUT = ROOT / "logs" / "pairwise_v1"
SEED = 42
N_PAIRS = 300
N_BLOCKS = 3
MAX_APPEAR = 3


def main():
    rng = random.Random(SEED)
    rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
    items = []
    for r in rows:
        if r["creator"] != "children" or r.get("category1") == "blank":
            continue
        p = (PENCILS / "csvs" / r["filepath"]).resolve()
        if not p.exists():
            continue
        items.append({
            "uid": f"{r['stimuli']}_{r['age']}_{r['pid']}",
            "path": str(p),
            "stimuli": r["stimuli"],
            "age": r["age"],
        })

    groups = defaultdict(list)
    for it in items:
        groups[(it["stimuli"], it["age"])].append(it)
    keys = [k for k, v in groups.items() if len(v) >= 2]

    pairs, seen, counts = [], set(), Counter()
    attempts = 0
    while len(pairs) < N_PAIRS and attempts < N_PAIRS * 500:
        attempts += 1
        g = groups[rng.choice(keys)]
        a, b = rng.sample(g, 2)
        key = tuple(sorted((a["uid"], b["uid"])))
        if key in seen:
            continue
        if counts[a["uid"]] >= MAX_APPEAR or counts[b["uid"]] >= MAX_APPEAR:
            continue
        seen.add(key)
        counts[a["uid"]] += 1
        counts[b["uid"]] += 1
        pairs.append({"a": a, "b": b, "group": f"{a['stimuli']}/{a['age']}"})

    if len(pairs) < N_PAIRS:
        raise SystemExit(f"只生成了 {len(pairs)} 对，不够 {N_PAIRS}")

    rng.shuffle(pairs)
    out = []
    for i, p in enumerate(pairs):
        out.append({
            "pair_id": f"p{i + 1:04d}",
            "block": i % N_BLOCKS + 1,
            "group": p["group"],
            "a": {"uid": p["a"]["uid"], "path": p["a"]["path"]},
            "b": {"uid": p["b"]["uid"], "path": p["b"]["path"]},
        })

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pairs.json").write_text(
        json.dumps({"seed": SEED, "n_pairs": len(out), "n_blocks": N_BLOCKS, "pairs": out},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(json.dumps({
        "images": len(items),
        "pairs": len(out),
        "blocks": Counter(p["block"] for p in out),
        "max_appear": max(counts.values()),
        "groups": len(keys),
    }, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
