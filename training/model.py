"""Dual-branch CNN with four heads: genre, emotion, mode, BPM.

Three architectures are provided:

``v1``
    The original checkpoint layout (plain 4/3-block CNNs + shared MLP).  Kept
    verbatim so checkpoints under ``training/runs/*/best_model.pt`` keep
    working with the existing scorer.

``v2``
    Same two branches, but with residual + squeeze-and-excitation blocks,
    average/max pooling and dropout.  It has roughly twice the capacity of v1
    while staying CPU-friendly (~0.8 M parameters).

``v3`` (default for new runs)
    Attention (mean/std/max) pooling instead of plain average/max, stochastic
    depth in the residual blocks, a two-layer classifier with a residual
    refinement, and a bin-based (soft-argmax) BPM head.  Same inputs, same four
    output keys, same normalised BPM scale as v2, so training, inference and
    scoring code are unchanged.  ~1.1 M parameters.

``v4``
    v3 plus an explicit tempo branch.  The convolutional trunk pools the time
    axis 16x (4 residual blocks), i.e. 43.07 fps -> 2.7 fps; the Nyquist limit
    of that feature map is ~81 BPM, so every faster tempo is aliased away and
    the BPM head can only regress the dataset mean (measured MAE ~20 BPM,
    identical to a constant predictor).  v4 computes a differentiable
    onset-autocorrelation ("tempogram") directly from the input mel and feeds
    it to the BPM head, which restores the missing information without
    slowing down the rest of the network.  ~1.2 M parameters.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

DEFAULT_GENRES = 13
DEFAULT_EMOTIONS = 4
DEFAULT_MODES = 2

# SR / HOP_LENGTH from training/features.py：43.0665 帧/秒
FRAME_RATE = 22050.0 / 512.0


class _SE(nn.Module):
    def __init__(self, channels: int, reduction: int = 8):
        super().__init__()
        hidden = max(4, channels // reduction)
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.fc1 = nn.Conv2d(channels, hidden, 1)
        self.fc2 = nn.Conv2d(hidden, channels, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        scale = self.pool(x)
        scale = F.relu(self.fc1(scale), inplace=True)
        scale = torch.sigmoid(self.fc2(scale))
        return x * scale


def _drop_path(x: torch.Tensor, p: float) -> torch.Tensor:
    """Stochastic depth: drop the whole residual branch per sample."""
    if p <= 0.0 or not x.requires_grad:
        return x
    keep = 1.0 - p
    mask = x.new_empty((x.shape[0],) + (1,) * (x.dim() - 1)).bernoulli_(keep)
    return x.div(keep) * mask


class _ResBlock(nn.Module):
    def __init__(
        self, in_ch: int, out_ch: int, pool: bool = True, drop_path: float = 0.0
    ):
        super().__init__()
        self.pool = pool
        self.drop_path = float(drop_path)
        self.conv1 = nn.Conv2d(in_ch, out_ch, 3, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(out_ch)
        self.conv2 = nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_ch)
        self.se = _SE(out_ch)
        if in_ch == out_ch:
            self.shortcut = nn.Identity()
        else:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_ch, out_ch, 1, bias=False), nn.BatchNorm2d(out_ch)
            )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        identity = self.shortcut(x)
        out = F.relu(self.bn1(self.conv1(x)), inplace=True)
        out = self.bn2(self.conv2(out))
        out = self.se(out)
        if self.pool:
            out = F.max_pool2d(out, 2)
            identity = F.max_pool2d(identity, 2)
        if self.training and self.drop_path > 0.0:
            out = _drop_path(out, self.drop_path)
        return F.relu(out + identity, inplace=True)


class _DualPool(nn.Module):
    """Concatenate global average and max statistics (2 * channels)."""

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        avg = F.adaptive_avg_pool2d(x, 1).flatten(1)
        maximum = F.adaptive_max_pool2d(x, 1).flatten(1)
        return torch.cat([avg, maximum], dim=1)


class _AttentionPool(nn.Module):
    """Attentive statistics pooling: weighted mean, std and max (3 * channels).

    The 1x1 attention conv starts at zero, so training begins from the plain
    average/max behaviour and the weights sharpen only where they help.
    """

    def __init__(self, channels: int):
        super().__init__()
        self.att = nn.Conv2d(channels, 1, 1)
        self.reset_parameters()

    def reset_parameters(self) -> None:
        nn.init.zeros_(self.att.weight)
        nn.init.zeros_(self.att.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        flat = x.flatten(2)  # B, C, N
        weights = torch.softmax(self.att(x).flatten(2), dim=-1)  # B, 1, N
        mean = (flat * weights).sum(-1)
        second = (flat * flat * weights).sum(-1)
        std = (second - mean * mean).clamp_min(1e-6).sqrt()
        peak = F.adaptive_max_pool2d(x, 1).flatten(1)
        return torch.cat([mean, std, peak], dim=1)


class ArtEvalNet(nn.Module):
    """v2 architecture."""

    arch = "v2"

    def __init__(
        self,
        n_genres: int = DEFAULT_GENRES,
        n_emotions: int = DEFAULT_EMOTIONS,
        n_modes: int = DEFAULT_MODES,
        mel_channels: Tuple[int, ...] = (32, 64, 96, 128),
        chroma_channels: Tuple[int, ...] = (32, 64, 96),
        hidden: int = 256,
        dropout: float = 0.3,
    ):
        super().__init__()
        mel_blocks = []
        in_ch = 1
        for out_ch in mel_channels:
            mel_blocks.append(_ResBlock(in_ch, out_ch))
            in_ch = out_ch
        self.mel_branch = nn.Sequential(*mel_blocks)

        chroma_blocks = []
        in_ch = 1
        for out_ch in chroma_channels:
            chroma_blocks.append(_ResBlock(in_ch, out_ch))
            in_ch = out_ch
        self.chroma_branch = nn.Sequential(*chroma_blocks)

        self.pool = _DualPool()
        feat_dim = 2 * mel_channels[-1] + 2 * chroma_channels[-1]
        self.shared = nn.Sequential(
            nn.Dropout(dropout * 0.5),
            nn.Linear(feat_dim, hidden),
            nn.BatchNorm1d(hidden),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
        )
        self.genre_head = nn.Linear(hidden, n_genres)
        self.emotion_head = nn.Linear(hidden, n_emotions)
        self.mode_head = nn.Linear(hidden, n_modes)
        self.bpm_head = nn.Linear(hidden, 1)
        self._init_weights()

    def _init_weights(self) -> None:
        for module in self.modules():
            if isinstance(module, nn.Conv2d):
                nn.init.kaiming_normal_(module.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(module, nn.BatchNorm2d):
                nn.init.ones_(module.weight)
                nn.init.zeros_(module.bias)
            elif isinstance(module, nn.Linear):
                nn.init.trunc_normal_(module.weight, std=0.02)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)

    def forward(
        self, mel: torch.Tensor, chroma: torch.Tensor
    ) -> Dict[str, torch.Tensor]:
        mel_feat = self.pool(self.mel_branch(mel))
        chroma_feat = self.pool(self.chroma_branch(chroma))
        fused = self.shared(torch.cat([mel_feat, chroma_feat], dim=1))
        return {
            "genre": self.genre_head(fused),
            "emotion": self.emotion_head(fused),
            "mode": self.mode_head(fused),
            "bpm": self.bpm_head(fused).squeeze(-1),
        }


# ---------------------------------------------------------------------------
# v3
# ---------------------------------------------------------------------------
class ArtEvalNetV3(nn.Module):
    """v3 architecture: attentive pooling, stochastic depth, soft-argmax BPM."""

    arch = "v3"

    def __init__(
        self,
        n_genres: int = DEFAULT_GENRES,
        n_emotions: int = DEFAULT_EMOTIONS,
        n_modes: int = DEFAULT_MODES,
        mel_channels: Tuple[int, ...] = (32, 64, 96, 128),
        chroma_channels: Tuple[int, ...] = (32, 64, 96),
        hidden: int = 320,
        dropout: float = 0.3,
        mel_drop_path: Tuple[float, ...] = (0.0, 0.05, 0.1, 0.15),
        chroma_drop_path: Tuple[float, ...] = (0.0, 0.05, 0.1),
        bpm_bins: int = 64,
        bpm_range: float = 4.0,
    ):
        super().__init__()
        mel_blocks = []
        in_ch = 1
        for index, out_ch in enumerate(mel_channels):
            mel_blocks.append(
                _ResBlock(in_ch, out_ch, drop_path=mel_drop_path[index])
            )
            in_ch = out_ch
        self.mel_branch = nn.Sequential(*mel_blocks)

        chroma_blocks = []
        in_ch = 1
        for index, out_ch in enumerate(chroma_channels):
            chroma_blocks.append(
                _ResBlock(in_ch, out_ch, drop_path=chroma_drop_path[index])
            )
            in_ch = out_ch
        self.chroma_branch = nn.Sequential(*chroma_blocks)

        self.mel_pool = _AttentionPool(mel_channels[-1])
        self.chroma_pool = _AttentionPool(chroma_channels[-1])
        feat_dim = 3 * mel_channels[-1] + 3 * chroma_channels[-1]
        self.shared = nn.Sequential(
            nn.Dropout(dropout * 0.5),
            nn.Linear(feat_dim, hidden),
            nn.BatchNorm1d(hidden),
            nn.GELU(),
            nn.Dropout(dropout),
        )
        self.shared_refine = nn.Sequential(
            nn.Linear(hidden, hidden),
            nn.BatchNorm1d(hidden),
            nn.GELU(),
            nn.Dropout(dropout / 3.0),
        )
        self.genre_head = nn.Linear(hidden, n_genres)
        self.emotion_head = nn.Linear(hidden, n_emotions)
        self.mode_head = nn.Linear(hidden, n_modes)
        self.bpm_trunk = nn.Sequential(
            nn.Linear(hidden, hidden // 2),
            nn.GELU(),
            nn.Dropout(dropout / 3.0),
        )
        self.bpm_head = nn.Linear(hidden // 2, bpm_bins)
        self.register_buffer(
            "bpm_centers",
            torch.linspace(-float(bpm_range), float(bpm_range), int(bpm_bins)),
        )
        self._init_weights()
        # Attention layers start as uniform averages (see _AttentionPool).
        self.mel_pool.reset_parameters()
        self.chroma_pool.reset_parameters()

    def _init_weights(self) -> None:
        for module in self.modules():
            if isinstance(module, nn.Conv2d):
                nn.init.kaiming_normal_(module.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(module, nn.BatchNorm2d):
                nn.init.ones_(module.weight)
                nn.init.zeros_(module.bias)
            elif isinstance(module, nn.BatchNorm1d):
                nn.init.ones_(module.weight)
                nn.init.zeros_(module.bias)
            elif isinstance(module, nn.Linear):
                nn.init.trunc_normal_(module.weight, std=0.02)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)

    def forward(
        self, mel: torch.Tensor, chroma: torch.Tensor
    ) -> Dict[str, torch.Tensor]:
        mel_feat = self.mel_pool(self.mel_branch(mel))
        chroma_feat = self.chroma_pool(self.chroma_branch(chroma))
        fused = self.shared(torch.cat([mel_feat, chroma_feat], dim=1))
        fused = fused + self.shared_refine(fused)
        bpm_logits = self.bpm_head(self.bpm_trunk(fused))
        bpm = (torch.softmax(bpm_logits, dim=-1) * self.bpm_centers).sum(-1)
        return {
            "genre": self.genre_head(fused),
            "emotion": self.emotion_head(fused),
            "mode": self.mode_head(fused),
            "bpm": bpm,
        }


# ---------------------------------------------------------------------------
# v4: v3 + 显式的 tempo（自相关）分支
# ---------------------------------------------------------------------------
class _TempoBranch(nn.Module):
    """从 mel 直接算“起音自相关”曲线（可微分，无参数）。

    步骤：频带平均 -> 正向差分（spectral flux）-> 去均值 -> FFT 自相关 ->
    在 55–200 BPM 的对数网格上插值采样。输出 ``[B, n_bins]`` 的 AC 值，
    第 i 维就是“以 bpm_grid[i] 为周期时，起音包络的周期性有多强”。

    为什么必须在这里做：``_ResBlock`` 每个都做 2 倍时间池化，mel 分支 4 个
    残差块后帧率只有 2.7 fps，Nyquist 上限约 81 BPM —— 80 BPM 以上的节拍
    在传到 BPM 头之前就被混叠掉了，网络无论怎么训都学不出来。自相关在原始
    分辨率上计算，不受后续池化影响。
    """

    def __init__(
        self,
        n_bins: int = 64,
        # 标签按 70–180 折叠（dsp_labels._fold_tempo），网格留一点余量；
        # 用 40–240 会把半速/双速的干扰峰也一起吃进来（实测裸 argmax MAE 38 vs 9.6）
        bpm_min: float = 55.0,
        bpm_max: float = 200.0,
        frame_rate: float = FRAME_RATE,
    ):
        super().__init__()
        self.frame_rate = float(frame_rate)
        grid = torch.logspace(
            math.log10(float(bpm_min)), math.log10(float(bpm_max)), int(n_bins)
        )
        self.register_buffer("bpm_grid", grid)

    def forward(self, mel: torch.Tensor) -> torch.Tensor:
        # FFT 在 fp16 下精度不足，这里统一转 fp32（开销可忽略）
        x = mel.float()
        energy = x.mean(dim=2)  # [B, 1, T] 频带平均后的响度包络
        if energy.shape[-1] < 8:
            return x.new_zeros((x.shape[0], self.bpm_grid.numel()))

        flux = F.relu(energy[:, :, 1:] - energy[:, :, :-1])
        flux = flux - flux.mean(dim=-1, keepdim=True)  # 去直流，否则 AC 被长周期主导

        n = flux.shape[-1]
        fft_len = 1 << int((2 * n - 1).bit_length())
        spec = torch.fft.rfft(flux, n=fft_len)
        power = spec.real * spec.real + spec.imag * spec.imag
        ac = torch.fft.irfft(power, n=fft_len)[..., :n]
        ac = ac / ac[..., :1].clamp_min(1e-6)  # 归一化到 AC[0] = 1

        # 60 * fps / bpm = 周期对应的帧数；线性插值取 AC
        lags = (60.0 * self.frame_rate) / self.bpm_grid
        lags = lags.clamp(1.0, float(n - 2))
        low = torch.floor(lags).long()
        frac = (lags - low.to(lags.dtype)).view(1, -1)
        sampled = ac[..., low] * (1.0 - frac) + ac[..., low + 1] * frac
        return sampled.squeeze(1)  # [B, 1, n_bins] -> [B, n_bins]


class ArtEvalNetV4(ArtEvalNetV3):
    """v3 主干 + tempo 分支；BPM 头同时看到池化特征和自相关曲线。"""

    arch = "v4"

    def __init__(
        self,
        n_genres: int = DEFAULT_GENRES,
        n_emotions: int = DEFAULT_EMOTIONS,
        n_modes: int = DEFAULT_MODES,
        tempo_bins: int = 64,
        **kwargs: Any,
    ):
        super().__init__(n_genres, n_emotions, n_modes, **kwargs)
        hidden = int(self.shared[1].out_features)
        dropout = float(self.shared[-1].p)

        self.tempo_branch = _TempoBranch(n_bins=int(tempo_bins))
        # 覆盖父类只吃 pooled 特征的 BPM 头
        self.bpm_trunk = nn.Sequential(
            nn.Linear(hidden + int(tempo_bins), hidden // 2),
            nn.GELU(),
            nn.Dropout(dropout / 3.0),
        )
        for module in (self.bpm_trunk[0], self.bpm_head):
            nn.init.trunc_normal_(module.weight, std=0.02)
            if module.bias is not None:
                nn.init.zeros_(module.bias)

    def forward(
        self, mel: torch.Tensor, chroma: torch.Tensor
    ) -> Dict[str, torch.Tensor]:
        mel_feat = self.mel_pool(self.mel_branch(mel))
        chroma_feat = self.chroma_pool(self.chroma_branch(chroma))
        fused = self.shared(torch.cat([mel_feat, chroma_feat], dim=1))
        fused = fused + self.shared_refine(fused)
        tempo_feat = self.tempo_branch(mel)
        bpm_logits = self.bpm_head(
            self.bpm_trunk(torch.cat([fused, tempo_feat], dim=1))
        )
        bpm = (torch.softmax(bpm_logits, dim=-1) * self.bpm_centers).sum(-1)
        return {
            "genre": self.genre_head(fused),
            "emotion": self.emotion_head(fused),
            "mode": self.mode_head(fused),
            "bpm": bpm,
        }


# ---------------------------------------------------------------------------
# v1 (legacy checkpoints)
# ---------------------------------------------------------------------------
def _legacy_block(in_ch: int, out_ch: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(in_ch, out_ch, 3, padding=1, bias=False),
        nn.BatchNorm2d(out_ch),
        nn.ReLU(inplace=True),
        nn.MaxPool2d(2),
    )


class LegacyNet(nn.Module):
    """Exact parameter layout of the pre-v2 checkpoints."""

    arch = "v1"

    def __init__(
        self,
        n_genres: int = DEFAULT_GENRES,
        n_emotions: int = DEFAULT_EMOTIONS,
        n_modes: int = DEFAULT_MODES,
    ):
        super().__init__()
        self.mel_branch = nn.Sequential(
            _legacy_block(1, 32),
            _legacy_block(32, 64),
            _legacy_block(64, 128),
            _legacy_block(128, 128),
        )
        self.chroma_branch = nn.Sequential(
            _legacy_block(1, 32),
            _legacy_block(32, 64),
            _legacy_block(64, 64),
        )
        self.shared = nn.Sequential(
            nn.Dropout(0.2),
            nn.Linear(128 + 64, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
        )
        self.genre_head = nn.Linear(256, n_genres)
        self.emotion_head = nn.Linear(256, n_emotions)
        self.mode_head = nn.Linear(256, n_modes)
        self.bpm_head = nn.Linear(256, 1)

    def forward(
        self, mel: torch.Tensor, chroma: torch.Tensor
    ) -> Dict[str, torch.Tensor]:
        mel_feat = F.adaptive_avg_pool2d(self.mel_branch(mel), 1).flatten(1)
        chroma_feat = F.adaptive_avg_pool2d(self.chroma_branch(chroma), 1).flatten(1)
        fused = self.shared(torch.cat([mel_feat, chroma_feat], dim=1))
        return {
            "genre": self.genre_head(fused),
            "emotion": self.emotion_head(fused),
            "mode": self.mode_head(fused),
            "bpm": self.bpm_head(fused).squeeze(-1),
        }


def build_model(
    arch: str = "v3",
    n_genres: int = DEFAULT_GENRES,
    n_emotions: int = DEFAULT_EMOTIONS,
    n_modes: int = DEFAULT_MODES,
) -> nn.Module:
    if arch == "v1":
        return LegacyNet(n_genres, n_emotions, n_modes)
    if arch == "v2":
        return ArtEvalNet(n_genres, n_emotions, n_modes)
    if arch == "v3":
        return ArtEvalNetV3(n_genres, n_emotions, n_modes)
    if arch == "v4":
        return ArtEvalNetV4(n_genres, n_emotions, n_modes)
    raise ValueError(f"unknown arch: {arch}")


def load_weights(
    model: nn.Module, state_dict: Dict[str, Any], *, verbose: bool = True
) -> Tuple[int, int]:
    """Shape-checked partial load; returns (loaded_tensors, skipped_tensors)."""
    target = model.state_dict()
    matched = {
        key: value
        for key, value in state_dict.items()
        if key in target and tuple(target[key].shape) == tuple(value.shape)
    }
    model.load_state_dict(matched, strict=False)
    skipped = len(state_dict) - len(matched)
    if verbose and matched:
        print(f"  loaded {len(matched)} tensors from checkpoint, skipped {skipped}")
    return len(matched), skipped
