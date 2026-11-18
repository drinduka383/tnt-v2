# TESS baseline on newer NASA catalog entries

On 2026-11-17 we retrieved the NASA Exoplanet Archive `toi` table through TAP with `query=select * from toi` and `format=csv`. The response contained 8,175 rows. The local snapshot is `backend/data/validation/nasa-toi.csv` and its SHA-256 is `c8e6455e6694af2f8e38a969dbaa56f93ba97f5d5976606ce4c4e780dff62002`. The service returns a mutable table, so a future download may give different results. [NASA TAP guide](https://exoplanetarchive.ipac.caltech.edu/docs/TAP/usingTAP.html) ? [TOI field definitions](https://exoplanetarchive.ipac.caltech.edu/docs/API_TOI_columns.html)

## Provenance

Both bundled CSVs match the upstream reference copies and their baseline manifests byte for byte by SHA-256. The original Git history first records them in `ea7a969ee1c5781b372450527a38a5d182c02f1c` on 2025-10-05. The latest TOI training row update is 2025-09-28. All 2,464 bundled TESS candidates joined to the downloaded catalog by both TOI and TIC. This ties the identifiers to the archive, while the original export date and full preprocessing history remain unknown. The downloaded table omits `st_loggerr2` for 580 of those matched rows. For the 1,884 rows with that field present in both snapshots, its values agree. The comparison cannot establish why the values are absent in the newer snapshot.

## Protocol and result

The evaluator freezes the shipped model and threshold, selects candidates created on or after 2025-10-06 UTC, and excludes every TOI and TIC present anywhere in the bundled data. It accepts the baseline's CP/KP versus FP labels and uses the same adapter and input validation as the app. No evaluation records were used to refit or select the model. Run from the checkout root:

```powershell
backend/.venv/Scripts/python.exe backend/evaluate_toi.py backend/data/validation/nasa-toi.csv
```

| Cohort or metric | Result |
|---|---:|
| Newer entries | 472 |
| Newer entries from unseen TIC hosts | 460 |
| Entries with eligible dispositions | 37 |
| Entries with eligible dispositions and usable inputs | 18 across 15 hosts |
| True positives / false negatives | 9 / 2 |
| True negatives / false positives | 7 / 0 |
| ROC AUC | 0.961 |
| Average precision | 0.981 |
| Balanced accuracy at the shipped threshold | 0.909 |

The main finding is coverage. The model scored 18 of 37 labeled rows (49%). Of the 19 labeled rows it could not score, 15 lacked the lower surface-gravity uncertainty `st_loggerr2`. Of the 18 scoreable rows, seven were already-known planets, four were confirmed planets, and seven were false positives. Current measurements may incorporate follow-up performed after the initial discovery. This date-separated catalog replay therefore measures performance on a small, selected and retrospectively labeled subset. Raw light-curve detection and performance at the time of candidate discovery remain untested.

Retain the baseline as an optional catalog scorer. A useful next model experiment would compare feature coverage and accuracy on an explicitly fixed cohort using inputs available at first observation. This inspected cohort should be treated as development evidence if it guides feature selection. Reserve a fresh later cohort before making promotion decisions. Kepler was included in the lineage check but was outside the scope of this temporal evaluation.


## Reduced-input experiment

The challenger uses three published transit measurements: orbital period, transit duration and transit depth. It uses the same labeled historical rows, host split, XGBoost settings and 0.5 decision threshold as the shipped model. Early stopping used the historical validation partition. The newer NASA snapshot was used only for comparison. It was already inspected before the experiment and serves as development evidence. The three measurements are plausible early inputs, but the snapshot does not establish that these values were available at first detection.

| Comparison | Shipped model | Three-input challenger |
|---|---:|---:|
| Labeled newer entries scored | 18 / 37 | 35 / 37 |
| Historical test ROC AUC, same 365 rows | 0.932 | 0.810 |
| Historical test balanced accuracy, same 365 rows | 84.7% | 73.5% |
| Newer balanced accuracy, same 18 rows | 90.9% | 64.9% |
| Newer balanced accuracy, challenger-only 17 rows | ? | 51.7% |

The 17 additional rows contained 15 positives and two negatives. The challenger correctly classified eight positives and one negative. Balanced accuracy averages the two class recalls, which is why that result matters more than raw coverage alone. On the historical test it produced 74 false positives versus 33 for the shipped model, with 23 false negatives each. Keep the three-input artifact offline. Displaying more scores would trade away too much discrimination in this experiment.

Reproduce from the checkout root using a new output directory:

```powershell
backend/.venv/Scripts/python.exe backend/experiment_toi.py backend/data/validation/nasa-toi.csv backend/data/validation/toi-three-feature-replay
```

The first experiment is under `backend/data/validation/toi-three-feature/`. The model hash is `14cae2a2733da7e9aba90dd2a7231af7bf495ec5ff988169beeb24b3059abf93`. The report records feature names, input hashes, the selected tree iteration and confusion matrices. The saved artifact was reloaded and reproduced its scores on the development cohort.

For the next promotion evaluation, freeze the feature list, artifact and threshold before reading the cohort's outcomes. Reserve entries first reported after the 2026-11-17 UTC snapshot day and exclude every TIC and TOI present in that snapshot or the bundled training data. Preserve the first-seen feature snapshot and join later vetted dispositions by TOI and TIC. Report abstentions, paired errors on the common subset, and errors on the extra covered subset. Keep CP and KP counts visible and compare the CP-versus-FP subset separately. If mature labels are too sparse for both classes, keep collecting rather than selecting a cutoff from observed errors. This evaluation requires future observations and follow-up labels.
