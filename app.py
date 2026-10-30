import os
import io
import json
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# Streamlit Community Cloud secrets first; local environment variables as fallback.
try:
    API_KEY = st.secrets.get("YOUTUBE_API_KEY", os.getenv("YOUTUBE_API_KEY", ""))
    HANDLE = st.secrets.get("YOUTUBE_HANDLE", os.getenv("YOUTUBE_HANDLE", "@macherlaguru"))
    GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
except Exception:
    API_KEY = os.getenv("YOUTUBE_API_KEY", "")
    HANDLE = os.getenv("YOUTUBE_HANDLE", "@macherlaguru")
    GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

BASE = "https://www.googleapis.com/youtube/v3"

st.set_page_config(page_title="Macherla Guru AI Manager", page_icon="🎬", layout="wide")
st.title("🎬 Macherla Guru — YouTube AI Manager")
st.caption("Free-first channel dashboard • Telugu AI entertainment")

api_key = API_KEY or st.sidebar.text_input("YouTube Data API key", type="password")
handle = st.sidebar.text_input("Channel handle", value=HANDLE)

@st.cache_data(ttl=1800)
def yt_get(endpoint, params):
    response = requests.get(f"{BASE}/{endpoint}", params={**params, "key": api_key}, timeout=20)
    response.raise_for_status()
    return response.json()

def load_channel():
    data = yt_get("channels", {"part":"snippet,statistics,contentDetails", "forHandle":handle.lstrip("@")})
    items = data.get("items", [])
    if not items:
        raise ValueError("Channel not found. Check the handle or API key.")
    return items[0]

if not api_key:
    st.info("Setup needed: add your YouTube Data API key in the sidebar or hosting Secrets.")
    st.markdown("**Your channel is preconfigured:** https://youtube.com/@macherlaguru")
    st.stop()

try:
    channel = load_channel()
    stats = channel.get("statistics", {})
    snippet = channel.get("snippet", {})
    playlist_id = channel.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    c1,c2,c3 = st.columns(3)
    c1.metric("Subscribers", f'{int(stats.get("subscriberCount",0)):,}' if not stats.get("hiddenSubscriberCount") else "Hidden")
    c2.metric("Total views", f'{int(stats.get("viewCount",0)):,}')
    c3.metric("Videos", f'{int(stats.get("videoCount",0)):,}')
    st.subheader(snippet.get("title", "Macherla Guru"))
    st.write(snippet.get("description", ""))
    st.caption(f"Channel ID: {channel.get('id','')}")

    if playlist_id:
        st.subheader("Recent uploads — sorted by views")
        uploads = yt_get("playlistItems", {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": 50
        })
        upload_items = uploads.get("items", [])
        if not upload_items:
            st.warning("YouTube returned no items from the channel uploads playlist. Check that the channel has public uploads.")
        else:
            # Build rows from the uploads playlist first so titles remain visible
            # even if some videos have disabled/unavailable statistics.
            video_ids = []
            rows_by_id = {}
            for item in upload_items:
                item_snippet = item.get("snippet", {})
                content = item.get("contentDetails", {})
                video_id = content.get("videoId") or item_snippet.get("resourceId", {}).get("videoId")
                if not video_id:
                    continue
                video_ids.append(video_id)
                rows_by_id[video_id] = {
                    "Title": item_snippet.get("title", "Untitled video"),
                    "Published": (content.get("videoPublishedAt") or item_snippet.get("publishedAt", ""))[:10],
                    "Views": 0,
                    "Likes": 0,
                    "Comments": 0,
                    "URL": "https://youtu.be/" + video_id
                }

            # Enrich playlist rows with public video statistics.
            for offset in range(0, len(video_ids), 50):
                batch = video_ids[offset:offset + 50]
                video_data = yt_get("videos", {
                    "part": "snippet,statistics",
                    "id": ",".join(batch)
                })
                for video in video_data.get("items", []):
                    video_id = video.get("id")
                    if video_id not in rows_by_id:
                        continue
                    video_stats = video.get("statistics", {})
                    video_snippet = video.get("snippet", {})
                    row = rows_by_id[video_id]
                    row["Title"] = video_snippet.get("title") or row["Title"]
                    row["Published"] = (video_snippet.get("publishedAt") or row["Published"])[:10]
                    row["Views"] = int(video_stats.get("viewCount", 0))
                    row["Likes"] = int(video_stats.get("likeCount", 0))
                    row["Comments"] = int(video_stats.get("commentCount", 0))

            rows = sorted(rows_by_id.values(), key=lambda row: row["Views"], reverse=True)
            if rows:
                st.success(f"Loaded {len(rows)} recent uploads. Showing the top 20 by views.")
                # A simple static table is easier to see on mobile than the interactive grid.
                st.table(rows[:20])
                with st.expander("Open interactive video table"):
                    st.dataframe(rows, use_container_width=True, hide_index=True)
                import pandas as pd
                st.download_button(
                    "Download video report CSV",
                    data=pd.DataFrame(rows).to_csv(index=False),
                    file_name="macherla-guru-videos.csv",
                    mime="text/csv"
                )
            else:
                st.warning("Uploads were found, but no video IDs could be read. Try refreshing the app.")

            st.subheader("AI growth suggestions")
            st.write("Review your top videos, repeat winning formats with fresh stories, and strengthen the first 1–3 seconds. Public data does not include private CTR or audience retention.")
            if GEMINI_KEY:
                st.success("Gemini key detected. AI recommendations can be enabled in the next setup step.")
            else:
                st.info("Add a Gemini API key later for AI-written Telugu titles, descriptions and weekly ideas. The dashboard works without it.")

