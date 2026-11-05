"""Local-only benchmark of the exact operator-approved PHP narration revision.

Reads a preserved parent job, renders into a separate review folder, never opens
a database, calls a script provider or changes production approvals.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil

from tubeforge.core.config import FakeProviderConfig, KokoroProviderConfig, RenderProfile
from tubeforge.domain.contracts import ContentPackage, VoiceRequest, video_plan_from_package
from tubeforge.pipeline.alignment import LocalWordAligner, verify_word_alignment
from tubeforge.pipeline.captions import timed_phrases, render_srt, render_highlighted_ass
from tubeforge.pipeline.direction import direction_report
from tubeforge.pipeline.narration import segment_content_package
from tubeforge.pipeline.scene_contracts import compile_scene_contract, scene_media_request
from tubeforge.pipeline.storyboard import storyboard_manifest, render_contact_sheets
from tubeforge.providers.media.local_graphics import LocalMotionGraphicsProvider
from tubeforge.providers.voice.kokoro import KokoroVoiceProvider
from tubeforge.rendering.audio import FFprobe, FFmpegAudioAssembler
from tubeforge.rendering.preview import build_timeline, PreviewRenderer, checksum

APPROVED = 'eb1a30e5b416b9693609af7bf806ee12d7f66460b48185a10c6caf33656ba239'


def revised_package(base: bytes, proposal: dict) -> ContentPackage:
    if hashlib.sha256(base).hexdigest() != proposal['base_content_package_sha256']:
        raise ValueError('parent package differs from the reviewed proposal')
    data = json.loads(base)
    data['script_sections'] = proposal['script_sections']
    data['claims'] = [claim for claim in data['claims'] if claim['claim_id'] != 'c6']
    next(claim for claim in data['claims'] if claim['claim_id'] == 'c2')['text'] = (
        'NCSC identifies CVE-2026-109618 and CVE-2026-109619 and urges organisations using any PHP version to assess their exposure.')
    scenes = {scene['scene_id']: scene for scene in data['scene_plans']}
    scenes['scene2']['on_screen_text'] = 'NCSC: assess PHP exposure'
    scenes['scene3']['on_screen_text'] = 'Conditional code execution'
    scenes['scene5']['on_screen_text'] = 'If updating is delayed'
    scenes['scene5']['visual_elements'][1] = 'Consider offline'
    scenes['scene6'].update(on_screen_text='Prioritise, then update',
        visual_elements=['Internet-facing first', 'Find PHP systems', 'Update PHP'],
        visual_subject='Prioritise and update PHP systems',
        visual_purpose='Recap the source-backed update action',
        composition='Wide action recap with ordered word-anchored steps',
        card_cues={'kind':'close','first_word_index':3,'second_word_index':4,'third_word_index':6})
    package = ContentPackage.model_validate(data)
    if [section.narration for section in package.script_sections] != proposal['narrations']:
        raise ValueError('benchmark narration differs from the approved draft')
    return package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--approval-dir',type=Path,default=Path('tests/fixtures/benchmarks/php_m4'))
    args = parser.parse_args()
    parent, output = args.parent.resolve(), args.output.resolve()
    # Never permit writes to the production tree, even through relative paths.
    if output == parent or parent in output.parents or output in parent.parents or Path('data').resolve() in output.parents:
        raise ValueError('use a separate benchmark output outside data/')
    raw = (args.approval_dir/'approved_proposal.json').read_bytes()
    approval = json.loads((args.approval_dir/'operator-approval.json').read_text())
    if hashlib.sha256(raw).hexdigest() != APPROVED or approval['proposal_sha256'] != APPROVED:
        raise ValueError('exact benchmark approval does not match')
    proposal = json.loads(raw)
    package = revised_package((parent/'content_package.json').read_bytes(),proposal)
    output.mkdir(parents=True,exist_ok=True)
    def save(name,value):
        (output/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    save('operator-approval.json',approval)
    save('effective_content_request.json',package.request.model_dump(mode='json'))
    package_bytes=package.model_dump_json().encode()
    (output/'content_package.json').write_bytes(package_bytes)
    source_bytes=(parent/'source_packet.json').read_bytes()
    (output/'source_packet.json').write_bytes(source_bytes)
    contract=compile_scene_contract(package_bytes,source_bytes,accepted_script_identity=hashlib.sha256(package_bytes).hexdigest())
    save('scene_contract.json',contract.model_dump(mode='json'))
    phrases=segment_content_package(package)
    original={item['phrase_id']:item for item in json.loads((parent/'voice_manifest.json').read_text())['voices']}
    voice=KokoroVoiceProvider(KokoroProviderConfig(model_path=Path('models/kokoro-v1.0.int8.onnx'),voices_path=Path('models/voices-v1.0.bin')))
    measured=[]
    probe=FFprobe()
    for phrase in phrases:
        destination=output/'voice'/f'{phrase.phrase_id}.wav';destination.parent.mkdir(exist_ok=True)
        old=original.get(phrase.phrase_id)
        if old and old['text']==phrase.text:
            source=Path('data/cache/kokoro/af_sarah')/Path(old['artifact_path']).name
            if not source.is_file() or checksum(source)!=old['checksum_sha256']:
                raise ValueError('preserved phrase audio is unavailable or changed')
            shutil.copy2(source,destination)
            reused=True
        else:
            print('SYNTHESIZE APPROVED',phrase.section_id,phrase.phrase_id,flush=True)
            voice.synthesize(VoiceRequest(text=phrase.text,language='en',voice_id='af_sarah',section_id=phrase.section_id,phrase_id=phrase.phrase_id,output_path=str(destination)))
            reused=False
        measured.append({'phrase_id':phrase.phrase_id,'section_id':phrase.section_id,'text':phrase.text,
            'claim_ids':list(phrase.claim_ids),'artifact_path':str(destination),'checksum_sha256':checksum(destination),
            'duration_seconds':float(probe.inspect(destination)['duration_seconds']), 'reused_exact_parent_audio':reused})
    save('voice_manifest.json',{'alignment_contract':{'provider':'local-waveform-v1','word_edges':'waveform span plus weighted estimates; not independent forced alignment'},'voices':measured})
    narration=output/'narration.wav'
    FFmpegAudioAssembler().assemble(tuple(Path(item['artifact_path']) for item in measured),narration,pause_seconds=.15)
    duration=float(probe.inspect(narration)['duration_seconds'])
    if not 36<=duration<=84:raise ValueError('outside original 60-second target tolerance')
    cues=timed_phrases(phrases,tuple(item['duration_seconds'] for item in measured),.15)
    words=[];aligner=LocalWordAligner()
    for cue,item in zip(cues,measured,strict=True):
        words.extend(aligner.align(audio_path=Path(item['artifact_path']),text=cue.phrase.text,phrase_id=cue.phrase.phrase_id,section_id=cue.phrase.section_id,phrase_start_seconds=cue.start_seconds,phrase_end_seconds=cue.end_seconds,ordinal_start=len(words)))
    timing={'final_duration_seconds':duration,'target_duration_seconds':60,
        'phrases':[{'phrase_id':cue.phrase.phrase_id,'section_id':cue.phrase.section_id,'start_seconds':cue.start_seconds,'end_seconds':cue.end_seconds} for cue in cues],
        'words':[asdict(word) for word in words], 'alignment':verify_word_alignment(tuple(words),final_duration=duration,tolerance=.15)}
    save('timing_map.json',timing)
    (output/'captions.srt').write_text(render_srt(cues))
    (output/'captions.ass').write_text(render_highlighted_ass(tuple(words),width=1920,height=1080,font_size=58,margin_vertical=65,margin_horizontal=100,center_x=960,phrases=cues))
    media=LocalMotionGraphicsProvider(FakeProviderConfig(artifact_root=output/'assets'))
    assets={}
    for row in contract.scenes:
        candidate=media.search(scene_media_request(row,orientation='landscape'))[0]
        path=Path(candidate.local_path);digest=checksum(path)
        assets[row.scene_id]={'candidate':candidate.model_dump(mode='json'),'path':str(path),'checksum_sha256':digest,
                             'validation':{'media_type':'image','width':1920,'height':1080,'checksum_sha256':digest}}
    save('asset_manifest.json',{'scenes':assets})
    report=storyboard_manifest(package,video_plan_from_package(package,aspect_ratio='16:9'),assets)
    report['direction']=direction_report(package)
    report['contact_sheets']=[str(p) for p in render_contact_sheets(report,output/'storyboard')]
    save('storyboard_manifest.json',report)
    renderer=PreviewRenderer(RenderProfile(width=1920,height=1080,bounded_memory=True,audio_normalization_enabled=True,timeout_seconds=1800,video_crf=20))
    segments=build_timeline(package,timing,assets,tolerance=renderer.config.sync_tolerance_seconds,scene_contract=contract)
    print('RENDER',duration,flush=True)
    result=renderer.render(segments,narration,output/'captions.ass',output/'final.mp4')
    save('final_manifest.json',{**result,'approval_identity':APPROVED,'scope':'new local benchmark; original production job/approvals unchanged','parent_package_sha256':proposal['base_content_package_sha256']})
    print('PASS render',checksum(output/'final.mp4'),flush=True)

if __name__=='__main__':main()
