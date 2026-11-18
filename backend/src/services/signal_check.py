"""Check a saved trial at fixed times in a separate observation."""
import numpy as np
import requests
from astropy.timeseries import BoxLeastSquares

from src.contracts import AnalysisError
from src.fits_downloader import LatestFITSFetcher
from src.services.observations import lightcurve_products
from src.services.tess_pixels import API, aperture_photometry, download_sector_cutout


def event_windows(time, flux, period, epoch, duration):
    cycles = np.rint((time - epoch) / period).astype(int)
    cadence = np.median(np.diff(time))
    events = []
    for cycle in range(int(cycles[0]), int(cycles[-1]) + 1):
        center = epoch + cycle * period
        start, stop = np.searchsorted(time, [center - 3 * duration, center + 3 * duration])
        offset = time[start:stop] - center
        values = flux[start:stop]
        core = abs(offset) <= duration / 2
        sides = abs(offset) >= duration
        counts = [int(core.sum()), int((sides & (offset < 0)).sum()), int((sides & (offset > 0)).sum())]
        row = dict(cycle=cycle, midpoint_bjd=center, in_dip=counts[0], before=counts[1], after=counts[2], depth_ppm=None)
        if counts[0] >= max(2, .6 * duration / cadence) and min(counts[1:]) >= 3:
            baseline = np.polyval(np.polyfit(offset[sides], values[sides], 1), offset[core])
            if np.all(baseline > 0):
                row['depth_ppm'] = float(np.mean(1 - values[core] / baseline)) * 1e6
        events.append(row)
    return events


def repeat_result(events, expected_depth_ppm, injected_events):
    measured = [row['depth_ppm'] for row in events if row['depth_ppm'] is not None]
    injected = [row['depth_ppm'] for row in injected_events if row['depth_ppm'] is not None]
    result = {'status': 'inconclusive', 'usable_events': len(measured), 'reason': 'insufficient_event_coverage'}
    if min(len(measured), len(injected)) < 3:
        return result
    depth = float(np.mean(measured))
    uncertainty = float(np.std(measured, ddof=1) / np.sqrt(len(measured)))
    input_detectable = (float(np.mean(injected)) - 3 * uncertainty >= expected_depth_ppm / 2
                        and sum(dip > 0 for dip in injected) >= 3)
    result.update(depth_ppm=depth, event_sem_ppm=uncertainty, injection_recovered=input_detectable,
                  reason='mixed_or_insensitive_measurements')
    if depth - 3 * uncertainty >= expected_depth_ppm / 2 and sum(dip > 0 for dip in measured) >= 3:
        result.update(status='repeats', reason='consistent_dimming_at_predicted_times')
    elif input_detectable and depth + 3 * uncertainty < expected_depth_ppm / 2:
        result.update(status='did_not_repeat', reason='original_depth_recoverable_at_predicted_times')
    return result


