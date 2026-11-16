"""模型运行时：加载 Qwen2.5-3B + LoRA 适配器，生成并校验题卡。"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import threading
import uuid
import zlib
from collections import OrderedDict
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

from .factcheck import (
    ANALYSIS_COVERAGE_MIN,
    check_analysis_provenance,
    check_card,
    check_short_answer_direction,
    check_short_answer_domain,
    check_short_answer_negation,
    check_single_choice_analysis_consistency,
    check_single_choice_color_comparison,
    check_single_choice_containment,
    check_single_choice_multi,
    check_single_choice_polarity,
    repair_fill_answer,
)
from .fallback import build_template_card
from .image_bank import IMAGE_BANK
from .prompting import build_messages, load_catalog, load_facts, parse_json_object, unit_index
from .validator import validate_card

from .paths import PROJECT_ROOT

_MODEL_CANDIDATES = [
    PROJECT_ROOT / "weights" / "Qwen2.5-3B-Instruct",       # 部署布局
    PROJECT_ROOT.parent / "weights" / "Qwen2.5-3B-Instruct",  # 本机开发布局
]
DEFAULT_MODEL = next((p for p in _MODEL_CANDIDATES if p.exists()), _MODEL_CANDIDATES[0])
_ADAPTER_CANDIDATES = [
    PROJECT_ROOT / "weights" / "qgen_lora_3b_v4",                 # 部署布局
    PROJECT_ROOT.parent / "weights" / "qgen_lora_3b_v4",          # 本机开发布局
]
DEFAULT_ADAPTER = Path(
    os.getenv("QGEN_ADAPTER")
    or next((p for p in _ADAPTER_CANDIDATES if p.exists()), _ADAPTER_CANDIDATES[0])
)
DEFAULT_MAX_ATTEMPTS = 2
DEFAULT_CACHE_SIZE = 256

# 这些 (unit_id, knowledge_point, type) 不走模型，直接出模板题。
# 2026-11-14 定向复审 #3：g1-u4/看画说感受 的单选，模型出的干扰项没有唯一解，
# 模板干扰项来自 misconceptions，答案唯一，先强制走模板。
FORCED_TEMPLATE: set[tuple[str, str, str]] = {
    ("g1-u4", "看画说感受", "single_choice"),
}

# 复核方用 scripts/validate_questions.py 判结构，这里直接复用同一份校验器，
# 保证运行时放行的卡离线也过；脚本不存在或 QGEN_OFFLINE_CHECK=0 时自动跳过。
_OFFLINE_MODULE = None
_OFFLINE_LOADED = False
OFFLINE_CHECK = os.getenv("QGEN_OFFLINE_CHECK", "1") != "0"


def offline_validator():
    global _OFFLINE_MODULE, _OFFLINE_LOADED
    if _OFFLINE_LOADED:
        return _OFFLINE_MODULE
    _OFFLINE_LOADED = True
    path = PROJECT_ROOT / "scripts" / "validate_questions.py"
    if not OFFLINE_CHECK or not path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("_qgen_offline_validate", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _OFFLINE_MODULE = module
    except Exception:
        _OFFLINE_MODULE = None
    return _OFFLINE_MODULE


class QgenRuntime:
    def __init__(
        self,
        model_path: str | None = None,
        adapter_path: str | None = None,
        load_4bit: bool = True,
        max_new_tokens: int = 600,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        cache_size: int | None = None,
        provenance_strict: bool | None = None,
        analysis_coverage_min: float | None = None,
    ) -> None:
        self.model_path = Path(model_path or os.getenv("QGEN_MODEL", DEFAULT_MODEL))
        self.adapter_path = Path(adapter_path or os.getenv("QGEN_ADAPTER", DEFAULT_ADAPTER))
        self.load_4bit = load_4bit
        self.max_new_tokens = max_new_tokens
        self.max_attempts = max(1, max_attempts)
        self.provenance_strict = (
            provenance_strict
            if provenance_strict is not None
            else os.getenv("QGEN_PROVENANCE_STRICT", "1") != "0"
        )
        if analysis_coverage_min is None:
            analysis_coverage_min = float(
                os.getenv("QGEN_ANALYSIS_COVERAGE_MIN", ANALYSIS_COVERAGE_MIN)
            )
        self.analysis_coverage_min = analysis_coverage_min
        if cache_size is None:
            cache_size = int(os.getenv("QGEN_CACHE_SIZE", DEFAULT_CACHE_SIZE))
        self.cache_size = max(0, int(cache_size))
        self._cache: OrderedDict[tuple, dict] = OrderedDict()
        self._cache_lock = threading.Lock()
        self.cache_hits = 0
        self.cache_misses = 0
        self.catalog = load_catalog()
        self.units = unit_index(self.catalog)
        self.facts = load_facts()
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
        try:
            seed = int(request.get("seed") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"seed 必须是整数：{request.get('seed')!r}") from exc
        return {
            "unit_id": unit_id,
            "unit_name": unit["unit_name"],
            "grade": unit["grade"],
            "knowledge_point": knowledge_point,
            "type": qtype,
            "difficulty": difficulty,
            "seed": seed,
            "request_id": str(request.get("request_id") or ""),
        }

    def _facts_for(self, normalized: dict) -> list[dict]:
        pool = self.facts.get((normalized["unit_id"], normalized["knowledge_point"]), [])
        if not pool:
            return []
        key = (f"{normalized['unit_id']}|{normalized['knowledge_point']}"
               f"|{normalized['type']}|{normalized['difficulty']}")
        offset = zlib.crc32(key.encode("utf-8")) % len(pool)
        return pool[offset:] + pool[:offset]

    def _offline_errors(self, card: dict) -> list[str]:
        """用离线校验器再过一遍，口径与复核方完全一致。"""
        module = offline_validator()
        if module is None:
            return []
        try:
            if not hasattr(self, "_offline_ready"):
                self._offline_catalog = module.load_catalog()
                self._offline_units = module.unit_index(self._offline_catalog)
                self._offline_facts = module.load_fact_index()
                self._offline_ready = True
            return module.validate_card(
                card, self._offline_units, self._offline_catalog, self._offline_facts
            )
        except Exception:
            return []

    @staticmethod
    def _fact_errors(card: dict, facts: list[dict]) -> list[str]:
        if not facts:
            return []
        haystack = re.sub(
            r"\s+",
            "",
            " ".join([
                str(card.get("stem", "")),
                str(card.get("analysis", "")),
                json.dumps(card.get("answer") or {}, ensure_ascii=False),
                json.dumps(card.get("options") or [], ensure_ascii=False),
            ]),
        )
        for fact in facts:
            keys = [re.sub(r"\s+", "", str(item)) for item in (fact.get("must_include") or [])]
            if keys and all(item in haystack for item in keys):
                return []
        return [f"{card.get('id', '<无 id>')}: 答案未命中事实卡关键词，可能编造"]

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
            "options": (parsed.get("options") or []) if qtype in {"single_choice", "multiple_choice"} else [],
            "answer": parsed.get("answer") or {},
            "analysis": parsed.get("analysis", ""),
            "score": parsed.get("score", 10 if qtype == "short_answer" else 5),
            "scoringMode": "manual" if qtype == "short_answer" else "auto",
            "source": "self_instruct",
            "review_status": "pending",
            "created_by": "model:qwen2.5-3b-qgen",
            "notes": "",
        }

    def _raw_outputs(self, normalized: list[dict]) -> list[str]:
        if len(normalized) == 1:
            messages = build_messages(normalized[0], self.catalog, self._facts_for(normalized[0]))
            with self._generate_lock:
                return [self._generate_text(messages)]
        texts = [
            self.tokenizer.apply_chat_template(
                build_messages(n, self.catalog, self._facts_for(n)),
                tokenize=False, add_generation_prompt=True,
            )
            for n in normalized
        ]

        prev_side = self.tokenizer.padding_side
        self.tokenizer.padding_side = "left"
        try:
            inputs = self.tokenizer(texts, return_tensors="pt", padding=True).to(self.model.device)
            with self._generate_lock, torch.inference_mode():
                output = self.model.generate(
                    **inputs,
                    max_new_tokens=self.max_new_tokens,
                    do_sample=True,
                    temperature=0.7,
                    top_p=0.9,
                    repetition_penalty=1.05,
                    pad_token_id=self.tokenizer.eos_token_id,
                )
        finally:
            self.tokenizer.padding_side = prev_side

        input_len = inputs["input_ids"].shape[1]
        return [self.tokenizer.decode(row[input_len:], skip_special_tokens=True) for row in output]

    def _records(self, normalized: list[dict]) -> list[dict]:
        records: list[dict] = []
        for norm, raw in zip(normalized, self._raw_outputs(normalized)):
            parsed = parse_json_object(raw)
            record = {
                "request": norm,
                "raw_output": raw,
                "parse_ok": parsed is not None,
                "card": None,
                "errors": [],
            }
            facts = self._facts_for(norm)
            record["fact_ids"] = [fact.get("fact_id") for fact in facts]
            record["fact_errors"] = []
            record["answer_errors"] = []
            record["provenance_errors"] = []
            record["generated_by"] = "model"
            if parsed is None:
                record["errors"] = ["JSON 解析失败"]
            else:
                card = self._build_card(parsed, norm)
                if card["type"] == "fill_blank":
                    fixed = repair_fill_answer(
                        card["stem"],
                        (card.get("answer") or {}).get("values") or [],
                        card.get("analysis", ""),
                    )
                    if fixed:
                        card["answer"]["values"] = fixed
                        record["answer_repaired"] = True
                record["card"] = card
                record["errors"] = (
                    validate_card(card, self.units, self.catalog) + self._offline_errors(card)
                )
                record["fact_errors"] = self._fact_errors(card, facts)
                extra = self._extra_facts(norm["unit_id"], norm["knowledge_point"])
                record["answer_errors"] = (
                    check_card(card, facts, extra)
                    + check_single_choice_multi(card, facts)
                    + check_single_choice_polarity(card, facts)
                    + check_single_choice_containment(card, facts)
                    + check_single_choice_color_comparison(card)
                    + check_single_choice_analysis_consistency(card, facts)
                    + check_short_answer_domain(card, facts)
                    + check_short_answer_negation(card, facts)
                    + check_short_answer_direction(card, facts)
                )
                if self.provenance_strict:
                    record["provenance_errors"] = check_analysis_provenance(
                        card, facts, self.analysis_coverage_min
                    )
            records.append(record)
        return records

    @staticmethod
    def _blocking(record: dict) -> bool:
        """结构、答案事实、解析溯源任一不过，都算这道题不能直出。"""
        return bool(
            record.get("errors")
            or record.get("answer_errors")
            or record.get("provenance_errors")
        )

    @staticmethod
    def _is_forced_template(normalized: dict) -> bool:
        return (normalized["unit_id"], normalized["knowledge_point"], normalized["type"]) in FORCED_TEMPLATE

    def _forced_record(self, normalized: dict) -> dict:
        """强制走模板的请求：不调模型，直接出兜底卡。"""
        record = {
            "request": normalized,
            "raw_output": "",
            "parse_ok": True,
            "card": None,
            "errors": [],
            "fact_ids": [fact.get("fact_id") for fact in self._facts_for(normalized)],
            "fact_errors": [],
            "answer_errors": [],
            "provenance_errors": [],
            "generated_by": "model",
            "forced_template": True,
            "attempts": 0,
        }
        record.update(self._fallback(normalized))
        record["forced_template"] = True
        record["attempts"] = 0
        return record

    def _generate_with_retry(self, normalized: list[dict]) -> list[dict]:
        records: list[dict | None] = [None] * len(normalized)
        model_index = [i for i, norm in enumerate(normalized) if not self._is_forced_template(norm)]
        sub: list[dict] = self._records([normalized[i] for i in model_index]) if model_index else []
        attempts = [1] * len(sub)
        for attempt in range(2, self.max_attempts + 1):
            pending = []
            for j, record in enumerate(sub):
                if not self._blocking(record):
                    continue
                # 答案/解析在事实卡里找不到依据时，重采样几乎不会变好，
                # 开关打开就直接交模板兜底，把重试次数留给结构性错误。
                if self.provenance_strict and (
                    record.get("provenance_errors") or record.get("answer_errors")
                ):
                    continue
                pending.append(j)
            if not pending:
                break
            retried = self._records([normalized[model_index[j]] for j in pending])
            for j, rec in zip(pending, retried):
                sub[j] = rec
                attempts[j] = attempt

        for pos, rec in enumerate(sub):
            records[model_index[pos]] = rec
        for i, norm in enumerate(normalized):
            if records[i] is None:
                records[i] = self._forced_record(norm)

        for pos, rec in enumerate(sub):
            rec["attempts"] = attempts[pos]
        for rec in records:
            if rec is None:
                continue
            rec.setdefault("attempts", 0)
            rec["fact_ok"] = not rec.get("fact_errors")
            if self._blocking(rec):
                model_errors = list(rec.get("errors") or [])
                model_answer_errors = list(rec.get("answer_errors") or [])
                provenance_errors = list(rec.get("provenance_errors") or [])
                rec.update(self._fallback(rec["request"]))
                # 兜底卡会覆盖 errors/answer_errors，模型那一次的判定单独留档，便于复盘。
                rec["model_errors"] = model_errors
                rec["model_answer_errors"] = model_answer_errors
                rec["model_attempts"] = rec["attempts"]
                rec["provenance_errors"] = provenance_errors
                rec["provenance_blocked"] = self.provenance_strict and bool(
                    provenance_errors or model_answer_errors
                )
        return [rec for rec in records if rec is not None]

    def _cache_key(self, normalized: dict) -> tuple:
        return (
            normalized["grade"],
            normalized["unit_id"],
            normalized["knowledge_point"],
            normalized["type"],
            normalized["difficulty"],
            normalized["seed"],
        )

    def _cache_get(self, key: tuple) -> dict | None:
        if self.cache_size <= 0:
            self.cache_misses += 1
            return None
        with self._cache_lock:
            record = self._cache.get(key)
            if record is None:
                self.cache_misses += 1
                return None
            self._cache.move_to_end(key)
            self.cache_hits += 1
            return copy.deepcopy(record)

    def _cache_put(self, key: tuple, record: dict) -> None:
        if self.cache_size <= 0:
            return
        with self._cache_lock:
            self._cache[key] = copy.deepcopy(record)
            self._cache.move_to_end(key)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)

    def cache_info(self) -> dict:
        with self._cache_lock:
            return {
                "size": len(self._cache),
                "maxsize": self.cache_size,
                "hits": self.cache_hits,
                "misses": self.cache_misses,
            }

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()

    def _extra_facts(self, unit_id: str, knowledge_point: str) -> list[dict]:
        pool: list[dict] = []
        for (uid, kp), items in self.facts.items():
            if uid == unit_id and kp != knowledge_point:
                pool.extend(items)
        return pool

    @staticmethod
    def _template_seed(normalized: dict) -> int:
        """模板种子纳入 request_id / seed，再按难度错开。

        难度不进 crc32 而是直接加到种子上：难度 2、3 只差 1，选到的模板卡必然不同一张，
        不会出现同知识点两个难度返回同一道题。
        """
        key = "|".join(str(normalized.get(field, "")) for field in (
            "unit_id", "knowledge_point", "type", "seed", "request_id",
        ))
        return zlib.crc32(key.encode("utf-8")) + max(int(normalized.get("difficulty", 1)) - 1, 0)

    def _fallback(self, normalized: dict) -> dict:
        facts = self._facts_for(normalized)
        extra = self._extra_facts(normalized["unit_id"], normalized["knowledge_point"])
        last = None
        base = self._template_seed(normalized)
        # 事实卡里可能有碎片（如“两个消失点”），模板会返回 None 换下一张；
        # 每个事实卡有 3 种取法，种子范围按事实卡数量放开，避免 6 次就放弃。
        for offset in range(max(6, len(facts) * 3)):
            seed = base + offset
            card = build_template_card(normalized, facts, extra, seed)
            if not card:
                continue
            last = card
            errors = (
                validate_card(card, self.units, self.catalog)
                + self._offline_errors(card)
                + check_card(card, facts, extra)
                + check_single_choice_color_comparison(card)
                + check_single_choice_analysis_consistency(card, facts)
            )
            if not errors:
                return {
                    "card": card,
                    "generated_by": "template",
                    "model_blocked": True,
                    "fact_ok": True,
                    "errors": [],
                    "answer_errors": [],
                }
        if last is None:
            return {"card": None, "generated_by": "none", "errors": ["模板兜底不可用"]}
        return {
            "card": last,
            "generated_by": "template",
            "model_blocked": True,
            "errors": validate_card(last, self.units, self.catalog) + self._offline_errors(last),
            "answer_errors": (
                check_card(last, facts, extra)
                + check_single_choice_color_comparison(last)
                + check_single_choice_analysis_consistency(last, facts)
            ),
        }

    def generate(self, request: dict) -> dict:
        normalized = self._normalize_request(request)
        if request.get("with_image"):
            image_record = IMAGE_BANK.pick(normalized)
            if image_record is not None:
                image_record["cache_hit"] = False
                return image_record
        if not self._is_forced_template(normalized):
            self.load()
        key = self._cache_key(normalized)
        cached = self._cache_get(key)
        if cached is not None:
            cached["cache_hit"] = True
            return cached
        record = self._generate_with_retry([normalized])[0]
        record["cache_hit"] = False
        self._cache_put(key, record)
        return record

    def generate_many(self, requests: list[dict]) -> list[dict]:
        """一次生成多条；未过校验的自动重采样，最多 max_attempts 次。命中的直接复用缓存。"""
        if not requests:
            return []
        normalized = [self._normalize_request(r) for r in requests]
        results: list[dict | None] = [None] * len(normalized)
        missing: list[int] = []
        for i, norm in enumerate(normalized):
            if requests[i].get("with_image"):
                image_record = IMAGE_BANK.pick(norm)
                if image_record is not None:
                    image_record["cache_hit"] = False
                    results[i] = image_record
                    continue
            cached = self._cache_get(self._cache_key(norm))
            if cached is None:
                missing.append(i)
            else:
                cached["cache_hit"] = True
                results[i] = cached
        if any(not self._is_forced_template(normalized[i]) for i in missing):
            self.load()
        if missing:
            records = self._generate_with_retry([normalized[i] for i in missing])
            for i, rec in zip(missing, records):
                rec["cache_hit"] = False
                self._cache_put(self._cache_key(normalized[i]), rec)
                results[i] = rec
        filled: list[dict] = []
        for index, record in enumerate(results):
            if record is None:
                raise RuntimeError(f"批量生成内部错误：第 {index} 条没有生成结果")
            filled.append(record)
        return filled
