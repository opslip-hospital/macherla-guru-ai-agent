import os
import json
import time
import re
import requests
import subprocess
import tempfile
import zipfile
from pathlib import Path

 
def create_prompt_broll_images(video_bytes, mime_type, display_name, api_key, user_prompt, aspect_ratio, clip_start=0.0, clip_duration=0.0):
    """Analyze speech in the source video, then generate timed still B-roll images."""
    if len(video_bytes) > 100 * 1024 * 1024:
        raise ValueError("AI Prompt B-Roll కోసం 100 MB కంటే చిన్న వీడియో ఎంచుకో.")
    start = requests.post(
        "https://generativelanguage.googleapis.com/upload/v1beta/files",
        headers={
            "x-goog-api-key": api_key,
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(len(video_bytes)),
            "X-Goog-Upload-Header-Content-Type": mime_type,
            "Content-Type": "application/json",
        },
        json={"file": {"display_name": display_name}},
        timeout=60,
    )
    start.raise_for_status()
    upload_url = start.headers.get("X-Goog-Upload-URL")
    if not upload_url:
        raise RuntimeError("Gemini upload URL రాలేదు.")
    finish = requests.post(
        upload_url,
        headers={
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
            "Content-Length": str(len(video_bytes)),
        },
        data=video_bytes,
        timeout=300,
    )
    finish.raise_for_status()
    info = finish.json().get("file", {})
    file_uri, file_name = info.get("uri"), info.get("name")
    if not file_uri or not file_name:
        raise RuntimeError("Gemini video file వివరాలు రాలేదు.")
    try:
        state = info.get("state", "PROCESSING")
        for _ in range(45):
            if state == "ACTIVE":
                break
            if state == "FAILED":
                raise RuntimeError("Gemini వీడియోను process చేయలేకపోయింది.")
            time.sleep(2)
            check = requests.get(
                "https://generativelanguage.googleapis.com/v1beta/" + file_name,
                headers={"x-goog-api-key": api_key},
                timeout=30,
            )
            check.raise_for_status()
            info = check.json()
            state = info.get("state", "")
        if state != "ACTIVE":
            raise RuntimeError("Gemini video processing timeout. చిన్న clipతో ప్రయత్నించు.")

        selected_range = (
            f"Analyze only the clip from {clip_start:.2f} seconds for {clip_duration:.2f} seconds, "
            "and return timestamps relative to the beginning of that selected clip."
            if clip_duration > 0 else
            "Analyze the whole video and return timestamps relative to the beginning of the video."
        )
        storyboard_prompt = (
            "Listen to the spoken words in this video and create up to 6 varied visual B-roll cutaways "
            "that directly illustrate the topics being discussed. " + selected_range +
            " The B-roll replaces the speaker picture temporarily, but the original voice will continue. "
            "Choose non-overlapping moments where a relevant visual would help the viewer. "
            "Each scene should last about 1.5 to 3.5 seconds and be within the video duration. "
            "Respect this user's visual direction: " + user_prompt + ". "
            "Return ONLY valid JSON: {\"scenes\":[{\"start\":2.0,\"end\":5.0,"
            "\"image_prompt\":\"Detailed visual description, no text or watermark\"}]}. "
            "Use up to 6 scenes maximum. Vary the visual language: mix realistic location cutaways, close-up detail shots, wide establishing shots, action visuals, and symbolic imagery where relevant. Avoid repeating the same composition. Keep all visuals directly tied to the spoken topic. Do not invent factual labels or put text in images. "
            "If speech is unclear, create visuals for the overall subject of the video."
        )
        analysis = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={
                "contents": [{"parts": [
                    {"file_data": {"mime_type": mime_type, "file_uri": file_uri}},
                    {"text": storyboard_prompt},
                ]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
            timeout=300,
        )
        analysis.raise_for_status()
        response_data = analysis.json()
        text_parts = [
            part["text"]
            for candidate in response_data.get("candidates", [])
            for part in candidate.get("content", {}).get("parts", [])
            if isinstance(part.get("text"), str)
        ]
        raw = "\n".join(text_parts).replace("```json", "").replace("```", "").strip()
        storyboard = json.loads(raw)
        scenes = storyboard.get("scenes", []) if isinstance(storyboard, dict) else []
        generated = []
        for scene in scenes[:6]:
            try:
                scene_start = max(0.0, float(scene.get("start", 0)))
                scene_end = float(scene.get("end", 0))
            except (TypeError, ValueError):
                continue
            if clip_duration > 0:
                scene_start = min(scene_start, clip_duration)
                scene_end = min(scene_end, clip_duration)
            if scene_end <= scene_start:
                continue
            visual_prompt = (
                "Create a photorealistic cinematic B-roll still image for a video cutaway. "
                + str(scene.get("image_prompt", ""))
                + " User style direction: " + user_prompt
                + ". No captions, letters, logos, watermarks, borders, or UI. "
                "Strong clear subject, realistic details, professional video footage look."
            )
            image_response = requests.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image:generateContent",
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": visual_prompt}]}],
                    "generationConfig": {
                        "responseModalities": ["TEXT", "IMAGE"],
                        "imageConfig": {"aspectRatio": aspect_ratio},
                    },
                },
                timeout=300,
            )
            image_response.raise_for_status()
            image_data = image_response.json()
            image_bytes = None
            for candidate in image_data.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    inline = part.get("inlineData") or part.get("inline_data")
                    if inline and inline.get("data"):
                        import base64
                        image_bytes = base64.b64decode(inline["data"])
                        break
                if image_bytes:
                    break
            if image_bytes:
                generated.append({
                    "name": f"ai_broll_{len(generated) + 1}.png",
                    "bytes": image_bytes,
                    "start": scene_start,
                    "end": scene_end,
                })
        if not generated:
            raise RuntimeError("Gemini visuals తయారు చేయలేదు. API quota/model access ఉందో చూసి మళ్లీ ప్రయత్నించు.")
        return generated
    finally:
        try:
            requests.delete(
                "https://generativelanguage.googleapis.com/v1beta/" + file_name,
                headers={"x-goog-api-key": api_key},
                timeout=20,
            )
        except Exception:
            pass


import imageio_ffmpeg
import streamlit as st

st.set_page_config(page_title="Macherla Guru AI Video Editor", page_icon="🎞️", layout="wide")
st.title("🎞️ Macherla Guru — AI Video Editor")
st.caption("Free-first video editing • FFmpeg engine • YouTube Manager remains separate")

