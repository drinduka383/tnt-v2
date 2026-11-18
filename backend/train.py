"""Offline candidate training. Artifacts publish once into a new immutable directory."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import uuid
import platform
from importlib.metadata import version
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
from xgboost import XGBClassifier
from src.contracts import FEATURES, SCHEMA_VERSION, UNITS
from src.data_mapper import build_model_payload_from_row
from src.validation import validate_features
from src.services.model_service import ROOT


def partition(frame, host_column):
    if frame[host_column].isna().any():
        raise ValueError('Every training row needs a host identifier')
    split = GroupShuffleSplit(n_splits=1, test_size=.3, random_state=42)
    train, rest = next(split.split(frame, groups=frame[host_column]))
    remaining = frame.iloc[rest]
    validation, test = next(GroupShuffleSplit(n_splits=1, test_size=.5, random_state=43).split(remaining, groups=remaining[host_column]))
    parts = [frame.iloc[train], remaining.iloc[validation], remaining.iloc[test]]
    for part in parts:
        if part['target'].nunique() != 2:
            raise ValueError('Each host-isolated partition must contain both classes; supply more independent hosts')
    return parts


def prepare_dataset(family, source):
    frame = pd.read_csv(source)
    source_rows = len(frame)
    host = 'tid' if family == 'TOI' else 'kepid'
    disposition = 'tfopwg_disp' if family == 'TOI' else 'koi_disposition'
    mapping = {'CP': 1, 'KP': 1, 'FP': 0} if family == 'TOI' else {'CONFIRMED': 1, 'CANDIDATE': 1, 'FALSE POSITIVE': 0}
    frame['target'] = frame[disposition].map(mapping)
    columns = list(FEATURES[family])
    mission = 'tess' if family == 'TOI' else 'kepler'
    adapted = pd.DataFrame([build_model_payload_from_row(mission, row).data[0] for row in frame.to_dict('records')], index=frame.index)
    frame[columns] = adapted[columns]
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=[*columns, host, 'target'])
    def valid(row):
        try:
            validate_features([row], FEATURES[family])
            return True
        except ValueError:
            return False
    frame = frame.loc[[valid(row) for row in frame.to_dict('records')]]
    return frame, host, mapping, {'source_rows': source_rows, 'eligible_rows': len(frame), 'excluded_rows': source_rows - len(frame)}


def fit_classifier(training, validation, columns, rounds=200):
    model = XGBClassifier(n_estimators=rounds, max_depth=4, learning_rate=.1,
                          objective='binary:logistic', random_state=42, n_jobs=2,
                          eval_metric='logloss', early_stopping_rounds=15)
    model.fit(training[columns], training.target, eval_set=[(validation[columns], validation.target)], verbose=False)
    return model


def train(family, output_root=None, rounds=200, dataset=None):
    if family not in FEATURES or isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 1:
        raise ValueError('Supply TOI or KOI and a positive integer number of rounds')
    source = Path(dataset) if dataset else ROOT / 'src/utils/datasets' / f'{family}.csv'
    frame, host, mapping, eligibility = prepare_dataset(family, source)
    columns = list(FEATURES[family])
    training, validation, test = partition(frame, host)
    model = fit_classifier(training, validation, columns, rounds)
    evaluations = {}
    for name, part in [('validation', validation), ('test', test)]:
        scores = model.predict_proba(part[columns])[:, 1]
        predictions = scores >= .5
        evaluations[name] = {'rows': len(part), 'hosts': int(part[host].nunique()),
                             'accuracy': accuracy_score(part.target, predictions),
                             'precision': precision_score(part.target, predictions, zero_division=0),
                             'recall': recall_score(part.target, predictions, zero_division=0),
                             'roc_auc': roc_auc_score(part.target, scores)}
    output = Path(output_root or ROOT / 'training-output')
    output.mkdir(parents=True, exist_ok=True)
    identifier = f'{family.lower()}-{uuid.uuid4().hex}'
    with tempfile.TemporaryDirectory(dir=output) as staging:
        staging = Path(staging)
        path = staging / 'model.json'
        model.save_model(path)
        manifest = {'family': family, 'schema': SCHEMA_VERSION, 'threshold': .5,
                    'sha256': sha256(path.read_bytes()).hexdigest(), 'features': columns, 'units': UNITS[family],
                    'preprocessing': 'shared catalog adapter; signed catalog uncertainties; geometric R-star/a',
                    'dataset_sha256': sha256(source.read_bytes()).hexdigest(), 'labels': mapping,
                    'split': 'host-isolated 70/15/15; no resampling', 'evaluation': evaluations,
                    'training_rows': len(training), 'best_iteration': model.best_iteration,
                    'eligibility': eligibility,
                    'configuration': {key: value for key, value in model.get_params().items() if value is not None and not (isinstance(value, float) and np.isnan(value))},
                    'versions': {'python': platform.python_version(), **{name: version(name) for name in ['numpy', 'pandas', 'scikit-learn', 'xgboost']}},
                    'scientific_validation': 'not independently validated'}
        (staging / 'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding='utf-8')
        # Rename a complete directory; no inference path ever sees a partial artifact.
        staging.rename(output / identifier)
    return identifier

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('family', choices=FEATURES)
    parser.add_argument('--dataset', type=Path, help='Updated mission catalog CSV; defaults to bundled snapshot')
    parser.add_argument('--output', type=Path, help='New artifact directory root; never replaces a baseline')
    parser.add_argument('--rounds', type=int, default=200)
    args = parser.parse_args()
    print(train(args.family, output_root=args.output, rounds=args.rounds, dataset=args.dataset))
