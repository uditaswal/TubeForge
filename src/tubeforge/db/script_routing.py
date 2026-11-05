"""Audited defaults for future jobs. Existing requests are never rewritten."""
from datetime import UTC, datetime
from sqlalchemy import select, text
from tubeforge.db.models import ScriptRoutingPolicyRecord


class ScriptRoutingRepository:
    def __init__(self, sessions, *, claude_enabled):
        self.sessions, self.claude_enabled = sessions, claude_enabled

    def _latest(self, session):
        return session.scalar(select(ScriptRoutingPolicyRecord).order_by(ScriptRoutingPolicyRecord.id.desc()).limit(1))

    def get(self):
        with self.sessions() as session:
            row = self._latest(session)
            return {'revision': row.id if row else 0, 'mode': row.mode if row else None,
                    'preferred_model': row.preferred_model if row else ('sonnet-medium' if self.claude_enabled else 'gpt-sol'),
                    'actor': row.actor if row else None, 'saved_at': row.created_at.isoformat() if row else None,
                    'modes': [{'id': mode, 'enabled': mode == 'codex_only' or self.claude_enabled}
                              for mode in ['claude_only', 'codex_only', 'automatic']]}

    def save(self, *, mode, preferred_model, expected_revision, actor):
        if mode not in {'claude_only', 'codex_only', 'automatic'}:
            raise ValueError('unknown routing mode')
        if mode != 'codex_only' and not self.claude_enabled:
            raise ValueError('this mode requires Claude to be enabled')
        if preferred_model not in {'gpt-sol', 'sonnet-medium', 'opus'} or (mode == 'codex_only' and preferred_model != 'gpt-sol') or (mode == 'claude_only' and preferred_model == 'gpt-sol'):
            raise ValueError('choose a preferred writer available in this mode')
        with self.sessions() as session:
            session.execute(text('BEGIN IMMEDIATE'))
            previous = self._latest(session)
            if expected_revision != (previous.id if previous else 0):
                raise ValueError('routing policy changed; reload before saving')
            session.add(ScriptRoutingPolicyRecord(mode=mode, preferred_model=preferred_model, actor=actor, created_at=datetime.now(UTC)))
            session.commit()
        return self.get()

    def apply(self, request, *, enforce_current=False, preferred_model=None):
        policy = self.get()
        mode = request.script_routing_mode
        if enforce_current and mode and policy['mode'] and mode != policy['mode']:
            raise ValueError('routing mode differs from the saved Studio policy; reload the form')
        # Revision/retry children already carry the immutable original policy.
        if mode is not None:
            return request
        if policy['mode'] is None or request.production_mode == 'source_clip':
            return request
        if policy['mode'] != 'codex_only' and not self.claude_enabled:
            raise ValueError('saved routing policy requires Claude; choose Codex only in Studio')
        model = preferred_model or policy['preferred_model']
        if policy['mode'] == 'codex_only' and model != 'gpt-sol' or policy['mode'] == 'claude_only' and model == 'gpt-sol':
            raise ValueError('selected writer is disabled by the saved routing policy; reload the form')
        owner = 'codex' if model == 'gpt-sol' else 'claude'
        return request.model_copy(update={'script_routing_mode': policy['mode'], 'script_owner': owner,
                                          'script_model': None if owner == 'codex' else model})
