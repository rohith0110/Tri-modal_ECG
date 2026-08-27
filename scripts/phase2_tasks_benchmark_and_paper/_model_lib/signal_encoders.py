"""1D ResNet-18 signal encoder (spec §5.2, locked by `decision_phase2.yaml`).

    Input:   (B, n_leads, 5000) float32, n_leads in {1, 12}
    Stem:    Conv1d(n_leads, 64, k=15, s=2, p=7) + BN + ReLU + MaxPool1d(3, s=2)
    Stage 1: 2 x BasicBlock1D(64,  64,  stride=1)
    Stage 2: 2 x BasicBlock1D(64,  128, stride=2)
    Stage 3: 2 x BasicBlock1D(128, 256, stride=2)
    Stage 4: 2 x BasicBlock1D(256, 512, stride=2)
    Head:    AdaptiveAvgPool1d(1) -> flatten -> Linear(512, 512)
    Output:  (B, 512)

Trained from scratch, Kaiming-normal init. The 1-lead and 12-lead
instantiations are the same class and share no weights -- Track-1 and Track-2
are independent runs per seed.

``forward(..., return_sequence=True)`` also returns the pre-pool feature map,
which the A4 / B3 localisation heads decode back to sample and bin resolution.
"""

from __future__ import annotations

import torch
import torch.nn as nn

EMBED_DIM = 512
KERNEL_SIZE = 7          # the two convs inside a BasicBlock1D
STEM_KERNEL = 15


class BasicBlock1D(nn.Module):
    """Standard 2-conv ResNet basic block, 1-D. Stride is applied to conv1 only."""

    expansion = 1

    def __init__(self, in_channels: int, out_channels: int, stride: int = 1) -> None:
        super().__init__()
        padding = KERNEL_SIZE // 2
        self.conv1 = nn.Conv1d(in_channels, out_channels, KERNEL_SIZE, stride=stride,
                               padding=padding, bias=False)
        self.bn1 = nn.BatchNorm1d(out_channels)
        self.conv2 = nn.Conv1d(out_channels, out_channels, KERNEL_SIZE, stride=1,
                               padding=padding, bias=False)
        self.bn2 = nn.BatchNorm1d(out_channels)
        self.relu = nn.ReLU(inplace=True)
        self.downsample: nn.Module | None = None
        if stride != 1 or in_channels != out_channels:
            self.downsample = nn.Sequential(
                nn.Conv1d(in_channels, out_channels, 1, stride=stride, bias=False),
                nn.BatchNorm1d(out_channels),
            )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        identity = x if self.downsample is None else self.downsample(x)
        out = self.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        return self.relu(out + identity)


