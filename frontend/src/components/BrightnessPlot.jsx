import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { extent } from '../utils/photometry.js';
import './BrightnessPlot.css';

function ticks([min, max], count) {
  const interval = (max - min) / count;
  const magnitude = 10 ** Math.floor(Math.log10(interval));
  const scaled = interval / magnitude;
  const step = (scaled >= Math.sqrt(50) ? 10 : scaled >= Math.sqrt(10) ? 5 : scaled >= Math.sqrt(2) ? 2 : 1) * magnitude;
  const digits = Math.min(9, Math.max(0, Math.ceil(-Math.log10(step)) + 1));
  const labels = [];
  for (let index = Math.ceil(min / step); index * step <= max; index++) {
    const value = index * step;
    labels.push([value, Number(value.toFixed(digits)).toLocaleString(undefined, { maximumFractionDigits: digits })]);
  }
  return labels;
}

function drawPoints(ctx, x, y, { px, py }, color, opacity) {
  ctx.fillStyle = color;
  ctx.globalAlpha = opacity;
  for (let i = 0; i < x.length; i++) {
    const screenX = px(x[i]);
    ctx.fillRect(screenX - .8, py(y[i]) - .8, 1.6, 1.6);
  }
}

export default function BrightnessPlot({ title, x, y, xLabel, xUnit, xRange, yRange, windowHours, tone = 'original', overlay }) {
  const canvasRef = useRef(null);
  const geometry = useRef(null);
  const [point, setPoint] = useState(null);
  const tooltipOpen = point !== null;
  useEffect(() => {
    if (!tooltipOpen) return;
    const dismiss = event => {
      if (event.key === 'Escape') setPoint(null);
    };
    window.addEventListener('keydown', dismiss);
    return () => window.removeEventListener('keydown', dismiss);
  }, [tooltipOpen]);
  useLayoutEffect(() => {
    const canvas = canvasRef.current;
    const color = getComputedStyle(canvas);
    const chartFont = `12px ${color.getPropertyValue('--body-font').trim()}`;
    const ink = key => color.getPropertyValue(`--plot-${key}`).trim();
    let active = true;
    function draw() {
      if (!active) return;
      const { width, height } = canvas.getBoundingClientRect();
      if (!width || !height) return;
      const ratio = Math.min(devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      const ctx = canvas.getContext('2d');
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.font = chartFont;

      const xBounds = xRange || extent([x]);
      const yBounds = yRange || extent([y]);
      const yTicks = ticks(yBounds, Math.max(2, Math.round((height - 42) / 46)));
      const left = Math.max(38, ...yTicks.map(([, label]) => ctx.measureText(label).width + 12));
      const right = width - 14;
      canvas.closest('figure').style.setProperty('--plot-left', `${left}px`);
      const top = 12;
      const bottom = height - 30;
      const px = value => left + (value - xBounds[0]) / (xBounds[1] - xBounds[0]) * (right - left);
      const py = value => bottom - (value - yBounds[0]) / (yBounds[1] - yBounds[0]) * (bottom - top);
      geometry.current = { px, py };
      const xTicks = ticks(xBounds, Math.max(2, Math.round((right - left) / 86)));

      // Daily guides are useful only when they have room between labeled divisions.
      if (xUnit === 'days' && px(1) - px(0) >= 14 && xTicks.length > 1 && xTicks[1][0] - xTicks[0][0] > 1) {
        const majorDays = new Set(xTicks.map(([value]) => value));
        ctx.fillStyle = ink('minor-grid');
        for (let day = Math.ceil(xBounds[0]); day <= xBounds[1]; day++) {
          if (!majorDays.has(day)) ctx.fillRect(px(day), top, 1, bottom - top);
        }
      }

      if (windowHours != null) {
        ctx.fillStyle = ink('window');
        const start = Math.max(left, px(-windowHours / 2));
        const end = Math.min(right, px(windowHours / 2));
        if (end > start) ctx.fillRect(start, top, end - start, bottom - top);
        if (xBounds[0] <= 0 && xBounds[1] >= 0) {
          ctx.strokeStyle = ink('center');
          ctx.setLineDash([3, 4]);
          ctx.beginPath();
          ctx.moveTo(px(0), top);
          ctx.lineTo(px(0), bottom);
          ctx.stroke();
          ctx.setLineDash([]);
        }
      }
      ctx.textBaseline = 'middle';
      ctx.textAlign = 'right';
      for (const [value, label] of yTicks) {
        ctx.fillStyle = ink('grid');
        ctx.fillRect(left, py(value), right - left, 1);
        ctx.fillStyle = ink('label');
        ctx.fillText(label, left - 7, py(value));
      }
      ctx.textAlign = 'center';
      for (const [value, label] of xTicks) {
        const tickX = px(value);
        const labelX = Math.min(width - ctx.measureText(label).width / 2 - 2, tickX);
        if (windowHours == null || value !== 0) {
          ctx.fillStyle = ink('grid');
          ctx.fillRect(tickX, top, 1, bottom - top);
        }
        ctx.fillStyle = ink('axis');
        ctx.fillRect(tickX, bottom, 1, 4);
        ctx.fillStyle = ink('label');
        ctx.fillText(label, labelX, bottom + 16);
      }
      ctx.save();
      ctx.beginPath();
      ctx.rect(left, top, right - left, bottom - top);
      ctx.clip();
      if (overlay) ctx.globalCompositeOperation = 'screen';
      drawPoints(ctx, x, y, geometry.current, ink(tone), overlay ? .16 : xRange ? .52 : x.length > 10000 ? .33 : .57);
      if (overlay) drawPoints(ctx, overlay.x, overlay.y, geometry.current, ink('independent'), .16);
      ctx.restore();
    }
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    draw();
    document.fonts.ready.then(draw);
    return () => {
      active = false;
      observer.disconnect();
    };
  }, [x, y, xRange, yRange, xUnit, windowHours, tone, overlay]);

  function inspect(event) {
    if (!geometry.current || event.pointerType === 'touch') return;
    const { px, py } = geometry.current;
    const bounds = event.currentTarget.getBoundingClientRect();
    const localX = event.clientX - bounds.left;
    const localY = event.clientY - bounds.top;
    const cursor = { cursorX: localX, cursorY: localY, flipX: localX > bounds.width / 2, flipY: localY > bounds.height / 2 };
    const original = { x, y, label: overlay?.originalLabel, tone };
    const observations = overlay
      ? [original, { x: overlay.x, y: overlay.y, label: overlay.independentLabel, tone: 'independent' }]
      : [original];
    let nearest = 144;
    let match = null;
    for (const series of observations) {
      for (let i = 0; i < series.x.length; i++) {
        const screenX = px(series.x[i]);
        const dx = screenX - localX;
        if (Math.abs(dx) > 12) continue;
        const screenY = py(series.y[i]);
        const distance = dx ** 2 + (screenY - localY) ** 2;
        if (distance < nearest) {
          nearest = distance;
          match = {
            time: series.x[i], brightness: series.y[i], label: series.label, tone: series.tone,
            left: screenX / bounds.width * 100, top: screenY / bounds.height * 100,
            ...cursor,
          };
        }
      }
    }
    setPoint(match);
  }

  return <figure className="brightness-plot">
    <figcaption>{overlay ? <span className="brightness-plot-key">
      <span>{overlay.originalLabel}</span><span>{overlay.independentLabel}</span>
    </span> : title}</figcaption>
    <div className="brightness-plot-area">
      <div className="brightness-plot-axis brightness-plot-axis-y">Brightness change (%)</div>
      <canvas ref={canvasRef} role="img" aria-label={`${title}. ${(x.length + (overlay?.x.length || 0)).toLocaleString()} measured points. Brightness change in percent versus ${xLabel.toLowerCase()} in ${xUnit}.`}
        onPointerMove={inspect} onPointerLeave={() => setPoint(null)} onPointerCancel={() => setPoint(null)} />
      {point && <>
        <span className="brightness-plot-focus" data-tone={point.tone} aria-hidden="true" style={{ left: `${point.left}%`, top: `${point.top}%` }} />
        <div className="brightness-plot-tooltip" data-left={point.flipX} data-above={point.flipY}
          style={{ '--cursor-x': `${point.cursorX}px`, '--cursor-y': `${point.cursorY}px` }}>
          {point.label && <div className="brightness-plot-tooltip-title" data-tone={point.tone}>{point.label}</div>}
          <dl>
            <dt>{xUnit === 'days' ? 'Time since start' : 'Time from center'}</dt>
            <dd>{point.time.toLocaleString(undefined, { maximumFractionDigits: 4 })} {xUnit === 'days' ? 'd' : 'h'}</dd>
            <dt>Brightness change</dt>
            <dd>{point.brightness.toLocaleString(undefined, { maximumFractionDigits: 4 })}%</dd>
          </dl>
        </div>
      </>}
    </div>
    <div className="brightness-plot-axis brightness-plot-axis-x">{xLabel} ({xUnit})</div>
  </figure>;
}
