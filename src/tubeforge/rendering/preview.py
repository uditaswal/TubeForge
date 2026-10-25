"""Deterministic FFmpeg preview rendering with validated argument arrays."""
from __future__ import annotations
import hashlib, json, math, shutil, subprocess, tempfile, time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from tubeforge.core.config import RenderProfile, SUPPORTED_AUDIO_ENCODERS, SUPPORTED_VIDEO_ENCODERS
from tubeforge.core.errors import ProviderValidationError, RetryableProviderError
from tubeforge.domain.contracts import ContentPackage
from tubeforge.pipeline.alignment import WordTiming
from tubeforge.pipeline.scene_contracts import ScriptBoundSceneContract
from tubeforge.rendering.animated_card import ANIMATED_CARD_VERSION, AnimatedCardScene, prepare_card_visual_command, resolve_card_cues
from tubeforge.rendering.animated_teaching import ANIMATED_TEACHING_PANELS_FIRST_VERSION, ANIMATED_TEACHING_VERSION, AnimatedTeachingScene, prepare_teaching_visual_command, resolve_teaching_cues
from tubeforge.rendering.animated_terminal import ANIMATED_TERMINAL_HEADING_VERSION, ANIMATED_TERMINAL_LONG_VERSION, ANIMATED_TERMINAL_THIRD_VERSION, ANIMATED_TERMINAL_VERSION, AnimatedTerminalScene, prepare_terminal_visual_command, resolve_cues
from tubeforge.rendering.loudness import LOUDNESS_VERSION, MUSIC_LOUDNESS_VERSION, TIGHTER_CEILING, LoudnessCancelled, analyze as analyze_loudness, analyze_mix as analyze_music_mix, second_pass_filter, validate_encoded

class PreviewRenderCancelled(RuntimeError): pass
RENDERER_TEMPLATE_VERSION = "m15-authored-ass-caption-style-v1"

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
    animation: AnimatedTerminalScene | AnimatedCardScene | AnimatedTeachingScene | None = None
    animation_words: tuple[WordTiming, ...] = ()
    @property
    def duration_seconds(self)->float: return self.end_seconds-self.start_seconds


def pace_segments(segments: tuple[TimelineSegment, ...], maximum_seconds: float) -> tuple[TimelineSegment, ...]:
    """Split long visual holds into deterministic camera cuts for short-form pacing."""
    output: list[TimelineSegment] = []
    for segment in segments:
        if segment.animation is not None:
            output.append(segment)
            continue
        slices = max(1, math.ceil(segment.duration_seconds / maximum_seconds))
        duration = segment.duration_seconds / slices
        for index in range(slices):
            start = segment.start_seconds + index * duration
            end = segment.end_seconds if index == slices - 1 else start + duration
            output.append(TimelineSegment(segment.scene_id, segment.section_id, start, end, segment.asset_path, segment.asset_checksum, segment.media_type))
    return tuple(output)


def maximum_static_hold(segments: tuple[TimelineSegment, ...], maximum_seconds: float) -> float:
    """Only still/video cuts are holds; aligned reveal scenes change on speech."""
    paced = pace_segments(segments, maximum_seconds)
    return max((segment.duration_seconds for segment in paced if segment.animation is None), default=0.0)


def _gap_frames(segments: tuple[TimelineSegment, ...], index: int, fps: int) -> int:
    """Return frames needed to keep this scene on the absolute narration clock."""
    if index + 1 >= len(segments):
        return 0
    current_end = round(segments[index].end_seconds * fps)
    next_start = round(segments[index + 1].start_seconds * fps)
    return max(0, next_start - current_end)

