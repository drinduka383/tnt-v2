import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from astropy.time import Time
import lightkurve as lk
from train import partition, train, prepare_dataset
import json
from src.contracts import FEATURES
from src.data_mapper import build_model_payload_from_row
from src.exoplanet_processor import ExoplanetParameterProcessor
from src.services.model_service import ModelService, ROOT

class ScienceContractTest(unittest.TestCase):
    def test_host_partitions_are_disjoint_with_multiple_candidates(self):
        frame = pd.DataFrame([{'host': host, 'target': host % 2} for host in range(200) for candidate in range(3)])
        parts = partition(frame, 'host')
        sets = [set(part.host) for part in parts]
        self.assertFalse(sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])
        self.assertEqual(sum(len(part) for part in parts), len(frame))

    def test_training_and_inference_use_identical_feature_adapter(self):
        for family, mission in [('TOI', 'tess'), ('KOI', 'kepler')]:
            source = pd.read_csv(ROOT / 'src/utils/datasets' / f'{family}.csv')
            raw = source.dropna(subset=list(FEATURES[family])).iloc[0].to_dict()
            features = build_model_payload_from_row(mission, raw).data[0]
            self.assertTrue(0 <= features['eng_transit_probability'] <= 1)
            model = ModelService().resolve(family)
            self.assertEqual(model['schema'], 'catalog-shared-signed-v2')
            self.assertEqual(len(ModelService().predict_rows([features], model)), 1)

    def test_offline_training_publishes_complete_selectable_native_artifact(self):
        with tempfile.TemporaryDirectory() as output:
            source = ROOT / 'src/utils/datasets/TOI.csv'
            name = train('TOI', output_root=output, rounds=5, dataset=source)
            model = ModelService(custom_root=output).resolve('TOI', name)
            self.assertEqual(model['name'], name)
            manifest = json.loads((Path(output) / name / 'manifest.json').read_text())
            self.assertEqual(manifest['configuration']['n_estimators'], 5)
            self.assertIn('xgboost', manifest['versions'])
            self.assertGreaterEqual(manifest['eligibility']['excluded_rows'], 0)
            frame, _, _, counts = prepare_dataset('TOI', source)
            self.assertEqual(counts['eligible_rows'], len(frame))
            self.assertEqual(counts['source_rows'], counts['eligible_rows'] + counts['excluded_rows'])
            self.assertEqual(len(ModelService(custom_root=output).predict_rows(frame.head(2).to_dict('records'), model)), 2)
            self.assertTrue((Path(output) / name / 'manifest.json').is_file())
            self.assertFalse(any(path.is_file() for path in Path(output).iterdir()))

    def test_synthetic_transit_keeps_unmeasured_uncertainties_missing(self):
        random = np.random.default_rng(42)
        time = np.arange(0, 27, .02)
        in_transit = np.abs((time - 1.5 + 1.5) % 3 - 1.5) < .06
        flux = 1 - .01 * in_transit + random.normal(0, .0005, len(time))
        curve = lk.LightCurve(time=Time(2457000 + time, format='jd'), flux=flux)
        with tempfile.TemporaryDirectory() as root, patch('src.exoplanet_processor.lk.read', return_value=curve):
            result = ExoplanetParameterProcessor(Path(root)/'test.fits', 'tess', {}).process()[0]
        self.assertAlmostEqual(result['parameters']['period_days'], 3, delta=.03)
        self.assertTrue(result['quality']['exploratory_signal'])
        self.assertIsNone(result['data'][0]['pl_orbpererr1'])
        self.assertEqual(len(result['visualizations']), 2)
