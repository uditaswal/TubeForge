"""Render seven explicitly synthetic token fixtures; never generate narration or publish."""
import argparse,os,sys,json,hashlib,shutil,tempfile,subprocess
from pathlib import Path
from tubeforge.rendering.shorts.schema import Hook,Loop,BigStat,BeforeAfter,Flow,Checklist,Terminal
from tubeforge.rendering.hyperframes_proto import compose,cli
from tubeforge.rendering.shorts.design_tokens import VideoDesignTokens,decorate_project
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=Path('artifacts/review/design-tokens-v1'))
parser.add_argument('--hyperframes-bin',default=os.environ.get('TUBEFORGE_HYPERFRAMES_BIN') or shutil.which('hyperframes'))
args=parser.parse_args()
if not args.hyperframes_bin:parser.error('supply --hyperframes-bin or install HyperFrames on PATH')
out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
tokens=VideoDesignTokens.from_data({'entity_colors':{'System A':'#ffb870','System B':'#79e8b0'},'anchor_headline':['LAYOUT FIXTURE','SYSTEM A / B']})
common=dict(source_ids=(),icon='code')
hook=dict(scene_id='hook',template='hook',vo='See how System A and System B handle this illustrative request.',caption='See how System A and System B handle this illustrative request.',reveal_words=[2],headline=['System A','System B'],chips=['Request','Route','Result'],**common)
cases=[Hook.model_validate(hook),BigStat.model_validate(dict(scene_id='stat',template='big_stat',vo='In this illustrative comparison, System A has one unit and System B has two.',caption='In this illustrative comparison, System A has one unit and System B has two.',reveal_words=[4,10],heading='System A vs System B',before=1,after=2,unit='x',before_label='System A',after_label='System B',**common)),BeforeAfter.model_validate(dict(scene_id='compare',template='before_after',vo='In this layout fixture, System A waits while System B advances.',caption='In this layout fixture, System A waits while System B advances.',reveal_words=[4,8],heading='Two illustrative states',before='System A: queued',after='System B: ready',**common)),Flow.model_validate(dict(scene_id='flow',template='flow',vo='Follow this illustrative request from System A through a router to System B.',caption='Follow this illustrative request from System A through a router to System B.',reveal_words=[5,9,11],heading='Follow the request',nodes=['System A','Router','System B'],**common)),Checklist.model_validate(dict(scene_id='check',template='checklist',vo='Check System A, check System B, then keep this illustrative request visible.',caption='Check System A, check System B, then keep this illustrative request visible.',reveal_words=[1,4,8],heading='Check the same request',items=['System A ready','System B ready','Request visible'],**common)),Terminal.model_validate(dict(scene_id='terminal',template='terminal',vo='This illustrative console checks System A, then shows System B as ready.',caption='This illustrative console checks System A, then shows System B as ready.',reveal_words=[3,6,8],heading='Illustrative console',evidence_label='ILLUSTRATIVE OUTPUT',lines=[{'kind':'command','text':'System A status'},{'kind':'output','text':'System A ready'},{'kind':'output','text':'System B ready'}],**common)),Loop.model_validate({**hook,'scene_id':'loop','template':'loop'})]
builders={'hook':compose.build_hook_project,'big_stat':compose.build_big_stat_project,'before_after':compose.build_before_after_project,'flow':compose.build_flow_project,'checklist':compose.build_checklist_project,'terminal':compose.build_terminal_project,'loop':compose.build_loop_project}
binary=args.hyperframes_bin
records=[]
with tempfile.TemporaryDirectory(prefix='tf-design-tokens-',dir='/tmp') as scratch:
 scratch=Path(scratch)
 env={'HYPERFRAMES_EXTRACT_CACHE_DIR':str(scratch/'cache')}
 for scene in cases:
  words=[(i*.3,(i+1)*.3) for i in range(len(scene.vo.split()))];duration=len(words)*.3+.18
  project=out/scene.template;builders[scene.template](scene,words,duration,project)
  record=decorate_project(project,scene,words,tokens,source_label='SYNTHETIC LAYOUT · ESTIMATED WORD TIMING')
  short=scratch/scene.template;shutil.copytree(project,short)
  print('CHECK',scene.template,flush=True)
  check=cli.check(short,hyperframes_bin=binary,timeout=180,extra_env=env)
  (project/'check.json').write_text(json.dumps(check,indent=2))
  video=scratch/(scene.template+'.mp4');cli.render(short,video,hyperframes_bin=binary,timeout=420,workers=1,quality='high',extra_env=env)
  subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(video),'-f','null','-'],check=True)
  shutil.copy2(video,project/'clip.mp4')
  subprocess.run(['ffmpeg','-v','error','-y','-ss',str(max(.1,duration*.65)),'-i',str(video),'-frames:v','1',str(project/'frame.png')],check=True)
  records.append({**record,'template':scene.template,'duration':duration,'word_timing':'synthetic .3s fixture; not measured','video_sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'check_ok':check['ok']})
  print('PASS',scene.template,flush=True)
(out/'review-manifest.json').write_text(json.dumps({'scope':'seven synthetic geometry clips, not production narration or factual evidence','tokens':tokens.to_data(),'scenes':records},indent=2)+'\n')
print(out,flush=True)
