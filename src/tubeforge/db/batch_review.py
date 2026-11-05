"""Local day review. Decisions never authorize publication or reset allowances."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, text
from tubeforge.db.models import ArtifactRecord, JobEventRecord, PipelineJobRecord, TopicRecord
from tubeforge.db.repositories import JobRepository
from tubeforge.domain.contracts import ContentRequest
from tubeforge.domain.states import JobState


def file_checksum(path: str) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


class BatchReviewRepository:
    def __init__(self, sessions, artifact_root=None, music_catalog=None):
        self.sessions = sessions
        self.music_catalog = music_catalog
        from tubeforge.pipeline.publication_batch_export import BatchExportStore
        self.exports = BatchExportStore(artifact_root or Path('data/artifacts'))

    def _snapshot(self, session, topic):
        options = json.loads(topic.options_json)
        job = session.get(PipelineJobRecord, topic.generation_job_id) if topic.generation_job_id else None
        artifacts = list(session.scalars(select(ArtifactRecord).where(ArtifactRecord.job_id == topic.generation_job_id))) if job else []
        final = next((a for a in artifacts if a.name == 'final'), None)
        script = next((a for a in artifacts if a.name == 'content_package'), None)
        thumbnail = next((a for a in artifacts if a.name == 'thumbnail'), None)
        available = bool(job and job.state == JobState.FINAL_READY.value and job.claim_owner is None and final and script)
        checksums = {}
        error = None
        for name, artifact in [('final', final), ('script', script), ('thumbnail', thumbnail)]:
            if artifact:
                try:
                    checksum = file_checksum(artifact.path)
                    if checksum != artifact.checksum_sha256:
                        raise ValueError(f'{name} checksum changed')
                    checksums[name] = checksum
                except (OSError, ValueError) as failure:
                    available, error = False, str(failure)
        identity = hashlib.sha256(json.dumps({'job_id': topic.generation_job_id, 'artifacts': checksums, 'brief': options['batch_plan']}, sort_keys=True).encode()).hexdigest() if available else None
        package = None
        if script and 'script' in checksums:
            try:
                if Path(script.path).stat().st_size <= 2_000_000:
                    package = json.loads(Path(script.path).read_text(encoding='utf-8'))
            except (OSError, ValueError):
                pass
        from tubeforge.pipeline.channel_safety import disclosure_record, read_audio
        audio = read_audio(final.path, self.music_catalog) if final else {}
        disclosure = disclosure_record(package or {}, audio, job_id=topic.generation_job_id, final_checksum=checksums.get('final'))
        if identity:
            identity = hashlib.sha256((identity + disclosure['evidence_identity']).encode()).hexdigest()
        saved_disclosure = options.get('batch_disclosure', {})
        if saved_disclosure.get('evidence_identity') == disclosure['evidence_identity'] and saved_disclosure.get('reviewed_identity') == identity:
            disclosure = saved_disclosure
        review = options.get('batch_review', {})
        current = review.get('identity') == identity and identity is not None
        state = review.get('state', 'needs_review') if current else 'needs_review'
        qa = options.get('batch_qa')
        qa_ok = bool(qa and qa.get('exit_code') == 0 and qa.get('artifact_checksum') == checksums.get('final') and 'final' in checksums)
        export = options.get('batch_export')
        export_ok = bool(current and state == 'ready' and qa_ok and self.exports.valid(export, identity))
        if export and not export_ok:
            self.exports.invalidate(export)
        if state == 'ready' and not export_ok:
            state = 'needs_review'
            current = False
        layout_family = None
        render_qa = next((a for a in artifacts if a.name == 'final_qa'), None)
        if render_qa:
            try:
                if Path(render_qa.path).stat().st_size <= 2_000_000 and file_checksum(render_qa.path) == render_qa.checksum_sha256:
                    layout_family = json.loads(Path(render_qa.path).read_text()).get('layout_family')
            except (OSError, ValueError):
                pass
        request = json.loads(job.request_json) if job else {}
        return {'created_at': topic.created_at.replace(tzinfo=UTC).isoformat(), 'layout_family': layout_family, 'music': next((entry.get('source_sha256') or entry.get('mode') for entry in audio.get('audio_licenses', []) if entry.get('asset') == 'music'), None), 'voice': request.get('voice_id'), 'disclosure': disclosure, 'id': options['batch_plan']['id'], 'short': options['batch_plan'], 'job_id': topic.generation_job_id,
                'production_state': job.state if job else 'not_started', 'state': state,
                'decision': review.get('decision') if current else None, 'reviewed_identity': identity,
                'checksum': checksums.get('final'), 'reviewed_checksums': checksums, 'export_url': f'/api/batch-plans/{options["batch_plan"]["id"]}/export' if export_ok else None, 'available': available, 'error': error,
                'qa': qa, 'qa_ok': qa_ok, 'script': package, 'thumbnail_result': options.get('batch_thumbnail'),
                'preview_url': f'/api/jobs/{job.id}/artifacts/final' if available else None,
                'thumbnail_url': f'/api/jobs/{job.id}/artifacts/thumbnail' if thumbnail and 'thumbnail' in checksums else None}

    def list_day(self, day=None):
        with self.sessions() as session:
            session.execute(text('BEGIN IMMEDIATE'))
            rows = session.scalars(select(TopicRecord).where(TopicRecord.id.like('batch-%')).order_by(TopicRecord.created_at, TopicRecord.id))
            items = []
            for row in rows:
                options = json.loads(row.options_json)
                plan = options.get('batch_plan')
                if not plan or options.get('batch_history'):
                    continue
                if day and (plan.get('publish_at') or '')[:10] != day:
                    continue
                items.append(self._snapshot(session, row))
            return items

    def decide(self, short_id, action, identity, actor, disclosure_required=None):
        with self.sessions() as session:
            session.execute(text('BEGIN IMMEDIATE'))
            row = session.get(TopicRecord, 'batch-' + short_id)
            if row is None:
                raise KeyError('short not found')
            options = json.loads(row.options_json)
            previous = options.get('batch_regeneration', {})
            if action == 'regenerate' and previous.get('identity') == identity:
                return {'id': short_id, 'state': 'needs_review', 'job_id': row.generation_job_id, 'action': 'skipped'}
            current = self._snapshot(session, row)
            if not current['available'] or current['reviewed_identity'] != identity:
                raise ValueError('reviewed artifact changed or is unavailable; reload review')
            job = session.get(PipelineJobRecord, row.generation_job_id)
            if action in {'approve', 'ready'} and not current['qa_ok']:
                raise ValueError('QA must pass for the exact reviewed final artifact')
            if action == 'ready' and current['state'] not in {'approved', 'ready'}:
                raise ValueError('approve this exact artifact before staging')
            previous_export = options.get('batch_export')
            if action != 'ready':
                options.pop('batch_export', None)
            if action == 'approve':
                record = current['disclosure']
                if not record['eligible']:
                    raise ValueError('disclosure evidence incomplete or originality check failed: ' + ', '.join(record['missing'] + record['originality']['problems']))
                if type(disclosure_required) is not bool:
                    raise ValueError('choose whether platform AI disclosure is required for this exact video')
                options['batch_disclosure'] = {**record, 'platform_disclosure_required': disclosure_required, 'reviewed_identity': identity, 'actor': actor}
                state, decision = 'approved', 'approved'
            elif action == 'ready':
                if not current['disclosure']['eligible'] or type(current['disclosure']['platform_disclosure_required']) is not bool:
                    raise ValueError('disclosure evidence changed; approve this video again')
                if not current['thumbnail_url']:
                    raise ValueError('thumbnail unavailable; export cannot be staged')
                artifacts = list(session.scalars(select(ArtifactRecord).where(ArtifactRecord.job_id == job.id)))
                final = next(a for a in artifacts if a.name == 'final')
                thumbnail = next(a for a in artifacts if a.name == 'thumbnail')
                plan = options['batch_plan']
                copy = (options.get('batch_thumbnail') or {}).get('text') or (plan.get('thumbnail') or {}).get('text') or next(iter((current.get('script') or {}).get('thumbnail_brief', {}).get('text_options', [])), '')
                options['batch_export'] = self.exports.prepare(plan_id=options.get('batch_plan_id', 'default'), short=plan,
                    package=current['script'], qa=current['qa'], disclosure=current['disclosure'], reviewed_identity=identity, reviewed_checksums=current['reviewed_checksums'],
                    final=final.path, thumbnail=thumbnail.path, thumbnail_text=copy, script=next(a.path for a in artifacts if a.name == 'content_package'))
                state, decision = 'ready', 'approved'
            elif action == 'reject':
                state, decision = 'needs_review', 'rejected'
            elif action == 'regenerate':
                from tubeforge.db.batch_automation import is_held
                if is_held(session):
                    raise ValueError('batch production is on hold')
                # Archive the old association so it can never become a publishable
                # ordinary FINAL_READY job when the current topic points to a child.
                archive = TopicRecord(id='batch-history-' + uuid4().hex, title=row.title, notes=row.notes,
                    status='generating', priority=0, options_json=json.dumps({**options, 'batch_history': True}),
                    generation_job_id=job.id, attempts=row.attempts, created_at=row.created_at, updated_at=datetime.now(UTC))
                session.add(archive)
                request = ContentRequest.model_validate_json(job.request_json).model_copy(update={'review_mode': 'manual'})
                child = JobRepository(self.sessions).create(uuid4().hex, request, transaction=session)
                row.generation_job_id = child.id
                options.pop('batch_qa', None)
                options.pop('batch_thumbnail', None)
                options['batch_regeneration'] = {'identity': identity, 'source_job_id': job.id}
                state, decision = 'needs_review', 'regenerated'
            else:
                raise ValueError('unknown review action')
            options['batch_review'] = {'state': state, 'decision': decision, 'identity': identity if action != 'regenerate' else None,
                                       'checksum': current['checksum'], 'actor': actor, 'at': datetime.now(UTC).isoformat()}
            row.options_json = json.dumps(options, sort_keys=True)
            row.updated_at = datetime.now(UTC)
            session.add(JobEventRecord(job_id=job.id, event_type='batch_review_' + action,
                details_json=json.dumps({'short_id': short_id, 'actor': actor, 'reviewed_identity': identity, 'checksum': current['checksum'], 'state': state, 'new_job_id': row.generation_job_id if action == 'regenerate' else None}), created_at=datetime.now(UTC)))
            session.commit()
            if action != 'ready':
                self.exports.invalidate(previous_export)
            return {'id': short_id, 'state': state, 'decision': decision, 'job_id': row.generation_job_id}

    def export_file(self, short_id, name):
        if name not in {'final.mp4', 'thumbnail.jpg', 'package.json'}:
            raise KeyError('export file not found')
        with self.sessions() as session:
            session.execute(text('BEGIN IMMEDIATE'))
            row = session.get(TopicRecord, 'batch-' + short_id)
            if row is None:
                raise KeyError('short not found')
            current = self._snapshot(session, row)
            if current['state'] != 'ready' or not current['export_url']:
                raise ValueError('export is unavailable or invalidated; review and stage again')
            info = json.loads(row.options_json)['batch_export']
            return Path(info['version']) / name
