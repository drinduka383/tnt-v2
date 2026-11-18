# Acceptance evidence - 2026-11-15

All work is local to tnt-v2. No source repository pushes or remote repository creation occurred. The two pinned reference checkouts have clean git status.

## Automated checks

- Python unittest discovery: scientific feature guard, raw/engineered feature parity, host-isolated partitions, actual native baseline inference, offline artifact publication, identity resolution, all-candidate handling, request validation, idempotency conflicts, cancellation racing completion, interrupted-run recovery, upload isolation and target mismatch.
- Node tests: score bounds and allowed run states.
- ESLint and Vite production build.
- Headless Chromium: request submission, cancel-and-return, scored and unscored candidate rendering, saved URL reload, mobile form layout, optional atlas failure. API responses are deterministic in this test.

Final results: 19 Python tests passed; two Node tests passed; ESLint passed; Vite build passed; headless Chromium acceptance passed. Python source compilation also passed. The environment used a local .venv with access to existing scientific packages and locally installed XGBoost/Waitress. A clean full dependency installation and Docker build were not performed.

## Live checks

Browser -> Vite on port 5188 -> /api proxy -> Flask/Waitress -> SQLite worker -> live NASA archive -> native model -> browser result succeeded for Kepler KIC 11446443. The saved run URL was reloaded successfully:

http://127.0.0.1:5188/start?run=a067802af15d47bd90e1ee15e69b52f9

That run is local ignored state, not a portable fixture. Subsequent requests use the final model metadata fingerprints; saved runs retain the metadata captured when submitted.

A live catalog check for TIC 150428135 returned four candidates (700.01 through 700.04), all with insufficient evidence. This is an accepted outcome: no zero substitution or invented scores.

The upstream TESS file tess2024249191853-s0083-0000000139298196-0280-s_lc.fits (TIC 139298196, sector 83) was replayed through real FITS loading, BLS search and two plots. The initial exploratory period was approximately 4.52 days. That is an execution check, not independent confirmation of a transit or planet. The bounded final search is also covered by a seeded synthetic-transit regression.

## Limits

Actual touch hardware remains unverified. Live sky imagery is now verified by the follow-up acceptance below. Aladin's separate lazy-loaded bundle still emits a Vite size warning. Independent scientific validation, calibration, out-of-distribution detection and public hosting are outside this local implementation's proof. Cancellation prevents further stages/publication but does not forcibly terminate a native operation already executing.

## Live sky-map repair and acceptance

The original P/DSS2/color default resolved to a CDS properties endpoint returning 404. The viewer constructor still succeeded, so the UI incorrectly hid its loading state while imagery remained blank. A separate optional telemetry endpoint also failed DNS; startup telemetry is now disabled.

The map now selects from two independently hosted mirrors of the same registered DSS2 survey: NASA/IPAC IRSA and MAST on S3. A provider must return valid HiPS properties and a decodable Allsky image before selection. Ready is sent from the actual layer attachment callback. Failed initialization remains visible, and Retry creates a fresh viewer document.

Five Node regressions, ESLint and the production build passed. The opt-in live check `python frontend/tests/map_live.py` passed all three scenarios:

- Real HTTP 200 imagery tiles, nonuniform rendered image pixels, pan and zoom.
- Blocking NASA/IPAC causes successful MAST fallback.
- Blocking both providers shows Retry; restoring them and retrying recovers imagery.

The test ran in separate Chromium because the shared preview status and snapshot calls timed out after 15 seconds, and its pending open eventually reported a disconnected automation client. The original failure was observed in the shared preview; the repaired imagery was visually inspected from the separate browser capture.

Backend /health, /models and a live /search against MAST all returned HTTP 200 in this follow-up. The small search cone returned zero matches as a successful empty result. This is a point-in-time availability check, not a claim that all external services or every upload/download path were exhaustively retested.

## Map picker acceptance

The map now shows selectable TIC objects, limits the list to projected on-screen coordinates, checks observation availability for the selected host, and fills the analysis form. UI tests use the real Aladin canvas with deterministic target/API data. Real marker clicks, out-of-order availability responses, moved-view invalidation and selected-host submission all passed. The existing browser smoke test also passed.

Live MAST region requests returned bounded, labelled catalog results. A visible target, TIC 67882510, returned five supported public TESS light-curve products through the final exact-ID query. A selected product from TESS-SPOC sector 84 was downloaded, and its FITS primary header confirmed TICID 67882510 with LIGHTCURVE and APERTURE extensions. A separate live check confirmed exact TIC 150428135 and Kepler bundle metadata queries. The external Kepler product-list request timed out; bundle expansion is covered by a deterministic regression, not claimed as a successful live Kepler download.

Final automated checks for this change: 27 Python tests, seven Node tests, ESLint, Vite production build and Python compilation passed. New tests cover region bounds, capped catalog results, missing values, availability failures versus absence, exact padded IDs, product-list expansion, atomic acquisition and cleanup after interrupted downloads. The opt-in UI test is frontend/tests/map_selection.py.

Shared preview status and snapshot calls again timed out after 15 seconds, so browser verification used separate Chromium. Physical phone interaction was not tested. Upstream reference repositories remain unchanged; no pushes occurred.

The final selected-target run aadfa20fe7894e11bae71b5f1ade49c0 completed through the real backend for TIC 67882510 with terminal insufficient_evidence and two generated light-curve plots. This confirms map-target acquisition and processing execute without manufacturing a model score. The saved result is local ignored runtime state.

