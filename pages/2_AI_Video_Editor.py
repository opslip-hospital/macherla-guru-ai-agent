import os
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg
import streamlit as st

st.set_page_config(page_title="Macherla Guru AI Video Editor", page_icon="🎞️", layout="wide")
st.title("🎞️ Macherla Guru — AI Video Editor")
st.caption("Free-first video editing • FFmpeg engine • YouTube Manager remains separate")

st.info(
    "ఈ Editor YouTube Managerకి వేరే Streamlit page. ఇక్కడ చేసే edits అసలు YouTube channelకి upload కావు. "
    "Final MP4ని నువ్వే download చేసుకుని ఉపయోగించవచ్చు."
)

video = st.file_uploader("ముందుగా వీడియో upload చేయి", type=["mp4", "mov", "mkv", "webm", "avi"])
if not video:
    st.markdown("### అందుబాటులో ఉన్న editing options")
    st.write("Quality enhance • Denoise • Sharpen • Smooth slow motion • 1080p / 2K export • Aspect ratio conversion")
    st.write("Green-screen footage ఉంటే కొత్త background image కూడా పెట్టవచ్చు.")
    st.stop()

left, right = st.columns(2)
with left:
    aspect = st.selectbox("Video format", ["9:16 Shorts / Reels", "16:9 YouTube", "1:1 Square"])
    resolution = st.selectbox("Export quality", ["1080p", "2K"], index=1)
    smooth = st.checkbox("Smooth slow motion (50% speed)", value=False)
    denoise = st.checkbox("Noise reduction", value=True)
    sharpen = st.checkbox("Sharpen details", value=True)
with right:
    brightness = st.slider("Brightness", -0.20, 0.20, 0.0, 0.01)
    contrast = st.slider("Contrast", 0.70, 1.50, 1.05, 0.05)
    saturation = st.slider("Color saturation", 0.0, 2.0, 1.05, 0.05)
    fps_choice = st.selectbox("Frame rate", ["Keep original", "30 FPS", "60 FPS"])
    bg_mode = st.checkbox("Chroma-key background replace (green/blue screen footage only)", value=False)

background = None
if bg_mode:
    key_color = st.selectbox("Original screen color", ["Green", "Blue"])
    key_similarity = st.slider("Green/blue removal strength", 0.05, 0.45, 0.18, 0.01)
    key_blend = st.slider("Edge blending", 0.00, 0.25, 0.08, 0.01)
    background = st.file_uploader("కొత్త background image", type=["jpg", "jpeg", "png", "webp"])
    st.caption("గమనిక: ఇది green/blue chroma-key footageకే. Removal strength ఎక్కువ చేస్తే subject edges కూడా పోవచ్చు. సాధారణ వీడియోకు AI background cutout ఇంకా లేదు.")

st.caption(
    "2K export అంటే 1440p output. చిన్న resolution వీడియోను 2Kగా export చేయవచ్చు, "
    "కానీ లేని original detail తిరిగి సృష్టించబడదు. Smooth slow motionలో motion artifacts రావచ్చు."
)

edit_prompt = st.text_area(
    "Optional editing prompt",
    placeholder="ఉదా: cinematic look, face softening, bright colours, smooth slow motion, sharp quality",
    help="ఈ మొదటి versionలో promptలోని సాధారణ keywords ఆధారంగా కొన్ని FFmpeg effects ఆటోమేటిక్‌గా apply అవుతాయి."
)

if st.button("✨ Edit video & create MP4", type="primary", disabled=(bg_mode and background is None)):
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
        if denoise:
            filters.append("hqdn3d=1.5:1.5:6:6")
        filters.append(f"eq=brightness={brightness}:contrast={contrast}:saturation={saturation}")
        if sharpen:
            filters.append("unsharp=5:5:0.7:3:3:0.0")
        if smooth:
            filters.extend(["setpts=2*PTS", "minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir"])
        if fps_choice == "30 FPS":
            filters.append("fps=30")
        elif fps_choice == "60 FPS" and not smooth:
            filters.append("fps=60")
        filters.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos")
        filters.append(f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2")
        filters.append("setsar=1")
        filters.append("format=yuv420p")

        cmd = [ffmpeg, "-y", "-i", str(source)]
        if bg_mode and background is not None:
            bg_path = Path(tmp) / ("background" + Path(background.name).suffix.lower())
            bg_path.write_bytes(background.getvalue())
            cmd += ["-loop", "1", "-i", str(bg_path)]
            # Keep the foreground alpha channel through scaling and compositing.
            # The final four filters in the normal path are scale, pad, setsar, format;
            # apply the visual adjustments before chroma-keying instead.
            fg_chain = ",".join(filters[:-4])
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
                f"[bg][fg]overlay=0:0:shortest=1,format=yuv420p[v]"
            )
            cmd += ["-filter_complex", graph, "-map", "[v]", "-map", "0:a?"]
        else:
            cmd += ["-vf", ",".join(filters), "-map", "0:v:0", "-map", "0:a?"]

        if smooth:
            cmd += ["-filter:a", "atempo=0.5"]
        cmd += [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            str(output),
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
    "Free engine: FFmpeg. ఈ buildలో actual video processing, denoise, color correction, sharpening, "
    "slow-motion interpolation, 1080p/2K export ఉన్నాయి. AI subject cutout, automatic Telugu captions, "
    "advanced object tracking, one-tap background removal ఇంకా ఇందులో లేవు."
)
