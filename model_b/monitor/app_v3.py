"""模型B v3.0 微调实时监控页。

只读 logs/apddv2_ft/train_log.txt，不写任何文件，不碰训练进程。
启动：python app_v3.py   浏览器打开打印出的地址（8002 起，占用则顺延）。
"""
import os
import re
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(os.getenv("ART_ROOT", HERE.parents[2]))
LOG = Path(os.getenv("ART_LOG", ROOT / "logs" / "apddv2_ft" / "train_log.txt"))

EPOCH_RE = re.compile(
    r"\[第 (\d+)/(\d+) 轮\] train_loss=([\d.]+) val_loss=([\d.]+) "
    r"val_MAE=构图=([\d.]+) 色彩=([\d.]+) 造型=([\d.]+) 创意=([\d.]+) "
    r"整体=([\d.]+) 用时=([\d.]+)s\s*(\*?)"
)
TS_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")

DIM_NAMES = ("构图", "色彩", "造型", "创意")
DIM_COLORS = ("#2563eb", "#dc2626", "#16a34a", "#d97706")
ACCEPT_MAE = 8.5


def read_log():
    if not LOG.exists():
        return "", 0.0
    text = LOG.read_text(encoding="utf-8", errors="replace")
    age = datetime.now().timestamp() - LOG.stat().st_mtime
    return text, age


def parse(text):
    epochs, total, start = [], 20, None
    for line in text.splitlines():
        m = EPOCH_RE.search(line)
        if m:
            g = m.groups()
            epochs.append({
                "epoch": int(g[0]), "total": int(g[1]),
                "train_loss": float(g[2]), "val_loss": float(g[3]),
                "mae": [float(g[4]), float(g[5]), float(g[6]), float(g[7])],
                "overall": float(g[8]), "seconds": float(g[9]),
                "best": bool(g[10]),
            })
            total = int(g[1])
            continue
        if start is None:
            t = TS_RE.match(line)
            if t:
                start = datetime.strptime(t.group(1), "%Y-%m-%d %H:%M:%S")
        if "epochs=" in line and "config" in line:
            mm = re.search(r"epochs=(\d+)", line)
            if mm:
                total = int(mm.group(1))
    return epochs, total, start


def status_of(text, age, epochs):
    last = text.strip().splitlines()[-1] if text.strip() else ""
    if "早停" in last or "完成：" in last:
        return "已结束"
    if "[测试]" in last:
        return "测试中"
    if epochs and age < 180:
        return "训练中"
    if epochs:
        return "已结束（无新日志）"
    return "等待开始"


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def svg_line_chart(title, series, ref=None, w=680, h=250):
    """series: [(name, color, values, dashed)]"""
    pad_l, pad_r, pad_t, pad_b = 52, 16, 34, 30
    vals = [v for _, _, vs, _ in series for v in vs if v is not None]
    if not vals:
        return f'<div class="empty">{esc(title)}：暂无数据</div>'
    lo, hi = min(vals), max(vals)
    if ref:
        lo, hi = min(lo, ref), max(hi, ref)
    span = hi - lo or 1.0
    lo -= span * 0.08
    hi += span * 0.08
    n = max(1, len(series[0][2]))

    def xy(i, v):
        x = pad_l + (i * (w - pad_l - pad_r) / max(n - 1, 1))
        y = pad_t + (hi - v) * (h - pad_t - pad_b) / (hi - lo)
        return x, y

    parts = [f'<svg viewBox="0 0 {w} {h}" role="img">']
    parts.append(f'<text x="{pad_l}" y="18" class="ct">{esc(title)}</text>')
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        _, y = xy(0, v)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{pad_l-6}" y="{y+4:.1f}" class="tick" text-anchor="end">{v:.1f}</text>')
    if ref is not None:
        _, y = xy(0, ref)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" class="ref"/>')
        parts.append(f'<text x="{w-pad_r}" y="{y-5:.1f}" class="tick" text-anchor="end">达标线 {ref}</text>')
    for name, color, vs, dashed in series:
        pts = []
        for i, v in enumerate(vs):
            if v is None:
                continue
            x, y = xy(i, v)
            pts.append(f"{x:.1f},{y:.1f}")
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        parts.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" '
                     f'stroke-width="2"{dash}/>')
        last = next(((i, v) for i, v in reversed(list(enumerate(vs))) if v is not None), None)
        if last:
            x, y = xy(*last)
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>')
    lx = pad_l
    for name, color, _, _ in series:
        parts.append(f'<rect x="{lx}" y="{h-16}" width="10" height="3" fill="{color}"/>')
        parts.append(f'<text x="{lx+14}" y="{h-10}" class="tick">{esc(name)}</text>')
        lx += 22 + len(name) * 13
    parts.append("</svg>")
    return "".join(parts)


