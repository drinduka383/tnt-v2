"""Acquire an indexed public light curve without alias resolution or shared files."""
from dataclasses import dataclass
from pathlib import Path
import time
import requests
from src.contracts import AnalysisError
from src.services.observations import lightcurve_products

@dataclass
class LatestFITSFetcher:
    mission: str
    target_id: str
    outdir: Path

    def select_or_download(self, listing=None):
        products, limited = listing if listing is not None else lightcurve_products(self.target_id, self.mission)
        if not products:
            raise AnalysisError('No supported public light-curve observation is available.', 422, 'no_observation')
        if limited:
            raise AnalysisError('Observation search is incomplete; cannot select the latest product.', 502, 'upstream_unavailable')
        product = products[0]
        self.outdir = Path(self.outdir).resolve()
        self.outdir.mkdir(parents=True, exist_ok=True)
        destination = self.outdir / Path(product['uri']).name
        partial = destination.with_suffix(destination.suffix + '.part')
        try:
            started = time.monotonic()
            with requests.get('https://mast.stsci.edu/api/v0.1/Download/file', params={'uri': product['uri']}, stream=True, timeout=(5, 30)) as response:
                response.raise_for_status()
                size = 0
                with partial.open('wb') as output:
                    for chunk in response.iter_content(chunk_size=65536):
                        size += len(chunk)
                        if size > 64 * 1024 * 1024 or time.monotonic() - started > 90:
                            raise ValueError('Observation exceeds the supported download size or duration')
                        output.write(chunk)
                if size == 0:
                    raise ValueError('Empty observation download')
            partial.replace(destination)
        except Exception as error:
            partial.unlink(missing_ok=True)
            raise AnalysisError('Observation download failed or exceeded its limits.', 502, 'upstream_unavailable') from error
        return {'path': str(destination), 'author': product['author'], 'group_val': product['group'], 'uri': product['uri']}
