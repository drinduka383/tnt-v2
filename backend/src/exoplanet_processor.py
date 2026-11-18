"""Preserve photometry even when transit search or model scoring is unavailable."""
from io import BytesIO
from pathlib import Path
import base64
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import lightkurve as lk
from astropy.timeseries import BoxLeastSquares
from src.contracts import FEATURES, MODEL_FAMILY

class ExoplanetParameterProcessor:
    def __init__(self, fits_path, mission, catalog, output_dir=None):
        self.path = Path(fits_path)
        self.output = Path(output_dir or self.path.parent)
        self.mission, self.catalog = mission, catalog
        if mission not in MODEL_FAMILY:
            raise ValueError('Unsupported mission')

    def process(self, print_json=False):
        observation = lk.read(self.path)
        if hasattr(observation, 'to_lightcurve'):
            mask = observation.pipeline_mask
            if mask is None or not np.any(mask):
                mask = observation.create_threshold_mask(threshold=3)
            observation = observation.to_lightcurve(aperture_mask=mask)
        if 'pdcsap_flux' in observation.colnames:
            observation = observation.select_flux('pdcsap_flux')
        elif 'sap_flux' in observation.colnames:
            observation = observation.select_flux('sap_flux')
        if 'quality' in observation.colnames:
            observation = observation[observation.quality == 0]
        observation = observation.remove_nans().normalize()
        t, flux = np.asarray(observation.time.jd), np.asarray(observation.flux.value)
        return self.process_samples(t, flux)

    def process_samples(self, t, flux):
        good = np.isfinite(t) & np.isfinite(flux)
        t, flux = t[good], flux[good]
        order = np.argsort(t)
        t, flux = t[order], flux[order]
        if len(t) < 2:
            raise ValueError('Observation has fewer than two finite photometry samples')
        self.output.mkdir(parents=True, exist_ok=True)
        partial = self.output / 'lightcurve.csv.part'
        np.savetxt(partial, np.column_stack((t, flux)), delimiter=',', header='time_bjd,normalized_flux', comments='')
        partial.replace(self.output / 'lightcurve.csv')
        baseline = float(t[-1] - t[0])
        relative = t - t[0]
        measurements = {key: self.catalog.get(key) for key in FEATURES[MODEL_FAMILY[self.mission]]}
        quality = {'exploratory_signal': False, 'search_status': 'completed',
                   'unmeasured': ['period uncertainty', 'duration uncertainty', 'epoch uncertainty'],
                   'rule': 'at least 3 covered events and depth/depth_error >= 7; not a calibrated detection probability'}
        parameters = {}
        folded = None
        if len(t) < 100:
            quality.update(search_status='insufficient_points', message='Photometry loaded; too few samples for this transit search.')
        elif baseline < 2:
            quality.update(search_status='insufficient_coverage', message='Photometry loaded; less than two days of coverage for this transit search.')
        elif len(t) > 100000 or baseline > 120:
            quality.update(search_status='limit_exceeded', message='Photometry loaded; this observation exceeds the supported transit-search range.')
        elif np.std(flux) == 0:
            quality.update(search_status='constant_flux', message='Photometry loaded; no flux variation to search.')
        else:
            try:
                max_period = min(20.0, baseline / 3)
                noise = np.median(np.abs(np.diff(flux))) / (0.67448975 * np.sqrt(2))
                if not np.isfinite(noise) or noise <= 0:
                    raise ValueError('Observation noise cannot be estimated')
                bls = BoxLeastSquares(relative, flux, dy=noise)
                spectrum = bls.power(np.linspace(.5, max_period, 4000), np.linspace(.02, .2, 8))
                index = int(np.argmax(spectrum.power))
                period, duration, depth = (float(getattr(spectrum, name)[index]) for name in ('period', 'duration', 'depth'))
                epoch, depth_error = float(spectrum.transit_time[index]), float(spectrum.depth_err[index])
                mask = bls.transit_mask(relative, period, duration, epoch)
                count = len(np.unique(np.round((relative[mask] - epoch) / period)))
                snr = depth / depth_error if depth_error > 0 else 0
                detected = count >= 3 and np.isfinite(snr) and snr >= 7 and depth > 0
                parameters = {'period_days':period, 'duration_hours':duration*24, 'depth_fraction':depth,
                              'depth_error':depth_error, 'midpoint_bjd':float(t[0]+epoch), 'transits_covered':count, 'snr':snr}
                quality['exploratory_signal'] = bool(detected)
                folded = (relative - epoch + period / 2) % period - period / 2
                if detected and self.mission == 'tess':
                    measurements.update(pl_orbper=period, pl_trandurh=duration*24, pl_trandep=depth*1e6,
                                        pl_trandeperr1=depth_error*1e6, pl_trandeperr2=-depth_error*1e6,
                                        pl_tranmid=float(t[0]+epoch), eng_period_duration_ratio=period/duration,
                                        eng_duration_period_ratio=duration/period)
                elif detected:
                    measurements.update(koi_num_transits=count, koi_model_snr=snr)
            except (ValueError, RuntimeError, ArithmeticError):
                quality.update(search_status='unavailable', message='Photometry loaded; transit fitting was not reliable for this observation.')
        plots = []
        display = np.linspace(0, len(t)-1, min(6000,len(t)), dtype=int)
        for name, x in [('normalized_light_curve', relative), ('phase_folded_light_curve', folded)]:
            if x is None: continue
            fig, ax = plt.subplots(figsize=(10,3.6))
            try:
                ax.scatter(x[display], flux[display], s=2, color='#295ab0', alpha=.7)
                ax.set(xlabel='Days from first observation' if name == 'normalized_light_curve' else 'Days from fitted transit center', ylabel='Normalized flux')
                ax.grid(alpha=.15)
                fig.tight_layout()
                stream = BytesIO()
                fig.savefig(stream, format='png', dpi=120)
                plots.append({'type':name, 'data':'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()})
            finally:
                plt.close(fig)
        return [{'mission':self.mission, 'data':[measurements], 'visualizations':plots,
                 'parameters':parameters, 'quality':quality,
                 'photometry':{'samples':len(t), 'baseline_days':baseline, 'first_bjd':float(t[0]), 'last_bjd':float(t[-1]),
                               'plotted_samples':len(display), 'preview':[[float(t[i]),float(flux[i])] for i in display[:8]]}}]
