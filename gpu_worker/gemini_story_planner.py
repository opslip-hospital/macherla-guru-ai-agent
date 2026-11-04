"""Gemini-backed Telugu story planner for the isolated GPU worker.

Requires GEMINI_API_KEY in the worker's secret environment. It only creates a
validated scene plan; video generation remains a separate GPU operation.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

try:
    from .story_plan import build_story_planner_prompt, validate_story_plan
except ImportError:  # Hugging Face Space runs app.py from the worker directory
    from story_plan import build_story_planner_prompt, validate_story_plan


class GeminiPlannerError(RuntimeError):
    pass


def _extract_json(text: str) -> dict[str, Any]:
    clean = (text or "").strip()
    if clean.startswith("```"):
        clean = re.sub(r"^\`\`\`(?:json)?\s*", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\s*\`\`\`$", "", clean)
    try:
        result = json.loads(clean)
    except json.JSONDecodeError as exc:
        raise GeminiPlannerError("Gemini నుంచి సరైన JSON కథా ప్లాన్ రాలేదు.") from exc
    if not isinstance(result, dict):
        raise GeminiPlannerError("Gemini కథా ప్లాన్ object రూపంలో లేదు.")
    return result


def generate_story_plan(
    story_te: str,
    *,
    character_name: str = "PJ Babu",
    aspect_ratio: str = "9:16",
    visual_style: str = "సినిమాటిక్ 3D CGI",
    duration_seconds: int = 10,
    api_key: str | None = None,
    model: str | None = None,
    timeout_seconds: int = 45,
) -> dict[str, Any]:
    """Ask Gemini for a Telugu-first scene plan and validate its timing/schema."""
    key = (api_key or os.environ.get("GEMINI_API_KEY", "")).strip()
    if not key:
        raise GeminiPlannerError(
            "GEMINI_API_KEY లేదు. Hugging Face Space Secretsలో Gemini API key జోడించాలి."
        )
    model_name = (model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")).strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", model_name):
        raise GeminiPlannerError("GEMINI_MODEL పేరు సరైనది కాదు.")
    if not 10 <= timeout_seconds <= 120:
        raise GeminiPlannerError("Gemini timeout 10–120 సెకన్ల మధ్య ఉండాలి.")

    prompt = build_story_planner_prompt(
        story_te,
        character_name=character_name,
        aspect_ratio=aspect_ratio,
        visual_style=visual_style,
        duration_seconds=duration_seconds,
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_name}:generateContent"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.25,
            "responseMimeType": "application/json",
        },
    }
    try:
        response = requests.post(
            url,
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json=payload,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
    except requests.Timeout as exc:
        raise GeminiPlannerError("Gemini కథా ప్లాన్ తయారీకి సమయం మించిపోయింది.") from exc
    except requests.RequestException as exc:
        detail = getattr(getattr(exc, "response", None), "text", "") or str(exc)
        raise GeminiPlannerError(f"Gemini APIలో సమస్య: {detail[-1000:]}") from exc
    except ValueError as exc:
        raise GeminiPlannerError("Gemini API response JSON చదవలేకపోయాం.") from exc

    try:
        text = body["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        block_reason = body.get("promptFeedback", {}).get("blockReason", "తెలియని కారణం")
        raise GeminiPlannerError(f"Gemini కథా ప్లాన్ ఇవ్వలేదు: {block_reason}") from exc

    plan = _extract_json(text)
    errors = validate_story_plan(plan, expected_duration=duration_seconds)
    if errors:
        raise GeminiPlannerError("కథా ప్లాన్ తనిఖీ విఫలమైంది: " + " ".join(errors))
    if plan.get("aspect_ratio") != aspect_ratio:
        raise GeminiPlannerError("Gemini ఇచ్చిన aspect ratio అడిగిన ratioతో సరిపోలలేదు.")
    return plan
