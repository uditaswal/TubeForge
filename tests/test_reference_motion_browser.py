"""Opt-in real Chromium check; uses an isolated local database and no provider calls."""
import hashlib
import json
import os
from pathlib import Path
import socket
import threading
import time

import pytest

pytestmark = pytest.mark.skipif(os.environ.get('TUBEFORGE_MOTION_BROWSER') != '1', reason='opt-in Chromium smoke')


def test_signed_in_reference_scene_review_desktop_and_mobile(tmp_path):
    from playwright.sync_api import sync_playwright
    import uvicorn
    from test_api_workflow import _migrate
    from tubeforge.api.app import create_app
    from tubeforge.core.config import Settings, AppConfig, AuthConfig, DatabaseConfig
    from tubeforge.db.repositories import Artifact
    from tubeforge.domain.contracts import ContentPackage
    from tubeforge.domain.states import JobState

    root = Path(__file__).resolve().parents[1]
    package_path = Path(os.environ.get('TUBEFORGE_MOTION_REVIEW_PACKAGE', str(root / 'artifacts/review/reference-motion-speech/content_package.json')))
    package = ContentPackage.model_validate_json(package_path.read_bytes())
    expected_anchors={scene.scene_id:list(scene.visual.line_reveal_words) for scene in package.reference_short.scenes
                      if getattr(scene.visual,'line_reveal_words',())}
    assert expected_anchors
    database = tmp_path/'browser.db'
    _migrate(database)
    app = create_app(Settings(app=AppConfig(name='Motion browser test', environment='test'),
        database=DatabaseConfig(url=f'sqlite:///{database}'), auth=AuthConfig(enabled=True)))
    runtime = app.state.runtime
    runtime.auth.create_admin('motion-reviewer', 'test-only-reference-motion-password')
    runtime.jobs.create('motion-review-fixture', package.request)
    runtime.jobs.update_state('motion-review-fixture', JobState.SCRIPT_APPROVAL_REQUIRED)
    runtime.artifacts.save(Artifact('motion-review-fixture', JobState.CONTENT_GENERATING,
        'content_package', str(package_path), hashlib.sha256(package_path.read_bytes()).hexdigest(), {}))
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    worker = threading.Thread(target=server.run, kwargs={'sockets':[listener]}, daemon=True)
    worker.start()
    deadline = time.monotonic()+15
    while not server.started and worker.is_alive() and time.monotonic() < deadline:
        time.sleep(.05)
    assert server.started
    evidence = Path(os.environ.get('TUBEFORGE_MOTION_BROWSER_EVIDENCE', str(root/'artifacts/review/reference-motion-browser')))
    evidence.mkdir(parents=True, exist_ok=True)
    results = []
    try:
        with sync_playwright() as browser_api:
            browser = browser_api.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
                args=['--no-sandbox','--disable-dev-shm-usage'])
            try:
                for name, width, height in [('desktop',1440,1000),('mobile',390,844)]:
                    context = browser.new_context(viewport=dict(width=width,height=height))
                    errors = []
                    page = context.new_page()
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    base = f'http://127.0.0.1:{listener.getsockname()[1]}'
                    response = context.request.post(base+'/login', data={
                        'username':'motion-reviewer','password':'test-only-reference-motion-password'})
                    assert response.ok
                    page.goto(base+'/#generations', wait_until='networkidle')
                    assert not errors, errors
                    page.locator('#filter').select_option('needs_review')
                    page.get_by_role('button', name='View / edit script', exact=True).click()
                    page.locator('dialog[open]').wait_for()
                    page.wait_for_function("document.querySelector('#skillReview').textContent.includes('line_reveal_words')")
                    details = json.loads(page.locator('#skillReview').text_content())
                    observed={scene['scene_id']:scene['visual']['line_reveal_words'] for scene in details['reference_scenes']
                              if scene.get('visual',{}).get('line_reveal_words')}
                    assert observed == expected_anchors
                    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                    assert not errors
                    page.locator('#skillReview').evaluate("el => { const details=el.closest('details'); if(details)details.open=true; }")
                    page.locator('#skillReview').scroll_into_view_if_needed()
                    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                    page.screenshot(path=str(evidence/f'{name}.png'), full_page=True)
                    results.append(dict(viewport=name, anchors=expected_anchors, js_errors=errors, overflow=False))
                    context.close()
            finally:
                browser.close()
        (evidence/'review.json').write_text(json.dumps(results,indent=2))
    finally:
        server.should_exit=True
        worker.join(15)
        listener.close()
    assert not worker.is_alive()
