"""训练进度本地监测页：读 logs/<run>/train_log.txt，浏览器 10 秒自动刷新。

用法：
    python train_monitor.py --run exp_seed1_320 --port 8765
然后打开 http://127.0.0.1:8765
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EPOCH_RE = re.compile(
    r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] \[第 (\d+)/(\d+) 轮\] "
    r"train_loss=([\d.]+) val_loss=([\d.]+) val_MAE=构图=([\d.]+) 色彩=([\d.]+) "
    r"造型=([\d.]+) 创意=([\d.]+) 整体=([\d.]+) 用时=([\d.]+)s(\s\*)?"
)
REF = {"seed1@224 测试": 7.092, "2-seed 集成": 6.812}

ARGS = None


def read_epochs(run):
    log = ROOT / "logs" / run / "train_log.txt"
    if not log.exists():
        return [], None
    rows, full = [], 0
    for line in log.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = EPOCH_RE.search(line)
        if not m:
            continue
        ts, ep, total, tl, vl, c1, c2, c3, c4, overall, secs, star = m.groups()
        rows.append({
            "time": ts, "epoch": int(ep), "total": int(total),
            "train_loss": float(tl), "val_loss": float(vl),
            "mae": [float(c1), float(c2), float(c3), float(c4)],
            "overall": float(overall), "seconds": float(secs), "best": bool(star),
        })
        full = int(total)
    return rows, full


def read_final(run):
    p = ROOT / "logs" / run / "history.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def gpu_text():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5).stdout.strip()
        if out:
            u, mu, mt, t = [x.strip() for x in out.split(",")]
            return f"GPU 利用率 {u}% | 显存 {mu}/{mt} MiB | {t}°C"
    except Exception:
        pass
    return "GPU 状态不可用"


def render(run):
    rows, total = read_epochs(run)
    final = read_final(run)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not rows:
        body = "<p class='muted'>还没有训练日志，等待第一轮……</p>"
        progress = ""
    else:
        total = total or rows[-1]["total"]
        done = rows[-1]["epoch"]
        best = min(rows, key=lambda r: r["overall"])
        avg = sum(r["seconds"] for r in rows) / len(rows)
        eta_min = avg * max(total - done, 0) / 60
        stalled = ""
        last = datetime.strptime(rows[-1]["time"], "%Y-%m-%d %H:%M:%S")
        if (datetime.now() - last).total_seconds() > max(avg * 2.5, 300):
            stalled = "<span class='warn'>⚠️ 已超过预期时间没有新轮次，可能已结束或卡住</span>"
        pct = done / total * 100
        progress = (
            f"<div class='bar'><div style='width:{pct:.1f}%'></div></div>"
            f"<p>第 <b>{done}</b>/{total} 轮 · 平均 {avg:.0f}s/轮 · "
            f"预计剩余 <b>{eta_min:.0f} 分钟</b> · 最好整体 MAE "
            f"<b>{best['overall']:.3f}</b>（第 {best['epoch']} 轮）{stalled}</p>"
        )
        trs = "".join(
            f"<tr class='{'best' if r is best else ''}'>"
            f"<td>{r['epoch']}</td><td>{r['train_loss']:.3f}</td><td>{r['val_loss']:.3f}</td>"
            + "".join(f"<td>{v:.2f}</td>" for v in r["mae"])
            + f"<td><b>{r['overall']:.3f}</b></td><td>{r['seconds']:.0f}s</td>"
            f"<td>{r['time'][11:]}</td></tr>"
            for r in rows
        )
        refs = " · ".join(f"{k} {v:.3f}" for k, v in REF.items())
        body = f"""
        {progress}
        <p class='muted'>参照：{refs}</p>
        <table>
          <tr><th>轮</th><th>train_loss</th><th>val_loss</th><th>构图</th><th>色彩</th>
              <th>造型</th><th>创意</th><th>整体</th><th>用时</th><th>完成时间</th></tr>
          {trs}
        </table>"""
    final_html = ""
    if final:
        dims = final.get("test_mae", {})
        final_html = (
            "<div class='card'><h2>测试集结果（只评估一次）</h2>"
            f"<p>整体 MAE <b style='font-size:28px'>{final['overall_mae']:.3f}</b> "
            f"vs 常数基线 {final['overall_baseline_mae']:.2f} · "
            f"最优轮次 {final['best_epoch']} · 总耗时 {final['seconds']/60:.1f} 分钟</p>"
            "<p>" + " · ".join(f"{k} {v:.3f}" for k, v in dims.items()) + "</p></div>"
        )
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="10">
<title>训练监测 · {run}</title>
<style>
body{{font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;background:#0f1115;color:#e6e6e6;margin:0;padding:28px}}
h1{{font-size:20px;margin:0 0 6px}} .muted{{color:#8b93a7;font-size:13px}}
.bar{{height:14px;background:#1e2430;border-radius:7px;overflow:hidden;margin:18px 0 8px}}
.bar div{{height:100%;background:linear-gradient(90deg,#3b82f6,#22c55e)}}
table{{border-collapse:collapse;margin-top:16px;width:100%;font-variant-numeric:tabular-nums}}
th,td{{padding:7px 10px;border-bottom:1px solid #1e2430;text-align:right;font-size:13px}}
th{{color:#8b93a7;font-weight:500}} td:first-child{{text-align:left}}
tr.best td{{background:#13251a;color:#7ee2a8}} .warn{{color:#fbbf24}}
.card{{background:#151a22;border:1px solid #1e2430;border-radius:10px;padding:14px 18px;margin-top:18px}}
</style></head><body>
<h1>训练监测 · {run}</h1>
<p class="muted">页面每 10 秒自动刷新 · 更新时间 {now} · {gpu_text()}</p>
{final_html}
{body}
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        html = render(ARGS.run).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def log_message(self, *a):
        pass


def main():
    global ARGS
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="exp_seed1_320")
    ap.add_argument("--port", type=int, default=8765)
    ARGS = ap.parse_args()
    print(f"监测页： http://127.0.0.1:{ARGS.port}  (run={ARGS.run})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", ARGS.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
