"""APDDv2 四维评分训练监控页（只读，独立于训练脚本）。

只读取三个文件：
    logs/apddv2/history.json
    logs/apddv2/train_log.txt
    weights/apddv2/last.pt        （仅取 args.epochs，不加载权重）

用法：
    python app.py
    浏览器打开 http://127.0.0.1:8002（被占用则自动换 8003），每 3 秒刷新。
"""
import json
import os
import socket
import time
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

HERE = Path(__file__).resolve().parent          # repo/model_b/monitor
ROOT = Path(os.getenv("ART_ROOT", HERE.parents[2]))
LOGS = Path(os.getenv("ART_LOGS", ROOT / "logs")) / "apddv2"
WEIGHTS = Path(os.getenv("ART_WEIGHTS", ROOT / "weights")) / "apddv2"
HISTORY = LOGS / "history.json"
TRAIN_LOG = LOGS / "train_log.txt"
LAST = WEIGHTS / "last.pt"

DEFAULT_EPOCHS = 10
DIMS = [["composition", "构图"], ["color", "色彩"], ["modeling", "造型"], ["creativity", "创意"]]
STALE_SECONDS = 120  # 超过这么久没写入，视为不在训练中

app = FastAPI(title="APDDv2 训练监控")

_epochs_cache = {"key": None, "value": DEFAULT_EPOCHS}
_history_cache = None


def read_total_epochs():
    """只从 last.pt 里取 args.epochs；mmap 避免把权重读进内存。"""
    try:
        st = LAST.stat()
    except OSError:
        return DEFAULT_EPOCHS
    key = (st.st_mtime_ns, st.st_size)
    if _epochs_cache["key"] == key:
        return _epochs_cache["value"]
    value = DEFAULT_EPOCHS
    try:
        import torch

        ckpt = torch.load(LAST, map_location="cpu", mmap=True, weights_only=True)
        ep = ckpt.get("args", {}).get("epochs")
        if isinstance(ep, int) and ep > 0:
            value = ep
        del ckpt
    except Exception:
        value = DEFAULT_EPOCHS
    _epochs_cache["key"] = key
    _epochs_cache["value"] = value
    return value


