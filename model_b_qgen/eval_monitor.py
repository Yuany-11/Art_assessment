"""评测只读监测页：解析 eval_runner 的 stdout 日志，实时显示进度。

只读，不加载模型、不占显存，可与评测进程同时跑。

    cd <仓库根>
    .venv/Scripts/python.exe -m model_b_qgen.eval_monitor \
        --log logs/qgen_eval/v4_strict100_fixed_20261114.stdout.log --port 8004
"""
from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .paths import PROJECT_ROOT

LINE = re.compile(
    r"^\[(?P<i>\d+)/(?P<n>\d+)\]\s+ok=(?P<ok>\w+)\s+parse=(?P<parse>\w+)\s+"
    r"errors=(?P<errors>.*?)\s+(?P<sec>[\d.]+)s\s*(?P<rest>.*)$"
)


def parse_log(path: Path) -> dict:
    total_expected = 0
    rows: list[dict] = []
    finished = False
    if path.exists():
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if "报告：" in line:
                finished = True
                continue
            match = LINE.match(line.strip())
            if not match:
                continue
            rest = match.group("rest").strip()
            qtype, _, stem = rest.partition(" ")
            rows.append(
                {
                    "index": int(match.group("i")),
                    "ok": match.group("ok") == "True",
                    "parse": match.group("parse") == "True",
                    "errors": match.group("errors"),
                    "seconds": float(match.group("sec")),
                    "type": qtype,
                    "stem": stem.strip(),
                }
            )
            total_expected = max(total_expected, int(match.group("n")))

    done = len(rows)
    total = total_expected or 0
    ok_count = sum(1 for row in rows if row["ok"])
    parse_fail = sum(1 for row in rows if not row["parse"])
    err_nonzero = sum(1 for row in rows if row["errors"] not in ("[]", "", "None"))
    seconds = [row["seconds"] for row in rows]
    avg = round(sum(seconds) / len(seconds), 2) if seconds else 0.0
    by_type: dict[str, int] = {}
    for row in rows:
        by_type[row["type"]] = by_type.get(row["type"], 0) + 1
    remaining = max(total - done, 0)
    return {
        "log": str(path),
        "log_mtime": path.stat().st_mtime if path.exists() else None,
        "total": total,
        "done": done,
        "remaining": remaining,
        "ok": ok_count,
        "ok_rate": round(ok_count / done, 4) if done else 0.0,
        "parse_fail": parse_fail,
        "err_nonzero": err_nonzero,
        "avg_seconds": avg,
        "gpu_seconds": round(sum(seconds), 1),
        "eta_seconds": round(avg * remaining, 1),
        "by_type": by_type,
        "finished": finished,
        "recent": rows[-14:],
    }


