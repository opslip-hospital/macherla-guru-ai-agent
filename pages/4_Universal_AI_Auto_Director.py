import importlib
import json
import logging
import os
import tempfile
from pathlib import Path

import streamlit as st

from gpu_worker.auto_director import detect_scene_changes, detect_face_tracking, make_comedy_edit_decision, clip_video_for_analysis
from gpu_worker import comedy_edit
from gpu_worker.auto_subtitles import SubtitleError, transcribe_to_srt
from gpu_worker.gemini_director import GeminiDirectorError, analyze_video_with_gemini

# Streamlit multipage sessions can retain imported modules after a page hot-reload.
# Reload the editor module so the UI and renderer always use the same function signature.
comedy_edit = importlib.reload(comedy_edit)
ComedyEditError = comedy_edit.ComedyEditError
render_comedy_edit = comedy_edit.render_comedy_edit

st.set_page_config(page_title="Universal AI Auto Director", page_icon="🎬", layout="centered")
st.title("🎬 Universal AI Auto Director & Video Editor")
st.caption("Upload any video → detect visual scene changes → apply dynamic edits → download MP4")
st.info(
    "ఏ వీడియో అయినా ఉపయోగించవచ్చు: animation, cartoon, story లేదా people footage. ఉన్న పాత్రలు/డైలాగ్‌లను మార్చదు. "
    "గరిష్ఠంగా 20 సెకన్లు. అసలు డైలాగ్‌ను అలాగే ఉంచుతుంది."
)

video = st.file_uploader("Upload any raw video (MP4/MOV/MKV/WEBM)", type=["mp4", "mov", "mkv", "webm"])
ratio = st.selectbox("Output format", ["9:16 Shorts", "16:9 Landscape", "1:1 Square"], index=0)
ratio_value = {"9:16 Shorts": "9:16", "16:9 Landscape": "16:9", "1:1 Square": "1:1"}[ratio]
intensity = st.select_slider("Dynamic punch intensity", options=["Medium", "High", "Extreme"], value="High")
speed_label = st.select_slider("Video speed", options=["Slow cinematic (0.85x)", "Normal (1.0x)", "Fast (1.15x)"], value="Normal (1.0x)")
playback_speed = {"Slow cinematic (0.85x)": 0.85, "Normal (1.0x)": 1.0, "Fast (1.15x)": 1.15}[speed_label]
duration = st.slider("Maximum output duration (seconds)", 1, 20, 20)
threshold = st.slider("Scene-change sensitivity", 0.10, 0.60, 0.28, 0.02)
music = st.file_uploader("Optional background music (MP3/WAV/AAC)", type=["mp3", "wav", "aac", "m4a"])
sfx = st.file_uploader("Optional comedy/reaction sound effect (MP3/WAV/AAC)", type=["mp3", "wav", "aac", "m4a"])
subtitle = st.file_uploader("Optional subtitles (SRT)", type=["srt"])
auto_subtitles = st.checkbox("Auto-generate subtitles from speech (Whisper)", value=False)
face_tracking = st.checkbox("Enable face-aware camera tracking (experimental)", value=True)
gemini_analysis = st.checkbox("Gemini AI story + dialogue analysis (uses API quota)", value=False)
subtitle_language = st.selectbox("Speech language", ["Auto detect", "Telugu", "English", "Hindi", "Tamil", "Kannada", "Malayalam"])
whisper_model = st.selectbox("Whisper model (CPU)", ["tiny", "base", "small"], index=0)
music_volume = st.slider("Background music volume", 0.0, 0.35, 0.12, 0.01)
sfx_volume = st.slider("Sound-effect volume", 0.0, 0.8, 0.22, 0.02)
st.caption(
    "Visual scene analysis is separate from dialogue meaning. Optional face-aware crop tracking and Whisper speech-to-text are available; reaction shots are not generated. Background music automatically ducks under original audio when both tracks are present."
)

