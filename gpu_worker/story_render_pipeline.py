"""Convert a validated Telugu story plan into deterministic per-scene render jobs.

This module prepares render instructions only. GPU inference is deliberately
kept separate so a plan can be inspected before any expensive generation.
"""
from __future__ import annotations

import json
import math
from typing import Any

try:
    from .story_plan import validate_story_plan
    from .dialogue_audio import parse_dialogue_script
except ImportError:  # Hugging Face Space imports files from its working directory
    from story_plan import validate_story_plan
    from dialogue_audio import parse_dialogue_script


class StoryRenderPlanError(ValueError):
    pass


DEFAULT_VOICE = "Mohan (పురుష వాయిస్)"


def _frames_for_duration(duration_seconds: float, fps: int) -> int:
    """Return a Wan-compatible 4n+1 frame count, rounding duration upward."""
    target = max(5, int(math.ceil(float(duration_seconds) * fps)))
    return max(5, int(math.ceil((target - 1) / 4) * 4 + 1))


def build_story_render_manifest(
    plan: dict[str, Any],
    *,
    aspect_ratio: str | None = None,
    fps: int = 24,
    default_voice: str = DEFAULT_VOICE,
    speaker_voices: dict[str, str] | None = None,
    reference_image_name: str | None = None,
) -> dict[str, Any]:
    """Create an inspectable render manifest and a validated Telugu voice script."""
    errors = validate_story_plan(plan)
    if errors:
        raise StoryRenderPlanError("కథా ప్లాన్ తనిఖీ విఫలమైంది: " + " ".join(errors))
    if fps not in {24, 25, 30}:
        raise StoryRenderPlanError("FPS 24, 25 లేదా 30 మాత్రమే.")
    ratio = aspect_ratio or plan.get("aspect_ratio", "9:16")
    if ratio not in {"9:16", "16:9"}:
        raise StoryRenderPlanError("Wan2.2 TI2V కోసం 9:16 లేదా 16:9 ఎంచుకోండి.")
    if not isinstance(default_voice, str) or not default_voice.strip():
        raise StoryRenderPlanError("డిఫాల్ట్ తెలుగు వాయిస్ ఎంచుకోండి.")

    speaker_voices = speaker_voices or {}
    jobs = []
    dialogue_lines = []
    total_planned_seconds = 0.0
    for index, scene in enumerate(plan["scenes"], start=1):
        start = float(scene["start_seconds"])
        end = float(scene["end_seconds"])
        duration = end - start
        visual = str(scene.get("visual_prompt_en", "")).strip()
        camera = str(scene.get("camera", "")).strip()
        characters = scene.get("characters", [])
        if not isinstance(characters, list):
            raise StoryRenderPlanError(f"సీన్ {index}: characters list కావాలి.")
        prompt_parts = [visual]
        if camera:
            prompt_parts.append("Camera: " + camera)
        if characters:
            prompt_parts.append("Keep these character identities visually consistent: " + ", ".join(str(x) for x in characters))
        continuity = str(scene.get("continuity_notes_te", "")).strip()
        if continuity:
            prompt_parts.append("Continuity direction: " + continuity)
        jobs.append({
            "scene_number": int(scene.get("scene_number", index)),
            "start_seconds": start,
            "end_seconds": end,
            "duration_seconds": round(duration, 3),
            "frame_num": _frames_for_duration(duration, fps),
            "fps": fps,
            "aspect_ratio": ratio,
            "prompt_en": "\n".join(prompt_parts),
            "output_filename": f"scene_{index:02d}.mp4",
            "reference_image_name": reference_image_name,
        })
        total_planned_seconds += duration
        for dialogue in scene.get("dialogue_te", []):
            if not isinstance(dialogue, dict):
                raise StoryRenderPlanError(f"సీన్ {index}: dialogue entry object కావాలి.")
            speaker = str(dialogue.get("speaker", "")).strip()
            line = str(dialogue.get("line", "")).strip()
            if not speaker or not line:
                raise StoryRenderPlanError(f"సీన్ {index}: speaker, line తప్పనిసరి.")
            voice = speaker_voices.get(speaker, default_voice)
            dialogue_lines.append(f"{speaker}|{voice}|{line}")

    if not jobs:
        raise StoryRenderPlanError("కథలో render చేయడానికి సీన్లు లేవు.")
    dialogue_script = "\n".join(dialogue_lines)
    if dialogue_script:
        try:
            parse_dialogue_script(dialogue_script)
        except Exception as exc:
            raise StoryRenderPlanError(f"తెలుగు డైలాగ్ తనిఖీ విఫలమైంది: {exc}") from exc

    return {
        "schema_version": 1,
        "title_te": str(plan.get("title_te", "తెలుగు కథ")),
        "aspect_ratio": ratio,
        "fps": fps,
        "scene_count": len(jobs),
        "planned_scene_seconds": round(total_planned_seconds, 3),
        "render_jobs": jobs,
        "dialogue_script": dialogue_script,
        "audio_required": bool(dialogue_lines),
        "reference_image_name": reference_image_name,
        "render_status": "prepared_not_rendered",
        "notes_te": [
            "ఇది GPU render job manifest మాత్రమే; ఇంకా వీడియో తయారు కాలేదు.",
            "ప్రతి సీన్‌కు ఒకే reference image పంపవచ్చు; అయినా పాత్ర ముఖం 100% ఒకేలా ఉంటుందని హామీ లేదు.",
            "సీన్ల మధ్య continuity, lip-sync, sound effects వేరుగా తనిఖీ చేయాలి.",
        ],
    }


def manifest_json(plan: dict[str, Any], **kwargs: Any) -> str:
    return json.dumps(
        build_story_render_manifest(plan, **kwargs),
        ensure_ascii=False,
        indent=2,
    )
