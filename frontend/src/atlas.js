import { mapRegion } from './utils/mapRegion.js';
import { selectSurvey, surveyMirrors } from './utils/skySurvey.js';
// A disposable document owns the SDK's WebGL context, timers and event listeners.
let atlas;
let catalog;
let sources = [];
let previousRegion;
let regionTimer;
function publishRegion() {
  if (!atlas) return;
  const [ra, dec] = atlas.getRaDec();
  const region = mapRegion(ra, dec, atlas.getFov());
  const signature = JSON.stringify(region);
  if (region && signature !== previousRegion) {
    previousRegion = signature;
    parent.postMessage({ type: 'sky-view', region }, location.origin);
  }
}
function scheduleRegion() {
  clearTimeout(regionTimer);
  regionTimer = setTimeout(publishRegion, 250);
}
let view = { ra: 10.6847, dec: 41.2688, fov: 1.5 };
function update() {
  if (!atlas) return;
  atlas.gotoRaDec(view.ra, view.dec);
  atlas.setFoV(view.fov);
}
window.addEventListener('message', event => {
  if (event.source !== parent || event.origin !== location.origin) return;
  if (event.data?.type === 'sky-targets') {
    if (!catalog || !Array.isArray(event.data.targets)) return;
    catalog.removeAll();
    sources = event.data.targets.slice(0, 200).filter(star => typeof star.id === 'string' && Number.isFinite(star.ra) && Number.isFinite(star.dec));
    const [width, height] = atlas.getSize();
    sources = sources.filter(star => {
      const point = atlas.world2pix(star.ra, star.dec);
      return point && point[0] >= 0 && point[0] <= width && point[1] >= 0 && point[1] <= height;
    });
    catalog.addSources(sources.map(star => sdk.source(star.ra, star.dec, { tic: star.id, name: `TIC ${star.id}` })));
    parent.postMessage({ type: 'sky-visible-targets', ids: sources.map(star => star.id) }, location.origin);
    return;
  }
  if (event.data?.type === 'sky-highlight') {
    if (!catalog) return;
    for (const source of catalog.sources) {
      if (source.data.tic === event.data.id) source.select(); else source.deselect();
    }
    return;
  }
  if (event.data?.type !== 'sky-position') return;
  const { ra, dec, fov } = event.data;
  if (![ra, dec, fov].every(Number.isFinite) || ra < 0 || ra > 360 || dec < -90 || dec > 90 || fov <= 0) return;
  view = { ra, dec, fov };
  update();
});
let sdk;
import('aladin-lite').then(async ({ default: A }) => {
  await A.init;
  sdk = A;
  const url = await selectSurvey();
  let remaining = surveyMirrors.filter(mirror => mirror !== url);
  function layer(base) {
    return A.HiPS(base, {
      name: 'DSS2 color',
      successCallback: () => {
        update();
        parent.postMessage({ type: 'sky-ready', survey: base }, location.origin);
        scheduleRegion();
      },
      errorCallback: async () => {
        parent.postMessage({ type: 'sky-loading' }, location.origin);
        try {
          const fallback = await selectSurvey(remaining);
          remaining = remaining.filter(mirror => mirror !== fallback);
          atlas.setImageLayer(layer(fallback));
        } catch { parent.postMessage({ type: 'sky-error' }, location.origin); }
      },
    });
  }
  atlas = A.aladin(document.getElementById('atlas'), { survey: layer(url), target: '10.6847 41.2688', fov: 1.5, showFullscreenControl: false, log: false });
  catalog = A.catalog({ name: 'Selectable TIC stars', color: '#70e5ff', sourceSize: 14, shape: 'circle', selectionColor: '#ffd166',
    onClick: source => parent.postMessage({ type: 'sky-select', id: source.data.tic }, location.origin) });
  atlas.addCatalog(catalog);
  atlas.on('positionChanged', scheduleRegion);
  atlas.on('zoomChanged', scheduleRegion);
  atlas.on('resizeChanged', scheduleRegion);
}).catch(() => parent.postMessage({ type: 'sky-error' }, location.origin));
