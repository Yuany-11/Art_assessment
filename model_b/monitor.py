"""训练监控页：读取 weights/*/history.json，训练时另开一个终端运行。

用法：python monitor.py
然后浏览器打开 http://127.0.0.1:8002（每 3 秒自动刷新）
"""
import json
import os
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

HERE = Path(__file__).resolve().parent
ROOT = Path(os.getenv("ART_ROOT", HERE.parents[1]))
WEIGHTS = Path(os.getenv("ART_WEIGHTS", ROOT / "weights"))

app = FastAPI(title="模型B训练监控")

PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>模型B 训练监控</title>
<style>
body{font-family:"Microsoft YaHei",system-ui;margin:24px;background:#f6f7f9;color:#222}
h1{font-size:20px;margin:0 0 16px}
#tick{color:#888;font-size:12px;font-weight:400}
.card{background:#fff;border-radius:10px;padding:16px;margin-bottom:16px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.head{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.name{font-weight:600;font-size:16px}
.badge{padding:2px 8px;border-radius:999px;font-size:12px}
.live{background:#e6f7ea;color:#1a7f37}.idle{background:#eee;color:#666}
.meta{color:#666;font-size:13px}
table{border-collapse:collapse;width:100%;margin-top:10px;font-size:13px}
th,td{padding:4px 8px;border-bottom:1px solid #eee;text-align:right}
th:first-child,td:first-child{text-align:left}
tr.last td{background:#fff8e1;font-weight:600}
pre{background:#111;color:#d8ffd8;padding:10px;border-radius:8px;font-size:12px;overflow:auto;max-height:180px;margin-top:10px}
.empty{color:#888}
</style>
</head>
<body>
<h1>模型B 训练监控 <span id="tick"></span></h1>
<div id="runs"><div class="empty">读取中…</div></div>
<script>
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const COLS = {train_loss:'train_loss', val_loss:'val_loss', train_acc:'train_acc', val_acc:'val_acc', val_mae:'val_mae', seconds:'秒'};
function fmt(k, v){
  if (v === undefined || v === null) return '-';
  if (k === 'val_acc' || k === 'train_acc') return (v * 100).toFixed(2) + '%';
  if (k === 'seconds') return Number(v).toFixed(1);
  return Number(v).toFixed(3);
}
function card(r){
  const last = r.history[r.history.length - 1] || {};
  const live = r.age < 90;
  const keys = Object.keys(last).filter(k => k !== 'epoch' && k !== 'per_dim_mae');
  const perDim = last.per_dim_mae ? Object.entries(last.per_dim_mae).map(([k, v]) => esc(k) + '=' + v).join('  ') : '';
  const rows = r.history.slice(-12).map((h, i, arr) =>
    '<tr class="' + (i === arr.length - 1 ? 'last' : '') + '"><td>' + h.epoch + '</td>' +
    keys.map(k => '<td>' + fmt(k, h[k]) + '</td>').join('') + '</tr>').join('');
  const head = '<tr><th>轮</th>' + keys.map(k => '<th>' + (COLS[k] || k) + '</th>').join('') + '</tr>';
  const dims = r.dims && r.dims.length ? '| 维度: ' + esc(r.dims.join(',')) : '';
  const log = r.log && r.log.length ? '<pre>' + esc(r.log.join('\\n')) + '</pre>' : '';
  return '<div class="card"><div class="head"><span class="name">' + esc(r.name) + '</span>' +
    '<span class="badge ' + (live ? 'live' : 'idle') + '">' + (live ? '训练中' : '无更新') + '</span>' +
    '<span class="meta">' + esc(r.version || '') + ' ' + dims + '</span>' +
    '<span class="meta">最后写入 ' + r.age + ' 秒前</span></div>' +
    (perDim ? '<div class="meta" style="margin-top:6px">每维 MAE: ' + perDim + '</div>' : '') +
    '<table>' + head + rows + '</table>' + log + '</div>';
}
async function load(){
  try {
    const rs = await (await fetch('/api/runs', {cache: 'no-store'})).json();
    document.getElementById('runs').innerHTML = rs.length
      ? rs.map(card).join('')
      : '<div class="empty">还没有训练记录（history.json）</div>';
  } catch (e) {
    document.getElementById('runs').innerHTML = '<div class="empty">连接不上监控服务</div>';
  }
  document.getElementById('tick').textContent = '更新于 ' + new Date().toLocaleTimeString();
}
load();
setInterval(load, 3000);
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE


@app.get("/api/runs")
def api_runs():
    runs = []
    if WEIGHTS.exists():
        for d in sorted(WEIGHTS.iterdir()):
            h = d / "history.json"
            if not h.is_file():
                continue
            try:
                data = json.loads(h.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            logf = d / "train_log.txt"
            tail = []
            if logf.is_file():
                try:
                    tail = logf.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-10:]
                except OSError:
                    pass
            runs.append({
                "name": d.name,
                "version": data.get("version", ""),
                "dims": data.get("dims") or data.get("classes") or [],
                "history": data.get("history", []),
                "log": tail,
                "age": round(time.time() - h.stat().st_mtime),
            })
    return runs


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8002, log_level="warning")
