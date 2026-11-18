import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from main import create_app
from src.analysis import AnalysisPipeline, resolve_target
from src.contracts import AnalysisError, FEATURES
from src.data_mapper import build_model_payload_from_row
from src.identity import parse_target
from src.runs import RunService
from src.services.model_service import ModelService

class WorkbenchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(self.tmp.name, background=False)
        self.client = self.app.test_client()
        self.runs = self.app.extensions['runs']

    def tearDown(self):
        self.runs.close()
        self.tmp.cleanup()

    def submit(self, **kwargs):
        return self.client.post('/runs', json={'mission': 'tess', 'id': 'TIC 123', 'evidence': 'catalog', **kwargs})

    def test_day_one_missing_evidence_never_invokes_predictor(self):
        with patch('src.analysis.resolve_target', return_value=(parse_target('tess', '123'), [{'toi': 1, **dict.fromkeys(FEATURES['TOI'])}])), patch('xgboost.Booster') as predictor:
            response = self.submit()
            self.assertEqual(response.status_code, 202)
            identifier = response.json['id']
            self.runs.execute(identifier)
            record = self.client.get('/runs/' + identifier).json
            self.assertEqual(record['status'], 'insufficient_evidence')
            self.assertEqual(record['result']['candidates'][0]['status'], 'insufficient_evidence')
            self.assertNotIn('probability', record['result']['candidates'][0])
            predictor.assert_not_called()
            self.assertTrue((Path(self.tmp.name) / identifier / 'evidence.json').exists())

    def test_catalog_nulls_remain_null_and_kepler_keeps_schema(self):
        row = build_model_payload_from_row('tess', {}).to_dict()['data'][0]
        self.assertTrue(all(value is None for value in row.values()))
        inherited = build_model_payload_from_row('tess', {'eng_transit_probability': 50}).data[0]
        self.assertIsNone(inherited['eng_transit_probability'])
        row = build_model_payload_from_row('kepler', {'koi_dor': 10, 'koi_prad': 2}).data[0]
        self.assertEqual(tuple(row), FEATURES['KOI'])
        self.assertEqual(row['eng_transit_probability'], .1)
        self.assertEqual(row['koi_prad'], 2)

    def test_identifiers_are_exact_and_alias_resolves_host(self):
        for mission, value in [('tess', 'KOI-1.01'), ('kepler', 'TIC 123'), ('tess', 'junk123'), ('tess', "123 or 1=1"), ([], '123')]:
            with self.subTest(value=value), self.assertRaises(AnalysisError):
                parse_target(mission, value)
        calls = []
        def query(sql):
            calls.append(sql)
            return [{'tid': 150428135, 'toi': 700.01}, {'tid': 150428135, 'toi': 700.02}]
        host, rows = resolve_target(parse_target('tess', 'TOI-700.01'), query)
        self.assertEqual(host['id'], '150428135')
        self.assertEqual(len(rows), 2)
        self.assertIn('tid=150428135', calls[-1])

    def test_idempotency_and_invalid_requests(self):
        args = {'json': {'mission': 'tess', 'id': '123'}, 'headers': {'Idempotency-Key': 'one'}}
        first = self.client.post('/runs', **args)
        second = self.client.post('/runs', **args)
        self.assertEqual(first.json['id'], second.json['id'])
        args['json']['id'] = '124'
        self.assertEqual(self.client.post('/runs', **args).status_code, 409)
        self.assertEqual(self.submit(model_name='../other').status_code, 404)
        self.assertEqual(self.submit(evidence='bogus').status_code, 400)
        self.assertEqual(self.client.post('/runs', json=[]).status_code, 400)
        self.assertEqual(self.client.get('/search?ra=nan&dec=0').status_code, 400)
        self.assertEqual(self.client.get('/search?ra=0&dec=0&mag_min=20&mag_max=1').status_code, 400)
        self.assertEqual(self.client.post('/train-model', json={}).status_code, 405)

    def test_terminal_state_never_regresses_and_restart_is_explicit(self):
        record = self.submit().json
        self.client.post(f"/runs/{record['id']}/cancel")
        self.runs.execute(record['id'])
        self.assertFalse(self.runs.finish(record['id'], 'succeeded', {}))
        self.assertEqual(self.runs.get(record['id'])['status'], 'cancelled')
        pending = self.submit(id='124').json
        self.runs.close()
        recovered = RunService(self.tmp.name, lambda *_: None, background=False)
        self.assertEqual(recovered.get(pending['id'])['error']['code'], 'interrupted')
        self.assertEqual(recovered.get(record['id'])['status'], 'cancelled')
        recovered.close()

    def test_uploads_are_content_identified_and_do_not_reuse_filenames(self):
        data = {'spec': json.dumps({'mission': 'tess', 'id': '123', 'evidence': 'upload'}),
                'file': (io.BytesIO(b'not fits'), 'same.fits')}
        self.assertEqual(self.client.post('/runs', data=data).status_code, 400)
        ids = []
        from astropy.io import fits
        import numpy as np
        contents = []
        for value in (1., 2.):
            stream = io.BytesIO()
            fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU.from_columns([fits.Column(name='FLUX', format='D', array=np.array([value]))], name='LIGHTCURVE')]).writeto(stream)
            contents.append(stream.getvalue())
        for content in contents:
            data['file'] = (io.BytesIO(content), '../../same.fits')
            record = self.client.post('/runs', data=data).json
            ids.append(record['id'])
            self.assertEqual((Path(self.tmp.name) / record['id'] / 'observation.fits').read_bytes(), content)
        self.assertNotEqual(*ids)

    def test_upload_target_mismatch_never_extracts(self):
        from astropy.io import fits
        import numpy as np
        stream = io.BytesIO()
        primary = fits.PrimaryHDU()
        primary.header['TICID'] = 124
        fits.HDUList([primary, fits.BinTableHDU.from_columns([fits.Column(name='FLUX', format='D', array=np.array([1.]))], name='LIGHTCURVE')]).writeto(stream)
        record = self.client.post('/runs', data={'spec': json.dumps({'mission': 'tess', 'id': '123', 'evidence': 'upload'}), 'file': (io.BytesIO(stream.getvalue()), 'input.fits')}).json
        with patch('src.analysis.resolve_target', return_value=(parse_target('tess', '123'), [])), patch('src.stellar_data_fetcher.StarMetaFetcher.fetch_stellar', return_value={'stellar': {}}), patch('src.exoplanet_processor.ExoplanetParameterProcessor') as extractor:
            self.runs.execute(record['id'])
            extractor.assert_not_called()
        self.assertEqual(self.runs.get(record['id'])['error']['code'], 'target_mismatch')

    def test_multiple_candidates_and_partial_evidence(self):
        class Models:
            def predict_rows(self, rows, model):
                if rows[0]['koi_prad'] is None:
                    raise AnalysisError('missing radius')
                return [{'probability': .8, 'class': 'Candidate-like', 'prediction': 1}]
        self.runs.pipeline = AnalysisPipeline(Models())
        from src.contracts import FEATURES
        rows = [{**dict.fromkeys(FEATURES['KOI'], 2), 'kepoi_name': 'K00001.01'}, {'kepoi_name': 'K00001.02'}]
        with patch('src.analysis.resolve_target', return_value=(parse_target('kepler', '123'), rows)):
            record = self.submit(mission='kepler', id='123').json
            self.runs.execute(record['id'])
        record = self.runs.get(record['id'])
        self.assertEqual(record['status'], 'succeeded')
        self.assertEqual([r['status'] for r in record['result']['candidates']], ['scored', 'insufficient_evidence'])
        self.assertNotIn('path', record['spec']['model'])

    def test_upstream_failure_is_not_empty_catalog(self):
        with patch('src.analysis.requests.get', side_effect=__import__('requests').Timeout):
            record = self.submit().json
            self.runs.execute(record['id'])
        self.assertEqual(self.runs.get(record['id'])['error']['code'], 'upstream_unavailable')

