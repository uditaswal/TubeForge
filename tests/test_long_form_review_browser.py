"""Actual signed-in Chromium review against an isolated synthetic writer."""
import json
import os
from pathlib import Path
import socket
from threading import Thread
import time

import pytest

from test_long_form_review_api import review_app
from test_reference_intake_extractor import URL

pytestmark = pytest.mark.skipif(os.environ.get('TUBEFORGE_LONG_FORM_BROWSER') != '1', reason='opt-in Chromium workflow')


def test_long_form_review_at_three_viewports(tmp_path):
    import uvicorn
    from playwright.sync_api import expect, sync_playwright

    evidence = Path(__file__).resolve().parents[1] / 'artifacts/review/long-form-lf2-c-browser'
    evidence.mkdir(parents=True, exist_ok=True)
    reports = []
    with review_app(tmp_path) as (app, runtime, writer):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        base = 'http://127.0.0.1:' + str(listener.getsockname()[1])
        server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
        thread = Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 15
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(.05)
            assert server.started
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox', '--disable-dev-shm-usage'])
                try:
                    for name, width, height in [('desktop', 1440, 1000), ('tablet', 820, 1180), ('mobile', 390, 844)]:
                        context = browser.new_context(viewport={'width': width, 'height': height}, accept_downloads=True)
                        page = context.new_page()
                        errors = []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        page.goto(base + '/login')
                        page.locator('[name=username]').fill('script-reviewer')
                        page.locator('[name=password]').fill('test-only-script-password')
                        page.locator('button[type=submit]').click()
                        page.wait_for_url(base + '/')
                        if name == 'mobile':
                            page.locator('.studio-menu').click()
                        page.get_by_role('link', name='Reference videos', exact=True).click()
                        page.locator('#referenceUrl').fill(URL)
                        with page.expect_response(lambda response: response.request.method == 'POST' and response.url.endswith('/api/reference-intakes')):
                            page.locator('#captureReference').click()
                        runtime.reference_intakes.run_once('reference-browser-fixture')
                        expect(page.locator('#prepareLongForm')).to_be_visible(timeout=10000)
                        page.locator('#prepareLongForm').click()
                        expect(page.locator('#lfTopic')).to_have_value('Synthetic reference')
                        topic = 'Synthetic script for ' + name
                        page.locator('#lfTopic').fill(topic)
                        page.locator('#lfAngle').fill('Show a separate example using a verifiable source.')
                        page.locator('#lfAudience').fill('Curious beginners')
                        page.locator('#lfCreate').click()
                        expect(page.locator('#lfTitle')).to_have_text(topic)
                        expect(page.locator('#lfState')).to_have_text('Queued')
                        run_id = runtime.long_form_writing.repository.list()[0]['id']
                        writer['mode'] = 'first_bad' if name == 'tablet' else 'pass'
                        for _ in range(4 if name == 'tablet' else 3):
                            runtime.long_form_writing.run_once('script-browser-fixture')
                        expect(page.locator('#lfState')).to_have_text('Ready for review', timeout=15000)
                        expect(page.locator('#lfMeta')).to_contain_text('Codex · fixture-model')
                        expect(page.locator('#lfApprove')).to_be_disabled()
                        page.locator('#lfChapters summary').first.click()
                        expect(page.locator('#lfChapters')).to_contain_text('Why should you check 3 source hashes')
                        page.locator('#lfEditorial summary').click()
                        expect(page.locator('#lfFindings')).to_contain_text('Original fixture addition')
                        page.locator('#lfUsagePanel > summary').click()
                        if name == 'tablet':
                            page.locator('#lfCalls summary').filter(has_text='Rejected by validation').click()
                            expect(page.locator('#lfCalls')).to_contain_text('{bad synthetic output')
                        page.locator('#lfReviewed').check()
                        expect(page.locator('#lfApprove')).to_be_enabled()
                        page.locator('#lfDetail').scroll_into_view_if_needed()
                        page.screenshot(path=str(evidence / (name + '.png')))
                        if name == 'desktop':
                            rendered = page.evaluate('''() => {
                                const clone = document.documentElement.cloneNode(true);
                                clone.querySelectorAll('script').forEach(node => node.remove());
                                for (const field of document.querySelectorAll('input[id], textarea[id], select[id]')) {
                                    const copy = clone.querySelector('#' + field.id);
                                    if (field.tagName === 'SELECT') {
                                        for (const option of copy.options) option.toggleAttribute('selected', option.value === field.value);
                                    } else if (field.tagName === 'TEXTAREA') {
                                        copy.textContent = field.value;
                                    } else if (field.type === 'checkbox') {
                                        copy.toggleAttribute('checked', field.checked);
                                    } else {
                                        copy.setAttribute('value', field.value);
                                    }
                                }
                                return '<!doctype html>' + clone.outerHTML;
                            }''')
                            (evidence / 'review.html').write_text(rendered)
                        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                        assert not errors, errors
                        with page.expect_download() as downloaded:
                            page.locator('#lfExport').click()
                        data = json.loads(Path(downloaded.value.path()).read_bytes())
                        run = data['preparation']
                        assert run['id'] == run_id and run['review_identity']
                        assert run['state'] == 'awaiting_review'
                        if name == 'desktop':
                            check_delayed_decision(page, run_id)
                        else:
                            page.locator('#lfReject').click()
                            expect(page.locator('#lfConfirm')).to_be_visible()
                            page.locator('#lfSaveDecision').click()
                            expect(page.locator('#lfState')).to_have_text('Script rejected')
                        if name == 'mobile':
                            check_delayed_cancellation(page, runtime)
                        assert context.request.get(base + '/api/jobs').json() == []
                        reports.append({'viewport': name, 'width': width, 'run_id': run_id, 'browser_errors': errors,
                                        'state': runtime.long_form_writing.repository.get(run_id)['state']})
                        page.locator('#signOutButton').click()
                        page.wait_for_url(base + '/login')
                        context.close()
                finally:
                    browser.close()
        finally:
            server.should_exit = True
            thread.join(15)
            listener.close()
        assert not thread.is_alive()
    (evidence / 'review.json').write_text(json.dumps(reports, indent=2))


