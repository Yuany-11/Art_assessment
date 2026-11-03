"""多任务损失平衡：固定权重 / 不确定性加权 / DWA。

三种模式的取舍
--------------
``fixed``
    旧行为：``total = Σ w_i · L_i``，权重由命令行给定。好处是 val loss 跨 epoch
    可直接比较，坏处是 emotion 这类噪声大的任务要么主导梯度、要么被压死。
``uncertainty``
    Kendall et al. (2018) 的不确定性加权。给每个任务一个可学习的
    ``s_i = log σ_i²``，总损失写成

        total = Σ_i [ exp(-s_i) · L_i + s_i ]

    ``exp(-s_i)`` 就是自动学出来的权重：loss 噪声大/幅度大的任务会被压低权重，
    ``+ s_i`` 防止模型把所有权重推到 0。参数很少（每任务一个），收敛很快。
    注意训练态总损失**不再跨 epoch 可比**（权重在变），所以验证/选模一律用
    ``fixed`` 权重计算，这一点在 ``train.py`` 里已经分开。
``dwa``
    Liu et al. (2019) Dynamic Weight Averaging：用上一轮各任务 loss 的下降速度
    来定权重，不增加任何可学习参数，实现简单、几乎不改优化器状态。

    ``r_i = L_i(t-1) / L_i(t-2)``，``w_i = n · softmax(r_i / T)``

    按论文原式：loss 下降得快（``r_i > 1``）的任务权重变大，卡住（``r_i ≈ 1``）
    或变差（``r_i < 1``）的任务权重变小——也就是说 DWA 会优先推进“学得动”的任务，
    避免被长期学不动的任务拖住。如果想把策略反过来（“谁落后补谁”），把
    ``_dwa_weights`` 里的 ``previous / current`` 改成 ``current / previous`` 即可。

为什么没有 GradNorm
-------------------
GradNorm 需要为每个任务单独反传一次以计算梯度范数，配合 AMP + 大模型会让每个
step 多 3 次反向，RTX 3080 上吞吐大约掉一半，收益与 DWA 接近，不划算。
"""

from __future__ import annotations

from typing import Dict, Mapping, Optional, Sequence

import torch
from torch import nn

TASK_NAMES: Sequence[str] = ("genre", "emotion", "mode", "bpm")
DEFAULT_WEIGHTS: Dict[str, float] = {
    "genre": 1.0,
    "emotion": 0.6,
    "mode": 0.4,
    "bpm": 0.3,
}


