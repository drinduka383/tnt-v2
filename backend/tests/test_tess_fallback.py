from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from astropy.io import fits
from astropy.wcs import WCS
import numpy as np

from src.analysis import AnalysisPipeline
from src.contracts import AnalysisError
from src.services.model_service import ModelService
from src.services.tess_vetting import check_ephemeris, followup_notes


class TessFallbackTest(unittest.TestCase):
    def test_empty_prepared_index_extracts_background_subtracted_cutout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'tesscut.fits'
            primary = fits.PrimaryHDU()
            primary.header['SECTOR'] = 31
            pixels = np.full((4, 7, 7), 50., dtype=np.float32)
            pixels[:, 3, 3] += [100, 90, 110, 5]
            table = fits.BinTableHDU.from_columns([
                fits.Column(name='TIME', format='D', array=[100, 101, 102, 103]),
                fits.Column(name='QUALITY', format='J', array=[0, 0, 0, 1]),
                fits.Column(name='FLUX', format='49E', dim='(7,7)', array=pixels),
            ], name='PIXELS')
            table.header.update(TIMESYS='TDB', BJDREFI=2457000, BJDREFF=0.)
            wcs = WCS(naxis=2)
            wcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
            wcs.wcs.crpix = [4, 4]
            wcs.wcs.crval = [51, -33]
            wcs.wcs.cdelt = [-.006, .006]
            aperture = fits.ImageHDU(np.zeros((7, 7)), header=wcs.to_header(), name='APERTURE')
            fits.HDUList([primary, table, aperture]).writeto(path)
            observation = {'path': str(path), 'coordinates': {'ra': 51, 'dec': -33},
                           'tic': {'Teff': 4600}, 'author': 'MAST TESScut', 'group_val': 31, 'uri': 'test cutout'}
            host = {'mission': 'tess', 'namespace': 'TIC', 'id': '123'}
            models = ModelService()
            spec = {'target': host, 'evidence': 'combined', 'model': models.resolve('TOI')}
            with patch('src.analysis.resolve_target', return_value=(host, [])), patch(
                    'src.fits_downloader.LatestFITSFetcher.select_or_download',
                    side_effect=AnalysisError('no prepared light curve', 422, 'no_observation')), patch(
                    'src.services.tess_pixels.download_cutout', return_value=observation) as fallback:
                status, result = AnalysisPipeline(models)(spec, root, lambda _: None)
            fallback.assert_called_once()
            self.assertEqual(status, 'succeeded')
            self.assertEqual(result['provenance']['observation']['kind'], 'pixel_cutout')
            self.assertEqual(result['sources']['observation']['status'], 'ready')
            self.assertEqual(result['processed_json'][0]['photometry']['samples'], 3)
            np.testing.assert_allclose(np.loadtxt(root/'lightcurve.csv', delimiter=',', skiprows=1)[:, 1], [1, .9, 1.1])

    def test_known_ephemeris_checks_both_windows_without_moving_the_epoch(self):
        epoch = 2459000.
        t = epoch + np.arange(-.5, 9., .002)
        phase = (t - epoch + 1) % 2 - 1
        flux = 1. + .0001 * (t - epoch) - .002 * (np.abs(phase) < .04)
        result = check_ephemeris(t, flux, {'pl_tranmid': epoch, 'pl_orbper': 2, 'pl_trandurh': 2})
        self.assertEqual(result['status'], 'measured')
        self.assertEqual(result['primary']['events'], 5)
        self.assertAlmostEqual(result['primary']['depth_ppm'], 2000., delta=5.)
        self.assertAlmostEqual(result['half_period']['depth_ppm'], 0., delta=1.)

    def test_followup_comment_is_joined_by_both_candidate_and_host(self):
        data = (b'TIC ID,TOI,TFOPWG Disposition,Comments\n'
                b'124,1000.01,CP,another target\n123,1000.01,FP,retired as NEB\n')
        with patch('src.services.tess_vetting.requests.get') as get:
            get.return_value.__enter__.return_value.iter_content.return_value = [data]
            result = followup_notes('123', [{'id': '1000.01'}, {'id': '1000.02'}])
        self.assertEqual(set(result), {'1000.01'})
        self.assertEqual(result['1000.01']['comment'], 'retired as NEB')
