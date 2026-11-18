# A World Away - TNT v2

An independent local workbench for exploring TESS/Kepler transit evidence. It distinguishes published catalog measurements, exploratory light-curve signals and model scores. Neither a score nor a BLS peak confirms a planet.

Read [ARCHITECTURE.md](ARCHITECTURE.md) for the implemented design and state-machine inventory, [VERIFICATION.md](VERIFICATION.md) for acceptance evidence, and [SOURCES.md](SOURCES.md) for pinned upstream revisions. The original repositories were not changed or pushed to.

## Run locally

Use Python 3.13 and Node 22. Create an isolated Python environment from this checkout:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
cd backend
.venv/Scripts/python.exe main.py
```

In a second terminal, from the repository root:

```powershell
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5188
```

Open http://127.0.0.1:5188/start. Enter a target and choose **Analyze target**, or select a map marker and use **Analyze TIC** above the map. The default analysis looks up published candidates and a public light curve in one saved run. The model scores eligible catalog rows, and the result identifies missing or invalid inputs for unscored candidates. Single-source and uploaded FITS modes are under **Analysis options**. The Evidence view shows the observation first, with measured sample count, coverage, plots and downloads. A missing model score is not treated as a failed observation. The frontend proxies /api to localhost:5000. On Linux/macOS use backend/.venv/bin/python instead of Scripts/python.exe. Only one backend process may own a data directory. Runs and evidence persist in backend/data (ignored by Git); retain it across restarts to preserve saved URLs.

Try **TIC 50365310** for a verified example with both a light curve and a model-scored catalog candidate. For catalog-only Kepler, try KIC 11446443 with the balanced model. A real NASA catalog run for this host completed successfully during acceptance. Archive data may change. Many TESS candidates legitimately remain unscored because required measurements are missing. Uploaded FITS must embed the matching TICID or KEPLERID, contain a supported observation extension, and fit within the 32 MB request limit.

## Pick targets from the sky

Pan or zoom, then click **Search this view**. Cyan circles and the matching keyboard-accessible list identify TIC stars actually on screen. Click a circle or list entry, then use **Analyze TIC** beside **Search this view**. The selected ID also fills the form. The run checks observation availability while acquiring evidence. When the supported TESS light-curve index is empty, the app checks full-frame coverage and can extract exploratory aperture photometry from one TESScut sector. Combined TESS results also show public ExoFOP follow-up comments when available and check the published transit and half-period windows in your observation.

The search queries an enclosing cone no wider than 0.5 degrees in radius, up to 200 catalog matches, and TESS magnitudes -5 through 16. Zoom in when prompted or when the result is capped. Moving the view invalidates the old region search, and the selected target stays available for analysis until changed. A failed source is shown separately from a source with no results and can be retried.

Observation availability uses exact TIC target names and the public SPOC, TESS-SPOC and QLP index. It does not download files until analysis starts or guarantee that the measurements will be sufficient for a model score. Map picking currently covers TESS/TIC; Kepler remains available through the identifier form. Failed source requests offer **Retry this target**, and **Recent runs** reopens evidence already stored locally without re-querying the archive.

## Verify

From backend/: `.venv/Scripts/python.exe -m unittest discover -s tests`.

From frontend/: `npm test`, `npm run lint`, `npm run build`.

From the root, with Python Playwright and Chromium installed: `python frontend/tests/browser_smoke.py`. This headless acceptance script starts and stops its own Vite instance on port 5187. It uses deterministic API responses and tests optional atlas failure; it does not establish external sky survey availability or physical phone behavior.

For opt-in real survey checks with the app running on port 5188: `python frontend/tests/map_live.py`. It checks visible imagery, pan/zoom, provider fallback and recovery after an outage.

With the app running, `python frontend/tests/map_selection.py` checks actual Aladin marker selection against deterministic API responses, including late-response races and the submitted target identity. It requires access to a live sky survey.

The evidence-focused browser check is `python frontend/tests/evidence_ui.py`. It covers unscored-but-visible data, CSV downloads, mobile layout, mismatched run responses and retrying the captured target.

## Model readiness

Both native catalog classifiers run locally. Verify artifact integrity and inference on eligible bundled rows with `backend/.venv/Scripts/python.exe backend/check_models.py` from the root. These models score catalog feature vectors; they do not classify raw images or arbitrary light curves. See [the project review](docs/PROJECT-REVIEW.md) for input requirements, training evidence, label limitations and the supported project structure. Archived prototypes under legacy/ are not active application paths. The [TESS temporal validation](docs/TOI-VALIDATION.md) records scores and feature coverage on newer NASA candidates from unseen hosts.

## Train an independent candidate model

From backend/: `.venv/Scripts/python.exe train.py TOI` (or KOI). Training uses the shared catalog adapter and host-isolated partitions. The command prints a unique model name. Enter that name in the workbench Catalog model ID field for the corresponding mission. Artifacts publish as complete new directories under backend/training-output; the HTTP API cannot train or replace models. Baseline native models and their manifests are included under backend/models.

Use `--dataset updated-catalog.csv` to retrain on new labeled catalog data and `--rounds 200` to set the tree ceiling. This trains a new artifact rather than continuing an existing model. Manifests record data eligibility, configuration and actual dependency versions. Training metrics are local snapshot evaluations, not external scientific validation. No calibrated confidence claim is made.

## Optional containers

`docker compose up --build` serves the app at http://127.0.0.1:8080 with a persistent analysis-data volume. Containers were configured but not built in this session. Public hosting requires a separate authentication and operational design; the supplied binding is local only.
