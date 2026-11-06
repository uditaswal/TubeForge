"""Chapter export from accepted structure and actual absolute audio timings."""
from __future__ import annotations

from tubeforge.domain.long_form import LongFormPlanningContract, LongFormTimingManifest


def export_chapters(planning: LongFormPlanningContract, timing: LongFormTimingManifest, *,
                    package_sha256: str, audio_sha256: str, artifact_sha256: str) -> str:
    """Whole-second timestamps are floored; no proportional/estimated timing.

    Callers validate the approved package first. The first chapter includes any
    opening lead-in from media time zero, even if the first spoken word is later.
    """
    if (timing.package_sha256 != package_sha256 or timing.audio_sha256 != audio_sha256
        or timing.artifact_sha256 != artifact_sha256):
        raise ValueError('chapter timing is stale for the accepted script/audio/artifact')
    if tuple(s.section_id for s in timing.sections) != planning.section_ids:
        raise ValueError('chapter timing must cover the exact ordered section inventory')
    if abs(timing.duration_seconds-planning.request.target_duration_seconds) > planning.request.target_duration_seconds*0.05:
        raise ValueError('chapter timing duration differs from target by more than five percent')
    by_id = {s.section_id:s.start_seconds for s in timing.sections}
    starts = tuple(0 if i == 0 else int(by_id[c.section_ids[0]]) for i,c in enumerate(planning.chapters))
    ends = (*starts[1:],timing.duration_seconds)
    if any(end-start < 10 for start,end in zip(starts,ends,strict=True)):
        raise ValueError('exported chapters must each last at least ten seconds')
    lines=[]
    for start,chapter in zip(starts,planning.chapters,strict=True):
        if '\n' in chapter.title or '\r' in chapter.title:
            raise ValueError('chapter titles cannot inject extra timestamp lines')
        lines.append(f'{start//60:02d}:{start%60:02d} {chapter.title}')
    return '\n'.join(lines)
