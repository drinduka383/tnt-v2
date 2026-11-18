"""Published TESS follow-up and a descriptive check at the catalog ephemeris."""
import csv
from decimal import Decimal
from io import BytesIO
import base64
import re

import numpy as np
import requests

from src.data_mapper import number

EXOFOP = 'https://exofop.ipac.caltech.edu/tess/download_toi.php'


def followup_notes(identifier, candidates):
    identifiers = [item['id'] for item in candidates if re.fullmatch(r'[0-9]+\.[0-9]{1,2}', item['id'])]
    if not identifiers:
        return {'status': 'skipped', 'notes': {}}
    prefix = identifiers[0].split('.')[0]
    try:
        with requests.get(EXOFOP, params={'toi': prefix, 'output': 'csv'}, stream=True, timeout=(4, 10)) as response:
            response.raise_for_status()
            content = bytearray()
            for part in response.iter_content(8192):
                content.extend(part)
                if len(content) > 128 * 1024:
                    return {'status': 'unavailable', 'notes': {}}
        reader = csv.DictReader(content.decode('utf-8-sig').splitlines())
        if not {'TIC ID', 'TOI', 'Comments'}.issubset(reader.fieldnames or []):
            return {'status': 'unavailable', 'notes': {}}
        rows = list(reader)
    except (requests.RequestException, UnicodeError, csv.Error):
        return {'status': 'unavailable', 'notes': {}}
    result = {}
    for row in rows:
        toi = row.get('TOI', '') or ''
        if row.get('TIC ID') != identifier or not re.fullmatch(r'[0-9]+\.[0-9]{1,2}', toi):
            continue
        result[Decimal(toi)] = {'disposition': row.get('TFOPWG Disposition') or None,
                                'comment': (row.get('Comments') or '').strip()[:500],
                                'updated': row.get('Date TOI Updated (UTC)'),
                                'source': f'{EXOFOP}?toi={toi}&output=csv'}
    notes = {toi: result[Decimal(toi)] for toi in identifiers if Decimal(toi) in result}
    return {'status': 'ready' if notes else 'empty', 'notes': notes}


def check_ephemeris(time, flux, row):
    period, epoch, duration = map(number, (row.get('pl_orbper'), row.get('pl_tranmid'), row.get('pl_trandurh')))
    if (period is None or epoch is None or duration is None or not 0.01 <= period <= 1e4 or
            not 2400000 <= epoch <= 2600000 or not 0 < duration < 24 * period / 12):
        return {'status': 'missing_ephemeris'}
    folded = []
    result = {'status': 'insufficient_coverage', 'period_days': period, 'epoch_bjd': epoch, 'duration_hours': duration}
    for offset, key in [(0, 'primary'), (.5, 'half_period')]:
        cycles = np.rint((time - epoch) / period - offset).astype(int)
        hours = 24 * (time - epoch - (cycles + offset) * period)
        near = np.abs(hours) <= 3 * duration
        x, y, groups = hours[near], flux[near], cycles[near]
        depths, traces = [], []
        for indices in np.split(np.arange(len(groups)), np.flatnonzero(np.diff(groups)) + 1):
            event_x, event_y = x[indices], y[indices]
            core = np.abs(event_x) <= .35 * duration
            shoulders = np.abs(event_x) >= duration
            if core.sum() < 2 or (shoulders & (event_x < 0)).sum() < 3 or (shoulders & (event_x > 0)).sum() < 3:
                continue
            baseline = np.polyval(np.polyfit(event_x[shoulders], event_y[shoulders], 1), event_x)
            if np.any(baseline <= 0):
                continue
            ppm = 1e6 * (event_y / baseline - 1)
            depths.append(-float(np.mean(ppm[core])))
            traces.append(np.column_stack((event_x, ppm)))
        result[key] = {'events': len(depths), 'depth_ppm': float(np.mean(depths)) if depths else None,
                       'event_sem_ppm': float(np.std(depths, ddof=1) / np.sqrt(len(depths))) if len(depths) >= 2 else None}
        folded.append(np.concatenate(traces) if traces else None)
    if result['primary']['events'] < 2:
        return result
    result['status'] = 'measured'
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4), sharey=True, layout='constrained')
    try:
        for ax, data, title in zip(axes, folded, ['Published transit time', 'Half an orbit later']):
            if data is not None:
                bins = np.linspace(-2 * duration, 2 * duration, 33)
                which = np.digitize(data[:, 0], bins) - 1
                counts = np.bincount(which[which >= 0], minlength=33)[:32]
                sums = np.bincount(which[which >= 0], weights=data[which >= 0, 1], minlength=33)[:32]
                good = counts > 0
                centers = (bins[1:] + bins[:-1]) / 2
                ax.plot(centers[good], sums[good] / counts[good], 'o-', color='#295ab0', markersize=3)
            ax.axvline(0, color='gray', linestyle=':')
            ax.axhline(0, color='gray', linewidth=.6)
            ax.set(title=title, xlabel='Hours from predicted center', xlim=(-2 * duration, 2 * duration))
        axes[0].set_ylabel('Flux relative to local baseline (ppm)')
        buffer = BytesIO()
        fig.savefig(buffer, format='png', dpi=120)
        result['plot'] = 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()
    finally:
        plt.close(fig)
    return result
