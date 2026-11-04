import json
import tempfile
from pathlib import Path

import streamlit as st

from gpu_worker.auto_director import detect_scene_changes, make_comedy_edit_decision
from gpu_worker.comedy_edit import ComedyEditError, render_comedy_edit

st.set_page_config(page_title="PJ Babu Comedy Auto Editor", page_icon="🎬", layout="centered")
st.title("🎬 PJ Babu — Comedy Auto Director")
st.caption("Upload raw animation → detect visual scene changes → apply punch edits → download MP4")
st.info(
    "ఈ టూల్ ఉన్న ఫుటేజ్‌ను మాత్రమే ఎడిట్ చేస్తుంది. కొత్త పాత్రలు/సీన్లు సృష్టించదు. "
    "గరిష్ఠంగా 20 సెకన్లు. అసలు డైలాగ్‌ను అలాగే ఉంచుతుంది."
)

video = st.file_uploader("Raw animated video (MP4/MOV)", type=["mp4", "mov", "mkv", "webm"])
ratio = st.selectbox("Output format", ["9:16 Shorts", "16:9 Landscape", "1:1 Square"], index=0)
ratio_value = {"9:16 Shorts": "9:16", "16:9 Landscape": "16:9", "1:1 Square": "1:1"}[ratio]
intensity = st.select_slider("Comedy punch intensity", options=["Medium", "High", "Extreme"], value="High")
duration = st.slider("Maximum output duration (seconds)", 1, 20, 20)
threshold = st.slider("Scene-change sensitivity", 0.10, 0.60, 0.28, 0.02)
music = st.file_uploader("Optional background music (MP3/WAV/AAC)", type=["mp3", "wav", "aac", "m4a"])
music_volume = st.slider("Background music volume", 0.0, 0.35, 0.12, 0.01)
st.caption(
    "Scene analysis detects visual changes only; it does not understand Telugu dialogue, "
    "recognize faces, or create reaction shots. Telugu captions can be made in the existing AI Video Editor."
)

if st.button("🔥 Auto Director + Comedy Edit", type="primary", disabled=video is None, use_container_width=True):
    with tempfile.TemporaryDirectory(prefix="pj_babu_director_") as temp:
        root = Path(temp)
        source = root / ("source" + (Path(video.name).suffix.lower() or ".mp4"))
        source.write_bytes(video.getvalue())
        music_path = None
        if music is not None:
            music_path = root / ("music" + Path(music.name).suffix.lower())
            music_path.write_bytes(music.getvalue())
        output = root / "pj_babu_comedy_final.mp4"
        try:
            with st.spinner("1/3 వీడియో సీన్లను విశ్లేషిస్తున్నాం…"):
                cuts = detect_scene_changes(str(source), threshold=threshold, max_duration=duration)
                plan = make_comedy_edit_decision(cuts, duration=duration)
            st.subheader("🎬 Auto Director Edit Plan")
            st.write(f"గుర్తించిన visual scene changes: {len(cuts)}")
            if cuts:
                st.write("Punch zoom points: " + ", ".join(f"{x:.2f}s" for x in cuts))
            else:
                st.write("స్పష్టమైన scene cuts గుర్తించలేదు; regular comedy punch zoom rhythm వాడతాం.")
            st.json(plan)
            with st.spinner("2/3 Cinematic reframing, punch zooms, colour polish, audio mix…"):
                rendered = render_comedy_edit(
                    str(source), str(output), aspect_ratio=ratio_value, intensity=intensity,
                    music_file=str(music_path) if music_path else None,
                    music_volume=music_volume, max_duration=duration, punch_times=cuts,
                )
            data = Path(rendered).read_bytes()
            st.success("3/3 Auto comedy edit పూర్తయింది!")
            st.video(data)
            st.download_button(
                "⬇️ Download Final MP4", data=data,
                file_name="pj-babu-comedy-final.mp4", mime="video/mp4",
                type="primary", use_container_width=True,
            )
            st.download_button(
                "⬇️ Download Director Edit Plan (JSON)",
                data=json.dumps(plan, ensure_ascii=False, indent=2).encode("utf-8"),
                file_name="pj-babu-edit-plan.json", mime="application/json",
            )
        except (ComedyEditError, OSError, ValueError) as exc:
            st.error(str(exc))

st.divider()
st.markdown(
    "**ఈ వెర్షన్‌లో:** visual scene-change detection, scene-aware punch zooms, "
    "9:16/16:9/1:1 reframing, contrast/saturation/sharpen polish, original dialogue preservation, "
    "optional low-volume background music, final MP4 + edit-plan export. "
    "ఇంకా పూర్తి కాలేనివి: Telugu speech understanding, automatic subtitle timing, face tracking, "
    "reaction-shot insertion, per-word sound effects, AI lip-sync, new scene generation."
)
