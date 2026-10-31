"""Authenticated batch endpoints inherit the application's auth/CSRF middleware."""
from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from tubeforge.batch_plans import parse_batch
from tubeforge.db.batch_plans import BatchPlanRepository


class BatchImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    markdown: str = Field(max_length=2_000_000)
    commit: bool = False


def register_batch_routes(app, runtime):
    repository = BatchPlanRepository(runtime.database.session_factory)

    @app.post('/api/batch-plans/import', tags=['batch'])
    def import_plan(value: BatchImportRequest):
        plan = parse_batch(value.markdown)
        if plan.errors:
            raise HTTPException(422, detail=[error.model_dump() for error in plan.errors])
        return {'committed': value.commit, 'items': repository.import_shorts(plan.shorts, commit=value.commit)}

    @app.get('/api/batch-plans', tags=['batch'])
    def list_plans():
        return repository.list()

    @app.get('/batch', response_class=HTMLResponse, include_in_schema=False)
    def batch_page():
        from tubeforge.api.batch_ui import BATCH_HTML
        return BATCH_HTML