except requests.HTTPError as e:
    st.error(f"YouTube API error: {e}. Check the API key and YouTube Data API v3 is enabled.")
except Exception as e:
    st.error(str(e))


# YouTube private upload, owner approval, and channel analytics
st.divider()
st.header("📤 వీడియో Upload & YouTube Performance")
st.caption("వీడియోను ముందుగా Privateగా Upload చేసి, నీ Approval తర్వాతే Public చేస్తుంది.")

YT_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

def get_oauth_config():
    try:
        cfg = st.secrets.get("youtube_oauth", {})
        client_id = cfg.get("client_id", "")
        client_secret = cfg.get("client_secret", "")
        redirect_uri = cfg.get("redirect_uri", "")
        if client_id and client_secret and redirect_uri:
            return {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri],
                }
            }, redirect_uri
    except Exception:
        pass
    return None, None

def get_owner_credentials():
    from google.oauth2.credentials import Credentials
    raw = st.session_state.get("youtube_owner_token")
    if not raw:
        return None
    creds = Credentials.from_authorized_user_info(json.loads(raw), YT_SCOPES)
    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        st.session_state["youtube_owner_token"] = creds.to_json()
    return creds if creds.valid else None

oauth_config, oauth_redirect_uri = get_oauth_config()
if "youtube_owner_token" not in st.session_state:
    st.session_state["youtube_owner_token"] = None

# Complete the OAuth callback after the owner returns from Google.
if oauth_config and st.query_params.get("code") and st.session_state.get("youtube_oauth_state"):
    try:
        if st.query_params.get("state") != st.session_state["youtube_oauth_state"]:
            raise ValueError("OAuth state mismatch. Start the YouTube connection again.")
        from google_auth_oauthlib.flow import Flow
        callback_flow = Flow.from_client_config(
            oauth_config,
            scopes=YT_SCOPES,
            state=st.session_state["youtube_oauth_state"],
            redirect_uri=oauth_redirect_uri,
        )
        callback_flow.fetch_token(code=st.query_params.get("code"))
        st.session_state["youtube_owner_token"] = callback_flow.credentials.to_json()
        st.session_state["youtube_oauth_state"] = None
        st.query_params.clear()
        st.success("YouTube channel authorization successful.")
        st.rerun()
    except Exception as exc:
        st.error(f"Google authorization could not be completed: {exc}")

owner_creds = None
try:
    owner_creds = get_owner_credentials()
except Exception as exc:
    st.warning(f"YouTube session needs reconnecting: {exc}")

