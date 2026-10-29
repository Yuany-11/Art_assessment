"""方法 1 门槛：7B 视觉模型在 APDD 官方高分/低分图上打分，看能不能分开。"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import time
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ROOT = REPO.parents[1]
MODEL = ROOT / "weights" / "Qwen2.5-VL-7B-Instruct"
APDD_IMG = ROOT / "data" / "05_apddv2" / "images"
APDD_CSV = ROOT / "data" / "05_apddv2" / "APDDv2-10023.csv"
OUT = ROOT / "logs" / "vlm_gate"
SEED = 42

PROMPTS = {
    "simple": "请给这幅美术作品的整体艺术质量打分，0-100 分。只输出一个数字。",
    "rubric": "请综合构图、色彩、造型、创意四个方面，给这幅美术作品一个 0-100 的总分。只输出一个数字。",
}


def load_samples(n: int):
    rows = []
    for r in csv.DictReader(open(APDD_CSV, encoding="gbk", errors="ignore")):
        p = APDD_IMG / r["filename"]
        if not p.exists():
            continue
        try:
            t = float(r["Total aesthetic score"])
        except (TypeError, ValueError):
            continue
        rows.append({"path": p, "official": t, "category": r.get("Artistic Categories", "")})
    rng = random.Random(SEED)
    high = [r for r in rows if r["official"] >= 80]
    low = [r for r in rows if r["official"] < 50]
    rng.shuffle(high)
    rng.shuffle(low)
    k = n // 2
    return high[:k] + low[:k]


def parse_score(text: str):
    m = re.search(r"\d{1,3}(?:\.\d+)?", text)
    if not m:
        return None
    v = float(m.group(0))
    return max(0.0, min(100.0, v))


def rankdata(x):
    order = np.argsort(np.argsort(x))
    return order.astype(np.float64)


def metrics(results):
    hi = [r["vlm"] for r in results if r["official"] >= 80 and r["vlm"] is not None]
    lo = [r["vlm"] for r in results if r["official"] < 50 and r["vlm"] is not None]
    if not hi or not lo:
        return {}
    win = sum(1 for a in hi for b in lo if a > b) + 0.5 * sum(1 for a in hi for b in lo if a == b)
    xs = np.array([r["official"] for r in results if r["vlm"] is not None], dtype=np.float64)
    ys = np.array([r["vlm"] for r in results if r["vlm"] is not None], dtype=np.float64)
    pear = float(np.corrcoef(xs, ys)[0, 1]) if len(xs) > 2 else None
    spear = float(np.corrcoef(rankdata(xs), rankdata(ys))[0, 1]) if len(xs) > 2 else None
    return {
        "n_high": len(hi), "n_low": len(lo),
        "mean_high": round(float(np.mean(hi)), 2), "mean_low": round(float(np.mean(lo)), 2),
        "pairwise_high_gt_low": round(win / (len(hi) * len(lo)), 4),
        "pearson": round(pear, 4) if pear is not None else None,
        "spearman": round(spear, 4) if spear is not None else None,
        "parse_fail": sum(1 for r in results if r["vlm"] is None),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--prompt", choices=list(PROMPTS), default="simple")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    out_dir = OUT / f"gate_{args.prompt}{args.tag}"
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl = out_dir / "results.jsonl"
    done = {}
    if jsonl.exists():
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                done[Path(r["path"]).name] = r
            except Exception:
                pass

    from qwen_vl_utils import process_vision_info
    try:
        from transformers import Qwen2_5_VLForConditionalGeneration as Cls
    except ImportError:
        from transformers import AutoModelForVision2Seq as Cls
    from transformers import AutoProcessor

    print("loading model...", flush=True)
    model = Cls.from_pretrained(str(MODEL), torch_dtype=torch.bfloat16, device_map="auto")
    processor = AutoProcessor.from_pretrained(str(MODEL))
    print("model ready", model.device, flush=True)

    samples = load_samples(args.n)
    results = []
    with jsonl.open("a", encoding="utf-8") as f:
        for i, s in enumerate(samples, 1):
            name = s["path"].name
            if name in done:
                results.append(done[name])
                continue
            messages = [{"role": "user", "content": [
                {"type": "image", "image": str(s["path"]),
                 "min_pixels": 256 * 28 * 28, "max_pixels": 768 * 28 * 28},
                {"type": "text", "text": PROMPTS[args.prompt]},
            ]}]
            text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            image_inputs, video_inputs = process_vision_info(messages)
            inputs = processor(text=[text], images=image_inputs, videos=video_inputs,
                               padding=True, return_tensors="pt").to(model.device)
            t0 = time.time()
            with torch.no_grad():
                gen = model.generate(**inputs, max_new_tokens=8, do_sample=False)
            raw = processor.batch_decode(gen[:, inputs["input_ids"].shape[1]:],
                                         skip_special_tokens=True)[0]
            score = parse_score(raw)
            rec = {"path": str(s["path"]), "official": s["official"], "vlm": score,
                   "raw": raw.strip()[:50], "sec": round(time.time() - t0, 1),
                   "category": s["category"]}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            results.append(rec)
            print(f"[{i}/{len(samples)}] official={s['official']:.0f} vlm={score} "
                  f"{rec['sec']}s {raw.strip()[:20]!r}", flush=True)

    m = metrics(results)
    (out_dir / "metrics.json").write_text(
        json.dumps({"prompt": args.prompt, "n": args.n, **m}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(json.dumps(m, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
