"""Opt-in native preview/final worker flow from imported, reviewed local media.

No content/TTS/source acquisition: their exact saved checkpoints are imported.
Approvals here are test-only, in a fresh database, never production decisions.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import threading
import time

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get('TUBEFORGE_MOTION_WORKFLOW') != '1',
    reason='opt-in native worker renders and signed-in Chromium',
)


class ForbiddenProvider:
    def __getattr__(self, name):
        raise AssertionError(f'imported-media workflow unexpectedly requested provider operation: {name}')


def test_native_worker_preview_approval_and_final_from_saved_media():
    from playwright.sync_api import sync_playwright
    import uvicorn
    from test_api_workflow import _migrate
    from scripts.benchmark_story_short import verify_prepared
    from tubeforge.api.app import create_app
    from tubeforge.core.config import Settings, AppConfig, AuthConfig, DatabaseConfig, WorkerConfig
    from tubeforge.db.repositories import Artifact
    from tubeforge.domain.contracts import ContentPackage
    from tubeforge.domain.states import ApprovalGate, JobState
    from tubeforge.pipeline.reference_short import write_options
    from tubeforge.workers.service import WorkerService

    source = Path(os.environ['TUBEFORGE_MOTION_WORKFLOW_INPUT']).resolve()
    output = Path(os.environ['TUBEFORGE_MOTION_WORKFLOW_OUTPUT']).resolve()
    assert output != source and not output.is_relative_to(source)
    verify_prepared(source)
    resume = os.environ.get('TUBEFORGE_MOTION_WORKFLOW_RESUME') == '1'
    if not resume:
        output.mkdir(parents=True, exist_ok=False)
    database = output / 'workflow.db'
    if not resume:
        _migrate(database)
    settings = Settings(app=AppConfig(name='Motion workflow test', environment='test'),
                        database=DatabaseConfig(url=f'sqlite:///{database}'), auth=AuthConfig(enabled=True))
    settings.pipeline.voice.artifact_root = output / 'jobs'
    settings.pipeline.reference_short.budget_realtime_factor = 20
    settings.pipeline.youtube.enabled = False
    app = create_app(settings)

    def forbid_providers(runtime):
        for name in ('content', 'media', 'voice', 'publisher'):
            setattr(runtime.orchestrator, name, ForbiddenProvider())
        runtime.orchestrator.source_ingestor = ForbiddenProvider()
        runtime.orchestrator.source_provider = ForbiddenProvider()

    runtime = app.state.runtime
    forbid_providers(runtime)
    job_id = 'motion-native-workflow'
    folder = output / 'jobs' / job_id
    if not resume:
        runtime.auth.create_admin('motion-workflow', 'test-only-motion-workflow-password')
        folder.mkdir(parents=True)
        proof = json.loads((source / 'prepared-inputs.json').read_text())
        for name in proof['files']:
            if name.startswith('reference/'):
                target = folder / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / name, target)
        package = ContentPackage.model_validate_json((source / 'content_package.json').read_bytes())
        package = package.model_copy(update={'request': package.request.model_copy(update={'video_style': 'story', 'review_mode': 'manual'})})
        package_path = folder / 'content_package.json'
        package_path.write_text(package.model_dump_json(indent=2))
        write_options(folder / 'reference', show_sources=package.request.show_source_credit,
                      watermark=package.request.channel_watermark, mascot=package.request.show_mascot, style='story')
        runtime.jobs.create(job_id, package.request)
        for stage, name, path in (
            (JobState.CONTENT_GENERATING, 'content_package', package_path),
            (JobState.VOICE_GENERATION, 'narration', folder / 'reference/narration.wav'),
            (JobState.VOICE_GENERATION, 'timing_map', folder / 'reference/timeline.json'),
        ):
            runtime.artifacts.save(Artifact(job_id, stage, name, str(path),
                hashlib.sha256(path.read_bytes()).hexdigest(), {'scope': 'test-only imported reviewed checkpoint'}))
        runtime.approvals.record('imported-script-test-only', job_id, ApprovalGate.SCRIPT,
            actor='test-only-import', reviewed_identity=hashlib.sha256(package_path.read_bytes()).hexdigest())
        runtime.jobs.update_state(job_id, JobState.CAPTION_GENERATION)
        (output / 'import.json').write_text(json.dumps({'scope': 'isolated test only; no production approval',
            'input': str(source), 'prepared_sha256': hashlib.sha256((source / 'prepared-inputs.json').read_bytes()).hexdigest(),
            'package_sha256': hashlib.sha256(package_path.read_bytes()).hexdigest(),
            'request_visual_change': 'video_style=story', 'imported_stage': 'caption_generation'}, indent=2))
    else:
        imported = json.loads((output / 'import.json').read_text())
        assert imported['input'] == str(source)
        assert imported['prepared_sha256'] == hashlib.sha256((source / 'prepared-inputs.json').read_bytes()).hexdigest()
        assert imported['package_sha256'] == hashlib.sha256((folder / 'content_package.json').read_bytes()).hexdigest()
        assert runtime.jobs.get(job_id).state is JobState.PREVIEW_READY
        assert runtime.orchestrator._reference_preview_is_current(runtime.jobs.get(job_id))

    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(.05)
    assert server.started
    evidence = []
    try:
        worker = WorkerService('motion-preview-worker', runtime.jobs, runtime.orchestrator, WorkerConfig())
        preview_job = runtime.jobs.get(job_id) if resume else worker.run_once()
        assert preview_job.state is JobState.PREVIEW_READY, preview_job.failure_message
        assert runtime.jobs.get(job_id).claim_owner is None
        preview_manifest = runtime.orchestrator._required_json(job_id, JobState.PREVIEW_RENDERING, 'preview_manifest')
        assert runtime.approvals.decision(job_id, ApprovalGate.PREVIEW, reviewed_identity=preview_manifest['render_identity']) is None
        assert worker.run_once() is None  # approval wait must not rerender
        print('native preview ready', preview_manifest['artifact_checksum'], flush=True)
        with sync_playwright() as api:
            browser = api.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage'])
            try:
                for name, width, height in [('desktop', 1440, 1000), ('mobile', 390, 844)]:
                    context = browser.new_context(viewport={'width': width, 'height': height})
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    base = f'http://127.0.0.1:{listener.getsockname()[1]}'
                    assert context.request.post(base + '/login', data={'username': 'motion-workflow',
                        'password': 'test-only-motion-workflow-password'}).ok
                    page.goto(base + '/#generations', wait_until='networkidle')
                    page.locator('#filter').select_option('all')
                    page.get_by_role('button', name='Watch preview', exact=True).click()
                    player = page.locator('#player')
                    page.wait_for_function('document.querySelector("#player").readyState >= 2')
                    assert player.evaluate('(v)=>v.videoWidth') == 720
                    assert player.evaluate('(v)=>v.videoHeight') == 1280
                    player.evaluate('(v)=>{v.muted=true; v.currentTime=40.8}')
                    page.wait_for_function('!document.querySelector("#player").seeking')
                    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                    page.screenshot(path=str(output / f'{name}-preview.png'), full_page=True)
                    page.locator('#videoDialog button').first.click()
                    if name == 'mobile':
                        csrf = next(c['value'] for c in context.cookies() if c['name'] == 'tubeforge_csrf')
                        stale = context.request.post(base + f'/api/jobs/{job_id}/approvals/preview',
                            headers={'x-csrf-token': csrf}, data={'status': 'approved', 'actor': 'test-only', 'reviewed_identity': 'stale-preview'})
                        assert stale.status == 409
                        with page.expect_response(lambda response: response.url.endswith('/approvals/preview') and response.request.method == 'POST') as decision:
                            page.get_by_role('button', name='Approve preview', exact=True).click()
                        assert decision.value.ok
                        approval = runtime.approvals.approved(job_id, ApprovalGate.PREVIEW, reviewed_identity=preview_manifest['render_identity'])
                        assert approval is not None
                    assert not errors
                    evidence.append({'viewport': name, 'preview': '720x1280 decoded', 'overflow': False, 'js_errors': errors})
                    context.close()

                # A fresh runtime/worker reads the durable approval and saved media.
                restarted = create_app(settings).state.runtime
                forbid_providers(restarted)
                final_worker = WorkerService('motion-final-worker', restarted.jobs, restarted.orchestrator, WorkerConfig())
                final_job = final_worker.run_once()
                assert final_job.state is JobState.FINAL_READY, final_job.failure_message
                assert restarted.jobs.get(job_id).claim_owner is None
                final = restarted.artifacts.get(job_id, JobState.FINAL_RENDERING, 'final')
                final_manifest = restarted.orchestrator._required_json(job_id, JobState.FINAL_RENDERING, 'final_manifest')
                assert final_manifest['approval_identity'] == preview_manifest['render_identity']
                assert final_manifest['approval_id'] == approval.id
                assert final.checksum_sha256 == hashlib.sha256(Path(final.path).read_bytes()).hexdigest()
                for name, width, height in [('desktop', 1440, 1000), ('mobile', 390, 844)]:
                    context = browser.new_context(viewport={'width': width, 'height': height})
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    assert context.request.post(base + '/login', data={'username': 'motion-workflow',
                        'password': 'test-only-motion-workflow-password'}).ok
                    page.goto(base + '/#generations', wait_until='networkidle')
                    page.locator('#filter').select_option('all')
                    page.get_by_role('button', name='Watch video', exact=True).click()
                    page.wait_for_function('document.querySelector("#player").readyState >= 2')
                    player = page.locator('#player')
                    assert player.evaluate('(v)=>[v.videoWidth,v.videoHeight]') == [1080, 1920]
                    player.evaluate('(v)=>{v.muted=true;v.currentTime=42}')
                    page.wait_for_function('!document.querySelector("#player").seeking')
                    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                    assert not errors
                    page.screenshot(path=str(output / f'{name}-final.png'), full_page=True)
                    evidence.append({'viewport': name, 'final': '1080x1920 decoded', 'overflow': False, 'js_errors': errors})
                    context.close()
                assert restarted.approvals.decision(job_id, ApprovalGate.PUBLICATION_PREPARATION) is None
                (output / 'workflow-review.json').write_text(json.dumps({'scope': 'native imported-media workflow; test-only approvals',
                    'preview_manifest': preview_manifest, 'final_manifest': final_manifest,
                    'screens': evidence, 'final_sha256': final.checksum_sha256,
                    'events': [{'type': row.event_type, 'details': row.details} for row in runtime.events.list_for_job(job_id, limit=100)]}, indent=2))
            finally:
                browser.close()
    finally:
        server.should_exit = True
        thread.join(15)
        listener.close()
    assert not thread.is_alive()


def test_saved_native_final_plays_on_desktop_and_mobile():
    """Verify presented, advancing video frames rather than only media metadata."""
    from playwright.sync_api import sync_playwright
    import uvicorn
    from tubeforge.api.app import create_app
    from tubeforge.core.config import Settings, AppConfig, AuthConfig, DatabaseConfig

    output = Path(os.environ['TUBEFORGE_MOTION_WORKFLOW_OUTPUT']).resolve()
    reviewed = json.loads((output / 'workflow-review.json').read_text())
    final = output / 'jobs/motion-native-workflow/final.mp4'
    assert hashlib.sha256(final.read_bytes()).hexdigest() == reviewed['final_sha256']
    settings = Settings(app=AppConfig(name='Motion playback test', environment='test'),
        database=DatabaseConfig(url=f'sqlite:///{output / "workflow.db"}'), auth=AuthConfig(enabled=True))
    settings.pipeline.voice.artifact_root = output / 'jobs'
    app = create_app(settings)
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(.05)
    assert server.started
    results = []
    try:
        with sync_playwright() as api:
            browser = api.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage'])
            try:
                for name, width, height in [('desktop', 1440, 1000), ('mobile', 390, 844)]:
                    context = browser.new_context(viewport={'width': width, 'height': height})
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    base = f'http://127.0.0.1:{listener.getsockname()[1]}'
                    assert context.request.post(base + '/login', data={'username': 'motion-workflow',
                        'password': 'test-only-motion-workflow-password'}).ok
                    page.goto(base + '/#generations', wait_until='networkidle')
                    page.locator('#filter').select_option('all')
                    page.get_by_role('button', name='Watch video', exact=True).click()
                    page.wait_for_function('document.querySelector("#player").readyState >= 2')
                    player = page.locator('#player')
                    player.evaluate('''async v => {
                        v.muted=true;
                        await new Promise(resolve=>{v.addEventListener('seeked',resolve,{once:true});v.currentTime=41.5});
                        await v.play();
                    }''')
                    page.wait_for_function('''() => {const v=document.querySelector('#player');
                        return v.currentTime>42.1 && !v.paused && !v.seeking && v.readyState>=3}''')
                    playback = player.evaluate('''v=>{v.pause();return {time:v.currentTime,
                        frames:v.getVideoPlaybackQuality().totalVideoFrames,width:v.videoWidth,height:v.videoHeight}}''')
                    assert playback['frames'] > 0 and [playback['width'], playback['height']] == [1080, 1920]
                    assert not errors
                    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                    page.screenshot(path=str(output / f'{name}-played-final.png'), full_page=True)
                    results.append({'viewport': name, 'muted_playback': playback, 'js_errors': errors, 'overflow': False})
                    context.close()
            finally:
                browser.close()
        (output / 'playback-review.json').write_text(json.dumps({'final_sha256': reviewed['final_sha256'],
            'scope': 'short muted playback sample, full watch/listen still pending', 'results': results}, indent=2))
    finally:
        server.should_exit = True
        thread.join(15)
        listener.close()
    assert not thread.is_alive()
