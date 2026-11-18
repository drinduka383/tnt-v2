"""Evidence remains visible without a score; archive errors retry the same target."""
import json
from playwright.sync_api import sync_playwright

PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aTpsAAAAASUVORK5CYII='
def record(identifier='data-run'):
    return {'id':identifier, 'status':'insufficient_evidence', 'stage':'classifying',
      'spec':{'target':{'mission':'tess','namespace':'TIC','id':'191179668'},'evidence':'lightcurve','model':{'name':'balanced'}},
      'result':{'manual_search':{'raw':{},'stellar':{'st_teff':5700}},
       'provenance':{'target':{'namespace':'TIC','id':'191179668'},'evidence':'lightcurve','observation':{'author':'SPOC','group':1}},
       'candidates':[{'id':'Signal','status':'insufficient_evidence','message':'Missing calibrated uncertainty'}],
       'artifacts':{'photometry':True,'observation':True,'evidence':True},
       'processed_json':[{'photometry':{'samples':200,'baseline_days':.7,'plotted_samples':200,'preview':[[2457000,1.0]]},'visualizations':[{'type':'normalized_light_curve','data':PNG}],'quality':{'search_status':'insufficient_coverage','message':'Photometry loaded; less than two days of coverage.'},'parameters':{}}]}}

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1280,'height':900})
    submitted=[]
    submission_keys=[]
    def api(route):
        url=route.request.url
        if '/artifacts/photometry' in url:
            route.fulfill(status=200,content_type='text/csv',headers={'Content-Disposition':'attachment; filename=lightcurve.csv'},body='time_bjd,normalized_flux\n2457000,1.0\n')
            return
        if url.endswith('/runs') and route.request.method=='GET': body=[]
        elif url.endswith('/runs'):
            submitted.append(route.request.post_data_json)
            submission_keys.append(route.request.headers['idempotency-key'])
            if len(submitted) == 1:
                route.abort()
                return
            body=record('retry-run')
        elif 'failed-run' in url:
            body=record('failed-run');body['status']='failed';body['result']=None;body['error']={'code':'upstream_unavailable','message':'Archive timed out'}
        elif '/runs/retry-run' in url: body=record('retry-run')
        else:body=record()
        route.fulfill(status=200,content_type='application/json',body=json.dumps(body))
    page.route('http://127.0.0.1:5188/api/**',api)
    page.route('**/*aladin*.js*',lambda route:route.abort())
    page.goto('http://127.0.0.1:5188/start?run=data-run',wait_until='domcontentloaded')
    page.get_by_role('heading',name='Evidence ready',exact=True).wait_for()
    assert page.get_by_role('img',name='Observed stellar brightness over time').is_visible()
    assert page.get_by_text('Model not scored',exact=True).is_visible()
    with page.expect_download() as download:
        page.get_by_role('link',name='Download photometry CSV').click()
    assert download.value.suggested_filename=='lightcurve.csv'
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.goto('http://127.0.0.1:5188/start?run=wrong-run',wait_until='domcontentloaded')
    page.get_by_role('heading',name='Connection interrupted',exact=True).wait_for()
    assert page.get_by_text('The service returned a different saved run.',exact=False).is_visible()
    page.goto('http://127.0.0.1:5188/start?run=failed-run',wait_until='domcontentloaded')
    page.get_by_role('heading',name='The archive did not respond',exact=True).wait_for()
    page.get_by_role('button',name='Retry this target').click()
    page.get_by_role('heading',name='Could not start analysis',exact=True).wait_for()
    page.get_by_role('button',name='Retry starting analysis').click()
    page.get_by_role('heading',name='Evidence ready',exact=True).wait_for()
    assert len(submitted)==2 and submitted[0]==submitted[1]
    assert submission_keys[0]==submission_keys[1]
    assert submitted[0]['id']=='TIC 191179668'
    page.wait_for_timeout(1700)
    assert page.get_by_role('heading',name='Evidence ready',exact=True).is_visible()
    page.get_by_role('button',name='New target',exact=True).click()
    assert page.get_by_label('TIC host or TOI candidate').input_value()=='TIC 191179668'
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    browser.close()
    print('PASS: unscored evidence is visible, CSV downloads, mobile layout, retry preserves target')
