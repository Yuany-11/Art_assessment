"""E1 three-seed training monitor (read-only).

Serves an auto-refreshing page on port 8003 (8002 is currently occupied).
Reads only:
    logs/exp_seed1/train_log.txt
    logs/exp_seed2/train_log.txt
    logs/exp_seed3/train_log.txt

Start:
    pythonw app_exp.py
Open:
    http://127.0.0.1:8003/
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(os.getenv("ART_ROOT", HERE.parents[2]))
PORT = int(os.getenv("ART_MONITOR_PORT", "8003"))
SEEDS = (1, 2, 3)

EPOCH_RE = re.compile(
    r"\[第 (\d+)/(\d+) 轮\] train_loss=([\d.]+) val_loss=([\d.]+) "
    r"val_MAE=构图=([\d.]+) 色彩=([\d.]+) 造型=([\d.]+) 创意=([\d.]+) "
    r"整体=([\d.]+) 用时=([\d.]+)s\s*(\*?)"
)
TS_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")


def read_seed(seed: int):
    path = ROOT / "logs" / f"exp_seed{seed}" / "train_log.txt"
    if not path.exists():
        return {"seed": seed, "status": "等待", "epochs": [], "total": 20,
                "best": None, "age": None, "log_tail": [], "start": None}
    text = path.read_text(encoding="utf-8", errors="replace")
    age = max(0.0, datetime.now().timestamp() - path.stat().st_mtime)
    epochs, total, start = [], 20, None
    for line in text.splitlines():
        m = EPOCH_RE.search(line)
        if m:
            g = m.groups()
            epochs.append({
                "epoch": int(g[0]), "total": int(g[1]),
                "train_loss": float(g[2]), "val_loss": float(g[3]),
                "mae": [float(g[4]), float(g[5]), float(g[6]), float(g[7])],
                "overall": float(g[8]), "seconds": float(g[9]), "best": bool(g[10]),
            })
            total = int(g[1])
            continue
        if start is None:
            t = TS_RE.match(line)
            if t:
                start = datetime.strptime(t.group(1), "%Y-%m-%d %H:%M:%S")
    tail = [ln for ln in text.strip().splitlines() if ln][-8:]
    last = tail[-1] if tail else ""
    if "完成：" in last or "早停" in last:
        status = "已完成"
    elif "已取消" in last:
        status = "已取消"
    elif age < 180 and epochs:
        status = "训练中"
    elif epochs:
        status = "已停止/无更新"
    else:
        status = "等待"
    best = min(epochs, key=lambda e: e["overall"]) if epochs else None
    return {"seed": seed, "status": status, "epochs": epochs, "total": total,
            "best": best, "age": round(age, 1), "log_tail": tail,
            "start": start.isoformat(sep=" ") if start else None}


def state():
    seeds = [read_seed(s) for s in SEEDS]
    done = [s for s in seeds if s["status"] == "已完成"]
    cur = next((s for s in seeds if s["status"] == "训练中"), None)
    if cur is None:
        cur = next((s for s in seeds if s["status"] not in ("已完成", "等待")), None)
    return {"now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "seeds": seeds, "done": len(done), "current": cur["seed"] if cur else None}


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def bar(pct, color="#2563eb"):
    pct = max(0.0, min(1.0, pct))
    return f'<div class="bar"><i style="width:{pct*100:.1f}%;background:{color}"></i></div>'


def seed_card(s):
    epochs = s["epochs"]
    best = s["best"]
    last = epochs[-1] if epochs else None
    total = s["total"]
    done = len(epochs)
    pct = done / max(total, 1)
    badge = {"训练中": "run", "已完成": "end", "等待": "wait"}.get(s["status"], "stop")
    cur_mae = f"{last['overall']:.2f}" if last else "—"
    best_mae = f"{best['overall']:.2f}（第 {best['epoch']} 轮）" if best else "—"
    last_ep = f"第 {last['epoch']}/{total} 轮" if last else "—"
    age = f"{s['age']:.0f}s 前更新" if s["age"] is not None else "—"
    rows = ""
    for e in epochs[-6:]:
        rows += (f"<tr><td>{e['epoch']}</td><td>{e['train_loss']:.3f}</td>"
                 f"<td>{e['val_loss']:.3f}</td>"
                 + "".join(f"<td>{v:.2f}</td>" for v in e["mae"])
                 + f"<td><b>{e['overall']:.2f}</b></td></tr>")
    tail = "<br>".join(esc(x) for x in s["log_tail"][-4:]) or "—"
    return f"""
    <div class="card">
      <div class="head"><h2>seed {s['seed']}</h2>
        <span class="badge {badge}">{esc(s['status'])}</span></div>
      <div class="meta">{last_ep} · {age}</div>
      {bar(pct, '#16a34a' if s['status']=='已完成' else '#2563eb')}
      <div class="stats">
        <div><span>当前整体 MAE</span><b>{cur_mae}</b></div>
        <div><span>最佳整体 MAE</span><b>{best_mae}</b></div>
      </div>
      <table><thead><tr><th>轮</th><th>train</th><th>val</th><th>构图</th><th>色彩</th><th>造型</th><th>创意</th><th>整体</th></tr></thead>
      <tbody>{rows or '<tr><td colspan="8">暂无数据</td></tr>'}</tbody></table>
      <pre>{tail}</pre>
    </div>"""


def page():
    st = state()
    cards = "".join(seed_card(s) for s in st["seeds"])
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="3">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>E1 三 seed 训练监控</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;padding:22px 26px 40px;background:#f5f7fa;color:#111827;
     font-family:"Microsoft YaHei","Segoe UI",system-ui,sans-serif}}
header{{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:16px}}
h1{{font-size:20px;margin:0}}
.sub{{color:#6b7280;font-size:12px}}
.links a{{margin-left:10px;color:#2563eb;text-decoration:none;font-size:12px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:14px}}
.card{{background:#fff;border-radius:12px;padding:16px 18px;box-shadow:0 1px 4px rgba(0,0,0,.07)}}
.head{{display:flex;align-items:center;justify-content:space-between;gap:10px}}
h2{{font-size:15px;margin:0}}
.badge{{padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600}}
.run{{background:#dcfce7;color:#166534}}
.end{{background:#e5e7eb;color:#374151}}
.wait{{background:#fef3c7;color:#92400e}}
.stop{{background:#fee2e2;color:#991b1b}}
.meta{{color:#6b7280;font-size:12px;margin:7px 0 8px}}
.bar{{height:10px;background:#e5e7eb;border-radius:6px;overflow:hidden;margin:6px 0 10px}}
.bar>i{{display:block;height:100%;transition:width .4s}}
.stats{{display:flex;gap:20px;margin:8px 0 10px}}
.stats span{{display:block;color:#6b7280;font-size:11px}}
.stats b{{font-size:18px}}
table{{width:100%;border-collapse:collapse;font-size:11.5px;margin-top:6px}}
th,td{{padding:4px 5px;border-bottom:1px solid #eef1f5;text-align:right}}
th:first-child,td:first-child{{text-align:left}}
th{{color:#6b7280;font-weight:600}}
pre{{background:#0f172a;color:#cbd5e1;border-radius:8px;padding:8px 10px;
     font-size:10.5px;line-height:1.55;overflow:auto;max-height:110px;margin:10px 0 0}}
.note{{margin-top:18px;color:#6b7280;font-size:12px;line-height:1.8}}
</style></head><body>
<header>
  <div><h1>E1 三 seed 训练监控</h1>
    <div class="sub">每 3 秒刷新 · 当前 {esc(st['now'])} · 完成 {st['done']}/3 · 当前 seed {st['current'] or '—'}</div></div>
  <div class="links"><a href="http://127.0.0.1:8010/" target="_blank">测试页 8010</a>
  <a href="/api/state" target="_blank">JSON</a></div>
</header>
<div class="grid">{cards}</div>
<div class="note">基线：v3.0 单模型 1923 张测试集整体 MAE <b>7.1996</b>。E1 目标是把 3 个 seed 的 raw 四维平均后再评估；低于 6.95 才算明显提升。</div>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/state":
            body = json.dumps(state(), ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
        elif self.path in ("/", "/index.html"):
            self._send(200, page().encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        else:
            self._send(404, b'{"error":"not found"}', "application/json")

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    srv = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"http://127.0.0.1:{PORT}/", flush=True)
    srv.serve_forever()
