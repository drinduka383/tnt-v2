const base = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

export async function request(path, { signal, body, method = 'GET', headers = {} } = {}) {
  const form = body instanceof FormData;
  const boundedSignal = signal ? AbortSignal.any([signal, AbortSignal.timeout(55000)]) : AbortSignal.timeout(55000);
  const response = await fetch(`${base}${path}`, {
    method, signal: boundedSignal, headers: { Accept: 'application/json', ...(!form && body ? { 'Content-Type': 'application/json' } : {}), ...headers },
    body: form ? body : body ? JSON.stringify(body) : undefined,
  });
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) throw new Error('The analysis service returned an invalid response.');
  const data = await response.json();
  if (!response.ok) throw new Error(data.message || `Request failed (${response.status})`);
  return data;
}

export const artifactURL = (id, kind) => `${base}/runs/${encodeURIComponent(id)}/artifacts/${encodeURIComponent(kind)}`;
