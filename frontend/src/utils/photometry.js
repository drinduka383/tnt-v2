export function parsePhotometry(csv) {
  const [header, ...rows] = csv.trim().split(/\r?\n/);
  if (header !== 'time_bjd,normalized_flux') throw new Error('Unexpected photometry columns.');
  const time = [];
  const brightness = [];
  for (const row of rows) {
    const [rawTime, rawFlux] = row.split(',');
    const bjd = Number(rawTime);
    const flux = Number(rawFlux);
    if (!rawTime || !rawFlux || !Number.isFinite(bjd) || !Number.isFinite(flux)) {
      throw new Error('The file contains an invalid measurement.');
    }
    time.push(bjd);
    brightness.push((flux - 1) * 100);
  }
  if (time.length < 2) throw new Error('Too few measurements to plot.');
  return { time, brightness };
}

export function hoursFromTransit(times, period, epoch) {
  return times.map(time => {
    const elapsed = time - epoch;
    return 24 * (elapsed - Math.floor(elapsed / period + .5) * period);
  });
}

export function extent(series) {
  let min = Infinity;
  let max = -Infinity;
  for (const values of series) {
    for (const value of values) {
      min = Math.min(min, value);
      max = Math.max(max, value);
    }
  }
  const pad = (max - min) * .05 || .01;
  return [min - pad, max + pad];
}
