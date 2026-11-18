"""Reject unavailable evidence instead of silently manufacturing zero measurements."""
import math

def validate_features(rows, features):
    if not isinstance(rows, list) or not rows:
        raise ValueError('Prediction data must be a non-empty list')
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError('Each prediction row must be an object')
        for feature in features:
            value = row.get(feature)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'Insufficient evidence: row {index}, {feature} must be a finite number')
            if feature in POSITIVE and value <= 0:
                raise ValueError(f'Insufficient evidence: {feature} must be positive')
            if feature == 'eng_transit_probability' and not 0 <= value <= 1:
                raise ValueError('Insufficient evidence: geometric transit probability must be within [0, 1]')
            if feature == 'pl_trandep' and not 0 <= value <= 1e6:
                raise ValueError('Insufficient evidence: transit depth must be within [0, 1e6] ppm')

# Signed lower uncertainties are intentionally excluded from these physical bounds.
POSITIVE = {'pl_orbper', 'pl_trandurh', 'st_rad', 'st_dist', 'st_teff',
            'koi_prad', 'koi_dor', 'koi_ror', 'koi_num_transits', 'koi_insol', 'koi_srho', 'koi_teq',
            'eng_prad_srad_ratio', 'eng_period_duration_ratio', 'eng_duration_period_ratio'}
