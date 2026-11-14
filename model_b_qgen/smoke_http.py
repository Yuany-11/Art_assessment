"""HTTP 冒烟：服务启动后验证 /health、/catalog、/generate 三个接口。

用法（服务已启动在 8002）：
    python -m model_b_qgen.smoke_http
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request


def get(url: str, timeout: float) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post(url: str, payload: dict, timeout: float) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    parser.add_argument("--wait", type=float, default=180, help="等待 /health 就绪的秒数")
    parser.add_argument("--timeout", type=float, default=300, help="单次生成超时秒数")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    deadline = time.time() + args.wait
    while True:
        try:
            health = get(f"{base}/health", 5)
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if time.time() > deadline:
                raise SystemExit(f"/health 未就绪：{exc}")
            time.sleep(2)
    print("health:", json.dumps(health, ensure_ascii=False))

    catalog = get(f"{base}/catalog", 10)
    grades = sorted(catalog["grades"], key=int)
    print("catalog grades:", grades)

    request = {
        "unit_id": "g7-u2",
        "knowledge_point": "冷暖色",
        "type": "single_choice",
        "difficulty": 1,
    }
    result = post(f"{base}/generate", request, args.timeout)
    card = result.get("card") or {}
    print("generate ok:", result.get("ok"), "| parse_ok:", result.get("parse_ok"))
    print("errors:", result.get("errors"))
    print("stem:", card.get("stem"))
    print("answer:", card.get("answer"))
    if not result.get("ok"):
        raise SystemExit("生成未通过校验")


if __name__ == "__main__":
    main()
