"""Advisory direction evidence; never rewrite an approved script or source packet."""
from __future__ import annotations

import hashlib
import re
from tubeforge.domain.contracts import ContentPackage

VERSION = 'video-direction-v1'


def direction_report(package: ContentPackage, context: dict | None = None) -> dict:
    planned = {scene.scene_id: scene for scene in package.scene_plans}
    rows, warnings = [], []
    sections = {section.scene_id: section for section in package.script_sections}
    reference = package.reference_short
    scenes = reference.scenes if reference is not None else tuple(planned[section.scene_id] for section in package.script_sections)
    for scene in scenes:
        plan = planned.get(scene.scene_id)
        layout = scene.template if reference is not None else scene.visual_type
        cues = (list(scene.reveal_words) if reference is not None else
                next((cue.model_dump(mode='json') for cue in
                      (scene.terminal_cues, scene.card_cues, scene.teaching_cues) if cue is not None), None))
        section = sections.get(scene.scene_id)
        narration = scene.vo if reference is not None else section.narration if section else ''
        row = {'scene_id': scene.scene_id, 'layout': layout,
               'subject': plan.visual_subject if plan else None,
               'purpose': plan.visual_purpose if plan else None,
               'composition': plan.composition if plan else None,
               'reveal_anchors': cues,
               'narration_sha256': hashlib.sha256(narration.encode()).hexdigest()}
        rows.append(row)
        if not row['purpose']:
            warnings.append({'code': 'purpose_missing', 'scene_id': scene.scene_id,
                             'message': 'Review what this scene teaches beyond its narration.'})
        if cues is None:
            warnings.append({'code': 'reveal_not_declared', 'scene_id': scene.scene_id,
                             'message': 'No word-anchored reveal is declared; inspect any long hold.'})
        if len(rows) >= 3 and len({r['layout'] for r in rows[-3:]}) == 1:
            warnings.append({'code': 'adjacent_layout_repetition', 'scene_id': scene.scene_id,
                             'message': 'Three adjacent scenes use this layout; review whether their teaching roles differ.'})
    history = (context or {}).get('recent_angles', [])
    def terms(value):
        return set(re.findall(r'\w+', value.casefold()))
    current = terms(package.request.topic + ' ' + package.request.angle)
    similar = []
    for item in history:
        previous = terms(item['topic'] + ' ' + item['angle'])
        overlap = len(current & previous) / max(1, len(current | previous))
        if overlap >= .65:
            similar.append({'job_id': item['job_id'], 'similarity': round(overlap, 3)})
    if similar:
        warnings.append({'code': 'recent_angle_overlap', 'scene_id': None,
                         'message': 'A recent local brief uses similar wording; review the new teaching angle.'})
    return {'version': VERSION, 'advisory': True,
            'context_scope': 'Local briefs, not publication history, factual sources or performance analytics.',
            'channel_identity': package.request.channel_identity,
            'history_available': context is not None, 'recent_angles': history,
            'similar_angles': similar, 'scenes': rows, 'warnings': warnings,
            'layouts_changed': False}
