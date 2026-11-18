import { useEffect, useRef, useState } from 'react';

type Star = { id: string; ra: number; dec: number };
type Region = { ra: number; dec: number; radius: number };
type Props = { target?: { ra: number; dec: number }; fov?: number; stars?: Star[]; selectedId?: string; onViewChange?: (region: Region) => void; onSelect?: (id: string) => void; onTargetsVisible?: (ids: string[]) => void };
const noStars: Star[] = [];
const initialTarget = { ra: 10.6847, dec: 41.2688 };

export default function SkyAtlas({ target = initialTarget, fov = .5, stars = noStars, selectedId, onViewChange, onSelect, onTargetsVisible }: Props) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState('loading');
  useEffect(() => {
    function receive(event: MessageEvent) {
      if (event.origin !== location.origin || event.source !== frame.current?.contentWindow) return;
      if (event.data?.type === 'sky-loading') setStatus('loading');
      if (event.data?.type === 'sky-ready') setStatus('ready');
      if (event.data?.type === 'sky-error') setStatus('error');
      if (event.data?.type === 'sky-view') {
        const region = event.data.region;
        if (region && [region.ra, region.dec, region.radius].every(Number.isFinite) && region.ra >= 0 && region.ra <= 360 && region.dec >= -90 && region.dec <= 90 && region.radius > 0) onViewChange?.(region);
      }
      if (event.data?.type === 'sky-visible-targets' && Array.isArray(event.data.ids) && event.data.ids.length <= 200 && event.data.ids.every((id: unknown) => typeof id === 'string')) onTargetsVisible?.(event.data.ids);
      if (event.data?.type === 'sky-select' && typeof event.data.id === 'string') onSelect?.(event.data.id);
    }
    window.addEventListener('message', receive);
    return () => window.removeEventListener('message', receive);
  }, [onViewChange, onSelect, onTargetsVisible]);
  const { ra, dec } = target;
  useEffect(() => {
    if (status === 'ready') frame.current?.contentWindow?.postMessage({ type: 'sky-position', ra, dec, fov }, location.origin);
  }, [status, ra, dec, fov]);
  useEffect(() => {
    if (status === 'ready') frame.current?.contentWindow?.postMessage({ type: 'sky-targets', targets: stars }, location.origin);
  }, [status, stars]);
  useEffect(() => {
    if (status === 'ready') frame.current?.contentWindow?.postMessage({ type: 'sky-highlight', id: selectedId }, location.origin);
  }, [status, selectedId, stars]);
  return <div style={{ width: '100%', height: '100%', position: 'relative' }}>
    <iframe key={attempt} ref={frame} src="/atlas.html" title="Astronomical sky atlas" style={{ width: '100%', height: '100%', border: 0 }} />
    {status !== 'ready' && <p role="status" style={{ position: 'absolute', bottom: 20, padding: 16, background: '#101c35' }}>{status === 'error' ? 'Sky atlas unavailable. You can still analyze evidence.' : 'Loading sky imagery...'}{status === 'error' && <button onClick={() => { setStatus('loading'); setAttempt(value => value + 1); }}>Retry map</button>}</p>}
  </div>;
}
