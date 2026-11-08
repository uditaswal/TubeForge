"""Small deterministic reference worksheet; observations are never factual evidence."""
from __future__ import annotations

import hashlib

from tubeforge.domain.reference_video import ReferenceSnapshot


def build_reference_brief(snapshot: ReferenceSnapshot, target_seconds: int) -> dict:
    identity=hashlib.sha256(snapshot.model_dump_json().encode()).hexdigest()
    cues=snapshot.cues
    indexes=sorted({round(i*(len(cues)-1)/5) for i in range(6)}) if cues else []
    samples=[dict(cue_index=i,start_seconds=cues[i].start_seconds,end_seconds=cues[i].end_seconds,
                  excerpt=cues[i].text[:240],excerpt_truncated=len(cues[i].text)>240) for i in indexes]
    # Union of caption intervals: overlap/ASR roll-up must not inflate coverage.
    covered=0.;end=0.
    for cue in cues:
        covered+=max(0.,cue.end_seconds-max(end,cue.start_seconds));end=max(end,cue.end_seconds)
    proposals=[]
    if cues:
        candidates=[(0,'Opening promise','Does the opening make the viewer payoff concrete?',
                     'Draft a distinct opening around our own useful result; compare it with this source opening.'),
                    (len(cues)//2,'Original worked example','What new worked example would help explain this part?',
                     'Research and demonstrate an original example instead of copying this wording or explanation order.'),
                    (len(cues)-1,'Limits and payoff','Which limitations and unanswered questions should our ending resolve?',
                     'Verify limitations with primary sources and plan a concrete final payoff.')]
        for index,label,question,change in candidates:
            cue=cues[index]
            proposals.append(dict(label=label,cue_index=index,start_seconds=cue.start_seconds,
                source_excerpt=cue.text[:240],viewer_question=question,proposed_change=change,
                supporting_evidence='NOT STARTED: primary-source research and editorial review required.',
                planned_scene='NOT STARTED: bind to reviewed narration in a later phase.'))
    return dict(schema_version='reference-observation-brief-v1',reference_snapshot_sha256=identity,
        classification='Untrusted reference observations and provisional improvement questions; no AI analysis or factual verification.',
        title_promise=snapshot.title,target_duration_seconds=target_seconds,source_duration_seconds=snapshot.duration_seconds,
        transcript_origin=snapshot.transcript_origin,cue_count=len(cues),
        caption_interval_coverage_percent=round(100*covered/snapshot.duration_seconds,1),
        samples=samples,proposed_improvements=proposals,
        limitations=['Samples are indexed excerpts, not a summary of every claim, example or visual.',
                     'Audience, questions answered and gaps need editorial review; no audience analytics were inspected.',
                     'Proposals are review questions, not findings that the original video is deficient.',
                     'Do not use this sampled worksheet alone for originality comparison; compare against the full transcript.'])
