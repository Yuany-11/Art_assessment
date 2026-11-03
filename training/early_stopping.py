"""早停：验证集指标连续 ``patience`` 个 epoch 不提升就停止。

用法
----
::

    stopper = EarlyStopping(patience=10, min_delta=1e-4, mode="max")

    for epoch in range(1, epochs + 1):
        score = validate(...)
        if stopper.step(score, epoch):
            save_checkpoint("best_model.pt", model.state_dict())   # 只在提升时保存
            best = stopper.best
        if stopper.triggered:
            print(f"early stop @ {epoch}, best {stopper.best:.4f}")
            break

``step`` 返回 ``True`` 表示这次是历史最优（此时才该写 best 权重），
``stopper.counter`` 是“已经连续多少个 epoch 没提升”，可以直接写进 state.json。

状态可序列化（``state_dict`` / ``load_state_dict``），断点续训时能接着计数，
不会因为重启训练而重新获得完整的 patience。
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, Optional


class EarlyStopping:
    """监控一个标量指标（这里用验证集 combined score），越大越好。"""

    def __init__(
        self,
        patience: int = 10,
        min_delta: float = 1e-4,
        mode: str = "max",
        start_epoch: int = 1,
        on_improve: Optional[Callable[[int], None]] = None,
    ):
        if mode not in ("max", "min"):
            raise ValueError("mode must be 'max' or 'min'")
        if patience < 0:
            raise ValueError("patience must be >= 0")
        self.patience = int(patience)
        self.min_delta = float(min_delta)
        self.mode = mode
        # 回调在每次刷新最优值时触发，参数是 epoch，用来“顺便保存最优模型”
        self.on_improve = on_improve
        self.start_epoch = int(start_epoch)
        self.best = -math.inf if mode == "max" else math.inf
        self.best_epoch = 0
        self.counter = 0
        self.triggered = False
        self.stopped_epoch = 0
        self.improved = False

    # ------------------------------------------------------------------ core
    def _is_better(self, value: float) -> bool:
        if self.mode == "max":
            return value > self.best + self.min_delta
        return value < self.best - self.min_delta

    def step(self, value: float, epoch: Optional[int] = None) -> bool:
        """喂入本 epoch 的指标，返回是否为历史最优。"""
        value = float(value)
        epoch = int(epoch if epoch is not None else self.start_epoch)
        self.improved = False

        if self._is_better(value):
            self.best = value
            self.best_epoch = epoch
            self.counter = 0
            self.improved = True
            if self.on_improve is not None:
                self.on_improve(epoch)
        else:
            self.counter += 1
            if self.patience > 0 and self.counter >= self.patience:
                self.triggered = True
                self.stopped_epoch = epoch

        return self.improved

    # ------------------------------------------------------------ checkpoint
    def state_dict(self) -> Dict[str, Any]:
        return {
            "best": self.best,
            "best_epoch": self.best_epoch,
            "counter": self.counter,
            "triggered": self.triggered,
            "stopped_epoch": self.stopped_epoch,
            "patience": self.patience,
            "min_delta": self.min_delta,
            "mode": self.mode,
        }

    def load_state_dict(self, state: Dict[str, Any]) -> None:
        self.best = float(state.get("best", self.best))
        self.best_epoch = int(state.get("best_epoch", 0))
        self.counter = int(state.get("counter", 0))
        self.triggered = bool(state.get("triggered", False))
        self.stopped_epoch = int(state.get("stopped_epoch", 0))

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return (
            f"EarlyStopping(mode={self.mode}, best={self.best:.4f} @ "
            f"{self.best_epoch}, counter={self.counter}/{self.patience}, "
            f"triggered={self.triggered})"
        )
