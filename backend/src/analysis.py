"""Explicit acquisition -> extraction -> validation -> prediction with provenance."""
from hashlib import sha256
from pathlib import Path
import json
import logging
import math
import requests
from src.contracts import AnalysisError, MODEL_FAMILY, FEATURES
from src.data_mapper import build_model_payload_from_row, number
from src.validation import validate_features

ARCHIVE = 'https://exoplanetarchive.ipac.caltech.edu/TAP/sync'
PROCESSING_VERSION = 'tnt-v2-evidence-4'

def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if hasattr(value, 'item'):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value

def catalog_query(query):
    try:
        response = requests.get(ARCHIVE, params={'query': query, 'format': 'json'}, timeout=(10, 45))
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError('Invalid catalog response')
        return rows
    except (requests.RequestException, ValueError) as error:
        raise AnalysisError('NASA catalog is unavailable; retry later.', 502, 'upstream_unavailable') from error

def resolve_target(target, query=catalog_query):
    mission, namespace, identifier = target['mission'], target['namespace'], target['id']
    table, host_column = ('toi', 'tid') if mission == 'tess' else ('cumulative', 'kepid')
    if namespace in ('TOI', 'KOI'):
        if namespace == 'TOI':
            where = f'toi={identifier}'
        else:
            parts = identifier.split('.')
            koi = f'K{int(parts[0]):05d}'
            where = f"kepoi_name='{koi}.{int(parts[1]):02d}'" if len(parts) == 2 else f"kepoi_name like '{koi}.%'"
        rows = query(f'select * from {table} where {where}')
        if not rows:
            raise AnalysisError('Candidate was not found in the catalog.', 404, 'not_found')
        hosts = {str(int(row[host_column])) for row in rows if row.get(host_column) is not None}
        if len(hosts) != 1:
            raise AnalysisError('Candidate does not resolve to one host.', 422, 'ambiguous_target')
        identifier = hosts.pop()
    host = {'mission': mission, 'namespace': 'TIC' if mission == 'tess' else 'KIC', 'id': identifier}
    rows = query(f'select * from {table} where {host_column}={identifier}')
    return host, rows

