"""Fast, deterministic FFmpeg comedy polish for short animated clips.

This is an edit-only pipeline: it never invents characters or replaces story content.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


class ComedyEditError(ValueError):
    pass


def build_comedy_filter(aspect_ratio: str = "9:16", intensity: str = "High", punch_times: list[float] | None = None) -> str:
    sizes = {"9:16": (720, 1280), "16:9": (1280, 720), "1:1": (720, 720)}
    if aspect_ratio not in sizes:
        raise ComedyEditError("Aspect ratio must be 9:16, 16:9, or 1:1.")
    if intensity not in {"Medium", "High", "Extreme"}:
        raise ComedyEditError("Intensity must be Medium, High, or Extreme.")
    width, height = sizes[aspect_ratio]
    zoom = {"Medium": "1.07", "High": "1.12", "Extreme": "1.18"}[intensity]
    # A cosine ease gives a quick but continuous zoom pulse instead of
    # the old frame-by-frame 1.0/1.12 toggle that looked jerky.
    base_cycle_frames = 72  # 2.4 seconds: brisk in/out motion at 30 fps
    base_expr = f"1+({zoom}-1)*(0.5-0.5*cos(2*PI*mod(on,{base_cycle_frames})/{base_cycle_frames}))"
    z_expr = base_expr
    # At each detected comedy beat, add a faster 0.6-second smooth punch.
    for punch_time in reversed((punch_times or [])[:20]):
        start = max(0, int(float(punch_time) * 30))
        end = start + 18
        condition = f"between(on,{start},{end})"
        pulse = f"1+({zoom}-1)*(0.5-0.5*cos(2*PI*(on-{start})/18))"
        z_expr = f"if({condition},{pulse},{z_expr})"
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height},setsar=1,"
        f"zoompan=z='{z_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d=1:s={width}x{height}:fps=30,"
        "eq=contrast=1.06:saturation=1.12:brightness=0.015,"
        "unsharp=5:5:0.45:5:5:0.0,format=yuv420p"
    )


def _ffmpeg_path() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


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
) -> str:
    source, output = Path(input_video), Path(output_video)
    if not source.is_file() or source.stat().st_size == 0:
        raise ComedyEditError("Input video is missing or empty.")
    if not 1 <= float(max_duration) <= 20:
        raise ComedyEditError("Choose a clip duration from 1 to 20 seconds.")
    if not 0 <= float(music_volume) <= 0.35:
        raise ComedyEditError("Background music volume must be between 0 and 0.35.")
    if music_file and (not Path(music_file).is_file() or Path(music_file).stat().st_size == 0):
        raise ComedyEditError("Background music file is missing or empty.")
    if subtitle_file and (not Path(subtitle_file).is_file() or Path(subtitle_file).stat().st_size == 0):
        raise ComedyEditError("Subtitle SRT file is missing or empty.")
    video_filter = build_comedy_filter(aspect_ratio, intensity, punch_times=punch_times)
    if subtitle_file:
        escaped = str(Path(subtitle_file).resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
        video_filter += f",subtitles=filename='{escaped}':force_style='FontName=Noto Sans Telugu,FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=55'"
    cmd = [_ffmpeg_path(), "-y", "-i", str(source)]
    if music_file:
        probe = subprocess.run([_ffmpeg_path(), "-hide_banner", "-i", str(source)], capture_output=True, text=True, timeout=30)
        has_original_audio = bool(re.search(r"Stream #\d+:\d+.*Audio:", probe.stderr or ""))
        cmd += ["-stream_loop", "-1", "-i", str(music_file)]
        if has_original_audio:
            graph = (
                f"[0:v]{video_filter}[v];"
                f"[0:a]volume=0.88[original];"
                f"[1:a]volume={float(music_volume):.3f},afade=t=in:st=0:d=0.6[music];"
                "[original][music]amix=inputs=2:duration=first:dropout_transition=1[a]"
            )
        else:
            graph = (
                f"[0:v]{video_filter}[v];"
                f"[1:a]volume={float(music_volume):.3f},afade=t=in:st=0:d=0.6[a]"
            )
        cmd += ["-filter_complex", graph, "-map", "[v]", "-map", "[a]"]
    else:
        cmd += ["-vf", video_filter, "-map", "0:v:0", "-map", "0:a?"]
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
