"""Mux a generated Telugu dialogue soundtrack into a rendered MP4."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


class VideoMuxError(RuntimeError):
    pass


def build_mux_command(
    ffmpeg: str,
    video_file: str,
    audio_file: str,
    output_file: str,
    *,
    keep_original_audio: bool = False,
    original_volume: float = 0.25,
    dialogue_volume: float = 1.0,
    source_has_audio: bool = True,
) -> list[str]:
    video = Path(video_file)
    audio = Path(audio_file)
    output = Path(output_file)
    if not video.is_file() or video.stat().st_size <= 0:
        raise VideoMuxError("రెండర్ చేసిన MP4 ఫైల్ కనిపించలేదు లేదా ఖాళీగా ఉంది.")
    if not audio.is_file() or audio.stat().st_size <= 0:
        raise VideoMuxError("తెలుగు dialogue WAV/MP3 ఫైల్ కనిపించలేదు లేదా ఖాళీగా ఉంది.")
    if not 0 <= original_volume <= 2 or not 0 <= dialogue_volume <= 2:
        raise VideoMuxError("ఆడియో volume 0 నుంచి 2 మధ్య ఉండాలి.")
    if keep_original_audio and not source_has_audio:
        raise VideoMuxError("మూల వీడియోలో audio లేదు. Original audio mix ఎంపికను off చేయండి.")

    output.parent.mkdir(parents=True, exist_ok=True)
    base = [ffmpeg, "-y", "-i", str(video), "-i", str(audio)]
    if keep_original_audio:
        graph = (
            f"[0:a:0]volume={original_volume:.3f}[original];"
            f"[1:a:0]volume={dialogue_volume:.3f}[dialogue];"
            "[original][dialogue]amix=inputs=2:duration=first:"
            "dropout_transition=2[aout]"
        )
        return base + [
            "-filter_complex", graph,
            "-map", "0:v:0", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(output),
        ]

    return base + [
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart", str(output),
    ]


def mux_dialogue_into_video(
    *,
    video_file: str,
    audio_file: str,
    output_file: str,
    keep_original_audio: bool = False,
    original_volume: float = 0.25,
    dialogue_volume: float = 1.0,
    timeout_seconds: int = 180,
) -> Path:
    if timeout_seconds < 10 or timeout_seconds > 600:
        raise VideoMuxError("వీడియో కలిపే సమయం 10–600 సెకన్ల మధ్య ఉండాలి.")
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise VideoMuxError("FFmpeg runtime అందుబాటులో లేదు.") from exc

    video = Path(video_file)
    if not video.is_file() or video.stat().st_size <= 0:
        raise VideoMuxError("రెండర్ చేసిన MP4 ఫైల్ కనిపించలేదు లేదా ఖాళీగా ఉంది.")

    source_has_audio = False
    probe = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(video)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    source_has_audio = bool(re.search(r"Audio:", probe.stderr or "", re.IGNORECASE))
    command = build_mux_command(
        ffmpeg, video_file, audio_file, output_file,
        keep_original_audio=keep_original_audio,
        original_volume=original_volume,
        dialogue_volume=dialogue_volume,
        source_has_audio=source_has_audio,
    )
    try:
        result = subprocess.run(
            command, capture_output=True, text=True,
            timeout=timeout_seconds, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise VideoMuxError("వీడియోతో ఆడియో కలపడానికి సమయం మించిపోయింది.") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "FFmpeg error")[-1600:]
        raise VideoMuxError(f"వీడియో + ఆడియో కలపడం విఫలమైంది: {detail}")

    output = Path(output_file)
    if not output.is_file() or output.stat().st_size < 1024:
        raise VideoMuxError("తయారైన MP4 ఫైల్ సరిగా లేదు.")
    with output.open("rb") as stream:
        if stream.read(12)[4:8] != b"ftyp":
            raise VideoMuxError("తయారైన ఫైల్ MP4 formatలో లేదు.")
    return output
