"""Normalize and stitch generated scene MP4 files into one silent timeline."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


class SceneStitchError(RuntimeError):
    pass


def build_normalize_command(
    ffmpeg: str,
    input_file: str,
    output_file: str,
    *,
    aspect_ratio: str = "9:16",
    fps: int = 24,
) -> list[str]:
    source = Path(input_file)
    target = Path(output_file)
    if not source.is_file() or source.stat().st_size <= 0:
        raise SceneStitchError("సన్నివేశం MP4 కనిపించలేదు లేదా ఖాళీగా ఉంది.")
    if aspect_ratio not in {"9:16", "16:9", "1:1"}:
        raise SceneStitchError("Aspect ratio 9:16, 16:9 లేదా 1:1 మాత్రమే.")
    if fps not in {24, 25, 30}:
        raise SceneStitchError("FPS 24, 25 లేదా 30 మాత్రమే.")
    dimensions = {"9:16": (720, 1280), "16:9": (1280, 720), "1:1": (720, 720)}
    width, height = dimensions[aspect_ratio]
    target.parent.mkdir(parents=True, exist_ok=True)
    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"setsar=1,fps={fps},format=yuv420p"
    )
    return [
        ffmpeg, "-y", "-i", str(source), "-an",
        "-vf", video_filter, "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "23",
        "-movflags", "+faststart", str(target),
    ]


def stitch_scene_videos(
    *,
    scene_files: list[str],
    output_file: str,
    aspect_ratio: str = "9:16",
    fps: int = 24,
    timeout_seconds: int = 900,
) -> Path:
    if not 2 <= len(scene_files) <= 12:
        raise SceneStitchError("2 నుంచి 12 సన్నివేశాల MP4 ఫైళ్లు ఇవ్వండి.")
    if timeout_seconds < 30 or timeout_seconds > 1800:
        raise SceneStitchError("Stitch timeout 30–1800 seconds మధ్య ఉండాలి.")
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise SceneStitchError("FFmpeg runtime అందుబాటులో లేదు.") from exc

    output = Path(output_file).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="macherla_scene_stitch_") as temp:
        work = Path(temp)
        normalized: list[Path] = []
        for index, scene in enumerate(scene_files):
            target = work / f"scene_{index:02d}.mp4"
            command = build_normalize_command(
                ffmpeg, scene, str(target), aspect_ratio=aspect_ratio, fps=fps
            )
            try:
                result = subprocess.run(
                    command, capture_output=True, text=True,
                    timeout=timeout_seconds, check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise SceneStitchError(f"సన్నివేశం {index + 1} normalize చేయడానికి సమయం మించిపోయింది.") from exc
            if result.returncode or not target.is_file() or target.stat().st_size < 1024:
                detail = (result.stderr or result.stdout or "FFmpeg error")[-1200:]
                raise SceneStitchError(f"సన్నివేశం {index + 1} సిద్ధం కాలేదు: {detail}")
            normalized.append(target)

        concat_file = work / "scenes.txt"
        concat_file.write_text(
            "".join("file '" + str(path).replace("'", "'\\''") + "'\\n" for path in normalized),
            encoding="utf-8",
        )
        try:
            result = subprocess.run(
                [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i",
                 str(concat_file), "-c", "copy", "-movflags", "+faststart", str(output)],
                capture_output=True, text=True, timeout=timeout_seconds, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise SceneStitchError("సన్నివేశాలను కలపడానికి సమయం మించిపోయింది.") from exc
        if result.returncode or not output.is_file() or output.stat().st_size < 1024:
            detail = (result.stderr or result.stdout or "FFmpeg error")[-1200:]
            raise SceneStitchError(f"సన్నివేశాల కలయిక విఫలమైంది: {detail}")
    with output.open("rb") as stream:
        if stream.read(12)[4:8] != b"ftyp":
            raise SceneStitchError("తయారైన ఫైల్ MP4 formatలో లేదు.")
    return output
