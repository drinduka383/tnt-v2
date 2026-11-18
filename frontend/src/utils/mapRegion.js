export function mapRegion(ra, dec, fov) {
  if (!Array.isArray(fov) || fov.length !== 2) return null;
  if (![ra, dec, ...fov].every(Number.isFinite) || ra < 0 || ra > 360 || dec < -90 || dec > 90 || fov.some(value => value <= 0 || value > 180)) return null;
  return { ra, dec, radius: Math.hypot(...fov) / 2 };
}

export function sameRegion(left, right) {
  return Boolean(left && right && ['ra', 'dec', 'radius'].every(key => Math.abs(left[key] - right[key]) < 1e-6));
}
