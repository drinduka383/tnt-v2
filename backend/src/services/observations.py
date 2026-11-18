"""One bounded exact-identity query shared by availability and acquisition."""
import json
import re
from src.contracts import AnalysisError
from src.services.mast_search_service import MastSearchService


def lightcurve_products(identifier, mission):
    if not re.fullmatch(r'[1-9][0-9]{0,15}', identifier) or mission not in ('tess', 'kepler'):
        raise AnalysisError('Use a canonical mission host identifier.', 400, 'invalid_request')
    names = [identifier.zfill(9), identifier, 'TIC ' + identifier] if mission == 'tess' else ['kplr' + identifier.zfill(9)]
    authors = ['SPOC', 'TESS-SPOC', 'QLP'] if mission == 'tess' else ['Kepler']
    query = {'service': 'Mast.Caom.Filtered', 'format': 'json', 'pagesize': 1000, 'page': 1,
             'params': {'columns': 'obsid,target_name,dataURL,provenance_name,sequence_number,t_exptime',
                        'filters': [{'paramName': 'target_name', 'values': list(dict.fromkeys(names))},
                                    {'paramName': 'project', 'values': ['TESS' if mission == 'tess' else 'Kepler']},
                                    {'paramName': 'provenance_name', 'values': authors},
                                    {'paramName': 'dataproduct_type', 'values': ['timeseries']},
                                    {'paramName': 'dataRights', 'values': ['PUBLIC']}]}}
    try:
        _, content = MastSearchService().mast_query(query, timeout=(5, 20))
        result = json.loads(content)
        if result.get('status') != 'COMPLETE' or not isinstance(result.get('data'), list):
            raise ValueError('Incomplete archive response')
        if mission == 'kepler' and result['data']:
            obsids = [str(row['obsid']) for row in result['data']]
            _, content = MastSearchService().mast_query({'service': 'Mast.Caom.Products', 'format': 'json',
                'pagesize': 1000, 'page': 1, 'params': {'obsid': ','.join(obsids)}}, timeout=(5, 20))
            result = json.loads(content)
            if result.get('status') != 'COMPLETE' or not isinstance(result.get('data'), list):
                raise ValueError('Incomplete Kepler product response')
            for row in result['data']:
                row['dataURL'] = row.get('dataURI')
                row['provenance_name'] = 'Kepler'
                quarter = re.search(r'\bQ([0-9]+)\b', row.get('description') or '')
                row['sequence_number'] = int(quarter[1]) if quarter else None
        products, seen = [], set()
        for row in result['data']:
            uri = row.get('dataURL') or ''
            if not isinstance(uri, str) or not uri.startswith('mast:') or not re.search(r'(?:[_-]lc|_[ls]lc)\.fits(?:\.gz)?$', uri, re.I) or uri in seen:
                continue
            seen.add(uri)
            sector = row.get('sequence_number')
            products.append({'uri': uri, 'author': row.get('provenance_name') or 'Unknown',
                             'group': int(sector) if sector is not None and int(sector) >= 0 else None,
                             'exptime': str(row.get('t_exptime') or 'unknown')})
        limited = int(result.get('paging', {}).get('rowsFiltered', len(result['data']))) > len(result['data'])
        if limited and not products:
            raise ValueError('Truncated search cannot establish absence')
        products.sort(key=lambda item: item['uri'], reverse=True)
        products.sort(key=lambda item: (authors.index(item['author']) if item['author'] in authors else len(authors), mission == 'kepler' and '_slc.fits' in item['uri'], -(item['group'] or 0)))
        return products, limited
    except Exception as error:
        raise AnalysisError('Light-curve availability could not be checked. Retry the check.', 502, 'upstream_unavailable') from error


class ObservationIndex:
    """Reuse successful listings between preview and acquisition, never cache failures."""
    def __init__(self):
        from collections import OrderedDict
        from threading import Lock
        self.entries = OrderedDict()
        self.lock = Lock()

    def get(self, identifier, mission):
        import time
        key = (mission, identifier)
        with self.lock:
            entry = self.entries.get(key)
            if entry and entry[0] > time.monotonic():
                self.entries.move_to_end(key)
                return entry[1]
        listing = lightcurve_products(identifier, mission)
        with self.lock:
            self.entries[key] = (time.monotonic() + (600 if listing[0] else 60), listing)
            self.entries.move_to_end(key)
            while len(self.entries) > 128:
                self.entries.popitem(last=False)
        return listing
