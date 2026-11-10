"""模型运行时：加载 Qwen2.5-3B + LoRA 适配器，生成并校验题卡。"""
from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

from .prompting import build_messages, load_catalog, parse_json_object, unit_index
from .validator import validate_card

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = PROJECT_ROOT / "weights" / "Qwen2.5-3B-Instruct"
DEFAULT_ADAPTER = PROJECT_ROOT / "weights" / "qgen_lora_3b"


class QgenRuntime:
    def __init__(
        self,
        model_path: str | None = None,
        adapter_path: str | None = None,
        load_4bit: bool = True,
        max_new_tokens: int = 600,
    ) -> None:
        self.model_path = Path(model_path or os.getenv("QGEN_MODEL", DEFAULT_MODEL))
        self.adapter_path = Path(adapter_path or os.getenv("QGEN_ADAPTER", DEFAULT_ADAPTER))
        self.load_4bit = load_4bit
        self.max_new_tokens = max_new_tokens
        self.catalog = load_catalog()
        self.units = unit_index(self.catalog)
        self.tokenizer = None
        self.model = None
        self._load_lock = threading.Lock()
        self._generate_lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        if self.loaded:
            return
        with self._load_lock:
            if self.loaded:
                return
            if not self.model_path.exists():
                raise FileNotFoundError(f"模型目录不存在：{self.model_path}")

            tokenizer = AutoTokenizer.from_pretrained(self.model_path, trust_remote_code=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            kwargs = dict(device_map="auto", low_cpu_mem_usage=True, trust_remote_code=True)
            if self.load_4bit:
                kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.bfloat16,
                    bnb_4bit_use_double_quant=True,
                )
            try:
                model = AutoModelForCausalLM.from_pretrained(
                    self.model_path, dtype=torch.bfloat16, **kwargs
                )
            except TypeError:
                model = AutoModelForCausalLM.from_pretrained(
                    self.model_path, torch_dtype=torch.bfloat16, **kwargs
                )

            if self.adapter_path.exists():
                from peft import PeftModel

                model = PeftModel.from_pretrained(model, self.adapter_path)
            model.eval()
            self.tokenizer, self.model = tokenizer, model

    def _normalize_request(self, request: dict) -> dict:
        unit_id = request.get("unit_id")
        unit = self.units.get(unit_id)
        if unit is None:
            raise ValueError(f"unit_id 不在目录中：{unit_id!r}")
        knowledge_point = request.get("knowledge_point")
        if knowledge_point not in unit["knowledge_points"]:
            raise ValueError(f"知识点不在单元中：{knowledge_point!r}")
        qtype = request.get("type")
        if qtype not in unit["allowed_types"]:
            raise ValueError(f"单元不支持题型：{qtype!r}")
        difficulty = int(request.get("difficulty", unit["difficulty_range"][0]))
        low, high = unit["difficulty_range"]
        if not low <= difficulty <= high:
            raise ValueError(f"难度超出单元范围：{difficulty} 不在 {low}-{high}")
        return {
            "unit_id": unit_id,
            "unit_name": unit["unit_name"],
            "grade": unit["grade"],
            "knowledge_point": knowledge_point,
            "type": qtype,
            "difficulty": difficulty,
        }

    def _generate_text(self, messages: list[dict]) -> str:
        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)
        with torch.inference_mode():
            output = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
                repetition_penalty=1.05,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        new_tokens = output[0][inputs["input_ids"].shape[1] :]
        return self.tokenizer.decode(new_tokens, skip_special_tokens=True)

    def _build_card(self, parsed: dict, request: dict) -> dict:
        qtype = request["type"]
        return {
            "id": f"gen-{uuid.uuid4().hex[:12]}",
            "subject": "art",
            "grade": request["grade"],
            "unit_id": request["unit_id"],
            "unit_name": request["unit_name"],
            "knowledge_point": request["knowledge_point"],
            "type": qtype,
            "difficulty": request["difficulty"],
            "stem": parsed.get("stem", ""),
            "options": (parsed.get("options") or []) if qtype == "single_choice" else [],
            "answer": parsed.get("answer") or {},
            "analysis": parsed.get("analysis", ""),
            "score": parsed.get("score", 10 if qtype == "short_answer" else 5),
            "scoringMode": "manual" if qtype == "short_answer" else "auto",
            "source": "self_instruct",
            "review_status": "pending",
            "created_by": "model:qwen2.5-3b-qgen",
            "notes": "",
        }

    def generate(self, request: dict) -> dict:
        self.load()
        normalized = self._normalize_request(request)
        messages = build_messages(normalized, self.catalog)
        with self._generate_lock:
            raw = self._generate_text(messages)

        parsed = parse_json_object(raw)
        record = {
            "request": normalized,
            "raw_output": raw,
            "parse_ok": parsed is not None,
            "card": None,
            "errors": [],
        }
        if parsed is None:
            record["errors"] = ["JSON 解析失败"]
            return record

        card = self._build_card(parsed, normalized)
        errors = validate_card(card, self.units, self.catalog)
        record["card"] = card
        record["errors"] = errors
        return record
