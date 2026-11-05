"""Atomic local handoff folders. No platform API, scheduling, or upload behavior."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo


def checksum(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


class BatchExportStore:
    def __init__(self, artifact_root):
        self.artifact_root = Path(artifact_root).resolve()
        self.root = self.artifact_root.parent / 'publishing' / 'staging' / 'batch'

    def _safe_root(self):
        for path in [self.root.parent.parent, self.root.parent, self.root, self.root / '.versions']:
            if path.is_symlink():
                raise ValueError('export root must not be a symlink')

    def prepare(self, *, plan_id, short, package, qa, reviewed_identity, reviewed_checksums, final, thumbnail, thumbnail_text, script=None, disclosure=None):
        self._safe_root()
        if not disclosure or not disclosure.get('eligible') or type(disclosure.get('platform_disclosure_required')) is not bool:
            raise ValueError('reviewed disclosure evidence is required')
        if disclosure.get('reviewed_identity') != reviewed_identity or disclosure.get('final_checksum') != reviewed_checksums['final']:
            raise ValueError('disclosure does not match the reviewed artifact')
        for value in [plan_id, short['id']]:
            if not re.fullmatch(r'[a-z0-9-]{1,120}', value):
                raise ValueError('invalid export plan or short id')
        for source in [final, thumbnail] + ([script] if script else []):
            if not Path(source).resolve(strict=True).is_relative_to(self.artifact_root):
                raise ValueError('export source is outside the registered artifact root')
        date = (short.get('publish_at') or datetime.now(ZoneInfo('Asia/Kolkata')).isoformat())[:10]
        metadata = (package or {}).get('metadata', {})
        manifest = {
            'title': short['title'], 'description': metadata.get('description') or short['concept'],
            'tags': short.get('tags') or metadata.get('tags', []), 'thumbnail_text': thumbnail_text,
            'plan_id': plan_id, 'short_id': short['id'], 'date': date,
            'publish_at': short.get('publish_at'), 'source_urls': sorted({s['url'] for s in disclosure['sources']}),
            'disclosure': disclosure, 'originality_report': disclosure['originality'],
            'qa': qa, 'reviewed_identity': reviewed_identity, 'reviewed_checksums': reviewed_checksums,
            'files': {'final.mp4': reviewed_checksums['final'], 'thumbnail.jpg': reviewed_checksums['thumbnail']},
            'state': 'ready', 'meaning': 'local staged export; no publication authorized',
        }
        encoded = (json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2) + '\n').encode()
        export_id = hashlib.sha256(encoded).hexdigest()
        folder = self.root / plan_id / date
        version_parent = self.root / '.versions' / plan_id / date / short['id']
        version = version_parent / export_id
        folder.mkdir(parents=True, exist_ok=True)
        version_parent.mkdir(parents=True, exist_ok=True)
        if not folder.resolve().is_relative_to(self.root.resolve()) or not version_parent.resolve().is_relative_to((self.root / '.versions').resolve()):
            raise ValueError('export folder escapes staging root')
        pointer = folder / short['id']
        if pointer.exists() and not pointer.is_symlink():
            raise ValueError('export target is not an owned atomic pointer')
        info = {'path': str(pointer), 'version': str(version), 'manifest_checksum': export_id, 'reviewed_identity': reviewed_identity}
        if version.exists() and not self._valid_version(info):
            version = version_parent / (export_id + '-' + uuid4().hex)
            info['version'] = str(version)
        if not version.exists():
            temporary = Path(tempfile.mkdtemp(prefix='.prepare-', dir=version_parent))
            try:
                for source, name in [(final, 'final.mp4'), (thumbnail, 'thumbnail.jpg')]:
                    expected = manifest['files'][name]
                    if checksum(source) != expected:
                        raise ValueError('reviewed source changed before export')
                    shutil.copy2(source, temporary / name)
                    if checksum(temporary / name) != expected or checksum(source) != expected:
                        raise ValueError('reviewed source changed during export')
                (temporary / 'package.json').write_bytes(encoded)
                for name in ['final.mp4', 'thumbnail.jpg', 'package.json']:
                    with (temporary / name).open('rb') as stream:
                        os.fsync(stream.fileno())
                descriptor = os.open(temporary, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                os.replace(temporary, version)
                descriptor = os.open(version_parent, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
        for name, source in [('final', final), ('thumbnail', thumbnail)] + ([('script', script)] if script else []):
            if checksum(source) != reviewed_checksums[name]:
                raise ValueError('reviewed artifact changed before export promotion')
        if pointer.is_symlink() and pointer.resolve() == version:
            return info
        link = folder / ('.' + short['id'] + '-' + uuid4().hex)
        try:
            link.symlink_to(os.path.relpath(version, folder), target_is_directory=True)
            os.replace(link, pointer)
            descriptor = os.open(folder, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            link.unlink(missing_ok=True)
        return info

    def _valid_version(self, info):
        try:
            self._safe_root()
            version = Path(info['version'])
            if not version.resolve().is_relative_to((self.root / '.versions').resolve()) or version.is_symlink():
                return False
            manifest_path = version / 'package.json'
            if checksum(manifest_path) != info['manifest_checksum']:
                return False
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            if manifest['reviewed_identity'] != info['reviewed_identity']:
                return False
            return all(not (version / name).is_symlink() and checksum(version / name) == expected for name, expected in manifest['files'].items())
        except (OSError, ValueError, KeyError):
            return False

    def valid(self, info, identity):
        if not info or info.get('reviewed_identity') != identity:
            return False
        pointer = Path(info['path'])
        return pointer.is_symlink() and pointer.resolve() == Path(info['version']) and self._valid_version(info)

    def invalidate(self, info):
        if not info:
            return
        pointer = Path(info['path'])
        # Remove only this version's owned pointer, never another export or data.
        if pointer.parent.resolve().is_relative_to(self.root.resolve()) and pointer.is_symlink() and pointer.resolve() == Path(info['version']):
            pointer.unlink(missing_ok=True)
