import tempfile
from pathlib import Path

import streamlit as st

from gpu_worker.comedy_edit import ComedyEditError, render_comedy_edit

st.set_page_config(page_title="PJ Babu Comedy Auto Editor", page_icon="🎬", layout="centered")
st.title("🎬 PJ Babu — Comedy Auto Editor")
st.caption("Raw animated clip → punchy cinematic polish → downloadable MP4")
st.info(
    "ఇది ఉన్న వీడియోనే ఎడిట్ చేస్తుంది. కొత్త పాత్రలు/సీన్లు సృష్టించదు. "
    "గరిష్ఠంగా 20 సెకన్ల క్లిప్; అసలు డైలాగ్ ఆడియో అలాగే ఉంచుతుంది."
)

video = st.file_uploader("Raw animated video (MP4/MOV)", type=["mp4", "mov", "mkv", "webm"])
ratio = st.selectbox("Aspect ratio", ["9:16", "16:9", "1:1"], index=0)
intensity = st.select_slider("Comedy punch intensity", options=["Medium", "High", "Extreme"], value="High")
duration = st.slider("Maximum output duration (seconds)", 1, 20, 20)
music = st.file_uploader("Optional background music (MP3/WAV/AAC)", type=["mp3", "wav", "aac", "m4a"])
music_volume = st.slider("Background music volume", 0.0, 0.35, 0.12, 0.01)
st.caption(
    "తెలుగు subtitles కోసం ప్రస్తుత AI Video Editorలోని Gemini Telugu Captions/SRT Burn-in ఉపయోగించవచ్చు. "
    "ఈ ఆటో ఎడిటర్ అసలు మాటలను మార్చదు."
)

if st.button("🔥 Auto Comedy Edit తయారు చేయి", type="primary", disabled=video is None, use_container_width=True):
    with tempfile.TemporaryDirectory(prefix="pj_babu_comedy_") as temp:
        root = Path(temp)
        source = root / ("source" + (Path(video.name).suffix.lower() or ".mp4"))
        source.write_bytes(video.getvalue())
        music_path = None
        if music is not None:
            music_path = root / ("music" + Path(music.name).suffix.lower())
            music_path.write_bytes(music.getvalue())
        output = root / "pj_babu_comedy_final.mp4"
        try:
            with st.spinner("Zoom punch-ins, cinematic polish, audio balance…"):
                rendered = render_comedy_edit(
                    str(source), str(output), aspect_ratio=ratio, intensity=intensity,
                    music_file=str(music_path) if music_path else None,
                    music_volume=music_volume, max_duration=duration,
                )
            data = Path(rendered).read_bytes()
            st.success("Auto edit పూర్తయింది!")
            st.video(data)
            st.download_button(
                "⬇️ Download Final MP4", data=data,
                file_name="pj-babu-comedy-final.mp4", mime="video/mp4",
                type="primary", use_container_width=True,
            )
        except (ComedyEditError, OSError) as exc:
            st.error(str(exc))

st.divider()
st.markdown(
    "**ఈ buildలో:** 9:16/16:9/1:1 reframing, recurring punch-in zoom, "
    "contrast/saturation/sharpen polish, original dialogue preservation, "
    "optional low-volume background music, MP4 export. "
    "Auto scene understanding, character tracking, automatic reaction inserts, "
    "sound-effect placement, Telugu subtitle generation, and AI lip-sync are not yet included."
)
