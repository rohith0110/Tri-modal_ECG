"""Text encoders: TF-IDF + SVD (§5.4.1) and Bio-ClinicalBERT (§5.4.2).

Both are trained for every text-using task; the paper reports Bio-ClinicalBERT
as primary and TF-IDF in the supplementary (§5.4, `decision_phase2.yaml`).

The one rule both obey: **anything fitted is fitted on TRAIN only.** The TF-IDF
vocabulary and the SVD basis are fitted on the training split and frozen for
val and test, and the fitted object travels inside the checkpoint so an eval
run cannot silently refit on the split it is scoring.
"""

from __future__ import annotations

import pickle
from typing import Sequence

import numpy as np
import torch
import torch.nn as nn

EMBED_DIM = 512
HF_ID = "emilyalsentzer/Bio_ClinicalBERT"
# Recorded at first fetch, 2026-08-27; ships in the release package (§5.4.2).
HF_REVISION_SHA = "d5892b39a4adaed74b92212a44081509db72f87b"
BERT_HIDDEN = 768


class TfidfTextEncoder:
    """Feature extractor, not a network (§5.4.1) -- no gradients, no GPU.

        Vocabulary: 50,000 features over char n-grams (2,3,4) + word 1,2-grams
        Vectorizer: TfidfVectorizer(sublinear_tf=True, max_df=0.95, min_df=10)
        Projection: TruncatedSVD -> 512 dims

    Both stages are fitted on the TRAIN split and reused verbatim elsewhere.
    The per-task MLP head downstream is what actually trains.
    """

    def __init__(self, embed_dim: int = EMBED_DIM, max_features: int = 50_000,
                 random_state: int = 2026) -> None:
        self.embed_dim = embed_dim
        self.max_features = max_features
        self.random_state = random_state
        self.word_vectorizer = None
        self.char_vectorizer = None
        self.svd = None
        self.fitted_on_n_docs = 0

    def fit(self, texts: Sequence[str]) -> "TfidfTextEncoder":
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        docs = [str(t) for t in texts]
        # sklearn cannot mix char and word analysers in one vectoriser, so the
        # 50,000-feature budget is split between them and the two matrices are
        # stacked before the SVD. Same vocabulary size, same fit-on-train rule.
        half = max(1, self.max_features // 2)
        self.word_vectorizer = TfidfVectorizer(
            analyzer="word", ngram_range=(1, 2), max_features=half,
            sublinear_tf=True, max_df=0.95, min_df=10)
        self.char_vectorizer = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(2, 4), max_features=half,
            sublinear_tf=True, max_df=0.95, min_df=10)
        word = self.word_vectorizer.fit_transform(docs)
        char = self.char_vectorizer.fit_transform(docs)

        from scipy.sparse import hstack

        stacked = hstack([word, char]).tocsr()
        n_components = min(self.embed_dim, stacked.shape[1] - 1)
        self.svd = TruncatedSVD(n_components=n_components, random_state=self.random_state)
        self.svd.fit(stacked)
        self.fitted_on_n_docs = len(docs)
        return self

    def transform(self, texts: Sequence[str]) -> np.ndarray:
        if self.svd is None:
            raise RuntimeError("TfidfTextEncoder.transform before fit -- §5.4.1 requires "
                               "the vocabulary to be fitted on TRAIN before any split is "
                               "transformed")
        from scipy.sparse import hstack

        docs = [str(t) for t in texts]
        stacked = hstack([self.word_vectorizer.transform(docs),
                          self.char_vectorizer.transform(docs)]).tocsr()
        out = np.zeros((len(docs), self.embed_dim), dtype="float32")
        reduced = self.svd.transform(stacked).astype("float32")
        out[:, : reduced.shape[1]] = reduced
        return out

    # The fitted vectorisers travel inside checkpoint_best.pt so an eval run
    # cannot refit on the split it is scoring.
    def state_bytes(self) -> bytes:
        return pickle.dumps({"word": self.word_vectorizer, "char": self.char_vectorizer,
                             "svd": self.svd, "embed_dim": self.embed_dim,
                             "fitted_on_n_docs": self.fitted_on_n_docs})

    def load_state_bytes(self, blob: bytes) -> "TfidfTextEncoder":
        state = pickle.loads(blob)
        self.word_vectorizer = state["word"]
        self.char_vectorizer = state["char"]
        self.svd = state["svd"]
        self.embed_dim = state["embed_dim"]
        self.fitted_on_n_docs = state.get("fitted_on_n_docs", 0)
        return self


