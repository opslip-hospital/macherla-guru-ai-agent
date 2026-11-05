import json
import os
import re
import time

import requests
import streamlit as st

st.set_page_config(page_title="Viral Video Optimizer", page_icon="🚀", layout="wide")
st.title("🚀 YouTube Viral Video Optimizer")
st.caption("నీ వీడియోనే analyze చేసి Title, Caption, Hashtags, SEO keywords తయారు చేస్తుంది. కొత్త video ideas ఇవ్వదు.")

try:
    GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
except Exception:
    GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

api_key = GEMINI_KEY or st.text_input("Gemini API key", type="password")
st.info("వీడియోలోని visuals, dialogue, language, topic, audience appeal ఆధారంగా metadata తయారవుతుంది. Viral అవుతుందని guarantee కాదు; misleading tags లేదా unrelated hashtags ఇవ్వదు.")

uploaded = st.file_uploader("నీ YouTube వీడియోను ఎంచుకో", type=["mp4", "mov", "mpeg", "mpg", "webm", "wmv", "3gpp"])
language = st.selectbox("Output language", ["Telugu (తెలుగు ప్రేక్షకుల కోసం)", "Telugu + English mix", "English"])
audience = st.text_input("Target audience (optional)", value="Telugu audience")
extra = st.text_area("ఏదైనా ప్రత్యేక సందర్భం / context (optional)", placeholder="ఉదా: PJ Babu comedy short, mythological scene...")
run = st.button("Analyze video & create viral package", type="primary", disabled=not (uploaded and api_key))

def gemini_video_analysis(video_bytes, mime_type, filename, key, language_choice, target, context):
    if len(video_bytes) > 100 * 1024 * 1024:
        raise ValueError("100 MB కంటే చిన్న వీడియోను ఎంచుకో.")

    start = requests.post(
        "https://generativelanguage.googleapis.com/upload/v1beta/files",
        headers={
            "x-goog-api-key": key,
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Header-Content-Length": str(len(video_bytes)),
            "X-Goog-Upload-Header-Content-Type": mime_type,
            "Content-Type": "application/json",
        },
        json={"file": {"display_name": filename}},
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

    state = info.get("state", "PROCESSING")
    for _ in range(60):
        if state == "ACTIVE":
            break
        if state == "FAILED":
            raise RuntimeError("Gemini వీడియోను process చేయలేకపోయింది.")
        time.sleep(2)
        check = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/" + file_name,
            headers={"x-goog-api-key": key},
            timeout=30,
        )
        check.raise_for_status()
        info = check.json()
        state = info.get("state", "")
    if state != "ACTIVE":
        raise RuntimeError("Video processing timeout. చిన్న వీడియోతో మళ్లీ ప్రయత్నించు.")

    prompt = f"""
You are a YouTube Shorts and Telugu entertainment metadata strategist.
Analyze ONLY the uploaded video. Do NOT invent new video ideas or alter its actual story.
Language preference: {language_choice}
Target audience: {target}
Extra context supplied by creator: {context or "None"}

Watch/listen to the actual video. Identify its real topic, language, characters, emotion, genre,
strongest moment, likely audience, and whether it is comedy, story, devotional, mythological,
news, or another format. Do not guess names or claims that are not clear from the video.

Create an honest, high-quality YouTube optimization package:
- 3 distinct clickable but accurate title options; put the strongest first.
- One natural Telugu-first description/caption with a compelling first line, a concise summary,
  and a genuine viewer engagement question. No fake claims, keyword stuffing, or begging.
- 3 to 5 highly relevant hashtags only. Include #Shorts only if the video is clearly a Short.
  Do not use unrelated trending tags.
- 8 to 12 search tags/keywords, comma-separated, directly related to the video.
- 2 alternate opening-hook text ideas ONLY as optional on-screen/caption hooks; do not suggest
  changing or re-editing the video.
- 2 to 4 word thumbnail text, only if useful.
- A short explanation of why these choices fit the actual video.
- A cautious packaging score from 1 to 100, explicitly NOT a prediction of views or virality.
Return ONLY valid JSON with keys:
video_summary, genre, language_detected, title_options (array of 3 strings),
description, hashtags (array of 3 to 5 strings), seo_keywords (array of 8 to 12 strings),
hook_options (array of 2 strings), thumbnail_text, packaging_score, score_note, rationale.
Make all public-facing copy in the selected language. Keep it natural and culturally appropriate.
"""
    payload = {
        "contents": [{"parts": [
            {"file_data": {"mime_type": mime_type, "file_uri": file_uri}},
            {"text": prompt},
        ]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7},
    }
    response = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json=payload,
        timeout=300,
    )
    response.raise_for_status()
    data = response.json()
    text_parts = [
        part["text"]
        for candidate in data.get("candidates", [])
        for part in candidate.get("content", {}).get("parts", [])
        if isinstance(part.get("text"), str)
    ]
    raw = "\n".join(text_parts).replace("```json", "").replace("```", "").strip()
    result = json.loads(raw)
    if not isinstance(result, dict) or not result.get("title_options") or not result.get("description"):
        raise RuntimeError("Gemini response incomplete. మళ్లీ ప్రయత్నించు.")
    return result

