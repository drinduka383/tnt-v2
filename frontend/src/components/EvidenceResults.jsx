import { artifactURL } from '../api/client.js';
import { toPercent } from '../utils/normalizeResults.js';

const number = (value, digits = 2) => typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString(undefined, { maximumFractionDigits: digits }) : 'Not recorded';

const sourceLabels = { catalog: 'Published catalog', observation: 'Light curve' };
const sourceStates = { ready: 'Available', empty: 'No usable data', failed: 'Could not load' };
const modelStates = { scored: 'Model scored', partially_scored: 'Some candidates scored',
  unscored: 'Model not scored', unavailable: 'Model unavailable', no_candidates: 'No candidates to score' };
const featureLabels = { st_loggerr2: 'lower surface gravity uncertainty', pl_orbpererr1: 'upper orbital period uncertainty',
  pl_trandurherr1: 'upper transit duration uncertainty', pl_trandurherr2: 'lower transit duration uncertainty',
  pl_trandeperr1: 'upper transit depth uncertainty', pl_trandeperr2: 'lower transit depth uncertainty' };

const dispositions = { FP: 'False positive', FA: 'False alarm', CP: 'Confirmed planet', KP: 'Known planet',
  PC: 'Planet candidate', APC: 'Ambiguous candidate', 'FALSE POSITIVE': 'False positive',
  CONFIRMED: 'Confirmed planet', CANDIDATE: 'Candidate' };

function PublishedSignal({ candidate }) {
  const check = candidate.ephemeris;
  if (!check) return null;
  return <details className="result-section">
    <summary>TOI {candidate.id} ? check at the published period</summary>
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
      unavailable: 'The published timing check could not be completed.' })[check.status]}</p>}
  </details>;
}

