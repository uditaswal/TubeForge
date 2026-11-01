"""Authenticated batch endpoints inherit the application's auth/CSRF middleware."""
from pathlib import Path
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


class BatchProduceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(min_length=1, max_length=200)


class BatchReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal['approve', 'reject', 'ready', 'regenerate']
    reviewed_identity: str = Field(pattern=r'^[a-f0-9]{64}$')


def register_batch_routes(app, runtime, build_request):
    repository = BatchPlanRepository(runtime.database.session_factory)

    @app.post('/api/batch-plans/import', tags=['batch'])
    def import_plan(value: BatchImportRequest):
        plan = parse_batch(value.markdown)
        if plan.errors:
            raise HTTPException(422, detail=[error.model_dump() for error in plan.errors])
        return {'committed': value.commit, 'items': repository.import_shorts(plan.shorts, commit=value.commit)}

    @app.get('/api/batch-plans', tags=['batch'])
    def list_plans(day: date | None = None):
        items = repository.list()
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
    def batch_page():
        from tubeforge.api.batch_ui import BATCH_HTML
        return BATCH_HTML

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
    export_root = Path(runtime.orchestrator.artifact_root).parent / 'batch-exports'
    reviews = BatchReviewRepository(runtime.database.session_factory, export_root=export_root)

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

    @app.get('/api/batch-plans/{short_id}/export', tags=['batch'])
    def batch_export(short_id: str):
        """The staged package for a ready short, re-verified against the reviewed artifact on every read."""
        from tubeforge.batch_export import verify
        item = next((x for x in reviews.list_day(None) if x['id'] == short_id), None)
        if item is None:
            raise HTTPException(404, detail='short not found')
        if not item['export']:
            raise HTTPException(404, detail='no export staged for this short')
        result = verify(Path(item['export']['path']), identity=item['reviewed_identity'] or 'unavailable')
        return {'status': result['status'], 'reason': result.get('reason'), 'path': item['export']['path'], 'package': result.get('package')}

    @app.get('/batch/review', response_class=HTMLResponse, include_in_schema=False)
    def day_review_page():
        from tubeforge.api.batch_review_ui import REVIEW_HTML
        return REVIEW_HTML