if not oauth_config:
    st.info(
        "Upload setup is not complete yet. In Streamlit → Settings → Secrets, add a "
        "[youtube_oauth] section with client_id, client_secret and redirect_uri. "
        "Create a Google OAuth Web application and add the exact Streamlit app URL "
        "as an authorized redirect URI."
    )
elif not owner_creds:
    from google_auth_oauthlib.flow import Flow
    if st.button("🔐 Connect my YouTube channel", type="primary"):
        try:
            flow = Flow.from_client_config(oauth_config, scopes=YT_SCOPES, redirect_uri=oauth_redirect_uri)
            auth_url, state = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
            )
            st.session_state["youtube_oauth_state"] = state
            st.link_button("Googleలో అనుమతి ఇవ్వండి", auth_url)
        except Exception as exc:
            st.error(f"Could not start Google authorization: {exc}")
    st.caption("నీ Google accountలో Macherla Guru channel access ఉన్న accountతోనే అనుమతి ఇవ్వాలి.")
else:
    st.success("YouTube channel connected for upload and analytics.")
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    youtube_owner = build("youtube", "v3", credentials=owner_creds, cache_discovery=False)
    analytics_owner = build("youtubeAnalytics", "v2", credentials=owner_creds, cache_discovery=False)

    with st.form("youtube_private_upload_form"):
        uploaded_video = st.file_uploader("వీడియో ఫైల్ ఎంచుకోండి", type=["mp4", "mov", "avi", "webm"])
        upload_title = st.text_input("YouTube Title", max_chars=100)
        upload_description = st.text_area("Description")
        upload_tags_text = st.text_input("Tags (comma separated)", value="Macherla Guru, Telugu Comedy, PJ Babu")
        upload_thumbnail = st.file_uploader("Thumbnail (ఐచ్ఛికం)", type=["jpg", "jpeg", "png"])
        upload_submit = st.form_submit_button("🔒 Privateగా Upload చేయి", type="primary")

    if upload_submit:
        if not uploaded_video or not upload_title.strip():
            st.warning("వీడియో ఫైల్ మరియు Title తప్పనిసరి.")
        else:
            try:
                from googleapiclient.errors import HttpError
                tags = [tag.strip() for tag in upload_tags_text.split(",") if tag.strip()][:500]
                media = MediaIoBaseUpload(
                    io.BytesIO(uploaded_video.getvalue()),
                    mimetype=uploaded_video.type or "video/mp4",
                    chunksize=8 * 1024 * 1024,
                    resumable=True,
                )
                with st.spinner("YouTubeకి Private వీడియో Upload అవుతోంది..."):
                    request = youtube_owner.videos().insert(
                        part="snippet,status",
                        body={
                            "snippet": {
                                "title": upload_title.strip(),
                                "description": upload_description,
                                "tags": tags,
                                "categoryId": "23",
                            },
                            "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False},
                        },
                        media_body=media,
                    )
                    result = None
                    while result is None:
                        _, result = request.next_chunk()
                new_video_id = result["id"]
                st.session_state["last_uploaded_video_id"] = new_video_id
                st.session_state["last_uploaded_video_title"] = upload_title.strip()
                if upload_thumbnail:
                    thumb_media = MediaIoBaseUpload(
                        io.BytesIO(upload_thumbnail.getvalue()),
                        mimetype=upload_thumbnail.type or "image/jpeg",
                        resumable=False,
                    )
                    youtube_owner.thumbnails().set(videoId=new_video_id, media_body=thumb_media).execute()
                st.success("వీడియో Privateగా Upload అయింది. నీ Approval వచ్చే వరకు Public కాదు.")
                st.video(uploaded_video.getvalue())
                st.markdown(f"[YouTubeలో Private Preview తెరువు](https://youtu.be/{new_video_id})")
            except Exception as exc:
                st.error(f"Upload failed: {exc}")

    pending_id = st.session_state.get("last_uploaded_video_id")
    if pending_id:
        st.subheader("నీ Approval కోసం")
        st.write(st.session_state.get("last_uploaded_video_title", "Uploaded video"))
        st.markdown(f"[Private YouTube Preview](https://youtu.be/{pending_id})")
        approve_col, keep_col = st.columns(2)
        with approve_col:
            if st.button("✅ Approve చేసి Public చేయి", type="primary"):
                try:
                    current = youtube_owner.videos().list(part="status", id=pending_id).execute()
                    if not current.get("items"):
                        st.error("ఈ వీడియోను YouTubeలో కనుగొనలేకపోయాం.")
                    else:
                        status = current["items"][0].get("status", {})
                        status["privacyStatus"] = "public"
                        youtube_owner.videos().update(part="status", body={"id": pending_id, "status": status}).execute()
                        st.success("నీ Approvalతో వీడియో Public అయింది!")
                        st.session_state["last_uploaded_video_id"] = None
                except Exception as exc:
                    st.error(f"Publish failed: {exc}")
        with keep_col:
            if st.button("🔐 Privateగానే ఉంచు"):
                st.info("వీడియో Privateగానే ఉంటుంది.")

    st.subheader("📊 వీడియో Analytics")
    analysis_id = st.text_input(
        "YouTube Video ID",
        value=st.session_state.get("last_uploaded_video_id") or "",
        help="ఉదా: https://youtu.be/VIDEO_ID లో చివరి భాగం",
    )
    from datetime import date, timedelta
    end_day = date.today() - timedelta(days=2)
    start_day = end_day - timedelta(days=6)
    date_col1, date_col2 = st.columns(2)
    with date_col1:
        analytics_start = st.date_input("Start date", value=start_day)
    with date_col2:
        analytics_end = st.date_input("End date", value=end_day)
    if st.button("📈 Analytics చూడు"):
        if not analysis_id.strip():
            st.warning("ముందుగా Video ID ఇవ్వండి.")
        elif analytics_end < analytics_start:
            st.warning("End date, Start date తర్వాత ఉండాలి.")
        else:
            try:
                public_data = youtube_owner.videos().list(part="snippet,statistics,status", id=analysis_id.strip()).execute()
                if not public_data.get("items"):
                    st.warning("ఈ Video ID నీ channelలో కనిపించలేదు.")
                else:
                    item = public_data["items"][0]
                    stats = item.get("statistics", {})
                    a, b, c = st.columns(3)
                    a.metric("Views", f'{int(stats.get("viewCount", 0)):,}')
                    b.metric("Likes", f'{int(stats.get("likeCount", 0)):,}')
                    c.metric("Comments", f'{int(stats.get("commentCount", 0)):,}')
                    st.write("Privacy:", item.get("status", {}).get("privacyStatus", "unknown"))
                    report = analytics_owner.reports().query(
                        ids="channel==MINE",
                        startDate=analytics_start.isoformat(),
                        endDate=analytics_end.isoformat(),
                        metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,impressions,impressionClickThroughRate",
                        dimensions="day",
                        filters=f"video=={analysis_id.strip()}",
                        sort="day",
                    ).execute()
                    headers = [h.get("name") for h in report.get("columnHeaders", [])]
                    data_rows = report.get("rows", [])
                    if data_rows:
                        import pandas as pd
                        st.caption("YouTube Analytics (processing delay ఉండవచ్చు; recent 1–2 days data ఇంకా అందుబాటులో లేకపోవచ్చు).")
                        st.dataframe(pd.DataFrame(data_rows, columns=headers), use_container_width=True, hide_index=True)
                    else:
                        st.info("ఈ తేదీలకు Analytics data ఇంకా లేదు. వీడియో కొత్తదైతే కొంత సమయం తర్వాత మళ్లీ ప్రయత్నించు.")
            except Exception as exc:
                st.warning(f"Analytics data ఇప్పుడందుబాటులో లేదు: {exc}")