class ECGResNet1D18(nn.Module):
    """The locked signal backbone. ``n_leads`` selects Track-1 vs Track-2."""

    STAGES = ((64, 64, 1), (64, 128, 2), (128, 256, 2), (256, 512, 2))

    def __init__(self, n_leads: int = 1, embed_dim: int = EMBED_DIM) -> None:
        super().__init__()
        if n_leads not in (1, 12):
            raise ValueError(f"n_leads must be 1 or 12 (§5.2 lead_subsets), got {n_leads}")
        self.n_leads = n_leads
        self.embed_dim = embed_dim

        self.stem = nn.Sequential(
            nn.Conv1d(n_leads, 64, STEM_KERNEL, stride=2, padding=STEM_KERNEL // 2, bias=False),
            nn.BatchNorm1d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool1d(3, stride=2, padding=1),
        )
        self.stages = nn.Sequential(*[
            nn.Sequential(BasicBlock1D(in_c, out_c, stride=stride),
                          BasicBlock1D(out_c, out_c, stride=1))
            for in_c, out_c, stride in self.STAGES
        ])
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.projection = nn.Linear(512, embed_dim)
        self._init_weights()

    def _init_weights(self) -> None:
        for module in self.modules():
            if isinstance(module, nn.Conv1d):
                nn.init.kaiming_normal_(module.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(module, nn.BatchNorm1d):
                nn.init.ones_(module.weight)
                nn.init.zeros_(module.bias)
            elif isinstance(module, nn.Linear):
                nn.init.kaiming_normal_(module.weight, nonlinearity="relu")
                nn.init.zeros_(module.bias)

    def forward(self, x: torch.Tensor, return_sequence: bool = False):
        if x.dim() != 3 or x.shape[1] != self.n_leads:
            raise ValueError(
                f"expected (B, {self.n_leads}, 5000), got {tuple(x.shape)}. "
                "read_modality returns CHANNEL-major arrays; a transposed read "
                "trains silently on the wrong axis (progress-doc trap 10)."
            )
        features = self.stages(self.stem(x))              # (B, 512, L')
        embedding = self.projection(self.pool(features).flatten(1))
        if return_sequence:
            return embedding, features
        return embedding


class DenseDecoder1D(nn.Module):
    """Upsample the backbone feature map back to per-sample resolution (A4).

    §5.6 gives A4 a per-sample sigmoid over 5,000 samples plus onset/offset
    regression. The backbone downsamples by 32, so a light three-step
    transposed-conv decoder brings 512 channels at L/32 back to ``out_channels``
    at L, and a final interpolation absorbs the rounding.
    """

    def __init__(self, in_channels: int = 512, out_channels: int = 3,
                 hidden: int = 128, n_samples: int = 5000) -> None:
        super().__init__()
        self.n_samples = n_samples
        self.blocks = nn.Sequential(
            nn.ConvTranspose1d(in_channels, hidden, 4, stride=4), nn.BatchNorm1d(hidden),
            nn.ReLU(inplace=True),
            nn.ConvTranspose1d(hidden, hidden, 4, stride=4), nn.BatchNorm1d(hidden),
            nn.ReLU(inplace=True),
            nn.ConvTranspose1d(hidden, hidden, 2, stride=2), nn.BatchNorm1d(hidden),
            nn.ReLU(inplace=True),
        )
        self.out = nn.Conv1d(hidden, out_channels, 1)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        x = self.out(self.blocks(features))
        if x.shape[-1] != self.n_samples:
            x = nn.functional.interpolate(x, size=self.n_samples, mode="linear",
                                          align_corners=False)
        return x                                           # (B, out_channels, 5000)


class BinPooler(nn.Module):
    """Pool the backbone feature map into 10 one-second bins (B3, §4.B.3.3)."""

    def __init__(self, in_channels: int = 512, n_bins: int = 10) -> None:
        super().__init__()
        self.pool = nn.AdaptiveAvgPool1d(n_bins)
        self.in_channels = in_channels

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.pool(features).transpose(1, 2)         # (B, n_bins, C)


def _self_check() -> None:
    """Shapes, parameter count, and the transposed-input guard."""
    torch.manual_seed(0)
    for n_leads in (1, 12):
        model = ECGResNet1D18(n_leads=n_leads)
        x = torch.randn(2, n_leads, 5000)
        embedding, features = model(x, return_sequence=True)
        assert embedding.shape == (2, EMBED_DIM), embedding.shape
        assert features.shape[1] == 512, features.shape
        n_params = sum(p.numel() for p in model.parameters())
        print(f"  n_leads={n_leads:2d}  embed={tuple(embedding.shape)}  "
              f"seq={tuple(features.shape)}  params={n_params/1e6:.2f} M")

        dense = DenseDecoder1D()(features)
        assert dense.shape == (2, 3, 5000), dense.shape
        bins = BinPooler()(features)
        assert bins.shape == (2, 10, 512), bins.shape

    try:
        ECGResNet1D18(n_leads=12)(torch.randn(2, 5000, 12))
    except ValueError as exc:
        assert "CHANNEL-major" in str(exc)
    else:                                                   # pragma: no cover
        raise AssertionError("sample-major input was accepted -- trap 10 is unguarded")

    print("signal_encoders self-check: PASS")


if __name__ == "__main__":
    _self_check()