def check_saved_signal(spec, directory, stage, observation_index=None):
    stage('checking_event_windows')
    period, epoch, duration = spec['period'], spec['epoch'], spec['duration']
    source = directory.parent / spec['parent_run'] / 'lightcurve.csv'
    time, flux = np.loadtxt(source, delimiter=',', skiprows=1, ndmin=2).T
    if not 100 <= len(time) <= 100000 or not np.isfinite([time, flux]).all() or np.any(np.diff(time) <= 0):
        raise AnalysisError('The saved light curve cannot be checked safely.', 422, 'invalid_photometry')
    primary = event_windows(time, flux, period, epoch, duration)
    result = {'status': 'inconclusive', 'reason': 'no_independent_sector', 'source_sector': spec['sector'],
              'proposed_period_days': period, 'events': primary, 'refits': []}
    # shortcut: refit up to eight usable windows, expand only with a bounded job budget.
    limit = min(20., (time[-1] - time[0]) / 3)
    noise = float(np.median(np.abs(np.diff(flux))) / (.67448975 * np.sqrt(2)))
    if limit > .5 and noise > 0:
        grid = np.linspace(.5, limit, 4000)
        for event in [row for row in primary if row['depth_ppm'] is not None][:8]:
            stage('checking_event_windows')
            keep = abs(time - event['midpoint_bjd']) > duration
            if keep.sum() < 100:
                continue
            spectrum = BoxLeastSquares(time[keep] - time[0], flux[keep], dy=noise).power(grid, np.linspace(.02, .2, 8))
            result['refits'].append({'omitted_cycle': event['cycle'],
                                     'best_period_days': float(spectrum.period[np.argmax(spectrum.power)])})
    stage('checking_independent_sector')
    coords = spec['coordinates']
    try:
        identifier = spec['target']['id']
        products, limited = (observation_index.get(identifier, 'tess') if observation_index
                             else lightcurve_products(identifier, 'tess'))
        choices = [item for item in products if item['group'] is not None and
                   0 < abs(item['group'] - spec['sector']) <= 2]
        choices.sort(key=lambda item: (abs(item['group'] - spec['sector']), item['author'] != spec['author']))
        comparable = False
        if choices and not limited:
            from src.exoplanet_processor import ExoplanetParameterProcessor
            from astropy.io import fits
            product = LatestFITSFetcher('tess', identifier, directory / 'downloads').select_or_download((choices, False))
            sector, url = product['group_val'], product['uri']
            result['independent_sector'] = sector
            stage('measuring_independent_events')
            with fits.open(product['path']) as hdus:
                if str(hdus[0].header.get('TICID')) != identifier or hdus[0].header.get('SECTOR') != sector:
                    raise ValueError('Independent light curve is for a different target or sector')
            independent_time, independent_flux = ExoplanetParameterProcessor(product['path'], 'tess', {}).load_samples()
            comparable = product['author'] == spec['author']
        else:
            response = requests.get(f'{API}/sector', params=coords, timeout=(5, 15))
            response.raise_for_status()
            sectors = {int(row['sector']) for row in response.json()['results']}
            sectors.discard(spec['sector'])
            if not sectors:
                return 'succeeded', {'signal_check': result}
            sector = min(sectors, key=lambda item: (abs(item - spec['sector']), item))
            result['independent_sector'] = sector
            path, url = download_sector_cutout(coords, sector, directory / 'downloads')
            stage('measuring_independent_events')
            independent_time, independent_flux = aperture_photometry(path, coords, sector)
        clean = np.isfinite(independent_time) & np.isfinite(independent_flux)
        order = np.argsort(independent_time[clean])
        independent_time, independent_flux = independent_time[clean][order], independent_flux[clean][order]
        if len(order) < 2 or np.any(np.diff(independent_time) <= 0):
            raise ValueError('Unusable independent observation')
    except (requests.RequestException, AnalysisError, OSError, KeyError, ValueError, TypeError):
        result['reason'] = 'independent_observation_unavailable'
        return 'succeeded', {'signal_check': result}
    result['independent_source'] = url
    if np.median(np.diff(independent_time)) > duration / 2:
        result['reason'] = 'independent_cadence_too_coarse'
        return 'succeeded', {'signal_check': result}
    if min(abs(independent_time[0] - time[-1]), abs(time[0] - independent_time[-1])) > 10 * period:
        result['reason'] = 'timing_prediction_too_far'
        return 'succeeded', {'signal_check': result}
    events = event_windows(independent_time, independent_flux, period, epoch, duration)
    phase = (independent_time - epoch + period / 2) % period - period / 2
    fake = independent_flux * np.where(abs(phase) <= duration / 2, 1 - spec['depth'], 1)
    injected = event_windows(independent_time, fake, period, epoch, duration)
    result.update(repeat_result(events, spec['depth'] * 1e6, injected), independent_events=events)
    if result['status'] == 'did_not_repeat' and not comparable:
        result.update(status='inconclusive', reason='different_photometry')
    return 'succeeded', {'signal_check': result}
