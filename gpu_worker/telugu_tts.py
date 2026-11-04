"""Telugu speech synthesis adapter using the Edge TTS online service.

This creates a separate MP3 voice track. It does not perform lip-sync or mix
audio into generated video.
"""
from __future__ import annotations

import asyncio
from pathlib import Path


TELUGU_VOICES = {
    "Mohan (పురుష వాయిస్)": "te-IN-MohanNeural",
    "Shruti (స్త్రీ వాయిస్)": "te-IN-ShrutiNeural",
}


class TeluguTTSSetupError(RuntimeError):
    pass


def validate_telugu_speech(text: str, voice: str) -> tuple[str, str]:
    clean = (text or "").strip()
    if not clean:
        raise TeluguTTSSetupError("తెలుగు డైలాగ్ రాయండి.")
    if len(clean) > 1500:
        raise TeluguTTSSetupError("ఒక్కసారి గరిష్ఠంగా 1500 అక్షరాల వరకు మాత్రమే ఇవ్వండి.")
    if not any("\u0c00" <= char <= "\u0c7f" for char in clean):
        raise TeluguTTSSetupError("దయచేసి తెలుగు లిపిలోనే డైలాగ్ రాయండి.")
    voice_id = TELUGU_VOICES.get(voice)
    if not voice_id:
        raise TeluguTTSSetupError("ఎంచుకున్న తెలుగు వాయిస్ అందుబాటులో లేదు.")
    return clean, voice_id


async def _save_speech(text: str, voice_id: str, output: Path, rate: str) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice_id, rate=rate)
    await asyncio.wait_for(communicate.save(str(output)), timeout=90)


def synthesize_telugu_speech(
    *,
    text: str,
    voice: str,
    output_file: str,
    rate: str = "+0%",
    timeout_seconds: int = 90,
) -> Path:
    clean, voice_id = validate_telugu_speech(text, voice)
    if timeout_seconds < 10 or timeout_seconds > 180:
        raise TeluguTTSSetupError("వాయిస్ తయారీ సమయం 10–180 సెకన్ల మధ్య ఉండాలి.")
    if rate not in {"-15%", "-10%", "-5%", "+0%", "+5%", "+10%", "+15%"}:
        raise TeluguTTSSetupError("వాయిస్ వేగం సరైన ఎంపిక కాదు.")

    output = Path(output_file).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    async def run():
        import edge_tts
        communicate = edge_tts.Communicate(clean, voice_id, rate=rate)
        await asyncio.wait_for(communicate.save(str(output)), timeout=timeout_seconds)

    try:
        asyncio.run(run())
    except asyncio.TimeoutError as exc:
        raise TeluguTTSSetupError("తెలుగు వాయిస్ తయారీకి సమయం మించిపోయింది. మళ్లీ ప్రయత్నించండి.") from exc
    except Exception as exc:
        raise TeluguTTSSetupError(
            f"ఆన్‌లైన్ తెలుగు వాయిస్ సేవలో సమస్య వచ్చింది: {type(exc).__name__}: {exc}"
        ) from exc

    if not output.is_file() or output.stat().st_size < 256:
        raise TeluguTTSSetupError("వాయిస్ MP3 సరిగా తయారు కాలేదు.")
    return output
