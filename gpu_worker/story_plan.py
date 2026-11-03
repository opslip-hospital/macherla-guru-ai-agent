"""Prompt and validation helpers for Telugu story-driven video planning.

This module does not call an AI model or render video. It prepares a strict
scene-planning prompt and validates a planner's JSON response.
"""
from __future__ import annotations

import json
from typing import Any


def build_story_planner_prompt(
    story_te: str,
    character_name: str = "PJ Babu",
    aspect_ratio: str = "9:16",
    visual_style: str = "సినిమాటిక్ 3D CGI",
    duration_seconds: int = 10,
) -> str:
    """Build a Telugu-only instruction for a future text/LLM scene planner."""
    story = (story_te or "").strip()
    if not story:
        raise ValueError("కథ ఖాళీగా ఉండకూడదు.")
    if aspect_ratio not in {"9:16", "16:9", "1:1"}:
        raise ValueError("అనుమతించిన aspect ratio కాదు.")
    if not 3 <= int(duration_seconds) <= 30:
        raise ValueError("వీడియో నిడివి 3 నుంచి 30 సెకన్ల మధ్య ఉండాలి.")

    spec = {
        "language": "తెలుగు మాత్రమే",
        "character_name": character_name.strip() or "PJ Babu",
        "aspect_ratio": aspect_ratio,
        "visual_style": visual_style.strip() or "సినిమాటిక్ 3D CGI",
        "duration_seconds": int(duration_seconds),
        "story": story,
        "output_schema": {
            "title_te": "string",
            "duration_seconds": "integer",
            "aspect_ratio": "string",
            "scenes": [
                {
                    "scene_number": "integer",
                    "start_seconds": "number",
                    "end_seconds": "number",
                    "visual_prompt_en": "string",
                    "camera": "string",
                    "characters": ["string"],
                    "action_te": "string",
                    "dialogue_te": [
                        {"speaker": "string", "line": "string"}
                    ],
                    "audio_notes_te": "string",
                    "continuity_notes_te": "string",
                }
            ],
            "global_negative_prompt_en": "string",
        },
    }
    return (
        "నీవు తెలుగు షార్ట్ ఫిల్మ్‌లకు సీన్ ప్లానర్‌వి. క్రింది కథ ఆధారంగా "
        "3 నుంచి 6 చిన్న సీన్లుగా విభజించు. ప్రతి సీన్‌లో దృశ్యాన్ని స్పష్టంగా "
        "వివరించు; ఒకే క్యారెక్టర్ ముఖం, దుస్తులు, శరీరాకృతి అన్ని సీన్లలో "
        "స్థిరంగా ఉంచు. డైలాగులు సహజమైన తెలుగులో మాత్రమే ఉండాలి; కొత్త "
        "డైలాగులు కల్పించకుండా కథలోని భావాన్ని కాపాడు. ప్రతి సీన్ సమయాలు "
        "ఒకదానితో ఒకటి ఓవర్‌ల్యాప్ కాకూడదు; మొత్తం నిడివి ఇచ్చిన సమయానికి "
        "సరిపోవాలి. హింసాత్మక దృశ్యాలు కాకుండా కామెడీని ముఖ కవళికలు, "
        "టైమింగ్, రియాక్షన్లతో చూపించు. వీడియోలో కనిపించే అక్షరాలు, "
        "వాటర్‌మార్కులు, అనవసర క్యారెక్టర్లు వద్దు. visual_prompt_en మరియు "
        "global_negative_prompt_en మాత్రమే ఇంగ్లీషులో ఉండాలి; మిగతా అన్ని "
        "ఫీల్డులు తెలుగులో ఉండాలి. సమాధానంగా JSON మాత్రమే ఇవ్వు.\n\n"
        "ప్లానింగ్ ఇన్‌పుట్:\n"
        + json.dumps(spec, ensure_ascii=False, indent=2)
    )


def validate_story_plan(plan: Any, expected_duration: int | None = None) -> list[str]:
    """Return validation errors; an empty list means the JSON shape is usable."""
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["ప్లాన్ JSON object రూపంలో లేదు."]
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 8:
        return ["scenes లో 1 నుంచి 8 సీన్లు ఉండాలి."]

    previous_end = 0.0
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            errors.append(f"సీన్ {index}: object రూపంలో లేదు.")
            continue
        try:
            start = float(scene["start_seconds"])
            end = float(scene["end_seconds"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"సీన్ {index}: start/end సమయాలు సరైనవి కావు.")
            continue
        if start < 0 or end <= start:
            errors.append(f"సీన్ {index}: సమయాల క్రమం తప్పు.")
        if start < previous_end:
            errors.append(f"సీన్ {index}: ముందు సీన్‌తో సమయం ఓవర్‌ల్యాప్ అవుతోంది.")
        previous_end = end
        if not isinstance(scene.get("visual_prompt_en"), str) or not scene["visual_prompt_en"].strip():
            errors.append(f"సీన్ {index}: visual_prompt_en ఖాళీగా ఉంది.")
        if not isinstance(scene.get("dialogue_te", []), list):
            errors.append(f"సీన్ {index}: dialogue_te list కావాలి.")

    if expected_duration is not None and scenes and previous_end > expected_duration + 0.25:
        errors.append("సీన్ల మొత్తం సమయం వీడియో నిడివిని మించిపోయింది.")
    return errors