if st.button("🎬 Auto Director + Edit Video", type="primary", disabled=video is None, use_container_width=True):
    with tempfile.TemporaryDirectory(prefix="universal_auto_director_") as temp:
        root = Path(temp)
        source = root / ("source" + (Path(video.name).suffix.lower() or ".mp4"))
        source.write_bytes(video.getvalue())
        music_path = None
        if music is not None:
            music_path = root / ("music" + Path(music.name).suffix.lower())
            music_path.write_bytes(music.getvalue())
        sfx_path = None
        if sfx is not None:
            sfx_path = root / ("sound_effect" + Path(sfx.name).suffix.lower())
            sfx_path.write_bytes(sfx.getvalue())
        subtitle_path = None
        if subtitle is not None:
            subtitle_path = root / "captions.srt"
            subtitle_path.write_bytes(subtitle.getvalue())
        output = root / "universal_edited_final.mp4"
        speech_points_path = root / "speech_punch_points.json"
        transcript_path = root / "speech_transcript.json"
        word_timestamps_path = root / "speech_word_timestamps.json"
        speech_points = []
        transcript_segments = []
        speech_word_timestamps = []
        face_track_points = []
        gemini_result = {"summary": "", "moments": []}
        gemini_error = ""
        try:
            if gemini_analysis:
                try:
                    gemini_key = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
                except Exception:
                    gemini_key = os.getenv("GEMINI_API_KEY", "")
                try:
                    with st.spinner("Gemini కోసం ఎంచుకున్న duration వరకు చిన్న MP4 సిద్ధం చేస్తున్నాం…"):
                        analysis_clip = clip_video_for_analysis(str(source), str(root / "gemini_analysis_clip.mp4"), max_duration=duration)
                    with st.spinner("Gemini వీడియోలో కథ, మాటలు, comedy/reaction moments విశ్లేషిస్తోంది…"):
                        gemini_result = analyze_video_with_gemini(analysis_clip, gemini_key, mime_type="video/mp4")
                    if gemini_result.get("remote_file_cleanup") == "deleted":
                        st.success("Gemini temporary video upload was deleted after analysis.")
                    elif gemini_result.get("remote_file_cleanup") == "delete_failed":
                        st.warning("Gemini analysis completed, but temporary-file deletion could not be confirmed. Check Google AI Studio Files.")
                    gemini_result["moments"] = [item for item in gemini_result.get("moments", []) if 0 <= float(item.get("time", -1)) < float(duration)]
                except GeminiDirectorError as exc:
                    # Gemini is an optional enhancement; its outage or missing key must
                    # not prevent the core visual edit and MP4 export from completing.
                    gemini_error = str(exc)
                    st.warning("Gemini analysis unavailable; continuing with visual editing and any Whisper cues. " + gemini_error)
            if auto_subtitles and subtitle is None:
                language_code = {"Auto detect": None, "Telugu": "te", "English": "en", "Hindi": "hi", "Tamil": "ta", "Kannada": "kn", "Malayalam": "ml"}[subtitle_language]
                try:
                    with st.spinner("Speech recognition model సిద్ధం చేస్తున్నాం; మొదటిసారి model download కావచ్చు…"):
                        subtitle_path = Path(transcribe_to_srt(str(source), str(root / "auto_captions.srt"), language=language_code, model_size=whisper_model, max_duration=duration, punch_points_path=str(speech_points_path), transcript_path=str(transcript_path), word_timestamps_path=str(word_timestamps_path)))
                    if speech_points_path.is_file():
                        speech_points = json.loads(speech_points_path.read_text(encoding="utf-8"))
                    if transcript_path.is_file():
                        transcript_segments = json.loads(transcript_path.read_text(encoding="utf-8"))
                    if word_timestamps_path.is_file():
                        speech_word_timestamps = json.loads(word_timestamps_path.read_text(encoding="utf-8"))
                except SubtitleError as exc:
                    # Speech recognition is optional: missing models/no speech must not
                    # block the visual edit or final MP4 export.
                    st.warning("Auto subtitles unavailable; continuing without generated captions. " + str(exc))
                    subtitle_path = None
            with st.spinner("1/3 వీడియో సీన్లను విశ్లేషిస్తున్నాం…"):
                cuts = detect_scene_changes(str(source), threshold=threshold, max_duration=duration)
                if face_tracking:
                    try:
                        face_track_points = detect_face_tracking(str(source), aspect_ratio=ratio_value, max_duration=duration)
                    except Exception as exc:
                        # Face tracking is experimental; fall back to centered framing
                        # rather than failing the entire video edit.
                        logging.warning("Face tracking unavailable; using center crop: %s", exc)
                        face_track_points = []
                        st.warning("Face tracking unavailable; using center crop. " + str(exc))
                plan = make_comedy_edit_decision(cuts, duration=duration)
                plan["speech_punch_points"] = speech_points
                plan["face_tracking_points"] = face_track_points
                plan["face_tracking_detected"] = bool(face_track_points)
                plan["gemini_story_summary"] = gemini_result.get("summary", "")
                plan["gemini_director_moments"] = gemini_result.get("moments", [])
                plan["gemini_analysis_error"] = gemini_error
                plan["speech_transcript"] = transcript_segments
                plan["speech_word_timestamps"] = speech_word_timestamps
                plan["note"] += " Speech phrase starts can also guide punch zoom timing when Whisper subtitles are enabled."
                gemini_times = [float(item["time"]) for item in gemini_result.get("moments", [])]
                punch_times = sorted({round(float(x), 3) for x in cuts + speech_points + gemini_times if 0.15 < float(x) < float(duration)})
                # Keep the combined edit cues visible and exportable, not just inside the FFmpeg render.
                plan["combined_director_cues"] = [
                    {"time": point, "action": "smooth_punch_zoom",
                     "sources": [name for name, values in (
                         ("visual_scene_change", cuts), ("speech_phrase_start", speech_points),
                         ("gemini_story_moment", gemini_times)
                     ) if any(abs(float(value) - point) < 0.01 for value in values)]}
                    for point in punch_times
                ]
                plan["punch_moments"] = plan["combined_director_cues"]
                punch_cues = [{"time": float(item["time"]), "kind": str(item.get("kind", "dialogue_emphasis"))}
                              for item in gemini_result.get("moments", [])]
                plan["reaction_emphasis_count"] = sum(1 for item in punch_cues if item["kind"].lower() == "reaction_emphasis")
            st.subheader("🎬 Auto Director Edit Plan")
            st.write(f"గుర్తించిన visual scene changes: {len(cuts)}")
            if face_tracking:
                st.write(f"Face tracking samples: {len(face_track_points)}" if face_track_points else "ముఖాలు గుర్తించలేదు; center crop వాడబడుతుంది.")
            if gemini_result.get("summary"):
                st.info("Gemini story understanding: " + gemini_result["summary"])
                st.write("Actual reaction moments detected: {}".format(plan["reaction_emphasis_count"]))
                for moment in gemini_result.get("moments", []):
                    st.write("{:.2f}s — {}: {}".format(moment["time"], moment["kind"], moment["reason"]))
            if transcript_segments:
                with st.expander("🗣️ గుర్తించిన మాటలు / Speech transcript", expanded=True):
                    for segment in transcript_segments:
                        st.write("{:.2f}s–{:.2f}s: {}".format(segment["start"], segment["end"], segment["text"]))
                    if speech_word_timestamps:
                        st.caption("Word-level timing (lip-sync preparation)")
                        st.write(" · ".join("{} [{:.2f}–{:.2f}s]".format(item["word"], item["start"], item["end"]) for item in speech_word_timestamps))
            if cuts:
                st.write("Dynamic punch points: " + ", ".join(f"{x:.2f}s" for x in cuts))
            else:
                st.write("స్పష్టమైన scene cuts గుర్తించలేదు; regular dynamic zoom rhythm వాడతాం.")
            with st.expander("🎯 Combined Director Cue Timeline", expanded=False):
                for cue in plan["combined_director_cues"]:
                    st.write("{:.2f}s — {} ({})".format(cue["time"], cue["action"], ", ".join(cue["sources"])))
            if sfx is not None:
                st.caption("Uploaded sound effect will be placed at up to 8 detected director punch cues; timing follows the selected playback speed.")
            st.success("సినిమాటిక్ ఎడిటింగ్ ప్లాన్ సిద్ధమైంది — వివరాలు కింద ఉన్నాయి.")
            st.write(f"• Zoom style: Fast + Smooth ({intensity})")
            st.write("• Colour polish: Contrast, saturation, sharpening")
            st.write(f"• Video speed: {speed_label}")
            st.write("• Smooth fade-in / fade-out transitions")
            st.write("• Original dialogue: అలాగే ఉంచబడుతుంది")
            with st.spinner("2/3 Reframing, dynamic zooms, colour polish, audio mix…"):
                rendered = render_comedy_edit(
                    str(source), str(output), aspect_ratio=ratio_value, intensity=intensity,
                    music_file=str(music_path) if music_path else None,
                    music_volume=music_volume, max_duration=duration, punch_times=punch_times,
                    subtitle_file=str(subtitle_path) if subtitle_path else None,
                    playback_speed=playback_speed, face_track_points=face_track_points,
                    sfx_file=str(sfx_path) if sfx_path else None, sfx_volume=sfx_volume,
                    punch_cues=punch_cues,
                )
            data = Path(rendered).read_bytes()
            st.success("3/3 వీడియో ఎడిటింగ్ పూర్తయింది!")
            st.info("ఫోన్‌లో dashboard buffering తగ్గించడానికి inline preview ఆఫ్‌లో ఉంది. కింద ఉన్న Download Final MP4 ద్వారా వీడియోను సేవ్ చేసి Gallery లేదా VLCలో ప్లే చేయండి.")
            st.download_button(
                "⬇️ Download Final MP4", data=data,
                file_name="universal-edited-final.mp4", mime="video/mp4",
                type="primary", use_container_width=True,
            )
            st.download_button(
                "⬇️ Download Director Edit Plan (JSON)",
                data=json.dumps(plan, ensure_ascii=False, indent=2).encode("utf-8"),
                file_name="universal-edit-plan.json", mime="application/json",
            )
        except (ComedyEditError, SubtitleError, GeminiDirectorError, OSError, ValueError) as exc:
            st.error(str(exc))
        except Exception as exc:
            # Keep the full traceback in Streamlit Cloud logs while showing a
            # useful, non-secret diagnostic in the app instead of a redacted crash.
            logging.exception("Unexpected Universal AI Auto Director failure")
            st.error(f"Unexpected {type(exc).__name__}: {exc}")
            st.info("ఈ error వివరంతో render సమస్యను గుర్తించి సరిచేయవచ్చు. వీడియో ఫైల్ మీ పరికరంలోనే ఉంటుంది.")

st.divider()
st.markdown(
    "**ఈ వెర్షన్‌లో:** visual scene-change detection, smooth scene-aware punch zooms, "
    "9:16/16:9/1:1 reframing, experimental face-aware crop tracking, contrast/saturation/sharpen polish, original dialogue preservation, "
    "optional low-volume background music and timed comedy/reaction sound-effect overlays at director punch cues, adjustable 0.85x–1.15x speed, smooth fade-in/fade-out, optional SRT subtitles, "
    "Whisper multilingual speech-to-text with transcript, word-level timing and phrase-timed punch points, optional Gemini video/story/dialogue moment analysis, timed uploaded SFX overlays, final MP4 + JSON edit-plan export. "
    "**ఇంకా అందుబాటులో లేనివి:** automatic reaction-shot insertion, per-word sound-effect selection, AI lip-sync generation, and new-scene generation. "
    "Gemini and face tracking require real-video testing; reaction emphasis is a stronger zoom on an existing visible reaction, not a generated reaction shot; face detection can miss stylized/cartoon characters."
)
