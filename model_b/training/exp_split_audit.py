"""Prove that E1 seed runs share one identical split.

For each model seed, reproduce the exact global RNG state used by
exp_train_seed.py, then call the same load_split(). Because stratified_pick()
and split() use random.Random(SEED) locally, the split must not depend on the
global seed. Writes per-seed manifests + SHA256 hashes.

Usage:
    python training/exp_split_audit.py
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
ROOT = Path(os.getenv("ART_ROOT", HERE.parents[2]))
sys.path.insert(0, str(HERE))

import train_apddv2_finetune as base  # noqa: E402

OUT = ROOT / "logs" / "split_audit"
DATA = ROOT / "data" / "05_apddv2"


def digest(items) -> str:
    h = hashlib.sha256()
    for path, labels, mask, cat in items:
        h.update(Path(path).name.encode("utf-8"))
        h.update(b"|")
        h.update(",".join(f"{v:.4f}" for v in labels).encode("ascii"))
        h.update(b"|")
        h.update("".join(str(m) for m in mask).encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"split_seed": base.SEED, "data_root": str(DATA), "seeds": {}}
    first = None
    for seed in (1, 2, 3):
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        train_s, val_s, test_s, dropped = base.load_split(DATA, 0.2, 0.15)
        entry = {"counts": {"train": len(train_s), "val": len(val_s), "test": len(test_s)},
                 "dedup_dropped": dropped}
        for name, part in (("train", train_s), ("val", val_s), ("test", test_s)):
            entry[f"{name}_sha256"] = digest(part)
            path = OUT / f"seed{seed}_{name}.txt"
            path.write_text(
                "\n".join(f"{Path(p).name}\t{','.join(f'{v:.4f}' for v in lab)}"
                          f"\t{''.join(str(m) for m in mask)}\t{cat}"
                          for p, lab, mask, cat in part) + "\n",
                encoding="utf-8",
            )
        report["seeds"][str(seed)] = entry
        if first is None:
            first = entry
        else:
            entry["identical_to_seed1"] = all(
                entry[f"{n}_sha256"] == first[f"{n}_sha256"] for n in ("train", "val", "test")
            )
        print(f"seed {seed}: {entry['counts']} "
              f"test={entry['test_sha256'][:16]} identical={entry.get('identical_to_seed1', True)}",
              flush=True)
    (OUT / "split_hashes.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("written:", OUT / "split_hashes.json", flush=True)


if __name__ == "__main__":
    main()
