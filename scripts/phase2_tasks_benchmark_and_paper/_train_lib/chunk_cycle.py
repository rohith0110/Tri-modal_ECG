"""Cycle chunk pieces WITHIN an epoch (spec §8.2 rule 2), two resident at a time.

The rule is locked and this module does not get to reinterpret it:

* an epoch visits **every** piece, in an order reshuffled every epoch;
* at most two pieces are resident, so the loop stages the next one and evicts
  the one it has finished with **during** the epoch;
* training piece 0 to convergence and then moving to piece 1 is **forbidden** --
  that is block-local SGD, and it forgets.

What that means concretely, and why it lives here rather than in the Dataset:
staging a piece is a transport call (`stage_data.sh`), which is an operation on
the node, not a property of a row. The Dataset can already *read* any staged
piece (`_dataset_lib/chunk_pieces.py` installs a manifest overlay for it); this
decides *when* a piece arrives and when it leaves.

**Transport, and what is still unknown.** Fetching piece k+1 mid-epoch needs
whatever `campaigns.sh::transport()` resolves to:

* ``rclone``          -- the online path: the piece is pulled from R2 mid-epoch.
* ``rclone-offline``  -- rclone exists but the node has no outbound internet.
  Nothing can be fetched mid-epoch, so the piece set must already be on the
  node; `TRIMODAL_SOURCE` (a mounted drive or a campus share) is the documented
  way, and this module then "stages" by copying locally, which is the same call.
* ``local``           -- TRIMODAL_SOURCE is set; works with no internet at all.
* ``none``            -- refuse, loudly, before the first epoch rather than at
  the first swap.

**Whether the DGX has outbound internet is OPEN QUESTION 4** and is answered in
one command on a compute node:

    rclone lsd r2:trimodal-data && echo ONLINE || echo OFFLINE

Until that is answered the online path is written but unvalidated: `plan()`
records the transport it saw into the run metadata, so a paper run can always
say which one it used.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Sequence

import numpy as np

from _dataset_lib import chunk_pieces

PORTABILITY = Path(__file__).resolve().parents[2] / "dgx_portability"
STAGE_DATA = PORTABILITY / "stage_data.sh"
EVICT_DATA = PORTABILITY / "evict_data.sh"

# §8.2 rule 2: "two pieces are resident at a time (train on k, prefetch k+1,
# evict k-1)". The window is that pair.
RESIDENT_PIECES = 2


def transport() -> str:
    """Ask campaigns.sh what transport this node actually has."""
    try:
        result = subprocess.run(
            ["bash", "-c", f'. "{PORTABILITY / "campaigns.sh"}" >/dev/null 2>&1; transport'],
            capture_output=True, text=True, timeout=60)
        return (result.stdout or "").strip() or "none"
    except (OSError, subprocess.SubprocessError):
        return "none"


class ChunkCycle:
    """The piece order for one epoch, and the staging calls that follow it."""

    def __init__(self, campaign: int, study_ids: np.ndarray, *, seed: int,
                 total_pieces: int | None = None, logger=None, dry_run: bool = False):
        self.campaign = int(campaign)
        self.study_ids = np.asarray(study_ids)
        self.seed = int(seed)
        self.total = int(total_pieces or chunk_pieces.n_pieces())
        self.log = logger
        self.dry_run = dry_run
        self.transport = transport()
        self.assignment = chunk_pieces.piece_of(self.study_ids, self.total)
        self.staged: list[int] = []

    # -- the order -----------------------------------------------------------
    def piece_order(self, epoch: int) -> list[int]:
        """Every piece, once, in an order that changes with the epoch."""
        rng = np.random.default_rng(self.seed * 100_003 + epoch)
        return [int(p) for p in rng.permutation(self.total)]

    def windows(self, epoch: int) -> list[list[int]]:
        """The epoch's pieces, grouped into resident windows."""
        order = self.piece_order(epoch)
        return [order[i:i + RESIDENT_PIECES] for i in range(0, len(order), RESIDENT_PIECES)]

    def rows_for(self, pieces: Sequence[int]) -> np.ndarray:
        """Row positions whose study lives in one of these pieces."""
        return np.flatnonzero(np.isin(self.assignment, np.asarray(pieces, dtype="int32")))

    # -- staging -------------------------------------------------------------
    def ensure(self, pieces: Sequence[int]) -> None:
        """Make exactly these pieces resident: stage what is missing, evict the rest."""
        want = sorted(int(p) for p in pieces)
        if want == self.staged:
            return
        for piece in want:
            if piece not in self.staged:
                self._stage(piece)
        for piece in list(self.staged):
            if piece not in want:
                self._evict(piece)
        self.staged = want
        chunk_pieces.install_overlays(self.log)     # the new piece becomes readable

    def _run(self, command: list[str]) -> None:
        if self.log:
            self.log.info("chunk cycle: %s", " ".join(str(c) for c in command))
        if self.dry_run:
            return
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"chunk staging failed ({' '.join(command)}):\n{result.stderr[-2000:]}")

    def _stage(self, piece: int) -> None:
        if self.transport == "none":
            raise RuntimeError(
                "chunk cycling needs a transport and this node has none. Either configure "
                "rclone with the bucket-scoped token, or export TRIMODAL_SOURCE=/path/to/data "
                "(mounted drive or campus share) -- the offline path. See open question 4.")
        self._run(["bash", str(STAGE_DATA), str(self.campaign),
                   "--pieces", str(piece), "--pieces-only"])

    def _evict(self, piece: int) -> None:
        self._run(["bash", str(EVICT_DATA), "--pieces", str(piece)])

    # -- what the run records ------------------------------------------------
    def metadata(self, epoch: int) -> dict:
        """Stamped into the run's metadata, so the supplementary can describe it.

        §8.2 calls the block-shuffled sampling a documented deviation from plain
        shuffling; a deviation that is not recorded per run is not documented.
        """
        return {
            "chunked": True,
            "n_pieces": self.total,
            "resident_pieces": RESIDENT_PIECES,
            "piece_order": self.piece_order(epoch),
            "sampling": "aligned i.i.d. chunk cycling within each epoch "
                        "(§8.2 rule 2); shuffled inside a two-piece window, "
                        "piece order reshuffled every epoch",
            "transport": self.transport,
            "piece_salt": chunk_pieces.PIECE_SALT,
        }


