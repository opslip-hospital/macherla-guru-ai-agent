"""End-to-end scene render orchestration for a configured, persistent GPU worker.

This is intended for a self-hosted/persistent GPU runtime, not a short-lived
ZeroGPU request. It renders each manifest job, stitches the clips, builds the
Telugu dialogue soundtrack, and muxes the final MP4. It never downloads weights.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

try:
    from .ti2v_adapter import TI2VSetupError, run_ti2v_job
    from .scene_stitch import SceneStitchError, stitch_scene_videos
    from .dialogue_audio import DialogueAudioError, build_dialogue_soundtrack
    from .video_mux import VideoMuxError, mux_dialogue_into_video
except ImportError:  # Hugging Face Space working-directory imports
    from ti2v_adapter import TI2VSetupError, run_ti2v_job
    from scene_stitch import SceneStitchError, stitch_scene_videos
    from dialogue_audio import DialogueAudioError, build_dialogue_soundtrack
    from video_mux import VideoMuxError, mux_dialogue_into_video


class StoryRenderPipelineError(RuntimeError):
    """Raised when a scene or final assembly step fails."""


def validate_render_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise StoryRenderPipelineError("Render manifest schema_version 1 కావాలి.")
    jobs = manifest.get("render_jobs")
    if not isinstance(jobs, list) or not 1 <= len(jobs) <= 12:
        raise StoryRenderPipelineError("1 నుంచి 12 scene render jobs అవసరం.")
    if manifest.get("aspect_ratio") not in {"9:16", "16:9"}:
        raise StoryRenderPipelineError("Aspect ratio 9:16 లేదా 16:9 కావాలి.")
    if manifest.get("fps") not in {24, 25, 30}:
        raise StoryRenderPipelineError("FPS 24, 25 లేదా 30 మాత్రమే.")
    previous_end = -1.0
    for index, job in enumerate(jobs, start=1):
        if not isinstance(job, dict):
            raise StoryRenderPipelineError(f"సీన్ {index} job object కావాలి.")
        try:
            start, end = float(job["start_seconds"]), float(job["end_seconds"])
            frames = int(job["frame_num"])
        except (KeyError, TypeError, ValueError) as exc:
            raise StoryRenderPipelineError(f"సీన్ {index} timing/frame వివరాలు తప్పుగా ఉన్నాయి.") from exc
        if start < previous_end or end <= start:
            raise StoryRenderPipelineError(f"సీన్ {index} timing క్రమం తప్పుగా ఉంది.")
        if frames < 5 or (frames - 1) % 4:
            raise StoryRenderPipelineError(f"సీన్ {index} frame_num 4n+1 రూపంలో ఉండాలి.")
        if not str(job.get("prompt_en", "")).strip():
            raise StoryRenderPipelineError(f"సీన్ {index} visual prompt ఖాళీగా ఉంది.")
        previous_end = end
    return jobs


def render_story_to_mp4(
    manifest: dict[str, Any],
    *,
    wan_repo: str,
    checkpoint_dir: str,
    output_dir: str,
    reference_image: str | None = None,
    render_timeout_seconds: int = 2700,
) -> Path:
    """Render all scenes sequentially and return the assembled MP4 path.

    Requires a persistent compatible GPU. Each generated shot is silent;
    dialogue is synthesized separately and muxed after scene assembly.
    """
    jobs = validate_render_manifest(manifest)
    repo = Path(wan_repo).expanduser().resolve()
    checkpoint = Path(checkpoint_dir).expanduser().resolve()
    if not repo.is_dir() or not (repo / "generate.py").is_file():
        raise StoryRenderPipelineError("WAN_REPO_PATHలో Wan2.2 generate.py కనిపించలేదు.")
    if not checkpoint.is_dir():
        raise StoryRenderPipelineError("Wan2.2 TI2V checkpoint directory కనిపించలేదు.")
    reference = None
    if reference_image:
        reference = Path(reference_image).expanduser().resolve()
        if not reference.is_file() or reference.stat().st_size == 0:
            raise StoryRenderPipelineError("Character reference image కనిపించలేదు లేదా ఖాళీగా ఉంది.")

    work = Path(output_dir).expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)
    clips: list[str] = []
    try:
        for index, job in enumerate(jobs, start=1):
            filename = Path(str(job.get("output_filename", f"scene_{index:02d}.mp4"))).name
            if not filename.lower().endswith(".mp4"):
                raise StoryRenderPipelineError(f"సీన్ {index} output filename MP4 కావాలి.")
            target = work / f"render_{index:02d}_{filename}"
            rendered = run_ti2v_job(
                wan_repo=str(repo),
                checkpoint_dir=str(checkpoint),
                prompt=str(job["prompt_en"]),
                output_file=str(target),
                aspect_ratio=str(job.get("aspect_ratio", manifest["aspect_ratio"])),
                frame_num=int(job["frame_num"]),
                reference_image=str(reference) if reference else None,
                timeout_seconds=render_timeout_seconds,
            )
            clips.append(str(rendered))

        if len(clips) == 1:
            silent_video = work / "story_silent.mp4"
            shutil.copy2(clips[0], silent_video)
        else:
            silent_video = stitch_scene_videos(
                scene_files=clips,
                output_file=str(work / "story_silent.mp4"),
                aspect_ratio=str(manifest["aspect_ratio"]),
                fps=int(manifest["fps"]),
                timeout_seconds=1800,
            )

        dialogue_script = str(manifest.get("dialogue_script", "")).strip()
        if not dialogue_script:
            final_video = work / "macherla_guru_story_final.mp4"
            shutil.copy2(silent_video, final_video)
            return final_video

        soundtrack = build_dialogue_soundtrack(
            script=dialogue_script,
            output_file=str(work / "telugu_dialogue_track.wav"),
            gap_ms=450,
            rate="+0%",
        )
        final_video = mux_dialogue_into_video(
            video_file=str(silent_video),
            audio_file=str(soundtrack),
            output_file=str(work / "macherla_guru_story_final.mp4"),
            keep_original_audio=False,
            original_volume=0.18,
            dialogue_volume=1.0,
            timeout_seconds=300,
        )
        return Path(final_video)
    except (TI2VSetupError, SceneStitchError, DialogueAudioError, VideoMuxError) as exc:
        raise StoryRenderPipelineError(str(exc)) from exc


def load_manifest_file(path: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StoryRenderPipelineError("Render manifest JSON ఫైల్ చదవలేకపోయాం.") from exc
    if not isinstance(value, dict):
        raise StoryRenderPipelineError("Render manifest JSON object కావాలి.")
    validate_render_manifest(value)
    return value
