"""Opt-in live survey acceptance. Requires the app on localhost:5188 and internet."""
from io import BytesIO
from PIL import Image
from playwright.sync_api import sync_playwright

PRIMARY = '**/irsa.ipac.caltech.edu/data/hips/CDS/DSS2/color/**'
FALLBACK = '**/stpubdata.s3.us-east-1.amazonaws.com/mast/skybackgrounds/DSSColor/**'

def ready(page):
    page.wait_for_function("!document.querySelector('.map-stage [role=status]')", timeout=45000)
    page.wait_for_timeout(8000)
    pixels = Image.open(BytesIO(page.screenshot())).crop((800, 120, 1250, 700)).convert('RGB')
    assert len(pixels.getcolors(pixels.width * pixels.height) or []) > 1000, 'Map is blank or uniform'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1280, 'height': 800})
    tiles = []
    page.on('response', lambda response: tiles.append(response.url) if response.status == 200 and '/Norder' in response.url else None)
    page.goto('http://127.0.0.1:5188/start', wait_until='domcontentloaded')
    ready(page)
    assert any('irsa.ipac' in url for url in tiles)
    atlas = page.frame_locator('iframe[title="Astronomical sky atlas"]')
    before = atlas.get_by_placeholder('Search for an object...').input_value()
    page.mouse.move(1050, 400)
    page.mouse.down()
    page.mouse.move(1150, 450, steps=8)
    page.mouse.up()
    page.mouse.wheel(0, -300)
    page.wait_for_timeout(3000)
    assert atlas.get_by_placeholder('Search for an object...').input_value() != before, 'Panning did not move the view'
    print('PASS: real survey tiles, rendered pixels, pan and zoom')
    page.route(PRIMARY, lambda route: route.abort())
    page.reload(wait_until='domcontentloaded')
    ready(page)
    assert any('stpubdata' in url for url in tiles)
    print('PASS: primary outage falls back to MAST imagery')
    page.route(FALLBACK, lambda route: route.abort())
    page.reload(wait_until='domcontentloaded')
    page.get_by_role('button', name='Retry map').wait_for(timeout=30000)
    page.unroute(PRIMARY)
    page.unroute(FALLBACK)
    page.get_by_role('button', name='Retry map').click()
    ready(page)
    print('PASS: all-mirrors failure is visible; Retry recovers live imagery')
    browser.close()
