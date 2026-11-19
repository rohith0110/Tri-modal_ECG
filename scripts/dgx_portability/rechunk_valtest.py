#!/usr/bin/env python3
"""Rewrite a local `*_valtest` signal container with one record per chunk.

    ./ecg_env/Scripts/python.exe scripts/dgx_portability/rechunk_valtest.py \
        data/processed/derived/signals_12lead_valtest/signals_12lead_valtest__val.h5

The R2 containers chunk `signal` as 64 records x 1 lead, so one record spans 12
chunks (7.7 MB inflated). Validation reads rows in task order, not container
order (~104 distinct blocks per 256-row batch), so every batch inflated ~800 MB
and an epoch's val pass took ~4 min against ~20 s of training (2026-11-19).

The copy keeps every dataset, value, dtype and attribute; only `signal`'s chunk
shape changes, to (1, 5000, 12) -- the layout the training pieces already use.
The original is kept beside it as `<name>.orig.h5`; values are compared before
the swap. Local only: R2 and the DGX keep the original layout.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import h5py
import numpy as np

BLOCK = 4096          # rows per copy step (~490 MB as int16)


def rechunk(source: Path) -> None:
    target = source.with_name(source.stem + ".rechunk.h5")
    backup = source.with_name(source.stem + ".orig.h5")
    if backup.exists():
        sys.exit(f"{backup} exists -- already rechunked?")
    with h5py.File(source, "r") as src, h5py.File(target, "w") as dst:
        dst.attrs.update(src.attrs)
        for name, dataset in src.items():
            if name != "signal":
                src.copy(dataset, dst, name=name)
                continue
            out = dst.create_dataset(name, shape=dataset.shape, dtype=dataset.dtype,
                                     chunks=(1, *dataset.shape[1:]), compression="gzip",
                                     compression_opts=4, shuffle=dataset.shuffle)
            out.attrs.update(dataset.attrs)
            for start in range(0, dataset.shape[0], BLOCK):
                out[start:start + BLOCK] = dataset[start:start + BLOCK]
                print(f"\r{source.name}: {min(start + BLOCK, dataset.shape[0])}/"
                      f"{dataset.shape[0]}", end="", flush=True)
    print()
    with h5py.File(source, "r") as src, h5py.File(target, "r") as dst:
        assert set(src) == set(dst), "dataset names differ"
        for name in src:
            for start in range(0, src[name].shape[0], BLOCK):
                if not np.array_equal(src[name][start:start + BLOCK],
                                      dst[name][start:start + BLOCK]):
                    raise SystemExit(f"{name} differs at rows {start}+ -- original kept")
    source.rename(backup)
    target.rename(source)
    print(f"{source.name}: rechunked and verified; original at {backup.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("containers", nargs="+", type=Path)
    for path in parser.parse_args().containers:
        rechunk(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