def _self_check() -> None:
    """The properties the science depends on, on a two-piece toy set."""
    import types

    ids = np.arange(1000, 1400)
    cycle = ChunkCycle(6, ids, seed=42, total_pieces=2, dry_run=True)

    # 1. one epoch visits every study exactly once
    visited: list[int] = []
    for window in cycle.windows(epoch=0):
        visited.extend(cycle.rows_for(window).tolist())
    assert sorted(visited) == list(range(len(ids))), \
        "an epoch must visit every study exactly once"

    # 2. the order is not piece-sequential across epochs -- it is reshuffled
    orders = {tuple(cycle.piece_order(e)) for e in range(8)}
    assert len(orders) > 1, "the piece order must change between epochs"

    # 3. signal and image agree on the piece for the same study: the assignment
    #    is a pure function of study_id, so two independently cut modalities
    #    place a study identically. This is what a fusion batch depends on.
    signal_assignment = chunk_pieces.piece_of(ids, 8)
    image_assignment = chunk_pieces.piece_of(ids, 8)
    assert np.array_equal(signal_assignment, image_assignment), \
        "modality alignment broken: piece k must hold the same studies in every kind"

    # 4. a window is a shuffle buffer, not an ordering: rows inside it come out
    #    shuffled rather than in row order
    from _train_lib.trainer import build_batch_order

    pool = cycle.rows_for([0])
    batches = build_batch_order(len(ids), 16, seed=1, epoch=0, shuffle=True, index_pool=pool)
    flat = [i for b in batches for i in b]
    assert sorted(flat) == sorted(pool.tolist()), "the window must cover its rows exactly once"
    assert flat != sorted(flat), "rows inside a piece window must be shuffled"

    # 5. never more than two pieces resident
    for window in cycle.windows(epoch=3):
        assert len(window) <= RESIDENT_PIECES

    print("chunk_cycle self-check PASS")


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    _self_check()