## Data-bridge and evidence-workspace repair

User-reported failures were reproduced using the saved failed run fc14024bbd864ef8835c6da8f1ac6a7f for TIC 191179668. The old run failed at acquisition after about 25 seconds with an archive lookup error. Independent probes confirmed the TIC catalog was responding while the observation-index queries intermittently timed out. These were real source failures, not a missing frontend binding.

Two deterministic regressions also failed before the repair: an observation run was blocked by a candidate-catalog outage even for a canonical TIC ID, and short observations were discarded before any photometry plot was returned. Both now pass. The pipeline no longer requires the NASA candidate catalog or an independent stellar lookup to read a canonical host's FITS observation. Stellar fields available in that FITS header are retained; missing fields stay unknown.

Successful observation listings are reused between availability and acquisition for ten minutes (one minute for successful empty listings), with at most 128 in-memory entries. Failures are not cached. Transient transport failures receive one retry. Full photometry is exported atomically as CSV before optional transit fitting. Short, flat or out-of-range observations can still provide their actual measurements and a time-series plot; their search limitation is explicit. Optional model failures cannot discard acquired evidence.

The exact failed target was rerun successfully as 9e129c849c3d424381ce437ef5e1d8db. It returned 10,007 valid samples covering approximately 25.69 days, two plots, and original FITS / photometry CSV / evidence-record downloads. The CSV endpoint returned HTTP 200 with exactly 10,007 data rows. Model status remained unscored, as expected without calibrated transit uncertainties; run status is succeeded because evidence was delivered.

The workbench now uses a compact sidebar and separate Map/Evidence views. Returned measurements and plots are shown first; model diagnostics and raw provenance are secondary. Recent runs reopen local saved results. A failed source request retains the captured target and can be retried. Reopening a saved evidence result does not initialize the sky SDK until the map is requested.

Actual saved data was inspected in desktop Chromium and at a 390px mobile viewport. Browser assertions cover visible plots despite an unscored model, actual CSV download behavior, mobile overflow, retrying the same target, and rejecting mismatched run IDs. Updated map-selection and general browser smoke checks pass. The shared preview still timed out on status and snapshot; separate Chromium was used. Physical phone behavior remains untested.

Final checks: 34 Python tests, seven Node tests, ESLint, production build and Python compilation passed. Evidence UI and general browser smoke tests passed. After restarting the backend, health and saved-run endpoints returned HTTP 200; the saved result retained both plots and its 10,007-row CSV. No upstream changes were pushed. External archive availability remains outside this app's control; cached listings and saved evidence reduce repeated dependencies rather than inventing substitute data.

## Project/model review 2026-11-17

Baseline artifacts passed real inference over all 2,464 eligible TOI and 7,923 eligible KOI rows through check_models.py. Both families were fully retrained with the default 200-round ceiling and early stopping into new local artifacts: toi-cedf44693b6543f0b5c8d0ca2538789f and koi-ae3fb99daa4646f7966f222d8b481d31. Both new artifacts resolved through ModelService and passed all-row inference. Their native model hashes matched their respective shipped baselines, reproducing the fitted artifacts in this environment. Manifests additionally capture data eligibility, configuration and actual library versions; JSON rejects non-finite metadata.

The trainer now accepts an explicit dataset, output root and round ceiling. Its regression checks explicit input selection, complete publication, recorded configuration/versions/counts and subsequent inference. All 34 backend tests and seven Node tests passed; ESLint and production build passed. Legacy prototypes and conflicting dependency lists were preserved under legacy rather than kept in the active application tree. Root documentation now identifies supported paths and distinguishes catalog retraining from observation classification. No baseline or saved evidence was replaced; no upstream pushes occurred.

## Combined analysis flow

The live combined run cce039b32d9e4d229d4129bbb044153f for TIC 50365310 returned both source states ready. It scored published TOI 1000.01 with the native baseline and returned 16,900 photometry samples. Chromium verified the score and plot on a 390px viewport, and the downloaded CSV contained 16,900 data rows. The saved run was rechecked after the service restart.

The API regression exercises both sources ready, one source missing, one upstream failure with preserved photometry, no usable data, and no usable data with a failed source. Complete published rows used the real model while an incomplete row identified its missing field. Browser checks cover direct marker selection, stale region rejection, cancellation, reopening saved results, and an uncertain submission retry that reuses the original idempotency key.

## TESS pixel fallback and published candidate checks

A verified empty prepared TESS product search now advances to TIC position lookup, TESScut footprint lookup, one 7 ? 7 cutout, and WCS-verified aperture extraction. Empty coverage and archive failures remain distinct. Aperture flux uses quality-zero cadences, a 3 ? 3 aperture and a border median background. The original cutout, extracted CSV and provenance are available through existing artifact routes.

Live combined run `3a03b4319503445ea9faadc074b7e4a9` for TIC 142870233 recovered 9,870 samples from sector 108 without a published candidate. Live combined run `3a0e12d1dc55482fa9be9612e9547650` for TIC 50365310 returned the ExoFOP follow-up note for TOI 1000.01 and measured approximately 720 ppm over twelve events at the published times in sector 34. The timing check measures flux in the aperture. Source localization still requires separate pixel vetting.

Backend regressions cover the empty-index fallback, aperture/background result, fixed-ephemeris event windows and the exact TIC-plus-TOI join for follow-up notes. All 38 backend tests and seven Node tests passed.
