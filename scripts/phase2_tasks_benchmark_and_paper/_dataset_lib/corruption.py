"""Train-time signal corruption for B2 regime_2 (spec §7.3).

The eight corruption families are NOT reimplemented here. They are imported
from the Phase 1 Stage 8 script that generated the frozen test set, so the
regime_2 augmenter draws from exactly the same distribution the test rows were
drawn from. A reimplementation would be a second definition of the same
physics, and any drift between the two would silently invalidate the
regime_1-vs-regime_2 comparison, which is B2's whole claim.

Only the SEED STREAM differs. ``config/corruption_recipes_LOCKED.yaml``
requires the train-time key to carry a literal ``regime2|`` prefix plus the run
seed and the epoch, so no train-time realisation can equal a locked test
realisation for the same (study, family, snr) -- the model cannot memorise the
test set's noise.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STAGE8_SCRIPT = (PROJECT_ROOT / "scripts" / "phase1_dataset_generation"
                 / "50_build_signals_corrupted.py")

SNR_LEVELS_DB = (30, 20, 10, 5, 0)
SEED_MODULUS = 2_147_483_648      # 2**31, per the recipe file's rng block


@lru_cache(maxsize=1)
def _stage8() -> Any:
    """Import the Stage 8 module by path -- its filename starts with a digit."""
    if not STAGE8_SCRIPT.exists():
        raise FileNotFoundError(
            f"Phase 1 Stage 8 script not found at {STAGE8_SCRIPT}. The regime_2 "
            "augmenter must reuse its corruption functions, not reimplement them."
        )
    # The Stage 8 script imports its sibling `_stage1_common`, which is only
    # importable from inside the Phase 1 script directory.
    stage1_dir = str(STAGE8_SCRIPT.parent)
    if stage1_dir not in sys.path:
        sys.path.insert(0, stage1_dir)
    spec = importlib.util.spec_from_file_location("_phase1_stage8", STAGE8_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # The Stage 8 module configures logging and touches disk only under
    # __main__, so a plain import is side-effect free.
    sys.modules["_phase1_stage8"] = module
    spec.loader.exec_module(module)
    return module


def families() -> tuple[str, ...]:
    return tuple(_stage8().CORRUPTIONS)


def train_seed(run_seed: int, epoch: int, study_id: int, family: str, snr_db: int) -> int:
    """The ``train_augmentation`` key from corruption_recipes_LOCKED.yaml."""
    key = f"regime2|{run_seed}|{epoch}|{study_id}|{family}|{snr_db}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(key).digest()[:4], "big") % SEED_MODULUS


def corrupt(signal: np.ndarray, family: str, snr_db: int,
            rng: np.random.Generator) -> np.ndarray:
    """Apply one locked corruption family. Delegates to the Stage 8 function."""
    fns = _stage8().CORRUPT_FN
    if family not in fns:
        raise ValueError(f"unknown corruption family {family!r}; the eight are {families()}")
    return np.asarray(fns[family](np.asarray(signal, dtype=np.float32), int(snr_db), rng),
                      dtype=np.float32)


def augment_regime_2(signal: np.ndarray, study_id: int, *, run_seed: int, epoch: int,
                     p_corrupt: float = 0.5) -> tuple[np.ndarray, str | None, int]:
    """Draw the regime_2 augmentation for one training sample.

    Policy (``regimes.regime_2.augmentation_policy``, progress-doc question 12
    default): corrupt with p = 0.5, family uniform over all 8, SNR uniform over
    the five-step ladder. Returns ``(signal, family_or_None, snr_db_or_-1)``.
    """
    # The decision RNG is keyed on the same stream as the realisation, so a
    # resumed epoch reproduces both the coin flip and the noise.
    decide = np.random.default_rng(train_seed(run_seed, epoch, study_id, "decide", -1))
    if decide.random() >= p_corrupt:
        return np.asarray(signal, dtype=np.float32), None, -1
    fam = str(families()[int(decide.integers(0, len(families())))])
    snr = int(SNR_LEVELS_DB[int(decide.integers(0, len(SNR_LEVELS_DB)))])
    rng = np.random.default_rng(train_seed(run_seed, epoch, study_id, fam, snr))
    return corrupt(signal, fam, snr, rng), fam, snr


def _self_check() -> None:
    """Determinism, disjointness from the test stream, and a real SNR check."""
    import yaml

    recipes = yaml.safe_load(
        (PROJECT_ROOT / "config" / "corruption_recipes_LOCKED.yaml").read_text(encoding="utf-8")
    )
    assert tuple(recipes["families"]) == families(), (
        f"family list drifted: yaml {tuple(recipes['families'])} vs stage 8 {families()}"
    )
    assert tuple(recipes["snr_levels_db"]) == SNR_LEVELS_DB

    rng = np.random.default_rng(0)
    sig = rng.standard_normal(5000).astype(np.float32)

    # Additive families must realise the requested SNR to within rounding.
    for family in ("gaussian", "baseline_wander", "powerline", "emg", "electrode_motion"):
        for snr in SNR_LEVELS_DB:
            out = corrupt(sig, family, snr, np.random.default_rng(7))
            noise = out - sig
            realised = 10 * np.log10(np.mean(sig**2) / max(np.mean(noise**2), 1e-30))
            assert abs(realised - snr) < 0.5, f"{family} @ {snr} dB realised {realised:.2f} dB"

    # Same key -> same bytes; different epoch -> different bytes.
    a = augment_regime_2(sig, 40000035, run_seed=42, epoch=0)
    b = augment_regime_2(sig, 40000035, run_seed=42, epoch=0)
    c = augment_regime_2(sig, 40000035, run_seed=42, epoch=1)
    assert np.array_equal(a[0], b[0]) and a[1:] == b[1:], "regime_2 augmentation is not reproducible"
    assert not (np.array_equal(a[0], c[0]) and a[1:] == c[1:]), "epoch does not change the stream"

    # The train stream must never collide with the frozen test stream.
    test_seed = int.from_bytes(
        hashlib.sha256(b"40000035|gaussian|10").digest()[:4], "big") % SEED_MODULUS
    assert train_seed(42, 0, 40000035, "gaussian", 10) != test_seed, (
        "train_augmentation seed collides with the frozen test seed"
    )

    corrupted = sum(augment_regime_2(sig, sid, run_seed=42, epoch=0)[1] is not None
                    for sid in range(4000))
    assert 1800 < corrupted < 2200, f"p_corrupt=0.5 realised {corrupted / 4000:.3f}"
    print(f"corruption self-check: PASS  ({len(families())} families, "
          f"realised p_corrupt={corrupted / 4000:.3f})")


if __name__ == "__main__":
    _self_check()