class NativeModelTest(unittest.TestCase):
    def test_native_artifacts_and_invalid_evidence(self):
        models = ModelService()
        for family in FEATURES:
            model = models.resolve(family)
            scores = models.predict_rows([{key: 1.0 for key in FEATURES[family]}], model)
            self.assertTrue(0 <= scores[0]['probability'] <= 1)
            with self.assertRaises(AnalysisError):
                models.predict_rows([dict.fromkeys(FEATURES[family])], model)
        with self.assertRaises(AnalysisError):
            models.resolve('TOI', 'nonexistent')

    def test_impossible_measurement_never_invokes_predictor(self):
        model = ModelService().resolve('TOI')
        for feature, value in [('pl_orbper', -1), ('st_rad', 0), ('eng_transit_probability', 2)]:
            row = {key: 1.0 for key in FEATURES['TOI']}
            row[feature] = value
            with patch('xgboost.Booster') as predictor, self.assertRaises(AnalysisError):
                ModelService().predict_rows([row], model)
            predictor.assert_not_called()

    def test_pinned_artifact_cannot_change_silently(self):
        with tempfile.TemporaryDirectory() as root:
            original = ModelService().resolve('TOI')
            path = Path(root) / 'TOI/balanced_model/model.json'
            path.parent.mkdir(parents=True)
            path.write_bytes(Path(original['path']).read_bytes())
            path.with_name('manifest.json').write_bytes(Path(original['path']).with_name('manifest.json').read_bytes())
            models = ModelService(root)
            model = models.resolve('TOI')
            path.write_text('{}')
            with self.assertRaises(AnalysisError) as error:
                models.predict_rows([{key: 1.0 for key in FEATURES['TOI']}], model)
            self.assertEqual(error.exception.code, 'model_changed')

    def test_running_cancellation_discards_late_completion(self):
        entered, release = threading.Event(), threading.Event()
        def pipeline(spec, directory, stage):
            entered.set()
            release.wait(5)
            return 'succeeded', {'late': True}
        with tempfile.TemporaryDirectory() as root:
            runs = RunService(root, pipeline)
            try:
                record = runs.create({'model': {}, 'target': {}})
                self.assertTrue(entered.wait(5))
                runs.cancel(record['id'])
                release.set()
                runs.close()
                self.assertEqual(runs.get(record['id'])['status'], 'cancelled')
                self.assertIsNone(runs.get(record['id'])['result'])
            finally:
                release.set()
                runs.close()
