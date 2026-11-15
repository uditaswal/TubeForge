"""Authenticated scheduling controls for already reviewed publishing drafts."""
from datetime import date, datetime
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from tubeforge.pipeline.publication_schedule import CadenceConfirmationRequired, default_slots


class ScheduleDraftRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reviewed_identity: str = Field(pattern=r'^[0-9a-f]{64}$')
    scheduled_for: datetime
    cadence_override: bool = False
    confirmed_public_accounts: list[str] = Field(default_factory=list, max_length=20)
    allow_future_public_youtube: bool = False


class PendingActionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['pause', 'resume', 'cancel']


def register_publishing_schedule_routes(app, runtime, presence, drafts, queue):
    @app.get('/api/publishing/slots', tags=['publishing'])
    def slots(day: date):
        return {'timezone': 'Asia/Kolkata', 'slots': [value.isoformat() for value in default_slots(day)]}

    @app.post('/api/publishing/drafts/{post_id}/schedule', tags=['publishing'])
    def schedule(post_id: str, value: ScheduleDraftRequest, request: Request):
        login = runtime.auth.session(request.cookies.get('tubeforge_session'))
        if login is None:
            raise HTTPException(401, detail='Studio sign-in is required')
        supported = presence.live_platforms() if runtime.token_cipher else set()
        if not supported:
            raise HTTPException(503, detail='publisher worker is unavailable')
        if len(set(value.confirmed_public_accounts)) != len(value.confirmed_public_accounts):
            raise HTTPException(422, detail='public confirmation accounts must be distinct')
        try:
            post = drafts.submit(post_id, reviewed_identity=value.reviewed_identity, actor=login.user_id,
                supported_platforms=supported, confirmed_public_accounts=frozenset(value.confirmed_public_accounts),
                scheduled_for=value.scheduled_for, cadence_override=value.cadence_override,
                safety_config=app.state.settings.channel_safety,
                youtube_api_audited=app.state.settings.pipeline.youtube.youtube_api_audited,
                allow_future_public_youtube=value.allow_future_public_youtube)
        except CadenceConfirmationRequired as error:
            raise HTTPException(409, detail={'message': str(error), 'warnings': error.warnings}) from error
        except KeyError as error:
            raise HTTPException(404, detail='publishing draft not found') from error
        except ValueError as error:
            raise HTTPException(409, detail=str(error)) from error
        return {'id': post.id, 'state': post.state, 'scheduled_for': post.scheduled_at.isoformat(),
                'destinations': [{'id': item.id, 'account_id': item.account_id, 'state': item.state} for item in drafts.deliveries(post.id)]}

    @app.post('/api/publishing/deliveries/{delivery_id}/pending-action', tags=['publishing'])
    def pending_action(delivery_id: str, value: PendingActionRequest, request: Request):
        login = runtime.auth.session(request.cookies.get('tubeforge_session'))
        if login is None:
            raise HTTPException(401, detail='Studio sign-in is required')
        try:
            result = queue.pending_action(delivery_id, value.action, login.user_id)
        except KeyError as error:
            raise HTTPException(404, detail='publishing delivery not found') from error
        except ValueError as error:
            raise HTTPException(409, detail=str(error)) from error
        return {'delivery_id': delivery_id, 'state': result}