def check_delayed_decision(page, run_id):
    from playwright.sync_api import expect
    pattern = '**/api/long-form/' + run_id
    held = []
    def hold(route):
        held.append((route, route.fetch()))
    page.route(pattern, hold)
    page.locator('#lfReload').click()
    expect(page.locator('#lfChapters details').first).to_have_attribute('open', '')
    page.locator('#lfApprove').click()
    expect(page.locator('#lfConfirm')).to_be_visible()
    assert held
    page.locator('#lfSaveDecision').click()
    expect(page.locator('#lfState')).to_have_text('Script approved')
    for route, snapshot in held:
        route.fulfill(response=snapshot)
    page.unroute(pattern)
    expect(page.locator('#lfState')).to_have_text('Script approved')
    expect(page.locator('#lfReviewed')).to_be_checked()


def check_delayed_cancellation(page, runtime):
    from playwright.sync_api import expect

    page.locator('#lfTopic').fill('Synthetic pending cancellation')
    page.get_by_text('Use your own primary sources', exact=True).click()
    page.locator('#lfPrimaryUrls').fill('https://example.com/primary\nhttps://example.org/primary')
    page.locator('#lfCreate').click()
    expect(page.locator('#lfTitle')).to_have_text('Synthetic pending cancellation')
    expect(page.locator('#lfState')).to_have_text('Queued')
    expect(page.locator('#lfMessage')).to_have_text('Next: capture supplied primary pages.')
    run_id = runtime.long_form_writing.repository.list()[0]['id']
    pattern = '**/api/long-form/' + run_id
    held = []

    def hold(route):
        held.append((route, route.fetch()))

    page.route(pattern, hold)
    page.locator('#lfReload').click()
    page.wait_for_timeout(150)
    assert held
    page.locator('#lfCancel').click()
    expect(page.locator('#lfState')).to_have_text('Preparation cancelled')
    for route, snapshot in held:
        route.fulfill(response=snapshot)
    page.unroute(pattern)
    expect(page.locator('#lfState')).to_have_text('Preparation cancelled')
    assert runtime.long_form_writing.run_once('cancelled-browser-fixture') is None
