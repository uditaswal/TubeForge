"""Signed-in LF2 preparation/review; creating a request performs no host work."""
import hashlib
import json
from typing import Literal

from fastapi import HTTPException,Request
from fastapi.responses import HTMLResponse,Response
from pydantic import BaseModel,ConfigDict,Field,ValidationError

from tubeforge.api.reference_intake import bounded_json
from tubeforge.db.long_form_writing import WritingConflict
from tubeforge.domain.long_form_writing import LongFormTokenPolicy
from tubeforge.core.errors import ProviderValidationError,RetryableProviderError


class PreparationRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    intake_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    intake_revision:int=Field(ge=1)
    topic:str=Field(min_length=1,max_length=500)
    angle:str=Field(min_length=1,max_length=1000)
    audience:str=Field(min_length=1,max_length=200)
    owner:Literal['codex','claude']='codex'
    model:Literal['sonnet-medium','opus']|None=None
    token_policy:LongFormTokenPolicy=Field(default_factory=LongFormTokenPolicy)


class ScriptDecision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    review_identity:str=Field(pattern=r'^[a-f0-9]{64}$')
    decision:Literal['approved','rejected']
    reviewed_evidence:Literal[True]


def register_long_form_routes(app,runtime,settings):
    service=runtime.long_form_writing;repo=service.repository
    def actor(request):
        session=runtime.auth.session(request.cookies.get('tubeforge_session'))
        return runtime.auth.username_for(session.user_id) if session else 'local-operator'
    def get(run_id):
        try:return repo.get(run_id)
        except KeyError:raise HTTPException(404,'Script preparation not found.') from None
        except ValueError:raise HTTPException(409,'Saved preparation integrity failed; inspect the stored evidence.') from None

    @app.get('/long-form',response_class=HTMLResponse,include_in_schema=False)
    def page(request:Request):
        from tubeforge.api.long_form_ui import render_long_form_html
        session=runtime.auth.session(request.cookies.get('tubeforge_session'))
        return render_long_form_html(runtime.auth.username_for(session.user_id) if session else None)

    @app.get('/api/long-form/options',tags=['long-form'])
    def options():
        owners=[dict(id='codex',model=None,label='Codex · '+settings.pipeline.codex.model)]
        if settings.pipeline.claude.enabled:
            owners.extend([dict(id='claude',model='sonnet-medium',label='Claude Sonnet · medium effort'),dict(id='claude',model='opus',label='Claude Opus · high effort')])
        return dict(writers=owners,token_policy=LongFormTokenPolicy().model_dump(),rendering_enabled=False)

    @app.get('/api/long-form',tags=['long-form'])
    def history():return dict(items=repo.list(),limit=50)

    @app.post('/api/long-form',status_code=201,tags=['long-form'])
    async def create(request:Request):
        try:
            value=PreparationRequest.model_validate(await bounded_json(request))
            defaults=LongFormTokenPolicy().model_dump()
            if any(v>defaults[k] for k,v in value.token_policy.model_dump().items()):raise ValueError('Token policy can only lower the displayed default bounds.')
            return service.create(**value.model_dump(exclude={'token_policy'}),token_policy=value.token_policy,actor=actor(request))
        except KeyError:raise HTTPException(404,'Reference intake revision not found.') from None
        except WritingConflict as error:raise HTTPException(409,str(error)) from error
        except (ValueError,ValidationError) as error:
            detail='Choose an exact ready reference revision and valid bounded brief/writer.' if isinstance(error,ValidationError) else str(error)
            raise HTTPException(422,detail) from None

    @app.get('/api/long-form/{run_id}',tags=['long-form'])
    def detail(run_id:str):return get(run_id)

    @app.post('/api/long-form/{run_id}/cancel',tags=['long-form'])
    def cancel(run_id:str,request:Request):
        get(run_id)
        try:return repo.cancel(run_id,actor(request))
        except WritingConflict as error:raise HTTPException(409,str(error)) from error

    @app.post('/api/long-form/{run_id}/decision',tags=['long-form'])
    async def decide(run_id:str,request:Request):
        get(run_id)
        try:
            decision=ScriptDecision.model_validate(await bounded_json(request))
            return repo.decide(run_id,decision.review_identity,decision.decision,actor(request))
        except WritingConflict as error:raise HTTPException(409,str(error)) from error
        except ValidationError:raise HTTPException(422,'Review the exact bundle and explicitly approve or reject it.') from None

    @app.post('/api/long-form/{run_id}/calls/{stage}/receipt',tags=['long-form'])
    def receipt(run_id:str,stage:Literal['research','draft','review','repair']):
        get(run_id);call=repo.stage_call(run_id,stage)
        if call is None:raise HTTPException(409,'This stage has no existing reserved call.')
        try:value=service.client.receipt(call['message'],'InspectLongFormCallV1')
        except (OSError,TimeoutError,RetryableProviderError):raise HTTPException(503,'Host receipt is unavailable. No model was launched; saved evidence is unchanged.') from None
        except ProviderValidationError:raise HTTPException(409,'Host could not confirm the exact saved receipt. No model was launched.') from None
        result=value.get('result') or {}
        return dict(call_id=value['call_id'],state=value['state'],invocation_started=value.get('invocation_started'),usage=result.get('usage'),notice='Read-only host inspection. This does not replay a call, replace saved evidence or approve a script.')

    @app.get('/api/long-form/{run_id}/export',tags=['long-form'])
    def export(run_id:str,review_identity:str):
        run=get(run_id)
        if run['draft'] is None or run['review_identity']!=review_identity:raise HTTPException(409,'Reload and export the exact current script review bundle.')
        data=json.dumps(dict(schema_version='lf2-review-v1',notice='Script review context; no rendered media or publishing approval.',preparation=run),ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str).encode()
        return Response(data,media_type='application/json',headers={'Content-Disposition':f'attachment; filename="long-form-{run_id}-{review_identity[:12]}.json"','ETag':'"'+hashlib.sha256(data).hexdigest()+'"'})