def create_srt_with_gemini(video_bytes, mime_type, display_name, api_key, language):
    if len(video_bytes) > 100 * 1024 * 1024:
        raise ValueError("Automatic captions కోసం 100 MB కంటే చిన్న వీడియో ఎంచుకో.")
    start = requests.post(
        "https://generativelanguage.googleapis.com/upload/v1beta/files",
        headers={
            "x-goog-api-key": api_key,
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(len(video_bytes)),
            "X-Goog-Upload-Header-Content-Type": mime_type,
            "Content-Type": "application/json",
        },
        json={"file": {"display_name": display_name}},
        timeout=60,
    )
    start.raise_for_status()
    upload_url = start.headers.get("X-Goog-Upload-URL")
    if not upload_url:
        raise RuntimeError("Gemini upload URL రాలేదు.")
    finish = requests.post(
        upload_url,
        headers={
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
            "Content-Length": str(len(video_bytes)),
        },
        data=video_bytes,
        timeout=300,
    )
    finish.raise_for_status()
    info = finish.json().get("file", {})
    file_uri = info.get("uri")
    file_name = info.get("name")
    if not file_uri or not file_name:
        raise RuntimeError("Gemini video file వివరాలు రాలేదు.")
    try:
        state = info.get("state", "PROCESSING")
        for _ in range(45):
            if state == "ACTIVE":
                break
            if state == "FAILED":
                raise RuntimeError("Gemini వీడియోను process చేయలేకపోయింది.")
            time.sleep(2)
            check = requests.get(
                "https://generativelanguage.googleapis.com/v1beta/" + file_name,
                headers={"x-goog-api-key": api_key},
                timeout=30,
            )
            check.raise_for_status()
            info = check.json()
            state = info.get("state", "")
        if state != "ACTIVE":
            raise RuntimeError("Gemini processing సమయం ముగిసింది. చిన్న వీడియోతో మళ్లీ ప్రయత్నించు.")
        language_rule = {
            "Auto detect (Telugu / English)": "Detect the spoken language automatically; preserve Telugu in Telugu script and English in English.",
            "Telugu": "Transcribe all speech in Telugu script. Keep unavoidable English words in English.",
            "English": "Transcribe all speech in English.",
        }[language]
        prompt = (
            "Transcribe the audible dialogue in this video into accurate subtitles. "
            + language_rule
            + " Return ONLY valid JSON in this exact shape: {\"segments\":[{\"start\":0.0,\"end\":2.5,\"text\":\"spoken words\"}]}. "
            "Times must be seconds from the start of the video, each segment must match the actual spoken words and timing, "
            "keep each subtitle short (ideally no more than 2 lines), do not invent dialogue, music lyrics, or sounds. "
            "If there is no intelligible speech return {\"segments\":[]}."
        )
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={
                "contents": [{"parts": [
                    {"file_data": {"mime_type": mime_type, "file_uri": file_uri}},
                    {"text": prompt},
                ]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
        parts = []
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if isinstance(part.get("text"), str):
                    parts.append(part["text"])
        raw = "\n".join(parts).replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        segments = parsed.get("segments", []) if isinstance(parsed, dict) else []
        def stamp(seconds):
            millis = max(0, int(float(seconds) * 1000))
            hours, remainder = divmod(millis, 3600000)
            minutes, remainder = divmod(remainder, 60000)
            secs, ms = divmod(remainder, 1000)
            return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"
        rows = []
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            text_value = str(segment.get("text", "")).strip()
            try:
                start_s = max(0.0, float(segment.get("start", 0)))
                end_s = float(segment.get("end", 0))
            except (TypeError, ValueError):
                continue
            if text_value and end_s > start_s:
                rows.append((start_s, end_s, text_value))
        rows.sort(key=lambda item: item[0])
        return "\n\n".join(
            f"{index}\n{stamp(start_s)} --> {stamp(end_s)}\n{text_value}"
            for index, (start_s, end_s, text_value) in enumerate(rows, start=1)
        ).encode("utf-8")
    finally:
        if file_name:
            try:
                requests.delete(
                    "https://generativelanguage.googleapis.com/v1beta/" + file_name,
                    headers={"x-goog-api-key": api_key},
                    timeout=20,
                )
            except Exception:
                pass



@st.cache_resource(show_spinner=False)
def load_local_whisper_model(model_size):
    from faster_whisper import WhisperModel
    return WhisperModel(
        model_size,
        device="cpu",
        compute_type="int8",
        cpu_threads=2,
        num_workers=1,
    )


def create_srt_with_local_whisper(video_bytes, display_name, language, model_size):
    """Create SRT locally with Whisper; no Gemini key or API quota is used."""
    import tempfile

    language_code = {
        "Auto detect (Telugu / English)": None,
        "Telugu": "te",
        "English": "en",
    }.get(language)
    with tempfile.TemporaryDirectory(prefix="macherla_whisper_") as temp_dir:
        suffix = Path(display_name).suffix or ".mp4"
        video_path = Path(temp_dir) / ("source" + suffix)
        video_path.write_bytes(video_bytes)
        model = load_local_whisper_model(model_size)
        whisper_options = {
            "language": language_code,
            "task": "transcribe",
            "beam_size": 5 if language_code == "te" else 3,
            "best_of": 5 if language_code == "te" else 3,
            "temperature": 0.0,
            "vad_filter": True,
            "condition_on_previous_text": True,
        }
        if language_code == "te":
            # Bias multilingual Whisper toward Telugu orthography, not Tamil-script transliteration.
            whisper_options["initial_prompt"] = (
                "తెలుగు భాషలో మాట్లాడుతున్నారు. మాటలను సహజమైన తెలుగు పదాలతో "
                "తెలుగు లిపిలోనే రాయండి. తమిళ అక్షరాలు లేదా ఆంగ్ల లిప్యంతరీకరణ వాడవద్దు."
            )
        segments, info = model.transcribe(str(video_path), **whisper_options)
        def stamp(seconds):
            millis = max(0, int(float(seconds) * 1000))
            hours, remainder = divmod(millis, 3600000)
            minutes, remainder = divmod(remainder, 60000)
            secs, ms = divmod(remainder, 1000)
            return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"
        rows = []
        for segment in segments:
            text_value = str(segment.text).strip()
            if text_value and segment.end > segment.start:
                rows.append((segment.start, segment.end, text_value))
        if not rows:
            raise ValueError("మాటలు గుర్తించబడలేదు. స్పష్టమైన voice ఉన్న clipతో ప్రయత్నించు.")
        if language_code == "te":
            combined_text = " ".join(row[2] for row in rows)
            has_telugu = bool(re.search(r"[\u0C00-\u0C7F]", combined_text))
            has_tamil = bool(re.search(r"[\u0B80-\u0BFF]", combined_text))
            if has_tamil and not has_telugu:
                raise ValueError(f"Whisper Telugu బదులు Tamil లిపి ఇచ్చింది (detected language: {info.language}, confidence: {info.language_probability:.0%}). Telugu prompt + accurate decodingతో కూడా ఇది వస్తే, ఈ audio/model combinationలో Whisper సరైన తెలుగు ఇవ్వలేకపోతోంది; తప్పు SRT save చేయలేదు.")
            if not has_telugu:
                raise ValueError(f"Telugu ఎంచుకున్నా తెలుగు లిపి రాలేదు (detected language: {info.language}, confidence: {info.language_probability:.0%}). తప్పు SRT save చేయలేదు.")
        srt = "\n\n".join(
            f"{index}\n{stamp(start_s)} --> {stamp(end_s)}\n{text_value}"
            for index, (start_s, end_s, text_value) in enumerate(rows, start=1)
        )
        return srt.encode("utf-8"), info.language, info.language_probability

st.info(
    "ఈ Editor YouTube Managerకి వేరే Streamlit page. ఇక్కడ చేసే edits అసలు YouTube channelకి upload కావు. "
    "Final MP4ని నువ్వే download చేసుకుని ఉపయోగించవచ్చు."
)

st.subheader("📱 Video → Video Person Replacement (Free trial)")
st.write(
    "Phone browserలో source video + replacement character photo ఇచ్చి person replacement try చేయవచ్చు. "
    "ఇది external cloud tool; ఈ editorలో direct rendering కాదు."
)
st.link_button("🪄 Open Free Video Person Replacement", "https://seedance.film/ai-video-generator/video-to-video", use_container_width=True)
st.caption(
    "కొత్త account free credits: వారి FAQ ప్రకారం రెండు attempts, ఒక completed video వరకు; "
    "free video-to-video Seedance 2.0 Miniలో గరిష్ఠంగా 720p. ఇది unlimited free కాదు. "
    "Stylized / fictional characters‌కు ప్రయత్నించు; photorealistic real-person faces reject కావచ్చు. "
    "Free tierలో commercial-use rights లేవని వారి terms చెబుతున్నాయి—monetized uploadకు ముందు licence తప్పనిసరిగా చెక్ చేయి. "
    "ఇది third-party service; upload చేసే వీడియో/ఫోటోలకు నీకు హక్కులు ఉండాలి."
)
with st.expander("ఈ toolలో ఏ prompt ఇవ్వాలి?"):
    st.code(
        "Replace the man in the video with the character from the image. "
        "Keep his movements, timing, framing, camera motion and lighting exactly as they are; "
        "change nothing else in the scene.",
        language="text",
    )

st.subheader("🎬 Merge multiple videos into one MP4")
merge_videos = st.file_uploader(
    "రెండు లేదా అంతకంటే ఎక్కువ videos ఎంచుకోండి",
    type=["mp4", "mov", "mkv", "webm", "avi"],
    accept_multiple_files=True,
    key="merge_video_files",
    help="వీడియోలు ఎంచుకున్న క్రమంలో ఒకే MP4గా కలుస్తాయి. గరిష్ఠంగా 8 clips."
)
merge_format = st.selectbox("Merged video format", ["9:16 Shorts / Reels", "16:9 YouTube", "1:1 Square"], key="merge_format")
if merge_videos:
    total_merge_mb = sum(len(item.getvalue()) for item in merge_videos) / (1024 * 1024)
    st.progress(1.0, text="All selected clips uploaded — 100%")
    st.caption(f"{len(merge_videos)} clips received • {total_merge_mb:.1f} MB • 100%")
if merge_videos and st.button("🎞️ Merge videos & create one MP4", type="primary"):
    if len(merge_videos) < 2:
        st.warning("Merge చేయడానికి కనీసం 2 videos ఎంచుకో.")
    elif len(merge_videos) > 8:
        st.warning("ఒకేసారి గరిష్ఠంగా 8 videos మాత్రమే merge చేయగలవు.")
    else:
        ffmpeg_merge = imageio_ffmpeg.get_ffmpeg_exe()
        if merge_format.startswith("9:16"):
            mw, mh = 720, 1280
        elif merge_format.startswith("16:9"):
            mw, mh = 1280, 720
        else:
            mw, mh = 720, 720
        with tempfile.TemporaryDirectory(prefix="macherla_merge_") as merge_tmp:
            merge_dir = Path(merge_tmp)
            normalized = []
            progress = st.progress(0, text="Merge కోసం clips సిద్ధం చేస్తున్నాను...")
            failed = False
            try:
                for idx, uploaded in enumerate(merge_videos, start=1):
                    input_path = merge_dir / f"input_{idx}{Path(uploaded.name).suffix.lower()}"
                    output_path = merge_dir / f"normalized_{idx:02d}.mp4"
                    input_path.write_bytes(uploaded.getvalue())
                    probe = subprocess.run(
                        [ffmpeg_merge, "-i", str(input_path)],
                        capture_output=True, text=True, timeout=120
                    )
                    has_audio = "Audio:" in (probe.stderr or "")
                    normalize_cmd = [ffmpeg_merge, "-y", "-i", str(input_path)]
                    if not has_audio:
                        normalize_cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
                    normalize_cmd += [
                        "-map", "0:v:0",
                        "-vf", f"scale={mw}:{mh}:force_original_aspect_ratio=decrease:flags=lanczos,pad={mw}:{mh}:(ow-iw)/2:(oh-ih)/2:color=black,fps=30,setsar=1,format=yuv420p",
                    ]
                    if has_audio:
                        normalize_cmd += ["-map", "0:a:0", "-af", "aresample=async=1:first_pts=0"]
                    else:
                        normalize_cmd += ["-map", "1:a:0"]
                    normalize_cmd += [
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "128k",
                        "-shortest", "-movflags", "+faststart", str(output_path)
                    ]
                    result = subprocess.run(normalize_cmd, capture_output=True, text=True, timeout=1800)
                    if result.returncode != 0 or not output_path.exists() or output_path.stat().st_size == 0:
                        st.error(f"{idx}వ వీడియో normalize కాలేదు: {uploaded.name}")
                        st.code((result.stderr or result.stdout or "FFmpeg error")[-2500:])
                        failed = True
                        break
                    normalized.append(output_path)
                    progress.progress(idx / len(merge_videos), text=f"{idx}/{len(merge_videos)} clips సిద్ధం")
                if not failed:
                    concat_list = merge_dir / "concat_list.txt"
                    concat_list.write_text(
                        "".join(f"file '{p.as_posix()}'\n" for p in normalized),
                        encoding="utf-8"
                    )
                    merged_path = merge_dir / "macherla-guru-merged.mp4"
                    joined = subprocess.run(
                        [ffmpeg_merge, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
                         "-c", "copy", "-movflags", "+faststart", str(merged_path)],
                        capture_output=True, text=True, timeout=1800
                    )
                    if joined.returncode != 0 or not merged_path.exists() or merged_path.stat().st_size == 0:
                        st.error("Videos merge కాలేదు.")
                        st.code((joined.stderr or joined.stdout or "FFmpeg error")[-3000:])
                    else:
                        st.success("అన్ని videos ఒకే MP4గా merge అయ్యాయి!")
                        merged_bytes = merged_path.read_bytes()
                        st.video(merged_bytes)
                        st.download_button(
                            "⬇️ Download merged MP4",
                            data=merged_bytes,
                            file_name="macherla-guru-merged.mp4",
                            mime="video/mp4",
                            type="primary"
                        )
            except subprocess.TimeoutExpired:
                st.error("Merge చేయడానికి ఎక్కువ సమయం పట్టింది. చిన్న clipsతో ప్రయత్నించు.")
            except Exception as exc:
                st.error(f"Merge error: {exc}")

st.divider()
video = st.file_uploader("ముందుగా వీడియో upload చేయి", type=["mp4", "mov", "mkv", "webm", "avi"])
if video is not None:
    uploaded_mb = len(video.getvalue()) / (1024 * 1024)
    st.progress(1.0, text="Upload complete — 100%")
    st.caption(f"వీడియో upload అయింది: {uploaded_mb:.1f} MB • 100% received")
trim_clip = False
trim_start = 0.0
trim_duration = 0.0
if video:
    trim_clip = st.checkbox("✂️ Trim only a selected part (optional)", value=False)
    if trim_clip:
        trim_col1, trim_col2 = st.columns(2)
        with trim_col1:
            trim_start = st.number_input("Start time (seconds)", min_value=0.0, max_value=86400.0, value=0.0, step=1.0)
        with trim_col2:
            trim_duration = st.number_input("Clip length (seconds)", min_value=1.0, max_value=3600.0, value=15.0, step=1.0)
        st.caption("ఉదా: Start 10, Clip length 15 అంటే 10వ second నుంచి 25వ second వరకు edit అవుతుంది.")
if video:
    st.subheader("✂️ Split video into two clips")
    split_at = st.number_input(
        "Split point (seconds from start)",
        min_value=1.0,
        max_value=86400.0,
        value=5.0,
        step=1.0,
        help="ఉదా: 5 అంటే మొదటి clip 0–5 seconds, రెండో clip 5 seconds నుంచి video చివరి వరకు."
    )
    if st.button("✂️ Create 2 separate clips"):
        ffmpeg_split = imageio_ffmpeg.get_ffmpeg_exe()
        with tempfile.TemporaryDirectory(prefix="macherla_split_") as split_tmp:
            split_source = Path(split_tmp) / ("input" + Path(video.name).suffix.lower())
            part_one = Path(split_tmp) / "clip_1.mp4"
            part_two = Path(split_tmp) / "clip_2.mp4"
            zip_path = Path(split_tmp) / "macherla_split_clips.zip"
            split_source.write_bytes(video.getvalue())
            try:
                first = subprocess.run(
                    [ffmpeg_split, "-y", "-i", str(split_source), "-t", str(split_at),
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                     "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(part_one)],
                    capture_output=True, text=True, timeout=1800
                )
                if first.returncode != 0 or not part_one.exists():
                    st.error("మొదటి clip తయారు కాలేదు.")
                    st.code((first.stderr or first.stdout or "FFmpeg error")[-2500:])
                    st.stop()
                second = subprocess.run(
                    [ffmpeg_split, "-y", "-ss", str(split_at), "-i", str(split_source),
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                     "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(part_two)],
                    capture_output=True, text=True, timeout=1800
                )
                if second.returncode != 0 or not part_two.exists() or part_two.stat().st_size == 0:
                    st.error("రెండో clip తయారు కాలేదు. Split point video duration కంటే తక్కువగా ఉందో చూసుకో.")
                    st.code((second.stderr or second.stdout or "FFmpeg error")[-2500:])
                    st.stop()
                with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.write(part_one, arcname="clip_1.mp4")
                    archive.write(part_two, arcname="clip_2.mp4")
                st.success("రెండు clips సిద్ధంగా ఉన్నాయి!")
                st.download_button(
                    "⬇️ Download both clips (ZIP)",
                    data=zip_path.read_bytes(),
                    file_name="macherla-guru-split-clips.zip",
                    mime="application/zip",
                    type="primary"
                )
            except subprocess.TimeoutExpired:
                st.error("Split చేయడానికి ఎక్కువ సమయం పట్టింది. చిన్న వీడియోతో ప్రయత్నించు.")
            except Exception as exc:
                st.error(f"Split error: {exc}")

if not video:
    st.markdown("### అందుబాటులో ఉన్న editing options")
    st.write("Quality enhance • Denoise • Sharpen • Smooth slow motion • 1080p / 2K export • Aspect ratio conversion")
    st.write("AIతో ఏ రకమైన background నుంచైనా subject cutout చేసి కొత్త background పెట్టే experimental option కూడా ఉంది.")
    st.stop()

left, right = st.columns(2)
with left:
    aspect = st.selectbox("Video format", ["9:16 Shorts / Reels", "16:9 YouTube", "1:1 Square"])
    resolution = st.selectbox("Export quality", ["1080p", "2K"], index=1)
    smooth = st.checkbox("Smooth slow motion (50% speed)", value=False)
    playback_speed = st.selectbox("Playback speed", ["0.5x", "0.75x", "1x (Normal)", "1.25x", "1.5x", "2x"], index=2)
    stabilize_video = st.checkbox("🎥 Reduce camera shake (stabilize)", value=False, help="FFmpeg deshake filter; extreme shake may remain.")
    denoise = st.checkbox("Video noise reduction", value=True)
    sharpen = st.checkbox("Sharpen details", value=True)
    framing = st.selectbox("Frame layout", ["Fit full video (bars if needed)", "Fill frame (crop edges)"])
    auto_reframe = st.checkbox("📱 Auto Reframe for Shorts (center crop)", value=False, help="Landscape వీడియోను vertical frameలో center crop చేస్తుంది; ఇది face tracking కాదు.")
    freeze_last_frame = st.checkbox("🧊 Hold final frame (Freeze Frame)", value=False)
    freeze_duration = st.slider("Final frame hold duration (seconds)", 1, 8, 2, disabled=not freeze_last_frame)
    rotation = st.selectbox("Rotate video", ["No rotation", "90° clockwise", "180°", "90° counter-clockwise"])
    flip_horizontal = st.checkbox("Mirror video horizontally", value=False)
with right:
    brightness = st.slider("Brightness", -0.20, 0.20, 0.0, 0.01)
    contrast = st.slider("Contrast", 0.70, 1.50, 1.05, 0.05)
    saturation = st.slider("Color saturation", 0.0, 2.0, 1.05, 0.05)
    fps_choice = st.selectbox("Frame rate", ["Keep original", "30 FPS", "60 FPS"])
    bg_mode = st.checkbox("Green/blue screen background replace", value=False)
    ai_bg_mode = st.checkbox("🤖 Remove ANY background with AI (not just green/blue)", value=False)
    mute_audio = st.checkbox("Mute original audio", value=False)
    audio_volume = st.slider("Original audio volume", 0, 200, 100, 5, disabled=mute_audio)
    audio_denoise = st.checkbox("🔊 Clean background noise in audio", value=False, disabled=mute_audio)
    voice_clarity = st.checkbox("🎙️ Improve voice clarity", value=False, disabled=mute_audio)
    export_size = st.selectbox("MP4 file size / quality", ["Best quality", "Balanced", "Smaller file"], index=0)

background = None
if bg_mode and ai_bg_mode:
    st.warning("ఒకేసారి ఒక background removal mode మాత్రమే ఎంచుకోండి.")
elif bg_mode:
    key_color = st.selectbox("Original screen color", ["Green", "Blue"])
    key_similarity = st.slider("Green/blue removal strength", 0.05, 0.45, 0.18, 0.01)
    key_blend = st.slider("Edge blending", 0.00, 0.25, 0.08, 0.01)
    background = st.file_uploader("కొత్త background image లేదా video", type=["jpg", "jpeg", "png", "webp", "mp4", "mov", "mkv", "webm"], key="chroma_background")
    st.caption("ఇది green/blue chroma-key footageకే.")
elif ai_bg_mode:
    ai_subject_type = st.selectbox(
        "ఏది cutout చేయాలి?",
        ["General subject / objects", "People / human characters"],
        help="General mode వస్తువులు, characters కోసం; People mode మనుషుల కోసం ప్రత్యేకంగా tune చేసిన model."
    )
    refine_edges = st.checkbox(
        "Improve hair / fine edges (slower)",
        value=False,
        help="Alpha matting edge refinement. Hair, fur వంటి అంచులకు ఉపయోగపడవచ్చు; CPU processing ఎక్కువ సమయం పడుతుంది."
    )
    ai_fps = st.selectbox("AI cutout frame sampling", [8, 12, 15], index=1, format_func=lambda x: f"{x} FPS")
    ai_width = st.selectbox("AI cutout detail", [720, 960, 1280], index=1, format_func=lambda x: f"{x}px wide")
    ai_bg_layout = st.selectbox("New background image layout", ["Fill screen (crop edges)", "Fit full image (black bars)"], index=0)
    background = st.file_uploader("కొత్త background image లేదా video", type=["jpg", "jpeg", "png", "webp", "mp4", "mov", "mkv", "webm"], key="ai_background")
    st.info(f"ఈ AI modeకి green/blue screen అవసరం లేదు. సాధారణ room, street, outdoor వంటి backgrounds నుంచీ subjectని వేరు చేయడానికి ప్రయత్నిస్తుంది. CPU processing నెమ్మదిగా ఉంటుంది; ఈ settingతో గరిష్ఠంగా సుమారు {300 / ai_fps:.0f} seconds clip (300 frames) మాత్రమే. Detail/FPS పెంచితే processing సమయం, memory usage పెరుగుతాయి. మొదటిసారి model download కావడానికి internet అవసరం.")

st.subheader("📝 Automatic captions + subtitles")
subtitle_file = st.file_uploader(
    "లేదా మీ దగ్గర ఉన్న SRT file upload చేయి",
    type=["srt"],
    key="subtitle_srt",
    help="తెలుగు లేదా English SRT ఫైల్ upload చేస్తే వీడియోలో captions కనిపిస్తాయి."
)
try:
    editor_gemini_key = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
except Exception:
    editor_gemini_key = os.getenv("GEMINI_API_KEY", "")
caption_language = st.selectbox(
    "Caption language",
    ["Auto detect (Telugu / English)", "Telugu", "English"]
)
if not editor_gemini_key:
    st.info("Automatic captions కోసం app Secretsలో ఇప్పటికే ఉన్న GEMINI_API_KEY అవసరం. SRT upload మాత్రం key లేకుండానే పనిచేస్తుంది.")
elif st.button("🎙️ Generate automatic captions with Gemini"):
    try:
        with st.spinner("Gemini వీడియోలోని మాటలు విని subtitles తయారు చేస్తోంది..."):
            generated_srt = create_srt_with_gemini(
                video.getvalue(),
                video.type or "video/mp4",
                video.name,
                editor_gemini_key,
                caption_language,
            )
        if not generated_srt:
            st.warning("వీడియోలో స్పష్టమైన మాటలు గుర్తించలేకపోయింది.")
            st.session_state.pop("auto_srt_bytes", None)
            st.session_state.pop("auto_srt_video_name", None)
        else:
            st.session_state["auto_srt_bytes"] = generated_srt
            st.session_state["auto_srt_video_name"] = video.name
            st.success("Automatic subtitles సిద్ధమయ్యాయి. ఇవి Edit video నొక్కినప్పుడు నేరుగా videoలో కలుస్తాయి.")
            st.download_button("⬇️ Download generated SRT", generated_srt, file_name="macherla-captions.srt", mime="application/x-subrip")
    except Exception as exc:
        st.error(f"Automatic captions తయారు కాలేదు: {exc}")

st.markdown("**🆓 Gemini quota అయిపోయినా captions — Local Whisper**")
whisper_language = st.selectbox(
    "Whisper language (తెలుగు వీడియోకు Telugu ఎంచుకో)",
    ["Telugu", "Auto detect (Telugu / English)", "English"],
    index=0,
    key="whisper_language",
)
whisper_model_size = st.selectbox(
    "Local caption model",
    ["tiny", "base", "small"],
    index=1,
    format_func=lambda value: {
        "tiny": "Tiny — వేగంగా, accuracy తక్కువ",
        "base": "Base — మధ్యస్థ వేగం",
        "small": "Small — ఎక్కువ accuracy అవకాశం, చాలా నెమ్మది; సుమారు 460 MB download",
    }[value],
    help="Small model మొదటిసారి సుమారు 460 MB download కావచ్చు; server CPU/RAMపై ఎక్కువ సమయం పడుతుంది.",
)
if st.button("🎧 Generate free captions (No Gemini quota)"):
    try:
        with st.spinner("Whisper model load/download చేసి captions తయారు చేస్తోంది. మొదటిసారి కొంత సమయం పట్టవచ్చు..."):
            whisper_srt, detected_language, language_probability = create_srt_with_local_whisper(
                video.getvalue(),
                video.name,
                whisper_language,
                whisper_model_size,
            )
        st.session_state["auto_srt_bytes"] = whisper_srt
        st.session_state["auto_srt_video_name"] = video.name
        st.success(
            f"Local Whisper captions సిద్ధం! గుర్తించిన భాష: {detected_language} "
            f"(confidence {language_probability:.0%}). Edit video నొక్కితే subtitles కలుస్తాయి."
        )
        st.download_button(
            "⬇️ Download Whisper SRT",
            whisper_srt,
            file_name="macherla-whisper-captions.srt",
            mime="application/x-subrip",
        )
    except Exception as exc:
        st.error(f"Local Whisper captions తయారు కాలేదు: {exc}")

subtitle_bytes = (
    subtitle_file.getvalue() if subtitle_file is not None
    else st.session_state.get("auto_srt_bytes")
    if st.session_state.get("auto_srt_video_name") == video.name
    else None
)
if subtitle_bytes:
    # Normalize common SRT encodings/newlines and reject empty or malformed files
    # before FFmpeg runs, so a silent subtitle failure is not mistaken for success.
    try:
        srt_text = subtitle_bytes.decode("utf-8-sig").replace("\\r\\n", "\\n").replace("\\r", "\\n")
        srt_text = srt_text.strip()
        if not re.search(r"(?m)^\s*\d{1,2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+\d{1,2}:\d{2}:\d{2}[,.]\d{3}", srt_text):
            raise ValueError("SRTలో సరైన timestamp cues కనిపించలేదు. SRT ఫైల్‌ను తెరిచి timing format సరిచూడు.")
        if not re.search(r"(?m)^\s*\d{1,2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+\d{1,2}:\d{2}:\d{2}[,.]\d{3}\s*\n.+", srt_text):
            raise ValueError("SRTలో timestamps ఉన్నాయి కానీ caption text కనిపించలేదు.")
        subtitle_bytes = srt_text.encode("utf-8")
        st.success("SRT గుర్తించబడింది — captions final MP4లో burn అవుతాయి.")
    except UnicodeDecodeError:
        st.error("SRT UTF-8 formatలో లేదు. UTF-8గా save చేసి మళ్లీ upload చేయి.")
        st.stop()
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
else:
    st.info("SRT upload చేయలేదు. Final videoలో subtitles ఉండవు.")
subtitle_size = st.slider("Subtitle text size", 16, 48, 28, 2)
subtitle_position = st.selectbox("Subtitle position", ["Bottom", "Middle", "Top"])
st.caption("Gemini captionsకు API quota వర్తిస్తుంది. Local Whisper captions Gemini quota/API key వాడవు; మొదటిసారి model download అవసరం, server CPUపై నెమ్మదిగా పని చేయవచ్చు. రెండు విధానాల్లోనూ final exportకి ముందు Telugu spelling/timing సరిచూసుకో.")

st.subheader("🎙️ Promptతో ఆటోమేటిక్ B-Roll visuals")
st.caption("ఒక prompt రాయి. Gemini వీడియోలోని మాటల్ని అర్థం చేసుకుని, సరిపోయే visualsను generate చేసి, voice కొనసాగుతుండగా సరైన timingలో చూపిస్తుంది.")
broll_mode = st.checkbox("✨ AI Prompt B-Roll enable చేయి", value=False)
broll_assets = []
broll_timeline = []
if broll_mode:
    st.markdown("**📤 నీ దగ్గరున్న B-Roll visuals upload చేయి**")
    uploaded_broll_files = st.file_uploader(
        "Images లేదా short B-Roll videos ఎంచుకో",
        type=["jpg", "jpeg", "png", "webp", "mp4", "mov", "mkv", "webm"],
        accept_multiple_files=True,
        key="manual_broll_uploads",
        help="నీ phone/gallery నుంచి ఒకటి లేదా ఎక్కువ images/videos upload చేయవచ్చు. ప్రతి visualకి start/end timing సెట్ చేయి."
    )
    st.caption("Gemini generate చేయకపోయినా, నువ్వు upload చేసిన visualsతోనే B-Roll edit చేయవచ్చు. Images స్థిరంగా కనిపిస్తాయి; videosలో motion ఉంటుంది.")
    if uploaded_broll_files:
        st.caption(f"{len(uploaded_broll_files)} manual B-Roll file(s) upload అయ్యాయి.")
        manual_scene_limit = trim_duration if trim_clip else 3600.0
        for manual_index, manual_asset in enumerate(uploaded_broll_files):
            st.markdown(f"**Uploaded visual {manual_index + 1}: {manual_asset.name}**")
            suffix = Path(manual_asset.name).suffix.lower()
            if suffix in [".jpg", ".jpeg", ".png", ".webp"]:
                st.image(manual_asset.getvalue(), use_container_width=True)
            else:
                st.video(manual_asset.getvalue())
            manual_col1, manual_col2 = st.columns(2)
            with manual_col1:
                manual_start = st.number_input(
                    f"Uploaded visual {manual_index + 1} start (sec)",
                    min_value=0.0, max_value=float(manual_scene_limit),
                    value=0.0, step=0.5,
                    key=f"manual_broll_start_{manual_index}_{video.name}_{manual_asset.name}"
                )
            with manual_col2:
                manual_end = st.number_input(
                    f"Uploaded visual {manual_index + 1} end (sec)",
                    min_value=0.5, max_value=float(manual_scene_limit),
                    value=min(3.0, float(manual_scene_limit)), step=0.5,
                    key=f"manual_broll_end_{manual_index}_{video.name}_{manual_asset.name}"
                )
            if manual_end > manual_start:
                broll_assets.append(manual_asset)
                broll_timeline.append((manual_start, manual_end, manual_asset))
            else:
                st.warning("ఈ visual end time, start time కంటే ఎక్కువగా పెట్టు.")
    broll_prompt = st.text_area(
        "Visuals కోసం నీ prompt",
        placeholder="ఉదా: నేను హైదరాబాద్ వర్షాల గురించి మాట్లాడుతున్నాను. నిజమైన వర్షపు రోడ్లు, ట్రాఫిక్, నీటి ప్రవాహం వంటి cinematic visuals చూపించు.",
        key="ai_broll_prompt",
        help="ఏ visuals కావాలో తెలుగులో లేదా Englishలో రాయవచ్చు."
    )
    broll_display_mode = st.selectbox(
        "B-Roll చూపించే విధానం",
        ["Full-screen visual cutaway (speaker picture temporarily replaced)", "Speaker + visual side-by-side (speaker remains visible)"],
        help="Side-by-sideలో speaker ఒక వైపు, సంబంధిత visual మరో వైపు కనిపిస్తాయి. Original voice కొనసాగుతుంది."
    )
    broll_side_by_side = broll_display_mode.startswith("Speaker +")
    st.caption("AI గరిష్ఠంగా 6 varied visual scenes తయారు చేస్తుంది. Full-screen modeలో visual మాత్రమే కనిపిస్తుంది; side-by-side modeలో speaker కూడా కనిపిస్తాడు. Original voice/audio అలాగే ఉంటుంది.")
    if st.button("🎨 Promptతో visuals generate చేయి", disabled=(not editor_gemini_key or not broll_prompt.strip())):
        try:
            clip_start_for_broll = trim_start if trim_clip else 0.0
            clip_duration_for_broll = trim_duration if trim_clip else 0.0
            ratio = "9:16" if aspect.startswith("9:16") else ("16:9" if aspect.startswith("16:9") else "1:1")
            with st.spinner("Gemini మాటలను analyze చేసి visuals generate చేస్తోంది. కొంత సమయం పట్టవచ్చు..."):
                generated_scenes = create_prompt_broll_images(
                    video.getvalue(),
                    video.type or "video/mp4",
                    video.name,
                    editor_gemini_key,
                    broll_prompt.strip(),
                    ratio,
                    clip_start_for_broll,
                    clip_duration_for_broll,
                )
            st.session_state["prompt_broll_scenes"] = generated_scenes
            st.session_state["prompt_broll_video_name"] = video.name
            st.session_state["prompt_broll_prompt"] = broll_prompt.strip()
            st.success(f"{len(generated_scenes)} AI visuals సిద్ధమయ్యాయి. ఇప్పుడు Edit video నొక్కు.")
        except Exception as exc:
            st.error(f"AI B-Roll తయారు కాలేదు: {exc}")
    generated_scenes = (
        st.session_state.get("prompt_broll_scenes", [])
        if st.session_state.get("prompt_broll_video_name") == video.name and st.session_state.get("prompt_broll_prompt") == broll_prompt.strip() else []
    )
    if generated_scenes:
        st.caption("ప్రతి visual ఎప్పుడు రావాలో నువ్వే మార్చుకోవచ్చు. Times ఎంచుకున్న clip ప్రారంభం నుంచి secondsలో ఉంటాయి.")
        for scene_index, scene in enumerate(generated_scenes):
            asset = type("GeneratedBrollAsset", (), {
                "name": scene["name"],
                "getvalue": lambda self, data=scene["bytes"]: data,
            })()
            scene_limit = trim_duration if trim_clip else 3600.0
            time_col1, time_col2 = st.columns(2)
            with time_col1:
                edited_start = st.number_input(
                    f"Visual {scene_index + 1} start (sec)",
                    min_value=0.0, max_value=float(scene_limit),
                    value=min(float(scene["start"]), float(scene_limit)),
                    step=0.5, key=f"prompt_broll_start_{scene_index}_{video.name}"
                )
            with time_col2:
                edited_end = st.number_input(
                    f"Visual {scene_index + 1} end (sec)",
                    min_value=0.5, max_value=max(0.5, float(scene_limit)),
                    value=min(max(float(scene["end"]), edited_start + 0.5), float(scene_limit)),
                    step=0.5, key=f"prompt_broll_end_{scene_index}_{video.name}"
                )
            broll_assets.append(asset)
            broll_timeline.append((edited_start, edited_end, asset))
            st.image(scene["bytes"], caption=f"AI visual {scene_index + 1}", use_container_width=True)
    if not editor_gemini_key:
        st.warning("Promptతో AI visuals కోసం app Secretsలో GEMINI_API_KEY అవసరం.")
    st.info("Gemini image generationకు API quota/charges వర్తించవచ్చు. Free quota ఉందో లేదో Google AI Studioలో నీ keyకి చెక్ చేయి. Visuals AI-generated still images; generated video clips కావు.")


st.caption(
    "2K export అంటే 1440p output. చిన్న resolution వీడియోను 2Kగా export చేయవచ్చు, "
    "కానీ లేని original detail తిరిగి సృష్టించబడదు. Smooth slow motionలో motion artifacts రావచ్చు."
)

edit_prompt = st.text_area(
    "✨ One Prompt → Video (అన్ని editing సూచనలు ఒకేసారి)",
    placeholder="ఉదా: ఈ Spider-Man వీడియోను cinematicగా enhance చేయి, B-Roll visuals add చేయి, Telugu subtitles పెట్టి 2K 9:16 MP4గా export చేయి.",
    help="Storytelling / dynamic visuals / బోర్ కాకుండా వంటి prompt ఇస్తే AI B-roll (up to 6 varied scenes), speech captions, subtle still-image motion and short visual fades ప్రయత్నిస్తుంది. Gemini API quota/charges may apply."
)

one_prompt_clicked = st.button(
    "🚀 One Prompt → Create final MP4",
    type="primary",
    disabled=((bg_mode or ai_bg_mode) and background is None) or (bg_mode and ai_bg_mode)
)
manual_edit_clicked = st.button(
    "✨ Advanced optionsతో Edit MP4",
    disabled=((bg_mode or ai_bg_mode) and background is None) or (bg_mode and ai_bg_mode) or (broll_mode and (not broll_assets or bg_mode or ai_bg_mode))
)

if one_prompt_clicked or manual_edit_clicked:
    if one_prompt_clicked:
        prompt_lower = edit_prompt.lower()
        # Apply common editing controls from one natural-language prompt.
        if any(term in prompt_lower for term in ["2k", "1440", "qhd"]):
            resolution = "2K"
        elif any(term in prompt_lower for term in ["1080p", "full hd", "full-hd"]):
            resolution = "1080p"
        if any(term in prompt_lower for term in ["9:16", "vertical", "portrait", "రీల్స్", "షార్ట్స్"]):
            aspect = "9:16 Portrait"
        elif any(term in prompt_lower for term in ["16:9", "landscape", "వైడ్ స్క్రీన్"]):
            aspect = "16:9 Landscape"
        elif any(term in prompt_lower for term in ["1:1", "square", "స్క్వేర్"]):
            aspect = "1:1 Square"
        if any(term in prompt_lower for term in ["slow motion", "slow-mo", "స్లో మోషన్", "నెమ్మదిగా"]):
            smooth = True
        if any(term in prompt_lower for term in ["no denoise", "without denoise", "నాయిస్ తగ్గించవద్దు"]):
            denoise = False
        elif any(term in prompt_lower for term in ["denoise", "noise reduction", "remove noise", "నాయిస్ తగ్గించు"]):
            denoise = True
        if any(term in prompt_lower for term in ["no sharpen", "without sharpen", "షార్పెన్ వద్దు"]):
            sharpen = False
        elif any(term in prompt_lower for term in ["sharpen", "sharp details", "షార్ప్"]):
            sharpen = True
        if any(term in prompt_lower for term in ["rotate 90 clockwise", "90° clockwise", "కుడివైపు తిప్పు"]):
            rotation = "90° clockwise"
        elif any(term in prompt_lower for term in ["rotate 90 counter", "90° counter-clockwise", "ఎడమవైపు తిప్పు"]):
            rotation = "90° counter-clockwise"
        elif any(term in prompt_lower for term in ["rotate 180", "180 degrees", "180°"]):
            rotation = "180°"
        if any(term in prompt_lower for term in ["mirror", "flip horizontal", "మిర్రర్", "ఎదురుగా తిప్పు"]):
            flip_horizontal = True
        if any(term in prompt_lower for term in ["fill frame", "crop edges", "ఫ్రేమ్ నింపు"]):
            framing = "Fill frame (crop edges)"
        elif any(term in prompt_lower for term in ["fit full", "no crop", "పూర్తి వీడియో"]):
            framing = "Fit full video (bars if needed)"
        if any(term in prompt_lower for term in ["mute", "silent", "మ్యూట్", "శబ్దం వద్దు"]):
            mute_audio = True
        volume_match = re.search(r"(?:volume|audio)\s*(?:to|at|=)?\s*(\d{1,3})\s*%|వాల్యూమ్\s*(\d{1,3})\s*%", prompt_lower)
        if volume_match and not mute_audio:
            volume_value = next((g for g in volume_match.groups() if g is not None), None)
            if volume_value is not None:
                audio_volume = max(0, min(200, int(volume_value)))
        if any(term in prompt_lower for term in ["30 fps", "30fps", "30 ఫ్రేమ్స్"]):
            fps_choice = "30 FPS"
        elif any(term in prompt_lower for term in ["60 fps", "60fps", "60 ఫ్రేమ్స్"]):
            fps_choice = "60 FPS"
        if any(term in prompt_lower for term in ["small file", "smaller file", "compress", "తక్కువ సైజు"]):
            export_size = "Smaller file"
        elif any(term in prompt_lower for term in ["best quality", "maximum quality", "అత్యుత్తమ క్వాలిటీ"]):
            export_size = "Best quality"
        elif "balanced" in prompt_lower:
            export_size = "Balanced"
        storytelling_mode = any(term in prompt_lower for term in [
            "storytelling", "story telling", "dynamic visuals", "engaging edit",
            "make it engaging", "not boring", "engaging video", "dynamic edit",
            "visual storytelling", "change visuals", "keep viewers engaged",
            "ఆసక్తికరంగా", "బోర్ కాకుండా", "బోర్ కొట్టకుండా", "చూడటానికి బాగుండేలా",
            "మాటలకు తగ్గట్టు visuals", "మాటలకు తగ్గ విజువల్స్", "విజువల్స్ మార్చు",
            "కథలా", "కథనం", "ఆటో ఎడిటింగ్"
        ])
        wants_broll = storytelling_mode or any(term in prompt_lower for term in [
            "b-roll", "broll", "బి-రోల్", "visuals", "విజువల్స్"
        ])
        # Storytelling mode automatically burns in speech captions as well as visual cutaways.
        wants_captions = storytelling_mode or any(term in prompt_lower for term in [
            "subtitle", "subtitles", "captions", "సబ్‌టైటిల్స్", "క్యాప్షన్స్", "text overlay"
        ])
        prompt_summary = [
            f"Format: {aspect}",
            f"Resolution: {resolution}",
            f"Noise reduction: {'ON' if denoise else 'OFF'}",
            f"Sharpen: {'ON' if sharpen else 'OFF'}",
            f"Slow motion: {'ON' if smooth and not wants_broll else ('Skipped with B-Roll' if smooth else 'OFF')}",
            f"Frame rate: {fps_choice}",
            f"Audio: {'Muted' if mute_audio else str(audio_volume) + '% volume'}",
            f"Export: {export_size}",
        ]
        if rotation != "No rotation":
            prompt_summary.append(f"Rotation: {rotation}")
        if flip_horizontal:
            prompt_summary.append("Mirror: ON")
        if wants_broll:
            prompt_summary.append("AI Storytelling visuals: requested (up to 6 varied scenes)")
        if wants_captions:
            prompt_summary.append(f"Automatic captions: {caption_language}")
        st.info("Prompt నుంచి ఎంచుకున్న settings:\n" + "\n".join(f"• {item}" for item in prompt_summary))
        wants_background = any(term in prompt_lower for term in ["change background", "replace background", "remove background", "background replacement", "బ్యాక్‌గ్రౌండ్ మార్చు", "బ్యాక్ గ్రౌండ్ మార్చు"])
        if wants_background and not (bg_mode or ai_bg_mode):
            st.error("Background మార్చాలంటే Green/Blue లేదా AI Background Removal mode ON చేసి, కొత్త background image/video upload చేయాలి. ఈ file అవసరాన్ని prompt ఒక్కటితో భర్తీ చేయలేం.")
            st.stop()
        if (wants_broll or wants_captions) and not editor_gemini_key:
            st.error("ఈ promptలో B-Roll లేదా automatic subtitles ఉన్నాయి. App Secretsలో GEMINI_API_KEY అవసరం.")
            st.stop()
        if wants_broll and (bg_mode or ai_bg_mode):
            st.error("B-Rollతో Green/Blue లేదా AI Background Removalను ఒకేసారి వాడలేము. ఆ modes OFF చేసి మళ్లీ ప్రయత్నించు.")
            st.stop()
        if wants_broll and not broll_assets:
            try:
                ratio = "9:16" if aspect.startswith("9:16") else ("16:9" if aspect.startswith("16:9") else "1:1")
                with st.spinner("Gemini వీడియోను అర్థం చేసుకుని B-Roll visuals తయారు చేస్తోంది..."):
                    scenes = create_prompt_broll_images(
                        video.getvalue(), video.type or "video/mp4", video.name,
                        editor_gemini_key, edit_prompt.strip(), ratio,
                        trim_start if trim_clip else 0.0,
                        trim_duration if trim_clip else 0.0,
                    )
                broll_assets = []
                broll_timeline = []
                for scene in scenes:
                    asset = type("GeneratedBrollAsset", (), {
                        "name": scene["name"],
                        "getvalue": lambda self, data=scene["bytes"]: data,
                    })()
                    broll_assets.append(asset)
                    broll_timeline.append((float(scene["start"]), float(scene["end"]), asset))
                if not scenes:
                    st.error("ఈ వీడియోకు సరిపోయే B-Roll scenes Gemini ఇవ్వలేదు. Prompt మార్చి మళ్లీ ప్రయత్నించు.")
                    st.stop()
                broll_mode = True
                broll_side_by_side = True
                st.success(f"{len(scenes)} B-Roll visuals సిద్ధమయ్యాయి. Final video render అవుతోంది.")
            except Exception as exc:
                st.error(f"Prompt B-Roll తయారు కాలేదు: {exc}")
                st.stop()
        if wants_captions and subtitle_bytes is None:
            try:
                with st.spinner("Gemini Telugu/English subtitles తయారు చేస్తోంది..."):
                    subtitle_bytes = create_srt_with_gemini(
                        video.getvalue(), video.type or "video/mp4", video.name,
                        editor_gemini_key, caption_language,
                    )
                if not subtitle_bytes:
                    st.warning("మాటలు స్పష్టంగా గుర్తించబడలేదు; subtitles లేకుండా కొనసాగుతుంది.")
            except Exception as exc:
                st.error(f"Automatic subtitles తయారు కాలేదు: {exc}")
                st.stop()
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory(prefix="macherla_editor_") as tmp:
        source = Path(tmp) / ("input" + Path(video.name).suffix.lower())
        output = Path(tmp) / "macherla_guru_edited.mp4"
        source.write_bytes(video.getvalue())

        if aspect.startswith("9:16"):
            w, h = ((1440, 2560) if resolution == "2K" else (1080, 1920))
        elif aspect.startswith("16:9"):
            w, h = ((2560, 1440) if resolution == "2K" else (1920, 1080))
        else:
            w, h = ((1440, 1440) if resolution == "2K" else (1080, 1080))

        filters = []
        prompt_text = edit_prompt.lower()
        prompt_notes = []
        # Prompt-assisted presets use local FFmpeg filters; no paid AI service is required.
        if any(word in prompt_text for word in ["smooth", "soft skin", "face smooth", "beauty", "స్మూత్", "ముఖం"]):
            filters.append("bilateral=sigmaS=8:sigmaR=0.08")
            prompt_notes.append("Soft smoothing (applied to the full frame, not face-only)")
        if any(word in prompt_text for word in ["cinematic", "film look", "సినిమాటిక్"]):
            filters.append("eq=contrast=1.12:saturation=1.12")
            prompt_notes.append("Cinematic contrast and colour")
        if any(word in prompt_text for word in ["bright", "brighter", "ప్రకాశం"]):
            filters.append("eq=brightness=0.04")
            prompt_notes.append("Brightness boost")
        if any(word in prompt_text for word in ["vivid", "colourful", "colorful", "vibrant", "రంగులు"]):
            filters.append("eq=saturation=1.18")
            prompt_notes.append("Vibrant colours")
        prompt_denoise = denoise and not any(term in prompt_text for term in ["no denoise", "without denoise", "నాయిస్ తగ్గించవద్దు"])
        prompt_sharpen = sharpen and not any(term in prompt_text for term in ["no sharpen", "without sharpen", "షార్పెన్ వద్దు"])
        prompt_smooth = smooth or any(term in prompt_text for term in ["slow motion", "స్లో మోషన్"])
        speed_factor = {"0.5x": 0.5, "0.75x": 0.75, "1x (Normal)": 1.0, "1.25x": 1.25, "1.5x": 1.5, "2x": 2.0}[playback_speed]
        if stabilize_video:
            filters.append("deshake=rx=16:ry=16:edge=mirror")
            prompt_notes.append("Camera-shake reduction (FFmpeg deshake)")
        if prompt_denoise:
            filters.append("hqdn3d=1.5:1.5:6:6")
        filters.append(f"eq=brightness={brightness}:contrast={contrast}:saturation={saturation}")
        if prompt_sharpen:
            filters.append("unsharp=5:5:0.7:3:3:0.0")
        if prompt_smooth:
            filters.extend(["setpts=2*PTS", "minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir"])
        elif speed_factor != 1.0:
            filters.append(f"setpts=PTS/{speed_factor:g}")
            prompt_notes.append(f"Playback speed {speed_factor:g}x")
            if speed_factor < 1.0:
                filters.append("minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir")
        if fps_choice == "30 FPS":
            filters.append("fps=30")
        elif fps_choice == "60 FPS" and not prompt_smooth:
            filters.append("fps=60")
        if rotation == "90° clockwise":
            filters.append("transpose=clock")
        elif rotation == "180°":
            filters.extend(["hflip", "vflip"])
        elif rotation == "90° counter-clockwise":
            filters.append("transpose=cclock")
        if flip_horizontal:
            filters.append("hflip")
        if framing == "Fill frame (crop edges)" or auto_reframe:
            filters.append(f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos")
            filters.append(f"crop={w}:{h}")
        else:
            filters.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos")
            filters.append(f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2")
        subtitle_graph_filter = None
        if subtitle_bytes is not None:
            subtitle_path = Path(tmp) / "captions.srt"
            subtitle_path.write_bytes(subtitle_bytes)
            alignment, margin = {
                "Bottom": ("2", "35"),
                "Middle": ("5", "0"),
                "Top": ("8", "35"),
            }[subtitle_position]
            subtitle_style = (
                f"FontName=Arial,FontSize={subtitle_size},PrimaryColour=&H00FFFFFF,"
                f"OutlineColour=&H00000000,BorderStyle=3,BackColour=&H90000000,"
                f"Outline=1,Shadow=2,Bold=1,Alignment={alignment},MarginV={margin}"
            )
            subtitle_filter_path = str(subtitle_path).replace("\\", "/").replace(":", "\\:")
            subtitle_graph_filter = f"subtitles=filename='{subtitle_filter_path}':force_style='{subtitle_style}'"
            if not bg_mode and not ai_bg_mode:
                filters.append(subtitle_graph_filter)
        if freeze_last_frame:
            filters.append(f"tpad=stop_mode=clone:stop_duration={freeze_duration}")
            prompt_notes.append(f"Final frame held for {freeze_duration}s")
        filters.append("setsar=1")
        filters.append("format=yuv420p")
        video_crf = {"Best quality": "18", "Balanced": "21", "Smaller file": "25"}[export_size]
        audio_filters = []
        if not mute_audio and audio_denoise:
            audio_filters.append("afftdn=nr=12:nf=-25")
        if not mute_audio and voice_clarity:
            audio_filters.extend(["highpass=f=80", "lowpass=f=12000",
                                  "acompressor=threshold=0.125:ratio=2:attack=20:release=250:makeup=1.5"])
        # Keep video and voice speed matched; B-Roll intentionally preserves original timing.
        if not mute_audio and not (broll_mode and broll_assets):
            if prompt_smooth:
                audio_filters.append("atempo=0.5")
            elif speed_factor != 1.0:
                audio_filters.append(f"atempo={speed_factor:g}")
        if not mute_audio and audio_volume != 100:
            audio_filters.append(f"volume={audio_volume / 100:.2f}")

        cmd = [ffmpeg, "-y"]
        if trim_clip:
            cmd += ["-ss", str(trim_start), "-i", str(source), "-t", str(trim_duration)]
        else:
            cmd += ["-i", str(source)]
        if broll_mode and broll_assets:
            if prompt_smooth or speed_factor != 1.0:
                st.warning("B-Roll modeలో speed change apply చేయలేదు; speaker voice sync అలాగే ఉంచాం. మిగతా enhancement settings apply అవుతాయి.")
            valid_timeline = sorted(broll_timeline, key=lambda item: item[0])
            previous_end = 0.0
            timeline_error = None
            for cue_start, cue_end, cue_asset in valid_timeline:
                if cue_end <= cue_start:
                    timeline_error = f"{cue_asset.name}: End time Start time కంటే ఎక్కువగా ఉండాలి."
                    break
                if cue_start < previous_end:
                    timeline_error = "B-Roll timings overlap అవుతున్నాయి. ప్రతి visualకు వేర్వేరు time range ఇవ్వు."
                    break
                if cue_start < 0:
                    timeline_error = "Start time 0 లేదా అంతకంటే ఎక్కువగా ఉండాలి."
                    break
                previous_end = cue_end
            if timeline_error:
                st.error(timeline_error)
                st.stop()

            broll_paths = []
            for bidx, (_, _, asset) in enumerate(valid_timeline, start=1):
                bpath = Path(tmp) / f"broll_{bidx}{Path(asset.name).suffix.lower()}"
                bpath.write_bytes(asset.getvalue())
                broll_paths.append(bpath)

            # Normalize every source segment to the selected output canvas.
            common = [
                item for item in filters
                if not item.startswith(("scale=", "crop=", "pad=", "subtitles=", "setsar=", "format="))
                and item not in ["setpts=2*PTS", "minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir"]
                and not item.startswith("setpts=PTS/")
                and not item.startswith("tpad=")
            ]
            if framing == "Fill frame (crop edges)":
                canvas_filter = (
                    f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
                    f"crop={w}:{h},setsar=1,fps=30,format=yuv420p"
                )
            else:
                canvas_filter = (
                    f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,"
                    f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=30,format=yuv420p"
                )
            common_chain = (",".join(common) + ",") if common else ""
            graph_parts = []
            segment_labels = []
            input_index = 1
            cursor = 0.0
            segment_index = 0
            main_count = 1
            gap_cursor = 0.0
            for cue_start, cue_end, _ in valid_timeline:
                if cue_start > gap_cursor:
                    main_count += 1
                gap_cursor = cue_end
            # Add all B-roll inputs first so FFmpeg input indices stay deterministic.
            for bpath in broll_paths:
                if bpath.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                    cmd += ["-loop", "1", "-i", str(bpath)]
                else:
                    cmd += ["-stream_loop", "-1", "-i", str(bpath)]
            # Split the original video stream when multiple speaker segments are needed.
            if main_count > 1:
                split_outputs = "".join(f"[main_src{i}]" for i in range(main_count))
                graph_parts.append(f"[0:v]split={main_count}{split_outputs}")
            main_source_index = 0
            speaker_side_index = 1 + len(valid_timeline)
            if broll_side_by_side:
                # A second source input keeps the speaker visible during each B-roll cue.
                if trim_clip:
                    cmd += ["-ss", str(trim_start), "-i", str(source)]
                else:
                    cmd += ["-i", str(source)]
                side_outputs = "".join(f"[speaker_side{i}]" for i in range(len(valid_timeline)))
                graph_parts.append(f"[{speaker_side_index}:v]split={len(valid_timeline)}{side_outputs}")

            for cue_index, (cue_start, cue_end, cue_asset) in enumerate(valid_timeline):
                if cue_start > cursor:
                    label = f"main{segment_index}"
                    main_source = f"[main_src{main_source_index}]" if main_count > 1 else "[0:v]"
                    graph_parts.append(
                        f"{main_source}trim=start={cursor}:end={cue_start},setpts=PTS-STARTPTS,"
                        f"{common_chain}{canvas_filter}[{label}]"
                    )
                    main_source_index += 1
                    segment_labels.append(f"[{label}]")
                    segment_index += 1

                bpath = broll_paths[cue_index]
                duration = cue_end - cue_start
                label = f"broll{segment_index}"
                if broll_side_by_side:
                    panel_w = max(2, (w // 2) // 2 * 2)
                    visual_w = w - panel_w
                    speaker_label = f"speaker_panel{segment_index}"
                    visual_label = f"visual_panel{segment_index}"
                    speaker_panel_filter = (
                        f"scale={panel_w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,"
                        f"pad={panel_w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=30,format=yuv420p"
                    )
                    visual_panel_filter = (
                        f"scale={visual_w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
                        f"crop={visual_w}:{h},setsar=1,fps=30,format=yuv420p"
                    )
                    graph_parts.append(
                        f"[speaker_side{cue_index}]trim=start={cue_start}:end={cue_end},setpts=PTS-STARTPTS,"
                        f"{common_chain}{speaker_panel_filter}[{speaker_label}]"
                    )
                    visual_motion = ""
                    if bpath.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                        visual_motion = (
                            f",zoompan=z='min(zoom+0.0012,1.07)':"
                            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                            f"d=1:s={visual_w}x{h}:fps=30"
                        )
                    fade_duration = min(0.18, max(0.05, duration / 3.0))
                    visual_transition = (
                        f",fade=t=in:st=0:d={fade_duration:g}:color=black,"
                        f"fade=t=out:st={max(0.0, duration - fade_duration):g}:"
                        f"d={fade_duration:g}:color=black"
                    )
                    graph_parts.append(
                        f"[{1 + cue_index}:v]trim=duration={duration},setpts=PTS-STARTPTS,"
                        f"{common_chain}{visual_panel_filter}{visual_motion}{visual_transition}[{visual_label}]"
                    )
                    graph_parts.append(
                        f"[{speaker_label}][{visual_label}]hstack=inputs=2:shortest=1[{label}]"
                    )
                else:
                    visual_motion = ""
                    if bpath.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                        visual_motion = (
                            f",zoompan=z='min(zoom+0.0012,1.07)':"
                            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                            f"d=1:s={w}x{h}:fps=30"
                        )
                    fade_duration = min(0.18, max(0.05, duration / 3.0))
                    visual_transition = (
                        f",fade=t=in:st=0:d={fade_duration:g}:color=black,"
                        f"fade=t=out:st={max(0.0, duration - fade_duration):g}:"
                        f"d={fade_duration:g}:color=black"
                    )
                    graph_parts.append(
                        f"[{1 + cue_index}:v]trim=duration={duration},setpts=PTS-STARTPTS,"
                        f"{common_chain}{canvas_filter}{visual_motion}{visual_transition}[{label}]"
                    )
                segment_labels.append(f"[{label}]")
                segment_index += 1
                cursor = cue_end

            # Keep the remainder of the speaker video after the last B-Roll cue.
            label = f"main{segment_index}"
            main_source = f"[main_src{main_source_index}]" if main_count > 1 else "[0:v]"
            graph_parts.append(
                f"{main_source}trim=start={cursor},setpts=PTS-STARTPTS,"
                f"{common_chain}{canvas_filter}[{label}]"
            )
            segment_labels.append(f"[{label}]")
            concat_inputs = "".join(segment_labels)
            graph_parts.append(
                f"{concat_inputs}concat=n={len(segment_labels)}:v=1:a=0[vbase]"
            )
            final_video_chain = "[vbase]"
            if freeze_last_frame:
                graph_parts.append(f"{final_video_chain}tpad=stop_mode=clone:stop_duration={freeze_duration}[vhold]")
                final_video_chain = "[vhold]"
            if subtitle_graph_filter:
                graph_parts.append(f"{final_video_chain}{subtitle_graph_filter}[vsub]")
                final_video_chain = "[vsub]"
            graph_parts.append(f"{final_video_chain}format=yuv420p[v]")
            cmd += ["-filter_complex", ";".join(graph_parts), "-map", "[v]", "-map", "0:a?", "-shortest"]

            if mute_audio:
                cmd += ["-an"]
            else:
                broll_audio_filters = [item for item in audio_filters if item != "atempo=0.5"]
                if broll_audio_filters:
                    cmd += ["-filter:a", ",".join(broll_audio_filters)]
                cmd += ["-c:a", "aac", "-b:a", "192k"]
            cmd += [
                "-c:v", "libx264", "-preset", "veryfast", "-crf", video_crf,
                "-movflags", "+faststart", str(output),
            ]
            with st.spinner("B-Roll visualsను speaker voiceతో sync చేస్తున్నాను..."):
                try:
                    broll_result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
                    if broll_result.returncode != 0 or not output.exists() or output.stat().st_size == 0:
                        st.error("B-Roll video render కాలేదు.")
                        st.code((broll_result.stderr or broll_result.stdout or "FFmpeg error")[-3500:])
                        st.stop()
                    edited = output.read_bytes()
                    st.success("B-Roll visuals videoలో కలిశాయి! Original voice కొనసాగుతుంది.")
                    st.video(edited)
                    st.download_button(
                        "⬇️ Download B-Roll edited MP4",
                        data=edited,
                        file_name="macherla-guru-broll-edited.mp4",
                        mime="video/mp4",
                        type="primary",
                    )
                except subprocess.TimeoutExpired:
                    st.error("B-Roll renderకు ఎక్కువ సమయం పట్టింది. చిన్న clipతో ప్రయత్నించు.")
                except Exception as exc:
                    st.error(f"B-Roll render error: {exc}")
            st.stop()

        if bg_mode and background is not None:
            bg_path = Path(tmp) / ("background" + Path(background.name).suffix.lower())
            bg_path.write_bytes(background.getvalue())
            bg_is_video = bg_path.suffix.lower() in [".mp4", ".mov", ".mkv", ".webm"]
            cmd += (["-stream_loop", "-1", "-i", str(bg_path)] if bg_is_video else ["-loop", "1", "-i", str(bg_path)])
            # Preserve alpha while applying chroma-key and compositing.
            fg_chain = ",".join(
                item for item in filters
                if not item.startswith(("scale=", "crop=", "pad=", "subtitles=", "setsar=", "format="))
            )
            key_hex = "0x00FF00" if key_color == "Green" else "0x0000FF"
            fg_finish = (
                f"chromakey={key_hex}:{key_similarity}:{key_blend},format=yuva420p,"
                f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black@0,setsar=1"
            )
            graph = (
                f"[0:v]{fg_chain},{fg_finish}[fg];"
                f"[1:v]scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={w}:{h},setsar=1[bg];"
                f"[bg][fg]overlay=0:0:shortest=1"
                f"{',' + subtitle_graph_filter if subtitle_graph_filter else ''},format=yuv420p[v]"
            )
            cmd += ["-filter_complex", graph, "-map", "[v]", "-map", "0:a?"]
        elif ai_bg_mode and background is not None:
            # AI segmentation is deliberately limited to short clips to protect free CPU/RAM.
            from rembg import new_session, remove

            bg_path = Path(tmp) / ("ai_background" + Path(background.name).suffix.lower())
            bg_path.write_bytes(background.getvalue())
            frames_dir = Path(tmp) / "ai_frames"
            frames_dir.mkdir()
            extract_cmd = [ffmpeg, "-y"]
            if trim_clip:
                extract_cmd += ["-ss", str(trim_start), "-i", str(source), "-t", str(trim_duration)]
            else:
                extract_cmd += ["-i", str(source)]
            extract_cmd += ["-vf", f"fps={ai_fps},scale={ai_width}:-2:flags=lanczos",
                            "-frames:v", "301", str(frames_dir / "frame_%06d.png")]
            extract = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=600)
            frame_paths = sorted(frames_dir.glob("frame_*.png"))
            if extract.returncode != 0:
                st.error("AI cutout కోసం video frames extract కాలేదు.")
                st.code((extract.stderr or extract.stdout or "")[-2500:])
                st.stop()
            if len(frame_paths) > 300:
                st.error(f"AI cutoutలో {300 / ai_fps:.0f} seconds పరిమితి దాటింది. AI FPS తగ్గించు లేదా చిన్న clip ఎంచుకో.")
                st.stop()
            if not frame_paths:
                st.error("Videoలో frames కనిపించలేదు.")
                st.stop()

            try:
                with st.spinner("AI model load చేస్తున్నాను. మొదటిసారి model download కావచ్చు..."):
                    model_name = "isnet-general-use" if ai_subject_type == "General subject / objects" else "u2net_human_seg"
                    session = new_session(model_name)
                progress = st.progress(0, text="AI background removal ప్రారంభమవుతోంది...")
                for frame_index, frame_path in enumerate(frame_paths, start=1):
                    frame_bytes = frame_path.read_bytes()
                    if refine_edges:
                        cutout = remove(
                            frame_bytes,
                            session=session,
                            only_mask=False,
                            alpha_matting=True,
                            alpha_matting_foreground_threshold=240,
                            alpha_matting_background_threshold=10,
                            alpha_matting_erode_size=10,
                        )
                    else:
                        cutout = remove(frame_bytes, session=session, only_mask=False)
                    frame_path.write_bytes(cutout)
                    if frame_index == 1 or frame_index % 5 == 0 or frame_index == len(frame_paths):
                        progress.progress(
                            frame_index / len(frame_paths),
                            text=f"AI cutout: {frame_index}/{len(frame_paths)} frames"
                        )
                progress.empty()
            except Exception as exc:
                st.error("AI model download లేదా background removalలో సమస్య వచ్చింది.")
                st.code(str(exc)[-2500:])
                st.stop()
            sequence = str(frames_dir / "frame_%06d.png")
            # Apply the same enhancement and prompt presets after compositing.
            # The final scale/pad filters are omitted because the composite is already sized.
            ai_post_filters = [
                item for item in filters
                if not item.startswith(("scale=", "crop=", "pad=", "subtitles=", "setsar=", "format="))
            ]
            # AI cutout frames use the selected sampling rate to bound CPU/RAM use.
            # Upsample the final timeline to a standard delivery rate when the user
            # chooses to keep the original frame rate; this avoids a 12-fps MP4.
            if fps_choice == "Keep original":
                ai_post_filters.append("fps=30")
            post_chain = ("," + ",".join(ai_post_filters)) if ai_post_filters else ""
            if ai_bg_layout == "Fill screen (crop edges)":
                bg_filter = f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h}"
            else:
                bg_filter = f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black"
            filter_graph = (
                f"[0:v]{bg_filter},setsar=1[bg];"
                f"[1:v]scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black@0,setsar=1[fg];"
                f"[bg][fg]overlay=0:0:shortest=1{post_chain}"
                f"{',' + subtitle_graph_filter if subtitle_graph_filter else ''},format=yuv420p[v]"
            )
            ai_cmd = [
                ffmpeg, "-y",
                *(["-stream_loop", "-1"] if bg_path.suffix.lower() in [".mp4", ".mov", ".mkv", ".webm"] else ["-loop", "1"]),
                "-i", str(bg_path),
                "-framerate", str(ai_fps), "-start_number", "1", "-i", sequence,
            ]
            if trim_clip:
                ai_cmd += ["-ss", str(trim_start)]
            ai_cmd += ["-i", str(source), "-filter_complex", filter_graph,
                "-map", "[v]", "-map", "2:a?", "-shortest"]
            if mute_audio:
                ai_cmd += ["-an"]
            else:
                if audio_filters:
                    ai_cmd += ["-filter:a", ",".join(audio_filters)]
                ai_cmd += ["-c:a", "aac", "-b:a", "192k"]
            ai_cmd += [
                "-c:v", "libx264", "-preset", "veryfast", "-crf", video_crf,
                "-movflags", "+faststart", str(output),
            ]
            result = subprocess.run(ai_cmd, capture_output=True, text=True, timeout=1800)
            if result.returncode != 0 or not output.exists():
                st.error("AI background replacement పూర్తి కాలేదు.")
                st.code((result.stderr or result.stdout or "Unknown FFmpeg error")[-3500:])
                st.stop()
            edited = output.read_bytes()
            st.success("AI background replacement పూర్తయింది! Final MP4 సిద్ధంగా ఉంది.")
            st.video(edited)
            st.download_button("⬇️ Download edited MP4", data=edited,
                               file_name="macherla-guru-ai-background.mp4",
                               mime="video/mp4", type="primary")
            st.stop()
        else:
            cmd += ["-vf", ",".join(filters), "-map", "0:v:0", "-map", "0:a?"]

        if mute_audio:
            cmd += ["-an"]
        else:
            if audio_filters:
                cmd += ["-filter:a", ",".join(audio_filters)]
            cmd += ["-c:a", "aac", "-b:a", "192k"]
        cmd += [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", video_crf,
            "-movflags", "+faststart", str(output),
        ]

        with st.spinner("వీడియోను process చేస్తున్నాను. వీడియో పొడవు, server resources బట్టి సమయం పడుతుంది..."):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
                if result.returncode != 0 or not output.exists():
                    details = (result.stderr or result.stdout or "Unknown FFmpeg error")[-3500:]
                    st.error("Video processing పూర్తి కాలేదు.")
                    st.code(details)
                else:
                    edited = output.read_bytes()
                    st.success("Editing పూర్తయింది! Final MP4 సిద్ధంగా ఉంది.")
                    if prompt_notes:
                        st.caption("Prompt effects applied: " + ", ".join(prompt_notes))
                    st.video(edited)
                    st.download_button(
                        "⬇️ Download edited MP4",
                        data=edited,
                        file_name="macherla-guru-edited.mp4",
                        mime="video/mp4",
                        type="primary",
                    )
            except subprocess.TimeoutExpired:
                st.error("ఈ వీడియో process చేయడానికి ఎక్కువ సమయం పట్టింది. చిన్న clipతో మళ్లీ ప్రయత్నించు.")
            except Exception as exc:
                st.error(f"Editing error: {exc}")

st.divider()
st.caption(
    "Free engine: FFmpeg. ఈ buildలో video denoise, camera-shake reduction, audio noise cleanup, voice clarity, "
    "playback speed, color correction, sharpening, slow-motion interpolation, 1080p/2K export, frame fit/crop, "
    "audio mute/volume, MP4 quality-size presets ఉన్నాయి. "
    "AI any-background subject cutout short clipsకే experimental modeలో ఉంది; "
    "Gemini automatic Telugu/English captions and SRT burn-in ఉన్నాయి; advanced object tracking ఇంకా లేదు."
)
