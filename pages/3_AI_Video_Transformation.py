import io
import json
import zipfile
from datetime import datetime, timezone

import streamlit as st


st.set_page_config(page_title="AI Video Transformation", page_icon="🎬", layout="wide")

st.title("🎬 AI Video Transformation Lab")
st.caption("మూల వీడియో + క్యారెక్టర్ రిఫరెన్స్ + తెలుగు సూచన → ట్రాన్స్‌ఫర్మేషన్ జాబ్")

st.info(
    "ఇది మొదటి ప్రోటోటైప్ దశ: మీ వీడియో, క్యారెక్టర్ ఫోటో, తెలుగు కథా సూచనలను "
    "ఒక జాబ్ ప్యాకేజీగా సిద్ధం చేస్తుంది. ప్రస్తుతం ఈ Streamlit సర్వర్‌లో Wan GPU "
    "రెండరింగ్ కనెక్ట్ కాలేదు; కాబట్టి ఇక్కడే MP4 తయారైందని చూపించదు."
)

with st.form("transformation_job_form"):
    left, right = st.columns(2)
    with left:
        source_video = st.file_uploader(
            "1) 5–10 సెకన్ల మూల వీడియో",
            type=["mp4", "mov", "webm"],
            help="చిన్న క్లిప్‌తో మొదలుపెడితే పరీక్ష సులభం.",
        )
        character_image = st.file_uploader(
            "2) క్యారెక్టర్ రిఫరెన్స్ ఫోటో",
            type=["png", "jpg", "jpeg", "webp"],
            help="PJ Babu లుక్ స్పష్టంగా కనిపించే ఒక ఫోటో ఇవ్వండి.",
        )
    with right:
        character_name = st.text_input("క్యారెక్టర్ పేరు", value="PJ Babu")
        task_mode = st.selectbox(
            "ఏ మార్పు కావాలి?",
            [
                "మూల వీడియో కదలికలతో క్యారెక్టర్‌ను యానిమేట్ చేయడం",
                "మూల వీడియోలోని క్యారెక్టర్ స్థానంలో రిఫరెన్స్ క్యారెక్టర్‌ను పెట్టడం",
                "కథ ప్రకారం కొత్త సీన్లు, కొత్త యాక్షన్లు సృష్టించడం (ప్రయోగాత్మక లక్ష్యం)",
            ],
        )
        aspect_ratio = st.selectbox("వీడియో నిష్పత్తి", ["9:16 Shorts", "16:9", "1:1"])
        language = st.selectbox("డైలాగులు / వాయిస్ భాష", ["తెలుగు మాత్రమే"], index=0)

    story_prompt = st.text_area(
        "3) తెలుగులో ఏం జరగాలో వివరించండి",
        placeholder=(
            "ఉదా: యముడు భయపడుతూ దున్నపోతు మీద వస్తాడు. PJ Babu ఏమైందని అడుగుతాడు. "
            "యముడు గిన్నెలు నీట్‌గా తోమలేదని చీపురుతో కొట్టిందని చెబుతాడు."
        ),
        height=150,
    )
    visual_style = st.text_input(
        "విజువల్ స్టైల్",
        value="నిజమైన సినిమాటిక్ 3D CGI, సహజమైన ముఖ కవళికలు, స్మూత్ కెమెరా కదలికలు",
    )
    keep_original_audio = st.checkbox("మూల వీడియో ఆడియోను అలాగే ఉంచాలి", value=False)
    submitted = st.form_submit_button("జాబ్ ప్యాకేజీ సిద్ధం చేయి", type="primary")

