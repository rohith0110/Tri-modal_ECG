STATUS: PASS

# Linkage audit
- Decision path: plan_a
- candidate_links rows: 602,314
- linkage_final rows: 785,761
- label_availability rows: 800,035
- linkage tier distribution: {'L3': 468176, 'L1': 237934, 'L2': 79651}
- label_availability tier distribution: {'L3': 468176, 'L1': 237934, 'L2': 79651, 'L0': 14274}
- duplicate final study_ids: 0
- duplicate label_availability study_ids: 0
- L2/L3 final rows missing candidate provenance: 0
- Tie-breaking validation mismatches: 0
- Tie-breaking rule checked: smallest abs_tie_minutes, exact before tolerance, then lowest hadm_id/stay_id.
