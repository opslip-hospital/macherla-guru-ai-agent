"""Build a timed Telugu dialogue soundtrack from speaker-labelled lines."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

try:
    from .telugu_tts import TELUGU_VOICES, TeluguTTSSetupError, synthesize_telugu_speech
except ImportError:  # Gradio Space runs this directory as its working import root.
    from telugu_tts import TELUGU_VOICES, TeluguTTSSetupError, synthesize_telugu_speech


class DialogueAudioError(RuntimeError):
    pass


def parse_dialogue_script(script: str) -> list[dict[str, str]]:
    lines = []
    for number, raw in enumerate((script or "").splitlines(), start=1):
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        parts = raw.split("|", 2)
        if len(parts) != 3:
            raise DialogueAudioError(
                f"లైన్ {number}: Speaker|Voice|Dialogue రూపంలో రాయండి."
            )
        speaker, voice, dialogue = (part.strip() for part in parts)
        if not speaker or not dialogue:
            raise DialogueAudioError(f"లైన్ {number}: పాత్ర పేరు, డైలాగ్ ఖాళీగా ఉండకూడదు.")
        if voice not in TELUGU_VOICES:
            raise DialogueAudioError(f"లైన్ {number}: తెలుగు వాయిస్ ఎంపిక సరైనది కాదు.")
        if not any("\u0c00" <= char <= "\u0c7f" for char in dialogue):
            raise DialogueAudioError(f"లైన్ {number}: డైలాగ్‌ను తెలుగు లిపిలో రాయండి.")
        if len(dialogue) > 700:
            raise DialogueAudioError(f"లైన్ {number}: ఒక్క డైలాగ్ 700 అక్షరాల లోపు ఉండాలి.")
        lines.append({"speaker": speaker, "voice": voice, "dialogue": dialogue})
    if not lines:
        raise DialogueAudioError("కనీసం ఒక తెలుగు డైలాగ్ ఇవ్వండి.")
    if len(lines) > 12:
        raise DialogueAudioError("ఒక్క soundtrackలో గరిష్ఠంగా 12 డైలాగ్ లైన్లు మాత్రమే.")
    return lines


def _run(command: list[str], timeout: int = 90) -> None:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise DialogueAudioError("ఆడియో తయారీకి సమయం మించిపోయింది.") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout or "FFmpeg error")[-1200:]
        raise DialogueAudioError(f"ఆడియో ప్రాసెసింగ్ విఫలమైంది: {detail}")


def build_dialogue_soundtrack(
    script: str,
    output_file: str,
    gap_ms: int = 450,
    rate: str = "+0%",
) -> Path:
    """Create a WAV soundtrack with short pauses between generated dialogue clips."""
    lines = parse_dialogue_script(script)
    if gap_ms < 0 or gap_ms > 3000:
        raise DialogueAudioError("డైలాగ్‌ల మధ్య gap 0–3000 ms మధ్య ఉండాలి.")
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise DialogueAudioError("FFmpeg runtime అందుబాటులో లేదు.") from exc

    output = Path(output_file).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="macherla_dialogue_") as temp:
        work = Path(temp)
        wav_files: list[Path] = []
        for index, line in enumerate(lines):
            mp3 = work / f"line_{index:02d}.mp3"
            wav = work / f"line_{index:02d}.wav"
            try:
                synthesize_telugu_speech(
                    text=line["dialogue"],
                    voice=line["voice"],
                    output_file=str(mp3),
                    rate=rate,
                    timeout_seconds=90,
                )
            except TeluguTTSSetupError as exc:
                raise DialogueAudioError(
                    f"{line['speaker']} వాయిస్ తయారీలో సమస్య: {exc}"
                ) from exc
            _run([
                ffmpeg, "-y", "-i", str(mp3), "-ac", "1", "-ar", "24000",
                "-c:a", "pcm_s16le", str(wav),
            ])
            wav_files.append(wav)
            if index < len(lines) - 1 and gap_ms:
                silence = work / f"silence_{index:02d}.wav"
                _run([
                    ffmpeg, "-y", "-f", "lavfi", "-i",
                    "anullsrc=r=24000:cl=mono", "-t", f"{gap_ms / 1000:.3f}",
                    "-c:a", "pcm_s16le", str(silence),
                ])
                wav_files.append(silence)

        concat_file = work / "concat.txt"
        concat_file.write_text(
            "".join("file '" + str(p).replace("'", "'\\''") + "'\n" for p in wav_files),
            encoding="utf-8",
        )
        _run([
            ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-c:a", "pcm_s16le", str(output),
        ], timeout=120)
    if not output.is_file() or output.stat().st_size < 1024:
        raise DialogueAudioError("తయారైన dialogue WAV సరిగా లేదు.")
    return output
