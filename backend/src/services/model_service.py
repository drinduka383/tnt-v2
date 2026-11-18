"""Inference from native artifacts only: no pickle or silent fallback."""
from hashlib import sha256
from pathlib import Path
import json
import re
import numpy as np
from src.contracts import FEATURES, SCHEMA_VERSION, UNITS, AnalysisError
from src.validation import validate_features
ROOT = Path(__file__).resolve().parents[2]

class ModelService:
    def __init__(self, root=None, custom_root=None):
        self.root = Path(root or ROOT / 'models')
        self.custom_root = Path(custom_root or ROOT / 'training-output')

    def resolve(self, family, name=None):
        if family not in FEATURES or not isinstance(name, (str, type(None))):
            raise AnalysisError('Unknown model.', 404, 'model_not_found')
        metadata = {'threshold': 0.5}
        if name in (None, 'balanced'):
            name = 'balanced'
            path = self.root / family / 'balanced_model/model.json'
            manifest = path.with_name('manifest.json')
            if not manifest.is_file():
                raise AnalysisError('Baseline manifest unavailable.', 503, 'model_unavailable')
            metadata = json.loads(manifest.read_text(encoding='utf-8'))
        else:
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', name):
                raise AnalysisError('Invalid model identifier.', 404, 'model_not_found')
            path = self.custom_root / name / 'model.json'
            manifest = path.with_name('manifest.json')
            if not manifest.is_file():
                raise AnalysisError('Model not found. No fallback was selected.', 404, 'model_not_found')
            metadata = json.loads(manifest.read_text(encoding='utf-8'))
            if metadata.get('family') != family or metadata.get('schema') != SCHEMA_VERSION:
                raise AnalysisError('Model family or schema is incompatible.', 422, 'model_incompatible')
        if not path.is_file():
            raise AnalysisError('Model artifact is unavailable.', 503, 'model_unavailable')
        content = path.read_bytes()
        learner = json.loads(content)['learner']
        if learner['objective']['name'] != 'binary:logistic' or tuple(learner['feature_names']) != FEATURES[family]:
            raise AnalysisError('Model output or schema is incompatible.', 503, 'model_incompatible')
        digest = sha256(content).hexdigest()
        if metadata.get('family') != family or metadata.get('schema') != SCHEMA_VERSION or metadata.get('units') != UNITS[family]:
            raise AnalysisError('Model schema is incompatible.', 503, 'model_incompatible')
        if metadata.get('sha256') != digest:
            raise AnalysisError('Model checksum does not match its manifest.', 503, 'model_incompatible')
        threshold = metadata['threshold']
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
            raise AnalysisError('Invalid model threshold.', 503, 'model_incompatible')
        manifest_digest = sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()
        return {'id': f'{family.lower()}-{name}-{digest}-{manifest_digest}', 'sha256': digest, 'manifest_sha256': manifest_digest,
                'family': family, 'name': name, 'threshold': threshold,
                'schema': SCHEMA_VERSION, 'output': 'planet_class_score', 'iteration_end': int(learner.get('attributes', {}).get('best_iteration', -1)) + 1, 'path': str(path)}

    def predict_rows(self, rows, model):
        features = FEATURES[model['family']]
        try:
            validate_features(rows, features)
        except ValueError as error:
            raise AnalysisError(str(error)) from error
        content = Path(model['path']).read_bytes()
        if sha256(content).hexdigest() != model['sha256']:
            raise AnalysisError('Pinned model changed; start a new run.', 409, 'model_changed')
        import xgboost as xgb
        booster = xgb.Booster()
        booster.load_model(bytearray(content))
        matrix = np.array([[row[f] for f in features] for row in rows], dtype=float)
        scores = booster.predict(xgb.DMatrix(matrix, feature_names=list(features)), iteration_range=(0, model.get('iteration_end', 0)))
        if len(scores) != len(rows) or not np.isfinite(scores).all() or ((scores < 0) | (scores > 1)).any():
            raise AnalysisError('Model returned invalid scores.', 503, 'model_incompatible')
        return [{'probability': float(score), 'prediction': int(score >= model['threshold']),
                 'class': 'Candidate-like' if score >= model['threshold'] else 'False-positive-like'} for score in scores]