def render():
    text, age = read_log()
    epochs, total, start = parse(text)
    status = status_of(text, age, epochs)
    done = len(epochs)
    best = min(epochs, key=lambda e: e["overall"]) if epochs else None
    avg_s = (sum(e["seconds"] for e in epochs) / done) if done else 0.0

    now = datetime.now()
    elapsed = 0.0
    if start:
        elapsed = max(0.0, (now - start).total_seconds())
    elif epochs:
        elapsed = sum(e["seconds"] for e in epochs)

    frac = 0.0
    if status == "训练中" and done:
        last_ts = None
        for line in reversed(text.splitlines()):
            t = TS_RE.match(line)
            if t:
                last_ts = datetime.strptime(t.group(1), "%Y-%m-%d %H:%M:%S")
                break
        if last_ts:
            frac = min(0.95, max(0.0, (now - last_ts).total_seconds() / max(avg_s, 1.0)))
    progress = min(1.0, (done + frac) / max(total, 1))
    remain = max(0.0, (total - done - frac) * avg_s)

    def mmss(s):
        s = int(max(s, 0))
        return f"{s // 60} 分 {s % 60} 秒"

    loss_chart = svg_line_chart(
        "loss 曲线",
        [("train_loss", "#2563eb", [e["train_loss"] for e in epochs], False),
         ("val_loss", "#dc2626", [e["val_loss"] for e in epochs], False)],
    )
    mae_series = [(DIM_NAMES[i], DIM_COLORS[i], [e["mae"][i] for e in epochs], False)
                  for i in range(4)]
    mae_series.append(("整体", "#6b7280", [e["overall"] for e in epochs], True))
    mae_chart = svg_line_chart("四维 val MAE 曲线（越低越好）", mae_series, ref=ACCEPT_MAE)

    rows = []
    for e in epochs:
        cls = ' class="best"' if best and e["epoch"] == best["epoch"] else ""
        rows.append(
            f"<tr{cls}><td>{e['epoch']}</td><td>{e['train_loss']:.3f}</td>"
            f"<td>{e['val_loss']:.3f}</td>"
            + "".join(f"<td>{v:.2f}</td>" for v in e["mae"])
            + f"<td><b>{e['overall']:.2f}</b></td><td>{e['seconds']:.1f}s</td>"
            f"<td>{'★' if e['best'] else ''}</td></tr>"
        )

    tail = [ln for ln in text.strip().splitlines() if ln][-8:]
    badge_cls = "run" if status == "训练中" else ("test" if status == "测试中" else "end")
    best_txt = f"{best['overall']:.2f}（第 {best['epoch']} 轮）" if best else "—"
    cur = epochs[-1] if epochs else None

    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="3">
