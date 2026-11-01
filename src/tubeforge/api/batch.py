"""Authenticated batch endpoints inherit the application's auth/CSRF middleware."""
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from datetime import date
from typing import Literal
from tubeforge.batch_plans import parse_batch
from tubeforge.db.batch_plans import BatchPlanRepository


class BatchImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    markdown: str = Field(max_length=2_000_000)
    commit: bool = False
    plan_id: str = Field(default="default", pattern=r"^[a-z0-9-]{1,80}$")


class BatchProduceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(min_length=1, max_length=200)


class BatchReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal['approve', 'reject', 'ready', 'regenerate']
    reviewed_identity: str = Field(pattern=r'^[a-f0-9]{64}$')


class BatchAutomationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = False
    start_time: str = Field(default='22:00', pattern=r'^([01][0-9]|2[0-3]):[0-5][0-9]$')
    timezone: str = 'Asia/Kolkata'
    day_offset: int = Field(default=1, ge=0, le=7)


class BatchHoldRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    hold: bool


def register_batch_routes(app, runtime, build_request):
    repository = BatchPlanRepository(runtime.database.session_factory)

    @app.post('/api/batch-plans/import', tags=['batch'])
    def import_plan(value: BatchImportRequest):
        plan = parse_batch(value.markdown)
        if plan.errors:
            raise HTTPException(422, detail=[error.model_dump() for error in plan.errors])
        return {'committed': value.commit, 'items': repository.import_shorts(plan.shorts, commit=value.commit, plan_id=value.plan_id)}

    @app.get('/api/batch-plans', tags=['batch'])
    def list_plans(day: date | None = None, plan_id: str | None = None):
        items = repository.list()
        if plan_id:
            items = [item for item in items if item['plan_id'] == plan_id]
        if day:
            items = [item for item in items if (item['short'].get('publish_at') or '')[:10] == day.isoformat()]
        for item in items:
            item['qa'] = None
            if item['job_id']:
                job = runtime.jobs.get(item['job_id'])
                item['status'] = job.state.value
                item['failure_message'] = job.failure_message
                if job.failure_message and 'exhaust' in job.failure_message.lower():
                    item['status'] = 'needs operator decision'
                item['qa'] = (repository.for_job(job.id) or {}).get('batch_qa')
                item['activity_url'] = f'/api/jobs/{job.id}/events'
        finished = [item for item in items if item['status'] == 'final_ready']
        durations = []
        for item in finished:
            events = runtime.events.list_for_job(item['job_id'], limit=1000)
            seconds = sum(float(e.details.get('elapsed_seconds', 0)) for e in events if e.event_type == 'batch_run_finished')
            if seconds:
                durations.append(seconds)
        remaining = sum(bool(item['job_id']) and item['status'] not in {'final_ready', 'failed_validation', 'failed_exhausted', 'cancelled', 'needs operator decision'} for item in items)
        waiting = any(item['status'] in {'script_approval_required', 'preview_ready'} for item in items)
        eta = round(sum(durations) / len(durations) * remaining) if durations and not waiting else None
        # ETA is unknown until completed jobs supply measured timings.
        for item in items:
            item['progress'] = {'finished': len(finished), 'total': sum(bool(value['job_id']) for value in items), 'eta_seconds': eta}
        return items

    @app.get('/batch', response_class=HTMLResponse, include_in_schema=False)
    def batch_page(request: Request):
        from tubeforge.api.batch_ui import render_batch_html
        session = runtime.auth.session(request.cookies.get('tubeforge_session'))
        return render_batch_html(runtime.auth.username_for(session.user_id) if session else None)

    @app.post('/api/batch-plans/produce', tags=['batch'])
    def produce(value: BatchProduceRequest):
        if len(set(value.ids)) != len(value.ids):
            raise HTTPException(422, detail='duplicate short ids')
        try:
            items = repository.produce(value.ids, build_request)
        except ValueError as error:
            raise HTTPException(422, detail=str(error)) from error
        for item in items:
            if item['action'] == 'created':
                runtime.events.append(item['job_id'], 'batch_job_created', short_id=item['id'])
        return {'items': items}

    from tubeforge.db.batch_review import BatchReviewRepository
    reviews = BatchReviewRepository(runtime.database.session_factory, runtime.orchestrator.artifact_root)

    @app.get('/api/batch-plans/review', tags=['batch'])
    def day_review(day: date | None = None):
        return reviews.list_day(day.isoformat() if day else None)

    @app.post('/api/batch-plans/{short_id}/review', tags=['batch'])
    def review_decision(short_id: str, value: BatchReviewRequest, request: Request):
        session = runtime.auth.session(request.cookies.get('tubeforge_session'))
        actor = str(session.user_id) if session else 'local-operator'
        try:
            return reviews.decide(short_id, value.action, value.reviewed_identity, actor)
        except KeyError as error:
            raise HTTPException(404, detail=str(error)) from error
        except (ValueError, OSError) as error:
            raise HTTPException(409, detail=str(error)) from error

    @app.get('/batch/review', response_class=HTMLResponse, include_in_schema=False)
    def day_review_page(request: Request):
        from tubeforge.api.batch_review_ui import render_review_html
        session = runtime.auth.session(request.cookies.get('tubeforge_session'))
        return render_review_html(runtime.auth.username_for(session.user_id) if session else None)

    from tubeforge.db.batch_automation import BatchAutomationRepository
    automation = BatchAutomationRepository(runtime.database.session_factory)

    @app.get('/api/batch-plans/automation/{plan_id}', tags=['batch'])
    def automation_state(plan_id: str):
        result = automation.get(plan_id)
        last = result.get('last_run')
        if last and last.get('result'):
            for item in last['result'].get('items', []):
                if item.get('job_id'):
                    job = runtime.jobs.get(item['job_id'])
                    item['status'] = 'needs operator decision' if job.failure_message and 'exhaust' in job.failure_message.lower() else job.state.value
        return result

    @app.put('/api/batch-plans/automation/{plan_id}', tags=['batch'])
    def configure_automation(plan_id: str, value: BatchAutomationRequest):
        import re
        if not re.fullmatch(r'[a-z0-9-]{1,80}', plan_id):
            raise HTTPException(422, detail='invalid plan id')
        try:
            return automation.configure(plan_id, **value.model_dump())
        except (ValueError, KeyError) as error:
            raise HTTPException(422, detail=str(error)) from error

    @app.put('/api/batch-plans/hold', tags=['batch'])
    def set_batch_hold(value: BatchHoldRequest):
        return {'hold': automation.hold(value.hold)}

    @app.get('/api/batch-plans/{short_id}/export', response_class=HTMLResponse, tags=['batch'])
    def open_export(short_id: str):
        import html
        from urllib.parse import quote
        try:
            reviews.export_file(short_id, 'package.json')
        except KeyError as error:
            raise HTTPException(404, detail=str(error)) from error
        except (ValueError, OSError) as error:
            raise HTTPException(409, detail=str(error)) from error
        from tubeforge.api.studio_shell import STUDIO_CSS
        base = '/api/batch-plans/' + quote(short_id, safe='') + '/export/'
        return '<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Local staged export</title><style>' + STUDIO_CSS + 'body{max-width:800px;margin:40px auto;padding:0 20px}a{color:var(--cyan)}li{margin:16px 0}</style><h1>Local staged export: ' + html.escape(short_id) + '</h1><p>Reviewed local files. No publication has occurred.</p><ul>' + ''.join('<li><a href="' + base + name + '">' + name + '</a></li>' for name in ['final.mp4', 'thumbnail.jpg', 'package.json']) + '</ul><a href="/batch/review">Return to review</a></html>'

    @app.get('/api/batch-plans/{short_id}/export/{name}', tags=['batch'])
    def download_export(short_id: str, name: str):
        from fastapi.responses import FileResponse
        try:
            path = reviews.export_file(short_id, name)
        except KeyError as error:
            raise HTTPException(404, detail=str(error)) from error
        except (ValueError, OSError) as error:
            raise HTTPException(409, detail=str(error)) from error
        return FileResponse(path, filename=name)
