import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from astropy.io import fits
from astropy.time import Time
import lightkurve as lk
from src.analysis import AnalysisPipeline
from src.contracts import AnalysisError, FEATURES
from src.exoplanet_processor import ExoplanetParameterProcessor
from src.services.model_service import ModelService

class EvidenceFlowTest(unittest.TestCase):
    def test_observation_evidence_survives_catalog_outage_and_missing_model_features(self):
        models = ModelService()
        spec = {'target':{'mission':'tess','namespace':'TIC','id':'191179668'}, 'evidence':'lightcurve','model':models.resolve('TOI')}
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'source.fits'
            primary = fits.PrimaryHDU()
            primary.header['TICID'] = 191179668
            primary.header['TEFF'] = 5700
            fits.HDUList([primary]).writeto(path)
            measurements = [{'mission':'tess','data':[dict.fromkeys(FEATURES['TOI'])],
                             'visualizations':[{'type':'normalized_light_curve','data':'data:image/png;base64,AA=='}],
                             'parameters':{'period_days':3},'quality':{'exploratory_signal':False}}]
            with patch('src.analysis.resolve_target', side_effect=AnalysisError('catalog unavailable',502,'upstream_unavailable')) as catalog, patch('src.fits_downloader.LatestFITSFetcher.select_or_download', return_value={'path':str(path),'author':'SPOC','group_val':1}), patch('src.exoplanet_processor.ExoplanetParameterProcessor.process', return_value=measurements):
                status, result = AnalysisPipeline(models)(spec, root, lambda stage: None)
            catalog.assert_not_called()
            self.assertEqual(status,'succeeded')
            self.assertEqual(len(result['processed_json'][0]['visualizations']),1)
            self.assertEqual(result['candidates'][0]['status'],'insufficient_evidence')
            self.assertEqual(result['manual_search']['stellar']['st_teff'],5700)

    def test_combined_run_keeps_each_source_and_scores_only_catalog_rows(self):
        import csv
        from main import create_app
        from src.services.model_service import ROOT
        with (ROOT / 'src/utils/datasets/TOI.csv').open(newline='') as source:
            candidate = next(csv.DictReader(source))
        host = {'mission': 'tess', 'namespace': 'TIC', 'id': candidate['tid']}
        incomplete = {**candidate, 'toi': 'missing', 'st_loggerr2': None}
        measurements = [{'visualizations': [{'type': 'normalized_light_curve', 'data': 'plot'}]}]
        catalog_error = AnalysisError('Catalog timed out.', 502, 'upstream_unavailable')
        no_observation = AnalysisError('No observed light curve.', 422, 'no_observation')
        cases = [
            ((host, [candidate, incomplete]), ({'raw': {}}, measurements), 'succeeded', 'ready', 'ready', 'partially_scored'),
            ((host, [candidate, incomplete]), no_observation, 'succeeded', 'ready', 'empty', 'partially_scored'),
            (catalog_error, ({'raw': {}}, measurements), 'succeeded', 'failed', 'ready', 'unavailable'),
            (catalog_error, no_observation, 'failed', 'failed', 'empty', 'unavailable'),
            ((host, []), no_observation, 'insufficient_evidence', 'empty', 'empty', 'no_candidates'),
        ]
        with tempfile.TemporaryDirectory() as root:
            app = create_app(root, background=False)
            runs = app.extensions['runs']
            self.addCleanup(runs.close)
            client = app.test_client()
            for catalog, obs, status, catalog_state, obs_state, model_state in cases:
                with self.subTest(catalog=catalog_state, observation=obs_state):
                    accepted = client.post('/runs', json={'mission': 'tess', 'id': host['id'], 'evidence': 'combined'})
                    self.assertEqual(accepted.status_code, 202)
                    identifier = accepted.json['id']
                    with patch('src.analysis.resolve_target', side_effect=[catalog]), patch.object(AnalysisPipeline, '_observation', side_effect=[obs]), patch('src.services.tess_vetting.followup_notes', return_value={'status':'empty', 'notes':{}}):
                        runs.execute(identifier)
                    record = client.get(f'/runs/{identifier}').json
                    self.assertEqual(record['status'], status)
                    result = record['result']
                    self.assertEqual(result['sources']['catalog']['status'], catalog_state)
                    self.assertEqual(result['sources']['observation']['status'], obs_state)
                    self.assertEqual(result['model_status'], model_state)
                    if model_state == 'partially_scored':
                        self.assertEqual(len(result['candidates']), 2)
                        self.assertIn('probability', result['candidates'][0])
                        self.assertEqual(result['candidates'][1]['invalid_features'], ['st_loggerr2'])
                    else:
                        self.assertEqual(result['candidates'], [])
            runs.close()

    def test_short_observation_still_returns_photometry_and_a_plot(self):
        time = np.linspace(0,.7,200)
        curve = lk.LightCurve(time=Time(2457000+time,format='jd'), flux=1+np.random.default_rng(1).normal(0,.001,len(time)))
        with tempfile.TemporaryDirectory() as root, patch('src.exoplanet_processor.lk.read',return_value=curve):
            result = ExoplanetParameterProcessor(Path(root)/'observation.fits','tess',{}).process()[0]
            self.assertGreaterEqual(len(result['visualizations']),1)
            self.assertEqual(result['quality']['search_status'],'insufficient_coverage')
            self.assertTrue((Path(root)/'lightcurve.csv').exists())

    def test_observation_listing_is_shared_between_preview_and_acquisition(self):
        from src.services.observations import ObservationIndex
        listing = ([{'uri':'mast:TESS/product/data_lc.fits','author':'SPOC','group':1}],False)
        index = ObservationIndex()
        with patch('src.services.observations.lightcurve_products',return_value=listing) as query:
            self.assertEqual(index.get('191179668','tess'),listing)
            self.assertEqual(index.get('191179668','tess'),listing)
            query.assert_called_once()

    def test_failed_listing_is_not_cached_as_no_data(self):
        from src.services.observations import ObservationIndex
        index = ObservationIndex()
        with patch('src.services.observations.lightcurve_products',side_effect=[AnalysisError('timeout',502,'upstream_unavailable'),([],False)]) as query:
            with self.assertRaises(AnalysisError): index.get('123','tess')
            self.assertEqual(index.get('123','tess'),([],False))
            self.assertEqual(query.call_count,2)

    def test_transient_transport_failure_gets_one_retry(self):
        import requests
        from src.services.mast_search_service import MastSearchService
        class Response:
            headers = {}
            content = b'{"status":"COMPLETE","data":[]}'
            def raise_for_status(self): pass
        with patch('src.services.mast_search_service.requests.post',side_effect=[requests.Timeout(),Response()]) as post, patch('time.sleep'):
            self.assertIn('COMPLETE',MastSearchService().mast_query({'service':'test'})[1])
            self.assertEqual(post.call_count,2)

    def test_saved_evidence_files_are_downloadable_without_leaking_paths(self):
        from main import create_app
        with tempfile.TemporaryDirectory() as root:
            app = create_app(root,background=False)
            client = app.test_client()
            record = client.post('/runs',json={'mission':'tess','id':'191179668','evidence':'lightcurve'}).json
            directory = Path(root)/record['id']
            (directory/'lightcurve.csv').write_text('time_bjd,normalized_flux\n2457000,1.0\n')
            response = client.get(f"/runs/{record['id']}/artifacts/photometry")
            self.assertEqual(response.status_code,200)
            self.assertIn('normalized_flux',response.text)
            self.assertIn('attachment',response.headers['Content-Disposition'])
            response.close()
            self.assertEqual(client.get(f"/runs/{record['id']}/artifacts/unknown").status_code,404)
            self.assertNotIn('path',client.get('/runs').text)
            app.extensions['runs'].close()

    def test_unexpected_optional_model_failure_cannot_discard_photometry(self):
        models = ModelService()
        spec = {'target':{'mission':'tess','namespace':'TIC','id':'123'},'evidence':'upload','model':models.resolve('TOI')}
        with tempfile.TemporaryDirectory() as root:
            primary = fits.PrimaryHDU()
            primary.header['TICID'] = 123
            primary.writeto(Path(root)/'observation.fits')
            features = dict.fromkeys(FEATURES['TOI'], 1)
            measurements = [{'data':[features],'visualizations':[{'type':'normalized_light_curve','data':'data:image/png;base64,AA=='}]}]
            with patch('src.exoplanet_processor.ExoplanetParameterProcessor.process',return_value=measurements), patch.object(models,'predict_rows',side_effect=RuntimeError('model unavailable')), self.assertLogs(level='ERROR'):
                status, result = AnalysisPipeline(models)(spec,root,lambda stage:None)
            self.assertEqual(status,'succeeded')
            self.assertEqual(result['candidates'][0]['status'],'unavailable')
            self.assertTrue(result['processed_json'][0]['visualizations'])
