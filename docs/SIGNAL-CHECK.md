# Check this signal

Select **Check this signal** below the transit search of a completed TESS analysis with a saved fit. The check is a separate durable run linked to its original analysis. It neither refits the published-candidate model nor changes saved photometry, catalog labels, or scores.

The check measures the original windows, refits after omitting up to eight usable windows, then tests the original timing in one independent sector. It prefers a prepared light curve from a nearby sector and tries a TESS pixel cutout when no suitable prepared sector is listed. A coarse cadence or distant observing dates produce an inconclusive result. Each usable window needs at least two in-dip cadences, 60% of the expected in-dip sample count, and measurements on both sides for a local linear baseline. The independent test needs three usable events. It compares the measured depth and scatter with the original depth and also tests whether a synthetic dip of the original depth can be recovered at those times. A missing dip in a different extraction remains inconclusive. This is a fixed-timing and depth check with a provisional rule, not a calibrated planet classifier or a complete search of the independent sector.

| State | Owner | What the result means |
| --- | --- | --- |
| Analysis lifecycle | Saved run | Queued, running, terminal, or cancelled. The signal check has its own lifecycle. |
| Transit search | Original evidence | Screen passed, below threshold, skipped, or failed. The old result fields remain readable. |
| Published follow-up | Catalog evidence | Ready, empty, unavailable, or skipped. A missing note after a failed lookup does not imply no follow-up. |
| Published timing | Per candidate | Measured, insufficient coverage, unsupported timing, unavailable, or skipped with a reason. |
| Repeatability | Signal check | Repeats, did not repeat at the tested schedule, or inconclusive with a reason. |
| Browser connection | Workbench | Reconnect or leave without ending the server run. Cancellation is a separate server action. The browser still derives button state from the URL and current record. |

## Pilot measurements

Run `backend/.venv/Scripts/python.exe backend/benchmark_signal_check.py` from the repository root. The seeded benchmark uses 30 simulations for each case. It recovered all 30 clean injected signals, marked all 30 empty observations and all 30 deliberately shifted signals as absent at the original times, abstained on all 30 observations with gaps at the predicted events, and abstained on 27 of 30 noisy injected signals. The simulated noise is white and the periods/durations are fixed, so these numbers are regression evidence and do not establish a field false-alarm rate.

On real data, the app recovered WASP-18 b with 23 usable events in independent sector 105 after fitting sector 106. TIC 142874279 abstained due to the independent cadence. Replaying the published timing in the original archived observations returned repeats for both the known planet WASP-18 b and the known nearby eclipsing binary TOI 1000.01. All six shifted timing controls on each light curve returned absence at the shifted timing. TOI 1000.01 did not recur in a separate older extraction at the exact published timing, which is why support in one observation and a published false-positive disposition are tracked separately. These examples establish behavior, not population performance. A neural model has not been trained or promoted because this pilot lacks a representative labeled holdout and cannot establish an improvement at a fixed false-alarm rate.

The recent-run lookup now reads summary fields from SQLite instead of transferring and decoding plot payloads in Python. In a 100-call local replay it returned the same summaries in about 6.1 ms per call versus 10.8 ms. Two archived TESS light curves reloaded to identical photometry arrays, and the stored native TOI 1000.01 model score reproduced exactly.
