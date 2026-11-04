"""Fast, deterministic FFmpeg comedy polish for short animated clips.

This is an edit-only pipeline: it never invents characters or replaces story content.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


class ComedyEditError(ValueError):
    pass


def _track_expr(points: list[dict] | None, axis: str) -> str:
    valid = sorted((p for p in (points or []) if axis in p), key=lambda p: float(p["time"]))[:40]
    if not valid:
        return "0.5"
    expr = f"{float(valid[-1][axis]):.4f}"
    for left, right in reversed(list(zip(valid, valid[1:]))):
        t0, t1 = float(left["time"]), float(right["time"])
        if t1 <= t0:
            continue
        v0, v1 = float(left[axis]), float(right[axis])
        linear = f"({v0:.4f}+({v1-v0:.4f})*(t-{t0:.3f})/{t1-t0:.3f})"
        expr = f"if(lt(t,{t1:.3f}),{linear},{expr})"
    return f"if(lt(t,{float(valid[0]['time']):.3f}),{float(valid[0][axis]):.4f},{expr})"


def build_comedy_filter(aspect_ratio: str = "9:16", intensity: str = "High", punch_times: list[float] | None = None, face_track_points: list[dict] | None = None) -> str:
    sizes = {"9:16": (720, 1280), "16:9": (1280, 720), "1:1": (720, 720)}
    if aspect_ratio not in sizes:
        raise ComedyEditError("Aspect ratio must be 9:16, 16:9, or 1:1.")
    if intensity not in {"Medium", "High", "Extreme"}:
        raise ComedyEditError("Intensity must be Medium, High, or Extreme.")
    width, height = sizes[aspect_ratio]
    zoom = {"Medium": "1.16", "High": "1.23", "Extreme": "1.31"}[intensity]
    punch_zoom = {"Medium": "1.25", "High": "1.34", "Extreme": "1.42"}[intensity]
    # Noticeable 1.8-second push/pull cycle with cosine easing: fast but fluid.
    base_cycle_frames = 54  # 1.8 seconds at 30 fps
    base_expr = f"1+({zoom}-1)*(0.5-0.5*cos(2*PI*mod(on,{base_cycle_frames})/{base_cycle_frames}))"
    z_expr = base_expr
    # Stronger half-second cinematic punch at detected visual beats.
    for punch_time in reversed((punch_times or [])[:20]):
        start = max(0, int(float(punch_time) * 30))
        end = start + 15
        condition = f"between(on,{start},{end})"
        pulse = f"1+({punch_zoom}-1)*(0.5-0.5*cos(2*PI*(on-{start})/15))"
        z_expr = f"if({condition},{pulse},{z_expr})"
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height}:x='(iw-ow)*({_track_expr(face_track_points, 'x') if face_track_points else '0.5'})':y='(ih-oh)*({_track_expr(face_track_points, 'y') if face_track_points else '0.5'})',setsar=1,"
        f"zoompan=z='{z_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d=1:s={width}x{height}:fps=30,"
        "eq=contrast=1.06:saturation=1.12:brightness=0.015,"
        "unsharp=5:5:0.45:5:5:0.0,format=yuv420p"
    )


def _ffmpeg_path() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _probe_duration(path: Path) -> float:
    """Read source duration from FFmpeg metadata for correctly timed end fades."""
    try:
        probe = subprocess.run(
            [_ffmpeg_path(), "-hide_banner", "-i", str(path)],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise ComedyEditError("Reading video metadata timed out. Try a shorter or simpler video.") from exc
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", probe.stderr or "")
    if not match:
        raise ComedyEditError("Could not read the input video's duration.")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _has_audio_stream(path: Path) -> bool:
    """Detect whether the source has audio before applying audio filters."""
    try:
        probe = subprocess.run(
            [_ffmpeg_path(), "-hide_banner", "-i", str(path)],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise ComedyEditError("Checking the original audio track timed out. Try a shorter video.") from exc
    return "Audio:" in (probe.stderr or "") and "Stream #" in (probe.stderr or "")


def _retime_srt(path: Path, speed: float) -> Path:
    """Retiming captions keeps subtitle sync when the video speed changes."""
    if abs(speed - 1.0) < 0.001:
        return path
    content = path.read_text(encoding="utf-8-sig")
    pattern = re.compile(r"(\d{2}:\d{2}:\d{2},\d{3})")

    def convert(match: re.Match[str]) -> str:
        hours, minutes, seconds_ms = match.group(1).split(":")
        seconds, milliseconds = seconds_ms.split(",")
        total_ms = int((int(hours) * 3600 + int(minutes) * 60 + int(seconds)) * 1000 + int(milliseconds))
        adjusted = max(0, round(total_ms / speed))
        h, remainder = divmod(adjusted, 3_600_000)
        m, remainder = divmod(remainder, 60_000)
        s, ms = divmod(remainder, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    # Rewrite the temporary uploaded SRT in place. This avoids FFmpeg/libass
    # path-resolution failures with an adjacent generated subtitle file.
    path.write_text(pattern.sub(convert, content), encoding="utf-8")
    return path


def render_comedy_edit(
    input_video: str,
    output_video: str,
    *,
    aspect_ratio: str = "9:16",
    intensity: str = "High",
    music_file: str | None = None,
    music_volume: float = 0.12,
    subtitle_file: str | None = None,
    max_duration: float = 20.0,
    timeout_seconds: int = 900,
    punch_times: list[float] | None = None,
    playback_speed: float = 1.0,
    face_track_points: list[dict] | None = None,
    sfx_file: str | None = None,
    sfx_volume: float = 0.22,
) -> str:
    source, output = Path(input_video), Path(output_video)
    if not source.is_file() or source.stat().st_size == 0:
        raise ComedyEditError("Input video is missing or empty.")
    if not 1 <= float(max_duration) <= 20:
        raise ComedyEditError("Choose a clip duration from 1 to 20 seconds.")
    if not 0 <= float(music_volume) <= 0.35:
        raise ComedyEditError("Background music volume must be between 0 and 0.35.")
    if not 0.0 <= float(sfx_volume) <= 0.8:
        raise ComedyEditError("Sound-effect volume must be between 0 and 0.8.")
    if not 0.75 <= float(playback_speed) <= 1.25:
        raise ComedyEditError("Playback speed must be between 0.75x and 1.25x.")
    if music_file and (not Path(music_file).is_file() or Path(music_file).stat().st_size == 0):
        raise ComedyEditError("Background music file is missing or empty.")
    if sfx_file and (not Path(sfx_file).is_file() or Path(sfx_file).stat().st_size == 0):
        raise ComedyEditError("Sound-effect file is missing or empty.")
    if subtitle_file and (not Path(subtitle_file).is_file() or Path(subtitle_file).stat().st_size == 0):
        raise ComedyEditError("Subtitle SRT file is missing or empty.")
    source_duration = _probe_duration(source)
    has_original_audio = _has_audio_stream(source)
    output_duration = min(float(max_duration), source_duration / float(playback_speed))
    fade_out_start = max(0.0, output_duration - 0.35)
    audio_fade_out_start = max(0.0, output_duration - 0.25)
    video_filter = build_comedy_filter(aspect_ratio, intensity, punch_times=punch_times, face_track_points=face_track_points)
    video_filter += f",setpts=PTS/{float(playback_speed):.3f},fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out_start:.3f}:d=0.35"
    if subtitle_file:
        subtitle_path = _retime_srt(Path(subtitle_file), float(playback_speed))
        if not subtitle_path.is_file():
            raise ComedyEditError("Retimed subtitle file could not be created.")
        escaped = str(subtitle_path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
        video_filter += f",subtitles={escaped}:force_style='FontName=Noto Sans Telugu,FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=55'"
    cmd = [_ffmpeg_path(), "-y", "-i", str(source)]
    music_index = None
    sfx_index = None
    if music_file:
        music_index = 1
        cmd += ["-stream_loop", "-1", "-i", str(music_file)]
    if sfx_file:
        sfx_index = 1 + int(bool(music_file))
        cmd += ["-i", str(sfx_file)]

    if music_file or sfx_file:
        graph_parts = [f"[0:v]{video_filter}[v]"]
        audio_labels = []
        if has_original_audio:
            graph_parts.append(
                f"[0:a]atempo={float(playback_speed):.3f},volume=0.88,"
                f"afade=t=in:st=0:d=0.15,afade=t=out:st={audio_fade_out_start:.3f}:d=0.25[original]"
            )
            audio_labels.append("[original]")
        elif not music_file and sfx_file:
            graph_parts.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={output_duration:.3f}[silence]")
            audio_labels.append("[silence]")
        if music_file:
            graph_parts.append(
                f"[{music_index}:a]volume={float(music_volume):.3f},"
                f"afade=t=in:st=0:d=0.6,afade=t=out:st={audio_fade_out_start:.3f}:d=0.25[music]"
            )
            audio_labels.append("[music]")
        if sfx_file:
            moments = sorted({max(0.0, float(t)) for t in (punch_times or []) if 0 <= float(t) < output_duration})[:8]
            if not moments:
                moments = [0.5]
            split_labels = "".join(f"[sfxsrc{i}]" for i in range(len(moments)))
            graph_parts.append(f"[{sfx_index}:a]asplit={len(moments)}{split_labels}")
            for i, moment in enumerate(moments):
                delay_ms = int(moment * 1000)
                graph_parts.append(
                    f"[sfxsrc{i}]atrim=duration=1.25,asetpts=PTS-STARTPTS,"
                    f"volume={float(sfx_volume):.3f},adelay={delay_ms}:all=1[sfx{i}]"
                )
                audio_labels.append(f"[sfx{i}]")
        graph_parts.append(
            "".join(audio_labels) + f"amix=inputs={len(audio_labels)}:duration=first:dropout_transition=1[a]"
        )
        cmd += ["-filter_complex", ";".join(graph_parts), "-map", "[v]", "-map", "[a]"]
    elif has_original_audio:
        cmd += [
            "-vf", video_filter, "-map", "0:v:0", "-map", "0:a:0",
            "-af", f"atempo={float(playback_speed):.3f},afade=t=in:st=0:d=0.15,afade=t=out:st={audio_fade_out_start:.3f}:d=0.25",
        ]
    else:
        # Silent source: do not attach an audio filter or optional audio map.
        cmd += ["-vf", video_filter, "-map", "0:v:0"]
    cmd += [
        "-t", str(float(max_duration)), "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "19", "-r", "30", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(output),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        raise ComedyEditError("Render took too long. Try a shorter clip.") from exc
    if result.returncode != 0 or not output.is_file() or output.stat().st_size < 1024:
        detail = (result.stderr or result.stdout or "FFmpeg failed")[-1800:]
        raise ComedyEditError("Video edit failed: " + detail)
    with output.open("rb") as handle:
        if handle.read(12)[4:8] != b"ftyp":
            raise ComedyEditError("Output is not a valid MP4 file.")
    return str(output)
