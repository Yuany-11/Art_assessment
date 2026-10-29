"""方法 3：用真人成对选择训练排序头，按图片留出，和 M0 对比。"""
from __future__ import annotations

import csv
import json
import random
import sys
import types
from collections import Counter
from pathlib import Path

import numpy as np

if "requests" not in sys.modules:
    try:
        import requests  # noqa: F401
    except Exception:
        stub = types.ModuleType("requests")

        class _Err(Exception):
            pass

        stub.Timeout = _Err
        stub.RequestException = _Err
        stub.get = lambda *a, **k: (_ for _ in ()).throw(_Err())
        sys.modules["requests"] = stub

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ROOT = REPO.parents[1]
sys.path.insert(0, str(REPO))

import torch
from PIL import Image
from torchvision import transforms

import model_runtime

PAIRS = ROOT / "logs" / "pairwise_v1" / "pairs.json"
VOTES = ROOT / "logs" / "pairwise_v1" / "votes.csv"
OUT = ROOT / "logs" / "pairwise_v1"
HEAD_OUT = ROOT / "weights" / "rank_human"
SEED = 42
N_SPLITS = 50
HOLD_FRAC = 0.3
L2 = 2e-3
ITERS = 500

NORM = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
TF = transforms.Compose([transforms.Resize(255), transforms.CenterCrop(224),
                         transforms.ToTensor(), NORM])


def load_data():
    pairs = json.loads(PAIRS.read_text(encoding="utf-8"))["pairs"]
    by_id = {p["pair_id"]: p for p in pairs}
    votes = list(csv.DictReader(open(VOTES, encoding="utf-8-sig")))
    uid_path = {}
    for p in pairs:
        for side in ("a", "b"):
            uid_path[p[side]["uid"]] = p[side]["path"]
    return votes, by_id, uid_path


def compute(uid_path):
    score_file = OUT / "m0_scores.json"
    feat_file = OUT / "features.npz"
    uids = sorted(uid_path)
    if score_file.exists() and feat_file.exists():
        scores = json.loads(score_file.read_text(encoding="utf-8"))
        z = np.load(feat_file, allow_pickle=True)
        if set(z["uids"].tolist()) == set(uids):
            return scores, {u: z["x"][i] for i, u in enumerate(z["uids"].tolist())}

    st = model_runtime._load()
    trunk, dev = st["trunk"], st["device"]
    scores, feats = {}, {}
    for i, u in enumerate(uids, 1):
        img = Image.open(uid_path[u]).convert("RGB")
        scores[u] = float(np.mean(list(model_runtime.predict(img)["scores"].values())))
        x = TF(img).unsqueeze(0).to(dev)
        with torch.no_grad():
            feats[u] = trunk(x).flatten(1).cpu().numpy()[0].astype(np.float32)
        if i % 50 == 0:
            print(f"scored {i}/{len(uids)}", flush=True)
    score_file.write_text(json.dumps(scores, ensure_ascii=False), encoding="utf-8")
    np.savez(feat_file, uids=np.array(uids), x=np.stack([feats[u] for u in uids]))
    return scores, feats


def pair_xy(v, by_id, feats, include_ties):
    p = by_id[v["pair_id"]]
    uid_a, uid_b = p["a"]["uid"], p["b"]["uid"]
    if v["winner"] == "a":
        y = 1.0
    elif v["winner"] == "b":
        y = 0.0
    elif v["winner"] == "same" and include_ties:
        y = 0.5
    else:
        return None
    x = feats[uid_a] - feats[uid_b]
    x = x / (np.linalg.norm(x) + 1e-6)
    return x, y, uid_a, uid_b


def fit(X, y, l2=L2, iters=ITERS, lr=0.5):
    w = np.zeros(X.shape[1], dtype=np.float32)
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(X @ w, -30, 30)))
        w -= lr * (X.T @ (p - y) / len(y) + l2 * w)
    return w


def acc_pair(w, feats, uid_a, uid_b):
    fa, fb = feats[uid_a], feats[uid_b]
    sa = float((fa / (np.linalg.norm(fa) + 1e-6)) @ w)
    sb = float((fb / (np.linalg.norm(fb) + 1e-6)) @ w)
    return 1.0 if sa > sb else 0.0 if sb > sa else 0.5


