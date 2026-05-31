# Access Check — PASS

**Generated:** 2026-05-31T16:22:01Z
**Script:** `00b_access_check.py`
**Elapsed:** 282.3s (4.7 min)
**Overall status:** PASS

## 1. File Existence

| # | Label | Status | Path |
|---|-------|--------|------|
| 1 | ECG record_list | ✅ EXISTS | `data\raw\record_list.csv` |
| 2 | ECG machine_measurements | ✅ EXISTS | `data\raw\machine_measurements.csv` |
| 3 | ECG waveform_note_links | ✅ EXISTS | `data\raw\waveform_note_links.csv` |
| 4 | ECG machine_measurements_data_dictionary | ✅ EXISTS | `data\raw\machine_measurements_data_dictionary.csv` |
| 5 | ECG waveform directory | ✅ EXISTS | `data\raw\files` |
| 6 | Hosp admissions | ✅ EXISTS | `data\raw\mimic-iv-hosp-3.1\hosp\admissions.csv.gz` |
| 7 | Hosp patients | ✅ EXISTS | `data\raw\mimic-iv-hosp-3.1\hosp\patients.csv.gz` |
| 8 | Hosp diagnoses_icd | ✅ EXISTS | `data\raw\mimic-iv-hosp-3.1\hosp\diagnoses_icd.csv.gz` |
| 9 | Hosp d_icd_diagnoses | ✅ EXISTS | `data\raw\mimic-iv-hosp-3.1\hosp\d_icd_diagnoses.csv.gz` |
| 10 | Hosp labevents | ✅ EXISTS | `data\raw\mimic-iv-hosp-3.1\hosp\labevents.csv.gz` |
| 11 | Hosp d_labitems | ✅ EXISTS | `data\raw\mimic-iv-hosp-3.1\hosp\d_labitems.csv.gz` |
| 12 | Hosp prescriptions | ✅ EXISTS | `data\raw\mimic-iv-hosp-3.1\hosp\prescriptions.csv.gz` |
| 13 | Hosp emar | ✅ EXISTS | `data\raw\mimic-iv-hosp-3.1\hosp\emar.csv.gz` |
| 14 | Hosp transfers | ✅ EXISTS | `data\raw\mimic-iv-hosp-3.1\hosp\transfers.csv.gz` |
| 15 | Hosp services | ✅ EXISTS | `data\raw\mimic-iv-hosp-3.1\hosp\services.csv.gz` |
| 16 | ED edstays | ✅ EXISTS | `data\raw\mimic-iv-ed-2.2\ed\edstays.csv.gz` |
| 17 | ED diagnosis | ✅ EXISTS | `data\raw\mimic-iv-ed-2.2\ed\diagnosis.csv.gz` |
| 18 | ED triage | ✅ EXISTS | `data\raw\mimic-iv-ed-2.2\ed\triage.csv.gz` |
| 19 | ED vitalsign | ✅ EXISTS | `data\raw\mimic-iv-ed-2.2\ed\vitalsign.csv.gz` |
| 20 | ED medrecon | ✅ EXISTS | `data\raw\mimic-iv-ed-2.2\ed\medrecon.csv.gz` |
| 21 | ED pyxis | ✅ EXISTS | `data\raw\mimic-iv-ed-2.2\ed\pyxis.csv.gz` |
| 22 | Hosp SHA256SUMS | ✅ EXISTS | `data\raw\mimic-iv-hosp-3.1\SHA256SUMS.txt` |
| 23 | ED SHA256SUMS | ✅ EXISTS | `data\raw\mimic-iv-ed-2.2\SHA256SUMS.txt` |

## 2. SHA256 Verification

- Files verified: 16
- Files with mismatch: 0

