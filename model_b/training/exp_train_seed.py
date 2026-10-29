"""E1: train one ResNet18 seed with isolated output dirs.

Keeps the baseline split seed fixed at 42; only model/DataLoader RNG changes.
Writes: weights/<run>/{best.pt,last.pt,说明.txt,config.json}
        logs/<run>/{train_log.txt,history.json,curves.png}

Usage:
    python training/exp_train_seed.py --seed 1 --yes
"""
from __future__ import annotations

import argparse
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--run", default=None)
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--img", type=int, default=224)
    ap.add_argument("--backbone", choices=["resnet18", "resnet34", "resnet50"],
                    default="resnet18")
    ap.add_argument("--version", default="")
    ap.add_argument("--data", default=None)
    ap.add_argument("--dim-weights", default="1,1,1,1.5")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    run = args.run or f"exp_seed{args.seed}"
    base.RUNS = ROOT / "weights" / run
    base.LOGS = ROOT / "logs" / run
    base.VERSION = args.version or (
        f"art-cnn-apddv2-v3.0-seed{args.seed}" if args.img == 224
        else f"art-cnn-apddv2-v4.0-{args.backbone}-{args.img}-seed{args.seed}")

    # split seed must stay 42; only model/DataLoader randomness varies by seed.
    assert base.SEED == 42
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True

    sys.argv = [
        sys.argv[0],
        "--epochs", str(args.epochs),
        "--batch", str(args.batch),
        "--img", str(args.img),
        "--backbone", args.backbone,
        "--dim-weights", args.dim_weights,
    ]
    if args.data:
        sys.argv += ["--root", args.data]
    if args.yes:
        sys.argv.append("--yes")

    base.main()

    cfg = {
        "run": run,
        "model_seed": args.seed,
        "split_seed": base.SEED,
        "epochs": args.epochs,
        "batch": args.batch,
        "img": args.img,
        "backbone": args.backbone,
        "dim_weights": args.dim_weights,
        "version": base.VERSION,
    }
    base.RUNS.mkdir(parents=True, exist_ok=True)
    (base.RUNS / "config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("config written:", base.RUNS / "config.json", flush=True)


if __name__ == "__main__":
    main()