class TfidfPassthrough(nn.Module):
    """Adapter so a TF-IDF run plugs into the same fusion head as BERT.

    The dataset hands over the precomputed 512-d SVD vector; §5.4.1 says the
    embedding itself carries no trainable parameters, so this module only
    normalises the dtype. It exists to keep one model-assembly path.
    """

    def __init__(self, embed_dim: int = EMBED_DIM) -> None:
        super().__init__()
        self.embed_dim = embed_dim

    def forward(self, text_vec: torch.Tensor) -> torch.Tensor:
        return text_vec.to(dtype=torch.float32)

    def param_groups(self, backbone_lr: float, head_lr: float) -> list[dict]:
        return []


class BioClinicalBertEncoder(nn.Module):
    """Bio-ClinicalBERT with a [CLS] -> Linear(768, 512) head (§5.4.2).

    Fine-tuning policy: full backbone trainable with discriminative LRs --
    transformer layers 1e-5, word/position embeddings 1e-6, head 1e-3.
    """

    def __init__(self, embed_dim: int = EMBED_DIM, hf_id: str = HF_ID,
                 pretrained: bool = True) -> None:
        super().__init__()
        from transformers import AutoConfig, AutoModel

        if pretrained:
            self.bert = AutoModel.from_pretrained(hf_id)
        else:
            # Offline smoke path only; every run records which branch it took.
            self.bert = AutoModel.from_config(AutoConfig.from_pretrained(hf_id))
        self.pretrained = bool(pretrained)
        self.hf_id = hf_id
        self.hf_revision_sha = HF_REVISION_SHA if pretrained else "random_init"
        self.projection = nn.Linear(self.bert.config.hidden_size, embed_dim)
        nn.init.kaiming_normal_(self.projection.weight, nonlinearity="relu")
        nn.init.zeros_(self.projection.bias)
        self.embed_dim = embed_dim

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        out = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        cls = out.last_hidden_state[:, 0]          # [CLS], last layer (§5.4.2)
        return self.projection(cls)

    def param_groups(self, backbone_lr: float, head_lr: float,
                     embedding_lr: float | None = None) -> list[dict]:
        embedding_lr = embedding_lr if embedding_lr is not None else backbone_lr / 10.0
        embeddings = list(self.bert.embeddings.parameters())
        embedding_ids = {id(p) for p in embeddings}
        head = list(self.projection.parameters())
        head_ids = {id(p) for p in head}
        layers = [p for p in self.bert.parameters() if id(p) not in embedding_ids]
        return [
            {"params": embeddings, "lr": embedding_lr, "name": "text_embeddings"},
            {"params": layers, "lr": backbone_lr, "name": "text_layers"},
            {"params": head, "lr": head_lr, "name": "text_head"},
        ]


def _self_check() -> None:
    """TF-IDF fits on train only and BERT emits a 512-d [CLS] embedding."""
    train = ["sinus bradycardia", "normal sinus rhythm", "atrial fibrillation",
             "left axis deviation", "right bundle branch block"] * 20
    test = ["sinus tachycardia", "normal sinus rhythm"]

    encoder = TfidfTextEncoder(embed_dim=32).fit(train)
    train_vec, test_vec = encoder.transform(train), encoder.transform(test)
    assert train_vec.shape == (len(train), 32), train_vec.shape
    assert test_vec.shape == (2, 32), test_vec.shape
    assert np.isfinite(test_vec).all()

    restored = TfidfTextEncoder().load_state_bytes(encoder.state_bytes())
    assert np.allclose(restored.transform(test), test_vec), \
        "a round-tripped TF-IDF encoder does not reproduce its own features"

    fresh = TfidfTextEncoder(embed_dim=32)
    try:
        fresh.transform(test)
    except RuntimeError as exc:
        assert "before fit" in str(exc)
    else:                                                   # pragma: no cover
        raise AssertionError("transform before fit was allowed")

    bert = BioClinicalBertEncoder(pretrained=True)
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(HF_ID)
    batch = tokenizer(test, max_length=32, truncation=True, padding="max_length",
                      return_tensors="pt")
    with torch.no_grad():
        out = bert(batch["input_ids"], batch["attention_mask"])
    assert out.shape == (2, EMBED_DIM), out.shape
    groups = bert.param_groups(1e-5, 1e-3, 1e-6)
    assert [g["name"] for g in groups] == ["text_embeddings", "text_layers", "text_head"]
    assert [g["lr"] for g in groups] == [1e-6, 1e-5, 1e-3]
    total = sum(p.numel() for g in groups for p in g["params"])
    assert total == sum(p.numel() for p in bert.parameters()), "a parameter is in no group"
    print(f"text_encoders self-check: PASS  (BERT {total/1e6:.1f} M params, "
          f"rev {bert.hf_revision_sha[:12]}, TF-IDF fitted on {encoder.fitted_on_n_docs} docs)")


if __name__ == "__main__":
    _self_check()
