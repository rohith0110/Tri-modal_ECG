# threshold_audit.md — Phase 2 threshold selection

Every classification threshold used anywhere in Phase 2, with the validation
Youden's J that chose it (spec §6.5). `selected_on_split` is `val` on every row
by construction — `_train_lib/threshold.py` refuses to select on any other split
and refuses to apply a threshold that was not selected on `val`.

> **PROVENANCE — READ BEFORE CITING. Every row currently in this file comes
> from Stage P2.5's int16 equivalence proof (2026-08-28), NOT from a paper
> run.** Those arms trained `A2_measurement_blind` on a deliberately reduced
> slice (`--limit-rows 10000`, 2 epochs) purely to compare float32 against
> int16 storage, so the thresholds below are real, correctly val-selected, and
> **not the numbers any results table should quote**. The campaign runs will
> append their own rows; when they do, delete this banner and treat rows dated
> before the first campaign as superseded. Ignoring this would put a
> 10,000-row smoke threshold into the paper.

| task | arch_tier | lead_subset | seed | head | class | threshold | val Youden J | sens | spec | n_val | n_pos_val | selected_on_split |
| --- | --- | --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| A2_measurement_blind | signal_resnet18_lead2_preprocessed | lead2 | 42 | hr_label | bradycardia | 0.122757 | 0.971646 | 0.9890 | 0.9827 | 10000 | 815 | val |
| A2_measurement_blind | signal_resnet18_lead2_preprocessed | lead2 | 42 | hr_label | normal | 0.588455 | 0.951950 | 0.9752 | 0.9768 | 10000 | 6682 | val |
| A2_measurement_blind | signal_resnet18_lead2_preprocessed | lead2 | 42 | hr_label | tachycardia | 0.331304 | 0.965480 | 0.9828 | 0.9827 | 10000 | 2503 | val |
| A2_measurement_blind | signal_resnet18_lead2_preprocessed | lead2 | 42 | qrs_label | normal | 0.675926 | 0.693609 | 0.8813 | 0.8123 | 10000 | 6521 | val |
| A2_measurement_blind | signal_resnet18_lead2_preprocessed | lead2 | 42 | qrs_label | borderline | 0.155400 | 0.535687 | 0.8269 | 0.7088 | 10000 | 1929 | val |
| A2_measurement_blind | signal_resnet18_lead2_preprocessed | lead2 | 42 | qrs_label | wide | 0.230866 | 0.837660 | 0.9103 | 0.9273 | 10000 | 1550 | val |
| A2_measurement_blind | signal_resnet18_lead2_preprocessed | lead2 | 42 | qtc_label | short | 0.000384 | 0.348674 | 0.6000 | 0.7487 | 10000 | 5 | val |
| A2_measurement_blind | signal_resnet18_lead2_preprocessed | lead2 | 42 | qtc_label | normal | 0.512733 | 0.637335 | 0.7842 | 0.8531 | 10000 | 5126 | val |
| A2_measurement_blind | signal_resnet18_lead2_preprocessed | lead2 | 42 | qtc_label | prolonged | 0.486346 | 0.637210 | 0.8532 | 0.7841 | 10000 | 4869 | val |
| A2_measurement_blind | signal_resnet18_lead2_preprocessed | lead2 | 123 | hr_label | bradycardia | 0.037465 | 0.968883 | 0.9963 | 0.9726 | 10000 | 815 | val |
| A2_measurement_blind | signal_resnet18_lead2_preprocessed | lead2 | 123 | hr_label | normal | 0.640912 | 0.947885 | 0.9747 | 0.9732 | 10000 | 6682 | val |
| A2_measurement_blind | signal_resnet18_lead2_preprocessed | lead2 | 123 | hr_label | tachycardia | 0.189721 | 0.964538 | 0.9884 | 0.9761 | 10000 | 2503 | val |
| A2_measurement_blind | signal_resnet18_lead2_preprocessed | lead2 | 123 | qrs_label | normal | 0.658836 | 0.693000 | 0.8945 | 0.7985 | 10000 | 6521 | val |
| A2_measurement_blind | signal_resnet18_lead2_preprocessed | lead2 | 123 | qrs_label | borderline | 0.175682 | 0.533179 | 0.7698 | 0.7634 | 10000 | 1929 | val |
| A2_measurement_blind | signal_resnet18_lead2_preprocessed | lead2 | 123 | qrs_label | wide | 0.208287 | 0.844329 | 0.9123 | 0.9321 | 10000 | 1550 | val |
| A2_measurement_blind | signal_resnet18_lead2_preprocessed | lead2 | 123 | qtc_label | short | 0.000006 | 0.238519 | 1.0000 | 0.2385 | 10000 | 5 | val |
| A2_measurement_blind | signal_resnet18_lead2_preprocessed | lead2 | 123 | qtc_label | normal | 0.556352 | 0.641264 | 0.7718 | 0.8695 | 10000 | 5126 | val |
| A2_measurement_blind | signal_resnet18_lead2_preprocessed | lead2 | 123 | qtc_label | prolonged | 0.501556 | 0.641065 | 0.8332 | 0.8078 | 10000 | 4869 | val |