if submitted:
    errors = []
    if source_video is None:
        errors.append("మూల వీడియోను ఎంచుకోండి.")
    if character_image is None:
        errors.append("క్యారెక్టర్ రిఫరెన్స్ ఫోటోను ఎంచుకోండి.")
    if not story_prompt.strip():
        errors.append("తెలుగులో కథ / సీన్ సూచన రాయండి.")

    if errors:
        for error in errors:
            st.error(error)
    else:
        video_bytes = source_video.getvalue()
        image_bytes = character_image.getvalue()
        if len(video_bytes) > 100 * 1024 * 1024:
            st.error("వీడియో 100 MB కంటే పెద్దది. చిన్న క్లిప్‌తో ప్రయత్నించండి.")
        else:
            job = {
                "schema_version": 1,
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "character_name": character_name.strip() or "PJ Babu",
                "task_mode": task_mode,
                "aspect_ratio": aspect_ratio,
                "dialogue_language": language,
                "story_prompt_te": story_prompt.strip(),
                "visual_style": visual_style.strip(),
                "keep_original_audio": keep_original_audio,
                "source_video_filename": source_video.name,
                "source_video_mime": source_video.type,
                "character_reference_filename": character_image.name,
                "character_reference_mime": character_image.type,
                "requested_output": "mp4",
                "render_status": "waiting_for_gpu_worker",
                "important_limit": (
                    "Wan2.2 Animate supports character animation/replacement from a driving video "
                    "and a reference image. Arbitrary story-driven scene rewriting needs a separate "
                    "video-generation workflow; this job package does not claim that it has rendered."
                ),
            }

            bundle = io.BytesIO()
            with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("source_video/" + source_video.name, video_bytes)
                archive.writestr("character_reference/" + character_image.name, image_bytes)
                archive.writestr(
                    "job.json",
                    json.dumps(job, ensure_ascii=False, indent=2),
                )
                archive.writestr(
                    "README_TE.txt",
                    "మాచెర్ల గురు AI వీడియో ట్రాన్స్‌ఫర్మేషన్ జాబ్\n"
                    "===========================================\n\n"
                    "ఈ ZIPలో మూల వీడియో, క్యారెక్టర్ ఫోటో, job.json ఉన్నాయి.\n"
                    "ఇది ఇన్‌పుట్ ప్యాకేజీ మాత్రమే; తయారైన MP4 కాదు.\n"
                    "రెండరింగ్ కోసం సరైన GPU worker / Wan2.2 Animate backend అవసరం.\n\n"
                    "గమనిక: క్యారెక్టర్ యానిమేషన్ లేదా రీప్లేస్‌మెంట్ సాధ్యం. "
                    "కథ ప్రకారం పూర్తిగా కొత్త సీన్లు సృష్టించడానికి అదనపు వీడియో జనరేషన్ మోడల్ అవసరం.\n",
                )

            st.success("జాబ్ ప్యాకేజీ సిద్ధమైంది. ఇది ఇంకా రెండర్ చేసిన వీడియో కాదు.")
            st.download_button(
                "⬇️ ట్రాన్స్‌ఫర్మేషన్ జాబ్ ZIP డౌన్‌లోడ్",
                data=bundle.getvalue(),
                file_name="macherla_guru_video_transform_job.zip",
                mime="application/zip",
            )
            with st.expander("జాబ్ వివరాలు చూడండి"):
                st.json(job)

st.divider()
st.subheader("ప్రస్తుత సామర్థ్యం — నిజాయితీగా")
st.markdown(
    "- **క్యారెక్టర్ యానిమేషన్ / రీప్లేస్‌మెంట్:** Wan2.2 Animate వంటి GPU మోడల్‌తో చేయవచ్చు.\n"
    "- **కథకు తగ్గ కొత్త సీన్లు, కొత్త యాక్షన్లు:** ప్రత్యేక text/video generation pipeline అవసరం.\n"
    "- **ఈ పేజీ ప్రస్తుతం:** ఇన్‌పుట్‌లను సేకరించి, తరువాతి GPU worker‌కు సరిపోయే job package తయారు చేస్తుంది.\n"
    "- **YouTube Manager:** ఈ పేజీ దానిని మార్చదు; ఇది వేరే ప్రోటోటైప్ పేజీ మాత్రమే."
)
st.caption("ప్రోటోటైప్ — GPU రెండరింగ్ కనెక్షన్ ఇంకా జోడించాల్సి ఉంది.")
