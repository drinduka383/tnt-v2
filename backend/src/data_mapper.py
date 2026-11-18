"""Catalog adapters preserve missing values and mission-specific names."""
from dataclasses import dataclass, asdict
import math
from src.contracts import FEATURES, MODEL_FAMILY

def number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None

@dataclass
class ModelPayload:
    model_type: str
    optimization_type: str
    model_name: str | None
    data: list

    def to_dict(self):
        return asdict(self)

def build_model_payload_from_row(mission, row, optimization_type='balanced', model_name=None, overrides=None):
    family = MODEL_FAMILY[mission.lower()]
    features = {name: number(row.get(name)) for name in FEATURES[family]}
    for name in features:
        if name.startswith('eng_'):
            features[name] = None
    if family == 'KOI':
        dor = number(row.get('koi_dor'))
        features['eng_transit_probability'] = 1 / dor if dor and dor >= 1 else None
    else:
        period, duration = number(row.get('pl_orbper')), number(row.get('pl_trandurh'))
        if period and duration and period > 0 and duration > 0:
            features['eng_period_duration_ratio'] = period / (duration / 24)
            features['eng_duration_period_ratio'] = (duration / 24) / period
        radius, stellar_radius = number(row.get('pl_rade')), number(row.get('st_rad'))
        if radius is not None and stellar_radius and stellar_radius > 0:
            features['eng_prad_srad_ratio'] = radius / (stellar_radius * 109.0)
        logg = number(row.get('st_logg'))
        if logg is not None and stellar_radius and period and stellar_radius > 0 and period > 0:
            try:
                r = stellar_radius * 6.957e10
                a = (10 ** logg * r * r * (period * 86400) ** 2 / (4 * math.pi ** 2)) ** (1 / 3)
                features['eng_transit_probability'] = min(1.0, r / a)
            except (OverflowError, ZeroDivisionError):
                pass
    if overrides:
        features.update({key: number(value) for key, value in overrides.items() if key in features})
    return ModelPayload(family, optimization_type, model_name, [features])
