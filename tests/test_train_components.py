from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from training.augment import (  # noqa: E402
    AugmentConfig,
    FeatureAugmenter,
    time_roll,
    time_stretch,
)
from training.early_stopping import EarlyStopping  # noqa: E402
from training.losses import TaskBalancer  # noqa: E402
from training.model import build_model  # noqa: E402

N_MELS, N_CHROMA, FRAMES = 128, 12, 200


def _features(seed: int = 0, frames: int = FRAMES):
    rng = np.random.default_rng(seed)
    mel = rng.normal(size=(N_MELS, frames)).astype(np.float32)
    chroma = rng.normal(size=(N_CHROMA, frames)).astype(np.float32)
    return mel, chroma


class AugmentTests(unittest.TestCase):
    def test_time_stretch_scales_frames_and_bpm(self) -> None:
        mel, chroma = _features()
        faster_mel, faster_chroma, scale = time_stretch(mel, chroma, 1.25)
        self.assertAlmostEqual(scale, 1.25)
        self.assertEqual(faster_mel.shape, (N_MELS, int(round(FRAMES / 1.25))))
        self.assertEqual(faster_chroma.shape[1], faster_mel.shape[1])

        slower_mel, _, scale = time_stretch(mel, chroma, 0.8)
        self.assertAlmostEqual(scale, 0.8)
        self.assertEqual(slower_mel.shape[1], int(round(FRAMES / 0.8)))

    def test_time_stretch_identity(self) -> None:
        mel, chroma = _features()
        out_mel, out_chroma, scale = time_stretch(mel, chroma, 1.0)
        self.assertAlmostEqual(scale, 1.0)
        self.assertTrue(np.array_equal(out_mel, mel))
        self.assertTrue(np.array_equal(out_chroma, chroma))

    def test_time_roll_keeps_shape_and_content(self) -> None:
        mel, chroma = _features()
        rolled, rolled_chroma = time_roll(mel, chroma, np.random.default_rng(3))
        self.assertEqual(rolled.shape, mel.shape)
        self.assertEqual(rolled_chroma.shape, chroma.shape)
        self.assertTrue(np.array_equal(np.sort(rolled, axis=1), np.sort(mel, axis=1)))

    def test_augmenter_keeps_fixed_length(self) -> None:
        config = AugmentConfig(
            noise_prob=1.0,
            noise_std=0.05,
            roll_prob=1.0,
            stretch_prob=1.0,
            stretch_range=(0.9, 1.1),
        )
        augmenter = FeatureAugmenter(config)
        mel, chroma = _features()
        out_mel, out_chroma, bpm_scale = augmenter(
            mel, chroma, np.random.default_rng(7), frames=FRAMES
        )
        self.assertEqual(out_mel.shape, (N_MELS, FRAMES))
        self.assertEqual(out_chroma.shape, (N_CHROMA, FRAMES))
        self.assertTrue(0.89 <= bpm_scale <= 1.11)

    def test_augmenter_is_deterministic_per_seed(self) -> None:
        augmenter = FeatureAugmenter(AugmentConfig(roll_prob=0.5, noise_prob=0.5))
        mel, chroma = _features()
        first = augmenter(mel, chroma, np.random.default_rng(11), frames=FRAMES)[0]
        second = augmenter(mel, chroma, np.random.default_rng(11), frames=FRAMES)[0]
        self.assertTrue(np.array_equal(first, second))

    def test_default_config_matches_legacy_behaviour(self) -> None:
        # 默认不开启平移/变速，只做 SpecAugment + 轻噪声
        config = AugmentConfig()
        self.assertEqual(config.roll_prob, 0.0)
        self.assertEqual(config.stretch_prob, 0.0)
        self.assertEqual(config.noise_std, 0.02)