def build_timeline(package: ContentPackage, timing_map: dict[str,object], assets: dict[str,object], *, tolerance:float, scene_contract:ScriptBoundSceneContract|None=None)->tuple[TimelineSegment,...]:
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
    contract_rows = {row.scene_id: row for row in scene_contract.scenes} if scene_contract is not None else {}
    aligned_words = tuple(WordTiming(**value) for value in timing_map.get("words", [])) if contract_rows else ()
    for step_index, section in enumerate(package.script_sections, 1):
        group=by_section.get(section.section_id); asset=assets.get(section.scene_id)
        if not group or not isinstance(asset,dict): raise ProviderValidationError("every narrated scene requires an accepted licensed asset")
        try:
            path=Path(str(asset["path"])); validation=asset["validation"]; candidate=asset["candidate"]; asset_checksum=str(asset["checksum_sha256"]); media_type=str(validation["media_type"])
        except (KeyError,TypeError) as error: raise ProviderValidationError("accepted asset manifest is invalid") from error
        if not isinstance(validation,dict) or not isinstance(candidate,dict) or media_type not in {"image","video"}: raise ProviderValidationError("asset is not a validated image or video")
        if not candidate.get("license_name") or candidate.get("editorial_only") or candidate.get("review_required") or candidate.get("attribution_required"): raise ProviderValidationError("asset is unlicensed or unapproved")
        if not path.is_file() or path.stat().st_size==0 or checksum(path)!=asset_checksum or validation.get("checksum_sha256")!=asset_checksum: raise ProviderValidationError("accepted asset is missing or checksum mismatched")
        start_seconds, end_seconds = float(group[0]["start_seconds"]), float(group[-1]["end_seconds"])
        animation = None
        row = contract_rows.get(section.scene_id)
        if row is not None and row.terminal_cues is not None:
            cue = row.terminal_cues
            animation = AnimatedTerminalScene(
                scene_id=section.scene_id, heading=row.heading, command=row.command or "",
                output_label="EXPLAINED STATE", output_line=row.display_elements[0],
                secondary_line=row.display_elements[1], source_ids=row.source_ids,
                section_id=section.section_id, scene_start_seconds=start_seconds,
                duration_seconds=end_seconds-start_seconds,
                command_start_word_index=cue.command_start_word_index,
                command_end_word_index=cue.command_end_word_index,
                output_word_index=cue.output_word_index,
                secondary_word_index=cue.secondary_word_index,
                step_number=step_index, step_count=len(package.script_sections),
                third_line=row.display_elements[2] if cue.third_word_index is not None else None,
                third_word_index=cue.third_word_index,
            )
            try:
                resolve_cues(animation, aligned_words)
            except ValueError as error:
                raise ProviderValidationError(str(error)) from error
        elif row is not None and row.card_cues is not None:
            cue = row.card_cues
            if package.request.aspect_ratio == "9:16" and ((cue.kind.value == "hook" and step_index != 1) or (cue.kind.value == "close" and step_index != len(package.script_sections))):
                raise ProviderValidationError("hook/close motion must match its narration position")
            animation = AnimatedCardScene(
                scene_id=section.scene_id, section_id=section.section_id, kind=cue.kind,
                heading=row.heading, elements=tuple(row.display_elements), source_ids=row.source_ids,
                scene_start_seconds=start_seconds, duration_seconds=end_seconds-start_seconds,
                first_word_index=cue.first_word_index, second_word_index=cue.second_word_index,
                third_word_index=cue.third_word_index,
                step_number=step_index, step_count=len(package.script_sections),
            )
            try:
                resolve_card_cues(animation, aligned_words)
            except ValueError as error:
                raise ProviderValidationError(str(error)) from error
        elif row is not None and row.teaching_cues is not None:
            cue = row.teaching_cues
            animation = AnimatedTeachingScene(
                scene_id=section.scene_id, section_id=section.section_id, layout=row.layout,
                heading=row.heading, elements=tuple(row.display_elements), source_ids=row.source_ids,
                scene_start_seconds=start_seconds, duration_seconds=end_seconds-start_seconds,
                first_word_index=cue.first_word_index, second_word_index=cue.second_word_index,
                third_word_index=cue.third_word_index,
                step_number=step_index, step_count=len(package.script_sections),
                comparison_panels_first=cue.comparison_panels_first,
            )
            try:
                resolve_teaching_cues(animation, aligned_words)
            except ValueError as error:
                raise ProviderValidationError(str(error)) from error
        output.append(TimelineSegment(section.scene_id,section.section_id,start_seconds,end_seconds,path,asset_checksum,media_type,animation,aligned_words if animation else ()))
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
        paced = pace_segments(segments, self.config.scene_max_duration_seconds)
        settings = self.config.model_dump(mode="json")
        if not self.config.audio_normalization_enabled:
            settings.pop("audio_normalization_enabled")
        value={"renderer":self.config.renderer_version,"template_version":self.template_version,"settings":settings,"narration":checksum(narration),"captions":checksum(captions),"segments":[(s.scene_id,s.section_id,s.start_seconds,s.end_seconds,s.asset_checksum,s.media_type,self._animation_data(s) if s.animation else None,self._animation_cues(s) if s.animation else None) for s in paced],"animation_version":ANIMATED_TERMINAL_VERSION if any(isinstance(s.animation,AnimatedTerminalScene) for s in paced) else None,"transition":"paced-cut","motion_variants":[self.motion_variant(index) for index, segment in enumerate(paced) if segment.media_type == "image" and segment.animation is None], "approval_identity": approval_identity}
        if self.config.audio_normalization_enabled:
            value["loudness_version"] = LOUDNESS_VERSION
        if any(isinstance(s.animation, AnimatedCardScene) for s in paced):
            value["card_animation_version"] = ANIMATED_CARD_VERSION
        if any(isinstance(s.animation, AnimatedTeachingScene) for s in paced):
            value["teaching_animation_version"] = ANIMATED_TEACHING_VERSION
        if any(isinstance(s.animation, AnimatedTeachingScene) and s.animation.comparison_panels_first for s in paced):
            value["teaching_panels_first_version"] = ANIMATED_TEACHING_PANELS_FIRST_VERSION
        if any(isinstance(s.animation, AnimatedTerminalScene) and len(s.animation.command) > 38 for s in paced):
            value["long_terminal_animation_version"] = ANIMATED_TERMINAL_LONG_VERSION
        if any(isinstance(s.animation, AnimatedTerminalScene) and s.animation.third_line is not None for s in paced):
            value["third_terminal_animation_version"] = ANIMATED_TERMINAL_THIRD_VERSION
        if any(isinstance(s.animation, AnimatedTerminalScene) and len(s.animation.heading) > 16 for s in paced):
            value["wrapped_terminal_heading_version"] = ANIMATED_TERMINAL_HEADING_VERSION
        return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()

    @staticmethod
    def _animation_data(segment: TimelineSegment) -> dict[str, object]:
        if segment.animation is None:
            raise ValueError("animated scene data is missing")
        value = asdict(segment.animation)
        if isinstance(segment.animation, AnimatedTerminalScene) and segment.animation.third_line is None:
            value.pop("third_line")
            value.pop("third_word_index")
        if isinstance(segment.animation, AnimatedTeachingScene) and not segment.animation.comparison_panels_first:
            value.pop("comparison_panels_first")
        return value

    @staticmethod
    def _animation_cues(segment: TimelineSegment) -> dict[str, float] | tuple[float, float, float]:
        if isinstance(segment.animation, AnimatedTerminalScene):
            return resolve_cues(segment.animation, segment.animation_words)
        if isinstance(segment.animation, AnimatedCardScene):
            return resolve_card_cues(segment.animation, segment.animation_words)
        if isinstance(segment.animation, AnimatedTeachingScene):
            return resolve_teaching_cues(segment.animation, segment.animation_words)
        raise ValueError("animated scene data is missing")
    def command(self,segments:tuple[TimelineSegment,...],narration:Path,captions:Path,output:Path,*,music:Path|None=None,audio_filter:str|None=None)->list[str]:
        if any(segment.animation is not None for segment in segments):
            raise ProviderValidationError("animated terminal scenes require bounded rendering")
        segments = pace_segments(segments, self.config.scene_max_duration_seconds)
        command=[self.ffmpeg,"-nostdin","-y","-v","error","-threads",str(self.config.threads),"-filter_complex_threads",str(self.config.threads)]; filters=[]
        for i,scene in enumerate(segments):
            gap_frames = _gap_frames(segments, i, self.config.fps)
            duration=f"{scene.duration_seconds + gap_frames / self.config.fps:.6f}"
            # Input codec options apply only to the following input. PNG frame
            # decoders otherwise create an automatic pool for every paced cut.
            command.extend(("-threads",str(self.config.threads)))
            command.extend(("-loop","1","-t",duration,"-i",str(scene.asset_path)) if scene.media_type=="image" else ("-stream_loop","-1","-t",duration,"-i",str(scene.asset_path)))
            filters.append(self._scene_filter(i, scene, duration))
        command.extend(("-i",str(narration)))
        narration_index = len(segments)
        if music is not None:
            command.extend(("-stream_loop","-1","-i",str(music)))
        labels="".join(f"[v{i}]" for i in range(len(segments))); caption=str(captions.resolve()).replace("\\","/").replace(":","\\:").replace("'","\\'"); style=f"FontSize={self.config.caption_font_size},Alignment=2,MarginV={self.config.caption_margin_vertical},MarginL={self.config.caption_margin_horizontal},MarginR={self.config.caption_margin_horizontal},Outline=2,Shadow=1"
        if captions.suffix.lower() == ".ass":
            style = ""
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
            f"[base]tpad=stop_mode=clone:stop_duration=10,subtitles='{caption}':force_style='{style}'[outv]",
        ]
        if music is None:
            filters.append(f"[{narration_index}:a]{audio_filter + ',' if audio_filter else ''}apad=pad_dur=10[outa]")
        else:
            music_index = narration_index + 1
            filters.extend((
                f"[{narration_index}:a]asplit=2[narration_mix][speech_key]",
                f"[{music_index}:a]volume=0.16[music_quiet]",
                "[music_quiet][speech_key]sidechaincompress=threshold=0.015:ratio=10:attack=20:release=350[ducked_music]",
                f"[narration_mix][ducked_music]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95,{audio_filter + ',' if audio_filter else ''}apad=pad_dur=10[outa]",
            ))
        return [*command,"-filter_complex",";".join(filters),"-map","[outv]","-map","[outa]","-c:v",self.config.video_codec,*self._quality_args(),"-threads",str(self.config.threads),"-pix_fmt",self.config.pixel_format,"-r",str(self.config.fps),"-c:a",self.config.audio_codec,"-b:a",self.config.audio_bitrate,"-ar",str(self.config.audio_sample_rate),"-t",f"{segments[-1].end_seconds:.6f}","-movflags","+faststart",str(output)]

    def _quality_args(self, *, intermediate: bool = False) -> list[str]:
        if self.config.video_codec != "libx264":
            return []
        # Bounded rendering transcodes each scene twice. Give the temporary
        # scene encode more headroom so small terminal glyphs survive the final pass.
        crf = max(0, self.config.video_crf - 4) if intermediate else self.config.video_crf
        return ["-crf", str(crf)]

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
        frames = max(1, math.ceil(float(duration) * self.config.fps))
        # Four stable variants change direction and speed without disturbing
        # the narration clock. Short paced cuts remain intentionally crisp;
        # dissolves between sub-three-second scenes made caption reading feel
        # softer and reduced the useful time on each composition.
        variant = index % 4
        ceiling = 1 + (self.config.image_motion_zoom - 1) * (1 if variant in {0, 2} else 0.62)
        zoom = f"min(zoom+({ceiling:.4f}-1)/{frames},{ceiling:.4f})"
        if variant == 0:
            x, y = f"(iw-iw/zoom)*on/{frames}", "ih/2-ih/zoom/2"
        elif variant == 1:
            x, y = f"(iw-iw/zoom)*(1-on/{frames})", "ih/2-ih/zoom/2"
        elif variant == 2:
            x, y = "iw/2-iw/zoom/2", f"(ih-ih/zoom)*on/{frames}"
        else:
            x, y = "iw/2-iw/zoom/2", f"(ih-ih/zoom)*(1-on/{frames})"
        overscan_width = round(self.config.width * self.config.image_motion_overscan)
        overscan_height = round(self.config.height * self.config.image_motion_overscan)
        return (
            f"[{index}:v]scale={overscan_width}:{overscan_height}:"
            f"force_original_aspect_ratio=increase,crop={overscan_width}:{overscan_height},"
            f"zoompan=z='{zoom}':x='{x}':y='{y}':d={frames}:"
            f"s={self.config.width}x{self.config.height}:fps={self.config.fps},"
            f"trim=duration={duration},setpts=PTS-STARTPTS[v{index}]"
        )

    @staticmethod
    def motion_variant(index: int) -> str:
        return ("pan-right-fast", "pan-left-gentle", "pan-down-fast", "pan-up-gentle")[index % 4]
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
            and sample_rate == self.config.audio_sample_rate
            and channels > 0
        )
        if not valid:
            raise ProviderValidationError(
                "preview stream metadata is invalid "
                f"(duration={duration!r}, expected_duration={expected!r}, "
                f"resolution={width}x{height}, fps={fps!r}, "
                f"video_codec={video.get('codec_name')!r}, audio_codec={audio.get('codec_name')!r}, "
                f"sample_rate={sample_rate!r}, expected_sample_rate={self.config.audio_sample_rate}, channels={channels!r})"
            )
        return {"duration_seconds":duration,"width":width,"height":height,"frame_rate":rate,"fps":fps,"video_codec":str(video["codec_name"]),"audio_codec":str(audio["codec_name"]),"sample_rate":sample_rate,"channels":channels}
    def render(self,segments:tuple[TimelineSegment,...],narration:Path,captions:Path,output:Path,*,music:Path|None=None,cancellation_requested:Callable[[],bool]|None=None)->dict[str,Any]:
        if not narration.is_file() or not captions.is_file() or narration.stat().st_size==0 or captions.stat().st_size==0: raise ProviderValidationError("preview narration or captions are missing")
        if cancellation_requested and cancellation_requested(): raise PreviewRenderCancelled("cancelled before preview command construction")
        output.parent.mkdir(parents=True,exist_ok=True)
        if shutil.disk_usage(output.parent).free<self.config.minimum_free_bytes: raise RetryableProviderError("insufficient disk space for preview render")
        if music is not None and (not music.is_file() or music.stat().st_size == 0): raise ProviderValidationError("selected music is missing or empty")
        temporary=output.with_name(f"{output.stem}.part{output.suffix}"); temporary.unlink(missing_ok=True)
        deadline=time.monotonic()+self.config.timeout_seconds
        try:
            audio_filter = None
            audio_loudness = None
            if self.config.audio_normalization_enabled:
                before = (
                    analyze_loudness(narration, ffmpeg=self.ffmpeg, deadline=deadline, cancelled=cancellation_requested, poll_seconds=self.poll_seconds)
                    if music is None else
                    analyze_music_mix(narration, music, duration=segments[-1].end_seconds, ffmpeg=self.ffmpeg, deadline=deadline, cancelled=cancellation_requested, poll_seconds=self.poll_seconds)
                )
                audio_filter = second_pass_filter(before)
            bounded = self.config.bounded_memory or any(segment.animation is not None for segment in segments)
            for ceiling in ((None,) if audio_filter is None else (None, TIGHTER_CEILING)):
                if ceiling is not None:
                    # AAC encoding overshot the limiter past the true-peak gate: re-encode once with more headroom instead of failing the job.
                    audio_filter = second_pass_filter(before, ceiling=ceiling)
                if bounded:
                    command=self._render_bounded(segments,narration,captions,temporary,music,cancellation_requested,deadline,audio_filter)
                else:
                    command=self.command(segments,narration,captions,temporary,music=music,audio_filter=audio_filter)
                    self._run_command(command,cancellation_requested,deadline)
                if cancellation_requested and cancellation_requested(): raise PreviewRenderCancelled("cancelled before preview validation")
                metadata=self.validate(temporary,segments[-1].end_seconds)
                if not self.config.audio_normalization_enabled: break
                after = analyze_loudness(temporary, ffmpeg=self.ffmpeg, deadline=deadline, cancelled=cancellation_requested, poll_seconds=self.poll_seconds)
                try:
                    validate_encoded(after)
                except ProviderValidationError:
                    if ceiling is not None: raise
                    continue
                audio_loudness = {"version": MUSIC_LOUDNESS_VERSION if music is not None else LOUDNESS_VERSION, "before": before, "encoded": after}
                if ceiling is not None: audio_loudness["limiter_ceiling"] = ceiling
                metadata["audio_loudness"] = audio_loudness
                break
            if cancellation_requested and cancellation_requested(): raise PreviewRenderCancelled("cancelled before preview acceptance")
            temporary.replace(output); return {"command":command,"metadata":metadata,"checksum_sha256":checksum(output),"render_strategy":"bounded-segments" if bounded else "single-graph"}
        except subprocess.TimeoutExpired as error: raise RetryableProviderError("FFmpeg preview render timed out") from error
        except LoudnessCancelled as error: raise PreviewRenderCancelled(str(error)) from error
        except OSError as error: raise ProviderValidationError("FFmpeg executable is unavailable") from error
        finally: temporary.unlink(missing_ok=True)

    def _run_command(self,command:list[str],cancellation_requested:Callable[[],bool]|None,deadline:float)->None:
        if cancellation_requested and cancellation_requested(): raise PreviewRenderCancelled("cancelled before FFmpeg execution")
        # A temporary file captures bounded diagnostics without risking an
        # unread-pipe deadlock on large FFmpeg errors. Include only the tail in
        # the durable failure reason so failed render jobs can be diagnosed.
        with tempfile.TemporaryFile() as stderr_log:
            process=self.process_factory(command,stdout=subprocess.DEVNULL,stderr=stderr_log,shell=False)
            while process.poll() is None:
                if cancellation_requested and cancellation_requested():
                    self._stop_process(process,graceful=True)
                    raise PreviewRenderCancelled("cancelled during FFmpeg execution")
                if time.monotonic()>=deadline:
                    self._stop_process(process,graceful=False)
                    raise subprocess.TimeoutExpired(command,self.config.timeout_seconds)
                time.sleep(self.poll_seconds)
            if process.returncode:
                stderr_log.flush()
                stderr_log.seek(0, 2)
                size = stderr_log.tell()
                stderr_log.seek(max(0, size - 8_192))
                details = stderr_log.read().decode("utf-8", errors="replace").strip()
                tail = "\n".join(details.splitlines()[-12:])
                reason = f"FFmpeg preview render failed: {tail}" if tail else "FFmpeg preview render failed"
                raise RetryableProviderError(reason)

    def _render_bounded(self,segments:tuple[TimelineSegment,...],narration:Path,captions:Path,output:Path,music:Path|None,cancellation_requested:Callable[[],bool]|None,deadline:float,audio_filter:str|None=None)->list[str]:
        """Encode one paced scene at a time, then burn captions over their concat.

        The original graph held every 1080x1920 decoder and zoompan buffer in
        memory simultaneously. Sequential scene files cap the live filter
        graph at one scene while preserving the same scene order and motion.
        All intermediates live beside the atomic output and are removed on
        success, failure or cancellation.
        """
        paced=pace_segments(segments,self.config.scene_max_duration_seconds)
        with tempfile.TemporaryDirectory(prefix=f"{output.stem}.segments-",dir=output.parent) as directory:
            workspace=Path(directory)
            clips=[]
            for index,scene in enumerate(paced):
                if cancellation_requested and cancellation_requested(): raise PreviewRenderCancelled("cancelled between FFmpeg segments")
                frame_count=round(scene.end_seconds*self.config.fps)-round(scene.start_seconds*self.config.fps)
                gap_frames = _gap_frames(paced, index, self.config.fps)
                if frame_count<=0: raise ProviderValidationError("paced scene has no output frames")
                clip=workspace/f"segment-{index:04d}.mp4"
                if scene.animation is not None:
                    portrait = self.config.width * 16 == self.config.height * 9
                    landscape = abs(self.config.width / self.config.height - 16 / 9) <= 0.02
                    supported_shape = portrait or (landscape and not isinstance(scene.animation, AnimatedTerminalScene))
                    if not supported_shape or self.config.fps != 30 or self.config.video_codec != "libx264":
                        raise ProviderValidationError("animated scene requires a supported H.264/30fps render profile")
                    try:
                        if isinstance(scene.animation, AnimatedTerminalScene):
                            command = prepare_terminal_visual_command(scene.animation, scene.animation_words, clip, workspace/f"terminal-{index:04d}", ffmpeg=self.ffmpeg, threads=self.config.threads, crf=max(0,self.config.video_crf-4), width=self.config.width, height=self.config.height, fps=self.config.fps, tail_pad_frames=gap_frames)
                        elif isinstance(scene.animation, AnimatedCardScene):
                            command = prepare_card_visual_command(scene.animation, scene.animation_words, clip, workspace/f"card-{index:04d}", ffmpeg=self.ffmpeg, threads=self.config.threads, crf=max(0,self.config.video_crf-4), width=self.config.width, height=self.config.height, fps=self.config.fps, tail_pad_frames=gap_frames)
                        elif isinstance(scene.animation, AnimatedTeachingScene):
                            command = prepare_teaching_visual_command(scene.animation, scene.animation_words, clip, workspace/f"teaching-{index:04d}", ffmpeg=self.ffmpeg, threads=self.config.threads, crf=max(0,self.config.video_crf-4), width=self.config.width, height=self.config.height, fps=self.config.fps, tail_pad_frames=gap_frames)
                        else:
                            raise ValueError("animated scene data is missing")
                    except ValueError as error:
                        raise ProviderValidationError(str(error)) from error
                else:
                    command = self._bounded_segment_command(index,scene,frame_count,clip,tail_pad_frames=gap_frames)
                self._run_command(command,cancellation_requested,deadline)
                clips.append(clip)
            concat=workspace/"segments.txt"
            concat.write_text("".join(f"file '{clip.name}'\n" for clip in clips),encoding="utf-8")
            command=self._bounded_finish_command(concat,narration,captions,output,segments[-1].end_seconds,music,audio_filter)
            self._run_command(command,cancellation_requested,deadline)
            return command

    def _bounded_segment_command(self,index:int,scene:TimelineSegment,frame_count:int,output:Path,*,tail_pad_frames:int=0)->list[str]:
        duration=f"{scene.duration_seconds + tail_pad_frames / self.config.fps:.6f}"
        input_args=["-loop","1","-t",duration,"-i",str(scene.asset_path)] if scene.media_type=="image" else ["-stream_loop","-1","-t",duration,"-i",str(scene.asset_path)]
        # Motion variant uses the global cut index, but each FFmpeg process
        # has only one input stream, always numbered zero.
        graph=self._scene_filter(index,scene,duration).replace(f"[{index}:v]","[0:v]",1)
        return [self.ffmpeg,"-nostdin","-y","-v","error","-threads",str(self.config.threads),"-filter_complex_threads",str(self.config.threads),"-threads",str(self.config.threads),*input_args,"-filter_complex",graph,"-map",f"[v{index}]","-an","-c:v",self.config.video_codec,*self._quality_args(intermediate=True),"-threads",str(self.config.threads),"-pix_fmt",self.config.pixel_format,"-r",str(self.config.fps),"-frames:v",str(frame_count+tail_pad_frames),"-movflags","+faststart",str(output)]

    def _bounded_finish_command(self,concat:Path,narration:Path,captions:Path,output:Path,duration:float,music:Path|None,audio_filter:str|None=None)->list[str]:
        caption=str(captions.resolve()).replace("\\","/").replace(":","\\:").replace("'","\\'")
        style=f"FontSize={self.config.caption_font_size},Alignment=2,MarginV={self.config.caption_margin_vertical},MarginL={self.config.caption_margin_horizontal},MarginR={self.config.caption_margin_horizontal},Outline=2,Shadow=1"
        if captions.suffix.lower() == ".ass":
            style = ""
        command=[self.ffmpeg,"-nostdin","-y","-v","error","-threads",str(self.config.threads),"-filter_complex_threads",str(self.config.threads),"-f","concat","-safe","1","-i",str(concat),"-i",str(narration)]
        filters=[f"[0:v]tpad=stop_mode=clone:stop_duration=10,subtitles='{caption}':force_style='{style}'[outv]"]
        if music is None:
            filters.append(f"[1:a]{audio_filter + ',' if audio_filter else ''}apad=pad_dur=10[outa]")
        else:
            command.extend(("-stream_loop","-1","-i",str(music)))
            filters.extend(("[1:a]asplit=2[narration_mix][speech_key]","[2:a]volume=0.16[music_quiet]","[music_quiet][speech_key]sidechaincompress=threshold=0.015:ratio=10:attack=20:release=350[ducked_music]",f"[narration_mix][ducked_music]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95,{audio_filter + ',' if audio_filter else ''}apad=pad_dur=10[outa]"))
        return [*command,"-filter_complex",";".join(filters),"-map","[outv]","-map","[outa]","-c:v",self.config.video_codec,*self._quality_args(),"-threads",str(self.config.threads),"-pix_fmt",self.config.pixel_format,"-r",str(self.config.fps),"-c:a",self.config.audio_codec,"-b:a",self.config.audio_bitrate,"-ar",str(self.config.audio_sample_rate),"-t",f"{duration:.6f}","-movflags","+faststart",str(output)]

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
