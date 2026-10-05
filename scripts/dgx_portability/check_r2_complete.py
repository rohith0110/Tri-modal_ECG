#!/usr/bin/env python3
"""Is every dataset of every campaign in R2 at the key and size `stage_data.sh` expects?

`upload_data.py --sizes` and `check_campaign_data.py` both read LOCAL files, so
neither proves the bucket. This lists `r2:trimodal-data` once and compares it
with `dataset_files()` for every dataset of every campaign: each key present,
each byte size equal to the local file, each directory's checksum manifest
present. A dataset with no local copy any more is checked by presence only.

Run it on the `data-laptop` (it needs `data/processed`) after any upload:

    ./ecg_env/Scripts/python.exe scripts/dgx_portability/check_r2_complete.py

`code` / `configs` go stale with every commit that touches `scripts/` or
`config/`. That is expected -- git is the source of truth on the DGX and the
bucket copy is only the fallback -- so they are reported as STALE and fail the
check only under --strict-code.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import upload_data as u  # noqa: E402

GIT_OWNED = {"code", "configs"}


def main() -> int:
    strict_code = "--strict-code" in sys.argv[1:]
    listing = subprocess.run(
        ["rclone", "lsf", "-R", "--files-only", "--format", "sp", "--separator", "\t", u.REMOTE],
        capture_output=True, text=True, check=True).stdout
    remote = {key: int(size) for size, key in (line.split("\t", 1) for line in listing.splitlines())}
    print(f"R2: {len(remote)} objects, {sum(remote.values()) / 2**30:.3f} GiB")

    datasets: dict[str, list[int]] = {}
    for campaign in range(1, u.n_campaigns() + 1):
        for dataset in u.campaign_datasets(campaign):
            datasets.setdefault(dataset, []).append(campaign)

    bad = 0
    for dataset, campaigns in datasets.items():
        if dataset == "results":        # r2:trimodal-results, filled from the DGX
            continue
        try:
            pairs = u.dataset_files(dataset)
        except SystemExit:
            # deleted locally after upload (R2 is the authority): presence only
            prefix = f"chunks/{dataset[:-len('_pieces')]}/" if dataset.endswith("_pieces") \
                else f"{dataset}/"
            keys = [k for k in remote if k.startswith(prefix)]
            bad += not keys
            print(f"{'ok  ' if keys else 'FAIL'} {dataset:32s} local absent; R2 has {len(keys)} "
                  f"objects, {sum(remote[k] for k in keys) / 1e9:.2f} GB   campaigns {campaigns}")
            continue
        missing = [k for _, k in pairs if k not in remote]
        wrong = [k for p, k in pairs if k in remote and remote[k] != p.stat().st_size]
        # the manifest stage_data.sh verifies against, one per remote directory
        directories = {Path(k).parent.as_posix() for _, k in pairs}
        manifests = {f"{d}/checksums.json" if d.startswith("chunks/")
                     else f"{d}/checksums_{dataset}.json" for d in directories}
        no_manifest = sorted(m for m in manifests if m not in remote)
        ok = not (missing or wrong or no_manifest)
        stale_only = not ok and dataset in GIT_OWNED and not strict_code
        bad += not ok and not stale_only
        size = sum(p.stat().st_size for p, _ in pairs) / 1e9
        print(f"{'ok  ' if ok else 'STALE' if stale_only else 'FAIL'} {dataset:32s} "
              f"{len(pairs):4d} files {size:7.2f} GB   campaigns {campaigns}")
        for label, items in (("missing", missing), ("size differs", wrong),
                             ("no manifest", no_manifest)):
            for key in items[:8]:
                print(f"       {label}: {key}")
            if len(items) > 8:
                print(f"       ... {len(items) - 8} more {label}")
    print("R2 COMPLETE: PASS" if not bad else f"R2 COMPLETE: FAIL ({bad} datasets)")
    return int(bool(bad))


if __name__ == "__main__":
    raise SystemExit(main())
