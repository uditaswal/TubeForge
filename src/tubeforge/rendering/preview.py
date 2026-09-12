"""Deterministic FFmpeg preview rendering with validated argument arrays."""
from __future__ import annotations
import hashlib, json, math, shutil, subprocess, time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from tubeforge.core.config import RenderProfile, SUPPORTED_AUDIO_ENCODERS, SUPPORTED_VIDEO_ENCODERS
from tubeforge.core.errors import ProviderValidationError, RetryableProviderError
from tubeforge.domain.contracts import ContentPackage

class PreviewRenderCancelled(RuntimeError): pass
RENDERER_TEMPLATE_VERSION = "m13-cinematic-motion-v1"

def parse_frame_rate(value: str) -> float:
    """Parse ffprobe's rational frame-rate representation."""
    try:
        numerator, denominator = value.split("/", 1)
        rate = float(numerator) / float(denominator)
    except (AttributeError, ValueError, ZeroDivisionError) as error:
        raise ProviderValidationError("ffprobe returned an invalid frame rate") from error
    if not math.isfinite(rate) or rate <= 0:
        raise ProviderValidationError("ffprobe returned a nonpositive frame rate")
    return rate

def checksum(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): digest.update(chunk)
    return digest.hexdigest()

@dataclass(frozen=True, slots=True)
class TimelineSegment:
    scene_id:str; section_id:str; start_seconds:float; end_seconds:float; asset_path:Path; asset_checksum:str; media_type:str
    @property
    def duration_seconds(self)->float: return self.end_seconds-self.start_seconds

def build_timeline(package: ContentPackage, timing_map: dict[str,object], assets: dict[str,object], *, tolerance:float)->tuple[TimelineSegment,...]:
    phrases=timing_map.get("phrases")
    if not isinstance(phrases,list) or not phrases: raise ProviderValidationError("preview requires a nonempty validated timing map")
    by_section:dict[str,list[dict[str,object]]]={}; previous=0.0
    for value in phrases:
        if not isinstance(value,dict): raise ProviderValidationError("timing map phrase is invalid")
        try: start,end,section=float(value["start_seconds"]),float(value["end_seconds"]),str(value["section_id"])
        except (KeyError,TypeError,ValueError) as error: raise ProviderValidationError("timing map phrase lacks valid timing") from error
        if not math.isfinite(start) or not math.isfinite(end) or start<0 or end<=start or abs(start-previous)>tolerance: raise ProviderValidationError("timing map has a gap, overlap, or invalid duration")
        previous=end; by_section.setdefault(section,[]).append(value)
    expected=float(timing_map.get("final_duration_seconds",0))
    if not math.isfinite(expected) or expected<=0 or abs(previous-expected)>tolerance: raise ProviderValidationError("timing map does not end with narration")
    if len({section.scene_id for section in package.script_sections}) != len(package.script_sections): raise ProviderValidationError("preview rejects duplicate scene IDs")
    if set(by_section) != {section.section_id for section in package.script_sections}: raise ProviderValidationError("timing map does not match approved script sections")
    output=[]
    for section in package.script_sections:
        group=by_section.get(section.section_id); asset=assets.get(section.scene_id)
        if not group or not isinstance(asset,dict): raise ProviderValidationError("every narrated scene requires an accepted licensed asset")
        try:
            path=Path(str(asset["path"])); validation=asset["validation"]; candidate=asset["candidate"]; asset_checksum=str(asset["checksum_sha256"]); media_type=str(validation["media_type"])
        except (KeyError,TypeError) as error: raise ProviderValidationError("accepted asset manifest is invalid") from error
        if not isinstance(validation,dict) or not isinstance(candidate,dict) or media_type not in {"image","video"}: raise ProviderValidationError("asset is not a validated image or video")
        if not candidate.get("license_name") or candidate.get("editorial_only") or candidate.get("review_required") or candidate.get("attribution_required"): raise ProviderValidationError("asset is unlicensed or unapproved")
        if not path.is_file() or path.stat().st_size==0 or checksum(path)!=asset_checksum or validation.get("checksum_sha256")!=asset_checksum: raise ProviderValidationError("accepted asset is missing or checksum mismatched")
        output.append(TimelineSegment(section.scene_id,section.section_id,float(group[0]["start_seconds"]),float(group[-1]["end_seconds"]),path,asset_checksum,media_type))
    previous=0.0
    for segment in output:
        if segment.duration_seconds<=0 or abs(segment.start_seconds-previous)>tolerance: raise ProviderValidationError("scene timeline has a gap, overlap, or zero-length segment")
        previous=segment.end_seconds
    if abs(previous-expected)>tolerance: raise ProviderValidationError("scene timeline is materially out of sync")
    return tuple(output)

