import json
import tempfile
import unittest
from unittest.mock import patch
from main import create_app
from src.contracts import AnalysisError
from src.services.sky_service import search_targets, observation_availability

class SkyTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = create_app(self.directory.name, background=False)
        self.client = self.app.test_client()

    def tearDown(self):
        self.app.extensions['runs'].close()
        self.directory.cleanup()

    def test_invalid_region_never_reaches_archive(self):
        with patch('src.services.sky_service.search_targets') as search:
            for query in ('ra=0&dec=0&radius=.6', 'ra=nan&dec=0&radius=.2', 'ra=0&dec=91&radius=.2', 'ra=0&dec=0', 'ra=0&dec=0&radius=.2&other=1'):
                self.assertEqual(self.client.get('/sky/targets?' + query).status_code, 400)
            search.assert_not_called()

    def test_target_search_is_bounded_and_preserves_unknown_measurements(self):
        rows = [{'ID': 123, 'ra': 10, 'dec': 20, 'Tmag': None, 'Teff': None, 'objType': 'STAR'},
                {'ID': 124, 'ra': 10.1, 'dec': 20, 'Tmag': 8, 'objType': 'STAR'},
                {'ID': 123, 'ra': 10, 'dec': 20, 'objType': 'STAR'},
                {'ID': 125, 'ra': 10, 'dec': 20, 'objType': 'GALAXY'},
                {'ID': 126, 'ra': None, 'dec': 20, 'objType': 'STAR'}]
        with patch('src.services.sky_service.MastSearchService.mast_query', return_value=({}, json.dumps({'status':'COMPLETE', 'data':rows, 'paging':{'rowsFiltered': 900}}))) as query:
            result = self.client.get('/sky/targets?ra=10&dec=20&radius=.2')
        self.assertEqual(result.status_code, 200)
        self.assertEqual([row['id'] for row in result.json['targets']], ['124','123'])
        self.assertIsNone(result.json['targets'][1]['magnitude'])
        self.assertTrue(result.json['limited'])
        self.assertEqual(query.call_args.args[0]['pagesize'], 200)
        self.assertNotIn('availability', result.json['targets'][0])

    def test_catalog_outage_is_not_a_successful_empty_field(self):
        with patch('src.services.sky_service.MastSearchService.mast_query', side_effect=OSError):
            self.assertEqual(self.client.get('/sky/targets?ra=0&dec=0&radius=.2').status_code, 502)
        with patch('src.services.sky_service.MastSearchService.mast_query', return_value=({}, '{"status":"EXECUTING"}')):
            with self.assertRaises(AnalysisError):
                search_targets(0, 0, .2)

    def test_availability_is_explicit_and_an_outage_is_not_none(self):
        payload = {'status':'COMPLETE', 'data':[{'dataURL':'mast:TESS/product/test_lc.fits', 'provenance_name':'SPOC', 'sequence_number':1, 't_exptime':120}], 'paging':{'rowsFiltered':1}}
        with patch('src.services.sky_service.MastSearchService.mast_query', return_value=({}, json.dumps(payload))) as query:
            result = observation_availability('67882512')
            self.assertEqual(result['status'], 'available')
            self.assertEqual(result['count'], 1)
            names = query.call_args.args[0]['params']['filters'][0]['values']
            self.assertIn('067882512', names)
            self.assertEqual(query.call_args.kwargs['timeout'], (5,20))
        with patch('src.services.sky_service.MastSearchService.mast_query', return_value=({}, '{"status":"COMPLETE","data":[]}')):
            self.assertEqual(observation_availability('123')['status'], 'none')
        with patch('src.services.sky_service.MastSearchService.mast_query', side_effect=OSError):
            self.assertEqual(self.client.get('/sky/targets/123/observations').status_code, 502)
        self.assertEqual(self.client.get('/sky/targets/not-a-tic/observations').status_code, 400)

    def test_kepler_bundles_expand_to_individual_fits_products(self):
        from src.services.observations import lightcurve_products
        responses = [({},json.dumps({'status':'COMPLETE','data':[{'obsid':1,'dataURL':'https://archive/bundle.tar'}]})),
                     ({},json.dumps({'status':'COMPLETE','data':[
                        {'dataURI':'mast:Kepler/path/old_llc.fits','description':'Lightcurve - Q1'},
                        {'dataURI':'mast:Kepler/path/new_llc.fits','description':'Lightcurve - Q17'}]}))]
        with patch('src.services.observations.MastSearchService.mast_query', side_effect=responses) as query:
            products, limited = lightcurve_products('11446443','kepler')
            self.assertEqual(products[0]['group'],17)
            self.assertFalse(limited)
            self.assertEqual(query.call_args.args[0]['service'],'Mast.Caom.Products')

class AcquisitionTest(unittest.TestCase):
    def test_acquisition_uses_the_indexed_uri_and_publishes_complete_file(self):
        from pathlib import Path
        from src.fits_downloader import LatestFITSFetcher
        product = {'uri':'mast:TESS/product/observation_lc.fits','author':'SPOC','group':1}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def raise_for_status(self): pass
            def iter_content(self, chunk_size): return iter([b'first',b'second'])
        with tempfile.TemporaryDirectory() as root, patch('src.fits_downloader.lightcurve_products', return_value=([product],False)), patch('src.fits_downloader.requests.get', return_value=Response()) as get:
            result = LatestFITSFetcher('tess','123',root).select_or_download()
            self.assertEqual(Path(result['path']).read_bytes(), b'firstsecond')
            self.assertFalse(list(Path(root).glob('*.part')))
            self.assertEqual(get.call_args.kwargs['params'], {'uri':product['uri']})

    def test_missing_products_do_not_fall_back_to_name_resolution(self):
        from src.fits_downloader import LatestFITSFetcher
        with tempfile.TemporaryDirectory() as root, patch('src.fits_downloader.lightcurve_products', return_value=([],False)), patch('src.fits_downloader.requests.get') as get:
            with self.assertRaises(AnalysisError):
                LatestFITSFetcher('tess','123',root).select_or_download()
            get.assert_not_called()

    def test_interrupted_download_never_leaves_a_partial_observation(self):
        from pathlib import Path
        from src.fits_downloader import LatestFITSFetcher
        product = {'uri':'mast:TESS/product/observation_lc.fits','author':'SPOC','group':1}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def raise_for_status(self): pass
            def iter_content(self, chunk_size):
                yield b'partial'
                raise OSError('connection lost')
        with tempfile.TemporaryDirectory() as root, patch('src.fits_downloader.lightcurve_products', return_value=([product],False)), patch('src.fits_downloader.requests.get', return_value=Response()):
            with self.assertRaises(AnalysisError):
                LatestFITSFetcher('tess','123',root).select_or_download()
            self.assertFalse(list(Path(root).iterdir()))
