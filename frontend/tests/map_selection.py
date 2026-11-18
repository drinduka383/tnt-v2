"""Live Aladin marker interaction with deterministic API timing. App must be on :5188."""
import asyncio
import json
import re
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width':1280, 'height':900})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        release_region = asyncio.Event()
        region_started = asyncio.Event()
        state = {'delay_region':False, 'submitted':None}
        targets = [{'id':'123', 'mission':'tess', 'ra':10.6847, 'dec':41.2688, 'magnitude':9, 'temperature':5700},
                   {'id':'124', 'mission':'tess', 'ra':10.7047, 'dec':41.2688, 'magnitude':10, 'temperature':5000}]
        result = {'id':'map-run', 'status':'succeeded', 'stage':'classifying', 'result':{
            'provenance':{'target':{'namespace':'TIC','id':'124'},'evidence':'catalog'},
            'manual_search':{'raw':{},'stellar':{}}, 'processed_json':[],
            'candidates':[{'id':'124.01','status':'scored','class':'Candidate-like','probability':.8}]}}
        async def api(route):
            url = route.request.url
            if url.endswith('/runs') and route.request.method == 'GET':
                body = []
            elif '/sky/targets?' in url:
                if state['delay_region']:
                    region_started.set()
                    await release_region.wait()
                body = {'targets':targets,'total':2,'limit':200,'limited':False}
            elif '/observations' in url:
                state['preflight_requested'] = True
                body = {}
            elif url.endswith('/runs'):
                state['submitted'] = route.request.post_data_json
                body = result
            elif '/runs/' in url:
                body = result
            else:
                body = {}
            try:
                await route.fulfill(status=200,content_type='application/json',body=json.dumps(body))
            except Exception:
                if not (release_region.is_set()): raise
        await page.route('http://127.0.0.1:5188/api/**',api)
        await page.goto('http://127.0.0.1:5188/start',wait_until='domcontentloaded')
        search = page.get_by_role('button',name='Search this view',exact=True)
        await search.wait_for()
        await page.wait_for_function("Array.from(document.querySelectorAll('button')).some(b=>b.textContent==='Search this view'&&!b.disabled)",timeout=45000)
        await search.click()
        await page.get_by_role('button',name=re.compile(r'TIC 123')).wait_for()
        await page.wait_for_timeout(500)
        frame = await page.locator('iframe[title="Astronomical sky atlas"]').bounding_box()
        await page.mouse.click(frame['x']+frame['width']/2,frame['y']+frame['height']/2)
        await page.get_by_role('heading',name='Selected TIC 123',exact=True).wait_for()
        await page.get_by_role('button',name=re.compile(r'TIC 124')).click()
        await page.wait_for_timeout(500)
        assert await page.get_by_label('TIC host or TOI candidate').input_value() == '124'
        assert await page.get_by_role('heading',name='Selected TIC 124',exact=True).is_visible()
        state['delay_region']=True
        await search.click()
        await asyncio.wait_for(region_started.wait(),5)
        await page.mouse.move(frame['x']+frame['width']*.8,frame['y']+frame['height']*.75)
        await page.mouse.down()
        await page.mouse.move(frame['x']+frame['width']*.7,frame['y']+frame['height']*.7,steps=10)
        await page.mouse.up()
        await page.wait_for_function("Array.from(document.querySelectorAll('button')).some(b=>b.textContent==='Search this view'&&!b.disabled)")
        release_region.set()
        await page.wait_for_timeout(500)
        assert await page.locator('.map-targets button').count() == 0, 'Stale region repopulated markers'
        await page.get_by_role('button',name='Analyze TIC 124',exact=True).click()
        await page.get_by_role('heading',name='Evidence ready',exact=True).wait_for()
        assert state['submitted']['id']=='124' and state['submitted']['mission']=='tess'
        assert state['submitted']['evidence']=='combined' and not state.get('preflight_requested')
        assert not errors,errors
        await browser.close()
        print('PASS: real marker click, form selection, stale region rejection and no availability preflight, selected-target analysis')

asyncio.run(main())
