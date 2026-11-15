"""Signed-in LF1 workflow; isolated DB/extractor, actual Chromium and HTTP API."""
import hashlib
import json
import os
from pathlib import Path
import socket
import threading
import time

import pytest

pytestmark=pytest.mark.skipif(os.environ.get('TUBEFORGE_REFERENCE_BROWSER')!='1',reason='opt-in real Chromium workflow')


def test_signed_in_reference_intake_desktop_tablet_mobile(tmp_path):
    from playwright.sync_api import sync_playwright,expect
    import uvicorn
    from tubeforge.api.app import create_app
    from tubeforge.core.config import Settings,AppConfig,DatabaseConfig,AuthConfig
    from tubeforge.reference.extractor import YoutubeReferenceExtractor
    from test_api_workflow import _migrate
    from test_reference_intake_extractor import FixtureHTTP,player,URL
    database=tmp_path/'browser.db';_migrate(database)
    from tubeforge.core.config import VideoPresetConfig
    settings=Settings(app=AppConfig(name='TubeForge LF1 browser',environment='test'),database=DatabaseConfig(url=f'sqlite:///{database}'),auth=AuthConfig(enabled=True))
    settings.pipeline.sources.research_enabled=True
    settings.pipeline.video_generation.presets['short']=VideoPresetConfig(aspect_ratio='9:16',prompt_version='m6-content-v8',minimum_duration_seconds=30,maximum_duration_seconds=90,duration_seconds=60)
    app=create_app(settings)
    runtime=app.state.runtime;runtime.auth.create_admin('intake-reviewer','test-only-browser-intake-password')
    raw=player();raw['captions']={};runtime.reference_intakes.extractor=YoutubeReferenceExtractor(FixtureHTTP(raw))
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen()
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'));thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True);thread.start()
    deadline=time.monotonic()+15
    while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.05)
    assert server.started
    root=Path(__file__).resolve().parents[1];evidence=root/'artifacts/review/reference-intake-lf1-browser-20261108';evidence.mkdir(parents=True,exist_ok=True)
    base=f'http://127.0.0.1:{listener.getsockname()[1]}';results=[]
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
            try:
                for name,width,height,target in [('desktop',1440,1000,'60'),('tablet',820,1180,'720'),('mobile',390,844,'900')]:
                    context=browser.new_context(viewport=dict(width=width,height=height));page=context.new_page();errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(base+'/login');page.locator('[name=username]').fill('intake-reviewer');page.locator('[name=password]').fill('test-only-browser-intake-password');page.locator('button[type=submit]').click();page.wait_for_url(base+'/')
                    if width<=760:page.locator('.studio-menu').click()
                    page.get_by_role('link',name='Reference videos',exact=True).click();page.wait_for_url(base+'/references')
                    expect(page.get_by_text('Signed in as intake-reviewer',exact=True)).to_have_count(1)
                    video_id='AbCdEfGhI_'+{'60':'1','720':'2','900':'3'}[target]
                    raw=player(video_id=video_id);raw['captions']={}
                    runtime.reference_intakes.extractor=YoutubeReferenceExtractor(FixtureHTTP(raw))
                    page.locator('#referenceUrl').fill(URL.replace('AbCdEfGhI_1',video_id));page.locator('#referenceTarget').select_option(target);page.locator('#captureReference').click()
                    expect(page.locator('#referenceState')).to_have_text('Capture pending')
                    created=runtime.reference_intakes.repository.list()[0]['intake'];key=created['intake_id']
                    runtime.reference_intakes.run_once('browser-worker')
                    expect(page.locator('#referenceState')).to_have_text('Transcript needed',timeout=10000)
                    page.locator('#supplyTranscript summary').click();page.locator('#transcriptText').fill('unsaved draft')
                    page.locator('#transcriptText').evaluate("el=>el.dataset.preserved='yes'")
                    with page.expect_response(lambda r:'/api/reference-intakes/'+key in r.url and r.request.method=='GET'):
                        page.locator('#reloadReferences').click()
                    expect(page.locator('#transcriptText')).to_have_value('unsaved draft')
                    assert page.locator('#supplyTranscript').get_attribute('open') is not None
                    assert page.locator('#transcriptText').get_attribute('data-preserved')=='yes'
                    page.locator('#saveTranscript').click();expect(page.locator('#transcriptNotice')).to_contain_text('invalid')
                    assert runtime.reference_intakes.repository.get(key)['intake']['revision']==1
                    srt=b'1\n00:00:00,000 --> 00:00:04,000\nOperator-supplied fixture transcript.\n'
                    page.locator('#transcriptFile').set_input_files(dict(name='fixture.srt',mimeType='text/plain',buffer=srt))
                    expect(page.locator('#transcriptText')).to_have_value(srt.decode())
                    page.locator('#saveTranscript').click();expect(page.locator('#referenceState')).to_have_text('Capture pending')
                    runtime.reference_intakes.run_once('browser-worker')
                    expect(page.locator('#referenceState')).to_have_text('Context captured',timeout=10000)
                    expect(page.locator('#referenceTranscript')).to_contain_text('Operator-supplied fixture transcript.')
                    if target=='60':
                        expect(page.locator('#prepareLongForm')).to_be_hidden()
                        expect(page.locator('#referenceList')).to_contain_text('60 sec target')
                        received=[]
                        def fake_short(route):
                            received.append(route.request.post_data_json)
                            route.fulfill(status=201,json={'job_id':'fake-short','state':'topic_created'})
                        page.route('**/api/reference-intakes/*/short',fake_short)
                        page.locator('#prepareShort summary').click()
                        page.locator('#shortTopic').fill('Original example')
                        page.locator('#shortAngle').fill('A fresh explanation')
                        page.locator('#shortStyle').fill('Fast cuts and large captions')
                        page.locator('#shortWatched').check();page.locator('#shortConfirm').check()
                        page.locator('#createShort').click()
                        expect(page.locator('#shortNotice')).to_contain_text('Short job created')
                        assert received[0]['reference_snapshot_sha256']==runtime.reference_intakes.repository.get(key)['intake']['reference_snapshot_sha256']
                        assert received[0]['watched_reference'] and received[0]['confirmed_queue']
                        page.unroute('**/api/reference-intakes/*/short')

                    assert len(runtime.reference_intakes.extractor.http.calls)==1
                    detail=runtime.reference_intakes.repository.get(key);identity=detail['intake']['reference_snapshot_sha256']
                    exported=context.request.get(base+f'/api/reference-intakes/{key}/snapshot')
                    assert exported.ok and hashlib.sha256(exported.body()).hexdigest()==identity
                    page.locator('#referenceRevision').select_option('1');expect(page.locator('#referenceState')).to_have_text('Transcript needed')
                    expect(page.locator('#saveTranscript')).to_be_disabled();expect(page.locator('#refreshReference')).to_be_disabled()
                    page.locator('#referenceRevision').select_option('2');expect(page.locator('#referenceState')).to_have_text('Context captured')
                    page.locator('#transcriptText').fill('keep this draft on refresh')
                    # Prove a background detail failure leaves visible data and edits intact.
                    page.route('**/api/reference-intakes/'+key+'?revision=2',lambda route:route.fulfill(status=503,content_type='application/json',body='{"detail":"Fixture outage"}'))
                    page.locator('#reloadReferences').click();expect(page.locator('#detailNotice')).to_contain_text('Could not refresh')
                    expect(page.locator('#referenceTitle')).to_have_text('Synthetic reference');expect(page.locator('#transcriptText')).to_have_value('keep this draft on refresh')
                    page.unroute('**/api/reference-intakes/'+key+'?revision=2');page.locator('#reloadReferences').click();expect(page.locator('#detailNotice')).to_have_text('')
                    runtime.reference_intakes.extractor=YoutubeReferenceExtractor(FixtureHTTP(player(video_id=video_id)))
                    page.locator('#refreshReference').click();expect(page.locator('#referenceState')).to_have_text('Capture pending')
                    runtime.reference_intakes.run_once('browser-worker');expect(page.locator('#referenceState')).to_have_text('Context captured',timeout=10000)
                    expect(page.locator('#referenceTranscript')).to_contain_text('First fixture cue.')
                    assert runtime.reference_intakes.repository.get(key,2)['intake']['reference_snapshot_sha256']==identity
                    page.reload();expect(page.locator('#referenceState')).to_have_text('Context captured')
                    if width<=760:
                        page.locator('#studioMenuToggle').click();expect(page.locator('.studio-sidebar')).to_have_class(__import__('re').compile('open'))
                        page.keyboard.press('Escape');expect(page.locator('#studioMenuToggle')).to_have_attribute('aria-expanded','false')
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                    assert not errors,errors
                    page.locator('#referenceBrief summary').click();expect(page.locator('#briefProposals')).to_contain_text('Source excerpt:')
                    page.locator('#referenceDetail').scroll_into_view_if_needed();page.screenshot(path=str(evidence/f'{name}.png'),full_page=True)
                    results.append(dict(viewport=name,width=width,intake_id=key,revision=3,checks=['signed-in navigation','queue','missing captions','SRT fallback','immutable history','download hash','preserved draft','failure without flicker','fresh capture','reload','mobile menu'],js_errors=errors,overflow=False))
                    page.locator('#refreshReference').click();expect(page.locator('#referenceState')).to_have_text('Capture pending')
                    _cancel_with_delayed_read(page,key)
                    assert runtime.reference_intakes.run_once('browser-worker') is None
                    assert context.request.get(base+'/api/jobs').json()==[]
                    if name=='desktop':_check_selection_races(page,context,base,runtime,key)
                    page.locator('#signOutButton').click();page.wait_for_url(base+'/login');context.close()
            finally:browser.close()
        (evidence/'review.json').write_text(json.dumps(results,indent=2)+'\n')
    finally:
        server.should_exit=True;thread.join(15);listener.close()
    assert not thread.is_alive()


