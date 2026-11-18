"""Verify artifacts and run real inference on eligible bundled catalog rows, offline."""
import argparse
import json
from pathlib import Path
from train import prepare_dataset
from src.services.model_service import ModelService, ROOT
from src.contracts import FEATURES


def check(family, name=None):
    service = ModelService()
    model = service.resolve(family, name)
    frame, _, _, eligibility = prepare_dataset(family, ROOT / 'src/utils/datasets' / f'{family}.csv')
    if frame.empty:
        raise ValueError('No eligible catalog rows for inference check')
    predictions = service.predict_rows(frame.to_dict('records'), model)
    manifest = json.loads(Path(model['path']).with_name('manifest.json').read_text(encoding='utf-8'))
    return {'family': family, 'model': model['name'], 'sha256': model['sha256'],
            'features': len(FEATURES[family]), **eligibility, 'predictions_checked': len(predictions),
            'test_metrics': manifest.get('evaluation', {}).get('test'),
            'labels': manifest.get('labels'), 'validation': manifest.get('scientific_validation')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--family', choices=FEATURES)
    parser.add_argument('--model', help='Custom model identifier; requires --family')
    args = parser.parse_args()
    if args.model and not args.family:
        parser.error('--model requires --family')
    print(json.dumps([check(family, args.model) for family in ([args.family] if args.family else FEATURES)], indent=2))
