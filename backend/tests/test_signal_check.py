import tempfile
import unittest

from benchmark_signal_check import benchmark
from main import create_app


class SignalCheckTest(unittest.TestCase):
    def test_repeat_missing_noise_and_wrong_schedule_have_distinct_outcomes(self):
        outcomes = benchmark()
        self.assertEqual(outcomes['transits'], {'repeats': 30})
        self.assertEqual(outcomes['no_transits'], {'did_not_repeat': 30})
        self.assertEqual(outcomes['wrong_timing'], {'did_not_repeat': 30})
        self.assertEqual(outcomes['gaps'], {'inconclusive': 30})
        self.assertGreater(outcomes['noisy_transits'].get('inconclusive', 0), 0)

    def test_signal_check_is_a_durable_child_of_a_completed_tess_run(self):
        target = {'mission': 'tess', 'namespace': 'TIC', 'id': '142874279'}

        def pipeline(spec, directory, stage):
            if spec['evidence'] == 'signal_check':
                return 'succeeded', {'signal_check': {'status': 'inconclusive'}}
            (directory / 'lightcurve.csv').write_text('time_bjd,normalized_flux\n')
            return 'succeeded', {
                'provenance': {'target': target, 'observation': {'group': 31, 'author': 'SPOC'}},
                'manual_search': {'raw': {'ra': 51., 'dec': -33.}},
                'processed_json': [{'parameters': {'period_days': 4.57, 'midpoint_bjd': 2459147.,
                                                   'duration_hours': .48, 'depth_fraction': .0047}}],
            }

        with tempfile.TemporaryDirectory() as root:
            app = create_app(root, pipeline, background=False)
            runs = app.extensions['runs']
            try:
                client = app.test_client()
                original = runs.create({'target': target, 'evidence': 'combined', 'model': {}})['id']
                route = f'/runs/{original}/signal-check'
                self.assertEqual(client.post(route).status_code, 422)
                runs.execute(original)
                saved = runs.get(original)
                headers = {'Idempotency-Key': 'signal-check-test'}
                response = client.post(route, headers=headers)
                self.assertEqual(response.status_code, 202)
                child = response.json['id']
                self.assertEqual(client.post(route, headers=headers).json['id'], child)
                runs.execute(child)
                self.assertEqual(runs.get(child)['result']['signal_check']['status'], 'inconclusive')
                self.assertEqual(runs.get(original), saved)
            finally:
                runs.close()
