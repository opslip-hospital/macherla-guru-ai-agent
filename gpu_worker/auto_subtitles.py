"""Optional multilingual speech-to-subtitle generation using faster-whisper."""
from __future__ import annotations

from pathlib import Path


class SubtitleError(ValueError):
    pass


def transcribe_to_srt(
    audio_video_path: str,
    output_srt: str,
    *,
    language: str | None = None,
    model_size: str = "tiny",
    device: str = "cpu",
    compute_type: str = "int8",
) -> str:
    source = Path(audio_video_path)
    if not source.is_file() or source.stat().st_size == 0:
        raise SubtitleError("Input video/audio file is missing or empty.")
    if model_size not in {"tiny", "base", "small"}:
        raise SubtitleError("Choose tiny, base, or small Whisper model.")
    if language not in {None, "te", "en", "hi", "ta", "kn", "ml"}:
        raise SubtitleError("Unsupported language selection.")
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SubtitleError("faster-whisper is not installed in this app environment.") from exc
    try:
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        segments, _info = model.transcribe(
            str(source), language=language, beam_size=1, vad_filter=True,
            word_timestamps=False,
        )
        def stamp(seconds: float) -> str:
            ms = max(0, int(round(float(seconds) * 1000)))
            hours, ms = divmod(ms, 3_600_000)
            minutes, ms = divmod(ms, 60_000)
            secs, ms = divmod(ms, 1000)
            return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"
        entries = []
        for segment in segments:
            text = (segment.text or "").strip()
            if not text:
                continue
            entries.append(
                f"{len(entries) + 1}\n{stamp(segment.start)} --> {stamp(segment.end)}\n{text}"
            )
        if not entries:
            raise SubtitleError("No speech was detected. Upload an SRT file instead.")
        target = Path(output_srt)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n\n".join(entries) + "\n", encoding="utf-8")
        return str(target)
    except SubtitleError:
        raise
    except Exception as exc:
        raise SubtitleError(f"Speech transcription failed: {exc}") from exc
