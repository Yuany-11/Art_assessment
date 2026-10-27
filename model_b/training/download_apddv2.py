"""Google Drive 多线程分段下载（用于 APDDv2 等大文件）。

用法：
    python download_apddv2.py --id 1wnulfQouSP1Ts6uMd2VrOJJl9em0HJtE ^
        --out E:\\Lab_Files\\Project\\Art_assessment\\data\\05_apddv2\\APDDv2.zip --threads 8
"""
import argparse
import os
import sys
import threading
import time

import requests
from gdown.download import get_url_from_gdrive_confirmation

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def resolve_url(file_id):
    sess = requests.Session()
    sess.headers["User-Agent"] = UA
    r = sess.get(f"https://drive.google.com/uc?id={file_id}", stream=True, timeout=40)
    r.raise_for_status()
    if "Content-Disposition" in r.headers:
        return r.url, sess.cookies.get_dict()
    return get_url_from_gdrive_confirmation(r.text), sess.cookies.get_dict()


def probe(url, cookies):
    r = requests.get(url, headers={"Range": "bytes=0-0", "User-Agent": UA},
                     cookies=cookies, stream=True, timeout=40)
    cr = r.headers.get("Content-Range", "")
    print(f"探测: HTTP {r.status_code} Content-Range={cr or '(无)'}", flush=True)
    if r.status_code == 206 and "/" in cr:
        return int(cr.rsplit("/", 1)[1])
    cl = r.headers.get("Content-Length")
    return int(cl) if cl and r.status_code == 200 else None


def worker(idx, start, end, url, out, cookies, counters, lock, stop):
    sess = requests.Session()
    sess.headers["User-Agent"] = UA
    if cookies:
        sess.cookies.update(cookies)
    pos, attempt = start, 0
    while pos <= end and not stop.is_set():
        try:
            with sess.get(url, headers={"Range": f"bytes={pos}-{end}"},
                          stream=True, timeout=(30, 90)) as r:
                if r.status_code == 200 and pos > start:
                    raise RuntimeError("服务器忽略 Range，无法分段")
                if r.status_code not in (200, 206):
                    raise RuntimeError(f"HTTP {r.status_code}")
                with open(out, "r+b") as f:
                    f.seek(pos)
                    for chunk in r.iter_content(256 * 1024):
                        if stop.is_set():
                            return
                        if not chunk:
                            continue
                        f.write(chunk)
                        pos += len(chunk)
                        with lock:
                            counters[idx] = pos - start
                        if pos > end:
                            break
            attempt = 0
        except Exception as e:
            attempt += 1
            print(f"[线程{idx}] {e}，重试 {attempt}", flush=True)
            time.sleep(min(2 * attempt, 10))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--threads", type=int, default=8)
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)

    print("解析直链…", flush=True)
    url, cookies = resolve_url(args.id)
    print("直链已获取", flush=True)
    total = probe(url, cookies)
    if not total:
        raise SystemExit("拿不到文件大小，可能链接失效或需要授权")
    print(f"文件大小: {total/1e9:.2f} GB，开始 {args.threads} 线程下载", flush=True)

    with open(out, "wb") as f:
        f.truncate(total)

    n = args.threads
    step = total // n
    ranges = [(i * step, (total - 1 if i == n - 1 else (i + 1) * step - 1)) for i in range(n)]
    counters = [0] * n
    lock = threading.Lock()
    stop = threading.Event()
    threads = [threading.Thread(target=worker, args=(i, s, e, url, out, cookies, counters, lock, stop),
                                daemon=True)
               for i, (s, e) in enumerate(ranges)]
    for t in threads:
        t.start()

    last, t0 = 0, time.time()
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(1)
            with lock:
                done = sum(counters)
            speed = (done - last) / 1
            last = done
            eta = (total - done) / speed if speed > 0 else 0
            print(f"{done/1e9:5.2f}/{total/1e9:.2f} GB {done/total*100:5.1f}% "
                  f"{speed/1e6:5.2f} MB/s 剩余 {eta/60:4.0f} 分钟", flush=True)
    except KeyboardInterrupt:
        stop.set()
        print("已中断", flush=True)
        for t in threads:
            t.join(timeout=3)
        raise SystemExit(130)

    for t in threads:
        t.join()
    got = os.path.getsize(out)
    print(f"完成: {got/1e9:.2f} GB，用时 {(time.time()-t0)/60:.1f} 分钟", flush=True)
    if got != total:
        print(f"警告: 实际大小 {got} 与预期 {total} 不一致", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
