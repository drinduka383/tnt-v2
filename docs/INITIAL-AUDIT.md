# TNT v2: rebuild the contract before the interface

## Product reconstructed from the code

The intended product, branded ?A World Away,? is an interactive exoplanet exploration and candidate-screening workbench. A person chooses a star from presets, an identifier form, or a filtered TIC catalog search; sees it in an Aladin sky atlas; requests analysis; and receives stellar properties, light-curve graphics when available, and a classifier result. A second ambition is user-configurable model training.

This is inferred from executable paths, not established by a product specification. Intended audience, scientific accuracy requirement, deployment load, and whether education or research is primary remain unknown. Those choices affect presentation and validation, but do not excuse incorrect identities or invented measurements.

The actual pipeline is:

1. Start.jsx stores selected stars and analysis settings. Search uses api.js; analysis uses analyze.js/client.js.
2. GET /analyze constructs StarProcessor, whose constructor performs archive requests, metadata fetching, and sometimes a FITS download.
3. With OI lookup enabled and a matching row, catalog-derived features go directly to classification. Otherwise, LatestFITSFetcher selects an observation and ExoplanetParameterProcessor loads, cleans, normalizes, searches with BLS, derives features, and renders plots.
4. Two mappers produce model input. ModelService resolves a pickle or model file, selects hard-coded features, applies a threshold, and returns candidate/false-positive labels.
5. normalizeResults collapses the first classifier result into the UI. No durable analysis run records what actually happened.

Critically, a catalog row and an independently processed observation are different evidence sources. Catalog lookup can classify an already characterized candidate without searching the light curve at all. Calling both ?AI analysis? hides that distinction. A star can host multiple transit candidates, and selecting rows[0] cannot represent that system.

## Irreducible constraints

- Identity is a mission plus catalog namespace plus identifier. TIC, TOI, KIC, KOI and Gaia identifiers are not interchangeable numbers. Resolve candidate aliases to their host before fetching host observations.
- A star is not an observation; an observation is not a transit candidate; a candidate is not a confirmed planet.
- A score is meaningful only for a particular feature schema, units, preprocessing, training population, model artifact and decision threshold.
- Missing evidence is neither zero nor negative evidence. An unavailable archive is not an empty catalog result.
- Asynchronous work can finish after the initiating screen or target has changed. Results must belong to a captured request, never whichever target is currently selected.
- Training and evaluation cannot share sampled observations. Related candidates from one host may also violate independence even when rows differ.
- A result must be reproducible without relying on ?latest,? process working directory, mutable shared files, or whichever default artifact happens to exist.

## What a principal architect should rewrite first

Rewrite the analysis boundary and its ownership of evidence. Keep React, Flask, Aladin and the existing scientific libraries until their limitations are measured. Framework replacement cannot fix scientific ambiguity.

Replace constructor-driven orchestration with a run service. Its input captures canonical target identity, evidence mode, selected observation or catalog snapshot, processing settings and an explicit model version. Each completed result records these inputs and their provenance. Stage functions consume explicit inputs and return values or typed failures. They should not hide network requests in object construction.

Use one feature contract per model family: ordered names, units, missingness policy and preprocessing version. Both catalog and FITS adapters must produce that contract. The artifact owns the expected schema; prediction must check it. Do not maintain several independent lists and guess that they agree.

Treat models as immutable artifacts. Training produces a candidate artifact and evaluation; publication is a separate, atomic pointer update after acceptance. An explicit missing model name must fail, never silently fall back. Production inference should not be able to overwrite its own model files through a public training request.

The highest-level abstraction is a reproducible AnalysisRun, not a generic workflow framework or another API wrapper. A result is a versioned conclusion over identified evidence. This removes most ad hoc coordination among UI flags, temporary paths, feature adapters and model defaults. It does not remove uncertainty in the underlying science.

## State-machine inventory

