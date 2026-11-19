import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import './SignalCheck.css';
import BrightnessPlot from './BrightnessPlot.jsx';
import { extent } from '../utils/photometry.js';
import ObservationPlot from './ObservationPlot.jsx';
import { artifactURL, request } from '../api/client.js';
import { toPercent } from '../utils/normalizeResults.js';

const number = (value, digits = 2) => typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString(undefined, { maximumFractionDigits: digits }) : 'Not recorded';

const sourceLabels = { catalog: 'Published catalog', observation: 'Light curve', followup: 'Published follow-up' };
const sourceStates = { ready: 'Available', empty: 'No usable data', failed: 'Could not load', unavailable: 'Could not load', skipped: 'Not checked' };
const modelStates = { scored: 'Model scored', partially_scored: 'Some candidates scored',
  unscored: 'Model not scored', unavailable: 'Model unavailable', no_candidates: 'No candidates to score' };
const featureLabels = { st_loggerr2: 'lower surface gravity uncertainty', pl_orbpererr1: 'upper orbital period uncertainty',
  pl_trandurherr1: 'upper transit duration uncertainty', pl_trandurherr2: 'lower transit duration uncertainty',
  pl_trandeperr1: 'upper transit depth uncertainty', pl_trandeperr2: 'lower transit depth uncertainty' };

const dispositions = { FP: 'False positive', FA: 'False alarm', CP: 'Confirmed planet', KP: 'Known planet',
  PC: 'Planet candidate', APC: 'Ambiguous candidate', 'FALSE POSITIVE': 'False positive',
  CONFIRMED: 'Confirmed planet', CANDIDATE: 'Candidate' };

function ReportSection({ title, open, children }) {
  return <details className="report-section" open={open}>
    <summary><h2>{title}</h2></summary>
    {children}
  </details>;
}

function PublishedSignal({ candidate }) {
  const check = candidate.ephemeris;
  if (!check) return null;
  return <ReportSection title={`TOI ${candidate.id} at the published period`}>
    {check.status === 'measured' ? <>
      <p>Folded at {number(check.period_days, 5)} days using the published transit time. The measurements show whether flux changes repeat at the expected times.</p>
      <div className="table-scroll"><table>
        <thead><tr><th>Window</th><th>Covered events</th><th>Depth (ppm)</th><th>Standard error across events (ppm)</th></tr></thead>
        <tbody>{[['Published transit', check.primary], ['Half an orbit later', check.half_period]].map(([label, data]) =>
          <tr key={label}><th scope="row">{label}</th><td>{data.events}</td><td>{number(data.depth_ppm, 0)}</td><td>{number(data.event_sem_ppm, 0)}</td></tr>)}</tbody>
      </table></div>
      {check.plot && <figure className="curve-figure"><img src={check.plot} alt="Brightness at published transit times and half an orbit later" /></figure>}
      <p className="muted">A dip can come from any star in the aperture. To locate it, compare in-transit and out-of-transit pixel images or use higher resolution follow-up.</p>
    </> : <p className="muted">{({ missing_ephemeris: 'A usable period, epoch and duration are required.',
      insufficient_coverage: 'This observation covers fewer than two usable predicted transits.',
      skipped_limit: 'The automatic timing check is limited to the first three published candidates.',
      skipped_no_observation: 'The timing check needs a light curve.',
      unavailable: 'The published timing check could not be completed.' })[check.status]}</p>}
  </ReportSection>;
}

const checkReasons = {
  insufficient_event_coverage: 'Too few predicted events had measurements in the dip and on both sides.',
  mixed_or_insensitive_measurements: 'The predicted windows had mixed or insufficient measurements.',
  consistent_dimming_at_predicted_times: 'The independent data show dimming at the predicted times.',
  original_depth_recoverable_at_predicted_times: 'A dip close to the original depth was recoverable in these windows, but was absent from the measured flux.',
  different_photometry: 'The independent extraction may change the depth of the dip, so its absence here is inconclusive.',
  no_independent_sector: 'The archive listed no other sector.',
  independent_observation_unavailable: 'The independent observation could not be downloaded or measured.',
  independent_cadence_too_coarse: 'The independent exposures are too far apart for this dip duration.',
  timing_prediction_too_far: 'The new observations are too far from the original data for the trial timing to be reliable.',
};

function EventTable({ events }) {
  return <div className="table-scroll"><table>
    <thead><tr><th>Predicted time (BJD)</th><th>Samples in dip</th><th>Before / after</th><th>Measured depth (ppm)</th></tr></thead>
    <tbody>{events.map(event => <tr key={event.cycle}>
      <td>{number(event.midpoint_bjd, 5)}</td><td>{event.in_dip}</td><td>{event.before} / {event.after}</td>
      <td>{event.depth_ppm == null ? 'Insufficient coverage' : number(event.depth_ppm, 0)}</td>
    </tr>)}</tbody>
  </table></div>;
}

