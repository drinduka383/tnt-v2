"""Local analysis API. Run one waitress process per data directory."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json
import math
import os
import re
from flask import Flask, request, jsonify, send_file
from werkzeug.exceptions import HTTPException
from src.contracts import AnalysisError, MODEL_FAMILY
from src.identity import parse_target
from src.runs import RunService
from src.analysis import AnalysisPipeline, clean
from src.services.model_service import ModelService

ROOT = Path(__file__).resolve().parent

def create_app(data_dir=None, pipeline=None, background=True):
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024
    models = ModelService()
    from src.services.observations import ObservationIndex
    observation_index = ObservationIndex()
    runs = RunService(data_dir or os.getenv('TNT_DATA_DIR', ROOT / 'data'), pipeline or AnalysisPipeline(models, observation_index), background)
    app.extensions['runs'] = runs

    @app.errorhandler(AnalysisError)
    def analysis_error(error):
        return jsonify({'code': error.code, 'message': str(error)}), error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify({'code': error.name, 'message': error.description}), error.code

    @app.errorhandler(Exception)
    def unexpected_error(error):
        app.logger.exception('API operation failed')
        return jsonify({'code': 'internal_error', 'message': 'Operation failed. See the server log.'}), 500

    @app.get('/health')
    def health():
        return jsonify({'status': 'ok'})

    @app.get('/models')
    def model_list():
        return jsonify([{k: v for k, v in models.resolve(family).items() if k != 'path'} for family in MODEL_FAMILY.values()])

    @app.get('/runs')
    def recent_runs():
        return jsonify(runs.recent())

    @app.post('/runs')
    def submit():
        upload = None
        if request.mimetype == 'multipart/form-data':
            try:
                data = json.loads(request.form.get('spec', '{}'))
            except ValueError as error:
                raise AnalysisError('Invalid analysis specification.', 400, 'invalid_request') from error
            file = request.files.get('file')
            if file is None:
                raise AnalysisError('FITS file is required.', 400, 'invalid_request')
            upload = file.read()
            if not upload.startswith(b'SIMPLE  ='):
                raise AnalysisError('Only FITS observations are supported.', 400, 'invalid_request')
            from astropy.io import fits
            try:
                with fits.open(BytesIO(upload)) as hdus:
                    hdus.verify('exception')
                    if not any(hdu.name in ('LIGHTCURVE', 'PIXELS', 'TARGETTABLES') for hdu in hdus):
                        raise ValueError('No supported observation extension')
            except Exception as error:
                raise AnalysisError('Invalid FITS observation.', 400, 'invalid_request') from error
        else:
            data = request.get_json()
        if not isinstance(data, dict) or set(data) - {'mission', 'id', 'evidence', 'model_name'}:
            raise AnalysisError('Invalid analysis fields.', 400, 'invalid_request')
        target = parse_target(data.get('mission'), data.get('id'))
        evidence = data.get('evidence', 'catalog')
        if evidence not in ('combined', 'catalog', 'lightcurve', 'upload') or (evidence == 'upload') != (upload is not None):
            raise AnalysisError('Choose combined, catalog, lightcurve, or upload with a FITS file.', 400, 'invalid_request')
        family = MODEL_FAMILY[target['mission']]
        name = data.get('model_name')
        try:
            model = models.resolve(family, name)
        except AnalysisError as error:
            if evidence != 'combined' or name not in (None, 'balanced') or error.status != 503:
                raise
            model = {'family': family, 'name': 'balanced', 'unavailable': str(error)}
        spec = {'target': target, 'evidence': evidence, 'model': model}
        if upload is not None:
            spec['upload_sha256'] = sha256(upload).hexdigest()
        key = request.headers.get('Idempotency-Key')
        if key is not None and not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', key):
            raise AnalysisError('Invalid Idempotency-Key.', 400, 'invalid_request')
        record = runs.create(spec, key, upload)
        return jsonify(record), 202 if record['status'] in ('accepted', 'running') else 200

    @app.post('/runs/<identifier>/signal-check')
    def signal_check(identifier):
        parent = runs.get(identifier)
        result = parent['result'] or {}
        target = result.get('provenance', {}).get('target') or {}
        observation = result.get('provenance', {}).get('observation', {})
        coords = result.get('manual_search', {}).get('raw', {})
        processed = result.get('processed_json') or [{}]
        fit = processed[0].get('parameters', {})
        from src.data_mapper import number
        ra, dec, period, epoch, hours, depth = map(number, [coords.get('ra'), coords.get('dec'),
            fit.get('period_days'), fit.get('midpoint_bjd'), fit.get('duration_hours'), fit.get('depth_fraction')])
        sector = observation.get('group')
        if (parent['status'] != 'succeeded' or target.get('namespace') != 'TIC' or
                not isinstance(sector, int) or None in (ra, dec, period, epoch, hours, depth) or
                not (0 <= ra < 360 and -90 <= dec <= 90 and .5 <= period <= 20 and
                     2400000 <= epoch <= 2600000 and 0 < hours < 24 * period / 6 and 0 < depth < 1) or
                not (runs.root / identifier / 'lightcurve.csv').is_file()):
            raise AnalysisError('This run has no saved TESS timing and sector to check.', 422, 'signal_check_unavailable')
        key = request.headers.get('Idempotency-Key')
        if key is not None and not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', key):
            raise AnalysisError('Invalid Idempotency-Key.', 400, 'invalid_request')
        published = [{'id': row['id'], 'disposition': row['catalog_disposition'],
                      'followup': row.get('followup')} for row in result.get('candidates', [])
                     if row.get('catalog_disposition')]
        record = runs.create({'target': target, 'evidence': 'signal_check', 'model': {}, 'parent_run': identifier,
                              'published_context': published,
                              'coordinates': {'ra': ra, 'dec': dec}, 'sector': sector, 'author': observation.get('author'), 'period': period,
                              'epoch': epoch, 'duration': hours / 24, 'depth': depth}, key)
        return jsonify(record), 202 if record['status'] in ('accepted', 'running') else 200

    @app.get('/runs/<identifier>')
    def run_status(identifier):
        return jsonify(runs.get(identifier))

    @app.get('/runs/<identifier>/artifacts/<kind>')
    def artifact(identifier, kind):
        runs.get(identifier)
        directory = runs.root / identifier
        if kind == 'observation':
            paths = [directory / 'observation.fits', *sorted((directory / 'downloads').glob('*.fits')), *sorted((directory / 'downloads').glob('*.fits.gz'))]
            path = next((candidate for candidate in paths if candidate.is_file()), None)
        else:
            name = {'photometry': 'lightcurve.csv', 'evidence': 'evidence.json'}.get(kind)
            path = directory / name if name else None
        if path is None or not path.is_file() or not path.resolve().is_relative_to(directory.resolve()):
            raise AnalysisError('This evidence file is not available.', 404, 'not_found')
        return send_file(path, as_attachment=True, download_name=path.name)

    @app.get('/runs/<identifier>/signal-comparison.<extension>')
    def signal_comparison(identifier, extension):
        if extension not in {'json', 'png'}:
            raise AnalysisError('Unknown comparison format.', 404, 'not_found')
        run = runs.get(identifier)
        spec = run['spec']
        check = (run['result'] or {}).get('signal_check', {})
        sector = check.get('independent_sector')
        if run['status'] != 'succeeded' or spec.get('evidence') != 'signal_check' or not check.get('independent_source'):
            raise AnalysisError('No independent observation was saved for this check.', 404, 'not_found')
        parent = runs.get(spec['parent_run'])
        original = runs.root / parent['id'] / 'lightcurve.csv'
        directory = runs.root / identifier / 'downloads'
        paths = [*directory.glob('*.fits'), *directory.glob('*.fits.gz')]
        if (not original.is_file() or not original.resolve().is_relative_to(original.parent.resolve())
                or len(paths) != 1 or not paths[0].resolve().is_relative_to(directory.resolve())):
            raise AnalysisError('The saved comparison measurements are unavailable.', 404, 'not_found')
        from src.services.signal_comparison import comparison_figure, comparison_samples
        try:
            samples, half, window = comparison_samples(original, paths[0], spec, sector)
            if extension == 'json':
                response = jsonify(window_hours=window, duration_hours=2 * half, series=[
                    {'sector': group, 'hours': phase.tolist(), 'brightness_change_percent': brightness.tolist()}
                    for group, (phase, brightness) in zip((spec['sector'], sector), samples)
                ])
                response.cache_control.max_age = 3600
                return response
            image = comparison_figure(samples, half, window, spec['sector'], sector)
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise AnalysisError('The saved observations cannot be plotted together.', 422, 'comparison_unavailable') from error
        return send_file(image, mimetype='image/png', max_age=3600)

    @app.post('/runs/<identifier>/cancel')
    def cancel(identifier):
        return jsonify(runs.cancel(identifier))

    @app.post('/train-model')
    def training():
        raise AnalysisError('Training is an offline operation: use train.py. Analysis cannot overwrite model artifacts.', 405, 'offline_only')

    @app.get('/sky/targets')
    def sky_targets():
        from src.services.sky_service import search_targets, MAX_RADIUS
        if set(request.args) != {'ra', 'dec', 'radius'}:
            raise AnalysisError('Supply ra, dec and radius in degrees.', 400, 'invalid_request')
        values = {}
        for name, lo, hi in [('ra', 0, 360), ('dec', -90, 90), ('radius', .001, MAX_RADIUS)]:
            try:
                value = float(request.args[name])
            except ValueError as error:
                raise AnalysisError('Sky coordinates must be numbers.', 400, 'invalid_request') from error
            if not math.isfinite(value) or not lo <= value <= hi:
                raise AnalysisError(f'{name} must be between {lo} and {hi} degrees.', 400, 'invalid_request')
            values[name] = value
        return jsonify(search_targets(**values))

    @app.get('/sky/targets/<identifier>/observations')
    def sky_observations(identifier):
        from src.services.sky_service import observation_availability
        return jsonify(observation_availability(identifier, observation_index))

    @app.get('/search')
    def search():
        bounds = {'ra': (0, 360, None), 'dec': (-90, 90, None), 'radius': (0.01, 30, 15),
                  'mag_min': (-30, 30, 6), 'mag_max': (-30, 30, 15),
                  'temp_min': (0, 100000, 3000), 'temp_max': (0, 100000, 7500),
                  'dist_min': (0, 1000000, 10), 'dist_max': (0, 1000000, 500)}
        values = {}
        for name, (lo, hi, default) in bounds.items():
            try:
                value = float(request.args.get(name, default))
            except (TypeError, ValueError) as error:
                raise AnalysisError(f'{name} must be a number.', 400, 'invalid_request') from error
            if not math.isfinite(value) or not lo <= value <= hi:
                raise AnalysisError(f'{name} is outside the permitted range.', 400, 'invalid_request')
            values[name] = value
        if any(values[f'{key}_min'] > values[f'{key}_max'] for key in ('mag', 'temp', 'dist')):
            raise AnalysisError('Minimum filters must not exceed maximums.', 400, 'invalid_request')
        if set(request.args) - set(bounds):
            raise AnalysisError('Unsupported search filter.', 400, 'invalid_request')
        from src.services.mast_search_service import MastSearchService
        result = MastSearchService().search_stars_with_filters(**values)
        if result.get('status') != 'success':
            raise AnalysisError('MAST search is unavailable.', 502, 'upstream_unavailable')
        return jsonify(clean(result))

    return app

if __name__ == '__main__':
    from waitress import serve
    app = create_app()
    try:
        serve(app, host=os.getenv('TNT_HOST', '127.0.0.1'), port=5000, threads=4)
    finally:
        app.extensions['runs'].close()