| Machine and current owner | Hidden state or failure | Required explicit contract | v2 status |
| --- | --- | --- | --- |
| Analysis UI, Start.jsx | hasResults, isAnalyzing, resultsData, analyzeError allow loading forever after error | idle -> loading -> success/error; Back invalidates completion | Fixed locally with one status object and request generation |
| Request lifetime, Start.jsx | old request can restore results after Back or unmount | only current request may commit | Fixed for UI publication; backend cancellation remains |
| Search form, StarSearch | local form resets on tab mount while parent retains old request settings | parent owns submitted settings | Shared identity/mission/settings now controlled; FITS draft still local |
| Target selection, Start.jsx | preset, filtered, typed and sky selections can disagree; numeric namespace guesses | one canonical target with selection source | Open; requires identity resolver and preset audit |
| Search, StarFilters/api.js | loading/error/empty; tab unmount loses form; obs selector not consumed by backend | explicit query snapshot and empty vs failed result | Open |
| Mobile panels, Start.jsx | open, menu flag, active panel can contradict; viewport read is not reactive | one panel enum plus responsive layout | Open |
| Viewer, SkyAtlas.tsx | initialization pending, ready, failed, disposed; effects before ready are lost; init rejection unhandled | latest props applied once ready; error and disposal handling | Open |
| Catalog resolution, StarProcessor | found overwritten by checkOI; first candidate only; constructor side effects | resolved host plus candidate list, absent vs failed | Open |
| Evidence acquisition, LatestFITSFetcher | latest observation, preferences and shared manifest state | immutable observation reference and isolated cache publication | Open; manifest updates can race |
| Upload, FileProcessor | same filename means silently reuse earlier content; stream name can differ from filename | validated FITS artifact with unique identity and lifecycle | Open; upload UI is not wired end to end |
| FITS processing, ExoplanetParameterProcessor | mutable intermediate fields; validation errors only logged; plotting may partially fail | stage result with quality flags, hard failures and optional plots | Inference now refuses unavailable required measurements; full extraction policy remains open |
| Feature adaptation, data_mapper/manual | separate schemas; Kepler catalog mapping emits TOI-shaped feature fields | family-specific shared feature schema and units | Open; Kepler catalog path needs repair before claiming support |
| Model resolution, ModelService | custom absent -> fallback; model type/schema guessed; paths depend on cwd | immutable model ID, explicit schema and provenance | Train/predict default directory aligned; full registry open |
| Training, ModelService | oversampling before splits; several direct artifact writes; no publication transaction | partition -> train -> evaluate -> candidate -> published | Oversampling moved after split, training only; atomic publication and host grouping open |
| Model result transport, main.py | predict error tuple embedded inside HTTP 200 analysis | terminal error preserves HTTP status | Fixed locally |
| Result semantics, normalizeResults | guessed logits/percentages and first result only | bounded class score with explicit meaning; all candidates represented | Removed heuristic conversion and misleading confidence label; multi-candidate display open |
| Training UI, HyperParametersPanel/Start | Train button only logs configuration; no training lifecycle | actual operation or explicit unavailable state | Open; do not advertise this as working training |
| API transport, api.js/api2.js/client.js | three clients disagree about base URL, error and timeout semantics | one same-origin transport and error contract | Main analysis origin and local proxy fixed; consolidation open |

This is an inventory of observed machines and their disposition, not a claim that every state machine has been eliminated. Cosmetic booleans should not all become libraries. An enum or derived value is usually sufficient; use a durable server state machine only for work that must survive process or browser loss.

## The single day-one design-breaking test

Analyze a target with all required feature keys present but every measurement unavailable. Stub archive resolution and observation acquisition so this condition is deterministic, then submit it through the analysis endpoint.

Pass condition: terminal insufficient-evidence response (422), zero predictor calls, no planet/false-positive verdict, and a UI that displays the reason and permits retry. The original implementation converts nulls to zero and may return a normal classification. This tests the core promise: the product must not manufacture certainty from absent evidence.

The checked-in unit regression exercises the evidence guard with null, NaN, infinity, malformed strings and booleans, plus legitimate numeric zero. Frontend tests verify that model-error responses cannot normalize into successful results and that probabilities outside [0,1] are not reinterpreted. These are component proofs, not the full endpoint/browser test above.