# Gemini-powered Telugu content studio
st.divider()
st.header("✨ Gemini AI Content Studio")
if not GEMINI_KEY:
    st.info("Gemini API key not detected. Add GEMINI_API_KEY in Streamlit → Settings → Secrets.")
else:
    st.success("Gemini API key detected.")
    content_type = st.selectbox(
        "ఏం తయారు చేయాలి?",
        ["PJ Babu కామెడీ స్క్రిప్ట్", "YouTube Shorts Title + SEO", "Thumbnail Prompt", "Weekly Content Calendar", "Complete Video Package"]
    )
    topic = st.text_area(
        "వీడియో ఐడియా / టాపిక్",
        placeholder="ఉదా: యముడు నరకాన్ని PJ Babu కి అమ్మేశాడు… దాని వెనుక కామెడీ కథ",
        height=90
    )
    extra = st.text_input("అదనపు సూచన (ఐచ్ఛికం)", placeholder="ఉదా: 10 సెకన్ల వీడియో, యమలోకం సెట్")
    if st.button("🚀 Gemini తో Generate చేయి", type="primary"):
        if not topic.strip():
            st.warning("ముందుగా వీడియో టాపిక్ రాయండి.")
        else:
            channel_title = "Macherla Guru"
            try:
                if "snippet" in locals():
                    channel_title = snippet.get("title") or channel_title
                recent_context = ""
                if "rows" in locals() and rows:
                    recent_context = "\n".join(
                        f"- {r.get('Title','')} ({r.get('Views',0)} views)"
                        for r in rows[:8]
                    )
                prompt = f"""
You are a Telugu YouTube Shorts creative strategist for the channel {channel_title}.
Create original, engaging content in natural spoken Telugu (Telugu script), with punchy comedy.
Channel niche: Mixed Telugu AI Entertainment, especially PJ Babu and Yamalokam comedy.
User topic: {topic}
Extra instructions: {extra or 'None'}
Requested output: {content_type}
Recent public channel video context (use only as inspiration, do not copy):
{recent_context or 'Not available'}
Rules:
- Strong hook starts on the very first frame / first spoken line. No slow intro, no dead air, no long pauses.
- Write all spoken dialogue ONLY in natural Telugu script. Never insert Chinese, Thai, Hindi or other foreign-script characters. Do not translate, shorten or silently alter any user-supplied exact dialogue.
- Keep a 10-second video realistic: normally use 2-3 short dialogue turns total, only when each line can be spoken naturally in its allotted time. Never force a third line just to meet a quota. Use fewer turns if the joke is stronger that way; do not overcrowd the take.
- When Requested output is "PJ Babu కామెడీ స్క్రిప్ట్" or "Complete Video Package", ALWAYS include all of these sections:
  1) Telugu comedy script with timestamps, actions and exact dialogue.
  2) A single copy-paste-ready Google Flow video prompt for ONE continuous 10-second take. Start it with: "ULTRA PREMIUM CINEMATIC 3D CGI ANIMATED MOVIE | 4K | GRAND COMEDY FINALE". Specify 9:16 vertical unless the user asks otherwise; colorful ultra-premium 3D CGI; Yamalokam/Narakam palace details when relevant; dramatic mythological lighting and floating flame VFX when relevant. Make the prompt self-contained and ready to paste.
     - Include a precise second-by-second timeline covering 0:00-0:10. For every beat specify: visible action, active speaker (or silent reaction), exact Telugu dialogue, camera framing/movement, and whose lips move.
     - Start the hook immediately at 0:00; no establishing-only delay. The first frame must already show the required character positions. The opening speaker begins immediately; no entrance walk, approach, ramp-walk, or empty camera travel unless explicitly requested. Use a motivated smooth pan/orbit/push-in to the active speaker, then a reaction/punchline move only after the line ends.
     - Preserve the final script dialogue word-for-word in the Flow prompt. The script and Flow prompt must contain exactly the same dialogue, in the same order, with the same speaker names. Never invent a different line in the Flow prompt.
     - Aim for lively, continuous comedy across all 10 seconds. Prefer a clear setup → PJ Babu comeback → strong final punch structure when it fits, but use only as many turns as the story and speaking time allow. The final line must be the strongest joke and must directly connect to the user's premise.
     - Fit dialogue to natural Telugu speaking speed and lip-sync. As a rough guide, keep each line short enough to be delivered clearly in its allotted time; do not cram long sentences. If needed, rewrite the generated script dialogue into concise, natural Telugu before presenting it, preserving the user's core joke and story premise. If the user explicitly supplied exact dialogue, do not alter it; explain if it needs more than 10 seconds.
     - Plan the full 0:00-0:10 with no dead air: immediate hook, quick response, visible reaction/action beat, and a strong final punch/reaction. Give each spoken line enough time, and fill non-speaking moments with purposeful visual comedy, not extra walking or empty pauses.
     - Allocate seconds realistically based on the actual number and length of Telugu words. Do not assign a long dialogue to a 2-second slot. If the lines do not fit, shorten the generated lines first or clearly recommend splitting into two takes rather than claiming they fit.
     - Give each character enough screen time to speak naturally. During a character's line, only that character speaks and lip-syncs; other characters keep mouths closed and react silently. Match mouth movement to Telugu syllables; no overlapping dialogue or off-screen wrong-speaker lip-sync.
     - Describe camera positions and character blocking concretely: who is foreground/background, throne position, distance and relative character scale. Never make an important character tiny or place them incorrectly. Camera movement must be smooth and motivated, not random rapid cuts.
     - State that the take is continuous with no cuts unless the story explicitly requires cuts; if camera changes are requested, use a smooth pan/orbit/push-in within the same take. No unnecessary walking or ramp-walk before the first line.
     - STRICT CAMERA / LIP-SYNC LOCK: This is one uninterrupted take: do not write "cut", "quick cut", "jump cut", "transition", or describe an edit between shots. Connect every framing change with one physically continuous camera move such as a smooth pan, orbit, dolly, or push-in.
     - Keep the camera framed on the active speaker's face throughout that character's complete dialogue. Do not pan away, pull focus to another character, or show a reaction shot while the current speaker is still talking. Move to the next character only after the current line has finished.
     - For a two-character conversation, plan the camera path in dialogue order: hold on speaker one during their full line, smoothly pan/orbit to speaker two and hold during their full line, then smoothly return/orbit to the final speaker and hold for the punchline. Do not force this order if the story has a different speaker order.
     - During every spoken line, the speaker's face and mouth must be clearly visible and centered enough for accurate Telugu lip-sync. Silent characters keep their mouths closed. Avoid wide shots during important dialogue.
     - In the final beat, use a smooth continuous camera move to the final speaker's close-up; do not cut. Keep all character positions and blocking unchanged during the move.
     - End with a clear visual punchline/reaction that fits the remaining seconds; don't add an extra CTA dialogue unless requested.
  3) Character and continuity locks: PJ Babu must match the user's uploaded character-sheet reference exactly (same face shape, eyes, nose, lips, moustache, hairstyle, skin tone and identity; medium build; blue-red-orange checked shirt, blue jeans, wristwatch and white/gray sneakers). Do not redesign, beautify, replace, shrink or drift his face/body/outfit. Tell the user to attach the PJ Babu character-sheet image in Google Flow as the visual reference. Keep Yama consistent with his black-and-gold royal look, crown and moustache. Include Chitragupta ONLY when the user explicitly asks for him or the supplied story/established scene already includes him; never add him by default. If included, he wears traditional accountant attire and MUST NOT wear a crown. Keep character scale, positions, props and palace layout consistent.
     - STRICT NO-INVENTION / CONTINUITY RULE: Use only the characters, props, animals, actions, costumes and locations explicitly requested by the user or already established in the described scene. Never invent extra animals (especially buffaloes), extra characters, drinks, bottles, glasses, tea cups, food, weapons, signs, neon lettering, labels, new furniture, throne redesigns, or unrelated actions for visual comedy. Do not add a prop merely to make a character look stylish or funny. If an object/action is not requested, leave it out.
     - CHARACTER CAST LOCK: Before writing, identify the exact cast from the user's topic and scene instructions. Include ONLY those characters. Chitragupta is NOT a default background character; do not add him to a PJ Babu–Yama two-character scene unless the user names him or the established scene already contains him. Do not add attendants, guards, demons, crowds, narrators or any other background people unless requested. The character list in the script, Flow prompt, and thumbnail must stay consistent.
     - STRICT STORY-PREMISE LOCK: Build the joke directly from the user's stated situation. Do not introduce a new subplot, business model, company/board/lease concept, job-loss angle, contract/agreement, sale deed, ownership paper, receipt, file, document, or other new premise unless the user explicitly mentions it. For example, if the user says Yama sold Narakam to PJ Babu and Yama returns asking for his throne, keep the comedy focused on that exact situation; do not invent a lease agreement or make PJ show a paper. Dialogue may be freshly written and funny, but every line must advance or punch up the exact user-provided story idea without changing its meaning.\n     - NO UNREQUESTED PROPS: Never add a paper, document, file, phone, board, sign, bottle, cup, weapon, or other object as a visual joke unless the user specifically asks for it or it is already part of the described scene. Create comedy through expressions, dialogue, reactions, and body language instead.
     - DIALOGUE QUALITY: Use natural, conversational Telugu that sounds like PJ Babu and Yama. Avoid awkward mixed-language wording, spelling glitches, or unnatural phrases. Keep each line short enough for the assigned seconds and prioritize a memorable punchline over unnecessary extra dialogue.
     - NATURAL PUNCHLINE LOCK: The final punchline must arise directly from the user's exact situation and should resolve or escalate the central joke. Do not introduce unrelated consequences such as losing a job, going to jail, getting married, or becoming poor unless the user introduced that idea. Prefer idiomatic spoken Telugu over forced English-Telugu phrases such as "ఓనర్ సీటు" or "ఓన్ ప్రాపర్టీ"; use simple natural wording a Telugu speaker would actually say.
     - FINAL DIALOGUE / PAYOFF LOCK: For a 10-second comedy script, aim for a complete setup → PJ Babu comeback → final punchline exchange when the speaking time genuinely allows it. The last beat must not default to a silent reaction if a short, natural Telugu punchline can fit. If the story works better with a silent reaction, use it intentionally and label it clearly; never add a random line just to create a third dialogue. The final punchline must be included identically in both the script and Flow timeline, with the correct speaker and visible lip-sync.
     - FIRST-FRAME ACTION LOCK: The first frame must already show the characters in their required positions, and the first dialogue must begin immediately at 0:00. Do not make a character walk in, approach the throne, enter the room, or perform a long setup before speaking unless the user explicitly requests an entrance. Use facial expression or a small reaction while the opening line begins.
     - SCENE-BLOCKING LOCK: Before writing the prompt, decide the exact starting positions of every character and keep them consistent for the full take. State who is seated/standing, which side of the throne they occupy, and approximate distance. Keep important characters at a believable, comparable screen scale; never hide Yama in the far background or make him tiny. Do not change seats, costumes, facial identity, or palace layout mid-take.
     - DIALOGUE-TO-TIMELINE CHECK: Add up the actual spoken lines before assigning timestamps. Give each line enough uninterrupted time for natural Telugu delivery and lip-sync. The script and Flow prompt must match word-for-word, speaker-for-speaker, and in the same order. Do not add, remove, paraphrase, or repeat dialogue in the Flow prompt. Use silent reaction beats only in the remaining time.
     - STORY ENDING LOCK: The final reaction or punchline must pay off the central conflict in the user's topic. Do not invent a new consequence or unrelated joke to fill the last seconds. If a satisfying punchline cannot fit in 10 seconds, make the dialogue shorter without changing the premise; if still not possible, clearly recommend two takes.
     - CHARACTER PERFORMANCE LOCK: PJ Babu's delivery should be energetic, confident Telugu mass-comedy style, with expressive face and natural body language. Yama should react according to the story with clear expressions. Do not make either character speak while the other is delivering a line; silent characters keep their mouths closed.
     - CAPTION / HASHTAG LOCK: For this Macherla Guru output, provide separate Instagram and YouTube captions, each with exactly five relevant hashtags. Avoid stuffing generic unrelated tags. The first caption line must create curiosity without revealing the entire punchline.
     - Respect the user's requested PJ Babu action and blocking exactly. Keep PJ Babu seated on Yama's throne only when the user's topic/scene places him there or an established continuity reference requires it. Otherwise, do not force a throne, sitting pose, walking, or any other default action into the scene. Once the scene's positions are established, keep them consistent unless the user asks for movement.
     - Yama must follow the user's supplied visual reference / established design: black-and-gold royal styling, crown and moustache. Do not add a beard or other facial/hair features unless they are visible in the reference or specifically requested. Do not redesign his face, body, crown or costume.
     - If Yama delivers the final line, end that line on a clear close-up of Yama's face with his mouth visibly lip-syncing the exact Telugu dialogue. PJ Babu stays silently seated on the throne in the same position and reacts only if the script specifies it.
     - THUMBNAIL CAST LOCK: The thumbnail must show only the characters who appear in the user's actual scene/script. Never add Chitragupta or any other character just to fill the composition.
     - No visible writing or graphic text anywhere in the scene, including signs, neon boards, labels or background lettering.
  4) Thumbnail image prompt with expressive readable composition and no unwanted text.
  5) Instagram and YouTube captions. Each caption must begin with a curiosity-driven hook and include exactly 5 relevant hashtags (not 3, not 6); hashtags must match this specific video and the Macherla Guru/PJ Babu Telugu-comedy brand.
- For the Google Flow prompt: no subtitles, captions, title cards, labels, logos or watermarks; no extra characters or unrequested dialogue; no BGM when dialogue clarity is requested. Camera must turn smoothly to the active speaker; actions must happen exactly with the dialogue. Do not add unnecessary walking or ramp-walks before the hook. Avoid violent wording; keep slapstick/fantasy comedy non-graphic.
- Use an energetic Telugu mass-comedy hero delivery for PJ Babu, not a Motu-like voice and do not request an exact real-person voice clone.
- For other Requested output types, answer that requested format only, unless the user explicitly asks for the full package.
- Do not invent channel analytics or guarantee views. Use recent video context only as inspiration, never copy it.
- For thumbnail prompts, specify 9:16 or 16:9 only when appropriate, 4K cinematic 3D CGI, clear expressions, readable composition, and no unwanted text. Show only the characters and props needed for this exact story; keep PJ Babu and Yama large, recognizable, and visually balanced.
Return clean headings and ready-to-use output.
"""
                with st.spinner("Gemini మీ కంటెంట్ తయారు చేస్తోంది..."):
                    request_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent"
                    request_headers = {"x-goog-api-key": GEMINI_KEY, "Content-Type": "application/json"}
                    request_body = {
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": 0.85, "maxOutputTokens": 2400}
                    }
                    # Allow extra time for a cold start and retry once on a transient timeout.
                    response = None
                    for attempt in range(2):
                        try:
                            response = requests.post(
                                request_url,
                                headers=request_headers,
                                json=request_body,
                                timeout=(15, 180)
                            )
                            break
                        except requests.Timeout:
                            if attempt == 1:
                                raise
                    if not response.ok:
                        try:
                            detail = response.json().get("error", {}).get("message", response.text)
                        except Exception:
                            detail = response.text
                        st.error(f"Gemini API error ({response.status_code}): {detail}")
                    else:
                        payload = response.json()
                        generated = "\n".join(
                            part.get("text", "")
                            for candidate in payload.get("candidates", [])
                            for part in candidate.get("content", {}).get("parts", [])
                            if part.get("text")
                        ).strip()
                        if generated:
                            st.markdown(generated)
                            st.download_button(
                                "⬇️ Download content as TXT",
                                data=generated,
                                file_name="macherla-guru-ai-content.txt",
                                mime="text/plain"
                            )
                        else:
                            st.error("Gemini నుంచి text రాలేదు. మరోసారి ప్రయత్నించండి.")
            except requests.RequestException as exc:
                st.error(f"Network error: {exc}")

st.caption("Privacy: API keys must be stored as deployment secrets, never committed to GitHub. This starter dashboard reads public channel/video data only; private YouTube Analytics requires a separate OAuth authorization.")