function ObservationComparison({ runId }) {
  const [view, setView] = useState('side-by-side');
  const [load, setLoad] = useState({ status: 'loading' });
  useEffect(() => {
    const controller = new AbortController();
    request(`/runs/${encodeURIComponent(runId)}/signal-comparison.json`, { signal: controller.signal })
      .then(data => {
        if (controller.signal.aborted) return;
        const [original, independent] = data.series;
        setLoad({
          status: 'ready',
          original,
          independent,
          overlay: {
            x: independent.hours, y: independent.brightness_change_percent,
            originalLabel: `Original · Sector ${original.sector}`,
            independentLabel: `Independent · Sector ${independent.sector}`,
          },
          axes: {
            xRange: [-data.window_hours, data.window_hours],
            yRange: extent(data.series.map(series => series.brightness_change_percent)),
            windowHours: data.duration_hours,
            xLabel: 'Time from predicted dip center',
            xUnit: 'hours',
          },
        });
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoad({ status: 'unavailable' });
      });
    return () => controller.abort();
  }, [runId]);
  return <ReportSection title="Compare observations" open>
    <p className="muted">Both sectors use the original timing and the same scale. Shading marks the predicted dip window.</p>
    {load.status === 'loading' && <p className="muted" role="status">Loading the comparison…</p>}
    {load.status === 'unavailable' && <p className="muted" role="status">The saved comparison measurements are unavailable.</p>}
    {load.status === 'ready' && <>
      <div className="plot-controls" role="group" aria-label="Observation comparison view">
        <button type="button" aria-pressed={view === 'side-by-side'} onClick={() => setView('side-by-side')}>Side by side</button>
        <button type="button" aria-pressed={view === 'overlay'} onClick={() => setView('overlay')}>Overlay</button>
      </div>
      {view === 'overlay'
        ? <BrightnessPlot key="overlay" title="Original and independent observations overlaid"
            x={load.original.hours} y={load.original.brightness_change_percent} overlay={load.overlay} {...load.axes} />
        : <div className="observation-pair">
            <BrightnessPlot title={load.overlay.originalLabel} x={load.original.hours} y={load.original.brightness_change_percent} {...load.axes} />
            <BrightnessPlot title={load.overlay.independentLabel} x={load.independent.hours} y={load.independent.brightness_change_percent} tone="independent" {...load.axes} />
          </div>}
    </>}
  </ReportSection>;
}

function SignalCheckResult({ run }) {
  const check = run.result.signal_check;
  const verdict = { repeats: 'Dip repeats at predicted times', did_not_repeat: 'Dip did not repeat at predicted times', inconclusive: 'Inconclusive' }[check.status];
  const original = check.events || [];
  const independent = check.independent_events || [];
  const parentId = run.spec.parent_run;
  const refits = check.refits || [];
  const periods = refits.map(refit => refit.best_period_days);
  const stable = periods.length > 0 && periods.every(period => period.toFixed(5) === check.proposed_period_days.toFixed(5));
  return <article className="evidence-result signal-dashboard">
    <p className="report-context"><Link to={`?run=${encodeURIComponent(parentId)}`}>Back to original analysis</Link></p>
    <ReportSection title="Original light curve" open>
      {parentId && <ObservationPlot key={parentId} runId={parentId} title={`TESS sector ${check.source_sector}`} />}
    </ReportSection>
    <div className="signal-verdict" data-verdict={check.status}>
      <ReportSection title={verdict} open>
        <p>{check.usable_events != null && independent.length > 0
          ? `${check.usable_events} of ${independent.length} predicted windows measured in sector ${check.independent_sector}.`
          : checkReasons[check.reason]}</p>
        {check.usable_events != null && independent.length > 0 && check.status !== 'repeats' && <p>{checkReasons[check.reason]}</p>}
      </ReportSection>
    </div>
    {check.independent_source && <ObservationComparison runId={run.id} />}
    {run.spec.published_context?.length > 0 && <ReportSection title="Published follow-up for this star" open>
      <ul>{run.spec.published_context.map(row => <li key={row.id}>TOI {row.id}: {dispositions[row.disposition] || row.disposition}
        {row.followup?.comment && <>. {row.followup.comment.replace(/\bNEB\b/g, 'nearby eclipsing binary')}</>}
      </li>)}</ul>
    </ReportSection>}
    <ReportSection title="Signal check details">
      <p>Fixed interval: {number(check.proposed_period_days, 5)} days. Repetition alone cannot identify the source or confirm a planet.</p>
      <details className="report-subsection" open><summary><h3>Does one dip drive the result?</h3></summary>
        <p>{stable ? `The best period stayed at ${number(check.proposed_period_days, 5)} days in all ${refits.length} refits.`
          : periods.length ? `Removing individual events gave best periods from ${number(Math.min(...periods), 5)} to ${number(Math.max(...periods), 5)} days.`
            : 'No event had enough coverage for a leave-one-out refit.'}</p>
        {periods.length > 0 && <details><summary>Individual refits</summary><ul>{refits.map(refit =>
          <li key={refit.omitted_cycle}>Cycle {refit.omitted_cycle}: {number(refit.best_period_days, 5)} days</li>)}</ul></details>}
      </details>
      {check.injection_recovered != null && <details className="report-subsection" open><summary><h3>Could the data see this dip?</h3></summary>
        <p>{check.injection_recovered ? 'Yes. The check recovered a simulated dip of the original depth in these windows.' : 'The check could not reliably recover a simulated dip of the original depth in these windows.'}</p>
      </details>}
    </ReportSection>
    <ReportSection title="Exact event measurements">
      <details className="report-subsection signal-raw" open><summary><h3>Original data, sector {check.source_sector}</h3></summary><EventTable events={original} /></details>
      {independent.length > 0 && <details className="report-subsection signal-raw" open><summary><h3>Independent data, sector {check.independent_sector}</h3></summary><EventTable events={independent} /></details>}
    </ReportSection>
  </article>;
}

