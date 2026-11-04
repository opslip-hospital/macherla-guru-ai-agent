"""Optional Gemini video understanding for short-form director cue suggestions."""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests


class GeminiDirectorError(ValueError):
    pass


def analyze_video_with_gemini(video_path: str, api_key: str, *, mime_type: str = "video/mp4") -> dict:
    source = Path(video_path)
    if not api_key:
        raise GeminiDirectorError("GEMINI_API_KEY is not configured in Streamlit Secrets or environment variables.")
    if not source.is_file() or source.stat().st_size == 0:
        raise GeminiDirectorError("Video file is missing for Gemini analysis.")
    data = source.read_bytes()
    try:
        start = requests.post(
            "https://generativelanguage.googleapis.com/upload/v1beta/files",
            headers={
                "x-goog-api-key": api_key,
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(len(data)),
                "X-Goog-Upload-Header-Content-Type": mime_type,
                "Content-Type": "application/json",
            },
            json={"file": {"display_name": source.name}},
            timeout=60,
        )
        start.raise_for_status()
        upload_url = start.headers.get("X-Goog-Upload-URL")
        if not upload_url:
            raise GeminiDirectorError("Gemini upload URL was not returned.")
        finish = requests.post(
            upload_url,
            headers={"X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize",
                     "Content-Length": str(len(data))},
            data=data, timeout=300,
        )
        finish.raise_for_status()
        info = finish.json().get("file", finish.json())
        uri, state = info.get("uri"), info.get("state", "PROCESSING")
        if not uri:
            raise GeminiDirectorError("Gemini did not return a video URI.")
        for _ in range(30):
            if state == "ACTIVE":
                break
            if state == "FAILED":
                raise GeminiDirectorError("Gemini could not process this video file. Try an MP4 export.")
            time.sleep(2)
            check = requests.get(
                "https://generativelanguage.googleapis.com/v1beta/" + info.get("name", ""),
                headers={"x-goog-api-key": api_key}, timeout=30,
            )
            check.raise_for_status()
            info = check.json()
            state = info.get("state", "")
        if state != "ACTIVE":
            raise GeminiDirectorError("Gemini video processing timed out. Retry once.")
        prompt = (
            "Analyze this short video for a Telugu short-form editor. Understand visible actions, "
            "spoken dialogue, mood and comedic/surprise beats. Do not invent events or dialogue. "
            "Return ONLY JSON: {summary:string, moments:[{time:number,kind:string,reason:string}]}. "
            "Use seconds from the start, only real moments within the clip, max 8 moments. "
            "Kinds may be dialogue_emphasis, comedy, surprise, suspense, reaction_emphasis. "
            "A reaction_emphasis is allowed only when an actual visible reaction is present; "
            "do not claim to create or insert a new shot."
        )
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={"contents": [{"parts": [{"file_data": {"mime_type": mime_type, "file_uri": uri}, "media_processing": "AGENTIC"},
                                            {"text": prompt}]}],
                  "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json", "maxOutputTokens": 1600}},
            timeout=240,
        )
        response.raise_for_status()
        payload = response.json()
        parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        raw = "\n".join(part.get("text", "") for part in parts if isinstance(part, dict))
        result = json.loads(raw.replace("```json", "").replace("```", "").strip())
        if not isinstance(result, dict) or not isinstance(result.get("moments", []), list):
            raise GeminiDirectorError("Gemini returned an unexpected analysis format.")
        moments = []
        for item in result.get("moments", [])[:8]:
            if not isinstance(item, dict):
                continue
            try:
                seconds = float(item.get("time"))
            except (TypeError, ValueError):
                continue
            if seconds >= 0:
                moments.append({"time": seconds, "kind": str(item.get("kind", "emphasis"))[:40],
                                "reason": str(item.get("reason", ""))[:240]})
        return {"summary": str(result.get("summary", ""))[:1000], "moments": moments}
    except GeminiDirectorError:
        raise
    except requests.RequestException as exc:
        raise GeminiDirectorError(f"Gemini API request failed: {exc}") from exc
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise GeminiDirectorError(f"Gemini analysis response could not be parsed: {exc}") from exc
