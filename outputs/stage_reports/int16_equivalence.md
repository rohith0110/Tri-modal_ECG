# int16 storage equivalence (Stage P2.5, spec §8.2)

Generated 2026-08-28T17:10:44Z by `scripts/dgx_portability/prove_int16_equivalence.py`.

§8.2 stages signals as **int16 with a per-record scale factor** instead of float32. This is the empirical check that the change is a storage change and not a precision compromise.

## Design

The same task, four runs:

| arm | storage | seed | purpose |
| --- | --- | ---: | --- |
| `A_float32` | float32 | 42 | float32, the original storage |
| `B_float32_repeat` | float32 | 42 | float32 again, identical settings -- proves determinism |
| `C_int16` | int16 + scale | 42 | int16 + per-record scale, the shrunk copy |
| `D_float32_seed123` | float32 | 123 | float32, a different seed -- the yardstick |

**B and D answer different questions, and both are needed.** B repeats A exactly and establishes that training here is deterministic, so any difference arm C shows belongs to the encoding and not to cuDNN autotuning or non-deterministic reductions. D changes only the seed, and measures how far the metric moves under variation the paper already accepts and reports as +/- std over three seeds. **D is the yardstick**: B's floor is exactly zero, and no perturbation of any kind can meet a zero bar, so zero is not a criterion anything could pass.

The deciding question is therefore: **is the float32-vs-int16 metric difference small next to the seed-to-seed difference already treated as noise?**

Task `A2_measurement_blind`, config `A2_signal_resnet18_lead2_preprocessed.yaml`, 10,000 training rows, 2 epochs, batch 32.

## Row-by-row divergence -- a DIAGNOSTIC, not the criterion

These are separately trained models, so they are expected to disagree row by row: a 1.5e-05 relative change in the inputs perturbs the SGD trajectory and the runs settle at different points in weight space, after which rows near a decision boundary can swing hard. Read the numbers against each other, not against zero -- **the seed change (D) moves individual predictions about twice as far as the quantisation (C) does**, which is the same story the metrics tell.

| comparison | rows | heads | bit-identical heads | max abs delta | rms delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| B vs A (identical repeat -- determinism check) | 10,000 | 9 | 9/9 | 0.000e+00 | 0.000e+00 |
| C vs A (int16 vs float32) | 10,000 | 9 | 0/9 | 4.409e-01 | 2.062e-02 |
| D vs A (different seed -- the yardstick) | 10,000 | 9 | 0/9 | 8.930e-01 | 5.358e-02 |

## Test metrics -- the criterion

Scored with `_train_lib.metrics`, the same code `31_eval.py` uses.

| metric | `A_float32` | `B_float32_repeat` | `C_int16` | `D_float32_seed123` | int16 effect | seed effect |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| hr_label accuracy | 0.971600 | 0.971600 | 0.971700 | 0.971500 | 1.00e-04 | 1.00e-04 |
| hr_label macro_AUPRC | 0.989100 | 0.989100 | 0.989153 | 0.988646 | 5.30e-05 | 4.55e-04 |
| qrs_label accuracy | 0.817800 | 0.817800 | 0.817500 | 0.820600 | 3.00e-04 | 2.80e-03 |
| qrs_label macro_AUPRC | 0.794567 | 0.794567 | 0.795073 | 0.800379 | 5.05e-04 | 5.81e-03 |
| qtc_label accuracy | 0.812300 | 0.812300 | 0.815200 | 0.819200 | 2.90e-03 | 6.90e-03 |
| qtc_label macro_AUPRC | 0.595920 | 0.595920 | 0.597063 | 0.599331 | 1.14e-03 | 3.41e-03 |
| **max** |  |  |  |  | **2.90e-03** | **6.90e-03** |

## Verdict

**EQUIVALENT.** The largest int16-vs-float32 metric difference is 2.90e-03, against a seed-to-seed difference of 6.90e-03 on the same metrics -- 0.42x. Changing the storage format moves the reported numbers LESS than changing the random seed does, and seed variation is already reported as +/- std in every results table. The int16 copies are safe to upload and to train on.

Arm B is bit-identical to arm A on every head, so training on this machine is deterministic and the whole of arm C's difference is attributable to the encoding -- there is no non-determinism confound to argue about.

## Storage actually saved

From `data/processed/signals_int16/int16_manifest.json`:

| file | float32 | int16 | ratio | max quantisation error |
| --- | ---: | ---: | ---: | ---: |
| `lead2_preprocessed.h5` | 12.73 GB | 7.42 GB | 58.3 % | 2.934e-02 |
| `twelve_lead_preprocessed_shard_00.h5` | 30.55 GB | 16.70 GB | 54.6 % | 3.090e-02 |
| `twelve_lead_preprocessed_shard_01.h5` | 30.47 GB | 16.66 GB | 54.7 % | 4.667e-03 |
| `twelve_lead_preprocessed_shard_02.h5` | 30.56 GB | 16.70 GB | 54.7 % | 2.758e-03 |
| `twelve_lead_preprocessed_shard_03.h5` | 30.37 GB | 16.61 GB | 54.7 % | 3.336e-02 |
| `twelve_lead_preprocessed_shard_04.h5` | 30.30 GB | 16.57 GB | 54.7 % | 3.199e-02 |
| **total** | **164.98 GB** | **90.66 GB** | **55.0 %** | |

The error column is the exact quantisation error, measured in float64 against the stored float32 scale; it is bounded by half a quantisation step by construction and measured at 1.000000 of one.
