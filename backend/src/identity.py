"""Exact, mission-aware identifiers; never infer namespace from arbitrary digits."""
import re
from src.contracts import AnalysisError, MODEL_FAMILY

def parse_target(mission, value):
    if not isinstance(mission, str) or mission not in MODEL_FAMILY or not isinstance(value, str):
        raise AnalysisError('Choose TESS or Kepler and enter an identifier.', 400, 'invalid_request')
    value = value.strip()
    host = 'TIC' if mission == 'tess' else 'KIC'
    match = re.fullmatch(rf'(?:{host}[ :_-]*)?([1-9][0-9]{{0,15}})', value, re.I)
    if match:
        return {'mission': mission, 'namespace': host, 'id': str(int(match[1]))}
    pattern = r'TOI[ -]*([1-9][0-9]{0,6}(?:\.[0-9]{1,2})?)' if mission == 'tess' else r'(?:KOI[ -]*|K)([0-9]{1,7}(?:\.[0-9]{1,2})?)'
    match = re.fullmatch(pattern, value, re.I)
    if match:
        return {'mission': mission, 'namespace': 'TOI' if mission == 'tess' else 'KOI', 'id': match[1]}
    raise AnalysisError(f'Use {host} host ID or a matching candidate ID.', 400, 'invalid_request')
