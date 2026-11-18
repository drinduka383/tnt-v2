import { isTerminal, validateRun } from '../utils/runState.js';
import { request } from './client';

export async function createRun(spec, file, signal, key) {
  if (spec.parent_run) return validateRun(await request(`/runs/${encodeURIComponent(spec.parent_run)}/signal-check`,
    { method: 'POST', signal, headers: { 'Idempotency-Key': key } }));
  let body = spec;
  if (file) {
    body = new FormData();
    body.append('spec', JSON.stringify(spec));
    body.append('file', file);
  }
  return validateRun(await request('/runs', { method: 'POST', body, signal, headers: { 'Idempotency-Key': key } }));
}
export async function getRun(id, signal) {
  const run = validateRun(await request(`/runs/${encodeURIComponent(id)}`, { signal }));
  if (run.id !== id) throw new Error('The service returned a different saved run. Reconnect to retry.');
  return run;
}
export async function cancelRun(id) {
  const run = validateRun(await request(`/runs/${encodeURIComponent(id)}/cancel`, { method: 'POST' }));
  if (run.id !== id || !isTerminal(run.status)) throw new Error('Cancellation was not confirmed. Retry or reconnect.');
  return run;
}
