# Project review and supported workflow

Verified locally on 2026-11-17. This review describes the current v2 code, not the original repositories.

## What the project actually does

The useful product is a local evidence workbench: select a stellar host, acquire a public observation or published candidate record, inspect its measurements and provenance, and optionally classify a compatible catalog feature vector. The map discovers hosts; it is not a detector. A successful light-curve download is not necessarily a model-eligible candidate. A model score is not a planet confirmation.

The core chain is identity -> acquired evidence -> extracted measurements -> optional model eligibility -> score. Persisted runs capture target, evidence mode and model identity. Cancellation, archive failure, insufficient features and successful evidence are separate outcomes. Avoid adding a second state model to work around these distinctions.

## Can the model run?

Yes. There are two native binary XGBoost models, checked against schema, units and artifact checksums before inference. TOI takes 23 features; KOI takes 14. The offline checker loaded both baselines and produced valid bounded scores for all 2,464 eligible bundled TOI rows and 7,923 eligible KOI rows. The KOI snapshot has 9,564 source rows; 1,641 are excluded by label/feature/physical validity requirements. TOI has no exclusions in this bundled snapshot. These are execution checks, not new accuracy measurements.

From the repository root:

```powershell
backend/.venv/Scripts/python.exe backend/check_models.py
```

For the UI, choose Published catalog and the corresponding mission. Balanced selects the shipped baseline. Enter a custom artifact identifier under Model options to use a separately trained model. Live catalog service availability and complete features remain prerequisites. For observations/uploads, retain the data even when the classifier cannot run: its input needs catalog transit parameters and calibrated uncertainties that the exploratory BLS search does not measure.

## Can it be trained further?

Yes, by offline retraining on a labeled mission catalog. The supported trainer builds a fresh classifier; it does not resume trees, learn from clicks or automatically absorb downloaded FITS files. Both families were retrained at the full default 200-round ceiling with validation early stopping, and their newly published artifacts were checked through the inference service. The shipped baselines were not replaced.

```powershell
backend/.venv/Scripts/python.exe backend/train.py TOI
backend/.venv/Scripts/python.exe backend/train.py KOI
backend/.venv/Scripts/python.exe backend/train.py TOI --dataset updated-toi.csv --rounds 200
backend/.venv/Scripts/python.exe backend/check_models.py --family TOI --model MODEL_ID_PRINTED_BY_TRAINING
```

An updated CSV needs the same raw mission catalog columns, host identifier and disposition labels. The shared adapter recomputes engineered features rather than trusting supplied engineered columns. Missing/invalid measurements are excluded, not imputed to zero. Host-disjoint train/validation/test partitions prevent candidates belonging to one host from crossing those partitions. Both classes must exist in every partition. Output is a new complete directory under backend/training-output; --output can select another root for offline experiments, but the app only discovers its configured training-output root.

New manifests record source checksum, row eligibility, effective configuration, package/Python versions, label definitions, split procedure, early-stop iteration and validation/test metrics. A different dataset is a different experiment. Repeatedly selecting models against the same test set invalidates its interpretation as a final held-out test.

## What the scores mean and what remains unproved

TOI positive labels are CP/KP; FP is negative. KOI positive labels include both CONFIRMED and CANDIDATE; FALSE POSITIVE is negative. The families therefore do not answer exactly the same scientific question. Scores are uncalibrated classifier outputs, not a probability that a planet exists.

Bundled baseline manifests report test accuracy around 85 percent and ROC AUC around 0.93. Those are local host-isolated snapshot evaluations, not independent scientific validation, prospective discovery performance or a guarantee on current live catalogs. Dataset acquisition dates and original preprocessing lineage are not fully established by the bundled files. Uncertainty and follow-up completeness features can encode catalog curation, so host isolation alone does not prove absence of scientific leakage. The active environment also contains NumPy/pandas patch versions different from requirements.txt; new manifests expose the actual versions instead of implying exact environment reproducibility.

## Streamlining decisions

One active backend, one shared feature adapter, one trainer, one dependency manifest, one model registry, one persisted run lifecycle and one evidence-first workbench. Legacy processing docs/examples, duplicate dependency lists and unused filter/hyperparameter components have been moved under legacy, preserving their contents without presenting them as supported paths. Home/team text has been corrected where it implied that selecting a star establishes planet presence. Existing evidence and upstream clones are preserved.

Keep raw-observation exploration and catalog classification as explicit workflows. Do not spend more effort forcing the current classifier onto arbitrary light curves by fabricating missing inputs. If direct observation classification becomes the goal, that is a separate research model: define labeled observation-level examples, account for sectors and host grouping, fit uncertainty-bearing transit parameters or train directly on vetted sequences, and validate against independent later observations. Start by establishing dataset lineage and a fixed external evaluation protocol before increasing model size or adding online training.

## Day-one breaking test

Select a valid TIC with public photometry, make candidate metadata unavailable, and withhold every calibrated transit uncertainty. Require an inspectable, downloadable observation, explicit unscored status and no invented confidence. Then reopen the saved run with archives offline. A design that treats this as a total failure has coupled evidence acquisition to a classifier it cannot reliably feed. Existing evidence-flow regressions cover the acquisition/optional-scoring separation; this is not a claim that every archive outage combination has been live-tested.

## Verification limits

Model loading, all-row baseline inference, full retraining of both families, and inference through the newly trained artifacts were exercised locally. Automated backend/frontend checks are recorded in VERIFICATION.md. No new independent astronomical validation, fresh labeled dataset collection, container build or physical phone test was performed. No upstream changes were pushed.
