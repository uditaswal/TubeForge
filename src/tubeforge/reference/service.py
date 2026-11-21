"""Durable reference work, driven by the existing worker process."""
from __future__ import annotations

import json
import re

from tubeforge.domain.reference_video import ReferenceSnapshot, TranscriptCue
from tubeforge.reference.extractor import IntakeFailure, YoutubeReferenceExtractor, check_reference_text


def is_plain_transcript(value: str) -> bool:
    """True for ordinary text: no JSON cue list and no SRT/VTT timing lines."""
    stripped = value.lstrip().lstrip('\ufeff').lstrip()
    return bool(stripped) and not stripped.startswith('[') and '-->' not in value


def parse_plain_transcript(value: str, duration_seconds: float):
    """Turn an ordinary transcript into cues spread over the video's length, in proportion to the words spoken.

    The timings are an estimate (a person pasting text has none), so they place each passage roughly, not exactly.
    Short lines are grouped into cues of about 20 words so the text stays readable.
    """
    import math
    text = re.sub(r'\[\s*\d{1,2}:\d{2}(?::\d{2})?\s*\]|\b\d{1,2}:\d{2}(?::\d{2})?\b(?=\s)', ' ', value.replace('\r\n', '\n').replace('\r', '\n').lstrip('\ufeff'))
    pieces = [piece.strip() for piece in re.split(r'(?<=[.!?])\s+|\n+', text) if piece.strip()]
    chunks, current = [], []
    for piece in pieces:
        current.append(piece)
        if sum(len(item.split()) for item in current) >= 20:
            chunks.append(' '.join(current)); current = []
    if current:
        chunks.append(' '.join(current))
    chunks = [chunk[:3900] for chunk in chunks if chunk.split()]
    words = [len(chunk.split()) for chunk in chunks]
    total = sum(words)
    if not chunks or total < 3 or not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError('Supply the transcript text and capture the video first so its length is known.')
    cues, spoken = [], 0
    for chunk, count in zip(chunks, words):
        start = duration_seconds * spoken / total
        spoken += count
        end = min(duration_seconds, max(duration_seconds * spoken / total, start + 0.05))
        cues.append(TranscriptCue(start_seconds=round(start, 3), end_seconds=round(end, 3), text=chunk))
    if len(cues) > 10000:
        raise ValueError('Supply between one and 10,000 timestamped cues.')
    check_reference_text('', '', tuple(cues))
    return tuple(cues)


def parse_supplied_transcript(value: str, duration_seconds: float | None = None):
    if not value.strip() or len(value.encode('utf-8'))>1_000_000:
        raise ValueError('Supply a nonempty transcript under 1 MB (plain text, SRT, VTT or JSON).')
    if is_plain_transcript(value):
        return parse_plain_transcript(value, float(duration_seconds or 0))
    if value.lstrip().startswith('['):
        cues=tuple(TranscriptCue.model_validate(c) for c in json.loads(value))
    else:
        text=value.replace('\r\n','\n').replace('\r','\n').lstrip('\ufeff')
        rows=[]
        stamp=r'(?:(\d{1,2}):)?(\d{2}):(\d{2})[,.](\d{3})'
        pattern=re.compile(stamp+r'\s+-->\s+'+stamp+r'(?:\s+.*)?$')
        def seconds(parts):
            hour,minute,second,ms=parts
            if int(minute)>59 or int(second)>59:raise ValueError('Invalid transcript timestamp.')
            return int(hour or 0)*3600+int(minute)*60+int(second)+int(ms)/1000
        for block in re.split(r'\n\s*\n',text):
            lines=block.strip().splitlines()
            if not lines or lines[0].startswith(('WEBVTT','NOTE','STYLE','REGION')):continue
            position=next((i for i,line in enumerate(lines) if '-->' in line),None)
            if position is None:raise ValueError('Every transcript cue needs an SRT/VTT timestamp.')
            match=pattern.fullmatch(lines[position])
            if not match:raise ValueError('Invalid SRT/VTT timestamp; use hours:minutes:seconds.milliseconds.')
            rows.append(TranscriptCue(start_seconds=seconds(match.groups()[:4]),end_seconds=seconds(match.groups()[4:]),text='\n'.join(lines[position+1:])))
        cues=tuple(rows)
    if not cues or len(cues)>10000:raise ValueError('Supply between one and 10,000 timestamped cues.')
    starts=tuple(c.start_seconds for c in cues)
    if starts!=tuple(sorted(starts)):raise ValueError('Transcript cues must be in source order.')
    check_reference_text('','',cues)
    return cues


class ReferenceIntakeService:
    def __init__(self,repository,extractor=None):
        self.repository=repository;self.extractor=extractor or YoutubeReferenceExtractor()

    def run_once(self,owner,*,cancelled=lambda:False):
        if cancelled():return None
        claim=self.repository.claim(owner)
        if claim is None:return None
        try:
            cached=self.repository.cached_snapshot(claim)
            snapshot=cached['snapshot'] if cached else None
            cache_hit=cached is not None
            cached_failure=IntakeFailure(cached['code'],cached['message']) if cached and cached['code'] else None
            if snapshot is None and claim['request'].supplied_cues:
                previous=self.repository.previous_snapshot(claim)
                if previous is not None:
                    request=claim['request']
                    check_reference_text(previous.title,previous.creator,request.supplied_cues)
                    raw=previous.model_dump(mode='python')
                    raw.update(cues=request.supplied_cues,language=request.language,transcript_origin='supplied',
                        limitations=('Metadata reused from the earlier capture; no new video fetch was made.',
                                     'Transcript supplied by the operator and not verified against source audio.',
                                     'Reference context is not factual approval or permission to reuse footage.'))
                    snapshot=ReferenceSnapshot.model_validate(raw)
            if snapshot is None:
                snapshot=self.extractor.capture(claim['request'],cancelled=lambda:cancelled() or not self.repository.owns(claim))
            if cancelled():return None  # leave the pending lease for a safe restart
            self.repository.finish(claim,snapshot=snapshot,failure=cached_failure,cache_hit=cache_hit)
        except IntakeFailure as error:
            if cancelled():return None
            self.repository.finish(claim,snapshot=error.snapshot,failure=error)
        except (ValueError,TypeError) as error:
            if cancelled():return None
            self.repository.finish(claim,failure=IntakeFailure('retrieval_failed','Reference or supplied transcript failed validation; inspect the source duration, language and cue bounds.'))
        except Exception:
            if cancelled():return None
            # Do not expose source URLs with signed caption tokens, raw text or tracebacks.
            self.repository.finish(claim,failure=IntakeFailure('retrieval_failed','Reference capture failed; inspect Activity and retry if appropriate.'))
        return self.repository.get(claim['intake_id'],claim['revision'])