| Dataset | File | Status | Detail |
|---------|------|--------|--------|
| Hosp | `hosp/admissions.csv.gz` | ✅ MATCH | a9584ed88e9ed664 |
| Hosp | `hosp/patients.csv.gz` | ✅ MATCH | 4c7507de7ecad8c5 |
| Hosp | `hosp/diagnoses_icd.csv.gz` | ✅ MATCH | 47665a41b2a3ad99 |
| Hosp | `hosp/d_icd_diagnoses.csv.gz` | ✅ MATCH | a81065bf45ccf74f |
| Hosp | `hosp/labevents.csv.gz` | ✅ MATCH | 2cd5e09b7e48c018 |
| Hosp | `hosp/d_labitems.csv.gz` | ✅ MATCH | b7afdda77b637a7a |
| Hosp | `hosp/prescriptions.csv.gz` | ✅ MATCH | 0d8481c7d5d7c9ec |
| Hosp | `hosp/emar.csv.gz` | ✅ MATCH | 1c147c152c8cc12d |
| Hosp | `hosp/transfers.csv.gz` | ✅ MATCH | 4ea296ddafb4fa51 |
| Hosp | `hosp/services.csv.gz` | ✅ MATCH | 31c82ebee94e0c04 |
| ED | `ed/edstays.csv.gz` | ✅ MATCH | 33b3f4f07a075d72 |
| ED | `ed/diagnosis.csv.gz` | ✅ MATCH | eaf78b530886dc79 |
| ED | `ed/triage.csv.gz` | ✅ MATCH | fde3d5910215454f |
| ED | `ed/vitalsign.csv.gz` | ✅ MATCH | 2c1c46cf2db88e31 |
| ED | `ed/medrecon.csv.gz` | ✅ MATCH | 0cce438c28ba4f7a |
| ED | `ed/pyxis.csv.gz` | ✅ MATCH | 87f7a561074c7875 |

## 3. Row Counts

| Label | Rows | Expected Range | Status |
|-------|------|----------------|--------|
| ECG record_list | 800,035 | 790,000 – 810,000 | ✅ IN_RANGE |
| ECG machine_measurements | 800,035 | 790,000 – 810,000 | ✅ IN_RANGE |
| ECG waveform_note_links | 609,272 | > 0 | ✅ NONZERO |
| Hosp admissions | 546,028 | 500,000 – 600,000 | ✅ IN_RANGE |
| Hosp patients | 364,627 | 350,000 – 400,000 | ✅ IN_RANGE |
| Hosp diagnoses_icd | 6,364,488 | 6,000,000 – 7,000,000 | ✅ IN_RANGE |
| Hosp d_icd_diagnoses | 112,107 | 100,000 – 130,000 | ✅ IN_RANGE |
| Hosp labevents | 158,374,764 | 150,000,000 – 170,000,000 | ✅ IN_RANGE |
| Hosp d_labitems | 1,650 | 1,500 – 2,000 | ✅ IN_RANGE |
| Hosp prescriptions | 20,292,611 | >= 1,000,000 | ✅ IN_RANGE |
| Hosp emar | 42,808,593 | >= 1,000,000 | ✅ IN_RANGE |
| Hosp transfers | 2,413,581 | >= 500,000 | ✅ IN_RANGE |
| Hosp services | 593,071 | >= 500,000 | ✅ IN_RANGE |
| ED edstays | 425,087 | 400,000 – 450,000 | ✅ IN_RANGE |
| ED diagnosis | 899,050 | 850,000 – 950,000 | ✅ IN_RANGE |
| ED triage | 425,087 | 400,000 – 450,000 | ✅ IN_RANGE |
| ED vitalsign | 1,564,610 | >= 500,000 | ✅ IN_RANGE |
| ED medrecon | 2,987,342 | >= 1,000,000 | ✅ IN_RANGE |
| ED pyxis | 1,586,053 | >= 500,000 | ✅ IN_RANGE |

## 4. Cross-Source Subject Overlap (ECG ↔ Hosp)

**Status:** PASS
**Detail:** ECG subjects: 161,352, Hosp subjects: 223,452, overlap: 130,621 (81.0% of ECG, 58.5% of Hosp)

This check verifies per §5.3 that at least *some* MIMIC-IV-ECG
subjects appear in MIMIC-IV Hosp, preventing silent version mismatch.

---

## Verdict: PASS

All checks passed. Raw data is ready for pipeline processing.
