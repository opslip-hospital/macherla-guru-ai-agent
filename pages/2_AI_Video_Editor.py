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
    resolution = st.selectbox("Export quality", ["1080p", "2K"])
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
    background = st.file_uploader("కొత్త background image", type=["jpg", "jpeg", "png", "webp"])
    st.caption("గమనిక: ఇది green/blue chroma-key footageకే. సాధారణ వీడియోలో వ్యక్తిని AIతో background నుంచి వేరు చేసే feature ఈ మొదటి versionలో లేదు.")

st.caption(
    "2K export అంటే 1440p output. చిన్న resolution వీడియోను 2Kగా export చేయవచ్చు, "
    "కానీ లేని original detail తిరిగి సృష్టించబడదు. Smooth slow motionలో motion artifacts రావచ్చు."
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
            # Chroma key is intentionally explicit: it does not remove arbitrary backgrounds.
            fg_chain = ",".join(filters[:-3]) if len(filters) > 3 else ",".join(filters)
            key_hex = "0x00FF00" if key_color == "Green" else "0x0000FF"
            final_scale = f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p"
            graph = (
                f"[0:v]{fg_chain},chromakey={key_hex}:0.18:0.08[fg];"
                f"[1:v]scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h}[bg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{final_scale}[v]"
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