<title>模型B 微调训练监控</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin:0; padding:20px 24px; background:#f5f7fa; color:#111827;
         font-family:"Microsoft YaHei","Segoe UI",sans-serif; }}
  h1 {{ font-size:20px; margin:0 0 4px; }}
  .sub {{ color:#6b7280; font-size:13px; margin-bottom:16px; }}
  .row {{ display:flex; gap:14px; flex-wrap:wrap; }}
  .card {{ background:#fff; border-radius:10px; padding:14px 18px; flex:1 1 180px;
           box-shadow:0 1px 3px rgba(0,0,0,.07); }}
  .k {{ color:#6b7280; font-size:12px; }}
  .v {{ font-size:22px; font-weight:700; margin-top:4px; }}
  .badge {{ display:inline-block; padding:3px 12px; border-radius:999px;
            font-size:13px; font-weight:600; }}
  .badge.run {{ background:#dcfce7; color:#166534; }}
  .badge.run::before {{ content:"●"; margin-right:6px; color:#16a34a;
                        animation:blink 1.2s infinite; }}
  .badge.test {{ background:#fef3c7; color:#92400e; }}
  .badge.end {{ background:#e5e7eb; color:#374151; }}
  @keyframes blink {{ 50% {{ opacity:.25; }} }}
  .bar {{ height:14px; background:#e5e7eb; border-radius:7px; overflow:hidden; }}
  .bar > i {{ display:block; height:100%; width:{progress*100:.1f}%;
              background:linear-gradient(90deg,#3b82f6,#22c55e); }}
  .chart {{ background:#fff; border-radius:10px; padding:10px; flex:1 1 460px;
            box-shadow:0 1px 3px rgba(0,0,0,.07); }}
  svg {{ width:100%; height:auto; display:block; }}
  .grid {{ stroke:#eef1f5; stroke-width:1; }}
  .ref {{ stroke:#f59e0b; stroke-width:1; stroke-dasharray:5 4; }}
  .tick {{ fill:#6b7280; font-size:11px; }}
  .ct {{ fill:#111827; font-size:13px; font-weight:600; }}
  table {{ width:100%; border-collapse:collapse; background:#fff; border-radius:10px;
           overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,.07); margin-top:14px; }}
  th, td {{ padding:7px 10px; font-size:13px; text-align:right; }}
  th {{ background:#f1f5f9; color:#475569; font-weight:600; }}
  td:first-child, th:first-child {{ text-align:center; }}
  tr.best td {{ background:#f0fdf4; }}
  tr + tr td {{ border-top:1px solid #f1f5f9; }}
  .log {{ background:#0f172a; color:#cbd5e1; border-radius:10px; padding:12px 14px;
          font:12px/1.7 Consolas,monospace; white-space:pre-wrap; margin-top:14px; }}
  .note {{ color:#9ca3af; font-size:12px; margin-top:10px; }}
  .empty {{ color:#9ca3af; padding:40px 10px; text-align:center; }}
</style></head><body>
<h1>模型B · APDDv2 四维评分微调</h1>
<div class="sub">art-cnn-apddv2-v3.0 · ResNet18 全参数微调 · 只读 {esc(str(LOG))} · 每 3 秒刷新</div>

<div class="row">
  <div class="card"><div class="k">状态</div><div class="v"><span class="badge {badge_cls}">{status}</span></div></div>
  <div class="card"><div class="k">进度</div><div class="v">{done} / {total} 轮</div>
    <div class="bar" style="margin-top:8px"><i></i></div>
    <div class="k" style="margin-top:6px">{'本轮按时间估算' if status=='训练中' else '已完成轮次占比'}</div></div>
  <div class="card"><div class="k">最佳整体 val MAE</div><div class="v">{best_txt}</div></div>
  <div class="card"><div class="k">累计耗时</div><div class="v">{mmss(elapsed)}</div>
    <div class="k" style="margin-top:6px">预计剩余 {'—' if status!='训练中' else mmss(remain)}</div></div>
</div>

<div class="row" style="margin-top:14px">
  <div class="chart">{loss_chart}</div>
  <div class="chart">{mae_chart}</div>
</div>

<table>
<thead><tr><th>轮</th><th>train_loss</th><th>val_loss</th><th>构图</th><th>色彩</th>
<th>造型</th><th>创意</th><th>整体</th><th>用时</th><th>最佳</th></tr></thead>
<tbody>{''.join(rows) if rows else '<tr><td colspan="10" style="text-align:center;color:#9ca3af">等待第一轮结果…</td></tr>'}</tbody>
</table>

<div class="log">{esc(chr(10).join(tail)) if tail else '尚无日志'}</div>
<div class="note">旧版监控页（v1/v2）不变；本页只读取 v3 的 train_log.txt，不修改训练脚本、不写文件。
{'当前第 ' + str(cur['epoch']) + ' 轮结果：train_loss=' + f"{cur['train_loss']:.3f}" if cur else ''}</div>
</body></html>"""
    return html


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = render().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    srv = None
    for port in range(8002, 8010):
        try:
            srv = HTTPServer(("127.0.0.1", port), Handler)
            print(f"监控页已启动: http://127.0.0.1:{port}/", flush=True)
            break
        except OSError:
            continue
    if srv is None:
        print("8002-8009 端口都被占用，无法启动", flush=True)
        sys.exit(1)
    srv.serve_forever()


if __name__ == "__main__":
    main()
