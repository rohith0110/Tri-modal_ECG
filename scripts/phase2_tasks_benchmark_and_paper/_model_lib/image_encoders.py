"""ImageNet-pretrained ResNet-50 image encoder (spec §5.3).

    Input:    (B, 3, H, W) -- 224x672 Lead-II strip or 384x512 12-lead grid
    Backbone: torchvision.models.resnet50(weights=IMAGENET1K_V2)
    Head:     final fc replaced with Linear(2048, 512)
    Output:   (B, 512)

Fine-tuning policy (§5.3, §6.3): all layers trainable, backbone at LR 1e-5 and
the new fc at 1e-3. :meth:`param_groups` hands the trainer that split so no
caller has to re-derive which tensors are "backbone".

Preprocessing lives in `_dataset_lib/task_dataset.build_image_transform`, next
to the loader that applies it, and is documented there -- including the one
deviation from §5.3's centre-crop, which would have cropped away 37 % of a
Lead-II strip given the real render aspect ratios.
"""

from __future__ import annotations

import torch
import torch.nn as nn

EMBED_DIM = 512
BACKBONE_FEATURES = 2048


class ImageResNet50(nn.Module):
    """The locked image backbone.

    Args:
        embed_dim: output width; 512 everywhere in Phase 2.
        pretrained: load IMAGENET1K_V2 weights (§5.3). Only a smoke test with
            no network should pass False, and it must say so in its run config.
    """

    def __init__(self, embed_dim: int = EMBED_DIM, pretrained: bool = True) -> None:
        super().__init__()
        from torchvision.models import ResNet50_Weights, resnet50

        weights = ResNet50_Weights.IMAGENET1K_V2 if pretrained else None
        self.backbone = resnet50(weights=weights)
        self.pretrained = bool(pretrained)
        self.weights_tag = "IMAGENET1K_V2" if pretrained else "random_init"
        self.backbone.fc = nn.Linear(BACKBONE_FEATURES, embed_dim)
        nn.init.kaiming_normal_(self.backbone.fc.weight, nonlinearity="relu")
        nn.init.zeros_(self.backbone.fc.bias)
        self.embed_dim = embed_dim

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.dim() != 4 or x.shape[1] != 3:
            raise ValueError(f"expected (B, 3, H, W), got {tuple(x.shape)}")
        return self.backbone(x)

    def param_groups(self, backbone_lr: float, head_lr: float) -> list[dict]:
        """§5.3 discriminative LRs: pretrained trunk slow, new fc fast."""
        head = list(self.backbone.fc.parameters())
        head_ids = {id(p) for p in head}
        trunk = [p for p in self.backbone.parameters() if id(p) not in head_ids]
        return [{"params": trunk, "lr": backbone_lr, "name": "image_backbone"},
                {"params": head, "lr": head_lr, "name": "image_head"}]


def _self_check() -> None:
    """Both locked input geometries, and the LR split."""
    torch.manual_seed(0)
    model = ImageResNet50(pretrained=False)          # offline-safe for the check
    for height, width in ((224, 672), (384, 512)):
        out = model(torch.randn(2, 3, height, width))
        assert out.shape == (2, EMBED_DIM), out.shape
        print(f"  {height}x{width} -> {tuple(out.shape)}")

    groups = model.param_groups(1e-5, 1e-3)
    assert [g["name"] for g in groups] == ["image_backbone", "image_head"]
    assert groups[0]["lr"] == 1e-5 and groups[1]["lr"] == 1e-3
    n_head = sum(p.numel() for p in groups[1]["params"])
    assert n_head == BACKBONE_FEATURES * EMBED_DIM + EMBED_DIM, n_head
    total = sum(p.numel() for g in groups for p in g["params"])
    assert total == sum(p.numel() for p in model.parameters()), "a parameter is in no group"
    print(f"image_encoders self-check: PASS  ({total/1e6:.1f} M params, "
          f"{n_head/1e6:.2f} M in the head)")


if __name__ == "__main__":
    _self_check()
