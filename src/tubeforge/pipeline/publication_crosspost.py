"""Prepare one reviewed Day-review final for separate destination deliveries."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from sqlalchemy import select

from tubeforge.db.models import ArtifactRecord, SocialAccountRecord, TopicRecord
from tubeforge.domain.contracts import ContentPackage
from tubeforge.pipeline.publication_suggest import suggest


class DayReviewCrosspost:
    def __init__(self, sessions, reviews, assets, drafts):
        self.sessions, self.reviews, self.assets, self.drafts = sessions, reviews, assets, drafts

    def preview(self, short_id: str, reviewed_identity: str) -> dict[str, object]:
        with self.sessions() as session:
            topic = session.get(TopicRecord, 'batch-' + short_id)
            if topic is None:
                raise KeyError('short not found')
            snapshot = self.reviews._snapshot(session, topic)
            self._require_approved(snapshot, reviewed_identity)
            defaults = suggest(ContentPackage.model_validate(snapshot['script']))
            caption, hashtags = instagram_caption(str(defaults['description']))
            return {'source_review_identity': reviewed_identity, 'asset_sha256': snapshot['checksum'],
                    'youtube': {'title': defaults['title'], 'caption': defaults['description'], 'tags': defaults['tags'], 'visibility': 'private'},
                    'instagram': {'caption': caption, 'hashtags': hashtags}}

    @staticmethod
    def _require_approved(snapshot, reviewed_identity):
        if (not snapshot['available'] or not snapshot['qa_ok'] or snapshot['state'] not in {'approved', 'ready'}
                or snapshot['decision'] != 'approved' or snapshot['reviewed_identity'] != reviewed_identity):
            raise ValueError('the exact Day-review approval changed or is unavailable')

    def prepare(self, short_id: str, reviewed_identity: str, account_ids: list[str]):
        if not account_ids or len(account_ids) != len(set(account_ids)):
            raise ValueError('select distinct connected YouTube and Instagram accounts')
        with self.sessions() as session:
            topic = session.get(TopicRecord, 'batch-' + short_id)
            if topic is None:
                raise KeyError('short not found')
            snapshot = self.reviews._snapshot(session, topic)
            self._require_approved(snapshot, reviewed_identity)
            accounts = list(session.scalars(select(SocialAccountRecord).where(SocialAccountRecord.id.in_(account_ids))))
            if len(accounts) != len(account_ids) or {a.platform for a in accounts} != {'youtube', 'instagram'}:
                raise ValueError('select connected YouTube and Instagram accounts')
            if any(a.disabled or a.status != 'connected' or not a.external_account_id or not a.credential_ciphertext or not a.last_validated_at for a in accounts):
                raise ValueError('selected account needs reconnection')
            package = ContentPackage.model_validate(snapshot['script'])
            defaults = suggest(package)
            checksums = dict(snapshot['reviewed_checksums'])
            job_id = snapshot['job_id']
            thumbnail_record = session.scalar(select(ArtifactRecord).where(ArtifactRecord.job_id == job_id, ArtifactRecord.name == 'thumbnail'))
            thumbnail_path = Path(thumbnail_record.path) if thumbnail_record else None
            platforms = {a.id: a.platform for a in accounts}
        asset = self.assets.register_final(job_id)
        if asset.sha256 != checksums.get('final'):
            raise ValueError('final video changed since Day review')
        thumbnail_sha = checksums.get('thumbnail')
        if thumbnail_sha:
            if thumbnail_path is None:
                raise ValueError('reviewed thumbnail is unavailable')
            self._stage_thumbnail(thumbnail_path, thumbnail_sha)
        caption, hashtags = instagram_caption(str(defaults['description']))
        destination_metadata = {}
        for account_id in account_ids:
            if platforms[account_id] == 'youtube':
                destination_metadata[account_id] = {'title': defaults['title'], 'caption': defaults['description'], 'tags': defaults['tags'], 'visibility': 'private'}
                if thumbnail_sha:
                    destination_metadata[account_id]['thumbnail_sha256'] = thumbnail_sha
            else:
                destination_metadata[account_id] = {'caption': caption, 'hashtags': hashtags}
        post = self.drafts.create_draft(asset.id, destination_metadata, source_review_identity=reviewed_identity)
        return post


    def _stage_thumbnail(self, source: Path, digest: str) -> None:
        root = self.reviews.exports.artifact_root
        if (source.is_symlink() or not source.resolve(strict=True).is_relative_to(root)
                or not source.is_file() or source.stat().st_size > 2_000_000):
            raise ValueError('reviewed thumbnail is unavailable')
        content = source.read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError('reviewed thumbnail changed')
        directory = self.assets.stage_root / 'thumbnails'
        if directory.is_symlink():
            raise ValueError('thumbnail staging must not be a symlink')
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f'{digest}.jpg'
        if target.is_symlink():
            raise ValueError('staged thumbnail must not be a symlink')
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise ValueError('staged thumbnail does not match its checksum')
            return
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(prefix='.thumbnail-', dir=directory, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)



def instagram_caption(description: str) -> tuple[str, list[str]]:
    """Keep the suggested caption within Instagram's text and hashtag limits."""
    text = description[:2200].strip()
    used = []
    def keep(match):
        tag = match.group(0)
        used.append(tag)
        return tag if len(used) <= 30 else ''
    text = re.sub(r'(?<!\w)#[\w]+', keep, text).strip()
    return text, list(dict.fromkeys(used[:30]))
