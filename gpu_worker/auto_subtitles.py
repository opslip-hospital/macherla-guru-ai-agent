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
    max_duration: float = 20.0,
    device: str = "cpu",
    compute_type: str = "int8",
    punch_points_path: str | None = None,
    transcript_path: str | None = None,
    word_timestamps_path: str | None = None,
) -> str:
    source = Path(audio_video_path)
    if not source.is_file() or source.stat().st_size == 0:
        raise SubtitleError("Input video/audio file is missing or empty.")
    if model_size not in {"tiny", "base", "small"}:
        raise SubtitleError("Choose tiny, base, or small Whisper model.")
    if not 1 <= float(max_duration) <= 20:
        raise SubtitleError("Speech analysis duration must be between 1 and 20 seconds.")
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
            word_timestamps=True, clip_timestamps=[0.0, float(max_duration)],
        )
        def stamp(seconds: float) -> str:
            ms = max(0, int(round(float(seconds) * 1000)))
            hours, ms = divmod(ms, 3_600_000)
            minutes, ms = divmod(ms, 60_000)
            secs, ms = divmod(ms, 1000)
            return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"
        entries = []
        speech_points = []
        transcript_segments = []
        word_timestamps = []
        for segment in segments:
            text = (segment.text or "").strip()
            if not text:
                continue
            # Phrase starts provide speech-aware visual emphasis points without changing dialogue.
            speech_points.append(round(max(0.0, float(segment.start)), 3))
            words = []
            for word in (getattr(segment, "words", None) or []):
                token = (getattr(word, "word", "") or "").strip()
                if token:
                    timed_word = {"start": round(float(word.start), 3), "end": round(float(word.end), 3), "word": token}
                    words.append(timed_word)
                    word_timestamps.append(timed_word)
            transcript_segments.append({"start": round(float(segment.start), 3), "end": round(float(segment.end), 3), "text": text, "words": words})
            entries.append(
                f"{len(entries) + 1}\n{stamp(segment.start)} --> {stamp(segment.end)}\n{text}"
            )
        if not entries:
            raise SubtitleError("No speech was detected. Upload an SRT file instead.")
        target = Path(output_srt)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n\n".join(entries) + "\n", encoding="utf-8")
        if punch_points_path or transcript_path or word_timestamps_path:
            import json
            if punch_points_path:
                Path(punch_points_path).write_text(json.dumps(speech_points), encoding="utf-8")
            if transcript_path:
                Path(transcript_path).write_text(json.dumps(transcript_segments, ensure_ascii=False, indent=2), encoding="utf-8")
            if word_timestamps_path:
                Path(word_timestamps_path).write_text(json.dumps(word_timestamps, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(target)
    except SubtitleError:
        raise
    except Exception as exc:
        raise SubtitleError(f"Speech transcription failed: {exc}") from exc