Next acceptance scenarios: A starts, Back, B starts, B finishes, A finishes; only B may publish. Train artifact X, predict X, request nonexistent Y; Y must fail. Concurrent publish and inference must see complete old or complete new artifacts. Multiple candidates on one host must remain distinct. Offline archive must become upstream-unavailable, not no-planets.

## Scientific concerns that survive clean architecture

- KOI training labels candidate and confirmed alike as positive; TOI labels only CP/KP positive and drops other non-FP dispositions. These model families answer different questions.
- A classifier score is not calibrated confidence in the displayed verdict, and a threshold crossing cannot confirm a planet. Show model class score and catalog disposition separately.
- Row-level random splitting can leak host-specific information. Group by host and audit observation/candidate duplication, then evaluate on held-out observations with known provenance.
- Uncertainty features and catalog-derived features may distinguish catalog curation or follow-up completeness rather than planetary physics. A declared ?non-leaky? feature list does not prove absence of leakage.
- Feature units and sign conventions must be compared across dataset, catalog mapper and FITS extraction. Existing catalog adaptation takes absolute error magnitudes, and different time references occur. Do not assert consistency without a unit audit.
- BLS always finding a best period is not sufficient evidence of a transit. Detection quality, aliases, coverage, contamination and out-of-distribution inputs need independent acceptance criteria.
- Rejecting incomplete features now is deliberately conservative and may make many real targets unclassifiable. Replace that restriction only with a scientifically justified preprocessing policy fitted during training and packaged with the model.

## Rebuild sequence and alternatives

1. Lock one honest vertical slice: canonical TIC target, pinned observation, fixed processing config, one versioned model, explicit unavailable-evidence result, provenance visible with result. Build integration tests with network boundaries stubbed and separately replay a pinned real observation.
2. Introduce AnalysisRun persistence with SQLite and a worker only when resumable work is implemented. POST creates the run, GET reads its status/result. Include accepted, running (stage), succeeded, insufficient_evidence, failed and cancelled; terminal states cannot regress. Idempotency keys collapse duplicate submissions; lease/attempt identity prevents old workers publishing after retries. Browser abandonment and server cancellation are different operations.
3. Unify feature contracts and repair Kepler/catalog semantics. Return candidates as a list and preserve catalog facts separately from model conclusions. Capture observation checksums, processing version, model digest, threshold and quality flags.
4. Move training behind an explicit privileged/offline operation. Split original hosts before any resampling. Publish artifacts atomically with their preprocessing/schema/metrics. Remove mutable default replacement from ordinary analysis.
5. Reduce UI to selection, request state and displayed run. Remove dead controls and duplicate clients/components after behavior is covered. Optimize 3D assets only after correctness; current production bundle warns about size.

Alternative A is incremental hardening of the current request/response implementation. It is the smallest diagnostic baseline and the approach used for the bounded fixes here, but it cannot provide durable runs or reproducible retries. Alternative B, recommended for the rebuild, is one modular application with a persisted run boundary, existing Python processing, and React UI. Alternative C is microservices, event sourcing or a general workflow platform; reject it until operational requirements justify those costs.

The strongest objection to AnalysisRun is that persistence and workers could overwhelm an educational demo. If education is the actual goal, the simpler product may be a curated library of precomputed, reproducible observations with interactive explanations. That eliminates live archive and training orchestration from the user path. Do not decide this by infrastructure taste; decide whether users need novel analysis or reliable exploration.

## Verification and boundaries

The imported revisions are pinned in SOURCES.md. Changes live only in this independent repository; reference clones are ignored. No upstream pushes or remote repository creation were performed.

Verified locally: frontend production build; Node normalization regressions; Python evidence-validation regressions; Python source compilation. Scientific dependencies, model artifact loading, real NASA/MAST calls, model retraining, concurrent publication and actual browser flows were not run. The independent read-only reviewer identified missingness, model publication, evaluation contamination and the Kepler mapping contract; these findings informed the fixes and open inventory.

Do not deploy this baseline as a trustworthy scientific classifier. Public training input, pickle artifact selection, file isolation, incomplete search validation, upstream timeouts, non-atomic writes and deployment routing still require work. No real user observations were deleted, no models were retrained, and no claim is made that the remaining open transitions are fixed.
