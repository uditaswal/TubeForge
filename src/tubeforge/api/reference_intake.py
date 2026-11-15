"""Authenticated durable reference intake; HTTP handlers never fetch sources."""
import json

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typing import Literal

from tubeforge.domain.reference_video import ReferenceIntakeRequest
from tubeforge.db.reference_intake import IntakeConflict
from tubeforge.reference.service import parse_supplied_transcript
from tubeforge.reference.extractor import IntakeFailure


class RevisionRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_revision: int=Field(ge=1)
    action: Literal['refresh','transcript','cancel']
    transcript_text: str | None=Field(default=None,max_length=1_000_000)


async def bounded_json(request):
    payload=bytearray()
    async for chunk in request.stream():
        if len(payload)+len(chunk)>2_000_000:raise HTTPException(413,'Reference request exceeds 2 MB.')
        payload.extend(chunk)
    try:return json.loads(payload)
    except (ValueError,UnicodeError):raise HTTPException(422,'Reference request must be valid JSON.') from None


def register_reference_routes(app,runtime,settings):
    repo=runtime.reference_intakes.repository
    channels=list(settings.pipeline.codex.voice_profiles) or ['default']
    if 'default' not in channels:channels.insert(0,'default')

    def actor(request):
        session=runtime.auth.session(request.cookies.get('tubeforge_session'))
        return runtime.auth.username_for(session.user_id) if session else 'local-operator'

    def get(intake_id,revision=None):
        try:return repo.get(intake_id,revision)
        except KeyError:raise HTTPException(404,'Reference intake not found.') from None
        except ValueError:raise HTTPException(409,'Saved reference integrity failed; inspect Activity before using it.') from None

    @app.get('/references',response_class=HTMLResponse,include_in_schema=False)
    def page(request:Request):
        from tubeforge.api.reference_intake_ui import render_reference_html
        session=runtime.auth.session(request.cookies.get('tubeforge_session'))
        return render_reference_html(runtime.auth.username_for(session.user_id) if session else None)

    @app.get('/api/reference-intakes/options',tags=['references'])
    def options():return dict(channels=channels,target_durations=[30,60,90,600,720,900],maximum_transcript_bytes=1_000_000)

    @app.get('/api/reference-intakes',tags=['references'])
    def list_intakes():return dict(items=repo.list(),limit=50)

    @app.post('/api/reference-intakes',status_code=201,tags=['references'])
    async def create(request:Request):
        try:value=ReferenceIntakeRequest.model_validate(await bounded_json(request))
        except ValidationError:raise HTTPException(422,'Use a public YouTube link, a 25–90 second Short or 600–900 second long-form target, a valid language and bounded timestamped transcript.') from None
        if value.channel_identity not in channels:raise HTTPException(422,'Choose a configured channel identity.')
        return repo.create(value,actor(request))

    @app.get('/api/reference-intakes/{intake_id}',tags=['references'])
    def detail(intake_id:str,revision:int|None=None):return get(intake_id,revision)

    @app.post('/api/reference-intakes/{intake_id}/revisions',status_code=201,tags=['references'])
    async def revise(intake_id:str,request:Request):
        try:
            value=RevisionRequest.model_validate(await bounded_json(request))
            if value.action=='cancel':return repo.cancel(intake_id,value.expected_revision,actor(request))
            if value.action=='refresh':
                if value.transcript_text is not None:raise ValueError('Refresh cannot replace transcript text.')
                return repo.revise(intake_id,value.expected_revision,actor(request),refresh=True)
            if value.transcript_text is None:raise ValueError('Supply an SRT, VTT or JSON transcript.')
            cues=parse_supplied_transcript(value.transcript_text)
            return repo.revise(intake_id,value.expected_revision,actor(request),supplied_cues=cues)
        except KeyError:raise HTTPException(404,'Reference intake not found.') from None
        except IntakeConflict as error:raise HTTPException(409,str(error)) from error
        except (ValueError,IntakeFailure):raise HTTPException(422,'Transcript or revision request is invalid. Use ordered SRT/VTT cues inside the video duration, or reload a stale revision.') from None

    @app.get('/api/reference-intakes/{intake_id}/snapshot',tags=['references'])
    def snapshot(intake_id:str,revision:int|None=None):
        value=get(intake_id,revision)['intake']
        if value['snapshot'] is None:raise HTTPException(409,'No snapshot has been captured for this revision.')
        from tubeforge.domain.reference_video import ReferenceSnapshot
        data=ReferenceSnapshot.model_validate(value['snapshot']).model_dump_json()
        return Response(data,media_type='application/json',headers={'Content-Disposition':f'attachment; filename="reference-{value["intake_id"]}-r{value["revision"]}.json"'})
