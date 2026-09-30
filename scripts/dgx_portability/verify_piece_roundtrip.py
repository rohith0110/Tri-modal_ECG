# -*- coding: utf-8 -*-
"""Prove a scan-like piece reads back byte-identical to the base shard.

Stages two real pieces the way `stage_data.sh` would (as `<DATA_ROOT>/<base>/`),
installs the overlay the way the campaign body would, and checks that
`read_modality()` returns exactly the bytes it returned from the base container
for studies in those pieces -- and still resolves a study OUTSIDE them to the
base container. Everything it creates is removed again.

    ./ecg_env/Scripts/python.exe <this file> <kind> <chunk-dir> [n_studies]
"""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path("scripts/phase2_tasks_benchmark_and_paper").resolve()))
from _dataset_lib import build_common as bc          # noqa: E402
from _dataset_lib import modality as mod             # noqa: E402
from _dataset_lib import chunk_pieces                # noqa: E402

KIND = sys.argv[1] if len(sys.argv) > 1 else "image_scanlike_12lead"
CHUNK_DIR = Path(sys.argv[2] if len(sys.argv) > 2
                 else "C:/trimodal_chunks/image_scanlike_12lead__train__p8")
N = int(sys.argv[3]) if len(sys.argv) > 3 else 40
BASE = {v: k for k, v in chunk_pieces.BASE_TO_KIND.items()}[KIND]

staged = bc.DATA_PROCESSED / BASE
overlay = mod.OVERLAY_DIR / f"pieces_{BASE}.parquet"
link_root = Path("C:/trimodal_chunks/_roundtrip") / BASE


def run(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"{cmd}\n{result.stdout}\n{result.stderr}")


def cleanup():
    if staged.is_dir() or staged.is_symlink():
        run(f'cmd /c rmdir "{staged}"')
    overlay.unlink(missing_ok=True)
    mod._INDEX.clear()
    mod.close_handles()


cleanup()
link_root.mkdir(parents=True, exist_ok=True)
for old in link_root.iterdir():
    old.unlink()
# two pieces resident, exactly as a campaign holds them
for index in (0, 1):
    for suffix in (".tar", ".h5"):
        source = CHUNK_DIR / f"piece_{index:03d}{suffix}"
        if source.exists():
            run(f'cmd /c mklink /H "{link_root / source.name}" "{source}"')
run(f'cmd /c mklink /J "{staged}" "{link_root}"')

try:
    assignment = pd.read_parquet(CHUNK_DIR / "assignment.parquet")
    inside = assignment.loc[assignment.piece.isin([0, 1]), "study_id"].to_numpy()[:N]
    outside = assignment.loc[~assignment.piece.isin([0, 1]), "study_id"].to_numpy()[:5]

    before = {int(s): mod.read_modality(int(s), KIND) for s in inside}
    before_out = {int(s): mod.read_modality(int(s), KIND) for s in outside}

    resident = chunk_pieces.install_overlays()
    mod._INDEX.clear()
    mod.close_handles()
    print(f"overlay installed, resident: {resident}")

    index = mod._index_for(KIND)
    from_piece = sum(1 for s in inside if BASE in str(index[int(s)][0]))
    bad = 0
    for study in inside:
        after = mod.read_modality(int(study), KIND)
        if isinstance(after, np.ndarray):
            same = np.array_equal(after, before[int(study)])
        else:
            same = after == before[int(study)]
        if not same:
            print(f"  MISMATCH study {study}")
            bad += 1
    for study in outside:
        after = mod.read_modality(int(study), KIND)
        same = (np.array_equal(after, before_out[int(study)])
                if isinstance(after, np.ndarray) else after == before_out[int(study)])
        if not same:
            print(f"  MISMATCH (outside the window) study {study}")
            bad += 1

    print(f"{KIND}: {len(inside)} studies in pieces 0/1, {from_piece} now resolve to "
          f"the piece; {len(outside)} outside still resolve to the base container")
    if bad or from_piece != len(inside):
        raise SystemExit(f"ROUND TRIP FAILED ({bad} mismatches, "
                         f"{from_piece}/{len(inside)} redirected)")
    print(f"ROUND TRIP PASS -- {KIND} pieces are byte-identical to the base shards")
finally:
    cleanup()
    for old in link_root.iterdir():
        old.unlink()
