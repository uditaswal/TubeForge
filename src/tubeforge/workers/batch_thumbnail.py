"""Best-effort local portrait thumbnail, under the existing worker fence."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, text
from tubeforge.db.models import ArtifactRecord, PipelineJobRecord, TopicRecord
from tubeforge.db.batch_review import file_checksum
from tubeforge.domain.states import JobState
from tubeforge.pipeline import thumbnail


def ensure_thumbnail(sessions, job_id, artifact_root, owner, guard):
    if not guard.check(force=True):
        return
    pending = None
    outcome = None
    with sessions() as session:
        topic = session.scalar(select(TopicRecord).where(TopicRecord.generation_job_id == job_id))
        if topic is None:
            return
        options = json.loads(topic.options_json)
        if options.get('batch_history') or 'batch_plan' not in options:
            return
        # A durable result, including an unavailable reason, prevents retry loops.
        if options.get('batch_thumbnail'):
            return
        package = session.scalar(select(ArtifactRecord).where(ArtifactRecord.job_id == job_id, ArtifactRecord.name == 'content_package'))
        existing = session.scalar(select(ArtifactRecord).where(ArtifactRecord.job_id == job_id, ArtifactRecord.name == 'thumbnail'))
    try:
        plan = options['batch_plan']
        copy = (plan.get('thumbnail') or {}).get('text', '').strip()
        if not copy:
            if package is None or file_checksum(package.path) != package.checksum_sha256:
                raise ValueError('generated package unavailable or changed')
            value = json.loads(Path(package.path).read_text(encoding='utf-8'))
            copy = next((text.strip() for text in value.get('thumbnail_brief', {}).get('text_options', []) if text.strip()), '')
        if not copy:
            raise ValueError('no thumbnail text in plan or generated package')
        if existing is not None and file_checksum(existing.path) == existing.checksum_sha256:
            outcome = {'status': 'available', 'text': copy, 'checksum': existing.checksum_sha256, 'path': existing.path}
        else:
            if artifact_root is None:
                raise ValueError('artifact root unavailable')
            folder = Path(artifact_root) / job_id
            folder.mkdir(parents=True, exist_ok=True)
            identity = hashlib.sha256(json.dumps({'text': copy, 'version': 'batch-portrait-v1'}, sort_keys=True).encode()).hexdigest()
            target = folder / f'batch-thumbnail-{identity[:24]}.jpg'
            fd, scratch = tempfile.mkstemp(prefix='.thumbnail-', suffix='.jpg', dir=folder)
            os.close(fd)
            pending = Path(scratch)
            image, _ = thumbnail.compose_portrait(None, copy)
            if image.size != (1080, 1920):
                raise ValueError('thumbnail must be 1080x1920')
            checksum = thumbnail.save(image, pending)
            if not guard.check(force=True):
                return
            os.replace(pending, target)
            outcome = {'status': 'available', 'text': copy, 'checksum': checksum, 'path': str(target), 'visual_hint': 'advisory only'}
    except Exception as failure:
        outcome = {'status': 'unavailable', 'reason': f'thumbnail unavailable: {failure}'}
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)
    if not guard.check(force=True):
        return
    with sessions() as session:
        session.execute(text('BEGIN IMMEDIATE'))
        job = session.get(PipelineJobRecord, job_id)
        if job is None or job.claim_owner != owner:
            return
        row = session.scalar(select(TopicRecord).where(TopicRecord.generation_job_id == job_id))
        values = json.loads(row.options_json)
        values['batch_thumbnail'] = outcome
        row.options_json = json.dumps(values, sort_keys=True)
        if outcome['status'] == 'available':
            registered = session.scalar(select(ArtifactRecord).where(ArtifactRecord.job_id == job_id, ArtifactRecord.name == 'thumbnail'))
            if registered is not None:
                registered.path, registered.checksum_sha256 = outcome['path'], outcome['checksum']
            else:
                session.add(ArtifactRecord(job_id=job_id, stage=JobState.FINAL_READY.value, name='thumbnail', path=outcome['path'], checksum_sha256=outcome['checksum'], provenance_json=json.dumps({'kind': 'batch-portrait-v1', 'text': outcome['text']}), created_at=datetime.now(UTC)))
        session.commit()