def main():
    votes, by_id, uid_path = load_data()
    scores, feats = compute(uid_path)

    decisive, ties, skips = [], [], []
    for v in votes:
        if v["winner"] in ("a", "b"):
            decisive.append(v)
        elif v["winner"] == "same":
            ties.append(v)
        else:
            skips.append(v)

    # M0 与真人选择的一致率
    m0_ok, diffs_dec, diffs_tie = 0.0, [], []
    for v in votes:
        p = by_id[v["pair_id"]]
        a, b = p["a"]["uid"], p["b"]["uid"]
        d = scores[a] - scores[b]
        if v["winner"] == "a":
            m0_ok += 1.0 if d > 0 else 0.5 if d == 0 else 0.0
            diffs_dec.append(abs(d))
        elif v["winner"] == "b":
            m0_ok += 1.0 if d < 0 else 0.5 if d == 0 else 0.0
            diffs_dec.append(abs(d))
        elif v["winner"] == "same":
            diffs_tie.append(abs(d))

    stats = {
        "votes": len(votes), "decisive": len(decisive), "same": len(ties), "skip": len(skips),
        "same_rate": round(len(ties) / max(len(votes), 1), 3),
        "m0_accuracy_decisive": round(m0_ok / max(len(decisive), 1), 4),
        "m0_absdiff_decisive": round(float(np.mean(diffs_dec)), 2),
        "m0_absdiff_same": round(float(np.mean(diffs_tie)), 2) if diffs_tie else None,
        "raters": dict(Counter(v["rater"] for v in votes)),
    }

    uids = np.array(sorted(uid_path))
    rng = random.Random(SEED)
    res = {"decisive_only": [], "with_ties": []}
    for mode in res:
        include_ties = mode == "with_ties"
        for _ in range(N_SPLITS):
            idx = list(uids)
            rng.shuffle(idx)
            hold = set(idx[: int(len(idx) * HOLD_FRAC)])
            tr, te = [], []
            for v in votes:
                rec = pair_xy(v, by_id, feats, include_ties)
                if rec is None:
                    continue
                _, _, ua, ub = rec
                if ua in hold and ub in hold:
                    te.append((v, ua, ub))
                elif ua not in hold and ub not in hold:
                    tr.append(rec)
            te_dec = [(v, ua, ub) for v, ua, ub in te if v["winner"] in ("a", "b")]
            if len(tr) < 20 or len(te_dec) < 10:
                continue
            X = np.stack([r[0] for r in tr])
            y = np.array([r[1] for r in tr], dtype=np.float32)
            w = fit(X, y)
            rk = np.mean([acc_pair(w, feats, ua, ub) for v, ua, ub in te_dec])
            m0 = np.mean([
                1.0 if (scores[ua] - scores[ub]) * (1 if v["winner"] == "a" else -1) > 0
                else 0.5 if scores[ua] == scores[ub] else 0.0
                for v, ua, ub in te_dec])
            res[mode].append((float(rk), float(m0), len(tr), len(te_dec)))

    report = {"stats": stats, "splits": {}}
    for mode, rows in res.items():
        if not rows:
            report["splits"][mode] = None
            continue
        rk = np.array([r[0] for r in rows])
        m0 = np.array([r[1] for r in rows])
        report["splits"][mode] = {
            "n_splits": len(rows),
            "rank_head": round(float(rk.mean()), 4),
            "rank_head_std": round(float(rk.std()), 4),
            "m0": round(float(m0.mean()), 4),
            "delta": round(float((rk - m0).mean()), 4),
            "win_rate_vs_m0": round(float(np.mean(rk > m0)), 3),
            "avg_train_pairs": int(np.mean([r[2] for r in rows])),
            "avg_test_pairs": int(np.mean([r[3] for r in rows])),
        }

    # 全量训练一个头，仅作试验产物，不接入
    all_pairs = [pair_xy(v, by_id, feats, True) for v in votes]
    all_pairs = [r for r in all_pairs if r is not None]
    X = np.stack([r[0] for r in all_pairs])
    y = np.array([r[1] for r in all_pairs], dtype=np.float32)
    w = fit(X, y)
    HEAD_OUT.mkdir(parents=True, exist_ok=True)
    np.savez(HEAD_OUT / "head.npz", w=w.astype(np.float32))
    (OUT / "metrics_human.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
