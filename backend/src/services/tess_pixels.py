"""Fall back to one small, public TESS full-frame cutout at verified TIC coordinates."""
from io import BytesIO
import json
import time
from zipfile import BadZipFile, ZipFile

import numpy as np
import requests
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

from src.contracts import AnalysisError
from src.data_mapper import number
from src.services.mast_search_service import MastSearchService

API = 'https://mast.stsci.edu/tesscut/api/v0.1'
MAX_BYTES = 32 * 1024 * 1024


def download_cutout(identifier, outdir, stage):
    stage('locating_tess_pixels')
    query = {'service': 'Mast.Catalogs.Filtered.Tic', 'format': 'json', 'pagesize': 2, 'page': 1,
             'params': {'columns': 'ID,ra,dec,Teff,rad,Tmag,objType',
                        'filters': [{'paramName': 'ID', 'values': [identifier]}]}}
    try:
        _, body = MastSearchService().mast_query(query, timeout=(5, 15))
        response = json.loads(body)
        if response['status'] != 'COMPLETE' or not isinstance(response['data'], list):
            raise ValueError('Incomplete TIC response')
        rows = [row for row in response['data'] if str(row['ID']) == identifier]
        if len(rows) != 1:
            raise AnalysisError('No verified TIC position is available for a pixel search.', 422, 'no_observation')
        row = rows[0]
        ra, dec = number(row.get('ra')), number(row.get('dec'))
        if ra is None or dec is None or not 0 <= ra < 360 or not -90 <= dec <= 90:
            raise ValueError('Invalid TIC coordinates')
        coords = {'ra': ra, 'dec': dec}
        response = requests.get(f'{API}/sector', params=coords, timeout=(5, 15))
        response.raise_for_status()
        sectors = response.json()['results']
        if not sectors:
            raise AnalysisError('TESScut lists no full-frame coverage for this TIC position.', 422, 'no_observation')
        sector = max(int(item['sector']) for item in sectors)
    except (requests.RequestException, KeyError, TypeError, ValueError) as error:
        raise AnalysisError('The TESS pixel coverage lookup failed. Retry this target.', 502, 'upstream_unavailable') from error

    stage('downloading_tess_pixels')
    path, request_url = download_sector_cutout(coords, sector, outdir)
    return {'path': str(path), 'author': 'MAST TESScut', 'group_val': sector, 'uri': request_url,
            'coordinates': coords, 'tic': row}


def download_sector_cutout(coords, sector, outdir):
    uri = f'{API}/astrocut'
    try:
        archive = BytesIO()
        start = time.monotonic()
        with requests.get(uri, params={**coords, 'x': 7, 'y': 7, 'sector': sector}, stream=True, timeout=(5, 40)) as response:
            response.raise_for_status()
            for chunk in response.iter_content(65536):
                if archive.tell() + len(chunk) > MAX_BYTES or time.monotonic() - start > 80:
                    raise ValueError('Pixel cutout exceeded its download limit')
                archive.write(chunk)
            request_url = response.url
        with ZipFile(archive) as bundle:
            members = [entry for entry in bundle.infolist() if not entry.is_dir()]
            if len(members) != 1 or not members[0].filename.lower().endswith('.fits') or members[0].file_size > MAX_BYTES:
                raise ValueError('Unexpected FITS cutout archive')
            content = bundle.read(members[0])
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / f'tesscut-s{sector:04d}.fits'
        partial = path.with_suffix('.part')
        partial.write_bytes(content)
        partial.replace(path)
    except (requests.RequestException, BadZipFile, ValueError, OSError) as error:
        raise AnalysisError('The TESS pixel cutout could not be downloaded or read.', 502, 'upstream_unavailable') from error
    return path, request_url


def aperture_photometry(path, coordinates, sector):
    with fits.open(path) as hdus:
        if int(hdus[0].header['SECTOR']) != sector or hdus['PIXELS'].header['TIMESYS'] != 'TDB':
            raise ValueError('Unexpected cutout sector or time system')
        pixels = hdus['PIXELS']
        data, header = pixels.data, pixels.header
        if not 2 <= len(data) <= 100000 or data['FLUX'].shape != (len(data), 7, 7):
            raise ValueError('Unexpected cutout shape')
        sky = SkyCoord(coordinates['ra'], coordinates['dec'], unit='deg')
        pixel = WCS(hdus['APERTURE'].header).celestial.world_to_pixel(sky)
        x, y = (int(round(float(value))) for value in pixel)
        if not (2 <= x <= 4 and 2 <= y <= 4):
            raise ValueError('TIC position is outside the cutout center')
        time_bjd = data['TIME'] + header['BJDREFI'] + header['BJDREFF']
        flux = data['FLUX']
        good = (data['QUALITY'] == 0) & np.isfinite(time_bjd) & np.all(np.isfinite(flux), axis=(1, 2))
        flux = flux[good]
        if len(flux) < 2:
            raise ValueError('No usable pixel cadences')
        border = np.ones((7, 7), dtype=bool)
        border[1:-1, 1:-1] = False
        signal = flux[:, y-1:y+2, x-1:x+2].sum(axis=(1, 2)) - 9 * np.median(flux[:, border], axis=1)
        scale = np.median(signal)
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError('Cutout aperture has no positive baseline')
        return time_bjd[good], signal / scale
