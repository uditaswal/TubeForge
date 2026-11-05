from pathlib import Path
import hashlib, json, subprocess, time
from tubeforge.rendering.shorts.editor import EditorScene, EditorRenderer, VERSION
s=EditorScene(("cache = {}", "", "def read(key):", "    if key in cache:", "        return cache[key]", "    return fetch(key)"), typing_seconds=4,hold_seconds=2)
r=EditorRenderer(s)
out=Path('artifacts/review/reference-motion'); t=time.monotonic()
p=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','1080x1920','-r','30','-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p',str(out/'editor-portrait.mp4')],stdin=subprocess.PIPE)
try:
 for n in range(round(s.duration*30)):
  frame=r.frame(n/30);p.stdin.write(frame.tobytes())
finally:p.stdin.close()
if p.wait():raise RuntimeError('encode failed')
for name,sec in [('opening',0),('typing',2),('hold',5)]:r.frame(sec).save(out/f'{name}.png')
(out/'benchmark.json').write_text(json.dumps(dict(version=VERSION,seconds=s.duration,frames=round(s.duration*30),wall_seconds=time.monotonic()-t,sha256=hashlib.sha256((out/'editor-portrait.mp4').read_bytes()).hexdigest(),scope='silent synthetic portrait scene; not production acceptance'),indent=2))
