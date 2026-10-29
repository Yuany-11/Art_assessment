"""用人工档位微调学生域评分头（冻结 v4.0 主干），交叉验证后决定是否采用。

输入：logs/cn_mid_eval/human_votes.jsonl（人工 4 档）
做法：seed1+seed2 主干 1024 维特征 -> Ridge 回归到档位目标分 -> 阈值分档；
      5 折交叉验证，比较「原模型」与「微调头」的 Spearman / QWK / 档位准确率。
只有 CV 明显更好才保存头；否则只留报告。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "logs" / "cn_mid_eval"
VOTES = OUT / "human_votes.jsonl"
TARGET = {"fail": 50, "pass": 67, "good": 82, "excellent": 93}
ORDER = ["fail", "pass", "good", "excellent"]

sys.path.insert(0, str(HERE.parent))
import model_runtime  # noqa: E402


def level_of(x):
    return "excellent" if x >= 90 else "good" if x >= 75 else "pass" if x >= 60 else "fail"


def main():
    votes = {}
    for line in VOTES.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            votes[r["path"]] = r["level"]
    paths = [p for p in votes if Path(p).exists()]
    if len(paths) < 20:
        print(f"样本不足：{len(paths)} 条，至少 20 条再训")
        return
    print(f"样本 {len(paths)}")

    from sklearn.linear_model import Ridge
    from sklearn.metrics import cohen_kappa_score
    from scipy.stats import spearmanr

    st = model_runtime._load()
    tf, device = st["tf"], st["device"]
    feats, y, base = [], [], []
    with st["torch"].no_grad():
        for p in paths:
            x = tf(Image.open(p).convert("RGB")).unsqueeze(0).to(device)
            fs = [tr(x).flatten(1).cpu().numpy()[0] for tr in st["trunks"]]
            feats.append(np.concatenate(fs))
            y.append(TARGET[votes[p]])
            s = model_runtime.predict(Image.open(p).convert("RGB"))["scores"]
            base.append(float(np.mean(list(s.values()))))
    X = np.asarray(feats)
    y = np.asarray(y, dtype=float)
    base = np.asarray(base, dtype=float)
    y_lv = [votes[p] for p in paths]

    rng = np.random.RandomState(20261029)
    idx = rng.permutation(len(paths))
    folds = np.array_split(idx, 5)
    pred = np.zeros(len(paths))
    for f in folds:
        tr = np.setdiff1d(idx, f)
        m = Ridge(alpha=100.0).fit(X[tr], y[tr])
        pred[f] = m.predict(X[f])

    def report(name, raw):
        lv = [level_of(v) for v in raw]
        spr = spearmanr(raw, y).statistic
        qwk = cohen_kappa_score(y_lv, lv, weights="quadratic", labels=ORDER)
        acc = float(np.mean([a == b for a, b in zip(y_lv, lv)]))
        print(f"{name}: Spearman={spr:.3f} QWK={qwk:.3f} 档位准确率={acc:.3f}")
        return {"spearman": round(float(spr), 3), "qwk": round(float(qwk), 3),
                "level_acc": round(acc, 3)}

    res = {"n": len(paths), "baseline_v4": report("v4.0 原模型", base),
           "student_head_cv": report("微调头(5折CV)", pred)}

    # 全量训练一版头，仅当 CV 优于基线才保存
    better = res["student_head_cv"]["qwk"] > res["baseline_v4"]["qwk"] + 0.03
    res["adopted"] = better
    if better:
        from sklearn.linear_model import Ridge
        m = Ridge(alpha=100.0).fit(X, y)
        np.savez(OUT / "student_head.npz", coef=m.coef_, intercept=m.intercept_)
        print("已保存 student_head.npz")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "student_head_report.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", OUT / "student_head_report.json")


if __name__ == "__main__":
    main()
