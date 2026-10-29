"""7B 初中美术档位打分（严格格式 + 多次采样 + 自一致性诊断）。

与 vlm_batch.py 的区别：
  - 先判四档（优秀/良好/合格/不合格），再在档内给 0-100；分数必须落在档位区间内
  - 严格校验：JSON 可解析、四维齐全、数值在 0-100、档位与分数一致
  - 不合格自动重试（最多 3 次），并记录最终是否合格
  - 多次采样（temperature），输出中位数 + 采样间分歧，用于估计重测一致性
  - 两种模式可对比：
      band : 四档判据 + 档内给分（新）
      abs  : 直接 0-100（复现旧行为，作为对照）

产出伪标签，不充当教师真值。不训练、不改任何权重。

用法：
    python -I training/vlm_grade.py --folder <dir> --out <dir> --mode band --samples 3
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from pathlib import Path

import torch
from PIL import Image, ImageOps
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration, BitsAndBytesConfig

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MODEL = ROOT / "weights" / "Qwen2.5-VL-7B-Instruct"

DIMS = ("composition", "color", "modeling", "creativity")
BANDS = ("excellent", "good", "pass", "fail")
BAND_RANGE = {"excellent": (90, 100), "good": (75, 89), "pass": (60, 74), "fail": (0, 59)}

COMMON = (
    "你是中国初中的美术教师，正在给学生课堂绘画作业评级。\n"
    "评价基准是《义务教育艺术课程标准（2022年版）》7-9年级，参照对象是"
    "“同年级大多数学生的正常水平”，不是专业画家、不是美术高考。\n"
    "先判断：这幅画看起来像初中生作业吗？如果有人物、教室、展板、多幅作品合影等"
    "“不是单件绘画作品”的情况，在 not_artwork 里填 true 并只输出 {\"not_artwork\":true}。\n"
)

RUBRIC = """四个维度：
- 构图：主体是否明确、主次与视觉中心、疏密层次、是否处理背景
- 色彩：是否有色调倾向、冷暖明暗关系、颜色是否服务于主题
- 造型：形体比例、结构转折与体积感、细节取舍
- 创意：是否有个人视角或独特组合，还是常见套路的常规画法

各维度四档判据（严格按此判断，不要凭整体印象）：
[构图]
  优秀：主体明确、主次分明、有明确视觉中心；疏密有节奏；有意识处理前景-中景-背景
  良好：主体清楚、画面基本均衡；有主次意识但略生硬；局部空或挤但整体可读
  合格：能看出画的是什么、元素在画面内；但平均分布、无主次无层次
  不合格：主体不明或严重偏位裁切；元素堆叠散乱
[色彩]
  优秀：有明确色调倾向；冷暖明暗服务于主题；用色有控制
  良好：较协调、能看出主色调；个别处颜色冲突或用色过多
  合格：涂色基本完整不外溢；但以平涂原色为主，无明暗调和
  不合格：大面积未完成、严重出界、颜色之间无任何关系
[造型]
  优秀：形体比例基本准确；有结构转折与体积感；细节有取舍
  良好：主要形体可辨认；比例有偏差但不影响识别；细节少
  合格：能认出对象类别，但形体概念化（符号化的人/树/房子），无体积
  不合格：形体难以辨认或比例严重失调
[创意]
  优秀：有个人视角或独特组合，不是常见套路；有叙事或情绪表达
  良好：常见题材里有自己的小改动（加细节或换视角）
  合格：常见题材的常规画法，模仿痕迹明显
  不合格：照抄范例或简笔画符号堆砌，无个人处理

档位对应分数区间：优秀 90-100，良好 75-89，合格 60-74，不合格 0-59。
每个维度的 score 必须落在它自己 band 的区间内。
"""

PROMPT_BAND = COMMON + RUBRIC + """
只输出一个 JSON 对象，不要任何其他文字、不要 markdown 代码块，字段结构如下（尖括号是占位符，要换成你自己判断的结果）：
{"not_artwork":<true|false>,
 "composition":{"band":"<excellent|good|pass|fail>","score":<0-100的整数>},
 "color":{"band":"<excellent|good|pass|fail>","score":<0-100的整数>},
 "modeling":{"band":"<excellent|good|pass|fail>","score":<0-100的整数>},
 "creativity":{"band":"<excellent|good|pass|fail>","score":<0-100的整数>},
 "reason":"一句话，必须是画面里实际看到的具体内容"}