def read_history():
    global _history_cache
    try:
        data = json.loads(HISTORY.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            _history_cache = data
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return _history_cache or {"history": []}


def read_log(lines=10):
    try:
        all_lines = TRAIN_LOG.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    except OSError:
        return [], []
    return all_lines[-lines:], all_lines[-20:]


def newest_mtime():
    times = []
    for p in (HISTORY, TRAIN_LOG):
        try:
            times.append(p.stat().st_mtime)
        except OSError:
            pass
    return max(times) if times else None


def build_state():
    data = read_history()
    history = data.get("history") or []
    total = read_total_epochs()
    log_tail, log_recent = read_log(10)
    completed = len(history)

    # 只看最后一行：脚本每次运行都以 finished. 收尾，续训会往后追加新行。
    finished = bool(log_recent) and "finished." in log_recent[-1]
    mtime = newest_mtime()
    age = None if mtime is None else max(0, int(time.time() - mtime))

    if finished:
        state = "已结束"
    elif age is not None and age <= STALE_SECONDS:
        state = "训练中"
    else:
        state = "已结束"

    elapsed = sum(float(h.get("seconds") or 0) for h in history)
    avg = elapsed / completed if completed else 0.0
    remaining = max(0.0, avg * (total - completed))
    best = min((float(h["val_mae"]) for h in history if h.get("val_mae") is not None), default=None)

    # 本轮按时间估算的进度：训练脚本不报 batch，只能拿"距上次写入的秒数 / 平均每轮秒数"估。
    epoch_est = avg if avg > 0 else 80.0
    in_epoch = min(0.99, max(0.0, (age or 0) / epoch_est)) if state == "训练中" else 0.0
    progress = min(1.0, (completed + in_epoch) / total) if total else 0.0

    return {
        "state": state,
        "age_seconds": age,
        "total_epochs": total,
        "completed_epochs": completed,
        "epoch_fraction": round(in_epoch, 3),
        "progress": round(progress, 3),
        "best_mae": best,
        "elapsed_seconds": round(elapsed, 1),
        "avg_epoch_seconds": round(avg, 1),
        "remaining_seconds": round(remaining, 1),
        "dims": data.get("dims") or [d[0] for d in DIMS],
        "history": history,
        "log_tail": log_tail,
    }


PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>APDDv2 训练监控</title>
<style>
:root{--bg:#f5f6f8;--card:#fff;--line:#e5e7eb;--ink:#1f2937;--muted:#6b7280;--blue:#2563eb;--green:#059669;--amber:#d97706;--purple:#9333ea}
*{box-sizing:border-box}
body{margin:0;padding:24px 28px 40px;background:var(--bg);color:var(--ink);font-family:"Microsoft YaHei","PingFang SC",system-ui,sans-serif}
h1{font-size:20px;margin:0}
h2{font-size:14px;margin:0 0 12px;color:#374151;font-weight:600}
header{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:18px}
.badge{padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600}
.live{background:#e7f7ee;color:#0f7a45;animation:pulse 1.6s ease-out infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(5,150,105,.45)}70%{box-shadow:0 0 0 8px rgba(5,150,105,0)}100%{box-shadow:0 0 0 0 rgba(5,150,105,0)}}
.done{background:#eef0f3;color:#4b5563}
.meta{color:var(--muted);font-size:12px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:14px}
.card{background:var(--card);border-radius:10px;padding:16px 18px;box-shadow:0 1px 3px rgba(16,24,40,.07)}
.stat .k{color:var(--muted);font-size:12px;margin-bottom:6px}
.stat .v{font-size:24px;font-weight:700;letter-spacing:.3px}
.stat .s{color:var(--muted);font-size:12px;margin-top:4px}
.progress-card{margin-bottom:14px}
.bar{height:10px;background:#e8ebef;border-radius:999px;overflow:hidden}
.bar>i{display:block;height:100%;width:0;background:linear-gradient(90deg,#2563eb,#059669);border-radius:999px;transition:width .4s ease}
.bar-row{display:flex;justify-content:space-between;font-size:12px;color:var(--muted);margin-top:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:14px;margin-bottom:14px}
.chart{width:100%}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:6px 8px;border-bottom:1px solid #eef0f3;text-align:right;white-space:nowrap}
th{color:var(--muted);font-weight:600;font-size:12px}
th:first-child,td:first-child{text-align:left}
tr.last td{background:#fff8e1;font-weight:600}
pre{background:#0f172a;color:#d5f5dd;padding:12px 14px;border-radius:8px;font-size:12px;line-height:1.6;overflow:auto;max-height:220px;margin:0;font-family:Consolas,"Courier New",monospace}
.empty{color:var(--muted);font-size:13px;padding:10px 0}
footer{color:var(--muted);font-size:12px;margin-top:18px;line-height:1.7}
</style>
</head>
<body>
<header>
  <h1>APDDv2 四维评分 · 训练监控</h1>
  <span id="stateBadge" class="badge done">读取中</span>
  <span id="conn" class="meta"></span>
</header>

<div class="cards">
  <div class="card stat"><div class="k">当前轮 / 总轮</div><div class="v" id="epochs">-</div><div class="s" id="epochsSub"></div></div>
  <div class="card stat"><div class="k">最佳验证 MAE</div><div class="v" id="best">-</div><div class="s">0–100 分制，越低越好</div></div>
  <div class="card stat"><div class="k">累计耗时</div><div class="v" id="elapsed">-</div><div class="s" id="avg"></div></div>
  <div class="card stat"><div class="k">估算剩余</div><div class="v" id="remain">-</div><div class="s">按已跑轮次平均耗时推算</div></div>
</div>

<div class="card progress-card">
  <div class="bar"><i id="barFill"></i></div>
  <div class="bar-row"><span id="progressText">-</span><span id="updated"></span></div>
</div>

<div class="grid">
  <div class="card"><h2>loss 曲线</h2><div id="lossChart" class="chart"></div></div>
  <div class="card"><h2>四维 MAE 曲线</h2><div id="maeChart" class="chart"></div></div>
</div>

<div class="card" style="margin-bottom:14px">
  <h2>每轮明细</h2>
  <div id="tableWrap"><div class="empty">暂无数据</div></div>
</div>

<div class="card">
  <h2>训练日志（最后 10 行）</h2>
  <pre id="log">暂无日志</pre>
</div>

<footer>
  每 3 秒自动刷新 · 只读 logs\\apddv2\\history.json、logs\\apddv2\\train_log.txt、weights\\apddv2\\last.pt（仅取 args.epochs）
</footer>

<script>
const DIMS = [["composition","构图"],["color","色彩"],["modeling","造型"],["creativity","创意"]];
const COLORS = ["#2563eb","#059669","#d97706","#9333ea"];
const NS = "http://www.w3.org/2000/svg";
let latest = null;

function el(name, attrs, parent){
  const e = document.createElementNS(NS, name);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
function fmtSec(s){
  if (s === null || s === undefined) return "-";
  s = Math.round(s);
  if (s < 60) return s + " 秒";
  const m = Math.floor(s / 60), r = s % 60;
  if (m < 60) return m + " 分" + (r ? " " + r + " 秒" : "");
  return Math.floor(m / 60) + " 小时 " + (m % 60) + " 分";
}
function chart(hostId, series, xs, unit){
  const host = document.getElementById(hostId);
  host.innerHTML = "";
  if (!xs.length){
    const d = document.createElement("div"); d.className = "empty"; d.textContent = "暂无数据"; host.appendChild(d); return;
  }
  const w = Math.max(host.clientWidth || 620, 320), h = 240;
  const pad = {l: 52, r: 14, t: 34, b: 30};
  const svg = el("svg", {viewBox: "0 0 " + w + " " + h, width: "100%", height: h, role: "img"}, host);

  const all = [];
  series.forEach(s => s.values.forEach(v => { if (v !== null && v !== undefined) all.push(Number(v)); }));
  if (!all.length){ const d = document.createElement("div"); d.className = "empty"; d.textContent = "暂无数据"; host.appendChild(d); return; }
  let min = Math.min.apply(null, all), max = Math.max.apply(null, all);
  if (min === max){ min -= 1; max += 1; }
  const span = max - min; min -= span * 0.08; max += span * 0.08;
  const X = i => pad.l + (xs.length <= 1 ? (w - pad.l - pad.r) / 2 : i * (w - pad.l - pad.r) / (xs.length - 1));
  const Y = v => pad.t + (1 - (v - min) / (max - min)) * (h - pad.t - pad.b);

  for (let t = 0; t <= 4; t++){
    const v = min + (max - min) * t / 4, y = Y(v);
    el("line", {x1: pad.l, x2: w - pad.r, y1: y, y2: y, stroke: "#eef0f3", "stroke-width": 1}, svg);
    el("text", {x: pad.l - 8, y: y + 4, "text-anchor": "end", fill: "#6b7280", "font-size": 11}, svg).textContent = v.toFixed(1);
  }
  xs.forEach((e, i) => {
    el("text", {x: X(i), y: h - 9, "text-anchor": "middle", fill: "#6b7280", "font-size": 11}, svg).textContent = "第" + e + "轮";
  });

  series.forEach(s => {
    const pts = [];
    s.values.forEach((v, i) => { if (v !== null && v !== undefined) pts.push([X(i), Y(Number(v)), Number(v)]); });
    if (pts.length > 1){
      el("polyline", {points: pts.map(p => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" "),
        fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round"}, svg);
    }
    pts.forEach(p => {
      const c = el("circle", {cx: p[0], cy: p[1], r: 3.2, fill: s.color}, svg);
      const tip = el("title", {}, c); tip.textContent = s.name + "：" + p[2];
    });
  });

  let lx = pad.l;
  series.forEach(s => {
    el("rect", {x: lx, y: 12, width: 10, height: 10, fill: s.color, rx: 2}, svg);
    const t = el("text", {x: lx + 14, y: 21, fill: "#374151", "font-size": 11}, svg);
    t.textContent = s.name;
    lx += 22 + s.name.length * 12;
  });
  if (unit){
    el("text", {x: w - pad.r, y: 21, "text-anchor": "end", fill: "#9ca3af", "font-size": 11}, svg).textContent = unit;
  }
}
function render(){
  if (!latest) return;
  const d = latest;
  const badge = document.getElementById("stateBadge");
  badge.textContent = d.state;
  badge.className = "badge " + (d.state === "训练中" ? "live" : "done");

  const total = d.total_epochs || 0, done = d.completed_epochs || 0;
  document.getElementById("epochs").textContent = done + " / " + total;
  document.getElementById("epochsSub").textContent = "已完成 " + done + " 轮";
  document.getElementById("best").textContent = d.best_mae === null || d.best_mae === undefined ? "-" : Number(d.best_mae).toFixed(2);
  document.getElementById("elapsed").textContent = fmtSec(d.elapsed_seconds);
  document.getElementById("avg").textContent = done ? "平均每轮 " + fmtSec(d.avg_epoch_seconds) : "";
  document.getElementById("remain").textContent = done < total ? fmtSec(d.remaining_seconds) : "-";

  const pct = (d.progress !== undefined ? d.progress : (total > 0 ? done / total : 0)) * 100;
  document.getElementById("barFill").style.width = pct.toFixed(1) + "%";
  const epochPct = Math.round((d.epoch_fraction || 0) * 100);
  document.getElementById("progressText").textContent = done + " / " + total + " 轮（" + pct.toFixed(0) + "%）" +
    (d.state === "训练中" ? " · 本轮按时间估算 " + epochPct + "%" : "");
  document.getElementById("updated").textContent = d.age_seconds === null ? "" : "最后写入 " + d.age_seconds + " 秒前";

  const h = d.history || [];
  const xs = h.map(x => x.epoch);
  chart("lossChart", [
    {name: "train_loss", color: COLORS[0], values: h.map(x => x.train_loss), raw: h.map(x => x.train_loss)},
    {name: "val_loss", color: COLORS[1], values: h.map(x => x.val_loss), raw: h.map(x => x.val_loss)}
  ], xs, "loss");
  chart("maeChart", DIMS.map(([key, name], i) => ({
    name: name, color: COLORS[i],
    values: h.map(x => x.per_dim_mae ? x.per_dim_mae[key] : null),
    raw: h.map(x => x.per_dim_mae ? x.per_dim_mae[key] : null)
  })), xs, "MAE（0–100）");

  const wrap = document.getElementById("tableWrap");
  if (!h.length){
    wrap.innerHTML = '<div class="empty">暂无数据</div>';
  } else {
    let html = "<table><thead><tr><th>轮</th><th>train_loss</th><th>val_loss</th><th>总 MAE</th>" +
      DIMS.map(x => "<th>" + x[1] + " MAE</th>").join("") + "<th>秒</th></tr></thead><tbody>";
    h.forEach((x, i) => {
      const cls = i === h.length - 1 ? ' class="last"' : "";
      html += "<tr" + cls + "><td>" + x.epoch + "</td><td>" + Number(x.train_loss).toFixed(4) +
        "</td><td>" + Number(x.val_loss).toFixed(4) + "</td><td>" + Number(x.val_mae).toFixed(2) + "</td>" +
        DIMS.map(([k]) => "<td>" + (x.per_dim_mae && x.per_dim_mae[k] !== undefined ? Number(x.per_dim_mae[k]).toFixed(2) : "-") + "</td>").join("") +
        "<td>" + Number(x.seconds).toFixed(1) + "</td></tr>";
    });
    wrap.innerHTML = html + "</tbody></table>";
  }

  const log = document.getElementById("log");
  log.textContent = (d.log_tail && d.log_tail.length) ? d.log_tail.join("\\n") : "暂无日志";
}
async function refresh(){
  try {
    const r = await fetch("/api/state", {cache: "no-store"});
    if (!r.ok) throw new Error(r.status);
    latest = await r.json();
    render();
    document.getElementById("conn").textContent = "页面更新于 " + new Date().toLocaleTimeString();
  } catch (e) {
    document.getElementById("conn").textContent = "连接不上监控服务，正在重试…";
  }
}
refresh();
setInterval(refresh, 3000);
window.addEventListener("resize", render);
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE


@app.get("/api/state")
def api_state():
    return JSONResponse(build_state())


def free_port(candidates=(8002, 8003)):
    for port in candidates:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return None


if __name__ == "__main__":
    port = free_port()
    if port is None:
        raise SystemExit("8002 和 8003 都被占用，请先释放端口。")
    print(f"监控页: http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
