# Stage P2.0 — Foundation (rewrite config + quarantine stale) — report

- **Stage:** P2.0 (spec `docs/PHASE2_SOURCE_OF_TRUTH.md` §9.1)
- **Date:** 2026-08-26
- **Machine:** development laptop, `./ecg_env/Scripts/python.exe` (Python 3.11.9)
- **Result:** **PASS — 26/26 validation checks**
- **Validation gate:** `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/schema_validators.py`
- **Blocking issues for later stages:** 5 recorded (see §8) — none blocks P2.0.

---

## 1. Files created

- `config/icd_label_map_LOCKED.yaml`  (7.6 KB, sha256 `b18ff6006f29`)
- `config/lab_itemid_map_LOCKED.yaml`  (11.6 KB, sha256 `fc43a41d9611`)
- `config/corruption_recipes_LOCKED.yaml`  (9.9 KB, sha256 `14746244d4db`)
- `config/claim_dictionary_LOCKED.yaml`  (13.5 KB, sha256 `6288f8fe90aa`)
- `config/decision_phase2.yaml`  (22.5 KB, sha256 `474fc4a58a5b`)
- `config/model_configs/README.md`  (1.2 KB, sha256 `911278c37afc`)
- `config/eval_configs/README.md`  (859 B, sha256 `3c10f165c07a`)
- `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/__init__.py`  (0 B, sha256 `e3b0c44298fc`)
- `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/modality.py`  (15.1 KB, sha256 `68979cd4c7c5`)
- `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/schema_validators.py`  (28.5 KB, sha256 `ab07c51ea476`)
- `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/dev_sample.py`  (6.7 KB, sha256 `5e732a63cea7`)
- `scripts/phase2_tasks_benchmark_and_paper/_model_lib/__init__.py`  (0 B, sha256 `e3b0c44298fc`)
- `scripts/phase2_tasks_benchmark_and_paper/_train_lib/__init__.py`  (0 B, sha256 `e3b0c44298fc`)
- `scripts/dgx_portability/README.md`  (2.7 KB, sha256 `7d606f191315`)
- `outputs/results/README.md`  (964 B, sha256 `8076cc076c3b`)
- `outputs/figures/README.md`  (979 B, sha256 `700aa7b481d8`)
- `outputs/tables/README.md`  (837 B, sha256 `1bbe8c38c700`)
- `outputs/model_runs/README.md`  (1.1 KB, sha256 `f37de9a8cd32`)
- `outputs/release_package/README.md`  (681 B, sha256 `2d0967fed111`)
- `outputs/stage_reports/stage_P2.0_validation.log`  (3.4 KB, sha256 `d0cab359b267`)
- `data/processed/tasks/README.md`  (1.6 KB, sha256 `5978319db40d`)
- `data/processed/dev_sample/README.md`  (2.6 KB, sha256 `84e13821b413`)
- `data/processed/dev_sample/dev_sample_studies.parquet`  (109.6 KB, sha256 `84eb732ed68d`)

Empty directories scaffolded (spec §9.1 item 9, §3): `outputs/results/`,
`outputs/release_package/`, `outputs/tables/{main,supplementary}/`,
`outputs/figures/{main,supplementary}/`, `data/processed/tasks/`,
`data/processed/dev_sample/`, `config/model_configs/`, `config/eval_configs/`,
`scripts/dgx_portability/slurm/`,
`scripts/phase2_tasks_benchmark_and_paper/{_dataset_lib,_model_lib,_train_lib}/`,
and `scripts/phase2_tasks_benchmark_and_paper/_legacy_phase1_pre_regen/`.
`outputs/stage_reports/`, `outputs/audit_reports/`, `outputs/tables/`,
`outputs/figures/` and `outputs/model_runs/` already existed from Phase 1.

## 2. Files modified

