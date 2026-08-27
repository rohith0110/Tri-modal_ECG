"""Determinism controls (spec §6.2) and RNG capture for resume (§6.9).

    set_seed(42)          # before anything random happens
    state = rng_state()   # into checkpoint_last.pt
    load_rng_state(state) # after a crash / preemption

``cudnn.benchmark = False`` costs 5-15 % throughput and is required: with
benchmark on, cuDNN picks a convolution algorithm from wall-clock timings, so
two runs of the same command can take different code paths and diverge.
"""

from __future__ import annotations

import os
import random
from typing import Any

import numpy as np
import torch

SEEDS = (42, 123, 456)      # §6.2 / Round 1.4 -- every task x arch


def set_seed(seed: int) -> None:
    """Seed every generator Phase 2 touches, and pin the deterministic path."""
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    # §8.1: TF32 on Ampere+; the non-determinism it introduces is bounded and
    # reproducible across runs, unlike a benchmarked algorithm choice.
    torch.set_float32_matmul_precision("high")


def rng_state() -> dict[str, Any]:
    """Everything needed to resume the exact stochastic trajectory (§6.9)."""
    return {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch": torch.get_rng_state(),
        "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
    }


def _byte_tensor(value: Any) -> torch.Tensor:
    return torch.as_tensor(value).detach().to(device="cpu", dtype=torch.uint8)


def load_rng_state(state: dict[str, Any] | None) -> None:
    if not state:
        return
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    # A checkpoint loaded with map_location="cuda" brings the RNG tensors back on
    # the GPU; set_rng_state insists on a CPU ByteTensor.
    torch.set_rng_state(_byte_tensor(state["torch"]))
    if state.get("cuda") and torch.cuda.is_available():
        try:
            torch.cuda.set_rng_state_all([_byte_tensor(s) for s in state["cuda"]])
        except (RuntimeError, ValueError):
            # A requeued job can land on a node with a different GPU count. The
            # CPU streams still restore, which is what drives shuffling and
            # dropout; losing the CUDA stream is a documented, bounded loss.
            pass


def environment_fingerprint() -> dict[str, str]:
    """Versions the reproducibility audit (§1.2) has to name."""
    import platform

    import torchvision

    fingerprint = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "torch": torch.__version__,
        "torchvision": torchvision.__version__,
        "cuda_available": str(torch.cuda.is_available()),
        "cuda_version": str(torch.version.cuda),
        "cudnn_version": str(torch.backends.cudnn.version()),
        "numpy": np.__version__,
    }
    if torch.cuda.is_available():
        fingerprint["gpu"] = torch.cuda.get_device_name(0)
        fingerprint["gpu_capability"] = ".".join(
            str(x) for x in torch.cuda.get_device_capability(0))
    try:
        import transformers

        fingerprint["transformers"] = transformers.__version__
    except ImportError:                                      # pragma: no cover
        pass
    # torch.__version__ is a TorchVersion, not a str; yaml.safe_dump refuses it.
    return {key: str(value) for key, value in fingerprint.items()}


def autocast_dtype() -> tuple[torch.dtype | None, str]:
    """§6.6 / §8.1: bf16 where supported, else fp16 + GradScaler, else off."""
    if not torch.cuda.is_available():
        return None, "fp32_cpu"
    if torch.cuda.is_bf16_supported():
        return torch.bfloat16, "bf16"
    return torch.float16, "fp16_gradscaler"


def _self_check() -> None:
    set_seed(42)
    first = (random.random(), float(np.random.rand()), float(torch.rand(1)))
    state = rng_state()
    second = (random.random(), float(np.random.rand()), float(torch.rand(1)))
    assert first != second
    load_rng_state(state)
    restored = (random.random(), float(np.random.rand()), float(torch.rand(1)))
    assert restored == second, (
        f"RNG restore did not reproduce the next draws: {restored} != {second} -- "
        "a resumed run would not follow the interrupted trajectory (§6.9)"
    )
    assert torch.backends.cudnn.deterministic and not torch.backends.cudnn.benchmark

    set_seed(42)
    again = (random.random(), float(np.random.rand()), float(torch.rand(1)))
    assert again == first, "set_seed is not reproducible"

    dtype, tag = autocast_dtype()
    print(f"  mixed precision resolves to: {tag} ({dtype})")
    print("  env:", {k: v for k, v in environment_fingerprint().items()
                     if k in ("python", "torch", "cuda_version", "gpu")})
    print("seed self-check: PASS")


if __name__ == "__main__":
    _self_check()