PAGE = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>模型B · 100 条评测监测</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#eef1f6;--panel:#fff;--ink:#0f172a;--dim:#64748b;--line:#e2e8f0;
--ok:#0f766e;--okbg:#ecfdf5;--bad:#b91c1c;--badbg:#fef2f2;--accent:#2563eb;--warn:#b45309;--warnbg:#fffbeb}
*{box-sizing:border-box}html,body{margin:0}
body{min-height:100vh;background:radial-gradient(1100px 500px at 85% -10%,#dbeafe 0,transparent 60%),
radial-gradient(900px 500px at -10% 10%,#ede9fe 0,transparent 55%),var(--bg);
color:var(--ink);font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.topbar{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:18px 32px;
background:linear-gradient(120deg,#0f172a 0,#1e3a8a 58%,#1d4ed8 100%);color:#fff}
.brand h1{margin:0;font-size:19px}.brand p{margin:2px 0 0;font-size:12px;color:#bfdbfe}
.pill{font-size:12px;padding:6px 12px;border-radius:999px;background:rgba(255,255,255,.12);
border:1px solid rgba(255,255,255,.22);color:#e0e7ff;white-space:nowrap}
.wrap{max-width:1180px;margin:0 auto;padding:22px 32px 48px;display:grid;gap:18px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;
box-shadow:0 10px 30px rgba(15,23,42,.07);padding:20px}
.bar{height:12px;border-radius:999px;background:#e2e8f0;overflow:hidden;margin:12px 0 6px}
.bar i{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,#2563eb,#4f46e5);
transition:width .4s ease}
.meta{display:flex;justify-content:space-between;font-size:12px;color:var(--dim)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px}
.tile{border:1px solid var(--line);border-radius:14px;padding:14px 16px;background:#fbfcfe}
.tile b{display:block;font-size:24px;letter-spacing:.5px}
.tile span{font-size:12px;color:var(--dim)}
.tile.good b{color:var(--ok)}.tile.bad b{color:var(--bad)}.tile.warn b{color:var(--warn)}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;color:var(--dim);font-weight:600;background:#f8fafc}
tbody tr:hover{background:#f8fafc}
.tag{display:inline-block;font-size:11px;padding:1px 8px;border-radius:999px;white-space:nowrap}
.tag.ok{background:var(--okbg);color:var(--ok)}.tag.bad{background:var(--badbg);color:var(--bad)}
.tag.warn{background:var(--warnbg);color:var(--warn)}
.note{font-size:12px;color:var(--dim);margin-top:8px}
.num{font-variant-numeric:tabular-nums;color:var(--dim);white-space:nowrap}
</style></head><body>
<div class="topbar">
  <div class="brand"><h1>模型B · 100 条评测监测</h1>
  <p id="log">读取日志中…</p></div>
  <div class="pill" id="state">连接中</div>
</div>
<div class="wrap">
  <div class="card">
    <div class="meta"><span id="lbl">已完成 0 / 0</span><span id="right">—</span></div>
    <div class="bar"><i id="fill" style="width:0%"></i></div>
    <div class="note">只读页面，直接解析评测进程的 stdout 日志；不触发生成、不占显存。</div>
  </div>
  <div class="grid" id="tiles"></div>
  <div class="card">
    <table><thead><tr><th>#</th><th>结果</th><th>耗时</th><th>题型</th><th>题干</th></tr></thead>
    <tbody id="rows"><tr><td colspan="5" class="num">等待数据…</td></tr></tbody></table>
  </div>
</div>
<script>
const fmt = s => s >= 60 ? (s/60).toFixed(1) + ' min' : s.toFixed(0) + ' s';
function tile(label, value, cls){return `<div class="tile ${cls||''}"><b>${value}</b><span>${label}</span></div>`}
async function tick(){
  let d;
  try { d = await (await fetch('/api/progress', {cache:'no-store'})).json(); }
  catch(e){ document.getElementById('state').textContent = '读取失败'; return; }
  const pct = d.total ? Math.min(100, d.done / d.total * 100) : 0;
  document.getElementById('fill').style.width = pct.toFixed(1) + '%';
  document.getElementById('lbl').textContent = `已完成 ${d.done} / ${d.total || '?'}`;
  document.getElementById('right').textContent =
    (d.eta_seconds ? '预计剩余 ' + fmt(d.eta_seconds) : '—') + ' · GPU 累计 ' + fmt(d.gpu_seconds);
  document.getElementById('log').textContent = d.log;
  const st = document.getElementById('state');
  if (d.finished) { st.textContent = '评测已结束'; st.className = 'pill'; }
  else if (d.done) { st.textContent = '评测进行中'; }
  else { st.textContent = '等待首条结果'; }
  const byType = Object.entries(d.by_type||{}).map(([k,v]) => `${k}:${v}`).join(' ') || '—';
  document.getElementById('tiles').innerHTML = [
    tile('ok 通过', `${d.ok} / ${d.done||0}`, 'good'),
    tile('通过率', (d.done? (d.ok_rate*100).toFixed(0)+'%' : '—'), 'good'),
    tile('parse 失败', d.parse_fail, d.parse_fail ? 'bad' : ''),
    tile('errors 非空', d.err_nonzero, d.err_nonzero ? 'warn' : ''),
    tile('平均耗时', d.avg_seconds ? d.avg_seconds+' s' : '—', ''),
    tile('题型分布', `<span style="font-size:13px">${byType}</span>`, ''),
  ].join('');
  const rows = (d.recent||[]).slice().reverse().map(r => {
    const bad = r.errors && r.errors !== '[]';
    return `<tr><td class="num">${r.index}</td>
      <td><span class="tag ${r.ok?'ok':'bad'}">${r.ok?'ok':'fail'}</span>
      ${bad ? `<span class="tag warn" title="${r.errors.replace(/"/g,'&quot;')}">errors</span>`:''}</td>
      <td class="num">${r.seconds}s</td><td>${r.type}</td>
      <td>${r.stem.replace(/</g,'&lt;')}</td></tr>`;
  }).join('');
  document.getElementById('rows').innerHTML = rows || '<tr><td colspan="5" class="num">等待数据…</td></tr>';
}
tick(); setInterval(tick, 3000);
</script></body></html>
"""


def make_handler(log_path: Path):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/api/progress"):
                data = json.dumps(parse_log(log_path), ensure_ascii=False).encode("utf-8")
                self._send(200, data, "application/json; charset=utf-8")
            elif self.path in ("/", "/index.html"):
                self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain; charset=utf-8")

        def log_message(self, *args) -> None:
            pass

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    default_log = PROJECT_ROOT / "logs" / "qgen_eval" / "v4_strict100_fixed_20261114.stdout.log"
    parser.add_argument("--log", default=str(default_log))
    parser.add_argument("--port", type=int, default=8004)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    log_path = Path(args.log).resolve()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(log_path))
    print(f"评测监测页：http://{args.host}:{args.port}/  日志：{log_path}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