class TaskBalancerTests(unittest.TestCase):
    def _losses(self) -> dict:
        return {
            "genre": torch.tensor(1.2),
            "emotion": torch.tensor(0.8),
            "mode": torch.tensor(0.4),
            "bpm": torch.tensor(0.6),
        }

    def test_fixed_matches_manual_weighting(self) -> None:
        weights = {"genre": 1.0, "emotion": 0.6, "mode": 0.4, "bpm": 0.3}
        balancer = TaskBalancer("fixed", weights)
        total = balancer(self._losses())
        expected = 1.2 * 1.0 + 0.8 * 0.6 + 0.4 * 0.4 + 0.6 * 0.3
        self.assertAlmostEqual(float(total), expected, places=5)

    def test_fixed_skips_invalid_tasks(self) -> None:
        balancer = TaskBalancer("fixed", {"genre": 1.0, "emotion": 1.0})
        total = balancer(
            {"genre": torch.tensor(1.0), "emotion": torch.tensor(5.0)},
            {"genre": True, "emotion": False},
        )
        self.assertAlmostEqual(float(total), 1.0, places=5)

    def test_uncertainty_weighting_formula(self) -> None:
        balancer = TaskBalancer("uncertainty")
        losses = self._losses()
        total = balancer(losses)
        # 初始 log 方差全为 0：total = Σ L_i
        self.assertAlmostEqual(float(total.detach()), 3.0, places=5)

        with torch.no_grad():
            balancer.log_vars[1] = math.log(2.0)  # σ² = 2 -> 权重 0.5
        total = balancer(losses)
        expected = 1.2 + 0.5 * 0.8 + math.log(2.0) + 0.4 + 0.6
        self.assertAlmostEqual(float(total.detach()), expected, places=5)

    def test_uncertainty_gradients_flow(self) -> None:
        balancer = TaskBalancer("uncertainty")
        total = balancer(self._losses())
        total.backward()
        self.assertIsNotNone(balancer.log_vars.grad)
        self.assertTrue(torch.all(balancer.log_vars.grad != 0))

    def test_uncertainty_reports_effective_weights(self) -> None:
        balancer = TaskBalancer("uncertainty")
        weights = balancer.current_weights()
        self.assertEqual(set(weights), {"genre", "emotion", "mode", "bpm"})
        self.assertAlmostEqual(sum(weights.values()), 4.0, places=4)

    def test_dwa_reweights_fast_task(self) -> None:
        balancer = TaskBalancer("dwa", dwa_temperature=1.0)
        # 第一轮：genre 下降一半，emotion 卡住
        balancer.update_dwa({"genre": 2.0, "emotion": 1.0, "mode": 1.0, "bpm": 1.0})
        balancer.update_dwa({"genre": 1.0, "emotion": 1.0, "mode": 1.0, "bpm": 1.0})
        weights = balancer.current_weights()
        # DWA 权重和等于任务数
        self.assertAlmostEqual(sum(weights.values()), 4.0, places=4)
        # 论文原式：下降快的 genre 权重高于卡住的 emotion（r = 2 vs r = 1）
        self.assertGreater(weights["genre"], weights["emotion"])

    def test_dwa_before_history_uses_base_weights(self) -> None:
        balancer = TaskBalancer("dwa", {"genre": 1.0, "emotion": 0.5})
        total = balancer({"genre": torch.tensor(1.0), "emotion": torch.tensor(2.0)})
        self.assertAlmostEqual(float(total), 2.0, places=5)

    def test_state_dict_roundtrip(self) -> None:
        source = TaskBalancer("uncertainty")
        with torch.no_grad():
            source.log_vars.copy_(torch.tensor([0.1, -0.2, 0.3, -0.4]))
        target = TaskBalancer("uncertainty")
        target.load_state_dict(source.state_dict())
        self.assertTrue(torch.allclose(source.log_vars, target.log_vars))


