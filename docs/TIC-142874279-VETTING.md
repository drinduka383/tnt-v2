# TIC 142874279: follow-up on the 4.57-day fit

The original saved run `ae24aa3583fc4fe6836994a2089f3ae9` used the TESS-SPOC sector 31 product. Its strongest box had a 4.570804-day period, a 28.8-minute duration (the shortest duration tested by the app), and depth-to-error ratio 5.22. These checks reuse the archived photometry and pixel products. No model score is involved.

## Individual events in sector 31

At the original period and epoch, fit a local line to points between 36 minutes and 5.28 hours from each predicted midpoint. Measure the fractional flux loss inside the 28.8-minute window. Require data on both sides. Four windows contain three usable corrected cadences each, and all four window averages are below their local baselines. Their approximate depths are 0.67%, 0.43%, 0.54% and 0.21%. The same dip pattern appears in uncorrected aperture flux from the same exposures, which shows that the correction alone did not create the pattern. The two flux columns are not independent observations.

Leaving out each of the three deeper windows in turn changes the strongest period to 5.081 days. Leaving out the shallowest leaves 4.571 days as the best fit. A separate blind search after dividing by a one-day running median favors approximately 8.19 days. Neither check demonstrates a stable period. The short fitted duration is only about three exposures.

A simple in/out pixel comparison of the same four windows places the brightest pixel of missing flux on one of the two pixels adjacent to the catalog position in each case. This supports a dimming near the target position in those images. The test uses the same three in-dip samples per event and does not fit a point-response function or establish astrometric significance. A close neighbor could still be responsible.

## Other observations

Checked sectors 4, 31, 105, 106, 107 and 108 using TESScut pixels and the 3 ? 3 background-subtracted aperture. A listed sector 97 cutout exceeded the download limits on both attempts and was not included. We tested the sector 31 ephemeris directly, and searched independently in each sector after detrending. We also let the epoch vary while searching within 2% of the trial period. The other sectors do not reproduce a coherent 4.5708-day signal in these tests. Sector 4 did not have adequate sampled original windows for a direct comparison, and sector 106 aperture flux is particularly noisy. The best shared-period fit in a weighted, detrended search of sectors 105?108 over 4.48?4.67 days is 4.6175 days. That period drifts by about 4.5 hours over four cycles relative to the original period, too far to explain all four of the original half-hour windows. The alternate fit was exploratory and is not a second candidate.

The early and recent observations are separated by years, so failure at the exact extrapolated epoch alone is weak evidence. The period instability within sector 31 and across the tested reductions is more informative. Keep this as an unvetted lead. A better independent test would use cleaner or higher cadence observations with a stable period and well-sampled events.

Output files are in `backend/data/validation/tic-142874279/`. They include `sector31-events.png`, `sector31-pixel-check.png`, `sector31-event-check.json`, and `independent-sector-check.json`.