export default function EvidenceResults({ run, onCheck, onRetry, retryLabel = 'Retry this target' }) {
  const result = run.result;
  if (!result) return null;
  if (result.signal_check) return <SignalCheckResult key={run.id} run={run} />;
  const processed = result.processed_json || [];
  const plots = processed.flatMap(item => item.visualizations || []);
  const photometry = processed[0]?.photometry;
  const fit = processed[0]?.parameters || {};
  const quality = processed[0]?.quality;
  const provenance = result.provenance || {};
  const observation = provenance.observation;
  const stellar = result.manual_search?.stellar || {};
  const candidates = result.candidates || [];
  const hasScore = candidates.some(item => item.status === 'scored');
  const hasCurve = result.artifacts?.photometry || plots.length > 0;
  const ready = hasCurve || result.evidence_status === 'ready' || hasScore;
  const sources = result.sources || {};
  const target = provenance.target || run.spec?.target;
  const isTess = target?.namespace === 'TIC';
  const cutout = observation?.kind === 'pixel_cutout';
  const catalogRows = provenance.evidence === 'catalog' || provenance.evidence === 'combined';
  const modelLabel = modelStates[result.model_status] || (hasScore ? 'Model scored' : 'Model not scored');
  return <article className="evidence-result">
    {!ready && <h2 className="report-heading">No usable evidence returned</h2>}
    {quality && <ReportSection title="Transit search" open>
      <p>{quality.message || ((quality.outcome ? quality.outcome === 'screen_passed' : quality.exploratory_signal) ? 'An exploratory periodic signal passed the search rule. It requires further vetting.' : 'No strong transit signal passed the current search rule. This does not establish that the star has no planets.')}</p>
      {fit.period_days != null && <dl className="evidence-metrics"><div><dt>Best trial period</dt><dd>{number(fit.period_days,4)} days</dd></div><div><dt>Fitted depth</dt><dd>{number(fit.depth_fraction * 1e6)} ppm</dd></div><div><dt>Covered events</dt><dd>{number(fit.transits_covered,0)}</dd></div><div><dt>Depth / error</dt><dd>{number(fit.snr)}</dd></div></dl>}
      {onCheck && isTess && fit.midpoint_bjd != null && observation?.group != null &&
        Number.isFinite(result.manual_search?.raw?.ra) && Number.isFinite(result.manual_search?.raw?.dec) &&
        <button type="button" className="report-action" onClick={onCheck}>Check this signal</button>}
    </ReportSection>}
    {hasCurve && <ReportSection title="Light curve" open>
    {cutout && <p className="information-note">Extracted from a TESS full-frame pixel cutout with a 3 × 3 aperture and local background subtraction. Nearby stars and detector effects can influence the result.</p>}
    {photometry && <dl className="evidence-metrics">
      <div><dt>Valid samples</dt><dd>{number(photometry.samples,0)}</dd></div>
      <div><dt>Coverage</dt><dd>{number(photometry.baseline_days)} days</dd></div>
      <div><dt>Pipeline</dt><dd>{observation?.author || 'Uploaded data'}</dd></div>
      <div><dt>Observation</dt><dd>{observation?.group != null ? `Sector / quarter ${observation.group}` : 'FITS file'}</dd></div>
    </dl>}
      <ObservationPlot key={run.id} runId={run.id} title="Observed stellar brightness over time" fit={fit} archived={plots} />
    </ReportSection>}
    <ReportSection title="Evidence sources" open={!hasCurve || Boolean(onRetry)}>
    {Object.keys(sources).length > 0 && <dl className="evidence-sources">
      {Object.entries(sources).map(([kind, source]) => <div key={kind}>
        <dt>{sourceLabels[kind]}</dt><dd>{kind === 'catalog' && source.status === 'empty' ? 'No candidates listed' : sourceStates[source.status]}{source.message && <small>{source.message}</small>}</dd>
      </div>)}
    </dl>}
    {!(result.model_status === 'no_candidates' && sources.catalog?.status === 'empty') && <p className="muted">{modelLabel}</p>}
    {target && isTess && <p><a href={`https://exofop.ipac.caltech.edu/tess/target.php?id=${encodeURIComponent(target.id)}`} target="_blank" rel="noreferrer">Open this target in ExoFOP</a></p>}
    {onRetry && <button type="button" className="secondary report-action" onClick={onRetry}>{retryLabel}</button>}
    </ReportSection>
    {(catalogRows || hasScore) && candidates.length > 0 && <ReportSection title={catalogRows ? 'Published candidates and model scores' : 'Saved model scores'} open={!hasCurve}>
      <p className="muted">Scores help rank candidates for review. Planet status comes from published follow-up.</p>
      <p className="muted">{candidates.filter(item => item.status === 'scored').length} of {candidates.length} scored by {provenance.model?.name || 'the catalog model'}.</p>
      <div className="table-scroll catalog-results"><table>
        <thead><tr><th>Candidate</th><th>Published disposition</th><th>Period (days)</th><th>Duration (h)</th><th>Depth (ppm)</th><th>Model result</th><th>Candidate-class score</th></tr></thead>
        <tbody>{candidates.map(item => <tr key={item.id}>
          <th scope="row">{catalogRows && isTess ? `TOI ${item.id}` : item.id}</th><td>
            {dispositions[item.catalog_disposition] || item.catalog_disposition || 'Not established'}
            {item.followup && <small className="model-reason">
              {item.followup.disposition && item.followup.disposition !== item.catalog_disposition && <span>ExoFOP lists {dispositions[item.followup.disposition] || item.followup.disposition}. </span>}
              {item.followup.comment && <span>{item.followup.comment.replace(/\bNEB\b/g, 'nearby eclipsing binary')} </span>}
              <a href={item.followup.source} target="_blank" rel="noreferrer">ExoFOP record</a>
            </small>}
          </td>
          <td>{number(item.measurements?.period_days,4)}</td><td>{number(item.measurements?.duration_hours)}</td><td>{number(item.measurements?.depth_ppm)}</td>
          <td>{item.status === 'scored' ? item.class : <>
            {item.status === 'unavailable' ? 'Unavailable' : 'Unscored'}
            {item.invalid_features?.length > 0 && <details><summary>{item.invalid_features.length} required fields missing or invalid</summary><ul>{item.invalid_features.map(name => <li key={name}>{featureLabels[name] || name}</li>)}</ul></details>}
            {!item.invalid_features?.length && item.message && <small className="model-reason">{item.message}</small>}
          </>}</td><td>{item.status === 'scored' ? `${toPercent(item.probability)}%` : '—'}</td>
        </tr>)}</tbody>
      </table></div>
    </ReportSection>}
    {candidates.map(candidate => <PublishedSignal key={candidate.id} candidate={candidate} />)}
    {photometry?.preview?.length > 0 && <ReportSection title="Preview the measurement table"><div className="table-scroll"><table><thead><tr><th>Time (BJD)</th><th>Normalized flux</th></tr></thead><tbody>{photometry.preview.map(([time,flux],index) => <tr key={index}><td>{time.toFixed(6)}</td><td>{flux.toFixed(7)}</td></tr>)}</tbody></table></div></ReportSection>}
    {(result.artifacts?.photometry || result.artifacts?.observation || result.artifacts?.evidence) && <ReportSection title="Download evidence">
      <ul className="evidence-downloads">
        {result.artifacts?.photometry && <li><a href={artifactURL(run.id,'photometry')}>Download photometry CSV</a></li>}
        {result.artifacts?.observation && <li><a href={artifactURL(run.id,'observation')}>{cutout ? 'Download FITS pixel cutout' : 'Original FITS observation'}</a></li>}
        {result.artifacts?.evidence && <li><a href={artifactURL(run.id,'evidence')}>Evidence record</a></li>}
      </ul>
    </ReportSection>}
    <ReportSection title="Stellar properties and source record"><dl className="evidence-metrics"><div><dt>Temperature</dt><dd>{number(stellar.st_teff,0)} K</dd></div><div><dt>Radius</dt><dd>{number(stellar.st_rad)} solar radii</dd></div></dl><pre>{JSON.stringify(provenance,null,2)}</pre></ReportSection>
    <ReportSection title="Model diagnostics"><pre>{JSON.stringify(candidates,null,2)}</pre></ReportSection>
  </article>;
}
