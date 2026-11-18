"""Offline check of an exploratory TESS signal against archived pixel cutouts."""
import argparse
import hashlib
import json
from pathlib import Path

from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.timeseries import BoxLeastSquares
from astropy.wcs import WCS
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import median_filter

from src.services.tess_pixels import aperture_photometry


def phase_days(time, period, epoch):
    return (time - epoch + period / 2) % period - period / 2


def flatten(time, flux):
    result = flux.copy()
    for part in np.split(np.arange(len(time)), np.flatnonzero(np.diff(time) > .25) + 1):
        if len(part) < 3:
            continue
        cadence = np.median(np.diff(time[part]))
        width = min(2 * int(.5 / cadence) + 1, len(part) // 2 * 2 + 1)
        result[part] /= median_filter(flux[part], size=width, mode='nearest')
    return result


def best_box(time, flux, periods, durations):
    relative = time - time[0]
    noise = np.median(np.abs(np.diff(flux))) / (.67448975 * np.sqrt(2))
    search = BoxLeastSquares(relative, flux, dy=noise)
    powers = search.power(periods, durations)
    i = int(np.argmax(powers.power))
    period, duration, epoch = map(float, (powers.period[i], powers.duration[i], powers.transit_time[i]))
    inside = search.transit_mask(relative, period, duration, epoch)
    return {'period_days': period, 'epoch_bjd': float(time[0] + epoch), 'duration_hours': duration * 24,
            'depth_ppm': float(powers.depth[i]) * 1e6, 'snr': float(powers.depth_snr[i]),
            'cycles_with_samples': int(len(np.unique(np.rint((relative[inside] - epoch) / period))))}


def pixel_events(path, coords, period, epoch, duration):
    with fits.open(path) as hdus:
        data = hdus['PIXELS'].data
        h = hdus['PIXELS'].header
        time = data['TIME'] + h['BJDREFI'] + h['BJDREFF']
        pixels = data['FLUX']
        keep = (data['QUALITY'] == 0) & np.isfinite(time) & np.all(np.isfinite(pixels), axis=(1, 2))
        time, pixels = time[keep], pixels[keep].copy()
        sky = SkyCoord(coords['ra'], coords['dec'], unit='deg')
        x, y = (float(value) for value in WCS(hdus['APERTURE'].header).celestial.world_to_pixel(sky))
    ix, iy = int(round(x)), int(round(y))
    border = np.ones((7, 7), dtype=bool)
    border[1:-1, 1:-1] = False
    pixels -= np.median(pixels[:, border], axis=1)[:, None, None]
    cadence = np.median(np.diff(time))
    phase = phase_days(time, period, epoch)
    cycles = np.rint((time - epoch) / period).astype(int)
    events, images = [], []
    for n in np.unique(cycles):
        primary = (cycles == n) & (np.abs(phase) <= duration / 2)
        before = (cycles == n) & (phase >= -2 * duration) & (phase <= -duration)
        after = (cycles == n) & (phase <= 2 * duration) & (phase >= duration)
        enough = (primary.sum() >= .6 * duration / cadence and
                  min(before.sum(), after.sum()) >= .5 * duration / cadence)
        item = {'cycle': int(n), 'predicted_bjd': epoch + int(n) * period,
                'inside': int(primary.sum()), 'before': int(before.sum()), 'after': int(after.sum()),
                'usable': bool(enough)}
        if not (primary.any() or before.any() or after.any()):
            continue
        if enough:
            outside = before | after
            coefficients = np.polyfit(phase[outside], pixels[outside].reshape(outside.sum(), 49), 1)
            baseline = (coefficients[0] * np.mean(phase[primary]) + coefficients[1]).reshape(7, 7)
            removed = baseline - np.mean(pixels[primary], axis=0)
            area = np.s_[iy-1:iy+2, ix-1:ix+2]
            scale = float(baseline[area].sum())
            if scale > 0:
                item['depth_ppm'] = float(removed[area].sum()) / scale * 1e6
                item['brightest_loss_pixel_xy'] = list(map(int, np.unravel_index(removed.argmax(), removed.shape)[::-1]))
                images.append((item, removed))
        events.append(item)
    return events, images, (x, y)


def injection_pilot(time, flux):
    """Recover injected box dips with the same grid and screening rule as the app."""
    trials = []
    grid = np.linspace(.5, min(20., (time[-1] - time[0]) / 3), 4000)
    durations = np.linspace(.02, .2, 8)
    duration = .08
    for period in [1., 3., 7.]:
        for depth in [2000, 10000, 40000]:
            for fraction in [.11, .34, .57, .80]:
                epoch = float(time[0] + period * fraction)
                mask = np.abs(phase_days(time, period, epoch)) <= duration / 2
                simulated = flux.copy()
                simulated[mask] *= 1 - depth / 1e6
                top = best_box(time, simulated, grid, durations)
                recovered = (abs(top['period_days'] / period - 1) <= .02 and
                             abs(phase_days(top['epoch_bjd'], period, epoch)) <= duration / 2 and
                             top['snr'] >= 7 and top['cycles_with_samples'] >= 3)
                trials.append({'period_days': period, 'depth_ppm': depth, 'phase': fraction,
                               'recovered': bool(recovered), 'strongest_period_days': top['period_days']})
    return trials


def report(args):
    coords = {'ra': args.ra, 'dec': args.dec}
    sectors = []
    curves = {}
    args.output.mkdir(parents=True, exist_ok=True)
    for path in args.fits:
        with fits.open(path) as hdus:
            sector = int(hdus[0].header['SECTOR'])
        time, flux = aperture_photometry(path, coords, sector)
        curves[sector] = (time, flux)
        events, images, target = pixel_events(path, coords, args.period, args.epoch, args.duration)
        detrended = flatten(time, flux)
        grid = np.linspace(.5, min(20., (time[-1] - time[0]) / 3), 4000)
        info = {'sector': sector, 'samples': len(time), 'file': path.name,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'strongest_after_detrending': best_box(time, detrended, grid, np.linspace(.02, .2, 8)),
                'fixed_period_free_epoch_after_detrending': best_box(time, detrended, args.period, args.duration),
                'events_at_original_ephemeris': events}
        sectors.append(info)
        print(sector, info['strongest_after_detrending']['period_days'],
              [(row['cycle'], round(row['depth_ppm'])) for row in events if 'depth_ppm' in row], flush=True)
        if sector == args.reference_sector:
            fig, axes = plt.subplots(2, 1, figsize=(10, 4.8), sharex=True, layout='constrained')
            for ax, values, label in zip(axes, [flux, detrended], ['Aperture flux', 'After detrending']):
                ax.scatter(time-time[0], values, s=3, color='#285284', alpha=.45)
                for event in events:
                    x = event['predicted_bjd'] - time[0]
                    ax.axvspan(x - args.duration / 2, x + args.duration / 2, color='#c66b2d', alpha=.3)
                ax.set_ylabel(label)
            axes[1].set_xlabel('Days from first valid exposure')
            fig.suptitle(f'TESS sector {sector} ? predicted windows at the original {args.period:.2f}-day period')
            fig.savefig(args.output / 'sector-window-check.png', dpi=160)
            plt.close(fig)
        if images and sector == args.reference_sector:
            fig, axes = plt.subplots(1, len(images), figsize=(3.8 * len(images), 3.8), squeeze=False, layout='constrained')
            for ax, (event, pixels) in zip(axes[0], images):
                scale = max(np.max(np.abs(pixels)), 1e-12)
                plotted = ax.imshow(pixels, cmap='RdBu_r', origin='lower', vmin=-scale, vmax=scale)
                ax.plot(*target, marker='+', color='black', markersize=12)
                ax.set(title=f"Cycle {event['cycle']}", xlabel='Cutout pixel column', ylabel='Cutout pixel row')
                fig.colorbar(plotted, ax=ax, label='Flux lost during event')
            fig.suptitle(f'TESS sector {sector} · in/out difference · + marks the target TIC position')
            fig.savefig(args.output / 'difference-images.png', dpi=160)
            plt.close(fig)
    time, flux = curves[args.reference_sector]
    trials = injection_pilot(time, flux)
    matrix = [[sum(row['recovered'] for row in trials if row['period_days'] == p and row['depth_ppm'] == d)
               for p in [1, 3, 7]] for d in [2000, 10000, 40000]]
    fig, ax = plt.subplots(figsize=(5, 3.6), layout='constrained')
    ax.imshow(matrix, origin='lower', cmap='Blues', vmin=0, vmax=4)
    for y, row in enumerate(matrix):
        for x, count in enumerate(row):
            ax.text(x, y, f'{count}/4', color='white' if count >= 3 else 'black', ha='center', va='center')
    ax.set(xticks=range(3), xticklabels=['1', '3', '7'], yticks=range(3), yticklabels=['0.2%', '1%', '4%'],
           xlabel='Injected period (days)', ylabel='Injected depth', title=f'Sector {args.reference_sector} · transit recovery pilot')
    fig.savefig(args.output / 'injection-recovery.png', dpi=160)
    plt.close(fig)
    (args.output / 'vetting.json').write_text(json.dumps({'sectors': sectors, 'reference_sector': args.reference_sector,
        'ephemeris': {'period_days': args.period, 'epoch_bjd': args.epoch, 'duration_days': args.duration},
        'injection_duration_days': .08, 'injection_pilot': trials}, indent=2, allow_nan=False), encoding='utf-8')
    print('Recovery counts (depth rows, period columns):', matrix, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ra', type=float, required=True)
    parser.add_argument('--dec', type=float, required=True)
    parser.add_argument('--period', type=float, required=True)
    parser.add_argument('--epoch', type=float, required=True)
    parser.add_argument('--duration', type=float, required=True, help='Trial duration in days')
    parser.add_argument('--reference-sector', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('fits', type=Path, nargs='+')
    report(parser.parse_args())
