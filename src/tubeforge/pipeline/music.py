"""Durable operator-approved music catalog and rights records."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tubeforge.core.config import MusicTrackConfig
from tubeforge.core.errors import ProviderValidationError


GENERIC_LICENSE_LABELS = {"free", "royalty free", "royalty-free", "unknown", "n/a"}
ALLOWED_AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}


class MusicTrackRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1, max_length=200)
    path: str = Field(min_length=1, max_length=4096)
    checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_url: str = Field(min_length=1, max_length=2000)
    license_name: str = Field(min_length=1, max_length=300)
    license_url: str = Field(min_length=1, max_length=2000)
    attribution_required: bool = False
    attribution: str = Field(default="", max_length=1000)
    publishing_allowed: bool = True
    duration_seconds: float = Field(gt=0, le=86_400)

    @model_validator(mode="after")
    def require_real_publishable_terms(self) -> "MusicTrackRecord":
        if self.license_name.strip().casefold() in GENERIC_LICENSE_LABELS:
            raise ValueError("music requires the actual licence name, not a generic royalty-free label")
        if not self.publishing_allowed:
            raise ValueError("music licence must permit the intended publishing use")
        if self.attribution_required and not self.attribution.strip():
            raise ValueError("attribution-required music needs attribution text")
        for field in (self.source_url, self.license_url):
            parsed = urlparse(field)
            if parsed.scheme != "https" or not parsed.hostname:
                raise ValueError("music source and licence URLs must be absolute HTTPS URLs")
        return self


class MusicCatalog:
    """Read configured tracks and atomically persist dashboard uploads."""

    def __init__(self, root: Path, configured: Iterable[MusicTrackConfig] = (), *, ffprobe: str = "ffprobe", max_bytes: int = 50_000_000) -> None:
        self.root, self.index_path = root, root / "catalog.json"
        self.configured = tuple(configured)
        self.ffprobe, self.max_bytes = ffprobe, max_bytes

    def list(self) -> tuple[MusicTrackRecord, ...]:
        records: dict[str, MusicTrackRecord] = {}
        for track in self.configured:
            if track.path is None:
                continue
            path = Path(track.path)
            if path.is_file():
                records[track.name] = self._record_from_config(track, path)
        for value in self._read_index():
            try:
                record = MusicTrackRecord.model_validate(value)
            except ValueError:
                continue
            if Path(record.path).is_file() and _checksum(Path(record.path)) == record.checksum_sha256:
                records[record.name] = record
        return tuple(records[name] for name in sorted(records, key=str.casefold))

    def names(self) -> set[str]:
        return {track.name for track in self.list()}

    def resolve(self, name: str) -> MusicTrackRecord:
        record = next((track for track in self.list() if track.name == name), None)
        if record is None:
            raise ProviderValidationError(f"approved music track is unavailable: {name}")
        return record

    def upload(self, *, name: str, filename: str, payload: bytes, source_url: str, license_name: str, license_url: str, attribution_required: bool, attribution: str, publishing_allowed: bool) -> MusicTrackRecord:
        name = name.strip()
        if not name or len(name) > 200 or not re.fullmatch(r"[\w .()&+-]+", name, flags=re.UNICODE):
            raise ProviderValidationError("music name contains unsupported characters")
        suffix = Path(filename).suffix.casefold()
        if suffix not in ALLOWED_AUDIO_SUFFIXES:
            raise ProviderValidationError("music file type is not supported")
        if not payload or len(payload) > self.max_bytes:
            raise ProviderValidationError("music upload is empty or exceeds the 50 MB limit")
        self.root.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(payload).hexdigest()
        destination = self.root / f"{digest}{suffix}"
        fd, temporary_name = tempfile.mkstemp(prefix="music-", suffix=suffix, dir=self.root)
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            temporary.write_bytes(payload)
            duration = _probe_audio(temporary, self.ffprobe)
            record = MusicTrackRecord(
                name=name,
                path=str(destination),
                checksum_sha256=digest,
                source_url=source_url,
                license_name=license_name.strip(),
                license_url=license_url,
                attribution_required=attribution_required,
                attribution=attribution.strip(),
                publishing_allowed=publishing_allowed,
                duration_seconds=duration,
            )
            temporary.replace(destination)
        except ValueError as error:
            raise ProviderValidationError(str(error)) from error
        finally:
            temporary.unlink(missing_ok=True)
        values = [item.model_dump(mode="json") for item in self.list() if item.name != name]
        values.append(record.model_dump(mode="json"))
        _atomic_json(self.index_path, values)
        return record

    def _record_from_config(self, track: MusicTrackConfig, path: Path) -> MusicTrackRecord:
        return MusicTrackRecord(
            name=track.name,
            path=str(path),
            checksum_sha256=_checksum(path),
            source_url=track.source_url,
            license_name=track.license_name,
            license_url=track.license_url,
            attribution_required=track.attribution_required,
            attribution=track.attribution,
            publishing_allowed=track.publishing_allowed,
            duration_seconds=_probe_audio(path, self.ffprobe),
        )

    def _read_index(self) -> list[object]:
        try:
            value = json.loads(self.index_path.read_text(encoding="utf-8"))
            return value if isinstance(value, list) else []
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return []


def _probe_audio(path: Path, executable: str) -> float:
    try:
        result = subprocess.run(
            [executable, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type:format=duration", "-of", "json", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ProviderValidationError("music audio inspection is unavailable") from error
    try:
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
        streams = data["streams"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ProviderValidationError("uploaded music is not a decodable audio file") from error
    if result.returncode or duration <= 0 or not isinstance(streams, list) or not any(item.get("codec_type") == "audio" for item in streams):
        raise ProviderValidationError("uploaded music is not a decodable audio file")
    return duration


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


__all__ = ["MusicCatalog", "MusicTrackRecord"]