class PreviewFFprobe:
    def __init__(self, executable:str="ffprobe", timeout_seconds:int=30)->None: self.executable,self.timeout_seconds=executable,timeout_seconds
    def command(self,path:Path)->list[str]: return [self.executable,"-v","error","-show_entries","format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels","-of","json",str(path)]
    def inspect(self,path:Path)->dict[str,Any]:
        if not path.is_file() or path.stat().st_size==0: raise ProviderValidationError("preview output is empty or missing")
        try: result=subprocess.run(self.command(path),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=self.timeout_seconds,check=False,shell=False)
        except subprocess.TimeoutExpired as error: raise RetryableProviderError("ffprobe preview validation timed out") from error
        except OSError as error: raise ProviderValidationError("ffprobe executable is unavailable") from error
        if result.returncode: raise ProviderValidationError("ffprobe rejected preview output")
        try: return json.loads(result.stdout.decode())
        except (UnicodeDecodeError,json.JSONDecodeError) as error: raise ProviderValidationError("ffprobe returned invalid preview metadata") from error

class PreviewRenderer:
    def __init__(self,config:RenderProfile,*,ffmpeg:str="ffmpeg",probe:PreviewFFprobe|None=None,process_factory:Callable[..., Any]=subprocess.Popen,template_version:str=RENDERER_TEMPLATE_VERSION,poll_seconds:float=0.1)->None: self.config,self.ffmpeg,self.probe,self.process_factory,self.template_version,self.poll_seconds=config,ffmpeg,probe or PreviewFFprobe(timeout_seconds=config.ffprobe_timeout_seconds),process_factory,template_version,poll_seconds
    def identity(self,segments:tuple[TimelineSegment,...],narration:Path,captions:Path, *, approval_identity: str | None = None)->str:
        value={"renderer":self.config.renderer_version,"template_version":self.template_version,"settings":self.config.model_dump(mode="json"),"narration":checksum(narration),"captions":checksum(captions),"segments":[(s.scene_id,s.section_id,s.start_seconds,s.end_seconds,s.asset_checksum,s.media_type) for s in segments],"transition":"cut", "approval_identity": approval_identity}
        return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    def command(self,segments:tuple[TimelineSegment,...],narration:Path,captions:Path,output:Path)->list[str]:
        command=[self.ffmpeg,"-nostdin","-y","-v","error","-threads",str(self.config.threads)]; filters=[]
        for i,scene in enumerate(segments):
            duration=f"{scene.duration_seconds:.6f}"
            command.extend(("-loop","1","-t",duration,"-i",str(scene.asset_path)) if scene.media_type=="image" else ("-stream_loop","-1","-t",duration,"-i",str(scene.asset_path)))
            filters.append(self._scene_filter(i, scene, duration))
        command.extend(("-i",str(narration))); labels="".join(f"[v{i}]" for i in range(len(segments))); caption=str(captions.resolve()).replace("\\","/").replace(":","\\:").replace("'","\\'"); style=f"FontSize={self.config.caption_font_size},Alignment=2,MarginV=36,Outline=2,Shadow=1"
        # Each independently rendered scene can lose up to one frame when its
        # measured narration duration is quantized to the configured frame
        # rate.  Without padding, ``-shortest`` uses that cumulative short
        # video stream and cuts off the end of the narration.  Holding the
        # final visual frame lets the measured narration timeline determine
        # the muxed duration while retaining the intended cut-only scene
        # sequence.  Padding both streams avoids FFmpeg's ``-shortest``
        # heuristic truncating a filtered multi-scene mux before the WAV's
        # measured end; the explicit output duration below is authoritative.
        filters += [
            f"{labels}concat=n={len(segments)}:v=1:a=0[base]",
            f"[base]subtitles='{caption}':force_style='{style}',tpad=stop_mode=clone:stop_duration=10[outv]",
            f"[{len(segments)}:a]apad=pad_dur=10[outa]",
        ]
        return [*command,"-filter_complex",";".join(filters),"-map","[outv]","-map","[outa]","-c:v",self.config.video_codec,"-pix_fmt",self.config.pixel_format,"-r",str(self.config.fps),"-c:a",self.config.audio_codec,"-b:a",self.config.audio_bitrate,"-t",f"{segments[-1].end_seconds:.6f}","-movflags","+faststart",str(output)]

    def _scene_filter(self, index: int, scene: TimelineSegment, duration: str) -> str:
        """Create a stable, subtle camera move for stills without affecting timing.

        Generated/local stills otherwise look like a slideshow.  ``zoompan``
        produces exactly one frame per output frame, so the existing measured
        narration timeline remains authoritative.  Video assets retain their
        native motion and only receive the normal fit/crop treatment.
        """
        common = (
            f"scale={self.config.width}:{self.config.height}:force_original_aspect_ratio=increase,"
            f"crop={self.config.width}:{self.config.height},setsar=1,fps={self.config.fps},"
            f"trim=duration={duration},setpts=PTS-STARTPTS"
        )
        if scene.media_type != "image" or not self.config.image_motion_enabled:
            return f"[{index}:v]{common}[v{index}]"
        frames = max(1, math.ceil(scene.duration_seconds * self.config.fps))
        # Alternate the pan direction by stable scene order.  The zoom grows
        # gently from 1.0 to the configured ceiling and is independent of the
        # source asset's dimensions or filename.
        direction = "iw-iw/zoom" if index % 2 else "0"
        zoom = f"min(zoom+({self.config.image_motion_zoom:.4f}-1)/{frames},{self.config.image_motion_zoom:.4f})"
        return (
            f"[{index}:v]scale={self.config.width * 2}:{self.config.height * 2}:"
            f"force_original_aspect_ratio=increase,crop={self.config.width * 2}:{self.config.height * 2},"
            f"zoompan=z='{zoom}':x='{direction}':y='ih/2-ih/zoom/2':d={frames}:"
            f"s={self.config.width}x{self.config.height}:fps={self.config.fps},"
            f"trim=duration={duration},setpts=PTS-STARTPTS[v{index}]"
        )
    def validate(self,path:Path,expected:float)->dict[str,Any]:
        data=self.probe.inspect(path); streams=data.get("streams"); video=next((x for x in streams if x.get("codec_type")=="video"),None) if isinstance(streams,list) else None; audio=next((x for x in streams if x.get("codec_type")=="audio"),None) if isinstance(streams,list) else None
        try: duration=float(data["format"]["duration"]); width,height=int(video["width"]),int(video["height"]); rate=str(video["avg_frame_rate"]); sample_rate,channels=int(audio["sample_rate"]),int(audio["channels"])
        except (KeyError,TypeError,ValueError) as error: raise ProviderValidationError("preview requires complete video and audio streams") from error
        fps=parse_frame_rate(rate); expected_video=SUPPORTED_VIDEO_ENCODERS[self.config.video_codec]; expected_audio=SUPPORTED_AUDIO_ENCODERS[self.config.audio_codec]
        valid = (
            math.isfinite(expected)
            and math.isfinite(duration)
            and duration > 0
            and abs(duration - expected) <= self.config.sync_tolerance_seconds
            and (width, height) == (self.config.width, self.config.height)
            and abs(fps - self.config.fps) <= self.config.fps_tolerance
            and video.get("codec_name") == expected_video
            and audio.get("codec_name") == expected_audio
            and sample_rate > 0
            and channels > 0
        )
        if not valid:
            raise ProviderValidationError(
                "preview stream metadata is invalid "
                f"(duration={duration!r}, expected_duration={expected!r}, "
                f"resolution={width}x{height}, fps={fps!r}, "
                f"video_codec={video.get('codec_name')!r}, audio_codec={audio.get('codec_name')!r}, "
                f"sample_rate={sample_rate!r}, channels={channels!r})"
            )
        return {"duration_seconds":duration,"width":width,"height":height,"frame_rate":rate,"fps":fps,"video_codec":str(video["codec_name"]),"audio_codec":str(audio["codec_name"]),"sample_rate":sample_rate,"channels":channels}
    def render(self,segments:tuple[TimelineSegment,...],narration:Path,captions:Path,output:Path,*,cancellation_requested:Callable[[],bool]|None=None)->dict[str,Any]:
        if not narration.is_file() or not captions.is_file() or narration.stat().st_size==0 or captions.stat().st_size==0: raise ProviderValidationError("preview narration or captions are missing")
        if cancellation_requested and cancellation_requested(): raise PreviewRenderCancelled("cancelled before preview command construction")
        output.parent.mkdir(parents=True,exist_ok=True)
        if shutil.disk_usage(output.parent).free<self.config.minimum_free_bytes: raise RetryableProviderError("insufficient disk space for preview render")
        temporary=output.with_name(f"{output.stem}.part{output.suffix}"); temporary.unlink(missing_ok=True); command=self.command(segments,narration,captions,temporary)
        try:
            if cancellation_requested and cancellation_requested(): raise PreviewRenderCancelled("cancelled before FFmpeg execution")
            # FFmpeg can emit enough diagnostics to fill a PIPE while a long
            # render is being polled.  We classify failures by exit status, so
            # discard the bounded diagnostic stream instead of risking a child
            # blocked on an unread pipe.
            process=self.process_factory(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)
            deadline=time.monotonic()+self.config.timeout_seconds
            while process.poll() is None:
                if cancellation_requested and cancellation_requested():
                    self._stop_process(process, graceful=True)
                    raise PreviewRenderCancelled("cancelled during FFmpeg execution")
                if time.monotonic() >= deadline:
                    self._stop_process(process, graceful=False)
                    raise subprocess.TimeoutExpired(command,self.config.timeout_seconds)
                time.sleep(self.poll_seconds)
            if process.returncode: raise RetryableProviderError("FFmpeg preview render failed")
            if cancellation_requested and cancellation_requested(): raise PreviewRenderCancelled("cancelled before preview validation")
            metadata=self.validate(temporary,segments[-1].end_seconds)
            if cancellation_requested and cancellation_requested(): raise PreviewRenderCancelled("cancelled before preview acceptance")
            temporary.replace(output); return {"command":command,"metadata":metadata,"checksum_sha256":checksum(output)}
        except subprocess.TimeoutExpired as error: raise RetryableProviderError("FFmpeg preview render timed out") from error
        except OSError as error: raise ProviderValidationError("FFmpeg executable is unavailable") from error
        finally: temporary.unlink(missing_ok=True)

    @staticmethod
    def _stop_process(process: Any, *, graceful: bool) -> None:
        """Stop and reap a child process without leaving FFmpeg behind."""
        if process.poll() is not None:
            return
        if graceful:
            process.terminate()
            try:
                process.wait(timeout=5)
                return
            except subprocess.TimeoutExpired:
                pass
        process.kill()
        process.wait(timeout=5)
