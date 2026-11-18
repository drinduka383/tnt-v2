# TIC 50365310 and TIC 142870233 follow-up

## TIC 50365310

TIC 50365310 is a star listed in the TESS Input Catalog, also known as TOI-1000, Gaia DR3 3033676761434888320 and TYC 5404-00535-1. TOI 1000.01 is the periodic signal that was flagged as a possible planet. The NASA TAP `toi` table marks it `FP`; the ExoFOP row has `TESS Disposition=EB`, `TFOPWG Disposition=FP`, and the comment ?TFOP FP; retired as NEB.? NEB refers to a nearby eclipsing binary. The ExoFOP target page lists no confirmed planet, and the NASA `ps` query by this TIC returned no rows. The NASA overview page still displays Candidate Planet, so use the follow-up disposition for vetting status.

- [ExoFOP target record](https://exofop.ipac.caltech.edu/tess/target.php?id=50365310)
- [ExoFOP TOI row and follow-up comment](https://exofop.ipac.caltech.edu/tess/download_toi.php?toi=1000.01&output=csv)
- [NASA overview](https://exoplanetarchive.ipac.caltech.edu/overview/TOI-1000.01)
- [NASA TOI table disposition definitions](https://exoplanetarchive.ipac.caltech.edu/docs/API_TOI_columns.html)

## What the local analysis found

The saved combined run `cce039b32d9e4d229d4129bbb044153f` downloaded SPOC sector 34 photometry. The app's exploratory search found a 2.17233-day signal, close to the published 2.17135 days. The local catalog classifier scored it false-positive-like. The exact candidate appears in the reconstructed training partition, so the result is an in-sample demonstration and supplies no independent evidence for the follow-up decision.

We also folded the FITS time series at the published period and epoch (2459229.630046 BJD TDB). For each well-covered event, we fitted a local line outside the dip between one and three published durations from its center on both sides. Depth is the mean relative flux decrement within 0.35 durations of center. Errors below are empirical standard errors across events. They omit shared systematics and are not a vetting statistic.

| Photometry | Primary (12 events) | Halfway between primary events (10 events) |
| --- | ---: | ---: |
| SAP | 756 ? 50 ppm | 3 ? 94 ppm |
| PDCSAP | 720 ? 49 ppm | 92 ? 37 ppm |

The dip appears in both products. The odd and even primary depths agree within the empirical scatter. The small halfway dip does not reproduce in SAP. Neither check can localize the eclipse because a TESS light curve sums light across an aperture. The public DAVE sector 7 difference image shows the changing flux close to the target marker and visually displaced from it. The displayed image alone does not give a localization significance or uniquely identify the neighbor. A stronger independent check is to compare in-transit and out-of-transit pixel images, match the centroid to nearby Gaia stars and corroborate with higher-resolution time-series photometry. The ExoFOP disposition is the evidence used here for the nearby-binary attribution.

- [DAVE sector 7 difference image](https://exofop.ipac.caltech.edu/tess/get_file.php?id=268353)
- [ExoFOP follow-up file list](https://exofop.ipac.caltech.edu/tess/download_filelist.php?id=50365310&output=csv)
- [SPOC data validation diagnostic methods](https://heasarc.gsfc.nasa.gov/docs/tess/docs/jenkinsSPIE2016-copyright.pdf)
- Local plot: `backend/data/validation/toi-1000-ephemeris.png`

## TIC 142870233

The pasted empty result belongs to another star. The MAST TIC lookup returned `objType=STAR`, Gaia source 5053513431632397952, TIC temperature 4617 K and TESS magnitude 14.5583. NASA returned no matching rows in either `toi` or `ps` at check time. The app found no ready-made light curve in its supported product search. TESScut nevertheless listed sectors 4, 31, 97, 105, 106, 107 and 108 at the catalog position.

We downloaded a 7 ? 7 pixel sector 31 cutout and extracted **3,445 quality-zero samples over 25.42 days**. This uses a 3 ? 3 aperture centered on the nearest WCS pixel and per-exposure background estimated from the median of the border pixels. It is exploratory photometry without a contamination model or transit vetting. The result shows the difference between lack of a supported prepared product and lack of observations. The extraction was done outside the app.

- [ExoFOP target record](https://exofop.ipac.caltech.edu/tess/target.php?id=142870233)
- [NASA TESS data products and TESScut](https://heasarc.gsfc.nasa.gov/docs/tess/data_products.html)
- Local outputs: `backend/data/validation/tic-142870233/sector31-exploratory.csv` and `sector31-aperture.png`

### Seven-sector vetting and recovery pilot

We downloaded pixel time series for all seven cataloged sectors at the verified TIC 142870233 coordinates. The 6.8642-day proposal comes from an exploratory box search on the sector 108 aperture. We checked the original epoch and duration in all seven sectors, and ran a separate blind search per sector after subtracting slow trends by dividing by a running median of approximately one day, within continuous segments.

| TESS sector | Strongest period after detrending (days) |
| ---: | ---: |
| 4 | 7.363 |
| 31 | 6.991 |
| 97 | 14.072 |
| 105 | 7.016 |
| 106 | 0.671 |
| 107 | 7.524 |
| 108 | 3.483 |

The peaks do not establish a coherent 6.8642-day ephemeris. Some independent peaks fall around seven days, which is insufficient to claim the same signal without matching event times. The original period search reported four sector 108 windows containing samples. Three lacked enough data before the predicted dip, and the fourth missed nearly the whole dip. The pixel difference check required at least 60% of the expected in-dip exposures and at least half the expected cadences on each side in windows between one and two durations from center. None of the sector 108 events met that requirement. We did not assign a physical source to the putative dip. The large age gap to early sectors also makes the original ephemeris less predictive there.

For the recovery pilot we injected box dips lasting 1.92 hours into the original sector 108 aperture flux, using four evenly spaced phases per depth and period. The search used the app's 4,000 trial periods, eight durations and exploratory screening rule. Recovery required the top result to pass that rule, match the injected period to within 2%, and match the epoch within half the injected duration. The pilot includes competition from real signals and systematics already present in the aperture flux.

| Injected depth | 1 day | 3 days | 7 days |
| ---: | ---: | ---: | ---: |
| 0.2% | 0/4 | 0/4 | 0/4 |
| 1% | 0/4 | 0/4 | 0/4 |
| 4% | 4/4 | 2/4 | 1/4 |

This is a small pilot on one aperture and one sector. It suggests poor sensitivity for this exact search setup and does not provide planet radius limits or rule out planets. The sector checks and recovery script run offline via `backend/vet_tess_signal.py`. `backend/data/validation/tic-142870233/vetting/vetting.json` records the original ephemeris, file hashes, per-event coverage and trial results. The plot outputs are `sector-window-check.png` and `injection-recovery.png` in the same directory. The app's production detection rule was not changed by this experiment.