export default function EvidenceResults({ run, onRetry, retryLabel = 'Retry this target' }) {
  const result = run.result;
  if (!result) return null;
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
  const ready = plots.length > 0 || result.evidence_status === 'ready' || hasScore;
  const sources = result.sources || {};
  const target = provenance.target || run.spec?.target;
  const isTess = target?.namespace === 'TIC';
  const cutout = observation?.kind === 'pixel_cutout';
  const catalogRows = provenance.evidence === 'catalog' || provenance.evidence === 'combined';
  const modelLabel = modelStates[result.model_status] || (hasScore ? 'Model scored' : 'Model not scored');
  return <article className="evidence-result">
    <div className="result-title"><h2>{ready ? 'Evidence ready' : 'No usable evidence returned'}</h2><span className="status-chip">{modelLabel}</span></div>
    {target && <p className="result-intro">Target {target.namespace} {target.id}{isTess && <> ? <a href={`https://exofop.ipac.caltech.edu/tess/target.php?id=${encodeURIComponent(target.id)}`} target="_blank" rel="noreferrer">TESS target and follow-up records</a></>}</p>}
    {Object.keys(sources).length > 0 && <dl className="evidence-sources">
      {Object.entries(sources).map(([kind, source]) => <div key={kind}>
        <dt>{sourceLabels[kind]}</dt><dd>{sourceStates[source.status]}{source.message && <small>{source.message}</small>}</dd>
      </div>)}
    </dl>}
    {onRetry && <button type="button" className="secondary" onClick={onRetry}>{retryLabel}</button>}
    {(catalogRows || hasScore) && candidates.length > 0 && <section className="result-section catalog-results">
      <h3>{catalogRows ? 'Published candidates and model scores' : 'Saved model scores'}</h3>
      <p className="muted">{candidates.filter(item => item.status === 'scored').length} of {candidates.length} scored by {provenance.model?.name || 'the catalog model'}.{catalogRows && ' Scores help rank catalog candidates for review.'}</p>
      <div className="table-scroll"><table>
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
          </>}</td><td>{item.status === 'scored' ? `${toPercent(item.probability)}%` : '?'}</td>
        </tr>)}</tbody>
      </table></div>
    </section>}
    <div className="evidence-downloads" aria-label="Download evidence">
      {result.artifacts?.photometry && <a href={artifactURL(run.id,'photometry')}>Download photometry CSV</a>}
      {result.artifacts?.observation && <a href={artifactURL(run.id,'observation')}>{cutout ? 'Download FITS pixel cutout' : 'Original FITS observation'}</a>}
      {result.artifacts?.evidence && <a href={artifactURL(run.id,'evidence')}>Evidence record</a>}
    </div>
    {cutout && <p className="information-note">Extracted from a TESS full-frame pixel cutout with a 3 ? 3 aperture and local background subtraction. Nearby stars and detector effects can influence the result.</p>}
    {photometry && <dl className="evidence-metrics">
      <div><dt>Valid samples</dt><dd>{number(photometry.samples,0)}</dd></div>
      <div><dt>Coverage</dt><dd>{number(photometry.baseline_days)} days</dd></div>
      <div><dt>Pipeline</dt><dd>{observation?.author || 'Uploaded data'}</dd></div>
      <div><dt>Observation</dt><dd>{observation?.group != null ? `Sector / quarter ${observation.group}` : 'FITS file'}</dd></div>
    </dl>}
    {plots.map((image,index) => <figure className="curve-figure" key={index}>
      <figcaption><h3>{image.type === 'phase_folded_light_curve' ? 'Phase-folded view' : 'Light curve'}</h3><p>{image.type === 'phase_folded_light_curve' ? 'Brightness aligned at the best-fitting trial period. This alone is not a planet detection.' : 'Each point is a measured brightness sample, after quality filtering and normalization.'}</p></figcaption>
      <img src={image.data} alt={image.type === 'phase_folded_light_curve' ? 'Phase-folded stellar brightness measurements' : 'Observed stellar brightness over time'} />
      {photometry && <p className="muted">Showing {number(photometry.plotted_samples,0)} of {number(photometry.samples,0)} actual samples. The CSV retains all valid samples.</p>}
    </figure>)}
    {quality && <section className="result-section"><h3>Transit search</h3>
      <p>{quality.message || (quality.exploratory_signal ? 'An exploratory periodic signal passed the search rule. It requires further vetting.' : 'No strong transit signal passed the current search rule. This does not establish that the star has no planets.')}</p>
      {fit.period_days != null && <dl className="evidence-metrics"><div><dt>Best trial period</dt><dd>{number(fit.period_days,4)} days</dd></div><div><dt>Fitted depth</dt><dd>{number(fit.depth_fraction * 1e6)} ppm</dd></div><div><dt>Covered events</dt><dd>{number(fit.transits_covered,0)}</dd></div><div><dt>Depth / error</dt><dd>{number(fit.snr)}</dd></div></dl>}
    </section>}
    {candidates.map(candidate => <PublishedSignal key={candidate.id} candidate={candidate} />)}
    {!catalogRows && !hasScore && <p className="muted">Catalog scoring requires published candidate measurements. Choose Observation and catalog to include it in an analysis.</p>}
    {photometry?.preview?.length > 0 && <details className="result-section"><summary>Preview the measurement table</summary><div className="table-scroll"><table><thead><tr><th>Time (BJD)</th><th>Normalized flux</th></tr></thead><tbody>{photometry.preview.map(([time,flux],index) => <tr key={index}><td>{time.toFixed(6)}</td><td>{flux.toFixed(7)}</td></tr>)}</tbody></table></div></details>}
    <details className="result-section"><summary>Stellar properties and source record</summary><dl className="evidence-metrics"><div><dt>Temperature</dt><dd>{number(stellar.st_teff,0)} K</dd></div><div><dt>Radius</dt><dd>{number(stellar.st_rad)} solar radii</dd></div></dl><pre>{JSON.stringify(provenance,null,2)}</pre></details>
    <details className="result-section"><summary>Model diagnostics</summary><pre>{JSON.stringify(candidates,null,2)}</pre></details>
  </article>;
}
