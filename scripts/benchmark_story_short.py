"""Render a distinct local Story comparison from captured, reviewed speech.

No provider, approval or publication actions. Source captures are refreshed from
already-cited URLs. --resume reuses only hash-verified prepared local inputs.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import time

from tubeforge.core.config import SourceCaptureConfig
from tubeforge.pipeline.capture import CAPTURE_POLICY, make_capture
from tubeforge.pipeline.plates import _source
from tubeforge.pipeline.reference_short import load_timeline
from tubeforge.rendering.shorts.schema import ShortsTopic, SourceVisual
from tubeforge.rendering.shorts.plates import load_manifest
from tubeforge.rendering.shorts.story import build_story, render_silent
from tubeforge.rendering.shorts.hyperframes_encode import encode


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_visual_revision(output, revision_path):
    """Bounded visual-only edits, each verified against the exact stored source."""
    reference=output/'reference'
    revision=json.loads(revision_path.read_text())
    if sha(reference/'topic.json')!=revision['expected_topic_sha256']:
        raise ValueError('visual revision belongs to a different topic')
    package=json.loads((output/'content_package.json').read_text())
    topic=json.loads((reference/'topic.json').read_text())
    sources={row['source_id']:row for row in package['request']['sources']}
    for change in revision['source_quotes']:
        scene=next(row for row in topic['scenes'] if row['scene_id']==change['scene_id'])
        if scene.get('visual',{}).get('kind')!='source' or scene['visual']['quote']!=change['expected_quote']:
            raise ValueError('visual revision does not match the saved source quote')
        new_quote=change['quote']
        approved=sources[scene['source_ids'][0]].get('excerpt') or ''
        normalize=lambda value:' '.join(value.split())
        if normalize(new_quote) not in normalize(approved) or new_quote not in change['expected_quote']:
            raise ValueError('replacement must be an exact bounded excerpt of the stored approved source')
        scene['visual']['quote']=new_quote
    validated=ShortsTopic.model_validate(topic)
    (reference/'topic.json').write_text(validated.model_dump_json(indent=2))
    package['reference_short']=validated.model_dump(mode='json')
    (output/'content_package.json').write_text(json.dumps(package,indent=2))
    timing=json.loads((reference/'timeline.json').read_text())
    timing['topic_sha256']=sha(reference/'topic.json')
    (reference/'timeline.json').write_text(json.dumps(timing,indent=2))
    shutil.copyfile(revision_path,output/'visual-revision.json')


def prepare(comparison, source_reference, output, visual_revision=None):
    output.mkdir(parents=True,exist_ok=False)
    reference=output/'reference'
    reference.mkdir()
    for name in ('topic.json','timeline.json','narration.wav'):
        shutil.copyfile(comparison/'reference'/name,reference/name)
    shutil.copyfile(comparison/'content_package.json',output/'content_package.json')
    shutil.copyfile(comparison/'accepted-mix.wav',output/'accepted-mix.wav')
    (reference/'mix').mkdir()
    shutil.copyfile(comparison/'reference/mix/audio-provenance.json',reference/'mix/audio-provenance.json')
    topic=ShortsTopic.model_validate_json((reference/'topic.json').read_bytes())
    load_timeline(topic,reference)  # exact topic, narration and timing must still match
    if visual_revision is not None:
        apply_visual_revision(output,visual_revision)
        topic=ShortsTopic.model_validate_json((reference/'topic.json').read_bytes())
        load_timeline(topic,reference)
    manifest=load_manifest(source_reference)
    plates=reference/'plates'
    plates.mkdir()
    # Only copy paths named by this manifest; never sweep generated artifact trees.
    for entry in manifest['scenes'].values():
        for key in ('file','highlight','file_2x','highlight_2x'):
            if not entry.get(key):
                continue
            relative=Path(entry[key])
            original=(source_reference/relative).resolve()
            target=(reference/relative).resolve()
            if not original.is_relative_to(source_reference.resolve()) or not target.is_relative_to(reference.resolve()):
                raise ValueError('plate path escapes its reference folder')
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(original,target)
    capture=make_capture(SourceCaptureConfig(timeout_seconds=45))
    if capture is None:
        raise ValueError('Chromium source capture is unavailable')
    sources={s.source_id:str(s.url) for s in topic.sources}
    for index,scene in enumerate(topic.scenes):
        if isinstance(scene.visual,SourceVisual):
            entry=_source(scene.visual,index,scene.source_ids[0],sources,plates,capture)
            if entry.get('kind')!='source' or not entry.get('matched'):
                raise ValueError(f'scene {index} full source quote was not recaptured: {entry}')
            manifest['scenes'][str(index)]=entry
            print('recaptured',index,entry['evidence']['hidden_controls'],flush=True)
    manifest_path=plates/'manifest.json'
    manifest_path.write_text(json.dumps(manifest,indent=2))
    paths=[output/'content_package.json',output/'accepted-mix.wav',reference/'topic.json',
           reference/'timeline.json',reference/'narration.wav',reference/'mix/audio-provenance.json',manifest_path]
    for entry in manifest['scenes'].values():
        paths.extend(reference/entry[key] for key in ('file','highlight','file_2x','highlight_2x') if entry.get(key))
    if (output/'visual-revision.json').exists():
        paths.append(output/'visual-revision.json')
    proof={'scope':'unapproved Story visual comparison; captured narration and mix reused',
           'capture_policy':CAPTURE_POLICY,'files':{str(p.relative_to(output)):sha(p) for p in paths}}
    (output/'prepared-inputs.json').write_text(json.dumps(proof,indent=2))


def verify_prepared(output):
    proof=json.loads((output/'prepared-inputs.json').read_text())
    if proof['capture_policy']!=CAPTURE_POLICY:
        raise ValueError('prepared captures use a different policy')
    for name,expected in proof['files'].items():
        path=(output/name).resolve()
        if not path.is_relative_to(output.resolve()) or sha(path)!=expected:
            raise ValueError(f'prepared input changed: {name}')
    reference=output/'reference'
    topic=ShortsTopic.model_validate_json((reference/'topic.json').read_bytes())
    return load_timeline(topic,reference)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comparison',type=Path,required=True)
    parser.add_argument('--source-reference',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--hyperframes-bin',required=True)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--visual-revision',type=Path)
    parser.add_argument('--budget-rtf',type=float,default=20)
    args=parser.parse_args()
    output=args.output.resolve()
    if any(output==source or source in output.parents for source in
           (args.comparison.resolve(),args.source_reference.resolve())):
        raise ValueError('use a separate comparison folder')
    if not args.resume:
        prepare(args.comparison.resolve(),args.source_reference.resolve(),output,args.visual_revision)
    timeline=verify_prepared(output)
    if (output/'final.mp4').exists():
        raise ValueError('a final artifact already exists; use a fresh comparison folder')
    reference=output/'reference'
    # Keep an inspectable project even if the guarded CLI render fails.
    report=build_story(timeline,output/'project',plates_directory=reference,manifest=load_manifest(reference))
    (output/'scene-plan-report.json').write_text(json.dumps(report,indent=2))
    source_root=Path(__file__).resolve().parents[1]
    code_paths=['src/tubeforge/rendering/shorts/story.py','src/tubeforge/rendering/shorts/editor.py',
                'src/tubeforge/rendering/shorts/hyperframes_encode.py','scripts/benchmark_story_short.py']
    (output/'render-inputs.json').write_text(json.dumps({
        'budget_rtf':args.budget_rtf,'prepared_inputs_sha256':sha(output/'prepared-inputs.json'),
        'renderer_sources':{name:sha(source_root/name) for name in code_paths}},indent=2))
    started=time.monotonic()
    report=render_silent(timeline,output/'silent.mp4',draft=False,budget_rtf=args.budget_rtf,
        hyperframes_bin=args.hyperframes_bin,plates_directory=reference)
    (output/'story-render-report.json').write_text(json.dumps(report,indent=2))
    voice_health=json.loads((reference/'mix/audio-provenance.json').read_text()).get('narration_health')
    final=encode(timeline,output/'silent.mp4',output/'accepted-mix.wav',output/'final.mp4',
        draft=False,budget_rtf=args.budget_rtf,render_started=started,scene_report=report,narration_health=voice_health)
    (output/'quality_report.json').write_text(json.dumps({'reference_qa':final},indent=2))
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(output/'final.mp4'),'-vf',
        f'fps=1/2,scale=270:480,tile=5x{math.ceil(timeline.duration/10)}','-frames:v','1',str(output/'contact.png')],check=True)
    print('final',json.dumps({'sha256':sha(output/'final.mp4'),'seconds':timeline.duration,
        'render_seconds':time.monotonic()-started,'loudness':final['loudness']}),flush=True)


if __name__=='__main__':
    main()
