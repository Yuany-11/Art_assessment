"""严格评估人工排序头：图片级交叉验证、置换检验、外部专家集检查。"""
from __future__ import annotations

import csv
import json
import random
import sys
import types
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
from torchvision.models import resnet18

import model_runtime

PAIRS = ROOT / "logs" / "pairwise_v1" / "pairs.json"
VOTES = ROOT / "logs" / "pairwise_v1" / "votes.csv"
OUT = ROOT / "logs" / "pairwise_v1"
APDD_IMG = ROOT / "data" / "05_apddv2" / "images"
APDD_CSV = ROOT / "data" / "05_apddv2" / "APDDv2-10023.csv"
PENCILS = ROOT / "_downloads" / "Pencils_to_Pixels"
SEED = 42
ALPHAS = [0.0, 0.25, 0.5, 0.75, 1.0]
L2 = 2e-3
ITERS = 500
NORM = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
TF = transforms.Compose([transforms.Resize(255), transforms.CenterCrop(224),
                         transforms.ToTensor(), NORM])


def load_cached():
    pairs = json.loads(PAIRS.read_text(encoding="utf-8"))["pairs"]
    by_id = {p["pair_id"]: p for p in pairs}
    votes = list(csv.DictReader(open(VOTES, encoding="utf-8-sig")))
    scores = json.loads((OUT / "m0_scores.json").read_text(encoding="utf-8"))
    z = np.load(OUT / "features.npz", allow_pickle=True)
    feats = {u: z["x"][i] for i, u in enumerate(z["uids"].tolist())}
    return pairs, by_id, votes, scores, feats


def fit(X, y, l2=L2, iters=ITERS, lr=0.5):
    w = np.zeros(X.shape[1], dtype=np.float32)
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(X @ w, -30, 30)))
        w -= lr * (X.T @ (p - y) / len(y) + l2 * w)
    return w


def unit(f):
    return f / (np.linalg.norm(f) + 1e-6)


def pair_sample(vote, by_id, feats):
    p = by_id[vote["pair_id"]]
    ua, ub = p["a"]["uid"], p["b"]["uid"]
    y = 1.0 if vote["winner"] == "a" else 0.0 if vote["winner"] == "b" else None
    if y is None:
        return None
    return unit(feats[ua] - feats[ub]), y, ua, ub


def oof_eval(decisive, by_id, feats, scores, rng, n_folds=5, permute=False):
    """一次随机分折：返回每个 alpha 的 OOF 准确率和覆盖对数。"""
    uids = sorted({by_id[v["pair_id"]][s]["uid"] for v in decisive for s in ("a", "b")})
    rng.shuffle(uids)
    folds = [set(uids[i::n_folds]) for i in range(n_folds)]
    per_alpha = {a: [0.0, 0] for a in ALPHAS}
    covered = 0
    for hold in folds:
        tr, te = [], []
        for v in decisive:
            s = pair_sample(v, by_id, feats)
            if s is None:
                continue
            _, y, ua, ub = s
            if ua in hold and ub in hold:
                te.append((s[0], y, ua, ub, v))
            elif ua not in hold and ub not in hold:
                tr.append(s)
        if len(tr) < 30 or not te:
            continue
        X = np.stack([t[0] for t in tr])
        y = np.array([t[1] for t in tr], dtype=np.float32)
        if permute:
            y = y.copy()
            rng.shuffle(y)
        w = fit(X, y)

        train_uids = sorted({t[2] for t in tr} | {t[3] for t in tr})
        rs = np.array([float(unit(feats[u]) @ w) for u in train_uids])
        ms = np.array([scores[u] for u in train_uids])
        rs_mu, rs_sd = float(rs.mean()), float(rs.std() + 1e-6)
        ms_mu, ms_sd = float(ms.mean()), float(ms.std() + 1e-6)

        for x, yv, ua, ub, v in te:
            zr = (float(unit(feats[ua]) @ w) - rs_mu) / rs_sd
            zb = (float(unit(feats[ub]) @ w) - rs_mu) / rs_sd
            zm_a = (scores[ua] - ms_mu) / ms_sd
            zm_b = (scores[ub] - ms_mu) / ms_sd
            sign = 1.0 if v["winner"] == "a" else -1.0
            for a in ALPHAS:
                d = (1 - a) * (zm_a - zm_b) + a * (zr - zb)
                per_alpha[a][0] += 1.0 if d * sign > 0 else 0.5 if d == 0 else 0.0
                per_alpha[a][1] += 1
            covered += 1
    return {a: (per_alpha[a][0] / per_alpha[a][1] if per_alpha[a][1] else None,
                per_alpha[a][1]) for a in ALPHAS}, covered


def compute_external(paths):
    st = model_runtime._load()
    trunk, dev = st["trunk"], st["device"]
    out = {}
    for p in paths:
        img = Image.open(p).convert("RGB")
        s = float(np.mean(list(model_runtime.predict(img)["scores"].values())))
        x = TF(img).unsqueeze(0).to(dev)
        with torch.no_grad():
            f = trunk(x).flatten(1).cpu().numpy()[0].astype(np.float32)
        out[str(p)] = {"score": s, "feat": f}
    return out


