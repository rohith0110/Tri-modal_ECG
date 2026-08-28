"""Convert signal HDF5 shards to int16 + per-record scale (spec §8.2 note).

    ./ecg_env/Scripts/python.exe scripts/dgx_portability/make_int16.py convert \
        --kinds preprocessed_12lead
    ./ecg_env/Scripts/python.exe scripts/dgx_portability/make_int16.py verify \
        --kinds preprocessed_12lead
    ./ecg_env/Scripts/python.exe scripts/dgx_portability/make_int16.py selfcheck

§8.2: "signals are staged as int16 with a per-record scale factor rather than
float32 (56.7 GB instead of 141.8 GB for the 12-lead preprocessed set)".

**Per record, not per dataset.** Each study gets its own
``scale = max(|x|) / 32767``, so a low-amplitude recording keeps the full 16-bit
resolution instead of being crushed against a global maximum set by the loudest
strip in the cohort. Reconstruction is ``x = code * scale`` and the worst case
error is half a quantisation step, ``scale / 2``.

**One file at a time, atomically.** Each shard is written to a temp file and
renamed only once it is complete and its checksum recorded, so a power cut costs
exactly the shard in flight -- never a half-written file that looks finished. A
shard already present in the manifest is skipped.

This is a STORAGE change, not a precision change, and the claim is checked
rather than asserted: `convert` measures the round-trip error on every shard it
writes and `verify` re-measures it from disk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / "phase2_tasks_benchmark_and_paper"
sys.path.insert(0, str(SCRIPTS))

from _dataset_lib import build_common as bc                            # noqa: E402
from _dataset_lib import modality as mod                               # noqa: E402

STAGE = "P2.5"
SIGNALS = bc.DATA_PROCESSED / "signals"
OUT_DIR = bc.DATA_PROCESSED / "signals_int16"
MANIFEST = OUT_DIR / "int16_manifest.json"
INT16_MAX = 32767

# Which files back each modality kind. Read off the modality manifest so this
# never drifts from what the loader actually opens.
def shards_for(kind: str) -> list[Path]:
    import pandas as pd

    manifest = pd.read_parquet(mod.MANIFEST_PATH, columns=["modality_kind", "container_path"])
    paths = sorted(manifest[manifest["modality_kind"] == kind]["container_path"].unique())
    if not paths:
        raise SystemExit(f"no container files for modality kind {kind!r}")
    return [bc.DATA_PROCESSED / p for p in paths]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest() -> dict[str, Any]:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"files": {}, "int16_max": INT16_MAX,
            "scheme": "per-record: code = rint(x / scale), scale = max(|x|) / 32767"}


def save_manifest(manifest: dict[str, Any]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    bc.atomic_replace(tmp, MANIFEST)


def convert_shard(source: Path, target: Path, log, rows_per_block: int = 256) -> dict[str, Any]:
    """One shard -> int16 + scale, streamed in blocks, with error measured."""
    import h5py

    tmp = target.with_suffix(".h5.tmp")
    if tmp.exists():
        tmp.unlink()

    started = time.time()
    worst_abs = 0.0
    worst_exact = 0.0
    worst_rel_to_step = 0.0
    total_sq = 0.0
    total_n = 0
    peak_max = 0.0

    with h5py.File(source, "r") as src, h5py.File(tmp, "w") as dst:
        data = src["signal"]
        n_rows = data.shape[0]
        out = dst.create_dataset(
            "signal", shape=data.shape, dtype="int16",
            chunks=data.chunks, compression="gzip", compression_opts=4)
        scale = dst.create_dataset("scale", shape=(n_rows,), dtype="float32")
        for name in ("study_id", "subject_id"):
            if name in src:
                dst.create_dataset(name, data=src[name][:], dtype=src[name].dtype)

        for start in range(0, n_rows, rows_per_block):
            stop = min(start + rows_per_block, n_rows)
            block = np.asarray(data[start:stop], dtype="float32")
            # max over every axis but the record axis
            axes = tuple(range(1, block.ndim))
            peak = np.abs(block).max(axis=axes)
            factor = np.where(peak > 0, peak / INT16_MAX, 1.0).astype("float32")
            shaped = factor.reshape((-1,) + (1,) * (block.ndim - 1))
            # The QUOTIENT is taken in float64 against the exact float32 scale.
            # In float32 the quotient carries ~6e-8 relative error, which at a
            # code magnitude of 32767 is ~2e-3 of a code -- enough to tip rint()
            # to the wrong neighbour and push the error just past half a step.
            # float64 here makes "error <= half a step" exactly true rather than
            # nearly true, and costs one transient cast per block.
            wide = shaped.astype("float64")
            codes = np.rint(block.astype("float64") / wide).astype("int16")
            out[start:stop] = codes
            scale[start:stop] = factor

            # Measure in float64 too: at an amplitude of ~1900 the float32
            # spacing is ~1.2e-4 against a half-step of ~0.03, so a float32
            # subtraction puts ~0.4 % of noise on the quantity being bounded.
            exact = np.abs(codes.astype("float64") * wide - block.astype("float64"))
            # What training actually sees: float32 reconstruction, float32 math.
            realised = np.abs(codes.astype("float32") * shaped - block)

            worst_abs = max(worst_abs, float(realised.max()))
            worst_exact = max(worst_exact, float(exact.max()))
            # a half-step is the theoretical worst case; >1.0 here means a bug
            worst_rel_to_step = max(
                worst_rel_to_step, float((exact / (wide / 2.0)).max()))
            error = exact
            total_sq += float((error ** 2).sum())
            total_n += error.size
            peak_max = max(peak_max, float(peak.max()))

            if start and start % (rows_per_block * 40) == 0:
                done = stop / n_rows
                rate = stop / max(1e-6, time.time() - started)
                log.info("    %s: %.1f%% (%d/%d rows, %.0f rows/s, ETA %.1f min)",
                         source.name, done * 100, stop, n_rows, rate,
                         (n_rows - stop) / max(rate, 1e-6) / 60)

        dst.attrs["source_file"] = source.name
        dst.attrs["dtype"] = "int16"
        dst.attrs["scaled"] = True
        dst.attrs["scale_scheme"] = "per-record: x = code * scale"
        dst.attrs["int16_max"] = INT16_MAX
        for key, value in src.attrs.items():
            if key not in dst.attrs:
                dst.attrs[key] = value

    bc.atomic_replace(tmp, target)
    elapsed = time.time() - started
    return {
        "source_bytes": source.stat().st_size,
        "target_bytes": target.stat().st_size,
        "ratio": target.stat().st_size / source.stat().st_size,
        "n_rows": int(n_rows),
        "max_abs_error": worst_abs,
        "max_abs_error_exact": worst_exact,
        "rms_error": float(np.sqrt(total_sq / max(total_n, 1))),
        "max_error_in_half_steps": worst_rel_to_step,
        "max_abs_amplitude": peak_max,
        "seconds": round(elapsed, 1),
        "sha256": sha256_file(target),
    }


def convert(kinds: list[str], log) -> int:
    manifest = load_manifest()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for kind in kinds:
        for source in shards_for(kind):
            if not source.exists():
                log.error("missing source shard %s", source)
                return 1
            target = OUT_DIR / source.name
            if source.name in manifest["files"] and target.exists():
                log.info("%s already converted, skipping", source.name)
                continue
            log.info("converting %s (%.2f GB)", source.name, source.stat().st_size / 1e9)
            info = convert_shard(source, target, log)
            info["kind"] = kind
            manifest["files"][source.name] = info
            save_manifest(manifest)                      # checksum written AS WE GO
            log.info("  -> %s  %.2f GB -> %.2f GB (%.1f%% of original) in %.1f min",
                     target.name, info["source_bytes"] / 1e9, info["target_bytes"] / 1e9,
                     info["ratio"] * 100, info["seconds"] / 60)
            log.info("     quantisation max|err| %.3e (%.4f of a half-step), "
                     "rms %.3e", info["max_abs_error_exact"],
                     info["max_error_in_half_steps"], info["rms_error"])
            log.info("     float32 round-trip max|err| %.3e on max amplitude %.2f "
                     "(relative %.2e)", info["max_abs_error"], info["max_abs_amplitude"],
                     info["max_abs_error"] / max(info["max_abs_amplitude"], 1e-12))
            # Exact arithmetic bounds the error at half a step. float32 rounding
            # in the divide-and-multiply adds ~1e-4 relative on top, so 0.1 % is
            # the honest bound; a real quantisation bug (wrong scale, int16
            # overflow, a global scale) misses by 2x or more, not 0.01 %.
            if info["max_error_in_half_steps"] > 1.0001:
                log.error("     QUANTISATION BUG: error exceeds a half step")
                return 1
    summarise(manifest, log)
    return 0


def summarise(manifest: dict[str, Any], log) -> None:
    files = manifest["files"]
    if not files:
        return
    src = sum(f["source_bytes"] for f in files.values())
    dst = sum(f["target_bytes"] for f in files.values())
    log.info("--- totals over %d files ---", len(files))
    log.info("  %.2f GB -> %.2f GB  (%.1f %% of original, %.2f GB saved)",
             src / 1e9, dst / 1e9, dst / src * 100, (src - dst) / 1e9)
    log.info("  worst quantisation |err| %.3e; worst half-step ratio %.6f",
             max(f.get("max_abs_error_exact", f["max_abs_error"]) for f in files.values()),
             max(f["max_error_in_half_steps"] for f in files.values()))
    log.info("  worst float32 round-trip |err| %.3e (what training sees)",
             max(f["max_abs_error"] for f in files.values()))


def verify(kinds: list[str], log) -> int:
    """Re-check checksums and re-measure the round-trip error from disk."""
    import h5py

    manifest = load_manifest()
    failures = 0
    for kind in kinds:
        for source in shards_for(kind):
            name = source.name
            recorded = manifest["files"].get(name)
            target = OUT_DIR / name
            if recorded is None or not target.exists():
                log.error("%s: not converted", name)
                failures += 1
                continue
            actual = sha256_file(target)
            if actual != recorded["sha256"]:
                log.error("%s: CHECKSUM MISMATCH", name)
                failures += 1
                continue
            # spot-check the reconstruction on a spread of records
            with h5py.File(source, "r") as src, h5py.File(target, "r") as dst:
                n_rows = src["signal"].shape[0]
                picks = np.unique(np.linspace(0, n_rows - 1, 64).astype(int))
                worst = 0.0
                for row in picks:
                    original = np.asarray(src["signal"][row], dtype="float64")
                    restored = (np.asarray(dst["signal"][row], dtype="float64")
                                * float(dst["scale"][row]))
                    worst = max(worst, float(np.abs(restored - original).max()))
            log.info("%s: OK  sha256 matches, %d spot rows, max|err| %.3e",
                     name, len(picks), worst)
    summarise(manifest, log)
    return 1 if failures else 0


def _self_check() -> None:
    """The quantisation contract, on synthetic records."""
    rng = np.random.default_rng(0)
    # one loud record and one very quiet one -- the case a GLOBAL scale ruins
    block = np.stack([rng.normal(0, 5.0, (12, 500)).astype("float32"),
                      rng.normal(0, 1e-3, (12, 500)).astype("float32")])
    peak = np.abs(block).max(axis=(1, 2))
    factor = (peak / INT16_MAX).astype("float32")
    shaped = factor.reshape(-1, 1, 1)
    wide = shaped.astype("float64")
    codes = np.rint(block.astype("float64") / wide).astype("int16")
    error = np.abs(codes.astype("float64") * wide - block.astype("float64"))

    assert np.abs(codes).max() <= INT16_MAX, "codes must fit in int16"
    ratio = (error / (wide / 2)).max()
    assert ratio <= 1.0001, f"error exceeds a half step by {ratio:.6f}x"

    # the point of per-record scaling: the quiet record keeps its resolution.
    quiet_relative = error[1].max() / np.abs(block[1]).max()
    assert quiet_relative < 1e-4, quiet_relative
    # a global scale would have destroyed it -- show the contrast
    global_factor = np.abs(block).max() / INT16_MAX
    global_error = np.abs(np.rint(block[1].astype("float64") / global_factor)
                          * global_factor - block[1].astype("float64"))
    assert global_error.max() / np.abs(block[1]).max() > quiet_relative * 100, \
        "per-record scaling should beat a global scale by orders of magnitude"

    assert np.abs(codes[0]).max() == INT16_MAX, "the loud record should use full range"
    print(f"make_int16 self-check PASS (worst {ratio:.6f} of a half-step; "
          f"per-record worst {error.max():.3e}; quiet-record relative "
          f"{quiet_relative:.2e} vs global {global_error.max() / np.abs(block[1]).max():.2e})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("action", choices=["convert", "verify", "selfcheck"])
    parser.add_argument("--kinds", nargs="+", default=["preprocessed_12lead"])
    args = parser.parse_args(argv)

    if args.action == "selfcheck":
        _self_check()
        return 0

    log = bc.setup_logging("make_int16", stage=STAGE)
    log.info("make_int16 %s: kinds=%s -> %s", args.action, args.kinds, OUT_DIR)
    if args.action == "convert":
        return convert(args.kinds, log)
    return verify(args.kinds, log)


if __name__ == "__main__":
    raise SystemExit(main())
