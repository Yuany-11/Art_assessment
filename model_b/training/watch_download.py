"""实时查看 APDDv2 下载进度（方块进度条）。

用法（另开一个 VSCode 终端）：
    cd E:\\Lab_Files\\Project\\Art_assessment\\repo\\model_b\\training
    python watch_download.py

按 Ctrl+C 退出，不影响下载本身。
"""
import re
import sys
import tempfile
import time
from pathlib import Path

TASKS = Path(tempfile.gettempdir()) / "claude"
PAT = re.compile(r"([\d.]+)/([\d.]+) GB\s+([\d.]+)%.*?([\d.]+) MB/s.*?剩余\s+(\d+) 分钟")
WIDTH = 32


def find_output():
    files = sorted(TASKS.rglob("tasks/*.output"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files:
        try:
            if "GB" in p.read_text(encoding="utf-8", errors="replace"):
                return p
        except OSError:
            pass
    return None


def latest(path):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = None
    for m in PAT.finditer(text):
        pass
    return m


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else find_output()
    if not path:
        print("没找到下载日志，确认下载是否已启动")
        return
    print(f"日志: {path}")
    try:
        while True:
            m = latest(path)
            if m:
                done, total, pct, spd, eta = m.groups()
                filled = int(float(pct) / 100 * WIDTH)
                bar = "█" * filled + "░" * (WIDTH - filled)
                if float(done) >= float(total):
                    line = f"\r[{bar}] 100.0%  下载完成" + " " * 20
                else:
                    line = (f"\r[{bar}] {float(pct):5.1f}%  {done}/{total} GB  "
                            f"{spd} MB/s  剩余 {eta} 分钟" + " " * 6)
                print(line, end="", flush=True)
            else:
                print("\r等待下载数据…" + " " * 50, end="", flush=True)
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n已退出（下载不受影响）")


if __name__ == "__main__":
    main()
