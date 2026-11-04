"""Automatic scene-cut analysis for short comedy edits using FFmpeg scene scores."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .comedy_edit import _ffmpeg_path, ComedyEditError


def detect_scene_changes(video_path: str, *, threshold: float = 0.28, max_duration: float = 20.0) -> list[float]:
    source = Path(video_path)
    if not source.is_file() or source.stat().st_size == 0:
        raise ComedyEditError("Video file is missing or empty.")
    if not 0.05 <= float(threshold) <= 0.9:
        raise ComedyEditError("Scene threshold must be between 0.05 and 0.9.")
    if not 1 <= float(max_duration) <= 20:
        raise ComedyEditError("Maximum duration must be between 1 and 20 seconds.")
    command = [
        _ffmpeg_path(), "-hide_banner", "-i", str(source), "-t", str(float(max_duration)),
        "-vf", f"select='gt(scene,{float(threshold):.3f})',metadata=print",
        "-an", "-f", "null", "-"
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as exc:
        raise ComedyEditError("Scene analysis timed out. Try a shorter video.") from exc
    output = (result.stderr or "") + "\n" + (result.stdout or "")
    found = []
    for match in re.finditer(r"pts_time:([0-9]+(?:\.[0-9]+)?)", output):
        value = float(match.group(1))
        if 0.15 < value < float(max_duration) and (not found or value - found[-1] >= 0.35):
            found.append(round(value, 3))
    return found[:30]


def make_comedy_edit_decision(cuts: list[float], *, duration: float) -> dict:
    if not 1 <= float(duration) <= 20:
        raise ComedyEditError("Duration must be between 1 and 20 seconds.")
    valid = sorted({round(float(x), 3) for x in cuts if 0.15 < float(x) < float(duration)})
    moments = []
    for index, timestamp in enumerate(valid):
        moments.append({
            "time": timestamp,
            "action": "punch_zoom",
            "reason": "visual_scene_change",
            "label": f"Scene transition {index + 1}",
        })
    return {
        "duration_seconds": float(duration),
        "scene_changes": valid,
        "punch_moments": moments,
        "editing_style": "fast_comedy",
        "note": "Scene-change detection is a visual heuristic; it does not understand dialogue or identify characters.",
    }