def _check_selection_races(page,context,base,runtime,original_id):
    """Delay reads and durable mutation responses while switching references."""
    from playwright.sync_api import expect
    from tubeforge.reference.extractor import YoutubeReferenceExtractor
    from test_reference_intake_extractor import FixtureHTTP,player
    original_title=page.locator('#referenceTitle').inner_text()
    token=next(c['value'] for c in context.cookies() if c['name']=='tubeforge_csrf')
    other_player=player(video_id='ZbCdEfGhI_1');other_player['videoDetails']['title']='Alternate reference'
    runtime.reference_intakes.extractor=YoutubeReferenceExtractor(FixtureHTTP(other_player))
    created=context.request.post(base+'/api/reference-intakes',headers={'x-csrf-token':token},data={'reference_url':'https://www.youtube.com/watch?v=ZbCdEfGhI_1','target_duration_seconds':600})
    assert created.status==201
    other_id=created.json()['intake']['intake_id'];runtime.reference_intakes.run_once('browser-worker')
    page.locator('#reloadReferences').click()
    held=[];pattern='**/api/reference-intakes/'+other_id
    page.route(pattern,lambda route:held.append(route))
    page.locator('#referenceList button').filter(has_text='Alternate reference').click()
    expect(page.locator('#refreshReference')).to_be_disabled()
    expect(page.locator('#saveTranscript')).to_be_disabled()
    page.wait_for_timeout(100);assert held
    for route in held:route.continue_()
    page.unroute(pattern)
    expect(page.locator('#referenceTitle')).to_have_text('Alternate reference')
    mutation=[];pattern='**/api/reference-intakes/'+other_id+'/revisions'
    page.route(pattern,lambda route:mutation.append((route,route.fetch())))
    page.locator('#refreshReference').click()
    page.wait_for_timeout(150);assert mutation
    page.locator('#referenceList button').filter(has_text='AbCdEfGhI_1').click()
    expect(page.locator('#referenceTitle')).to_have_text(original_title)
    for route,response in mutation:route.fulfill(response=response)
    page.unroute(pattern)
    page.wait_for_timeout(150)
    expect(page.locator('#referenceTitle')).to_have_text(original_title)
    assert runtime.reference_intakes.repository.get(original_id)['intake']['revision']==4
    assert runtime.reference_intakes.repository.get(other_id)['intake']['revision']==2
    runtime.reference_intakes.repository.cancel(other_id,2,'browser-reviewer')


def _cancel_with_delayed_read(page,key):
    from playwright.sync_api import expect
    held=[];pattern='**/api/reference-intakes/'+key+'?revision=4'
    page.route(pattern,lambda route:held.append((route,route.fetch())))
    page.locator('#reloadReferences').click();page.wait_for_timeout(150);assert held
    page.locator('#cancelReference').click();expect(page.locator('#referenceState')).to_have_text('Capture failed')
    for route,response in held:route.fulfill(response=response)
    page.unroute(pattern);page.wait_for_timeout(150)
    expect(page.locator('#referenceState')).to_have_text('Capture failed')
