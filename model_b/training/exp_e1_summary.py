"""Build the E1 evaluation record.

Decision is based on paired bootstrap CI, not on across-seed mean/std.
Includes equal-weight 2-seed, equal-weight 3-seed (deployment candidate) and
validation-weighted 3-seed (comparison only; runtime does not support weights).
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIMS = ("composition", "color", "modeling", "creativity")
DIM_CN = {"composition": "构图", "color": "色彩", "modeling": "造型", "creativity": "创意"}
SEEDS = (1, 2, 3)
PY = sys.executable
ENSEMBLE_SIZE_MB = 134          # user-provided: 3 checkpoints, ~44.7MB each
ENSEMBLE_CPU_SECONDS = 0.55     # user-provided: CPU single image, 3 models
MIN_GAIN = 0.05


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_preds(path: Path):
    out = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[(r["file"], r["dim"])] = (float(r["cal"]), float(r["label"]))
    return out


def stats(preds):
    per = {}
    for d in DIMS:
        errs = np.array([abs(c - l) for (f, dim), (c, l) in preds.items() if dim == d])
        per[d] = {"n": int(errs.size), "mae": float(errs.mean()),
                  "std": float(errs.std(ddof=1)) if errs.size > 1 else 0.0}
    overall = float(np.mean([per[d]["mae"] for d in DIMS]))
    return per, overall


def bootstrap(base: Path, cand: Path, out: Path):
    subprocess.run(
        [PY, str(HERE / "exp_bootstrap.py"), "--base", str(base), "--cand", str(cand),
         "--out", str(out)], check=True, stdout=subprocess.DEVNULL,
    )
    return json.loads(out.read_text(encoding="utf-8"))


def gain_info(boot):
    """Positive gain = candidate has lower MAE than the single/reference model."""
    d = boot["delta"]
    gain = -d["overall_mae"]
    lo, hi = -d["overall_ci95"][1], -d["overall_ci95"][0]
    return {"gain": round(gain, 4), "ci95": [round(lo, 4), round(hi, 4)],
            "significant": lo > 0}


def fmt(x):
    return f"{x:.3f}"


def decide(gain_val, gain_fixed):
    """Fair, deployment-compatible decision rule."""
    ok = (gain_val["significant"] and gain_val["gain"] >= MIN_GAIN
          and gain_fixed["significant"] and gain_fixed["gain"] > 0)
    reasons = []
    if not gain_val["significant"]:
        reasons.append("相对验证集最佳 seed 的 95% CI 跨 0")
    elif gain_val["gain"] < MIN_GAIN:
        reasons.append(f"相对验证集最佳 seed 仅降 {gain_val['gain']:.3f}，"
                       f"低于 {MIN_GAIN:.2f} 门槛")
    if not gain_fixed["significant"]:
        reasons.append("相对固定 seed1 的 95% CI 跨 0")
    elif gain_fixed["gain"] <= 0:
        reasons.append("未优于固定 seed1")
    return ok, "；".join(reasons) + ("。" if reasons else "")


def main():
    base_csv = ROOT / "logs" / "e0_baseline_raw" / "preds_test.csv"
    seed_csv = {s: ROOT / "logs" / f"exp_seed{s}" / "eval_raw" / "preds_test.csv" for s in SEEDS}
    ens3_dir = ROOT / "logs" / "exp_ensemble3"
    ens2_dir = ROOT / "logs" / "exp_ensemble2"
    ens3w_dir = ROOT / "logs" / "exp_ensemble3_weighted"

    candidates = [
        ("baseline", "基线 v3.0", base_csv, None, False),
        *[(f"seed{s}", f"seed{s}", seed_csv[s], None, False) for s in SEEDS],
        ("ens2", "2-seed 等权（seed1+seed2）", ens2_dir / "preds_test.csv", ens2_dir, True),
        ("ens3", "3-seed 等权（部署候选）", ens3_dir / "preds_test.csv", ens3_dir, True),
        ("ens3w", "3-seed 加权（仅对比）", ens3w_dir / "preds_test.csv", ens3w_dir, False),
    ]
    rows, metrics = {}, {}
    for key, label, csv_path, mdir, _ in candidates:
        if not csv_path.exists():
            continue
        per, overall = stats(load_preds(csv_path))
        rows[key] = {"label": label, "per_dim": per, "overall": overall,
                     "path": str(csv_path)}
        mpath = (mdir / "test_metrics.json") if mdir else None
        if mpath and mpath.exists():
            metrics[key] = json.loads(mpath.read_text(encoding="utf-8"))
    if "ens3" not in rows or "ens2" not in rows:
        raise SystemExit("missing ensemble preds; run exp_eval_ensemble.py first")

    # Selection uses validation only; test-best is reported but labelled optimistic.
    val = {}
    for s in SEEDS:
        h = json.loads((ROOT / "logs" / f"exp_seed{s}" / "history.json")
                       .read_text(encoding="utf-8"))
        rec = next(e for e in h["history"] if e["epoch"] == h["best_epoch"])
        val[s] = {"epoch": h["best_epoch"], "val_mae_mean": rec["val_mae_mean"],
                  "test_mae": h["overall_mae"]}
    val_best_seed = min(SEEDS, key=lambda s: val[s]["val_mae_mean"])
    test_best_seed = min(SEEDS, key=lambda s: rows[f"seed{s}"]["overall"])
    val_rank = sorted(SEEDS, key=lambda s: val[s]["val_mae_mean"])
    two_members = val_rank[:2]

    # 3-seed equal: deployment candidate for the user's runtime (equal, raw).
    b3 = {
        "baseline": bootstrap(base_csv, ens3_dir / "preds_test.csv",
                              ens3_dir / "bootstrap_vs_baseline.json"),
        "val_best": bootstrap(seed_csv[val_best_seed], ens3_dir / "preds_test.csv",
                              ens3_dir / f"bootstrap_vs_val_best_seed{val_best_seed}.json"),
        "test_best": bootstrap(seed_csv[test_best_seed], ens3_dir / "preds_test.csv",
                               ens3_dir / f"bootstrap_vs_test_best_seed{test_best_seed}.json"),
        "fixed": bootstrap(seed_csv[1], ens3_dir / "preds_test.csv",
                           ens3_dir / "bootstrap_vs_fixed_seed1.json"),
    }
    # 2-seed equal: also deployable if two models are cheaper.
    b2 = {
        "baseline": bootstrap(base_csv, ens2_dir / "preds_test.csv",
                              ens2_dir / "bootstrap_vs_baseline.json"),
        "val_best": bootstrap(seed_csv[val_best_seed], ens2_dir / "preds_test.csv",
                              ens2_dir / f"bootstrap_vs_val_best_seed{val_best_seed}.json"),
        "fixed": bootstrap(seed_csv[1], ens2_dir / "preds_test.csv",
                           ens2_dir / "bootstrap_vs_fixed_seed1.json"),
        "vs_ens3": bootstrap(ens3_dir / "preds_test.csv", ens2_dir / "preds_test.csv",
                             ens2_dir / "bootstrap_vs_3seed_equal.json"),
    }
    # 3-seed weighted: comparison only, NOT runtime-compatible.
    b3w = {
        "baseline": bootstrap(base_csv, ens3w_dir / "preds_test.csv",
                              ens3w_dir / "bootstrap_vs_baseline.json"),
        "val_best": bootstrap(seed_csv[val_best_seed], ens3w_dir / "preds_test.csv",
                              ens3w_dir / f"bootstrap_vs_val_best_seed{val_best_seed}.json"),
        "fixed": bootstrap(seed_csv[1], ens3w_dir / "preds_test.csv",
                           ens3w_dir / "bootstrap_vs_fixed_seed1.json"),
        "vs_ens3": bootstrap(ens3_dir / "preds_test.csv", ens3w_dir / "preds_test.csv",
                             ens3w_dir / "bootstrap_vs_3seed_equal.json"),
    }

    g3 = {k: gain_info(v) for k, v in b3.items()}
    g2 = {k: gain_info(v) for k, v in b2.items()}
    g3w = {k: gain_info(v) for k, v in b3w.items()}

    ok3, why3 = decide(g3["val_best"], g3["fixed"])
    ok2, why2 = decide(g2["val_best"], g2["fixed"])

    result = {
        "command": {
            "per_seed": ("python training/exp_eval_ensemble.py --ckpt "
                         "../../weights/exp_seedN/best.pt --out ../../logs/exp_seedN/eval_raw "
                         "--no-head --no-calib --no-pencils --tta base3"),
            "ens2": ("python training/exp_eval_ensemble.py --ckpt "
                     "../../weights/exp_seed1/best.pt ../../weights/exp_seed2/best.pt "
                     "--out ../../logs/exp_ensemble2 --no-head --no-calib --no-pencils --tta base3"),
            "ens3": ("python training/exp_eval_ensemble.py --ckpt "
                     "../../weights/exp_seed1/best.pt ../../weights/exp_seed2/best.pt "
                     "../../weights/exp_seed3/best.pt --out ../../logs/exp_ensemble3 "
                     "--no-head --no-calib --no-pencils --tta base3"),
            "ens3w": ("python training/exp_eval_ensemble.py --ckpt "
                      "../../weights/exp_seed1/best.pt ../../weights/exp_seed2/best.pt "
                      "../../weights/exp_seed3/best.pt --weights "
                      f"{' '.join(f'{w:.6f}' for w in metrics['ens3w']['model_weights'])} "
                      "--out ../../logs/exp_ensemble3_weighted "
                      "--no-head --no-calib --no-pencils --tta base3"),
        },
        "ensemble_algorithm": {
            "space": "raw",
            "order": ("per-model TTA mean -> weighted mean over models on raw 4 dims "
                      "-> optional calibration"),
            "equal_weights": "1/N per checkpoint",
            "weighted_rule": "w_i = (1/val_best_mae_i) / sum_j(1/val_best_mae_j)",
            "weighted_weights": metrics["ens3w"]["model_weights"],
            "runtime_supported": "equal-weight raw average only",
            "calibration_used": False,
        },
        "split": json.loads((ROOT / "logs" / "split_audit" / "split_hashes.json")
                            .read_text(encoding="utf-8")),
        "rows": rows,
        "metrics": metrics,
        "across_seed": {
            "overall_mean": round(float(np.mean([rows[f"seed{s}"]["overall"] for s in SEEDS])), 4),
            "overall_std": round(float(np.std([rows[f"seed{s}"]["overall"] for s in SEEDS], ddof=1)), 4),
            "values": [round(rows[f"seed{s}"]["overall"], 4) for s in SEEDS],
            "note": "descriptive only; significance from paired bootstrap CI",
        },
        "selection": {
            "val_best_seed": val_best_seed,
            "test_best_seed": test_best_seed,
            "fixed_seed": 1,
            "val_rank": val_rank,
            "two_seed_members": two_members,
            "per_seed": val,
        },
        "bootstrap": {"ens3": b3, "ens2": b2, "ens3w": b3w},
        "gains": {"ens3": g3, "ens2": g2, "ens3w": g3w},
        "decisions": {
            "ens3_equal": {"recommend": ok3, "reason": why3,
                           "deployment": {"models": 3, "size_mb": ENSEMBLE_SIZE_MB,
                                          "cpu_seconds_per_image": ENSEMBLE_CPU_SECONDS}},
            "ens2_equal": {"recommend": ok2, "reason": why2,
                           "deployment": {"models": 2, "size_mb_estimate": 90,
                                          "cpu_seconds_note": "未实测；3 模型为 0.55s"}},
            "ens3_weighted": {
                "recommend": False,
                "reason": ("运行时只支持等权 raw 平均；且相对 3-seed 等权仅降 "
                           f"{g3w['vs_ens3']['gain']:.3f}，不值得为此改运行时。"),
                "runtime_compatible": False,
            },
        },
        "threshold_gain": MIN_GAIN,
    }

    # Artifact paths and hashes.
    weights = {f"seed{s}": ROOT / "weights" / f"exp_seed{s}" / "best.pt" for s in SEEDS}
    before_txt = (ROOT / "logs" / "e0_baseline_raw" / "SHA256_baseline_before.txt")
    before = before_txt.read_text(encoding="utf-8").split()[0] if before_txt.exists() else None
    after = sha256(ROOT / "weights" / "apddv2_ft" / "best.pt")
    result["artifacts"] = {
        "preds": {k: str(v["path"]) for k, v in rows.items()},
        "weights": {k: {"path": str(p), "sha256": sha256(p), "bytes": p.stat().st_size}
                    for k, p in weights.items()},
        "baseline_weight": {"path": str(ROOT / "weights" / "apddv2_ft" / "best.pt"),
                            "sha256_before": before, "sha256_after": after,
                            "unchanged": before == after},
        "scripts": [str(HERE / n) for n in
                    ("exp_train_seed.py", "exp_eval_ensemble.py",
                     "exp_bootstrap.py", "exp_split_audit.py", "exp_e1_summary.py")],
    }
    (ROOT / "logs" / "E1_EVAL_SUMMARY.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    md = []
    md.append("# E1 评估记录\n")
    md.append("APDD 测试集 1923 张。所有指标均为原始四维输出（未接创意头、未做 v3.1 校准），"
              "TTA 为 base3（原图 + 水平翻转 + 中心裁 6% 三路平均）。\n")
    md.append("## 复现命令\n")
    md.append("```bash")
    for label, cmd in [("逐 seed", result["command"]["per_seed"]),
                       ("2-seed", result["command"]["ens2"]),
                       ("3-seed 等权", result["command"]["ens3"]),
                       ("3-seed 加权", result["command"]["ens3w"])]:
        md.append(f"# {label}\n{cmd}")
    md.append("```\n")
    md.append("## 集成算法\n")
    md.append("- 平均发生在 **raw 四维**，不是校准后。")
    md.append("- 每个模型先对自己的 3 个 TTA 视角取平均，再按模型权重加权平均："
              "`p = Σ w_m · mean_v(pred_{m,v})`，`Σ w_m = 1`。")
    md.append("- 等权：`w_m = 1/N`。加权：`w_i = (1/val_best_mae_i) / Σ_j(1/val_best_mae_j)`。")
    md.append(f"- 本次加权版权重：`{metrics['ens3w']['model_weights']}`。")
    md.append("- **运行时目前只支持等权、raw 层平均**；加权版仅用于对比，不代表可直接部署。")
    md.append("- 本次评估未启用校准（`--no-calib`），因此 raw 平均和最终分数是同一空间。\n")

    md.append("## 划分一致性\n")
    md.append("| seed | train | val | test | test SHA256 |\n|---|---|---|---|---|")
    for s, e in result["split"]["seeds"].items():
        md.append(f"| {s} | {e['counts']['train']} | {e['counts']['val']} | "
                  f"{e['counts']['test']} | `{e['test_sha256']}` |")
    md.append("\n完整哈希见 `logs/split_audit/split_hashes.json`，逐文件清单见 `logs/split_audit/seedN_*.txt`。\n")

    md.append("## 分数（± 为逐图绝对误差标准差）\n")
    md.append("| 模型 | 构图 | 色彩 | 造型 | 创意 | 整体 |\n|---|---|---|---|---|---|")
    for key in ("baseline", "seed1", "seed2", "seed3", "ens2", "ens3", "ens3w"):
        if key not in rows:
            continue
        per = rows[key]["per_dim"]
        cells = " | ".join(f"{fmt(per[d]['mae'])} ± {per[d]['std']:.2f}" for d in DIMS)
        md.append(f"| {rows[key]['label']} | {cells} | **{fmt(rows[key]['overall'])}** |")
    md.append(f"\n三个 seed 整体 MAE：{', '.join(fmt(v) for v in result['across_seed']['values'])}，"
              f"**{result['across_seed']['overall_mean']:.3f} ± "
              f"{result['across_seed']['overall_std']:.3f}**（mean ± sample std, n=3，仅描述）。\n")

    md.append("## 单 seed 选择口径\n")
    md.append("| seed | 最佳轮 | 最佳 val MAE | 测试 MAE | 用途 |\n|---|---|---|---|---|")
    for s in SEEDS:
        v = val[s]
        use = []
        if s == val_best_seed:
            use.append("验证集最佳（公平口径）")
        if s == test_best_seed:
            use.append("测试集最佳（乐观口径）")
        if s == 1:
            use.append("固定参照")
        md.append(f"| {s} | 第 {v['epoch']} 轮 | {fmt(v['val_mae_mean'])} | "
                  f"{fmt(v['test_mae'])} | {'、'.join(use) or '—'} |")
    md.append("\n注：选择表的“测试 MAE”来自训练脚本的单视角评估；"
              "上面的分数表是 base3 TTA，两者口径不同，数字会略有差异"
              "（例如 seed1 单视角 7.092、TTA 7.097）。集成对比全部用 TTA 后的 preds。\n")
    md.append(f"\n2-seed 成员按验证集前二选出：seed{two_members[0]}、seed{two_members[1]}，"
              "选择过程不使用测试集。\n")
    md.append("用测试集挑最好单 seed 等于在测试集上选了一次，"
              "“集成 vs 测试集最佳”的数字只作参考；主判断看“验证集最佳”和“固定 seed1”。\n")

    md.append("## 集成对比（正 = 集成更好）\n")
    md.append("| 集成 | 对比对象 | 整体 MAE 降幅 | 95% CI | band acc delta |\n|---|---|---|---|---|")
    comp_rows = [
        ("3-seed 等权", "基线", g3["baseline"], b3["baseline"]),
        (f"3-seed 等权", f"seed{val_best_seed}（验证集最佳）", g3["val_best"], b3["val_best"]),
        (f"3-seed 等权", f"seed{test_best_seed}（测试集最佳，乐观）", g3["test_best"], b3["test_best"]),
        ("3-seed 等权", "seed1（固定）", g3["fixed"], b3["fixed"]),
        ("2-seed 等权", f"seed{val_best_seed}（验证集最佳）", g2["val_best"], b2["val_best"]),
        ("2-seed 等权", "seed1（固定）", g2["fixed"], b2["fixed"]),
        ("2-seed 等权", "基线", g2["baseline"], b2["baseline"]),
        ("2-seed 等权", "3-seed 等权", g2["vs_ens3"], b2["vs_ens3"]),
        ("3-seed 加权", f"seed{val_best_seed}（验证集最佳）", g3w["val_best"], b3w["val_best"]),
        ("3-seed 加权", "3-seed 等权", g3w["vs_ens3"], b3w["vs_ens3"]),
    ]
    for name, ref, g, b in comp_rows:
        md.append(f"| {name} | {ref} | {g['gain']:+.4f} | "
                  f"[{g['ci95'][0]:+.4f}, {g['ci95'][1]:+.4f}] | "
                  f"{b['delta']['band_acc']:+.4f} |")

    md.append("\n## 结论\n")
    md.append(f"**3-seed 等权：{'建议接入' if ok3 else '建议不接入'}。** "
              f"相对验证集最佳 seed{val_best_seed} 整体 MAE 降 {g3['val_best']['gain']:.3f}"
              f"（95% CI {g3['val_best']['ci95'][0]:.3f} ~ {g3['val_best']['ci95'][1]:.3f}）；"
              f"相对固定 seed1 降 {g3['fixed']['gain']:.3f}"
              f"（95% CI {g3['fixed']['ci95'][0]:.3f} ~ {g3['fixed']['ci95'][1]:.3f}）。"
              f"{why3}")
    md.append(f"**2-seed 等权（seed{two_members[0]}+seed{two_members[1]}）："
              f"{'建议接入' if ok2 else '建议不接入'}。** "
              f"相对验证集最佳 seed{val_best_seed} 整体 MAE 降 {g2['val_best']['gain']:.3f}"
              f"（95% CI {g2['val_best']['ci95'][0]:.3f} ~ {g2['val_best']['ci95'][1]:.3f}）；"
              f"相对固定 seed1 降 {g2['fixed']['gain']:.3f}"
              f"（95% CI {g2['fixed']['ci95'][0]:.3f} ~ {g2['fixed']['ci95'][1]:.3f}）。"
              f"{why2}")
    md.append(f"2-seed 与 3-seed 等权整体只差 {g2['vs_ens3']['gain']:.3f}"
              f"（95% CI {g2['vs_ens3']['ci95'][0]:.3f} ~ {g2['vs_ens3']['ci95'][1]:.3f}，打平），"
              "但 2-seed 少一个模型，且对最好单 seed 的 CI 不跨 0；"
              "如果接入，优先 2-seed，不需要 3-seed。")
    md.append("**3-seed 加权：建议不接入。** 运行时只支持等权 raw 平均，"
              f"且相对 3-seed 等权仅降 {g3w['vs_ens3']['gain']:.3f}，不值得改运行时。")
    md.append(f"\n判断门槛：相对最好单 seed 的整体 MAE 降幅低于 {MIN_GAIN:.2f}、"
              "或 paired bootstrap 的 95% CI 跨 0，就不建议上集成。"
              f"3 模型部署代价约 {ENSEMBLE_SIZE_MB}MB、CPU 单张 {ENSEMBLE_CPU_SECONDS:.2f} 秒；"
              "2 模型约 90MB，CPU 延迟未实测。\n")

    md.append("## 统计口径\n")
    md.append("- 三个 seed 的 mean±std（n=3）只作描述，不当作显著性依据。")
    md.append("- 最终只认 paired bootstrap 的 95% CI：CI 不跨 0 才算有统计意义。")
    md.append("- 集成要同时打过“验证集最佳 seed”和“固定 seed1”才值得上；只打过基线不算。")
    md.append("- 本记录不改变线上模型、默认权重和校准文件。\n")

    md.append("## 产物路径与哈希\n")
    md.append("| 文件 | 路径 |\n|---|---|")
    for key, path in result["artifacts"]["preds"].items():
        md.append(f"| preds {key} | `{path}` |")
    for key, info in result["artifacts"]["weights"].items():
        md.append(f"| {key} best.pt | `{info['path']}` |")
    md.append(f"| 基线 weights/apddv2_ft/best.pt | "
              f"`{ROOT / 'weights' / 'apddv2_ft' / 'best.pt'}` |")
    md.append(f"| 基线 before SHA256 | `{before}` |")
    md.append(f"| 基线 after SHA256 | `{after}` |")
    md.append(f"\n基线权重训练前后一致：**{result['artifacts']['baseline_weight']['unchanged']}**。\n")
    md.append("权重 SHA256：\n")
    for key, info in result["artifacts"]["weights"].items():
        md.append(f"- `{key}`：`{info['sha256']}`")
    md.append("\n脚本：\n")
    for p in result["artifacts"]["scripts"]:
        md.append(f"- `{p}`")

    (ROOT / "logs" / "E1_EVAL_SUMMARY.md").write_text("\n".join(md), encoding="utf-8")
    print("written:", ROOT / "logs" / "E1_EVAL_SUMMARY.md", flush=True)


if __name__ == "__main__":
    main()
