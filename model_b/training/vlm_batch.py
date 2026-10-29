"""对人工点评清单跑 7B 四档打分（伪标签，不充当真值）。

读 logs/mid_school_eval/manifest.json，逐张输出 JSON 到 vlm_scores.json；可断点续跑。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration, BitsAndBytesConfig

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "logs" / "mid_school_eval"
MODEL = ROOT / "weights" / "Qwen2.5-VL-7B-Instruct"
PROMPT = (
    "你是初中美术教师。依据《义务教育艺术课程标准（2022年版）》和《中小学生艺术素质测评办法》"
    "（优秀≥90、良好75-89、合格60-74、不合格<60），评价这幅学生绘画作品。\n"
    "构图指画面安排与主次；色彩指色调与搭配；造型指形体、比例与细节；创意指想法与个人表达。\n"
    "只输出 JSON："
    '{"composition":0,"color":0,"modeling":0,"creativity":0,"level":"excellent|good|pass|fail",'
    '"reason":"一句话"}'
)


def parse(ans: str):
    m = re.search(r"\{.*\}", ans, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except Exception:
        return None
    if d.get("level") not in ("excellent", "good", "pass", "fail"):
        return None
    return d


def main():
    items = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    out_path = OUT / "vlm_scores.json"
    done = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    todo = [x for x in items if x["path"] not in done]
    print(f"todo {len(todo)}/{len(items)}", flush=True)
    if not todo:
        return

    q = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                           bnb_4bit_compute_dtype=torch.bfloat16)
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        str(MODEL), quantization_config=q, device_map={"": 0}, attn_implementation="sdpa"
    ).eval()
    proc = AutoProcessor.from_pretrained(str(MODEL), min_pixels=256 * 28 * 28,
                                         max_pixels=768 * 28 * 28)

    t_start = time.time()
    for n, it in enumerate(todo, 1):
        img = Image.open(it["path"]).convert("RGB")
        msgs = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": PROMPT}]}]
        text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inp = proc(text=[text], images=[img], return_tensors="pt").to(0)
        with torch.no_grad():
            gen = model.generate(**inp, max_new_tokens=96, do_sample=False)
        ans = proc.batch_decode(gen[:, inp["input_ids"].shape[1]:], skip_special_tokens=True)[0]
        rec = parse(ans) or {"raw": ans}
        rec.update({"path": it["path"], "name": it["name"], "group": it["group"]})
        done[it["path"]] = rec
        if n % 10 == 0:
            out_path.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{n}/{len(todo)}  {time.time()-t_start:.0f}s", flush=True)

    out_path.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
    print("done", len(done), flush=True)


if __name__ == "__main__":
    main()
