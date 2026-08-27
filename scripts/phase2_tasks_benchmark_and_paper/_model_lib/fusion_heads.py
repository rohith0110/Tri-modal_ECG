"""Late-concat fusion head (spec §5.5) and the small MLP heads it feeds.

    Concat:  [sig_emb, img_emb, txt_emb, presence_mask_3] -> (B, 1539)
    MLP:     Linear(1539, 1024) + GELU + Dropout(0.2) +
             Linear(1024, 512)  + GELU + Dropout(0.2) +
             Linear(512, task_out)

One head class serves every multimodal task; only the final ``task_out`` layer
differs. A missing modality contributes an all-zeros embedding and a zero
presence bit, so the head can tell "absent" from "present and near zero".

The single-modality tiers (§5.6's "where signal-only is the only allowed input,
no fusion head is used") route through :class:`UnimodalMLP` instead -- the same
two-hidden-layer geometry over one 512-d embedding, so a signal-only result and
a fusion result differ in inputs rather than in head capacity.
"""

from __future__ import annotations

import torch
import torch.nn as nn

EMBED_DIM = 512
N_MODALITIES = 3
CONCAT_DIM = N_MODALITIES * EMBED_DIM + N_MODALITIES      # 1539, per §5.5
HIDDEN_DIMS = (1024, 512)
DROPOUT = 0.2


def _mlp(in_dim: int, hidden_dims, out_dim: int, dropout: float) -> nn.Sequential:
    layers: list[nn.Module] = []
    width = in_dim
    for hidden in hidden_dims:
        layers += [nn.Linear(width, hidden), nn.GELU(), nn.Dropout(dropout)]
        width = hidden
    layers.append(nn.Linear(width, out_dim))
    return nn.Sequential(*layers)


class LateFusionMLP(nn.Module):
    """The locked fusion head. ``task_out`` is the only per-task difference."""

    def __init__(self, task_out: int, embed_dim: int = EMBED_DIM,
                 hidden_dims=HIDDEN_DIMS, dropout: float = DROPOUT) -> None:
        super().__init__()
        self.embed_dim = embed_dim
        self.concat_dim = N_MODALITIES * embed_dim + N_MODALITIES
        self.mlp = _mlp(self.concat_dim, hidden_dims, task_out, dropout)

    def forward(self, signal_emb: torch.Tensor | None, image_emb: torch.Tensor | None,
                text_emb: torch.Tensor | None, presence: torch.Tensor) -> torch.Tensor:
        reference = next(e for e in (signal_emb, image_emb, text_emb, presence)
                         if e is not None)
        batch = reference.shape[0]
        zeros = torch.zeros(batch, self.embed_dim, dtype=reference.dtype,
                            device=reference.device)
        parts = [signal_emb if signal_emb is not None else zeros,
                 image_emb if image_emb is not None else zeros,
                 text_emb if text_emb is not None else zeros,
                 presence.to(dtype=reference.dtype)]
        return self.mlp(torch.cat(parts, dim=1))


class UnimodalMLP(nn.Module):
    """Task head for the single-modality tiers -- same geometry, one input."""

    def __init__(self, task_out: int, in_dim: int = EMBED_DIM,
                 hidden_dims=HIDDEN_DIMS, dropout: float = DROPOUT) -> None:
        super().__init__()
        self.mlp = _mlp(in_dim, hidden_dims, task_out, dropout)

    def forward(self, embedding: torch.Tensor) -> torch.Tensor:
        return self.mlp(embedding)


class EmbeddingSimilarityHead(nn.Module):
    """The §4.A.5.7 / §4.B.4.7 'cosine similarity between frozen embeddings'
    baseline tier, expressed as a head so it shares the trainer stack.

    The only learned parameters are a scale and a bias on the mean pairwise
    cosine similarity of whichever modalities the run reads -- a calibrated
    similarity threshold rather than a learned decision boundary.
    """

    def __init__(self) -> None:
        super().__init__()
        self.scale = nn.Parameter(torch.tensor(10.0))
        self.bias = nn.Parameter(torch.tensor(0.0))

    def forward(self, signal_emb, image_emb, text_emb, presence) -> torch.Tensor:
        available = [e for e in (signal_emb, image_emb, text_emb) if e is not None]
        if len(available) < 2:
            raise ValueError("the similarity baseline needs at least two modalities")
        sims = []
        for i in range(len(available)):
            for j in range(i + 1, len(available)):
                sims.append(torch.cosine_similarity(available[i], available[j], dim=1))
        return (self.scale * torch.stack(sims, dim=1).mean(dim=1) + self.bias).unsqueeze(1)


def _self_check() -> None:
    torch.manual_seed(0)
    head = LateFusionMLP(task_out=5)
    assert head.concat_dim == CONCAT_DIM, head.concat_dim

    batch = 4
    embeddings = [torch.randn(batch, EMBED_DIM) for _ in range(3)]
    presence = torch.ones(batch, N_MODALITIES)
    full = head(*embeddings, presence)
    assert full.shape == (batch, 5), full.shape

    # A dropped modality must change the output AND still run.
    presence_no_text = presence.clone()
    presence_no_text[:, 2] = 0.0
    dropped = head(embeddings[0], embeddings[1], None, presence_no_text)
    assert dropped.shape == (batch, 5)
    assert not torch.allclose(full, dropped), "dropping text did not change the output"

    uni = UnimodalMLP(task_out=3)
    assert uni(embeddings[0]).shape == (batch, 3)

    sim = EmbeddingSimilarityHead()
    assert sim(embeddings[0], embeddings[1], embeddings[2], presence).shape == (batch, 1)
    # An anchor-aligned triple must score above a mismatched one.
    aligned = embeddings[0]
    same = sim(aligned, aligned, aligned, presence).mean()
    different = sim(embeddings[0], embeddings[1], embeddings[2], presence).mean()
    assert same > different, "cosine baseline does not prefer an aligned triple"

    print(f"fusion_heads self-check: PASS  (concat_dim={head.concat_dim}, "
          f"{sum(p.numel() for p in head.parameters())/1e6:.2f} M params)")


if __name__ == "__main__":
    _self_check()
