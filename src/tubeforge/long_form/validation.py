"""Bind exact LF2 source/reference context and execute canonical local tools."""
from __future__ import annotations
import hashlib

from tubeforge.domain.long_form import LongFormPlanningContract
from tubeforge.providers.content.youtube_skills import evaluate,hook_gate
from tubeforge.long_form.prompts import word_limits
from tubeforge.pipeline.scene_contracts import validate_request_source_packet
from tubeforge.pipeline.long_form_reference import reference_content_identity


def validate_draft(draft,message,reference,*,source_packet_bytes):
    if draft.package is None:raise ValueError(draft.reason or 'insufficient primary-source support')
    package=draft.package
    if package.request!=message.request:raise ValueError('draft changed the canonical request')
    minimum,maximum=word_limits(message.request.target_duration_seconds)
    words=sum(len(s.narration.split()) for s in package.script_sections)
    if not minimum<=words<=maximum:raise ValueError('narration does not fit the explicit long-form word range')
    if len(message.request.sources)<2 or len({str(s.url) for s in message.request.sources})!=len(message.request.sources):
        raise ValueError('long-form writing requires at least two distinct captured primary sources')
    if hashlib.sha256(reference.model_dump_json().encode()).hexdigest()!=message.reference_snapshot_sha256 or reference_content_identity(reference)!=message.reference_content_sha256:
        raise ValueError('reference snapshot changed since reservation')
    if reference.transcript_origin=='unavailable' or reference.language.casefold()!=message.request.language.casefold():
        raise ValueError('reference needs usable transcript context in the requested language')
    for excerpt in message.reference_excerpts:
        if excerpt.cue_index>=len(reference.cues) or excerpt.start_seconds!=reference.cues[excerpt.cue_index].start_seconds or excerpt.text not in reference.cues[excerpt.cue_index].text:
            raise ValueError('reference observation differs from captured source cue')
    if hashlib.sha256(source_packet_bytes).hexdigest()!=message.source_packet_sha256:
        raise ValueError('primary-source packet changed since reservation')
    validate_request_source_packet(message.request,source_packet_bytes)
    if len(package.metadata.description)>5000:raise ValueError('long-form description exceeds 5,000 characters')
    if [s.scene_id for s in package.script_sections]!=[s.scene_id for s in package.scene_plans]:
        raise ValueError('every section needs one corresponding ordered teaching scene')
    if not any(s.contains_factual_claims for s in package.script_sections):
        raise ValueError('a grounded explanation must contain factual teaching beats')
    if {c for s in package.script_sections for c in s.claim_ids}!={c.claim_id for c in package.claims}:
        raise ValueError('every supplied claim must support an actual script section')
    if any(not (s.on_screen_text and s.visual_subject and s.visual_purpose and s.composition and s.visual_elements) for s in package.scene_plans):
        raise ValueError('every teaching scene needs concrete display and landscape directions')
    for item in draft.improvements:
        if item.reference_cue_index>=len(reference.cues):raise ValueError('improvement references an unknown source cue')
        if item.reference_quote not in reference.cues[item.reference_cue_index].text:
            raise ValueError('improvement observation quote must match its captured reference cue')
    plan=LongFormPlanningContract(request=message.request,source_packet_sha256=message.source_packet_sha256,
        reference_snapshot_sha256=message.reference_snapshot_sha256,section_ids=tuple(s.section_id for s in package.script_sections),
        cited_source_ids=tuple(dict.fromkeys(source for c in package.claims for source in c.source_ids)),chapters=draft.chapters)
    scores=evaluate(package)
    if len(scores['selected_hook'].split())>24:raise ValueError('chosen opening exceeds 24 spoken words')
    hook_problem=hook_gate(package)
    if hook_problem:raise ValueError(hook_problem)
    return plan,scores


def validate_review(review,draft):
    package=draft.package
    if package is None:raise ValueError('review needs a complete draft')
    claims={c.claim_id:c for c in package.claims};sources={s.source_id:s for s in package.request.sources}
    sections={s.section_id for s in package.script_sections}
    seen=set()
    for check in review.claim_checks:
        if check.claim_id not in claims or check.source_id not in claims[check.claim_id].source_ids:
            raise ValueError('review cites an unknown claim or uncited source')
        if check.source_quote not in (sources[check.source_id].excerpt or ''):
            raise ValueError('review support quote must be literal captured primary-source text')
        pair=(check.claim_id,check.source_id)
        if pair in seen:raise ValueError('review evidence checks must be distinct')
        seen.add(pair)
    if {claim for claim,_ in seen}!=set(claims):raise ValueError('independent review must check every claim')
    if any(not set(f.section_ids)<=sections for f in review.findings):raise ValueError('review finding names an unknown section')
    return review
