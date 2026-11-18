import test from 'node:test';
import assert from 'node:assert/strict';
import { selectSurvey } from './skySurvey.js';
const metadata = { ok: true, text: async () => 'hips_tile_format = jpeg' };
const image = { ok: true, blob: async () => new Blob(['image']) };
const decode = async () => ({ width: 100, height: 100, close() {} });

test('a 404 survey must fall back before the viewer is declared ready', async () => {
  const requests = [];
  const fetchResource = async url => {
    requests.push(url);
    if (url.startsWith('broken')) return { ok: false };
    return url.endsWith('/properties') ? metadata : image;
  };
  assert.equal(await selectSurvey(['broken', 'working'], fetchResource, decode), 'working');
  assert.ok(requests.includes('working/Norder3/Allsky.jpg'));
});
test('metadata alone is not a working map', async () => {
  const fetchResource = async url => url.endsWith('/properties') ? metadata : { ok: false };
  await assert.rejects(selectSurvey(['broken'], fetchResource, decode), /unavailable/);
});
test('undecodable image data cannot count as ready', async () => {
  await assert.rejects(selectSurvey(['broken'], async url => url.endsWith('/properties') ? metadata : image, async () => { throw new Error('not an image'); }), /unavailable/);
});
