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
        "editing_style": "dynamic_punch_edit",
        "note": "Scene-change detection is a visual heuristic; it does not analyze dialogue meaning, character identity, or story context.",
    }


def detect_face_tracking(video_path: str, *, aspect_ratio: str = "9:16", max_duration: float = 20.0, sample_interval: float = 0.25) -> list[dict]:
    """Sample face locations and return smoothed normalized crop anchors."""
    source = Path(video_path)
    if not source.is_file() or source.stat().st_size == 0:
        raise ComedyEditError("Video is missing for face tracking.")
    sizes = {"9:16": (720, 1280), "16:9": (1280, 720), "1:1": (720, 720)}
    if aspect_ratio not in sizes:
        raise ComedyEditError("Unsupported aspect ratio for face tracking.")
    try:
        import cv2
    except ImportError as exc:
        raise ComedyEditError("Face tracking requires opencv-python-headless.") from exc
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise ComedyEditError("Could not open video for face tracking.")
    try:
        sw, sh = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = max(1.0, cap.get(cv2.CAP_PROP_FPS))
        duration = min(float(max_duration), cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps)
        ow, oh = sizes[aspect_ratio]
        scale = max(ow / max(1, sw), oh / max(1, sh))
        vw, vh = ow / (sw * scale), oh / (sh * scale)
        cascade_type = getattr(cv2, "CascadeClassifier", None)
        if cascade_type is None:
            # Some minimal OpenCV wheels omit the legacy Haar API; safely fall back to center framing.
            return []
        detector = cascade_type(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if detector.empty():
            raise ComedyEditError("OpenCV face detector model could not be loaded.")
        points, smooth_x, smooth_y = [], None, None
        t = 0.0
        while t < duration:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                break
            h, w = frame.shape[:2]
            nw = min(480, w)
            small = cv2.resize(frame, (nw, max(1, int(h * nw / w))))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(24, 24))
            if len(faces):
                x, y, fw, fh = max(faces, key=lambda box: int(box[2]) * int(box[3]))
                cx, cy = (x + fw / 2) / small.shape[1], (y + fh / 2) / small.shape[0]
                tx = min(1.0, max(0.0, (cx - vw / 2) / max(1e-6, 1 - vw)))
                ty = min(1.0, max(0.0, (cy - vh / 2) / max(1e-6, 1 - vh)))
                smooth_x = tx if smooth_x is None else 0.35 * tx + 0.65 * smooth_x
                smooth_y = ty if smooth_y is None else 0.35 * ty + 0.65 * smooth_y
                points.append({"time": round(t, 3), "x": round(smooth_x, 4), "y": round(smooth_y, 4)})
            t += max(0.1, float(sample_interval))
        return points
    finally:
        cap.release()
