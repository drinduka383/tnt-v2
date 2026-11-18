"""Bounded target discovery and separate, explicit light-curve availability."""
import json
import re
from src.contracts import AnalysisError
from src.data_mapper import number
from src.services.mast_search_service import MastSearchService

MAX_RADIUS = .5
MAX_TARGETS = 200

def search_targets(ra, dec, radius):
    query = {'service': 'Mast.Catalogs.Filtered.Tic.Position', 'format': 'json',
             'pagesize': MAX_TARGETS, 'page': 1,
             'params': {'columns': 'ID,ra,dec,Tmag,Teff,objType', 'ra': ra, 'dec': dec, 'radius': radius,
                        'filters': [{'paramName': 'objType', 'values': ['STAR']},
                                    {'paramName': 'Tmag', 'values': [{'min': -5, 'max': 16}]}]}}
    try:
        _, content = MastSearchService().mast_query(query)
        result = json.loads(content)
        if result.get('status') != 'COMPLETE' or not isinstance(result.get('data'), list):
            raise ValueError('Incomplete MAST response')
        targets, seen = [], set()
        for row in result['data'][:MAX_TARGETS]:
            identifier = str(row.get('ID', ''))
            x, y = number(row.get('ra')), number(row.get('dec'))
            if row.get('objType') != 'STAR':
                continue
            if not re.fullmatch(r'[1-9][0-9]{0,15}', identifier) or identifier in seen or x is None or y is None or not 0 <= x <= 360 or not -90 <= y <= 90:
                continue
            seen.add(identifier)
            targets.append({'id': identifier, 'mission': 'tess', 'ra': x, 'dec': y,
                            'magnitude': number(row.get('Tmag')), 'temperature': number(row.get('Teff'))})
        targets.sort(key=lambda star: (star['magnitude'] is None, star['magnitude'] or 0, star['id']))
        total = int(result.get('paging', {}).get('rowsFiltered', len(result['data'])))
        return {'targets': targets, 'total': total, 'limited': total > len(result['data']),
                'limit': MAX_TARGETS, 'region': {'ra': ra, 'dec': dec, 'radius': radius},
                'source': 'MAST TIC', 'selection': 'TIC objects classified STAR; TESS magnitude -5 to 16'}
    except Exception as error:
        raise AnalysisError('Target catalog is unavailable. Retry this region.', 502, 'upstream_unavailable') from error


def observation_availability(identifier, index=None):
    from src.services.observations import lightcurve_products
    products, limited = index.get(identifier, 'tess') if index is not None else lightcurve_products(identifier, 'tess')
    samples = [{'author': item['author'], 'mission': f"TESS Sector {item['group']}" if item['group'] is not None else 'TESS',
                'exptime': item['exptime']} for item in products[:5]]
    return {'id': identifier, 'mission': 'tess', 'status': 'available' if products else 'none',
            'count': len(products), 'limited': limited, 'samples': samples,
            'source': 'MAST public SPOC/TESS-SPOC/QLP light-curve index; exact TIC target names'}
