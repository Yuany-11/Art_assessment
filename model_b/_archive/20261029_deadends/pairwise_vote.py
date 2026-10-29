"""方法 3：本地成对点选页。只记录真人选择，不产生任何 AI 分数。"""
from __future__ import annotations

import csv
import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / "logs" / "pairwise_v1"
PAIRS_FILE = DATA / "pairs.json"
VOTES_FILE = DATA / "votes.csv"
TEMPLATE = HERE / "pairwise_template.html"
PORT = 8020
PENCILS = ROOT / "_downloads" / "Pencils_to_Pixels"
CHOICES = {"a", "b", "same", "skip"}
FIELDS = ["ts", "rater", "block", "pair_id", "winner", "a_uid", "b_uid",
          "left_uid", "right_uid", "ms"]
LOCK = threading.Lock()

PAIRS = json.loads(PAIRS_FILE.read_text(encoding="utf-8"))["pairs"]
BY_ID = {p["pair_id"]: p for p in PAIRS}
UID_PATH: dict[str, Path] = {}
for p in PAIRS:
    for side in ("a", "b"):
        UID_PATH[p[side]["uid"]] = Path(p[side]["path"]).resolve()


def read_votes() -> list[dict]:
    if not VOTES_FILE.exists():
        return []
    with VOTES_FILE.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def append_vote(row: dict) -> None:
    new = not VOTES_FILE.exists()
    VOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with VOTES_FILE.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def undo_last(rater: str, pair_id: str) -> bool:
    rows = read_votes()
    last = None
    for i, r in enumerate(rows):
        if r["rater"] == rater:
            last = i
    if last is None or rows[last]["pair_id"] != pair_id:
        return False
    rows.pop(last)
    with VOTES_FILE.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            self._send(200, TEMPLATE.read_bytes(), "text/html; charset=utf-8")
            return
        if u.path == "/api/session":
            q = parse_qs(u.query)
            rater = (q.get("rater", [""])[0] or "").strip()[:32]
            try:
                block = int(q.get("block", ["1"])[0])
            except ValueError:
                block = 1
            if not rater:
                self._json(400, {"error": "rater 不能为空"})
                return
            answered = sorted({r["pair_id"] for r in read_votes() if r["rater"] == rater})
            items = [{"pair_id": p["pair_id"], "a": p["a"]["uid"], "b": p["b"]["uid"],
                      "group": p["group"]} for p in PAIRS if p["block"] == block]
            self._json(200, {"block": block, "total": len(items),
                             "answered": answered, "pairs": items})
            return
        if u.path.startswith("/img/"):
            uid = unquote(u.path[len("/img/"):])
            path = UID_PATH.get(uid)
            if path is None or not path.is_file():
                self._send(404, b"not found", "text/plain")
                return
            try:
                path.relative_to(PENCILS.resolve())
            except ValueError:
                self._send(403, b"forbidden", "text/plain")
                return
            ctype = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
            self._send(200, path.read_bytes(), ctype)
            return
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        u = urlparse(self.path)
        if u.path not in ("/api/vote", "/api/undo"):
            self._send(404, b"not found", "text/plain")
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            self._json(400, {"error": "bad json"})
            return

        rater = str(data.get("rater", "")).strip()[:32]
        pair_id = str(data.get("pair_id", ""))
        p = BY_ID.get(pair_id)
        if not rater or p is None:
            self._json(400, {"error": "rater/pair_id 无效"})
            return

        with LOCK:
            if u.path == "/api/undo":
                ok = undo_last(rater, pair_id)
                self._json(200 if ok else 409, {"ok": ok})
                return

            winner = str(data.get("winner", ""))
            left = str(data.get("left_uid", ""))
            right = str(data.get("right_uid", ""))
            if winner not in CHOICES:
                self._json(400, {"error": "winner 无效"})
                return
            expected = {p["a"]["uid"], p["b"]["uid"]}
            if {left, right} != expected:
                self._json(400, {"error": "图片不匹配"})
                return
            try:
                ms = max(0, min(600000, int(data.get("ms", 0))))
            except (TypeError, ValueError):
                ms = 0
            append_vote({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "rater": rater,
                "block": p["block"],
                "pair_id": pair_id,
                "winner": winner,
                "a_uid": p["a"]["uid"],
                "b_uid": p["b"]["uid"],
                "left_uid": left,
                "right_uid": right,
                "ms": ms,
            })
        self._json(200, {"ok": True})


def main():
    if not PAIRS_FILE.exists():
        raise SystemExit(f"缺少 {PAIRS_FILE}，先运行 training/make_pairs.py")
    if not TEMPLATE.exists():
        raise SystemExit(f"缺少 {TEMPLATE}")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"http://127.0.0.1:{PORT}/  (Ctrl+C 停止)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
