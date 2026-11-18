import unittest
from src.validation import validate_features

class EvidenceTest(unittest.TestCase):
    def test_unavailable_evidence_never_becomes_a_score(self):
        for value in (None, float('nan'), float('inf'), 'bad', True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_features([{'period': value}], ['period'])
        validate_features([{'period': 0.0}], ['period'])

    def test_bad_container_and_missing_feature(self):
        for rows in (None, [], {}, [None], [{}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                validate_features(rows, ['period'])