- `config/task_definitions.yaml`  ::  rewritten from the 6 Plan-B tasks to the full 12-task §4 data contract; adds shared_label_defs, per-task cohort/targets/metrics/baselines/sensitivity, the §4.C invariants, and two recorded spec conflicts (A2 SQI cohort, B2 anchor pool)
- `config/task_input_policy.yaml`  ::  rewritten against §4.X.4 verbatim; adds report_text_masked to A5, corrects B5 (was report_text_corrupted / machine_report_text_original), corrects B3 to forbid images, adds the §2.6 enum block and the two baseline-only carve-outs for A1 and A6
- `.gitignore`  ::  re-includes outputs/results/ and the provenance READMEs under outputs/figures/ and outputs/release_package/, which the /outputs/* rule was silently swallowing

## 3. Files / folders deleted

**none — quarantine only** (spec §2.4 step 4: deletion is deferred until the
Phase 2 regen completes end-to-end and the reviewer signs off).

36 scripts moved from `scripts/phase2_tasks_benchmark_and_paper/` to
`scripts/phase2_tasks_benchmark_and_paper/_legacy_phase1_pre_regen/`:

```
01_task_A_verification.py            24_train_B2_regime2.py       51_write_benchmark_report.py
02_task_B_temporal_grounding.py      30_neurokit2_baseline_B1.py  60_find_examples.py
03_task_C_plausibility.py            31_baseline_B3_temporal.py   61_viz_overview.py
04_task_B1_measurement_blind.py      32_baseline_B5_contradiction.py  62_viz_12lead_only.py
05_task_B2_noise_robustness.py       33_baseline_B4_cross_modal.py    63_viz_examples.py
06_task_B5_contradiction_detection.py 34_baseline_B6_difficulty.py    64_viz_extras.py
10_run_audits.py                     40_aggregate_seeds.py        65_viz_tasks_bc.py
11_audit_against_spec.py             41_eval_B2_regime1.py        66_viz_paper.py
12_fill_audit_gaps.py                42_eval_B2_regime2.py        70_paper_stream_taskB.py
20_train_B1_bank.py                  43_b2_auc_metrics.py         71_post_regen_taskB.py
21_train_B1_baselines.py             44_b1_sqi_stratified.py      72_print_taskB_paper_numbers.py
22_train_B1_baselines_fast.py        50_benchmark_figures.py      _dev_check_linkage_feasibility.py
23_train_B1_ram.py
```

Moved with `git mv`, so history follows. `README.md` deliberately stayed at the
origin path — it already carries the "every script here is pre-regen and stale"
banner and points forward to the Phase 2 plan.

`data/processed/task_jsonl/` (spec §2.4 step 1) was **already absent** before
this stage and needed no action; it was removed during the Phase 1 regen
cleanup, so no `data/archive_phase1_old/task_jsonl_<ts>/` was created. Recorded
here as §2.4 requires.

The quarantine is wider than §2.4's original `01..06_task_*.py`: the new Phase 2
scripts also need slots 10–12, 20–22, 30–34, 40–44, 50–51, 60–66 and 70–72, all
of which were occupied.

## 4. Design decisions

- **The Phase 2 modality enum and the Phase 1 manifest spell image kinds
  differently, and `modality.py` is the only place they meet.**  ::  Spec §2.6
  locks nine kinds including `image_clean_lead2` / `image_clean_12lead` /
  `image_scanlike_lead2` / `image_scanlike_12lead`. The manifest on disk stores
  those as two `modality_kind` values (`image_clean`, `image_scanlike`) crossed
  with a `layout` column (`lead2`, `12lead`). `read_modality` holds the mapping
  table and every caller uses the §2.6 spelling. Neither the spec's enum nor the
  Phase 1 manifest changed.

- **`read_modality` returns 12-lead signals channel-major, `(12, 5000)`.**  ::
  The HDF5 shards store `(n_studies, 5000, 12)` — sample-major. The §5.2 encoder
  contract is `(B, n_leads, 5000)`. Returning the container's native layout would
  let a caller feed a transposed tensor to `Conv1d` and train silently on
  nonsense. The loader transposes once (a view plus `ascontiguousarray`, no
  re-read) and exposes `LEAD_ORDER_12`. A self-check asserts
  `raw_lead2 == raw_12lead[LEAD_II_INDEX]`.

- **Tar offsets in the manifest point at the 512-byte member HEADER, not the
  data.**  ::  Verified against `tarfile.TarInfo.offset_data` at lock time
  (`container_offset` 1457152, `offset_data` 1457664). `read_modality` seeks to
  `offset + 512`. Getting this wrong returns a tar header where a PNG was
  expected; the self-check asserts the PNG/JPEG magic bytes on every read.

- **B5 and the A2/B1 measurement bins read MACHINE measurements, not the
  NeuroKit2 columns.**  ::  §4.B.5.3 names `structured_features.parquet.pr_ms`.
  That column is NeuroKit-derived (median 120 ms, max 9468 ms) and
  `structured_features.qrs_ms` is byte-identical to `structured_features.qrs_dur_ms`,
  not the machine `qrs_end - qrs_onset` that §4.A.2.3's own formula specifies.
  Using the NeuroKit PR would put 425,562 studies in the "clear normal PR" zone
  and ship 9,035 studies whose report already says "1st degree A-V block" as
  CLEAN rows. The machine PR yields 1,083 such disagreements against 13,111
  coherent ones. **User decision at P2.0: machine measurements everywhere.**
  Recorded as a documented deviation in `claim_dictionary_LOCKED.yaml` and
  `task_definitions.yaml`; must be disclosed in the supplementary.

- **The machine-measurement missing sentinel is `29999`, and the `*_missing`
  flag columns are unusable.**  ::  `p_onset_missing`, `qrs_onset_missing`,
  `qrs_end_missing`, `qrs_axis_missing` and `rr_interval_missing` are **all
  False for all 749,112 rows** — they mark nothing. The real encoding is the
  literal `29999` (`p_onset` 119,385 rows, `p_axis` 119,483, `qrs_axis` 1,531,
  `rr_interval` 487, `qrs_onset`/`qrs_end` 341 each). Masking it turns PR from
  mean −4600 ms into mean 162.7 ms (median 160, sd 37). Every builder that
  touches a machine measurement must apply this; the rule is recorded in both
  `claim_dictionary_LOCKED.yaml` and `task_definitions.yaml`.

- **B5 injections are SWAPS of text that is actually present, never
  insertions.**  ::  §4.B.5.3 specifies a swap and requires a recorded span. An
  inserted claim would produce a span with no original counterpart and would
  make the corrupted class detectable by length or phrase style rather than by
  the contradiction. A study is eligible only when the measurement is in a clear
  zone **and** the report carries a matching surface form. Measured: 128,653 of
  749,112 studies (17.2 %) are eligible for at least one family.

- **The `incomplete` exclusion in the B5 QRS family.**  ::  Incomplete RBBB/LBBB
  is defined by QRS < 120 ms, so "incomplete right bundle branch block" is
  consistent with a narrow QRS. Without the negative lookbehind, the naive
  pattern produced 29,755 spurious report-says-wide / measurement-says-narrow
  pairs; with it, 23 remain.

- **The `corruption_recipes_LOCKED.yaml` file is a transcription of Phase 1
  Stage 8, not a redefinition.**  ::  The corrupted test set is frozen and Phase
  2 never regenerates it (§9.3). Every parameter was read out of
  `50_build_signals_corrupted.py`, and a validation check re-parses that source
  and asserts the family list and SNR ladder still match. The file additionally
  specifies the regime_2 train-time RNG stream with a literal `regime2|` salt, so
  §7.3's disjointness requirement is mechanically guaranteed rather than assumed.

- **The dev sample is deliberately enriched and says so.**  ::  Proportional
  stratification on `(split, link_tier, sqi_tier)` yields ~28 high-SQI rows,
  because `sqi_tier == "high"` is 0.56 % of the clean cohort. 100 B2 anchors and
  300 high-SQI studies are force-included and flagged (`is_b2_anchor`,
  `is_sqi_high_boost`) so no one mistakes the sample for a prevalence estimate.

- **`pydantic` 2.13.4 was installed into `ecg_env`.**  ::  §9.1's validation
  bullet names a Pydantic schema explicitly. It is the only dependency this stage
  added. `transformers` is still absent and is a Step 3 prerequisite; recorded in
  `decision_phase2.yaml` under `compute.development.env`.

- **`.gitignore` was swallowing three Phase 2 output paths.**  ::  The
  allowlist's `/outputs/*` rule re-included only `audit_reports/`,
  `stage_reports/` and `tables/`. `outputs/results/` holds the per-task CSVs the
  paper is built from, and `outputs/figures/README.md` is the Stage P2.12
  provenance gate. Both are now re-included, along with
  `outputs/release_package/{README.md,checksums.txt}`. Binary contents stay
  ignored. This is the same class of bug as the `docs/` gap found on 2026-08-26.

## 5. Complete code

### `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/modality.py`

```python
"""Canonical Phase 2 modality loader (spec §2.1).

Every dataloader, every label builder and every evaluation script in Phase 2
resolves modality bytes through :func:`read_modality`. Nothing else may
``open()`` an HDF5 file or a tar archive directly -- an inheritance violation
is CRITICAL (spec §2, §11).

    from _dataset_lib.modality import read_modality
    sig = read_modality(40000017, "preprocessed_lead2")     # -> (5000,) float32
    png = read_modality(40000017, "image_clean_lead2")      # -> PNG bytes
    bad = read_modality(40000035, "signal_corrupted",
                        corruption_type="gaussian", snr_db=10)

Caching policy (spec §2.1): index-only structures (manifest rows, tar offsets,
open file handles) may be cached; **raw bytes may not** -- that is the on-disk
container's job. Handle caches are keyed by PID so a forked DataLoader worker
never inherits a parent's HDF5 handle, which is not safe to share.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

import numpy as np

# --- repo layout -------------------------------------------------------------
# .../scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/modality.py
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
MANIFEST_PATH = DATA_PROCESSED / "modality_manifest.parquet"

# --- the locked modality-kind enum (spec §2.6) -------------------------------
# Adding a kind here is a CRITICAL spec violation.
SIGNAL_KINDS = ("raw_lead2", "raw_12lead", "preprocessed_lead2", "preprocessed_12lead")
IMAGE_KINDS = (
    "image_clean_lead2",
    "image_clean_12lead",
    "image_scanlike_lead2",
    "image_scanlike_12lead",
)
CORRUPTED_KIND = "signal_corrupted"
MODALITY_KINDS = SIGNAL_KINDS + IMAGE_KINDS + (CORRUPTED_KIND,)

# The Phase 2 enum splits image kinds by layout; the Phase 1 manifest stores
# them as (modality_kind, layout) pairs. This is the only place the two
# spellings meet.
_IMAGE_KIND_TO_MANIFEST = {
    "image_clean_lead2": ("image_clean", "lead2"),
    "image_clean_12lead": ("image_clean", "12lead"),
    "image_scanlike_lead2": ("image_scanlike", "lead2"),
    "image_scanlike_12lead": ("image_scanlike", "12lead"),
}

# Tar members are stored as a 512-byte header block followed by the file data.
# `container_offset` in the manifest points at the HEADER, so member bytes begin
# 512 bytes later. Verified against tarfile.TarInfo.offset_data at Stage P2.0.
TAR_HEADER_BYTES = 512

_N_SAMPLES = 5000
_N_LEADS = 12

# Phase 1 stores 12-lead signals as (n_studies, 5000, 12) -- sample-major. The
# §5.2 encoder contract is (B, n_leads, 5000) -- channel-major. read_modality
# returns the CHANNEL-MAJOR view, (12, 5000), so a caller can never silently
# feed a transposed tensor to Conv1d. The transpose is a view plus one
# ascontiguousarray; it does not re-read the container.
LEAD_ORDER_12 = ("I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6")
LEAD_II_INDEX = LEAD_ORDER_12.index("II")  # == 1

_index_lock = threading.Lock()
_INDEX: dict[str, dict[int, tuple]] = {}
_HANDLES: dict[tuple[int, str], Any] = {}
_CORRUPT_READER: dict[int, Any] = {}


class ModalityError(KeyError):
    """Raised when a (study_id, kind) pair has no manifest row."""


# -----------------------------------------------------------------------------
# index
# -----------------------------------------------------------------------------
def _build_index(kind: str) -> dict[int, tuple]:
    """Load the manifest rows for one kind into a study_id -> row lookup.

    Index only -- no bytes. Roughly 470 MB is read from the manifest once per
    process and discarded; what is retained is one small dict per kind actually
    used.
    """
    import pandas as pd

    cols = [
        "study_id",
        "modality_kind",
        "layout",
        "container_path",
        "container_row",
        "container_offset",
        "container_length",
    ]
    if kind == CORRUPTED_KIND:
        cols += ["corruption_type", "snr_db"]

    manifest = pd.read_parquet(MANIFEST_PATH, columns=cols)

    if kind in _IMAGE_KIND_TO_MANIFEST:
        manifest_kind, layout = _IMAGE_KIND_TO_MANIFEST[kind]
        rows = manifest[
            (manifest["modality_kind"] == manifest_kind) & (manifest["layout"] == layout)
        ]
    else:
        rows = manifest[manifest["modality_kind"] == kind]

    if rows.empty:
        raise ModalityError(f"manifest has no rows for modality kind {kind!r}")

    if kind == CORRUPTED_KIND:
        # One study has 40 corrupted variants, so the key is the triple.
        return {
            (int(s), str(c), int(n)): (str(p), int(r))
            for s, c, n, p, r in zip(
                rows["study_id"],
                rows["corruption_type"],
                rows["snr_db"],
                rows["container_path"],
                rows["container_row"],
            )
        }

    if kind in SIGNAL_KINDS:
        return {
            int(s): (str(p), int(r))
            for s, p, r in zip(rows["study_id"], rows["container_path"], rows["container_row"])
        }

    return {
        int(s): (str(p), int(o), int(l))
        for s, p, o, l in zip(
            rows["study_id"],
            rows["container_path"],
            rows["container_offset"],
            rows["container_length"],
        )
    }


def _index_for(kind: str) -> dict:
    idx = _INDEX.get(kind)
    if idx is None:
        with _index_lock:
            idx = _INDEX.get(kind)
            if idx is None:
                idx = _build_index(kind)
                _INDEX[kind] = idx
    return idx


# -----------------------------------------------------------------------------
# handles -- keyed by PID so forked workers never share one
# -----------------------------------------------------------------------------
def _h5(path: str):
    import h5py

    key = (os.getpid(), path)
    handle = _HANDLES.get(key)
    if handle is None:
        # swmr=False: we are a plain reader, not a SWMR writer (spec §8.5).
        handle = h5py.File(str(DATA_PROCESSED / path), "r", swmr=False)
        _HANDLES[key] = handle
    return handle


def _tar(path: str):
    key = (os.getpid(), path)
    handle = _HANDLES.get(key)
    if handle is None:
        handle = open(DATA_PROCESSED / path, "rb")
        _HANDLES[key] = handle
    return handle


def _corrupt_reader(path: str):
    """Row-group-cached reader over signals_corrupted.parquet.

    The file is ~0.92 GB, too large to hold whole on the 6 GB laptop alongside a
    model. We keep the row-group boundaries (index only) and materialise one
    row group at a time; sequential access over an anchor's 40 variants hits
    the same group repeatedly.
    """
    import pyarrow.parquet as pq

    key = os.getpid()
    state = _CORRUPT_READER.get(key)
    if state is None or state["path"] != path:
        pf = pq.ParquetFile(DATA_PROCESSED / path)
        bounds = []
        start = 0
        for i in range(pf.num_row_groups):
            n = pf.metadata.row_group(i).num_rows
            bounds.append((start, start + n))
            start += n
        state = {"path": path, "pf": pf, "bounds": bounds, "cached_group": None, "cached": None}
        _CORRUPT_READER[key] = state
    return state


def close_handles() -> None:
    """Close every cached handle for this process. Call at worker teardown."""
    pid = os.getpid()
    for key in [k for k in _HANDLES if k[0] == pid]:
        try:
            _HANDLES.pop(key).close()
        except Exception:  # pragma: no cover - teardown must not raise
            pass
    _CORRUPT_READER.pop(pid, None)


# -----------------------------------------------------------------------------
# the public entry point
# -----------------------------------------------------------------------------
def read_modality(
    study_id: int,
    kind: str,
    *,
    corruption_type: str | None = None,
    snr_db: int | None = None,
) -> bytes | np.ndarray:
    """Resolve a study + modality to bytes (tar) or an array (HDF5 / parquet).

    Resolution always goes through ``data/processed/modality_manifest.parquet``.

    Args:
        study_id: MIMIC-IV-ECG study identifier.
        kind: one of :data:`MODALITY_KINDS` --
            ``raw_lead2``, ``raw_12lead``, ``preprocessed_lead2``,
            ``preprocessed_12lead``, ``image_clean_lead2``,
            ``image_clean_12lead``, ``image_scanlike_lead2``,
            ``image_scanlike_12lead``, ``signal_corrupted``.
        corruption_type: required when ``kind == "signal_corrupted"``; one of the
            8 families in ``config/corruption_recipes_LOCKED.yaml``.
        snr_db: required when ``kind == "signal_corrupted"``; one of 30/20/10/5/0.

    Returns:
        ``(5000,) float32`` for Lead-II signals and corrupted signals,
        ``(12, 5000) float32`` for 12-lead signals -- CHANNEL-MAJOR, in
        :data:`LEAD_ORDER_12`, transposed from the container's sample-major
        layout so it drops straight into a Conv1d -- and raw image ``bytes``
        (PNG/JPEG, exactly as stored) for the four image kinds.

    Raises:
        ValueError: unknown ``kind``, or corruption arguments used incorrectly.
        ModalityError: the study has no manifest row for that kind.
    """
    if kind not in MODALITY_KINDS:
        raise ValueError(
            f"unknown modality kind {kind!r}. The enum is locked (spec §2.6): "
            f"{', '.join(MODALITY_KINDS)}"
        )

    if kind == CORRUPTED_KIND:
        if corruption_type is None or snr_db is None:
            raise ValueError(
                "signal_corrupted requires corruption_type and snr_db "
                "(a study has 8 x 5 = 40 corrupted variants)"
            )
        return _read_corrupted(int(study_id), str(corruption_type), int(snr_db))

    if corruption_type is not None or snr_db is not None:
        raise ValueError(f"corruption_type / snr_db are only valid for {CORRUPTED_KIND!r}")

    if kind in SIGNAL_KINDS:
        return _read_signal(int(study_id), kind)
    return _read_image(int(study_id), kind)


def _read_signal(study_id: int, kind: str) -> np.ndarray:
    row = _index_for(kind).get(study_id)
    if row is None:
        raise ModalityError(f"no {kind} row for study_id {study_id}")
    path, container_row = row
    raw = np.asarray(_h5(path)["signal"][container_row], dtype=np.float32)
    if raw.ndim == 2:
        # (5000, 12) as stored -> (12, 5000) as the encoder expects.
        raw = np.ascontiguousarray(raw.T)
    return raw


def _read_image(study_id: int, kind: str) -> bytes:
    row = _index_for(kind).get(study_id)
    if row is None:
        raise ModalityError(f"no {kind} row for study_id {study_id}")
    path, offset, length = row
    handle = _tar(path)
    handle.seek(offset + TAR_HEADER_BYTES)
    data = handle.read(length)
    if len(data) != length:
        raise ModalityError(
            f"short read for {kind} study_id {study_id}: got {len(data)} of {length} bytes"
        )
    return data


def _read_corrupted(study_id: int, corruption_type: str, snr_db: int) -> np.ndarray:
    row = _index_for(CORRUPTED_KIND).get((study_id, corruption_type, snr_db))
    if row is None:
        raise ModalityError(
            f"no signal_corrupted row for study_id {study_id}, "
            f"corruption_type={corruption_type!r}, snr_db={snr_db}"
        )
    path, container_row = row
    state = _corrupt_reader(path)

    group = next(
        (i for i, (lo, hi) in enumerate(state["bounds"]) if lo <= container_row < hi), None
    )
    if group is None:
        raise ModalityError(f"row {container_row} is out of range in {path}")

    if state["cached_group"] != group:
        state["cached"] = state["pf"].read_row_group(group, columns=["signal"])
        state["cached_group"] = group

    local = container_row - state["bounds"][group][0]
    return np.asarray(state["cached"]["signal"][local].as_py(), dtype=np.float32)


# -----------------------------------------------------------------------------
# self-check -- the spec §9.1 validation for this module
# -----------------------------------------------------------------------------
def _self_check(n_per_kind: int = 10, seed: int = 2026) -> None:
    """Resolve `n_per_kind` random studies per modality kind and assert shapes.

    This is the runnable form of the P2.0 validation item "read_modality()
    resolves 10 random (study_id, kind) calls per modality kind successfully".
    """
    import random

    rng = random.Random(seed)

    for kind in SIGNAL_KINDS + IMAGE_KINDS:
        keys = list(_index_for(kind).keys())
        assert keys, f"{kind}: empty index"
        for study_id in rng.sample(keys, n_per_kind):
            out = read_modality(study_id, kind)
            if kind in SIGNAL_KINDS:
                expected = (_N_SAMPLES,) if kind.endswith("lead2") else (12, _N_SAMPLES)
                assert isinstance(out, np.ndarray), f"{kind}: expected ndarray"
                assert out.shape == expected, f"{kind} {study_id}: {out.shape} != {expected}"
                assert out.dtype == np.float32, f"{kind} {study_id}: dtype {out.dtype}"
                assert np.isfinite(out).all(), f"{kind} {study_id}: non-finite samples"
            else:
                assert isinstance(out, bytes), f"{kind}: expected bytes"
                assert out[:8] == b"\x89PNG\r\n\x1a\n" or out[:2] == b"\xff\xd8", (
                    f"{kind} {study_id}: not a PNG or JPEG"
                )
        print(f"  {kind:24s} OK  ({n_per_kind} studies, {len(keys):,} indexed)")

    keys = list(_index_for(CORRUPTED_KIND).keys())
    assert keys, "signal_corrupted: empty index"
    for study_id, corruption_type, snr_db in rng.sample(keys, n_per_kind):
        out = read_modality(
            study_id, CORRUPTED_KIND, corruption_type=corruption_type, snr_db=snr_db
        )
        assert isinstance(out, np.ndarray), "signal_corrupted: expected ndarray"
        assert out.shape == (_N_SAMPLES,), f"signal_corrupted {study_id}: {out.shape}"
        assert np.isfinite(out).all(), f"signal_corrupted {study_id}: non-finite samples"
    print(f"  {CORRUPTED_KIND:24s} OK  ({n_per_kind} variants, {len(keys):,} indexed)")

    # A Lead-II raw signal must equal lead II of the same study's 12-lead raw.
    study_id = next(iter(_index_for("raw_lead2")))
    lead2 = read_modality(study_id, "raw_lead2")
    twelve = read_modality(study_id, "raw_12lead")
    assert twelve.shape == (_N_LEADS, _N_SAMPLES), f"raw_12lead shape {twelve.shape}"
    assert np.allclose(twelve[LEAD_II_INDEX], lead2, atol=1e-5), (
        f"raw_lead2 for study {study_id} does not match raw_12lead lead "
        f"{LEAD_II_INDEX} ('II') -- the channel-major transpose or the lead "
        f"order is wrong"
    )
    print(f"  cross-check              OK  (raw_lead2 == raw_12lead['II'], index {LEAD_II_INDEX})")

    close_handles()
    print("read_modality self-check: PASS")


if __name__ == "__main__":
    _self_check()

```

### `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/dev_sample.py`

```python
"""Build the fixed 5,000-study development sample (spec §8.2.1).

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/dev_sample.py

The laptop authors and smoke-tests every Phase 2 script against this sample so a
builder runs in minutes instead of hours; it trains nothing that reaches the
paper. The sample is a **pointer table only** -- study ids plus the cohort flags
a builder filters on. Modality bytes still resolve through
``read_modality``, so a script exercised on the sample takes the exact code path
it will take at full scale on the DGX.

Determinism: the row set is a pure function of the Phase 1 artifacts and
``SEED``. Re-running overwrites the file with identical content.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
OUT_DIR = DATA_PROCESSED / "dev_sample"
OUT_PATH = OUT_DIR / "dev_sample_studies.parquet"

SEED = 2026
N_STUDIES = 5_000
N_B2_ANCHORS = 100     # force-included so B2 has corrupted variants to smoke-test
N_SQI_HIGH_FLOOR = 300  # force-included so A2/A4 have a workable high-SQI cohort

# Why the floor: sqi_tier == "high" is only 0.56 % of the clean cohort (4,166 of
# 749,112 studies), so proportional sampling yields ~28 high-SQI rows -- too few
# to exercise A2's primary cohort (sqi high) or A4's (sqi high+medium) at all.
# The boosted rows carry `is_sqi_high_boost = True`. THE SAMPLE IS THEREFORE NOT
# A PREVALENCE ESTIMATE: drop the boosted and anchor rows before reading any
# class balance off it. Real prevalence lands in cohort_audit.md at Stage P2.3.


def build() -> pd.DataFrame:
    meta = pd.read_parquet(
        DATA_PROCESSED / "index" / "ecg_metadata_clean_with_measurements.parquet",
        columns=["study_id", "subject_id", "split", "link_tier", "cart_id", "hr_bucket"],
    )
    qc = pd.read_parquet(
        DATA_PROCESSED / "waveform_qc.parquet",
        columns=["study_id", "sqi_tier", "decode_ok", "length_ok", "text_ok",
                 "image_clean_ok", "image_scanlike_ok"],
    )
    avail = pd.read_parquet(
        DATA_PROCESSED / "linkage" / "label_availability.parquet",
        columns=["study_id", "hadm_id", "icd_available", "any_key_lab_within_24h",
                 "mortality_observable", "readmission_eligible"],
    )

    df = meta.merge(qc, on="study_id", how="left").merge(avail, on="study_id", how="left")
    df = df[df.decode_ok.fillna(False) & df.length_ok.fillna(False)]

    # Stratify on (split, link_tier, sqi_tier) so the sample is a fair miniature
    # of the clean cohort: the 70/10/20 ratio, the linkage mix that decides which
    # tasks are exercisable, and the SQI mix the sensitivity tables slice on.
    df["stratum"] = (
        df.split.astype(str) + "|" + df.link_tier.astype(str) + "|" + df.sqi_tier.astype(str)
    )

    corrupted_anchors = pd.read_parquet(
        DATA_PROCESSED / "signals_corrupted.parquet", columns=["study_id"]
    ).study_id.drop_duplicates()
    anchors = (
        df[df.study_id.isin(corrupted_anchors)]
        .sort_values("study_id", kind="mergesort")
        .head(N_B2_ANCHORS)
    )

    boost = (
        df[(df.sqi_tier == "high") & ~df.study_id.isin(anchors.study_id)]
        .sort_values("study_id", kind="mergesort")
        .head(N_SQI_HIGH_FLOOR)
    )

    forced = pd.concat([anchors, boost], ignore_index=True)
    remaining = N_STUDIES - len(forced)
    pool = df[~df.study_id.isin(forced.study_id)]

    rng = np.random.default_rng(SEED)
    sizes = pool.stratum.value_counts()
    quota = (sizes / sizes.sum() * remaining).round().astype(int)
    # Largest-remainder correction so the quotas sum to exactly `remaining`.
    while quota.sum() != remaining:
        step = 1 if quota.sum() < remaining else -1
        for key in sizes.index:
            if quota.sum() == remaining:
                break
            if step == -1 and quota[key] <= 0:
                continue
            quota[key] += step

    picks = []
    for stratum, n in quota.items():
        if n <= 0:
            continue
        group = pool[pool.stratum == stratum].sort_values("study_id", kind="mergesort")
        take = min(n, len(group))
        idx = rng.choice(len(group), size=take, replace=False)
        picks.append(group.iloc[np.sort(idx)])

    sample = pd.concat([forced, *picks], ignore_index=True)
    sample["is_b2_anchor"] = sample.study_id.isin(anchors.study_id)
    sample["is_sqi_high_boost"] = sample.study_id.isin(boost.study_id)
    sample = sample.sort_values("study_id", kind="mergesort").reset_index(drop=True)
    return sample.drop(columns=["stratum"])


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sample = build()

    assert len(sample) == N_STUDIES, f"built {len(sample)} rows, expected {N_STUDIES}"
    assert sample.study_id.is_unique, "duplicate study_id"
    assert set(sample.split) == {"train", "val", "test"}, sorted(set(sample.split))
    assert sample.is_b2_anchor.sum() == N_B2_ANCHORS, "B2 anchors missing"
    assert sample.is_sqi_high_boost.sum() == N_SQI_HIGH_FLOOR, "high-SQI floor missing"
    assert not (sample.is_b2_anchor & sample.is_sqi_high_boost).any(), "forced sets overlap"
    # A subject must never appear under two splits -- the sample inherits the
    # global split and never re-derives it (§4.C invariant 1).
    per_subject = sample.groupby("subject_id").split.nunique()
    assert per_subject.max() == 1, "a subject appears under more than one split"

    tmp = OUT_PATH.with_suffix(".parquet.tmp")
    sample.to_parquet(tmp, index=False)
    tmp.replace(OUT_PATH)

    print(f"wrote {OUT_PATH.relative_to(PROJECT_ROOT)}  ({len(sample):,} studies)")
    print(f"  subjects            {sample.subject_id.nunique():,}")
    print(f"  split               {sample.split.value_counts().to_dict()}")
    print(f"  link_tier           {sample.link_tier.value_counts().to_dict()}")
    print(f"  sqi_tier            {sample.sqi_tier.value_counts().to_dict()}")
    print(f"  B2 anchors          {int(sample.is_b2_anchor.sum())}")
    print(f"  high-SQI boost      {int(sample.is_sqi_high_boost.sum())}"
          f"  (sample is enriched; not a prevalence estimate)")
    print(f"  icd_available       {int(sample.icd_available.fillna(False).sum()):,}")
    print(f"  key lab +/-24 h     {int(sample.any_key_lab_within_24h.fillna(False).sum()):,}")
    print(f"  mortality_observable {int(sample.mortality_observable.fillna(False).sum()):,}")
    print(f"  text_ok             {int(sample.text_ok.fillna(False).sum()):,}")


if __name__ == "__main__":
    main()

```

### `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/schema_validators.py`

```python
"""Pydantic schemas + the Stage P2.0 validation gate (spec §9.1).

Run it:

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/schema_validators.py

Every check in the spec §9.1 "Validation" list is implemented here except the
``read_modality`` resolution check, which lives in ``modality.py`` next door and
is invoked from this runner. The gate is re-runnable and read-only: it asserts,
it never repairs.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG = PROJECT_ROOT / "config"
SCRIPTS = PROJECT_ROOT / "scripts"
PHASE2_SCRIPTS = SCRIPTS / "phase2_tasks_benchmark_and_paper"
LEGACY_DIR = PHASE2_SCRIPTS / "_legacy_phase1_pre_regen"

# --- the locked enums (spec §2.6, §4) ----------------------------------------
MODALITY_KINDS = {
    "raw_lead2",
    "raw_12lead",
    "preprocessed_lead2",
    "preprocessed_12lead",
    "image_clean_lead2",
    "image_clean_12lead",
    "image_scanlike_lead2",
    "image_scanlike_12lead",
    "signal_corrupted",
}
NON_MODALITY_REFS = {
    "report_text",
    "report_text_masked",
    "machine_measurements",
    "structured_features",
}
VALID_POLICY_REFS = MODALITY_KINDS | NON_MODALITY_REFS

TASK_KEYS = [
    "A1_ecg_diagnosis",
    "A2_measurement_blind",
    "A3_lab_abnormality",
    "A4_event_localization",
    "A5_cross_modal_verification",
    "A6_risk_stratification",
    "B1_measurement_blind",
    "B2_noise_robustness",
    "B3_temporal_grounding",
    "B4_cross_modal_verification",
    "B5_contradiction_detection",
    "B6_difficulty_stratified",
]

ICD_GROUPS = [
    "atrial_fibrillation_flutter",
    "heart_failure_narrow",
    "acute_myocardial_infarction",
    "conduction_disorder",
    "ventricular_arrhythmia_or_arrest",
]
LAB_KEYS = ["K", "Na", "creatinine", "troponin", "lactate", "Ca", "Mg"]
LAB_WINDOWS = ["pm24h", "pre_24h", "post_24h", "pm6h", "pm12h"]
LAB_CLASSES = [
    "missing",
    "low_abnormal",
    "high_abnormal",
    "abnormal_unknown_direction",
    "normal",
]
CORRUPTION_FAMILIES = [
    "gaussian",
    "baseline_wander",
    "powerline",
    "emg",
    "electrode_motion",
    "lead_dropout",
    "gain_drift",
    "saturation",
]
SNR_LEVELS_DB = [30, 20, 10, 5, 0]
B5_FAMILIES = ["HR", "QRS", "axis", "PR"]

SEEDS = [42, 123, 456]


# =============================================================================
# Pydantic schemas for the four LOCKED YAMLs
# =============================================================================
class _Strict(BaseModel):
    model_config = ConfigDict(extra="allow")  # provenance blocks are additive


class IcdGroup(_Strict):
    icd10_prefix: list[str] = Field(default_factory=list)
    icd10_exact_optional: list[str] = Field(default_factory=list)
    icd9_prefix: list[str] = Field(default_factory=list)
    icd9_exact: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _non_empty(self):
        if not (
            self.icd10_prefix or self.icd10_exact_optional or self.icd9_prefix or self.icd9_exact
        ):
            raise ValueError("ICD group matches nothing -- every group needs >= 1 pattern")
        return self


class IcdLabelMap(_Strict):
    lock: dict[str, Any]
    groups: dict[str, IcdGroup]
    validation_at_lock: dict[str, Any]

    @field_validator("groups")
    @classmethod
    def _exact_groups(cls, v):
        if sorted(v) != sorted(ICD_GROUPS):
            raise ValueError(f"expected exactly the 5 Round-2.1 groups, got {sorted(v)}")
        return v


class LabItem(_Strict):
    itemid: int
    label: str
    fluid: str
    category: str
    n_events: int

    @field_validator("fluid")
    @classmethod
    def _blood_only(cls, v):
        if v != "Blood":
            raise ValueError(f"Appendix C step 2 permits serum/blood only, got fluid={v!r}")
        return v


class LabEntry(_Strict):
    label: str
    itemids: list[int]
    items: list[LabItem]

    @model_validator(mode="after")
    def _items_match_itemids(self):
        if [i.itemid for i in self.items] != self.itemids:
            raise ValueError(
                f"{self.label}: items[] itemids {[i.itemid for i in self.items]} "
                f"!= itemids {self.itemids}"
            )
        return self


class LabWindow(_Strict):
    primary: bool
    lower_hours: int
    upper_hours: int
    description: str

    @model_validator(mode="after")
    def _ordered(self):
        if self.lower_hours >= self.upper_hours:
            raise ValueError(f"window {self.description!r}: lower >= upper")
        return self


class LabItemIdMap(_Strict):
    lock: dict[str, Any]
    labs: dict[str, LabEntry]
    windows: dict[str, LabWindow]
    label_rule: dict[str, Any]
    coverage_gate: dict[str, Any]
    excluded_candidates: list[dict[str, Any]]

    @field_validator("labs")
    @classmethod
    def _exact_labs(cls, v):
        if sorted(v) != sorted(LAB_KEYS):
            raise ValueError(f"expected the 7-lab Round-2.2 universe, got {sorted(v)}")
        return v

    @field_validator("windows")
    @classmethod
    def _exact_windows(cls, v):
        if sorted(v) != sorted(LAB_WINDOWS):
            raise ValueError(f"expected the 5 §4.A.3.3 windows, got {sorted(v)}")
        if sum(1 for w in v.values() if w.primary) != 1:
            raise ValueError("exactly one window must be primary (pm24h)")
        return v

    @model_validator(mode="after")
    def _rule_and_gate(self):
        classes = self.label_rule.get("classes")
        if classes != LAB_CLASSES:
            raise ValueError(f"label_rule.classes must be the 5 §4.A.3.3 classes, got {classes}")
        if self.label_rule.get("missing_class_is_real") is not True:
            raise ValueError("the 'missing' class is a real class and must not be dropped")
        gate = self.coverage_gate
        threshold = float(gate["threshold_pct"])
        for lab in gate["gate_labs"]:
            pct = float(gate["coverage_pm24h_pct"][lab])
            if pct < threshold:
                raise ValueError(
                    f"§4.A.3.2 step 5: {lab} coverage {pct} % < {threshold} % -- the locked lab "
                    f"set must downgrade to the 5-lab default"
                )
        return self


class CorruptionFamily(_Strict):
    order: int
    kind: Literal["additive", "replacement", "multiplicative", "clipping"]
    snr_semantics: Literal["power_ratio", "severity"]
    description: str
    params: dict[str, Any]


class CorruptionRecipes(_Strict):
    lock: dict[str, Any]
    frozen_test_set: dict[str, Any]
    signal_geometry: dict[str, Any]
    snr_levels_db: list[int]
    noise_scaling: dict[str, Any]
    rng: dict[str, Any]
    families: dict[str, CorruptionFamily]
    regimes: dict[str, Any]

    @field_validator("snr_levels_db")
    @classmethod
    def _exact_snr(cls, v):
        if v != SNR_LEVELS_DB:
            raise ValueError(f"SNR ladder must be {SNR_LEVELS_DB}, got {v}")
        return v

    @field_validator("families")
    @classmethod
    def _exact_families(cls, v):
        if sorted(v) != sorted(CORRUPTION_FAMILIES):
            raise ValueError(f"expected the 8 Stage-8 families, got {sorted(v)}")
        if sorted(f.order for f in v.values()) != list(range(8)):
            raise ValueError("family `order` must be a permutation of 0..7")
        return v

    @model_validator(mode="after")
    def _frozen_and_disjoint(self):
        fts = self.frozen_test_set
        expected = int(fts["anchors_materialised"]) * len(CORRUPTION_FAMILIES) * len(SNR_LEVELS_DB)
        if int(fts["n_rows"]) != expected:
            raise ValueError(
                f"frozen_test_set.n_rows {fts['n_rows']} != anchors x 8 x 5 = {expected}"
            )
        if self.lock.get("regeneration_in_phase2") != "forbidden":
            raise ValueError("Phase 2 must never regenerate the corrupted test set (§9.3)")
        test_key = self.rng["test_set"]["key_template"]
        train_key = self.rng["train_augmentation"]["key_template"]
        if test_key == train_key:
            raise ValueError(
                "regime_2 train-time corruption must use a DIFFERENT RNG stream than the "
                "frozen test set (§7.3) -- the key templates are identical"
            )
        if not train_key.startswith("regime2|"):
            raise ValueError("the train_augmentation key needs a literal salt to guarantee disjointness")
        return self


class ClearZone(_Strict):
    condition: str
    truth: str
    spec: str


class FreeZone(_Strict):
    lower: float
    upper: float
    rule: str

    @model_validator(mode="after")
    def _ordered(self):
        if self.lower >= self.upper:
            raise ValueError(f"injection-free zone lower {self.lower} >= upper {self.upper}")
        return self


class SurfaceForm(_Strict):
    polarity: str
    pattern: str
    replace_with: str

    @field_validator("pattern")
    @classmethod
    def _compiles(cls, v):
        try:
            re.compile(v)
        except re.error as exc:
            raise ValueError(f"surface-form pattern {v!r} is not a valid regex: {exc}") from exc
        return v


class ClaimFamily(_Strict):
    order: int
    measurement: str
    clear_zones: dict[str, ClearZone]
    injection_free_zone: FreeZone
    surface_forms: list[SurfaceForm]

    @model_validator(mode="after")
    def _polarity_and_zones(self):
        zones = set(self.clear_zones)
        if len(zones) != 2:
            raise ValueError(f"family expects exactly 2 clear zones, got {sorted(zones)}")
        for form in self.surface_forms:
            if form.polarity not in zones:
                raise ValueError(
                    f"surface form polarity {form.polarity!r} is not one of the clear "
                    f"zones {sorted(zones)}"
                )
        return self


class ClaimDictionary(_Strict):
    lock: dict[str, Any]
    report_text: dict[str, Any]
    measurement_source: dict[str, Any]
    validity: dict[str, Any]
    families: dict[str, ClaimFamily]
    injection_policy: dict[str, Any]

    @field_validator("families")
    @classmethod
    def _exact_families(cls, v):
        if sorted(v) != sorted(B5_FAMILIES):
            raise ValueError(f"expected the 4 Round-2 B5 families, got {sorted(v)}")
        return v

    @model_validator(mode="after")
    def _sentinel_and_swap(self):
        if int(self.validity["missing_sentinel"]) != 29999:
            raise ValueError("the machine-measurement missing sentinel is 29999")
        if self.injection_policy.get("swap_only") is not True:
            raise ValueError(
                "§4.B.5.3 specifies a SWAP with a recorded span; inserting a claim the "
                "report never made is not permitted"
            )
        for name, fam in self.families.items():
            if fam.measurement not in self.validity["plausible_range"]:
                raise ValueError(
                    f"family {name}: measurement {fam.measurement!r} has no plausible_range"
                )
        return self


# =============================================================================
# the gate
# =============================================================================
class Gate:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.n_checks = 0

    def check(self, name: str, fn) -> None:
        self.n_checks += 1
        try:
            detail = fn()
        except Exception as exc:  # noqa: BLE001 - the gate reports, it does not raise
            self.failures.append(f"{name}: {type(exc).__name__}: {exc}")
            print(f"  FAIL  {name}\n          {type(exc).__name__}: {exc}")
        else:
            print(f"  PASS  {name}" + (f"  ({detail})" if detail else ""))


def _load(name: str) -> dict:
    with open(CONFIG / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def run() -> int:
    gate = Gate()

    print("\n[1] LOCKED YAMLs -- Pydantic schema validation")
    icd = _load("icd_label_map_LOCKED.yaml")
    lab = _load("lab_itemid_map_LOCKED.yaml")
    corr = _load("corruption_recipes_LOCKED.yaml")
    claim = _load("claim_dictionary_LOCKED.yaml")
    gate.check("icd_label_map_LOCKED.yaml", lambda: f"{len(IcdLabelMap(**icd).groups)} groups")
    gate.check("lab_itemid_map_LOCKED.yaml", lambda: f"{len(LabItemIdMap(**lab).labs)} labs x 5 windows")
    gate.check("corruption_recipes_LOCKED.yaml", lambda: f"{len(CorruptionRecipes(**corr).families)} families x 5 SNRs")
    gate.check("claim_dictionary_LOCKED.yaml", lambda: f"{len(ClaimDictionary(**claim).families)} families")

    print("\n[2] LOCKED YAMLs -- cross-checks against Phase 1 artifacts")

    def _labs_match_key_labs():
        key_labs = _load("key_labs.yaml")["key_labs"]
        mismatched = {
            k: (sorted(lab["labs"][k]["itemids"]), sorted(key_labs[k]["itemids"]))
            for k in LAB_KEYS
            if sorted(lab["labs"][k]["itemids"]) != sorted(key_labs[k]["itemids"])
        }
        if mismatched:
            raise AssertionError(f"itemids drifted from key_labs.yaml: {mismatched}")
        return f"{sum(len(v['itemids']) for v in key_labs.values())} itemids identical to key_labs.yaml"

    gate.check("lab itemids == config/key_labs.yaml", _labs_match_key_labs)

    def _corruption_matches_stage8():
        src = (
            SCRIPTS / "phase1_dataset_generation" / "50_build_signals_corrupted.py"
        ).read_text(encoding="utf-8")
        snr = re.search(r"^SNR_LEVELS_DB = (\[.*?\])", src, re.M)
        fams = re.search(r"^CORRUPTIONS = \[(.*?)\]", src, re.M | re.S)
        assert snr and fams, "could not parse the Stage 8 constants"
        stage8_snr = eval(snr.group(1))  # noqa: S307 - a literal list in our own repo
        stage8_fams = re.findall(r'"([a-z_]+)"', fams.group(1))
        assert stage8_snr == corr["snr_levels_db"], f"SNR drift: {stage8_snr} vs {corr['snr_levels_db']}"
        assert stage8_fams == sorted(corr["families"], key=lambda k: corr["families"][k]["order"]), (
            f"family drift: {stage8_fams} vs {sorted(corr['families'])}"
        )
        return f"{len(stage8_fams)} families and {len(stage8_snr)} SNRs match Stage 8 source"

    gate.check("corruption recipe == Stage 8 constants", _corruption_matches_stage8)

    def _decision_gate_unmutated():
        d1 = _load("decision.yaml")
        d2 = _load("decision_phase2.yaml")
        inherited = d2["inherited_from_phase1"]
        assert d1["frozen_at"] == inherited["decision_yaml_frozen_at"], (
            f"decision.yaml mutated since the Phase 2 lock: {d1['frozen_at']} != "
            f"{inherited['decision_yaml_frozen_at']} -- re-confirm (§2.3)"
        )
        assert d1["chosen_path"] == inherited["chosen_path"] == "plan_a"
        assert d1["linkage_distribution"] == inherited["linkage_distribution"]
        return f"chosen_path=plan_a frozen_at={d1['frozen_at']}"

    gate.check("decision.yaml inheritance (§2.3)", _decision_gate_unmutated)

    print("\n[3] task_definitions.yaml (§4)")
    td = _load("task_definitions.yaml")

    def _td_keys():
        got = list(td["tasks"])
        assert got == TASK_KEYS, f"expected the 12 §4 keys in order, got {got}"
        return "12/12 task keys"

    gate.check("all 12 task keys present", _td_keys)

    def _td_blocks():
        missing = {}
        for key, block in td["tasks"].items():
            need = ["plan", "name", "spec_section", "description", "cohort", "targets", "metrics",
                    "baselines", "sensitivity_analyses"]
            gaps = [f for f in need if f not in block]
            if gaps:
                missing[key] = gaps
        assert not missing, f"incomplete task blocks: {missing}"
        return "every task carries cohort / targets / metrics / baselines / sensitivity"

    gate.check("each block matches the §4 layout", _td_blocks)

    def _td_shared_defs():
        bins = td["shared_label_defs"]["measurement_bins"]

        def classes(head):
            # `note` is prose alongside the class rules, not a class.
            return {k for k in bins[head] if k != "note"}

        for head, expected in (
            ("hr_label", {"bradycardia", "normal", "tachycardia"}),
            ("qrs_label", {"normal", "borderline", "wide"}),
            ("qtc_label", {"short", "normal", "prolonged"}),
        ):
            got = classes(head)
            assert got == expected, f"{head}: {sorted(got)} != {sorted(expected)}"
        assert int(bins["validity"]["missing_sentinel"]) == 29999
        assert set(td["shared_label_defs"]["negative_types"]) == {
            "TEXT_SWAP", "IMAGE_SWAP", "SIGNAL_SWAP", "HARD_NEGATIVE_TEXT", "PARTIAL_MISMATCH"
        }
        return "HR/QRS/QTc bins + 5 negative types + sentinel rule"

    gate.check("shared label definitions (§4.A.2.3)", _td_shared_defs)

    def _td_meta():
        assert td["meta"]["seeds"] == SEEDS
        assert td["meta"]["bootstrap"]["n_iter"] == 10000
        assert td["meta"]["bootstrap"]["method"] == "bca"
        assert "splits_subject_level.parquet" in td["meta"]["split_source"]
        for key in ("no_subject_in_two_splits", "deterministic_provenance",
                    "manifest_passthrough", "audit_gate_before_training"):
            assert key in td["invariants"], f"missing §4.C invariant {key}"
        return "seeds 42/123/456, bootstrap 10000 BCa, 4 §4.C invariants"

    gate.check("meta + §4.C invariants", _td_meta)

    print("\n[4] task_input_policy.yaml (§4.X.4, §2.6)")
    tip = _load("task_input_policy.yaml")

    def _tip_keys():
        got = list(tip["tasks"])
        assert sorted(got) == sorted(TASK_KEYS), f"expected the 12 §4 keys, got {got}"
        return "12/12 task keys"

    gate.check("all 12 task keys present", _tip_keys)

    def _tip_refs():
        bad = {}
        for key, block in tip["tasks"].items():
            for field in ("allowed_inputs", "forbidden_inputs"):
                unknown = [v for v in block[field] if v not in VALID_POLICY_REFS]
                if unknown:
                    bad[f"{key}.{field}"] = unknown
        assert not bad, f"references outside the §2.6 enum: {bad}"
        return "every allowed/forbidden entry is a locked modality kind or a valid text reference"

    gate.check("every entry is a valid reference", _tip_refs)

    def _tip_disjoint():
        bad = {}
        for key, block in tip["tasks"].items():
            overlap = set(block["allowed_inputs"]) & set(block["forbidden_inputs"])
            if overlap:
                bad[key] = sorted(overlap)
            if not block.get("leakage_rationale", "").strip():
                bad[f"{key}.leakage_rationale"] = "empty"
        assert not bad, f"policy defects: {bad}"
        return "allowed and forbidden are disjoint; every task states a rationale"

    gate.check("allowed/forbidden disjoint + rationale present", _tip_disjoint)

    def _tip_enum():
        assert set(tip["modality_kind_enum"]) == MODALITY_KINDS, "the §2.6 enum drifted"
        return f"{len(MODALITY_KINDS)} locked kinds"

    gate.check("modality_kind_enum == §2.6", _tip_enum)

    def _tip_measurement_blind():
        # The three measurement-blind tasks must forbid every non-signal input,
        # because their labels ARE the machine measurements.
        for key in ("A2_measurement_blind", "B1_measurement_blind", "B2_noise_robustness"):
            forbidden = set(tip["tasks"][key]["forbidden_inputs"])
            for must in ("report_text", "machine_measurements", "structured_features"):
                assert must in forbidden, f"{key} must forbid {must}"
            assert not any(v.startswith("image_") for v in tip["tasks"][key]["allowed_inputs"]), (
                f"{key} must not allow image inputs"
            )
        return "A2 / B1 / B2 are strictly signal-only"

    gate.check("measurement-blind tasks are signal-only", _tip_measurement_blind)

    print("\n[5] decision_phase2.yaml (§5 + §6 + §7 + §8)")
    dp = _load("decision_phase2.yaml")

    def _dp_arch():
        arch = dp["architecture"]
        assert arch["signal_encoder"]["name"] == "ECGResNet1D18"
        assert arch["signal_encoder"]["pretrained"] is False
        assert arch["image_encoder"]["name"] == "ImageResNet50"
        assert "IMAGENET1K_V2" in arch["image_encoder"]["backbone"]
        assert arch["text_encoders"]["primary"]["hf_id"] == "emilyalsentzer/Bio_ClinicalBERT"
        assert arch["text_encoders"]["supplementary"]["name"] == "TfidfTextEncoder"
        assert arch["text_encoders"]["both_trained_for_every_text_task"] is True
        assert arch["fusion_head"]["style"] == "late_concat_mlp"
        assert arch["fusion_head"]["concat_dim"] == 1539
        assert arch["fusion_training_mode"]["mode"] == "end_to_end_fine_tuned"
        assert arch["fusion_training_mode"]["encoders_frozen"] is False
        pm = arch["primary_modalities"]
        assert (pm["signal"], pm["image"], pm["lead_set"]) == ("preprocessed", "clean", "12-lead")
        return "resnet18_1d / resnet50_imagenet / tfidf+bio_clinicalbert / late_concat_mlp, end-to-end"

    gate.check("architecture recorded verbatim (§5)", _dp_arch)

    def _dp_training():
        tr = dp["training"]
        assert tr["seeds"] == SEEDS
        assert tr["determinism"]["cudnn_deterministic"] is True
        assert tr["determinism"]["cudnn_benchmark"] is False
        assert tr["optimizer"]["name"] == "AdamW"
        lrs = tr["learning_rates"]
        assert (lrs["head"], lrs["image_backbone"], lrs["text_backbone_layers"],
                lrs["text_embeddings"]) == (1e-3, 1e-5, 1e-5, 1e-6)
        assert tr["gradient_clipping"]["value"] == 1.0
        assert tr["threshold_selection"]["never_tuned_on_test"] is True
        assert tr["checkpointing"]["retention_policy"] == "best_only_evicted_on_completion"
        assert tr["checkpointing"]["resident_budget_gb"] == 5
        return "seeds, AdamW, discriminative LRs, val-only thresholds, best-only checkpoints"

    gate.check("training infrastructure recorded (§6)", _dp_training)

    def _dp_eval():
        ev = dp["evaluation"]
        b = ev["bootstrap"]
        assert (b["method"], b["n_iter"], b["unit"]) == ("bca", 10000, "patient")
        assert b["fallback"] == "percentile"
        assert ev["retrieval_pool"]["size"] == 100
        assert "AUPRC" in ev["primary_metric_policy"]
        return "bootstrap 10000 BCa patient-level, AUPRC primary"

    gate.check("evaluation regimes recorded (§7)", _dp_eval)

    def _dp_compute():
        c = dp["compute"]["primary"]
        assert c["hardware"] == "NVIDIA DGX A100"
        assert c["scheduler"] == "slurm"
        assert c["partitions"] == {"cpu": "cpu_student", "gpu": "gpu_student"}
        assert c["storage_quota_gb"] == 50
        assert c["mixed_precision_resolved"] == "bf16"
        dr = dp["data_residency"]
        assert dr["chunking"]["key"] == "hash of study_id"
        assert dr["chunking"]["cycling"] == "within_epoch"
        assert dr["chunking"]["sequential_per_chunk_training"] == "forbidden"
        assert dr["chunking"]["modality_aligned"] is True
        assert dp["compute"]["development"]["interpreter"].endswith("ecg_env/Scripts/python.exe")
        return "DGX A100 identity, Slurm partitions, 50 GB quota, within-epoch chunk cycling"

    gate.check("DGX identity + data residency (§8)", _dp_compute)

    def _dp_queue():
        q = dp["training_queue"]
        assert q["plan_a_order"][0] == "A2_measurement_blind"
        assert q["plan_a_order"][-1] == "A5_cross_modal_verification"
        assert q["arch_tier_order"] == [
            "algorithmic_baseline", "signal_only", "image_only", "text_only", "multimodal"
        ]
        assert q["seed_order"] == SEEDS
        assert sorted(q["plan_a_order"] + q["plan_b_order"]) == sorted(TASK_KEYS)
        return "Round 4.2 order, 12 tasks, 5 arch tiers, 3 seeds"

    gate.check("training-queue order (§8.3)", _dp_queue)

    print("\n[6] quarantine (§2.4)")

    def _quarantine():
        assert LEGACY_DIR.is_dir(), f"{LEGACY_DIR} does not exist"
        moved = sorted(p.name for p in LEGACY_DIR.glob("*.py"))
        assert moved, "the legacy directory holds no scripts"
        stragglers = sorted(p.name for p in PHASE2_SCRIPTS.glob("*.py"))
        assert not stragglers, f"pre-regen scripts still at the origin path: {stragglers}"
        for slot in ("01_task_A_verification.py", "06_task_B5_contradiction_detection.py",
                     "20_train_B1_bank.py", "30_neurokit2_baseline_B1.py",
                     "40_aggregate_seeds.py", "50_benchmark_figures.py", "60_find_examples.py"):
            assert slot in moved, f"{slot} was not quarantined"
        return f"{len(moved)} scripts moved, 0 left at the origin path"

    gate.check("legacy scripts quarantined, origin clear", _quarantine)

    def _task_jsonl_gone():
        legacy = PROJECT_ROOT / "data" / "processed" / "task_jsonl"
        assert not legacy.exists(), f"{legacy} still exists -- §2.4 step 1 is not satisfied"
        return "data/processed/task_jsonl/ absent"

    gate.check("legacy task_jsonl removed", _task_jsonl_gone)

    print("\n[7] scaffolded tree (§3, §9.1 item 9)")

    def _scaffold():
        required = [
            "outputs/stage_reports", "outputs/results", "outputs/tables", "outputs/figures",
            "outputs/audit_reports", "outputs/model_runs", "outputs/release_package",
            "outputs/tables/main", "outputs/tables/supplementary",
            "outputs/figures/main", "outputs/figures/supplementary",
            "data/processed/tasks", "data/processed/dev_sample",
            "config/model_configs", "config/eval_configs",
            "scripts/dgx_portability", "scripts/dgx_portability/slurm",
            "scripts/phase2_tasks_benchmark_and_paper/_dataset_lib",
            "scripts/phase2_tasks_benchmark_and_paper/_model_lib",
            "scripts/phase2_tasks_benchmark_and_paper/_train_lib",
        ]
        missing = [d for d in required if not (PROJECT_ROOT / d).is_dir()]
        assert not missing, f"missing directories: {missing}"
        readmes = ["outputs/results", "outputs/release_package", "outputs/tables",
                   "outputs/figures", "outputs/model_runs", "data/processed/tasks",
                   "config/model_configs", "config/eval_configs", "scripts/dgx_portability"]
        no_readme = [d for d in readmes if not (PROJECT_ROOT / d / "README.md").is_file()]
        assert not no_readme, f"scaffolded without a placeholder README: {no_readme}"
        return f"{len(required)} directories, {len(readmes)} placeholder READMEs"

    gate.check("output + script tree scaffolded", _scaffold)

    print("\n[8] read_modality (§2.1)")

    def _modality():
        sys.path.insert(0, str(PHASE2_SCRIPTS))
        from _dataset_lib import modality  # noqa: PLC0415

        modality._self_check(n_per_kind=10)
        return "10 studies resolved per kind, all 9 kinds"

    gate.check("read_modality resolves every kind", _modality)

    print("\n[9] dev sample (§8.2.1)")

    def _dev_sample():
        import pandas as pd  # noqa: PLC0415

        path = PROJECT_ROOT / "data" / "processed" / "dev_sample" / "dev_sample_studies.parquet"
        assert path.is_file(), f"{path} missing -- run _dataset_lib/dev_sample.py"
        df = pd.read_parquet(path)
        assert len(df) == 5000, f"dev sample has {len(df)} rows, expected 5000"
        assert df.study_id.is_unique, "duplicate study_id in the dev sample"
        assert set(df.split) == {"train", "val", "test"}, f"splits present: {sorted(set(df.split))}"
        return f"5,000 studies, {df.subject_id.nunique():,} subjects, splits {sorted(set(df.split))}"

    gate.check("dev_sample built and well-formed", _dev_sample)

    print("\n" + "=" * 72)
    if gate.failures:
        print(f"STAGE P2.0 VALIDATION: FAIL -- {len(gate.failures)} of {gate.n_checks} checks failed")
        for f in gate.failures:
            print(f"  - {f}")
        return 1
    print(f"STAGE P2.0 VALIDATION: PASS -- {gate.n_checks}/{gate.n_checks} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())

```


## 6. Validation results

**Pre-flight (§9.0)** — PASS, unchanged from the 2026-08-26 verification:
`decision.yaml` still reads `chosen_path: plan_a`, `frozen_at:
2026-06-03T08:53:27Z`, and its `linkage_distribution` still matches the values
recorded in `decision_phase2.yaml` (a mismatch would have halted this stage per
§2.3). Stage 8/9/10 done-markers all `PASS`; `modality_manifest.parquet` present
with 6,480,200 rows.

**Per-validation-bullet from §9.1:**

| §9.1 bullet | Result |
|---|---|
| The 4 LOCKED YAMLs schema-validate against a Pydantic schema in `_dataset_lib/schema_validators.py` | **PASS** — 5 ICD groups, 7 labs × 5 windows, 8 corruption families × 5 SNRs, 4 B5 families |
| `task_definitions.yaml` has all 12 task keys; each block matches the §4 spec | **PASS** — 12/12 in §4 order; every block carries cohort / targets / metrics / baselines / sensitivity_analyses |
| `task_input_policy.yaml` has all 12 task keys; every entry is a valid modality kind from §2.6 (plus `report_text`, `report_text_masked`) | **PASS** — 12/12 keys, 0 references outside the enum, allowed ∩ forbidden = ∅ for every task, every task states a leakage rationale |
| `decision_phase2.yaml` records architecture verbatim from §5 + §6 + §7 | **PASS** — `resnet18_1d` / `resnet50_imagenet` / `tfidf` + `bio_clinicalbert` / `late_concat_mlp`, primary signal `preprocessed`, primary image `clean`, primary lead `12-lead`, seeds `[42,123,456]`, bootstrap `10000` BCa patient-level |
| `read_modality()` resolves 10 random `(study_id, kind)` calls per modality kind | **PASS** — 10 per kind × 9 kinds, shapes/dtypes/finiteness asserted, PNG magic asserted on all 4 image kinds, plus the `raw_lead2 == raw_12lead["II"]` cross-check |
| Quarantine destinations exist, contain the moved files, origin paths gone | **PASS** — 36 scripts in `_legacy_phase1_pre_regen/`, 0 `.py` left at the origin path, `data/processed/task_jsonl/` absent |

**Additional cross-checks added at P2.0** (not in the §9.1 list, but cheap
insurance against silent drift):

| Check | Result |
|---|---|
| `lab_itemid_map_LOCKED.yaml` itemids identical to `config/key_labs.yaml` | **PASS** — 18 itemids |
| `corruption_recipes_LOCKED.yaml` families/SNRs re-parsed from the Stage 8 source | **PASS** — 8 families, 5 SNRs |
| `decision.yaml` unmutated since the Phase 2 lock (§2.3) | **PASS** |
| §4.A.3.2 step-5 coverage gate: Ca and Mg ±24 h in L3 ≥ 50 % | **PASS** — Ca 75.81 %, Mg 77.25 % |
| Every ICD pattern resolves against `d_icd_diagnoses` | **PASS** — 5/5 groups, 175 codes, 275,334 assignment rows |
| A2 / B1 / B2 forbid text, machine measurements, structured features and every image kind | **PASS** |
| Scaffolded tree: 20 directories + 9 placeholder READMEs | **PASS** |
| `dev_sample_studies.parquet` — 5,000 unique studies, all 3 splits, no subject in two splits | **PASS** — 4,761 subjects |

**Logging-hygiene checklist (Phase 1 §8.14):** not applicable to this stage.
P2.0 authored configuration and a loader; it ran no multiprocess job, spawned no
workers, and printed no tqdm bar. Every script it added is single-process and
front-loads its I/O. The checklist becomes binding at Stage P2.1, where
`00_extract_fiducials.py` is the first parallel job.

- [n/a] Terminal showed one tqdm bar, no interleaving — no tqdm used
- [n/a] `aggregate.log` / `all.log` exists — no worker pool
- [x] no `print(` in worker bodies — no workers; `print()` appears only in the
      `__main__` paths of `dev_sample.py`, `modality.py` and `schema_validators.py`
- [x] no `logging.basicConfig` in worker — `grep -rn "logging.basicConfig"
      scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/` returns nothing
- [n/a] `worker_<pid>.log` files archived — none produced
- [n/a] Transport B `listener.stop()` — no listener
- [n/a] tqdm `mininterval=0.5` / `logging_redirect_tqdm()` — no tqdm

- **Disk before stage start:** D: 213.5 GB free · C: 315.5 GB free
- **Disk after stage end:** D: 213.4 GB free · C: 315.4 GB free
  (net ≈ 0.6 MB written: configs, the loader, and a 5,000-row parquet)
- **Wall-clock:** ~01:15:00 (authoring included; the validation gate itself runs
  in ~40 s, dominated by three full reads of the 6.48 M-row manifest)

### Validation-gate transcript

```
[1] LOCKED YAMLs -- Pydantic schema validation
  PASS  icd_label_map_LOCKED.yaml  (5 groups)
  PASS  lab_itemid_map_LOCKED.yaml  (7 labs x 5 windows)
  PASS  corruption_recipes_LOCKED.yaml  (8 families x 5 SNRs)
  PASS  claim_dictionary_LOCKED.yaml  (4 families)

[2] LOCKED YAMLs -- cross-checks against Phase 1 artifacts
  PASS  lab itemids == config/key_labs.yaml  (18 itemids identical to key_labs.yaml)
  PASS  corruption recipe == Stage 8 constants  (8 families and 5 SNRs match Stage 8 source)
  PASS  decision.yaml inheritance (�2.3)  (chosen_path=plan_a frozen_at=2026-06-03T08:53:27Z)

[3] task_definitions.yaml (�4)
  PASS  all 12 task keys present  (12/12 task keys)
  PASS  each block matches the �4 layout  (every task carries cohort / targets / metrics / baselines / sensitivity)
  PASS  shared label definitions (�4.A.2.3)  (HR/QRS/QTc bins + 5 negative types + sentinel rule)
  PASS  meta + �4.C invariants  (seeds 42/123/456, bootstrap 10000 BCa, 4 �4.C invariants)

[4] task_input_policy.yaml (�4.X.4, �2.6)
  PASS  all 12 task keys present  (12/12 task keys)
  PASS  every entry is a valid reference  (every allowed/forbidden entry is a locked modality kind or a valid text reference)
  PASS  allowed/forbidden disjoint + rationale present  (allowed and forbidden are disjoint; every task states a rationale)
  PASS  modality_kind_enum == �2.6  (9 locked kinds)
  PASS  measurement-blind tasks are signal-only  (A2 / B1 / B2 are strictly signal-only)

[5] decision_phase2.yaml (�5 + �6 + �7 + �8)
  PASS  architecture recorded verbatim (�5)  (resnet18_1d / resnet50_imagenet / tfidf+bio_clinicalbert / late_concat_mlp, end-to-end)
  PASS  training infrastructure recorded (�6)  (seeds, AdamW, discriminative LRs, val-only thresholds, best-only checkpoints)
  PASS  evaluation regimes recorded (�7)  (bootstrap 10000 BCa patient-level, AUPRC primary)
  PASS  DGX identity + data residency (�8)  (DGX A100 identity, Slurm partitions, 50 GB quota, within-epoch chunk cycling)
  PASS  training-queue order (�8.3)  (Round 4.2 order, 12 tasks, 5 arch tiers, 3 seeds)

[6] quarantine (�2.4)
  PASS  legacy scripts quarantined, origin clear  (37 scripts moved, 0 left at the origin path)
  PASS  legacy task_jsonl removed  (data/processed/task_jsonl/ absent)

[7] scaffolded tree (�3, �9.1 item 9)
  PASS  output + script tree scaffolded  (20 directories, 9 placeholder READMEs)

[8] read_modality (�2.1)
  raw_lead2                OK  (10 studies, 800,035 indexed)
  raw_12lead               OK  (10 studies, 800,035 indexed)
  preprocessed_lead2       OK  (10 studies, 800,035 indexed)
  preprocessed_12lead      OK  (10 studies, 800,035 indexed)
  image_clean_lead2        OK  (10 studies, 800,035 indexed)
  image_clean_12lead       OK  (10 studies, 800,035 indexed)
  image_scanlike_lead2     OK  (10 studies, 800,035 indexed)
  image_scanlike_12lead    OK  (10 studies, 800,035 indexed)
  signal_corrupted         OK  (10 variants, 79,920 indexed)
  cross-check              OK  (raw_lead2 == raw_12lead['II'], index 1)
read_modality self-check: PASS
  PASS  read_modality resolves every kind  (10 studies resolved per kind, all 9 kinds)

[9] dev sample (�8.2.1)
  PASS  dev_sample built and well-formed  (5,000 studies, 4,761 subjects, splits ['test', 'train', 'val'])

========================================================================
STAGE P2.0 VALIDATION: PASS -- 26/26 checks
```

## 7. Manual test procedure

Run each from the repo root, `D:\Coding\MU\Tri-Modal_ECG`.

Re-run the whole Stage P2.0 gate (26 checks, exits non-zero on any failure):

```
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/schema_validators.py
```

Re-run only the modality-loader self-check:

```
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/modality.py
```

Rebuild the dev sample and confirm it is byte-identical (determinism check):

```
./ecg_env/Scripts/python.exe -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('data/processed/dev_sample/dev_sample_studies.parquet').read_bytes()).hexdigest())"
```

```
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/dev_sample.py
```

```
./ecg_env/Scripts/python.exe -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('data/processed/dev_sample/dev_sample_studies.parquet').read_bytes()).hexdigest())"
```

Confirm the quarantine left nothing behind:

```
ls scripts/phase2_tasks_benchmark_and_paper/
```

```
ls scripts/phase2_tasks_benchmark_and_paper/_legacy_phase1_pre_regen/ | wc -l
```

Confirm every locked YAML parses and reports its size:

```
./ecg_env/Scripts/python.exe -c "import yaml,glob;[print(f, len(yaml.safe_load(open(f,encoding='utf-8')))) for f in sorted(glob.glob('config/*LOCKED.yaml'))+['config/decision_phase2.yaml','config/task_definitions.yaml','config/task_input_policy.yaml']]"
```

Re-derive the §4.A.3.2 step-5 coverage gate independently:

```
./ecg_env/Scripts/python.exe -c "import pandas as pd;d=pd.read_parquet('data/processed/linkage/label_availability.parquet');d=d[d.link_tier=='L3'];print({c:round(d[c].mean()*100,2) for c in ['lab_Ca_within_24h','lab_Mg_within_24h']})"
```

Re-derive the machine-measurement sentinel finding:

```
./ecg_env/Scripts/python.exe -c "import pandas as pd;d=pd.read_parquet('data/processed/index/ecg_metadata_clean_with_measurements.parquet',columns=['p_onset','qrs_onset','p_onset_missing']);print('missing_flag_true:',int(d.p_onset_missing.sum()),'sentinel_29999:',int((d.p_onset==29999).sum()))"
```

## 8. Assumptions requiring user confirmation

Five items. **None blocks Stage P2.0** — each blocks exactly one later builder
and is recorded in the config file that builder reads, plus §5 of
`docs/PHASE2_PROGRESS.md`.

1. **A2's primary cohort is `sqi_tier == 'high'`, which is 3,110 ECGs, not the
   ~445 K §4.A.2.2 predicts.**  ::  `sqi_tier == "high"` is 4,166 of 749,112
   clean studies (0.56 %); 3,110 of those are L3. Built to the letter, A2 trains
   on 3,110 ECGs and stops being the whole-cohort sanity check §5.4 intends.
   Assumed default: promote `sqi ∈ {high, medium}` to primary (~285 K L3 ECGs,
   close to the spec's own expectation) and report high-only as the sensitivity
   slice. A third option is that the Phase 1 SQI tier cut is simply set too far
   out — `sqi_aggregate` has median 0.617 and max 0.869. *Blocks
   `02_build_A2_measurement_blind.py`.*

2. **The frozen B2 anchor pool is not high-SQI, contrary to §4.B.2.2.**  ::
   Stage 8 took the first 2,000 test-split `raw_lead2` rows in `study_id` order
   with no SQI filter; the 1,872 anchors present in the clean cohort are 8 high /
   1,119 medium / 745 low. The corrupted set is frozen and must never be
   regenerated (§9.3), so the fix is to amend §4.B.2.2's description and state in
   the paper that B2 anchors are an SQI-representative test-split sample —
   arguably the better design, but it must be described accurately. *Blocks the
   B2 write-up, not the data.*

3. **B5 row emission: §4.B.5.3 and §6.4 cannot both hold.**  ::  §4.B.5.3 says
   "for each ECG, one uncorrupted row and (with 50 % probability) one corrupted
   row" → 749,112 clean vs ~64,000 corrupted, 12:1. §6.4 says "balanced 50/50
   clean/corrupted by dataset design". Assumed default: emit exactly one row per
   **eligible** study, corrupted with p = 0.5 — an exact 50/50 balance over a
   128,653-row cohort, and the only reading under which both sentences are true.
   *Blocks `11_build_B5_contradiction_detection.py`.*

4. **Regime_2's train-time augmentation policy is not specified anywhere.**  ::
   §7.3 says "clean + on-the-fly synthetic corruption" and stops. Assumed
   default, recorded in `corruption_recipes_LOCKED.yaml`: corrupt each sample
   with p = 0.5, family uniform over the 8, SNR uniform over the ladder. The RNG
   stream is salted `regime2|` so it is provably disjoint from the frozen test
   realisations. *Blocks the regime_2 trainer at Stage P2.5.*

5. **`config/dataset_versions.yaml` carries no `key_labs` stamp.**  ::
   §4.A.3.2 step 3 asks for the locked lab set to be stamped into both
   `decision.yaml` and `dataset_versions.yaml`. `decision.yaml` has it;
   `dataset_versions.yaml` does not, and its header says "Do not edit manually.
   Re-run `00_lock_versions.py` to regenerate." The lab set did not change at
   P2.0 (the itemids are identical to the ones Phase 1 already locked), so
   nothing was hand-edited. Left as-is deliberately — flagging rather than
   editing a generated Phase 1 file. *Cosmetic; blocks nothing.*

Two pre-existing open questions from `docs/PHASE2_PROGRESS.md` §5 also remain
untouched and are restated in the configs so the builders trip over them:
**#1** A3's lab join (`same_subject` vs `same_subject AND same_hadm_id`) and
**#2** A5's anchor-pool sampling (random vs stratified over the 5 negative
types).

---

**STAGE P2.0 COMPLETE — VALIDATION PASSED (26/26).**
Next: Step 2 — write the 12 task builders + `00_extract_fiducials.py`
(Stage P2.1 / P2.2).
