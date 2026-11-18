// Registered mirrors of the same DSS2 color survey, independent of the failing CDS host.
export const surveyMirrors = [
  'https://irsa.ipac.caltech.edu/data/hips/CDS/DSS2/color',
  'https://stpubdata.s3.us-east-1.amazonaws.com/mast/skybackgrounds/DSSColor',
];

export async function selectSurvey(mirrors = surveyMirrors, fetchResource = fetch, decode = createImageBitmap) {
  for (const url of mirrors) {
    try {
      const properties = await fetchResource(`${url}/properties`, { signal: AbortSignal.timeout(10000) });
      if (!properties.ok || !(await properties.text()).includes('hips_tile_format')) continue;
      const image = await fetchResource(`${url}/Norder3/Allsky.jpg`, { signal: AbortSignal.timeout(10000) });
      if (!image.ok) continue;
      const bitmap = await decode(await image.blob());
      const valid = bitmap.width > 0 && bitmap.height > 0;
      bitmap.close();
      if (valid) return url;
    } catch { /* Try the independent mirror when metadata or imagery is unavailable. */ }
  }
  throw new Error('DSS survey imagery is unavailable from both mirrors.');
}
