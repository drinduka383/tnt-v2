"""Shared feature order and analysis failure contract."""
FEATURES = {
 'TOI': ('pl_trandurherr1', 'eng_transit_probability', 'pl_trandurherr2', 'eng_prad_srad_ratio', 'pl_orbpererr1', 'pl_orbper', 'eng_period_duration_ratio', 'eng_duration_period_ratio', 'pl_tranmiderr1', 'pl_trandeperr2', 'pl_tranmid', 'pl_trandep', 'pl_trandurh', 'pl_trandeperr1', 'st_tmagerr2', 'st_disterr2', 'st_loggerr2', 'st_disterr1', 'st_dist', 'st_teff', 'st_tmagerr1', 'st_rad', 'st_tefferr2'),
 'KOI': ('koi_prad', 'koi_dor', 'koi_ror', 'koi_num_transits', 'koi_duration_err1', 'koi_prad_err1', 'koi_period_err2', 'koi_srad_err1', 'koi_insol', 'eng_transit_probability', 'koi_model_snr', 'koi_srho', 'koi_max_mult_ev', 'koi_teq'),
}
MODEL_FAMILY = {'tess': 'TOI', 'kepler': 'KOI'}
SCHEMA_VERSION = 'catalog-shared-signed-v2'

class AnalysisError(Exception):
    def __init__(self, message, status=422, code='insufficient_evidence'):
        super().__init__(message)
        self.status, self.code = status, code

UNITS = {
 'TOI': {**dict.fromkeys(('pl_trandurherr1','pl_trandurherr2','pl_trandurh'), 'hours'),
         **dict.fromkeys(('pl_orbpererr1','pl_orbper','pl_tranmiderr1'), 'days'),
         'pl_tranmid': 'BJD',
         **dict.fromkeys(('pl_trandeperr2','pl_trandep','pl_trandeperr1'), 'ppm'),
         **dict.fromkeys(('st_tmagerr2','st_tmagerr1'), 'mag'),
         **dict.fromkeys(('st_disterr2','st_disterr1','st_dist'), 'pc'),
         'st_loggerr2': 'log10(cm/s^2)',
         **dict.fromkeys(('st_teff','st_tefferr2'), 'K'), 'st_rad': 'R_sun',
         **dict.fromkeys(('eng_transit_probability','eng_prad_srad_ratio','eng_period_duration_ratio','eng_duration_period_ratio'), 'dimensionless')},
 'KOI': {'koi_prad': 'R_earth', 'koi_dor': 'dimensionless', 'koi_ror': 'dimensionless',
         'koi_num_transits': 'count', 'koi_duration_err1': 'hours', 'koi_prad_err1': 'R_earth',
         'koi_period_err2': 'days', 'koi_srad_err1': 'R_sun', 'koi_insol': 'Earth_flux',
         'eng_transit_probability': 'dimensionless', 'koi_model_snr': 'dimensionless',
         'koi_srho': 'g/cm^3', 'koi_max_mult_ev': 'dimensionless', 'koi_teq': 'K'},
}
