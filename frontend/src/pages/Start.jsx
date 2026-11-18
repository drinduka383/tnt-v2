import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import SkyAtlas from '../components/SkyAtlas.tsx';
import EvidenceResults from '../components/EvidenceResults.jsx';
import { createRun, getRun, cancelRun } from '../api/analyze.js';
import { request } from '../api/client.js';
import { sameRegion } from '../utils/mapRegion.js';
import { isTerminal } from '../utils/runState.js';
import './Workbench.css';

export default function Start() {
  const [params, setParams] = useSearchParams();
  const runId = params.get('run');
  const [target, setTarget] = useState({ mission: 'tess', id: '' });
  const [evidence, setEvidence] = useState('combined');
  const [modelName, setModelName] = useState('balanced');
  const [file, setFile] = useState(null);
  const [recent, setRecent] = useState([]);
  const [historyError, setHistoryError] = useState(false);
  const [focus, setFocus] = useState(undefined);
  const [mapMounted, setMapMounted] = useState(() => !runId);
  const [pane, setPane] = useState(() => runId ? 'evidence' : 'map');
  const [record, setRun] = useState(null);
  const run = record?.id === runId ? record : null;
  const [transfer, setTransfer] = useState({ status: 'idle' });
  const [pollError, setPollError] = useState(null);
  const submitting = transfer.status === 'submitting';
  const cancelling = transfer.status === 'cancelling';
  const actionInFlight = submitting || cancelling;
  const actionError = transfer.error;
  const actionLock = useRef(false);
  const submitController = useRef(null);
  const submission = useRef(null);
  const evidencePane = useRef(null);
  useEffect(() => { evidencePane.current?.scrollTo(0,0); window.scrollTo(0,0); }, [runId]);
  const [pollVersion, setPollVersion] = useState(0);
  const [region, setRegion] = useState(null);
  const regionRef = useRef(null);
  const mapRequest = useRef(null);
  const [discovery, setDiscovery] = useState({ status: 'idle', targets: [] });
  const [mapSelected, setMapSelected] = useState(null);
  const mapTargets = discovery.targets;
  const [visibleIds, setVisibleIds] = useState([]);
  const visibleMapTargets = mapTargets.filter(star => visibleIds.includes(star.id));
  const onTargetsVisible = useCallback(ids => {
    setVisibleIds(previous => JSON.stringify(previous) === JSON.stringify(ids) ? previous : ids);
  }, []);
  const onMapView = useCallback(next => {
    if (sameRegion(regionRef.current, next)) return;
    regionRef.current = next;
    mapRequest.current?.abort();
    setRegion(next);
    setVisibleIds([]);
    setDiscovery({ status: 'idle', targets: [] });
  }, []);
  const chooseMapStar = useCallback(id => {
    if (runId || submitting) return;
    const star = mapTargets.find(item => item.id === id);
    if (!star) return;
    setMapSelected(star);
    setTarget({ mission: 'tess', id: star.id });
    setEvidence('combined');
    setFile(null);
  }, [mapTargets, runId, submitting]);
  useEffect(() => () => mapRequest.current?.abort(), []);
  async function searchMap() {
    if (!region || region.radius > .5) return;
    mapRequest.current?.abort();
    const controller = new AbortController();
    mapRequest.current = controller;
    setDiscovery({ status: 'loading', targets: [] });
    try {
      const data = await request(`/sky/targets?${new URLSearchParams(region)}`, { signal: controller.signal });
      if (controller.signal.aborted) return;
      if (!Array.isArray(data.targets)) throw new Error('Invalid map target response.');
      setDiscovery({ ...data, status: data.targets.length ? 'success' : 'empty' });
    } catch (err) {
      if (!controller.signal.aborted) setDiscovery({ status: 'error', targets: [], message: err.message });
    }
  }
  useEffect(() => () => submitController.current?.abort(), []);
  useEffect(() => {
    if (!runId) return;
    const controller = new AbortController();
    let timer;
    let active = true;
    async function poll() {
      try {
        const next = await getRun(runId, controller.signal);
        if (!active) return;
        setRun(next);
        const position = next.result?.manual_search?.raw;
        if (Number.isFinite(position?.ra) && Number.isFinite(position?.dec)) setFocus({ ra:position.ra, dec:position.dec });
        setPollError(null);
        if (!isTerminal(next.status)) timer = setTimeout(poll, 1500);
      } catch (err) {
        if (active && err.name !== 'AbortError') setPollError({ id: runId, message: err.message });
      }
    }
    poll();
    return () => { active = false; controller.abort(); clearTimeout(timer); };
  }, [runId, pollVersion]);

  useEffect(() => {
    const controller = new AbortController();
    request('/runs', { signal:controller.signal }).then(data => { if (!controller.signal.aborted && Array.isArray(data)) { setRecent(data); setHistoryError(false); } }).catch(() => { if (!controller.signal.aborted) setHistoryError(true); });
    return () => controller.abort();
  }, [run?.id, run?.status]);

  async function submit(event, retrySpec = null, capturedUpload = undefined) {
    event?.preventDefault();
    if (actionLock.current) return;
    const spec = retrySpec || { ...target, id: target.id.trim(), evidence, model_name: modelName.trim() };
    const upload = capturedUpload ?? (spec.evidence === 'upload' ? file : null);
    if (!spec.id || (spec.evidence === 'upload' && !upload)) return;
    const sameAttempt = submission.current?.spec && JSON.stringify(submission.current.spec) === JSON.stringify(spec)
      && submission.current.upload === upload;
    if (!sameAttempt) submission.current = { spec, upload, key: crypto.randomUUID() };
    actionLock.current = true;
    setPane('evidence');
    const controller = new AbortController();
    submitController.current = controller;
    setTransfer({ status: 'submitting' });
    try {
      const next = await createRun(spec, upload, controller.signal, submission.current.key);
      if (controller.signal.aborted) return;
      submission.current = null;
      setRun(next);
      setPollError(null);
      setParams({ run: next.id });
      setTransfer({ status: 'idle' });
    } catch (err) {
      if (!controller.signal.aborted) setTransfer({ status: 'submit_error', error: err.message, spec, upload });
    } finally {
      actionLock.current = false;
    }
  }
  function returnToTarget() {
    setTransfer({ status: 'idle' });
    setPollError(null);
    if (run?.spec) {
      setTarget({ mission:run.spec.target.mission, id:`${run.spec.target.namespace} ${run.spec.target.id}` });
      setEvidence(run.spec.evidence);
      setModelName(run.spec.model?.name || 'balanced');
      setMapSelected(null);
    }
    setRun(null);
    setParams({});
    setMapMounted(true);
    setPane('map');
  }
  async function back() {
    if (actionLock.current) return;
    if (!run || isTerminal(run.status)) {
      returnToTarget();
      return;
    }
    actionLock.current = true;
    setTransfer({ status: 'cancelling' });
    try {
      await cancelRun(run.id);
      returnToTarget();
    } catch (err) {
      setTransfer({ status: 'cancel_error', error: err.message });
    } finally {
      actionLock.current = false;
    }
  }
  function openSavedRun(id) {
    setPane('evidence');
    if (id === runId) return;
    setRun(null);
    setPollError(null);
    setTransfer({ status: 'idle' });
    setParams({ run: id });
  }
  function retryRun() {
    const spec = run?.spec;
    if (!spec) return;
    submit(null, { mission: spec.target.mission, id: `${spec.target.namespace} ${spec.target.id}`, evidence: spec.evidence, model_name: spec.model?.name || 'balanced' });
  }
  const result = run?.result;
  const atlasTarget = focus;

  const connectionError = pollError?.id === runId ? pollError.message : null;
  const activeRun = run && !isTerminal(run.status);
  const busy = actionInFlight || Boolean(!connectionError && (activeRun || (runId && !run)));
  const backLabel = cancelling ? 'Cancelling?' : activeRun ? 'Cancel and return' : 'Change target';
  const stageLabels = { queued: 'Waiting for the worker', resolving_target: 'Resolving the target', loading_catalog: 'Looking up published candidates', locating_tess_pixels: 'Checking full-frame TESS coverage', downloading_tess_pixels: 'Downloading a TESS pixel cutout', checking_published_signal: 'Checking the published transit times and follow-up', acquiring_observation: 'Looking up and downloading observations', extracting_features: 'Reading the light curve', classifying: 'Checking model eligibility' };
  const runTarget = run?.spec?.target;
  const targetLabel = runTarget ? `${runTarget.namespace} ${runTarget.id}` : target.id || 'No target selected';
  const plotCount = result?.processed_json?.reduce((total,item) => total + (item.visualizations?.length || 0), 0) || 0;
  const hasResult = result && (result.sources || plotCount > 0 || result.candidates?.length > 0);
  const sourceFailed = Object.values(result?.sources || {}).some(source => source.status === 'failed');
  const canUpdate = run?.spec?.evidence === 'combined' && run.spec.target.mission === 'tess'
    && result?.provenance?.processing_version === 'tnt-v2-evidence-3';

  const formTarget = run?.spec ? { mission:run.spec.target.mission, id:`${run.spec.target.namespace} ${run.spec.target.id}` } : target;
  const formEvidence = run?.spec?.evidence || evidence;

  return <main className="workbench">
    <aside className="workbench-panel">
      <header className="workspace-brand"><Link to="/">A WORLD AWAY</Link><h1>Stellar evidence</h1><p>Choose a star. Load its measurements.</p></header>
      <form onSubmit={submit} className="target-form">
        <fieldset disabled={Boolean(runId) || actionInFlight}>
          <label>Mission<select value={formTarget.mission} onChange={e => { setTarget({ mission: e.target.value, id: '' }); setMapSelected(null); setFile(null); }}><option value="tess">TESS</option><option value="kepler">Kepler</option></select></label>
          <label>{formTarget.mission === 'tess' ? 'TIC host or TOI candidate' : 'KIC host or KOI candidate'}<input required maxLength={40} value={formTarget.id} onChange={e => { setTarget({ ...target, id:e.target.value }); setMapSelected(null); }} placeholder={target.mission === 'tess' ? 'e.g. TIC 67882510' : 'e.g. KIC 11446443'} /></label>
          <details className="processing-options"><summary>Analysis options</summary>
          <label>Evidence source<select value={formEvidence} onChange={e => setEvidence(e.target.value)}><option value="combined">Observation and catalog</option><option value="lightcurve">Observed light curve only</option><option value="catalog">Published candidate catalog</option><option value="upload">My FITS observation</option></select></label>
          {!runId && formEvidence === 'upload' && <label>FITS file<input required type="file" accept=".fits,.fit" onChange={e => setFile(e.target.files?.[0] || null)} /></label>}
          <label>Catalog model ID<input required value={run?.spec?.model?.name || modelName} onChange={e => setModelName(e.target.value)} /></label><p className="muted">The model scores eligible published candidates.</p></details>
        </fieldset>
        {!runId ? <button className="primary-action" disabled={submitting || !target.id.trim() || (evidence === 'upload' && !file)}>{submitting ? 'Starting...' : 'Analyze target'}</button> : <button type="button" className="secondary full-width" disabled={actionInFlight} onClick={back}>{backLabel}</button>}
        {!runId && !target.id && <button type="button" className="text-button" onClick={() => { setTarget({ mission:'tess',id:'50365310' }); setEvidence('combined'); setMapSelected(null); }}>Try example TIC 50365310</button>}
      </form>
      {!runId && mapSelected && <section className="selection-card" aria-label="Selected map star">
        <div className="selection-heading"><span className="eyebrow">Selected from map</span><h2>Selected TIC {mapSelected.id}</h2></div>
        <p className="muted">RA {mapSelected.ra.toFixed(4)} / Dec {mapSelected.dec.toFixed(4)}{mapSelected.temperature ? ` / ${Math.round(mapSelected.temperature)} K` : ''}</p>
      </section>}
      {!runId && <section className="map-discovery" aria-label="Map target selection">
        <div className="section-heading"><h2>Find stars on the map</h2></div>
        <p className="muted">Pan or zoom, then search. Select a cyan marker or a star below.</p>
        {!region && <p role="status" className="muted">Sky map is loading. You can also enter an ID above.</p>}
        {region && region.radius > .5 && <p role="status">Zoom in until the field diagonal is under one degree.</p>}
        {discovery.status === 'empty' && <p role="status">No matching TIC stars in this region.</p>}
        {discovery.status === 'error' && <p role="alert">{discovery.message}</p>}
        {discovery.status === 'success' && <>
          <p role="status" className="muted">{visibleMapTargets.length} stars in view{discovery.limited ? ` / search capped at ${discovery.limit} matches` : ''}</p>
          <ul className="map-targets" aria-label="Stars in searched region">{visibleMapTargets.map(star => <li key={star.id}><button type="button" aria-pressed={mapSelected?.id === star.id} onClick={() => chooseMapStar(star.id)}><span>TIC {star.id}</span><small>mag {star.magnitude?.toFixed(1) ?? '?'}</small></button></li>)}</ul>
        </>}
      </section>}
      {recent.length > 0 && <details className="recent-runs"><summary>Recent runs</summary><ul>{recent.map(item => <li key={item.id}><button type="button" disabled={actionInFlight} onClick={() => openSavedRun(item.id)}><span>{item.target.namespace} {item.target.id}</span><small>{item.has_evidence ? 'Evidence saved' : item.status.replaceAll('_',' ')} / {new Date(item.created * 1000).toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' })}</small></button></li>)}</ul></details>}
      {historyError && <p className="muted">Saved runs are unavailable while the service is disconnected.</p>}
      <p className="sidebar-note">Sky imagery, observations and model scores are separate evidence sources. A score does not confirm a planet.</p>
    </aside>
    <section className="workbench-content">
      <header className="view-header"><div className="view-switch" aria-label="Workspace view"><button type="button" aria-pressed={pane === 'map'} onClick={() => { setMapMounted(true); setPane('map'); }}>Sky map</button><button type="button" aria-pressed={pane === 'evidence'} onClick={() => setPane('evidence')}>Evidence</button></div><span className="current-target">{targetLabel}</span>{runId && <button type="button" className="mobile-target-action secondary" disabled={actionInFlight} onClick={back}>{activeRun ? 'Cancel' : 'New target'}</button>}</header>
      {pane === 'map' && !runId && <div className="map-analysis-action">
        <button type="button" className="secondary" onClick={searchMap} disabled={actionInFlight || !region || region.radius > .5 || discovery.status === 'loading'}>
          {discovery.status === 'loading' ? 'Searching region?' : 'Search this view'}
        </button>
        {mapSelected ? <button type="button" disabled={actionInFlight} onClick={() => submit(null, { mission: 'tess', id: mapSelected.id, evidence: 'combined', model_name: modelName.trim() })}>Analyze TIC {mapSelected.id}</button>
          : <span>{region?.radius > .5 ? 'Zoom in to search' : 'Select a star marker'}</span>}
      </div>}
      <div className="map-stage" hidden={pane !== 'map'}>{mapMounted && <SkyAtlas target={atlasTarget} fov={.5} stars={runId || submitting ? [] : mapTargets} selectedId={mapSelected?.id} onViewChange={onMapView} onSelect={chooseMapStar} onTargetsVisible={onTargetsVisible} />}</div>
      <div ref={evidencePane} className="evidence-stage" hidden={pane !== 'evidence'}>
        {connectionError && <div role="alert" className="error-card"><h2>Connection interrupted</h2><p>{connectionError}</p><button onClick={() => setPollVersion(value => value+1)}>Reconnect to saved run</button></div>}
        {actionError && <div role="alert" className="error-card"><h2>{transfer.status === 'submit_error' ? 'Could not start analysis' : 'Could not cancel analysis'}</h2><p>{actionError}</p>{transfer.status === 'submit_error' && <button onClick={() => submit(null, transfer.spec, transfer.upload)}>Retry starting analysis</button>}</div>}
        {busy && <section className="loading-evidence" aria-live="polite"><span className="status-chip">{run?.status === 'accepted' && !submitting ? 'Queued' : 'Working'}</span><h2>{cancelling ? 'Cancelling analysis' : 'Loading evidence'}</h2><p>{submitting ? 'Starting a saved analysis run?' : cancelling ? 'Waiting for the service to confirm cancellation.' : stageLabels[run?.stage] || 'Contacting the analysis service?'}</p></section>}
        {!submitting && run?.error && <section className="error-card" role="alert"><span className="eyebrow">{run.status === 'insufficient_evidence' ? 'No usable evidence returned' : 'Source request failed'}</span><h2>{run.error.code === 'upstream_unavailable' ? 'The archive did not respond' : 'This run could not finish'}</h2><p>{run.error.message}</p><p className="muted">This is a data-acquisition issue, not a planetary verdict.</p><button onClick={retryRun} disabled={submitting || (run.spec?.evidence === 'upload' && !file)}>Retry this target</button>{run.spec?.evidence === 'upload' && !file && <p>Change target to reselect your FITS file.</p>}</section>}
        {hasResult && <EvidenceResults run={run} onRetry={(sourceFailed || canUpdate) && !actionInFlight ? retryRun : undefined} retryLabel={canUpdate ? 'Run updated analysis' : undefined} />}
        {!busy && !run?.error && !hasResult && !connectionError && !actionError && <section className="empty-evidence"><p className="eyebrow">Observation workspace</p><h2>{run?.status === 'cancelled' ? 'Run cancelled' : 'Choose a target to begin'}</h2><p>Load an observation to see the measured light curve, source metadata and downloadable data here.</p><button type="button" className="secondary" onClick={() => { setMapMounted(true); setPane('map'); }}>Explore the sky map</button></section>}
      </div>
    </section>
  </main>;
}
