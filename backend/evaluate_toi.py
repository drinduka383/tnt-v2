"""Evaluate the frozen TESS baseline on newer NASA TOIs from unseen TIC hosts."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import average_precision_score, balanced_accuracy_score, confusion_matrix, roc_auc_score

from src.contracts import FEATURES
from src.data_mapper import build_model_payload_from_row
from src.services.model_service import ModelService, ROOT
from train import prepare_dataset

# ea7a969 introduced both bundled CSVs on this date. Exclude the entire day.
FIRST_BUNDLED_COMMIT_DAY = pd.Timestamp("2025-10-05", tz="UTC")


def later_cohort(snapshot, model):
    bundled_path = ROOT / 'src/utils/datasets/TOI.csv'
    manifest = json.loads(Path(model['path']).with_name('manifest.json').read_text(encoding='utf-8'))
    if sha256(bundled_path.read_bytes()).hexdigest() != manifest['dataset_sha256']:
        raise ValueError('Bundled data no longer matches the baseline manifest')
    bundled = pd.read_csv(bundled_path)
    current = pd.read_csv(snapshot)
    for frame in (bundled, current):
        if frame[['tid', 'toi']].isna().any().any() or frame['toi'].duplicated().any():
            raise ValueError('Expected unique TOIs with complete TIC IDs')
    updates = pd.to_datetime(bundled['rowupdate'], format='mixed', utc=True)
    created = pd.to_datetime(current['toi_created'], format='mixed', utc=True)
    if updates.isna().any() or created.isna().any():
        raise ValueError('Missing catalog dates')
    cutoff = max(updates.max().normalize(), FIRST_BUNDLED_COMMIT_DAY)
    later = current.loc[created >= cutoff + pd.Timedelta(days=1)]
    unseen = later.loc[~later.tid.isin(bundled.tid) & ~later.toi.isin(bundled.toi)]
    return bundled_path, unseen, {
        'snapshot_sha256': sha256(snapshot.read_bytes()).hexdigest(),
        'bundled_latest_row_update': updates.max().isoformat(),
        'excluded_through_utc_day': cutoff.date().isoformat(),
        'snapshot_rows': len(current), 'later_rows': len(later), 'unseen_rows': len(unseen),
    }


def evaluate(snapshot):
    service = ModelService()
    model = service.resolve('TOI')
    _, unseen, cohort = later_cohort(snapshot, model)
    prepared, _, labels, _ = prepare_dataset('TOI', snapshot)
    labeled = unseen.tfopwg_disp.isin(labels)
    eligible = prepared.loc[prepared.toi.isin(unseen.toi)]
    if eligible.target.nunique() != 2:
        raise ValueError('The later unseen-host cohort needs scoreable examples of both classes')
    omitted = unseen.loc[labeled & ~unseen.toi.isin(eligible.toi)]
    missing = pd.DataFrame([build_model_payload_from_row('tess', row).data[0]
                            for row in omitted.to_dict('records')], columns=FEATURES['TOI'])
    missing_counts = missing.isna().sum().sort_values(ascending=False)
    predictions = service.predict_rows(eligible.to_dict('records'), model)
    scores = [row['probability'] for row in predictions]
    classes = [row['prediction'] for row in predictions]
    return {'protocol': 'frozen baseline; TOI creation after latest bundled update or first bundled commit day, whichever is later; excludes all bundled TICs and TOIs',
            **cohort, 'model_sha256': model['sha256'],
            'labeled_rows': int(labeled.sum()), 'scoreable_rows': len(eligible),
            'labeled_by_disposition': unseen.loc[labeled, 'tfopwg_disp'].value_counts().to_dict(),
            'scoreable_by_disposition': eligible.tfopwg_disp.value_counts().to_dict(),
            'missing_features_among_unscored_labeled': missing_counts[missing_counts > 0].to_dict(),
            'scoreable_hosts': int(eligible.tid.nunique()),
            'positive_prevalence': float(eligible.target.mean()),
            'roc_auc': roc_auc_score(eligible.target, scores),
            'average_precision': average_precision_score(eligible.target, scores),
            'balanced_accuracy': balanced_accuracy_score(eligible.target, classes),
            'threshold': model['threshold'],
            'confusion_matrix_actual_by_predicted_negative_then_positive': confusion_matrix(eligible.target, classes, labels=[0, 1]).tolist()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path, help='Unmodified NASA TAP TOI CSV snapshot')
    args = parser.parse_args()
    print(json.dumps(evaluate(args.snapshot), indent=2, allow_nan=False))
