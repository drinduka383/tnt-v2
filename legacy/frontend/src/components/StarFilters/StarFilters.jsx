import { useEffect, useRef, useState } from 'react';
import { request } from '../../api/client.js';

const fields = [
  ['ra', 'Right ascension (degrees)', 0, 360], ['dec', 'Declination (degrees)', -90, 90],
  ['radius', 'Radius (arcminutes)', 0.01, 30], ['mag_min', 'Minimum magnitude', -30, 30],
  ['mag_max', 'Maximum magnitude', -30, 30], ['temp_min', 'Minimum temperature (K)', 0, 100000],
  ['temp_max', 'Maximum temperature (K)', 0, 100000], ['dist_min', 'Minimum distance (pc)', 0, 1000000],
  ['dist_max', 'Maximum distance (pc)', 0, 1000000],
];
export default function StarFilters({ onResults }) {
  const [form, setForm] = useState({ ra: 0, dec: 0, radius: 15, mag_min: 6, mag_max: 15, temp_min: 3000, temp_max: 7500, dist_min: 10, dist_max: 500 });
  const [state, setState] = useState({ status: 'idle' });
  const controller = useRef(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function search(event) {
    event.preventDefault();
    controller.current?.abort();
    const pending = new AbortController();
    controller.current = pending;
    setState({ status: 'loading' });
    try {
      const response = await request(`/search?${new URLSearchParams(form)}`, { signal: pending.signal });
      if (pending.signal.aborted) return;
      onResults(response.data.map(star => ({ id: String(star.ID), magnitude: star.Tmag ?? 'unknown' })));
      setState({ status: response.data.length ? 'success' : 'empty' });
    } catch (error) {
      if (!pending.signal.aborted) { onResults([]); setState({ status: 'error', message: error.message }); }
    }
  }
  return <form onSubmit={search}>
    {fields.map(([name, label, min, max]) => <label key={name}>{label}<input type="number" required step="any" min={min} max={max} value={form[name]} onChange={e => setForm({ ...form, [name]: e.target.value })} /></label>)}
    <button disabled={state.status === 'loading'}>{state.status === 'loading' ? 'Searching...' : 'Search TIC catalog'}</button>
    {state.status === 'error' && <p role="alert">{state.message}</p>}
    {state.status === 'empty' && <p role="status">No hosts match these filters.</p>}
  </form>;
}