class EarlyStoppingTests(unittest.TestCase):
    def test_triggers_after_patience(self) -> None:
        stopper = EarlyStopping(patience=3)
        self.assertTrue(stopper.step(0.5, 1))
        self.assertFalse(stopper.step(0.49, 2))
        self.assertFalse(stopper.step(0.48, 3))
        self.assertFalse(stopper.triggered)
        self.assertFalse(stopper.step(0.47, 4))
        self.assertTrue(stopper.triggered)
        self.assertEqual(stopper.best_epoch, 1)
        self.assertEqual(stopper.counter, 3)
        self.assertEqual(stopper.stopped_epoch, 4)

    def test_min_delta(self) -> None:
        stopper = EarlyStopping(patience=1, min_delta=0.01)
        stopper.step(0.5, 1)
        # 提升 0.005 < min_delta，不算提升
        self.assertFalse(stopper.step(0.505, 2))
        self.assertTrue(stopper.triggered)

    def test_min_mode(self) -> None:
        stopper = EarlyStopping(patience=2, mode="min")
        self.assertTrue(stopper.step(1.0, 1))
        self.assertTrue(stopper.step(0.9, 2))
        self.assertFalse(stopper.step(0.95, 3))
        self.assertFalse(stopper.step(0.96, 4))
        self.assertTrue(stopper.triggered)

    def test_zero_patience_never_triggers(self) -> None:
        stopper = EarlyStopping(patience=0)
        stopper.step(1.0, 1)
        for epoch in range(2, 12):
            stopper.step(0.0, epoch)
        self.assertFalse(stopper.triggered)
        self.assertEqual(stopper.counter, 10)

    def test_state_roundtrip_resumes_counter(self) -> None:
        stopper = EarlyStopping(patience=5)
        stopper.step(0.8, 1)
        stopper.step(0.7, 2)
        stopper.step(0.6, 3)
        restored = EarlyStopping(patience=5)
        restored.load_state_dict(stopper.state_dict())
        self.assertEqual(restored.best, 0.8)
        self.assertEqual(restored.counter, 2)
        self.assertEqual(restored.best_epoch, 1)


class TempoBranchTests(unittest.TestCase):
    """v4 的 tempo 分支：形状、数值范围、梯度、arch 识别。"""

    def setUp(self) -> None:
        torch.manual_seed(0)
        self.model = build_model("v4", 13, 4, 2)
        self.model.eval()

    def test_forward_shapes(self) -> None:
        for frames in (129, 517):
            mel = torch.randn(2, 1, N_MELS, frames)
            chroma = torch.randn(2, 1, N_CHROMA, frames)
            with torch.no_grad():
                out = self.model(mel, chroma)
            self.assertEqual(out["genre"].shape, (2, 13))
            self.assertEqual(out["emotion"].shape, (2, 4))
            self.assertEqual(out["mode"].shape, (2, 2))
            self.assertEqual(out["bpm"].shape, (2,))
            # soft-argmax over centers in [-4, 4]
            self.assertTrue(torch.all(out["bpm"].abs() <= 4.0))

    def test_tempo_features_bounded(self) -> None:
        mel = torch.randn(3, 1, N_MELS, 257)
        feats = self.model.tempo_branch(mel)
        self.assertEqual(feats.shape, (3, 64))
        self.assertTrue(torch.isfinite(feats).all())
        self.assertLessEqual(float(feats.abs().max()), 1.05)

    def test_tempo_grid_covers_label_range(self) -> None:
        grid = self.model.tempo_branch.bpm_grid
        self.assertLessEqual(float(grid.min()), 70.0)
        self.assertGreaterEqual(float(grid.max()), 180.0)

    def test_bpm_branch_receives_gradient(self) -> None:
        mel = torch.randn(3, 1, N_MELS, 129)
        chroma = torch.randn(3, 1, N_CHROMA, 129)
        self.model.train()
        out = self.model(mel, chroma)
        out["bpm"].sum().backward()
        for parameter in self.model.bpm_trunk.parameters():
            self.assertIsNotNone(parameter.grad)

    def test_arch_detection(self) -> None:
        from training.infer import _detect_arch

        v4_state = build_model("v4", 13, 4, 2).state_dict()
        v3_state = build_model("v3", 13, 4, 2).state_dict()
        self.assertEqual(_detect_arch(v4_state), "v4")
        self.assertEqual(_detect_arch(v3_state), "v3")

    def test_v3_still_builds(self) -> None:
        model = build_model("v3", 13, 4, 2)
        out = model(torch.randn(2, 1, N_MELS, 129), torch.randn(2, 1, N_CHROMA, 129))
        self.assertNotIn("tempo_branch", dict(model.named_modules()))


if __name__ == "__main__":
    unittest.main()
