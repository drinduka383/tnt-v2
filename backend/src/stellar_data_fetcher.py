"""Fetch canonical host metadata once, without hidden caches or alias guessing."""
from dataclasses import dataclass
import numpy as np
from src.contracts import AnalysisError
from src.data_mapper import number

@dataclass
class StarMetaFetcher:
    mission: str
    target_id: str

    def fetch_stellar(self):
        if self.mission == 'tess':
            from astroquery.mast import Catalogs
            Catalogs.TIMEOUT = 45
            table = Catalogs.query_criteria(catalog='TIC', ID=int(self.target_id))
            if len(table) != 1:
                raise AnalysisError('Host metadata was not found.', 404, 'not_found')
            raw = {key: None if np.ma.is_masked(table[0][key]) else table[0][key].item() if hasattr(table[0][key], 'item') else table[0][key] for key in table.colnames}
            stellar = {}
            for source, target in [('Teff','st_teff'),('rad','st_rad'),('mass','st_mass'),('logg','st_logg'),('d','st_dist'),('Tmag','st_tmag')]:
                value, error = number(raw.get(source)), number(raw.get('e_' + source))
                stellar.update({target: value, target + 'err1': error, target + 'err2': -error if error is not None else None})
            return {'source': 'MAST TIC', 'raw': raw, 'stellar': stellar}
        from src.analysis import catalog_query
        rows = catalog_query(f'select * from q1_q17_dr25_stellar where kepid={int(self.target_id)}')
        if not rows:
            raise AnalysisError('Kepler stellar metadata was not found.', 404, 'not_found')
        raw, stellar = rows[0], {}
        for source, target in [('teff','st_teff'),('radius','st_rad'),('mass','st_mass'),('logg','st_logg'),('dist','st_dist')]:
            stellar.update({target: number(raw.get(source)), target + 'err1': number(raw.get(source + '_err1')), target + 'err2': number(raw.get(source + '_err2'))})
        return {'source': 'NASA DR25 stellar', 'raw': raw, 'stellar': stellar}
