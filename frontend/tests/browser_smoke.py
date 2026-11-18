"""Headless UI acceptance against deterministic API responses; starts its own Vite process."""
import json
from pathlib import Path
import subprocess
import time
import urllib.request
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PORT = 5187
process = subprocess.Popen(['node', 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', str(PORT), '--strictPort'], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for attempt in range(100):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{PORT}', timeout=1)
            break
        except OSError:
            time.sleep(.1)
    else:
        raise AssertionError('Vite did not start')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        state = {'status': 'running', 'created': 0, 'cancelled': 0}
        def record():
            result = None
            if state['status'] == 'succeeded':
                result = {'provenance': {'target': {'namespace': 'TIC', 'id': '123'}, 'evidence': 'catalog'},
                          'manual_search': {'stellar': {}}, 'processed_json': [],
                          'candidates': [{'id': '1.01', 'status': 'scored', 'class': 'Candidate-like', 'probability': .8},
                                         {'id': '1.02', 'status': 'insufficient_evidence', 'message': 'Missing measurements'}]}
            return {'id': f"run{state['created']}", 'status': state['status'], 'stage': 'classifying', 'result': result}
        def api(route):
            request = route.request
            if request.method == 'POST' and request.url.endswith('/runs'):
                state['created'] += 1
                payload = record()
            elif request.url.endswith('/cancel'):
                state['status'] = 'cancelled'
                state['cancelled'] += 1
                payload = record()
            else:
                payload = record()
            route.fulfill(status=200, content_type='application/json', body=json.dumps(payload))
        page.route(f'http://127.0.0.1:{PORT}/api/**', api)
        # Test that an unavailable optional atlas cannot prevent the analysis workflow.
        page.route('**/*aladin*.js*', lambda route: route.abort())
        page.goto(f'http://127.0.0.1:{PORT}/start')
        page.get_by_label('TIC host or TOI candidate').fill('123')
        page.get_by_role('button', name='Analyze target', exact=True).click()
        page.get_by_role('heading', name='Loading evidence', exact=True).wait_for()
        page.get_by_role('button', name='Cancel and return').click()
        page.get_by_role('button', name='Analyze target', exact=True).wait_for()
        assert state['cancelled'] == 1
        state['status'] = 'succeeded'
        page.get_by_role('button', name='Analyze target', exact=True).click()
        page.get_by_role('cell', name='80%', exact=True).wait_for()
        page.get_by_role('row').filter(has_text='1.02').get_by_text('Missing measurements', exact=True).wait_for()
        page.reload()
        page.get_by_role('cell', name='80%', exact=True).wait_for()
        page.get_by_role('button', name='Change target').click()
        page.set_viewport_size({'width': 390, 'height': 844})
        page.get_by_label('Mission').select_option('kepler')
        assert page.get_by_label('KIC host or KOI candidate').input_value() == ''
        page.get_by_label('KIC host or KOI candidate').fill('KIC 123')
        page.get_by_role('button', name='Evidence', exact=True).click()
        page.get_by_role('button', name='Sky map', exact=True).click()
        assert page.get_by_label('KIC host or KOI candidate').input_value() == 'KIC 123'
        assert not errors, errors
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile layout overflows'
        browser.close()
        print('PASS: submit, cancel, multi-candidate results, reload recovery, mobile form and optional-atlas failure')
finally:
    process.terminate()
    process.wait(timeout=10)