def external_sets():
    rows = list(csv.DictReader(open(PENCILS / "csvs/all_product.csv", encoding="utf-8-sig")))
    ad = sorted([PENCILS / "csvs" / r["filepath"] for r in rows if r["creator"] == "adults"])
    ch = sorted([PENCILS / "csvs" / r["filepath"] for r in rows if r["creator"] == "children"])
    ad = [p for p in ad if p.exists()][:40]
    ch = [p for p in ch if p.exists()][:40]
    hi, lo = [], []
    for r in csv.DictReader(open(APDD_CSV, encoding="gbk", errors="ignore")):
        p = APDD_IMG / r["filename"]
        if not p.exists():
            continue
        try:
            t = float(r["Total aesthetic score"])
        except (TypeError, ValueError):
            continue
        if t >= 80 and len(hi) < 40:
            hi.append(p)
        elif t < 50 and len(lo) < 40:
            lo.append(p)
    return {"adult": ad, "child": ch, "apdd_high": hi, "apdd_low": lo}


def main():
    pairs, by_id, votes, scores, feats = load_cached()
    decisive = [v for v in votes if v["winner"] in ("a", "b")]
    same = [v for v in votes if v["winner"] == "same"]
    rng = random.Random(SEED)

    partitions = 10
    agg = {a: [] for a in ALPHAS}
    cover = []
    for _ in range(partitions):
        res, cov = oof_eval(decisive, by_id, feats, scores, rng)
        for a, (acc, n) in res.items():
            if acc is not None:
                agg[a].append(acc)
        cover.append(cov)

    rngp = random.Random(SEED + 1)
    null = {a: [] for a in ALPHAS}
    for _ in range(20):
        res, _ = oof_eval(decisive, by_id, feats, scores, rngp, permute=True)
        for a, (acc, n) in res.items():
            if acc is not None:
                null[a].append(acc)

    report = {
        "votes": len(votes), "decisive": len(decisive), "same": len(same),
        "same_rate": round(len(same) / len(votes), 3),
        "cv": {}, "null": {}, "covered_pairs_mean": round(float(np.mean(cover)), 1),
    }
    for a in ALPHAS:
        if agg[a]:
            arr = np.array(agg[a])
            nul = np.array(null[a]) if null[a] else np.array([0.5])
            report["cv"][str(a)] = {
                "mean": round(float(arr.mean()), 4),
                "std": round(float(arr.std()), 4),
                "min": round(float(arr.min()), 4),
                "max": round(float(arr.max()), 4),
                "above_null_p95": bool(arr.mean() > np.percentile(nul, 95)),
            }
            report["null"][str(a)] = {
                "mean": round(float(nul.mean()), 4),
                "p95": round(float(np.percentile(nul, 95)), 4),
            }

    # 全量头（用所有明确选择训练）
    tr = [pair_sample(v, by_id, feats) for v in decisive]
    tr = [t for t in tr if t is not None]
    X = np.stack([t[0] for t in tr])
    y = np.array([t[1] for t in tr], dtype=np.float32)
    w = fit(X, y)
    all_uids = sorted({t[2] for t in tr} | {t[3] for t in tr})
    rs = np.array([float(unit(feats[u]) @ w) for u in all_uids])
    ms = np.array([scores[u] for u in all_uids])
    rs_mu, rs_sd = float(rs.mean()), float(rs.std() + 1e-6)
    ms_mu, ms_sd = float(ms.mean()), float(ms.std() + 1e-6)

    ext_paths = external_sets()
    ext = {}
    need = {str(p) for v in ext_paths.values() for p in v if str(p) not in scores}
    if need:
        got = compute_external(sorted(need))
        ext.update(got)

    def ext_acc(pos, neg, alpha):
        vals = []
        for pa in pos:
            for pb in neg:
                a = ext.get(str(pa)) or {"score": scores.get(str(pa)),
                                          "feat": feats.get(str(pa))}
                b = ext.get(str(pb)) or {"score": scores.get(str(pb)),
                                          "feat": feats.get(str(pb))}
                if a["score"] is None or b["score"] is None:
                    continue
                zr = ((float(unit(a["feat"]) @ w) - rs_mu) / rs_sd
                      - (float(unit(b["feat"]) @ w) - rs_mu) / rs_sd)
                zm = ((a["score"] - ms_mu) / ms_sd
                      - (b["score"] - ms_mu) / ms_sd)
                d = (1 - alpha) * zm + alpha * zr
                vals.append(1.0 if d > 0 else 0.5 if d == 0 else 0.0)
        return round(float(np.mean(vals)), 4) if vals else None

    report["external"] = {}
    for name, (pos, neg) in {
        "adult_gt_child": (ext_paths["adult"], ext_paths["child"]),
        "apdd_high_gt_low": (ext_paths["apdd_high"], ext_paths["apdd_low"]),
    }.items():
        report["external"][name] = {
            str(a): ext_acc(pos, neg, a) for a in ALPHAS
        }

    (OUT / "metrics_human_strict.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