class TaskBalancer(nn.Module):
    """把四个任务的标量 loss 合成一个总 loss。

    参数
    ----
    mode:
        ``"fixed"`` / ``"uncertainty"`` / ``"dwa"``。
    weights:
        ``fixed`` 模式下的权重；其余模式只用来初始化/记录。
    dwa_temperature:
        DWA 的 softmax 温度，越大越平滑。
    """

    def __init__(
        self,
        mode: str = "fixed",
        weights: Optional[Mapping[str, float]] = None,
        task_names: Sequence[str] = TASK_NAMES,
        dwa_temperature: float = 2.0,
    ):
        super().__init__()
        if mode not in ("fixed", "uncertainty", "dwa"):
            raise ValueError(f"unknown loss balance mode: {mode}")
        self.mode = mode
        self.task_names = tuple(task_names)
        self.dwa_temperature = float(max(dwa_temperature, 1e-3))

        base = dict(DEFAULT_WEIGHTS)
        if weights:
            base.update({key: float(value) for key, value in weights.items()})
        self.base_weights = {name: float(base.get(name, 1.0)) for name in self.task_names}

        # uncertainty 模式：每个任务一个 log 方差参数，fp32（AMP 下也不降精度）
        if mode == "uncertainty":
            self.log_vars = nn.Parameter(
                torch.zeros(len(self.task_names), dtype=torch.float32)
            )
        else:
            self.register_parameter("log_vars", None)

        # 当前生效的权重（DWA 会更新），只用于日志
        self.register_buffer(
            "task_weights",
            torch.tensor(
                [self.base_weights[name] for name in self.task_names],
                dtype=torch.float32,
            ),
        )
        # DWA 用最近两轮的 epoch 平均 loss
        self.register_buffer(
            "loss_history",
            torch.zeros(len(self.task_names), 2, dtype=torch.float32),
        )
        self.register_buffer("history_filled", torch.zeros(1, dtype=torch.float32))

    # ---------------------------------------------------------------- forward
    def forward(
        self,
        task_losses: Mapping[str, torch.Tensor],
        valid: Optional[Mapping[str, bool]] = None,
    ) -> torch.Tensor:
        """合成总损失。

        ``valid`` 用来跳过当前 batch 里一个有效样本都没有的任务
        （例如某个 batch 全是无情绪标注的曲目）。缺失的任务按 invalid 处理。
        """
        losses = {
            name: task_losses[name].float()
            for name in self.task_names
            if name in task_losses
        }
        if valid is not None:
            losses = {
                name: value for name, value in losses.items() if valid.get(name, True)
            }
        if not losses:
            return torch.zeros((), dtype=torch.float32, device=self._device())

        if self.mode == "uncertainty":
            total = None
            for index, name in enumerate(self.task_names):
                if name not in losses:
                    continue
                s = self.log_vars[index]
                term = torch.exp(-s) * losses[name] + s
                total = term if total is None else total + term
            assert total is not None
            return total

        if self.mode == "dwa":
            # 只在“本 batch 有效”的任务上做 softmax，权重和为有效任务数，
            # 量级与 fixed 模式（权重约 0.3～1.0）接近。
            active = [name for name in self.task_names if name in losses]
            weights = self._dwa_weights(active)
            total = None
            for name in active:
                term = weights[name] * losses[name]
                total = term if total is None else total + term
            assert total is not None
            return total

        total = None
        for index, name in enumerate(self.task_names):
            if name not in losses:
                continue
            weight = float(self.base_weights[name])
            term = weight * losses[name]
            total = term if total is None else total + term
        assert total is not None
        return total

    # ------------------------------------------------------------------ DWA
    def _dwa_weights(self, active: Sequence[str]) -> Dict[str, float]:
        """由最近两轮的 loss 比值算权重；历史不足时退回基础权重。"""
        if not active:
            return {}
        if float(self.history_filled.item()) < 2.0:
            return {name: float(self.base_weights[name]) for name in active}

        indices = [self.task_names.index(name) for name in active]
        previous = self.loss_history[indices, 0].clamp_min(1e-6)
        current = self.loss_history[indices, 1].clamp_min(1e-6)
        ratios = (previous / current).clamp(0.5, 2.0)
        scaled = torch.softmax(ratios / self.dwa_temperature, dim=0) * len(indices)
        return {
            name: float(scaled[position])
            for position, name in enumerate(active)
        }

    @torch.no_grad()
    def update_dwa(self, epoch_losses: Mapping[str, float]) -> None:
        """每个 epoch 结束时调用一次，喂入本 epoch 各任务的平均 loss。"""
        if self.mode != "dwa":
            return
        values = [
            float(epoch_losses.get(name, float(self.loss_history[i, 1])))
            for i, name in enumerate(self.task_names)
        ]
        history = self.loss_history.clone()
        history[:, 0] = history[:, 1]
        history[:, 1] = torch.tensor(values, dtype=torch.float32)
        self.loss_history.copy_(history)
        self.history_filled.fill_(
            min(2.0, float(self.history_filled.item()) + 1.0)
        )
        weights = self._dwa_weights(list(self.task_names))
        self.task_weights.copy_(
            torch.tensor(
                [weights[name] for name in self.task_names], dtype=torch.float32
            )
        )

    # ---------------------------------------------------------------- helpers
    def current_weights(self) -> Dict[str, float]:
        """当前权重的可读快照，写到 metrics.json 便于排查。"""
        if self.mode == "uncertainty":
            with torch.no_grad():
                values = torch.exp(-self.log_vars).detach().cpu()
            return {
                name: round(float(values[index]), 4)
                for index, name in enumerate(self.task_names)
            }
        weights = self.task_weights.detach().cpu()
        return {
            name: round(float(weights[index]), 4)
            for index, name in enumerate(self.task_names)
        }

    def _device(self) -> torch.device:
        if self.log_vars is not None:
            return self.log_vars.device
        return self.task_weights.device