if run:
    try:
        with st.spinner("వీడియోను Gemini analyze చేస్తోంది... కొద్దిసేపు వేచి ఉండు."):
            result = gemini_video_analysis(
                uploaded.getvalue(),
                uploaded.type or "video/mp4",
                uploaded.name,
                api_key,
                language,
                audience,
                extra,
            )
        st.session_state["viral_optimizer_result"] = result
        st.success("Video analysis complete. నీ వీడియోకు సరిపోయే package సిద్ధమైంది.")
    except requests.HTTPError as exc:
        detail = ""
        try:
            detail = exc.response.text[:1000]
        except Exception:
            pass
        st.error(f"Gemini API error: {exc}. {detail}")
    except Exception as exc:
        st.error(f"Analysis failed: {exc}")

result = st.session_state.get("viral_optimizer_result")
if result:
    st.divider()
    st.subheader("🎯 Video analysis")
    st.write(result.get("video_summary", ""))
    st.caption(
        f"Genre: {result.get('genre', '—')}  |  Language: {result.get('language_detected', '—')}"
    )
    score = result.get("packaging_score")
    if isinstance(score, (int, float)):
        st.metric("Packaging quality score (not a views prediction)", f"{score}/100")
    st.caption(result.get("score_note", "This score is not a guarantee of reach or virality."))

    st.subheader("🔥 Title options")
    for index, title in enumerate(result.get("title_options", []), 1):
        st.text_input(f"Title {index}", value=str(title), key=f"viral_title_{index}")

    st.subheader("📝 Description / Caption")
    st.text_area("Copy-ready description", value=str(result.get("description", "")), height=220, key="viral_description")

    st.subheader("#️⃣ Relevant hashtags")
    hashtags = result.get("hashtags", [])
    st.code(" ".join(str(tag) for tag in hashtags), language=None)

    st.subheader("🔎 SEO keywords")
    keywords = result.get("seo_keywords", [])
    st.code(", ".join(str(tag) for tag in keywords), language=None)

    st.subheader("⚡ Optional hook lines")
    for hook in result.get("hook_options", []):
        st.write("• " + str(hook))

    if result.get("thumbnail_text"):
        st.subheader("🖼️ Thumbnail text")
        st.write(result["thumbnail_text"])
    if result.get("rationale"):
        st.subheader("Why these fit this video")
        st.write(result["rationale"])

    st.warning("ఇది metadata optimization మాత్రమే. YouTube reach/viral guarantee కాదు. Title, caption, hashtags publish చేసే ముందు నువ్వు review చేయాలి; ఈ page ఏ వీడియోనూ upload లేదా publish చేయదు.")
    copy_bundle = (
        "TITLES\n" + "\n".join(str(x) for x in result.get("title_options", []))
        + "\n\nDESCRIPTION\n" + str(result.get("description", ""))
        + "\n\nHASHTAGS\n" + " ".join(str(x) for x in hashtags)
        + "\n\nSEO KEYWORDS\n" + ", ".join(str(x) for x in keywords)
    )
    st.download_button("Download optimization package (.txt)", data=copy_bundle, file_name="youtube-viral-optimization.txt", mime="text/plain")
