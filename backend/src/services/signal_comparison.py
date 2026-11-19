"""Load saved comparison measurements without rerunning the signal check."""
from io import BytesIO

import numpy as np
from astropy.io import fits
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from src.exoplanet_processor import ExoplanetParameterProcessor
from src.services.tess_pixels import aperture_photometry


def comparison_samples(original, independent, spec, sector):
    time, flux = np.loadtxt(original, delimiter=',', skiprows=1, ndmin=2).T
    with fits.open(independent) as hdus:
        header = hdus[0].header
        if header.get('SECTOR') != sector:
            raise ValueError('Unexpected independent sector')
        cutout = 'PIXELS' in hdus
        if not cutout and str(header.get('TICID')) != spec['target']['id']:
            raise ValueError('Unexpected independent TIC')
    if cutout:
        other_time, other_flux = aperture_photometry(independent, spec['coordinates'], sector)
    else:
        other_time, other_flux = ExoplanetParameterProcessor(independent, 'tess', {}).load_samples()

    period, epoch, duration = spec['period'], spec['epoch'], spec['duration']
    half = 12 * duration
    window = min(2.5 * duration, period / 2) * 24
    folded = []
    for t, f in [(time, flux), (other_time, other_flux)]:
        phase = ((t - epoch + period / 2) % period - period / 2) * 24
        keep = np.isfinite(phase) & np.isfinite(f) & (abs(phase) <= window)
        if not np.any(keep):
            raise ValueError('No samples in the plotted window')
        folded.append((phase[keep], (f[keep] - 1) * 100))

    return folded, half, window


def comparison_figure(folded, half, window, original_sector, sector):
    figure = Figure(figsize=(7.4, 4.75), layout='constrained')
    canvas = FigureCanvasAgg(figure)
    top, bottom = figure.subplots(2, 1, sharex=True, sharey=True)
    for ax, (phase, relative), title, color in zip(
        (top, bottom), folded, (f'Original observation / Sector {original_sector}',
                                f'Independent observation / Sector {sector}'), ('#235b9c', '#177e70'),
    ):
        ax.axvspan(-half, half, color='#e9bd67', alpha=.25)
        ax.axhline(0, color='#7e8d9d', linewidth=.6)
        ax.scatter(phase, relative, s=3, alpha=.3, color=color, linewidths=0)
        ax.set(title=title, ylabel='Brightness change (%)', xlim=(-window, window))
        ax.title.set_fontsize(10)
        ax.tick_params(labelsize=9)
    bottom.set_xlabel('Hours from predicted dip center')
    buffer = BytesIO()
    canvas.print_png(buffer)
    buffer.seek(0)
    return buffer
