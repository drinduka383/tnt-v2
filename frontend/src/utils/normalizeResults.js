// /src/utils/normalizeResults.js
export const toPercent = (p) =>
  typeof p === 'number' && Number.isFinite(p) && p >= 0 && p <= 1
    ? Math.round(p * 100) : null;
