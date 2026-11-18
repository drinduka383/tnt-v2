"""Offline reduced-input TESS experiment. Artifacts are separate from app models."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import average_precision_score, balanced_accuracy_score, confusion_matrix, roc_auc_score

from evaluate_toi import later_cohort
from src.data_mapper import build_model_payload_from_row
from src.services.model_service import ModelService
from src.validation import validate_features
from train import fit_classifier, partition, prepare_dataset

# Direct transit measurements only. Do not use follow-up uncertainties or stellar fits.
COLUMNS = ['pl_orbper', 'pl_trandurh', 'pl_trandep']


def transit_rows(frame):
    rows = []
    for row in frame.to_dict('records'):
        features = build_model_payload_from_row('tess', row).data[0]
        try:
            validate_features([features], COLUMNS)
        except ValueError:
            continue
        rows.append({**row, **{key: features[key] for key in COLUMNS}})
    return pd.DataFrame(rows, columns=frame.columns)


def metrics(rows, scores, threshold):
    classes = [score >= threshold for score in scores]
    report = {'rows': len(rows), 'hosts': int(rows.tid.nunique()),
              'confusion_matrix': confusion_matrix(rows.target, classes, labels=[0, 1]).tolist()}
    if rows.target.nunique() == 2:
        report.update(roc_auc=roc_auc_score(rows.target, scores),
                      average_precision=average_precision_score(rows.target, scores),
                      balanced_accuracy=balanced_accuracy_score(rows.target, classes))
    return report


def experiment(snapshot, output):
    service = ModelService()
    baseline = service.resolve('TOI')
    source, unseen, cohort = later_cohort(snapshot, baseline)
    historical, _, labels, _ = prepare_dataset('TOI', source)
    training, validation, historical_test = partition(historical, 'tid')
    challenger = fit_classifier(training, validation, COLUMNS)
    assert not set(training.tid) & set(unseen.tid)

    labeled = unseen.loc[unseen.tfopwg_disp.isin(labels)].copy()
    labeled['target'] = labeled.tfopwg_disp.map(labels)
    reduced = transit_rows(labeled)
    full, _, _, _ = prepare_dataset('TOI', snapshot)
    common = full.loc[full.toi.isin(reduced.toi)]
    added = reduced.loc[~reduced.toi.isin(common.toi)]

    def compare(rows):
        full_scores = [entry['probability'] for entry in service.predict_rows(rows.to_dict('records'), baseline)]
        return {'shipped': metrics(rows, full_scores, baseline['threshold']),
                'challenger': metrics(rows, challenger.predict_proba(rows[COLUMNS])[:, 1], .5)}

    report = {'purpose': 'development only; NASA cohort previously inspected', **cohort,
              'features': COLUMNS, 'training_sha256': sha256(source.read_bytes()).hexdigest(),
              'shipped_sha256': baseline['sha256'], 'training_rows': len(training),
              'validation_rows': len(validation), 'best_iteration': challenger.best_iteration,
              'historical_common_test': compare(historical_test), 'labeled_later_rows': len(labeled),
              'later_common': compare(common),
              'later_challenger_all': metrics(reduced, challenger.predict_proba(reduced[COLUMNS])[:, 1], .5),
              'later_challenger_only': metrics(added, challenger.predict_proba(added[COLUMNS])[:, 1], .5)}
    output.mkdir(parents=True, exist_ok=False)
    artifact = output / 'model.json'
    challenger.save_model(artifact)
    report['challenger_sha256'] = sha256(artifact.read_bytes()).hexdigest()
    (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('output', type=Path, help='New directory for offline experiment artifacts')
    args = parser.parse_args()
    print(json.dumps(experiment(args.snapshot, args.output), indent=2, allow_nan=False))
