"""给评测请求集打图题标记：知识点有图题素材的请求加 with_image=true。

出题服务据此走图题通道，返回带配图的题卡；没有图题素材的知识点仍由模型出文字题。
另生成图题专项请求集（从图题库反推请求），用于单独验收图题通道。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "09_qgen" / "eval" / "requests_v6_100.jsonl"
OUT = ROOT / "data" / "09_qgen" / "eval" / "requests_v6_100_images.jsonl"
IMAGE_FILES = (
    ROOT / "data" / "09_qgen" / "image_questions" / "img_questions.jsonl",
    ROOT / "data" / "09_qgen" / "image_questions" / "low_grade_20261114.jsonl",
    ROOT / "data" / "09_qgen" / "image_questions" / "type_cover_20261114.jsonl",
)


def load_cards() -> list[dict]:
    cards = []
    for path in IMAGE_FILES:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            card = json.loads(line)
            if card.get("resources") and card.get("stem"):
                cards.append(card)
    return cards


def main() -> None:
    cards = load_cards()
    keys = {(int(c["grade"]), c["unit_id"], c["knowledge_point"]) for c in cards}
    requests = [json.loads(line) for line in SRC.read_text(encoding="utf-8").splitlines() if line.strip()]
    marked = 0
    out_lines = []
    for request in requests:
        item = dict(request)
        if (int(item["grade"]), item["unit_id"], item["knowledge_point"]) in keys:
            item["with_image"] = True
            marked += 1
        out_lines.append(json.dumps(item, ensure_ascii=False))
    OUT.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"请求 {len(requests)} 条，标记图题 {marked} 条 -> {OUT}")

    # 图题专项：每年级四类题型各抽一道，验收「图题覆盖全部题型」。
    by_grade: dict[int, list[dict]] = {}
    for card in cards:
        by_grade.setdefault(int(card["grade"]), []).append(card)
    picked: list[dict] = []
    for grade in sorted(by_grade):
        by_type: dict[str, list[dict]] = {}
        for card in sorted(by_grade[grade], key=lambda c: str(c.get("id", ""))):
            by_type.setdefault(card["type"], []).append(card)
        for qtype in ("single_choice", "true_false", "fill_blank", "short_answer"):
            pool = by_type.get(qtype) or []
            if pool:
                picked.append(pool[(grade - 1) % len(pool)])
    image_requests = [
        {
            "request_id": f"img-eval-{i:04d}",
            "grade": int(card["grade"]),
            "unit_id": card["unit_id"],
            "unit_name": card.get("unit_name", ""),
            "knowledge_point": card["knowledge_point"],
            "type": card["type"],
            "difficulty": int(card.get("difficulty", 1)),
            "with_image": True,
        }
        for i, card in enumerate(picked, 1)
    ]
    out_image = OUT.with_name("requests_image_36.jsonl")
    out_image.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in image_requests) + "\n",
        encoding="utf-8",
    )
    print(f"图题专项 {len(image_requests)} 条 -> {out_image}")


if __name__ == "__main__":
    main()