class AnalysisPipeline:
    def __init__(self, models, observation_index=None):
        self.models = models
        self.observation_index = observation_index

    def _observation(self, spec, host, directory, stage, provenance):
        stage('acquiring_observation')
        if spec['evidence'] == 'upload':
            path = directory / 'observation.fits'
            observation = {'source': 'uploaded FITS'}
        else:
            from src.fits_downloader import LatestFITSFetcher
            try:
                fetcher = LatestFITSFetcher(host['mission'], host['id'], outdir=directory / 'downloads')
                observation = fetcher.select_or_download(listing=self.observation_index.get(host['id'], host['mission'])) if self.observation_index else fetcher.select_or_download()
            except AnalysisError as error:
                if error.code != 'no_observation' or host['mission'] != 'tess':
                    raise
                from src.services.tess_pixels import download_cutout
                observation = download_cutout(host['id'], directory / 'downloads', stage)
            except Exception as error:
                raise AnalysisError('Light-curve observation is unavailable.', 502, 'upstream_unavailable') from error
            if not observation.get('path'):
                raise AnalysisError('No light-curve observation found.', 422, 'no_observation')
            path = Path(observation['path'])
        if 'coordinates' in observation:
            stage('extracting_features')
            from src.services.tess_pixels import aperture_photometry
            from src.exoplanet_processor import ExoplanetParameterProcessor
            row = observation['tic']
            stellar = {'st_teff': number(row.get('Teff')), 'st_rad': number(row.get('rad')), 'st_tmag': number(row.get('Tmag'))}
            metadata = {'source': 'MAST TESS Input Catalog', 'stellar': stellar,
                        'raw': {'ID': host['id'], **observation['coordinates']}}
            try:
                t, flux = aperture_photometry(path, observation['coordinates'], observation['group_val'])
                processed = ExoplanetParameterProcessor(path, 'tess', stellar, directory).process_samples(t, flux)
            except (OSError, ValueError, KeyError, TypeError) as error:
                raise AnalysisError('TESS returned pixels, but the cutout could not provide usable aperture photometry.', 422, 'unusable_cutout') from error
            provenance['observation'] = {'filename': path.name, 'sha256': sha256(path.read_bytes()).hexdigest(),
                                         'author': observation['author'], 'group': observation['group_val'],
                                         'uri': observation['uri'], 'kind': 'pixel_cutout',
                                         'coordinates': observation['coordinates'],
                                         'method': '3 x 3 aperture; border median background; quality-zero cadences'}
            return metadata, processed

        from astropy.io import fits
        try:
            with fits.open(path) as hdus:
                header = hdus[0].header
                actual_id = header.get('TICID') if host['mission'] == 'tess' else header.get('KEPLERID')
                if actual_id is None or str(int(actual_id)) != host['id']:
                    raise AnalysisError('FITS target does not match the selected host.', 422, 'target_mismatch')
                stellar = {key: number(header.get(field)) for field, key in
                           [('TEFF','st_teff'),('RADIUS','st_rad'),('MASS','st_mass'),('LOGG','st_logg'),('TESSMAG','st_tmag')]}
                raw = {'ID': host['id'], 'ra': number(header.get('RA_OBJ', header.get('RA'))),
                       'dec': number(header.get('DEC_OBJ', header.get('DEC')))}
                metadata = {'source': 'Observation FITS header', 'stellar': stellar, 'raw': raw}

        except (OSError, ValueError) as error:
            raise AnalysisError('Invalid FITS observation.') from error
        provenance['observation'] = {'filename': path.name, 'sha256': sha256(path.read_bytes()).hexdigest(),
                                     'author': observation.get('author'), 'group': observation.get('group_val'), 'uri': observation.get('uri')}
        stage('extracting_features')
        from src.exoplanet_processor import ExoplanetParameterProcessor
        try:
            processor = ExoplanetParameterProcessor(str(path), host['mission'], metadata.get('stellar', {}), output_dir=directory)
            processed = processor.process(print_json=False)
        except Exception as error:
            raise AnalysisError('Observation could not provide usable transit measurements.') from error
        return metadata, processed

    def _score(self, row, label, model, directory):
        invalid = []
        for feature in FEATURES[model['family']]:
            try:
                validate_features([row], (feature,))
            except ValueError:
                invalid.append(feature)
        if invalid:
            return {'id': label, 'status': 'insufficient_evidence', 'invalid_features': invalid,
                    'message': 'Required measurements are missing or invalid.'}
        if model.get('unavailable'):
            return {'id': label, 'status': 'unavailable', 'message': model['unavailable']}
        try:
            return {'id': label, 'status': 'scored', **self.models.predict_rows([row], model)[0]}
        except AnalysisError as error:
            return {'id': label, 'status': 'unavailable', 'message': str(error)}
        except Exception:
            logging.exception('Optional model scoring failed for run %s', directory.name)
            return {'id': label, 'status': 'unavailable', 'message': 'The model could not score this candidate.'}

    def __call__(self, spec, directory, stage):
        directory = Path(directory)
        mode = spec['evidence']
        model = spec['model']
        stage('resolving_target')
        host = dict(spec['target'])
        catalog = None
        sources = {}
        needs_alias = host['namespace'] in ('TOI', 'KOI')
        if mode in ('catalog', 'combined') or needs_alias:
            stage('loading_catalog')
            try:
                host, catalog = resolve_target(host)
            except AnalysisError as error:
                if mode != 'combined' or needs_alias:
                    raise
                sources['catalog'] = {'status': 'failed', 'message': str(error)}
            else:
                if mode in ('catalog', 'combined'):
                    sources['catalog'] = ({'status': 'ready'} if catalog else {'status': 'empty', 'message': 'No published candidates were listed for this target.'})
        if mode == 'catalog' and not catalog:
            raise AnalysisError('No catalog candidates for this host. Try light-curve analysis.')

        snapshot = json.dumps(clean(catalog), sort_keys=True, allow_nan=False).encode()
        if catalog is not None:
            (directory / 'catalog.json').write_bytes(snapshot)
        provenance = {'target': host, 'requested_target': spec['target'], 'evidence': mode,
                      'catalog_sha256': sha256(snapshot).hexdigest() if catalog is not None else None,
                      'catalog_source': ARCHIVE if catalog is not None else None,
                      'processing_version': PROCESSING_VERSION,
                      'model': {k: v for k, v in model.items() if k != 'path'}}
        metadata = {'raw': {}, 'stellar': {}}
        if catalog:
            stellar = catalog[0]
            metadata = {'source': 'NASA candidate catalog', 'raw': stellar,
                        'stellar': {key: value for key, value in stellar.items() if key.startswith('st_')}}

        processed = []
        if mode != 'catalog':
            try:
                metadata, processed = self._observation(spec, host, directory, stage, provenance)
            except AnalysisError as error:
                if mode != 'combined':
                    raise
                sources['observation'] = {'status': 'empty' if error.code == 'no_observation' else 'failed',
                                          'message': str(error)}
            else:
                sources['observation'] = {'status': 'ready'}

        candidates = []
        rows = []
        stage('classifying')
        if mode in ('combined', 'catalog'):
            is_tess = host['mission'] == 'tess'
            for index, raw in enumerate(catalog or []):
                row = clean(build_model_payload_from_row(host['mission'], raw).data[0])
                rows.append(row)
                label = str(raw.get('toi') or raw.get('kepoi_name') or index)
                candidate = self._score(row, label, model, directory)
                candidate['catalog_disposition'] = raw.get('tfopwg_disp') or raw.get('koi_disposition')
                candidate['measurements'] = {'period_days': raw.get('pl_orbper' if is_tess else 'koi_period'),
                                             'duration_hours': raw.get('pl_trandurh' if is_tess else 'koi_duration'),
                                             'depth_ppm': raw.get('pl_trandep' if is_tess else 'koi_depth')}
                candidates.append(candidate)
        elif processed:
            # Preserve the single-source API for callers and older workflows.
            rows = [clean(item['data'][0]) for item in processed]
            candidates = [self._score(row, f'BLS signal {index + 1}', model, directory)
                          for index, row in enumerate(rows)]

        if mode == 'combined' and host['mission'] == 'tess' and candidates:
            stage('checking_published_signal')
            from src.services.tess_vetting import check_ephemeris, followup_notes
            notes = followup_notes(host['id'], candidates)
            csv_path = directory / 'lightcurve.csv'
            time_flux = None
            if processed and csv_path.is_file():
                import numpy as np
                time_flux = np.loadtxt(csv_path, delimiter=',', skiprows=1, ndmin=2).T
            for candidate in candidates:
                if candidate['id'] in notes:
                    candidate['followup'] = notes[candidate['id']]
            for candidate, raw in zip(candidates[:3], (catalog or [])[:3]):
                if time_flux is not None:
                    try:
                        candidate['ephemeris'] = check_ephemeris(*time_flux, raw)
                    except (ValueError, ArithmeticError, RuntimeError):
                        logging.exception('Published signal check failed for run %s', directory.name)
                        candidate['ephemeris'] = {'status': 'unavailable'}

        catalog_usable = any(any(value is not None for value in row.values()) for row in rows) or any(
            any(number(value) is not None for value in candidate.get('measurements', {}).values())
            for candidate in candidates)
        has_evidence = bool(processed) or catalog_usable
        if sources.get('catalog', {}).get('status') == 'ready' and not catalog_usable:
            sources['catalog'] = {'status': 'empty', 'message': 'Catalog entries had no usable measurements.'}
        scored = sum(item['status'] == 'scored' for item in candidates)
        model_status = 'scored' if scored else 'unscored'
        if mode == 'combined':
            if not candidates:
                model_status = 'unavailable' if sources['catalog']['status'] == 'failed' else 'no_candidates'
            elif scored and scored < len(candidates):
                model_status = 'partially_scored'
            elif not scored and any(item['status'] == 'unavailable' for item in candidates):
                model_status = 'unavailable'
        evidence_record = {'metadata': metadata, 'catalog': catalog, 'features': rows, 'sources': sources,
                           'processing': [{k: v for k, v in item.items() if k != 'visualizations'} for item in processed],
                           'candidates': candidates, 'provenance': provenance}
        (directory / 'evidence.json').write_text(json.dumps(clean(evidence_record), allow_nan=False), encoding='utf-8')
        result = clean({'manual_search': metadata, 'processed_json': processed, 'candidates': candidates,
                        'sources': sources, 'provenance': provenance, 'model_status': model_status,
                        'evidence_status': 'ready' if has_evidence else 'empty',
                        'artifacts': {'photometry': (directory / 'lightcurve.csv').is_file(),
                                      'observation': sources.get('observation', {}).get('status') == 'ready', 'evidence': True}})
        if has_evidence:
            return 'succeeded', result
        return ('failed' if any(source['status'] == 'failed' for source in sources.values())
                else 'insufficient_evidence'), result
