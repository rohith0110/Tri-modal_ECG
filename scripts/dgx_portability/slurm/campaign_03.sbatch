#!/usr/bin/env bash
#SBATCH --job-name=trimodal_c3_images_lead2
#SBATCH --gres=gpu:a100:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=28:00:00
#SBATCH --requeue
#SBATCH --signal=B:TERM@300
#SBATCH --output=trimodal_c3_%j.out
#SBATCH --error=trimodal_c3_%j.err
#
# Campaign 3 -- images_lead2.
#   resident data ~21 GB | plan estimate ~14 GPU-hours | chunked: no
#   wall clock requested is 2x the estimate for queue and I/O, capped at 48 h.
#
# Environment surveyed 2026-08-30 (Step 7). What that changed:
#   * No --partition is set: `gpu_student` is confirmed (Step 7, 2026-08-30) but
#     it is a submit-time choice, and cpu_student exists for jobs that need no
#     GPU.  Pass it:  sbatch --partition=gpu_student campaign_03.sbatch
#   * --mem is MANDATORY here and is the reason a job silently never starts.
#     These partitions default to the whole node's memory (1,031,800 MB), so a
#     job without --mem waits for a completely empty node -- which never happens
#     on a shared box -- and Slurm reports it as "Nodes required for job are
#     DOWN, DRAINED or reserved", blaming the nodes rather than the request.
#     64G is a floor for 8 loader workers; raise it the same way as the others:
#         sbatch --partition=gpu_student --mem=128G campaign_03.sbatch
#   * --gres names the GPU TYPE on purpose. The A100s are MIG-partitioned into
#     a100, a100_4g.20gb, a100_3g.20gb, a100_2g.10gb and a100_1g.5gb, and an
#     untyped `--gres=gpu:1` matches ANY of them -- including a 5 GB slice, which
#     OOMs hours in. There are only 7 full a100s across dgxa+dgxb, shared with
#     faculty and scholars, so this is the contended resource. Override with:
#         sbatch --partition=gpu_student --gres=gpu:a100:2 campaign_03.sbatch
#   * --requeue with --signal=B:TERM@300 is what makes the §6.9/§8.1 resume
#     path real: the trainer gets 5 minutes' warning, writes checkpoint_last.pt
#     and exits 0, so Slurm requeues it and it continues mid-epoch.
#
# TRIMODAL_HOME defaults to ~/se23ucse027 -- the roll number, because the DGX
# account is shared and one named folder means nobody confuses whose files
# these are. Set it if the checkout lives elsewhere.

set -euo pipefail
export CAMPAIGN=3
export PROJECT_ROOT="${TRIMODAL_HOME:-$HOME/se23ucse027}"

. "$PROJECT_ROOT/scripts/dgx_portability/slurm/_campaign_body.sh"
