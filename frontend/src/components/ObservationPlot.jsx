import { useEffect, useMemo, useState } from 'react';
import { artifactURL } from '../api/client.js';
import { hoursFromTransit, parsePhotometry } from '../utils/photometry.js';
import BrightnessPlot from './BrightnessPlot.jsx';

export default function ObservationPlot({ runId, title, fit, archived }) {
  const [load, setLoad] = useState({ status: 'loading' });
  const [mode, setMode] = useState('time');
  useEffect(() => {
    const controller = new AbortController();
    async function loadPhotometry() {
      try {
        const response = await fetch(artifactURL(runId, 'photometry'), {
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30000)]),
        });
        if (!response.ok) throw new Error('Photometry unavailable.');
        const data = parsePhotometry(await response.text());
        if (!controller.signal.aborted) setLoad({ status: 'ready', data });
      } catch {
        if (!controller.signal.aborted) setLoad({ status: 'unavailable' });
      }
    }
    loadPhotometry();
    return () => controller.abort();
  }, [runId]);

  const data = load.data;
  const period = fit?.period_days;
  const epoch = fit?.midpoint_bjd;
  const canFold = Number.isFinite(period) && period > 0 && Number.isFinite(epoch);
  const x = useMemo(() => {
    if (!data) return [];
    if (mode === 'folded' && canFold) return hoursFromTransit(data.time, period, epoch);
    return data.time.map(time => time - data.time[0]);
  }, [data, mode, canFold, period, epoch]);

  if (load.status === 'loading') return <p className="muted" role="status">Loading the brightness measurements…</p>;
  if (load.status === 'unavailable') {
    return archived?.length ? archived.map(image => <figure className="curve-figure" key={image.type}>
      <img src={image.data} alt={image.type === 'phase_folded_light_curve' ? 'Archived phase-folded view' : 'Archived light curve'} />
    </figure>) : <p className="muted" role="status">The saved brightness measurements are unavailable.</p>;
  }
  const folded = canFold && mode === 'folded';
  return <>
    {canFold && <div className="plot-controls" role="group" aria-label="Light curve view">
      <button type="button" aria-pressed={mode === 'time'} onClick={() => setMode('time')}>Over time</button>
      <button type="button" aria-pressed={folded} onClick={() => setMode('folded')}>Aligned by trial period</button>
    </div>}
    {folded && <p className="muted">Measurements are aligned to the fitted {period.toFixed(5)}-day schedule. The shading marks the fitted dip window.</p>}
    <BrightnessPlot key={mode} title={folded ? 'Trial-period view' : title} x={x} y={data.brightness}
      xLabel={folded ? 'Time from fitted transit center' : 'Time since first measurement'} xUnit={folded ? 'hours' : 'days'}
      windowHours={folded ? fit.duration_hours : undefined} />
  </>;
}