严禁在四张不同的画上输出相同的分数；如果你发现四维分数是不看画面就能写出的固定值，说明判断无效。
reason 里必须提到画面中真实存在的一个具体对象或具体颜色（例如“画的是操场上的篮球架”），不能写套话。"""

PROMPT_ABS = COMMON + """四个维度各给 0 到 100 的整数分（例如 63、78、91），不要只写 1、2、3、4。
只输出一个 JSON 对象，不要任何其他文字、不要 markdown 代码块：
{"not_artwork":false,"composition":65,"color":70,"modeling":60,"creativity":75,
 "level":"pass","reason":"一句话"}
level 按四维均分：优秀>=90，良好75-89，合格60-74，不合格<60。"""

RETRY_SUFFIX = (
    "\n\n上一次输出不合格。这次必须严格只输出上面那个 JSON 对象，"
    "所有字段齐全，数值是 0-100 的整数。"
)


def extract_json(ans: str):
    ans = ans.strip()
    ans = re.sub(r"^```(?:json)?|```$", "", ans, flags=re.M).strip()
    m = re.search(r"\{.*\}", ans, re.S)
    if not m:
        return None, "no_json"
    try:
        return json.loads(m.group(0)), None
    except Exception as exc:  # noqa: BLE001
        return None, f"bad_json:{str(exc)[:60]}"


def _num(x):
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str) and re.fullmatch(r"-?\d+(\.\d+)?", x.strip()):
        return float(x.strip())
    return None


def validate_band(d):
    """返回 (clean_record, problems)."""
    problems = []
    if not isinstance(d, dict):
        return None, ["not_object"]
    if d.get("not_artwork") is True:
        return {"not_artwork": True}, []

    out = {"not_artwork": False, "dims": {}}
    for dim in DIMS:
        v = d.get(dim)
        if not isinstance(v, dict):
            problems.append(f"{dim}:missing")
            continue
        band = str(v.get("band", "")).strip().lower()
        score = _num(v.get("score"))
        if band not in BANDS:
            problems.append(f"{dim}:bad_band={v.get('band')!r}")
            continue
        if score is None or not (0 <= score <= 100):
            problems.append(f"{dim}:bad_score={v.get('score')!r}")
            continue
        lo, hi = BAND_RANGE[band]
        if not (lo <= score <= hi):
            problems.append(f"{dim}:score_band_mismatch={score}>{band}")
        out["dims"][dim] = {"band": band, "score": int(round(score))}

    if len(out["dims"]) != 4:
        return None, problems or ["dims_incomplete"]
    out["reason"] = str(d.get("reason", ""))[:200]
    return out, problems


def validate_abs(d):
    problems = []
    if not isinstance(d, dict):
        return None, ["not_object"]
    if d.get("not_artwork") is True:
        return {"not_artwork": True}, []
    scores = {}
    for dim in DIMS:
        s = _num(d.get(dim))
        if s is None or not (0 <= s <= 100):
            problems.append(f"{dim}:bad_score={d.get(dim)!r}")
            continue
        scores[dim] = int(round(s))
    if len(scores) != 4:
        return None, problems or ["dims_incomplete"]
    mean = sum(scores.values()) / 4
    lvl = "excellent" if mean >= 90 else "good" if mean >= 75 else "pass" if mean >= 60 else "fail"
    stated = str(d.get("level", "")).strip().lower()
    if stated != lvl:
        problems.append(f"level_mismatch:stated={stated},computed={lvl}")
    return {"not_artwork": False, "scores": scores, "level": lvl,
            "reason": str(d.get("reason", ""))[:200]}, problems


def band_of(mean: float) -> str:
    return "excellent" if mean >= 90 else "good" if mean >= 75 else "pass" if mean >= 60 else "fail"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=("band", "abs"), default="band")
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--max-new", type=int, default=160)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    folder = Path(args.folder)
    files = sorted(p for p in folder.rglob("*") if p.suffix.lower() in exts)
    if args.limit:
        files = files[: args.limit]
    if not files:
        raise SystemExit(f"no images under {folder}")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    prompt = PROMPT_BAND if args.mode == "band" else PROMPT_ABS
    validate = validate_band if args.mode == "band" else validate_abs

    t0 = time.time()
    q = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                           bnb_4bit_compute_dtype=torch.bfloat16)
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        str(MODEL), quantization_config=q, device_map={"": 0}, attn_implementation="sdpa"
    ).eval()
    proc = AutoProcessor.from_pretrained(str(MODEL), min_pixels=256 * 28 * 28,
                                         max_pixels=768 * 28 * 28)
    print(f"load {time.time()-t0:.1f}s vram {torch.cuda.max_memory_allocated()/2**30:.2f}G", flush=True)

    results = {}
    t_start = time.time()
    for n, p in enumerate(files, 1):
        img = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
        rec = {"file": str(p.relative_to(folder)), "samples": [], "invalid": 0}
        for s in range(args.samples):
            got = None
            problems = []
            raw_ans = ""
            for attempt in range(args.retries):
                text = prompt + (RETRY_SUFFIX if attempt else "")
                msgs = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": text}]}]
                chat = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
                inp = proc(text=[chat], images=[img], return_tensors="pt").to(0)
                with torch.no_grad():
                    gen = model.generate(
                        **inp, max_new_tokens=args.max_new,
                        do_sample=args.temperature > 0,
                        temperature=max(args.temperature, 1e-5),
                        top_p=0.9,
                    )
                raw_ans = proc.batch_decode(gen[:, inp["input_ids"].shape[1]:],
                                            skip_special_tokens=True)[0]
                d, err = extract_json(raw_ans)
                if d is None:
                    problems = [err]
                    continue
                got, problems = validate(d)
                if got is not None:
                    break
            if got is None:
                rec["invalid"] += 1
                rec["samples"].append({"ok": False, "problems": problems,
                                       "raw": raw_ans[:400]})
            else:
                rec["samples"].append({"ok": True, "problems": problems, **got})
        results[rec["file"]] = rec
        if n % 5 == 0 or n == len(files):
            print(f"{n}/{len(files)}  {time.time()-t_start:.0f}s", flush=True)

    # ---------------- aggregate ----------------
    def dims_of(rec):
        out = []
        for s in rec["samples"]:
            if not s.get("ok") or s.get("not_artwork"):
                continue
            if args.mode == "band":
                out.append({d: s["dims"][d]["score"] for d in DIMS})
            else:
                out.append(dict(s["scores"]))
        return out

    per_image = {}
    all_std = []
    retest = []
    band_vote_agree = []
    for f, rec in results.items():
        valid = dims_of(rec)
        n_ok = len(valid)
        entry = {"n_samples": len(rec["samples"]), "n_valid": n_ok,
                 "invalid": rec["invalid"],
                 "not_artwork": any(s.get("not_artwork") for s in rec["samples"] if s.get("ok"))}
        if n_ok:
            entry["median"] = {d: statistics.median([v[d] for v in valid]) for d in DIMS}
            entry["mean_total"] = round(sum(entry["median"].values()) / 4, 2)
            entry["band"] = band_of(entry["mean_total"])
            entry["dim_std"] = {d: round(statistics.pstdev([v[d] for v in valid]), 2)
                                if n_ok > 1 else 0.0 for d in DIMS}
            all_std.append(max(entry["dim_std"].values()))
            if n_ok >= 2:
                half = n_ok // 2
                a = {d: statistics.median([v[d] for v in valid[:half]]) for d in DIMS}
                b = {d: statistics.median([v[d] for v in valid[half:]]) for d in DIMS}
                retest.append(sum(abs(a[d] - b[d]) for d in DIMS) / 4)
                ba = band_of(sum(a.values()) / 4)
                bb = band_of(sum(b.values()) / 4)
                band_vote_agree.append(ba == bb)
        if args.mode == "band" and n_ok:
            for d in DIMS:
                vbs = [s["dims"][d]["band"] for s in rec["samples"]
                       if s.get("ok") and not s.get("not_artwork")]
                if len(vbs) > 1:
                    entry.setdefault("band_agree", {})[d] = round(
                        max(vbs.count(b) for b in set(vbs)) / len(vbs), 3)
        per_image[f] = entry

    n_slots = sum(len(r["samples"]) for r in results.values())
    n_bad = sum(r["invalid"] for r in results.values())
    summary = {
        "mode": args.mode,
        "samples_per_image": args.samples,
        "temperature": args.temperature,
        "n_images": len(results),
        "valid_rate": round(1 - n_bad / max(n_slots, 1), 4),
        "n_invalid_samples": n_bad,
        "not_artwork_flagged": sum(1 for e in per_image.values() if e["not_artwork"]),
        "self_consistency": {
            "mean_max_dim_std": round(statistics.mean(all_std), 2) if all_std else None,
            "mean_retest_mae": round(statistics.mean(retest), 2) if retest else None,
            "retest_band_agreement": round(sum(band_vote_agree) / len(band_vote_agree), 3)
            if band_vote_agree else None,
        },
        "band_distribution": {b: sum(1 for e in per_image.values() if e.get("band") == b)
                              for b in BANDS},
        "elapsed_s": round(time.time() - t_start, 1),
    }

    (out_dir / "results.json").write_text(
        json.dumps({"summary": summary, "per_image": per_image,
                    "raw": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
