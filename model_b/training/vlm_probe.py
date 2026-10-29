"""7B 视觉模型单张/小批推理测速（4bit，8G 显存）。

只测可行性：加载时间、每张生成时间、显存峰值。不产出任何"真值"。
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration, BitsAndBytesConfig

MODEL = Path(r"E:/Lab_Files/Project/Art_assessment/weights/Qwen2.5-VL-7B-Instruct")
PROMPT = (
    "你是初中美术教师。依据《义务教育艺术课程标准（2022年版）》和《中小学生艺术素质测评办法》，"
    "以“大多数初中生的正常水平”为参照给这幅学生画打分。\n"
    "四个分数必须是 0 到 100 的整数（例如 63、78、91），绝对不能只写 1、2、3、4；"
    "等级按总分：优秀≥90，良好75-89，合格60-74，不合格<60。\n"
    "只输出 JSON："
    '{"composition":65,"color":70,"modeling":60,"creativity":75,"level":"pass","reason":"一句话"}'
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", nargs="+", required=True)
    ap.add_argument("--max-new", type=int, default=96)
    args = ap.parse_args()

    t0 = time.time()
    q = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        str(MODEL), quantization_config=q, device_map={"": 0}, attn_implementation="sdpa"
    ).eval()
    proc = AutoProcessor.from_pretrained(str(MODEL), min_pixels=256 * 28 * 28, max_pixels=768 * 28 * 28)
    print(f"load {time.time()-t0:.1f}s vram {torch.cuda.max_memory_allocated()/2**30:.2f}G", flush=True)

    for p in args.images:
        img = Image.open(p).convert("RGB")
        msgs = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": PROMPT}]}]
        text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inp = proc(text=[text], images=[img], return_tensors="pt").to(0)
        t = time.time()
        with torch.no_grad():
            out = model.generate(**inp, max_new_tokens=args.max_new, do_sample=False)
        dt = time.time() - t
        gen = out[:, inp["input_ids"].shape[1]:]
        ans = proc.batch_decode(gen, skip_special_tokens=True)[0]
        print(f"{Path(p).name} {dt:.1f}s {ans}", flush=True)


if __name__ == "__main__":
    main()
