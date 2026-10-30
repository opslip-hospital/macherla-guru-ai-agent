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
    "https://www.googleapis.com/auth/youtube.force-ssl",
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

def get_supabase_config():
    try:
        cfg = st.secrets.get("supabase", {})
        url = cfg.get("url", st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL", "")))
        secret_key = cfg.get("secret_key", st.secrets.get("SUPABASE_SECRET_KEY", os.getenv("SUPABASE_SECRET_KEY", "")))
        return (url.rstrip("/"), secret_key) if url and secret_key else None
    except Exception:
        url = os.getenv("SUPABASE_URL", "")
        secret_key = os.getenv("SUPABASE_SECRET_KEY", "")
        return (url.rstrip("/"), secret_key) if url and secret_key else None

def token_cipher():
    # Derive an app-specific encryption key from the OAuth client secret.
    # The key is never stored in the database or committed to source control.
    import base64
    from cryptography.fernet import Fernet
    secret = oauth_config["web"]["client_secret"].encode("utf-8")
    key_material = hmac.new(
        secret,
        b"macherla-guru-youtube-oauth-token-encryption-v1",
        hashlib.sha256,
    ).digest()
    return Fernet(base64.urlsafe_b64encode(key_material))

def supabase_headers(secret_key):
    return {
        "apikey": secret_key,
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
    }

def persist_owner_credentials(creds):
    config = get_supabase_config()
    if not config:
        return False
    supabase_url, secret_key = config
    encrypted = token_cipher().encrypt(creds.to_json().encode("utf-8")).decode("utf-8")
    response = requests.post(
        f"{supabase_url}/rest/v1/youtube_oauth_tokens",
        params={"on_conflict": "singleton"},
        headers={**supabase_headers(secret_key), "Prefer": "resolution=merge-duplicates,return=minimal"},
        json={"singleton": True, "encrypted_token": encrypted},
        timeout=20,
    )
    response.raise_for_status()
    return True

def load_persisted_owner_credentials():
    config = get_supabase_config()
    if not config:
        return None
    supabase_url, secret_key = config
    response = requests.get(
        f"{supabase_url}/rest/v1/youtube_oauth_tokens",
        params={"select": "encrypted_token", "singleton": "eq.true", "limit": "1"},
        headers=supabase_headers(secret_key),
        timeout=20,
    )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        return None
    encrypted = rows[0].get("encrypted_token")
    if not encrypted:
        return None
    return token_cipher().decrypt(encrypted.encode("utf-8")).decode("utf-8")

def get_owner_credentials():
    from google.oauth2.credentials import Credentials
    raw = st.session_state.get("youtube_owner_token")
    if not raw:
        try:
            raw = load_persisted_owner_credentials()
            if raw:
                st.session_state["youtube_owner_token"] = raw
        except Exception as exc:
            st.warning(f"Saved YouTube session could not be loaded: {exc}")
            return None
    if not raw:
        return None
    creds = Credentials.from_authorized_user_info(json.loads(raw), YT_SCOPES)
    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        st.session_state["youtube_owner_token"] = creds.to_json()
        try:
            persist_owner_credentials(creds)
        except Exception as exc:
            st.warning(f"Session refreshed, but secure backup could not be updated: {exc}")
    return creds if creds.valid else None

oauth_config, oauth_redirect_uri = get_oauth_config()
if "youtube_owner_token" not in st.session_state:
    st.session_state["youtube_owner_token"] = None

# Use a signed OAuth state so the callback remains verifiable even if
# Google's redirect creates a fresh Streamlit browser session.
import hashlib
import hmac
import secrets

def make_oauth_state(code_verifier):
    nonce = secrets.token_urlsafe(24)
    payload = f"{nonce}.{code_verifier}"
    secret = oauth_config["web"]["client_secret"].encode("utf-8")
    signature = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"

def verify_oauth_state(state):
    try:
        nonce, code_verifier, signature = state.rsplit(".", 2)
        payload = f"{nonce}.{code_verifier}"
        secret = oauth_config["web"]["client_secret"].encode("utf-8")
        expected = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if hmac.compare_digest(signature, expected):
            return code_verifier
    except Exception:
        pass
    return None

# Complete the OAuth callback after the owner returns from Google.
if oauth_config and st.query_params.get("code"):
    try:
        returned_state = st.query_params.get("state", "")
        saved_code_verifier = verify_oauth_state(returned_state)
        if not saved_code_verifier:
            raise ValueError("OAuth state validation failed. Please connect YouTube again.")
        from google_auth_oauthlib.flow import Flow
        callback_flow = Flow.from_client_config(
            oauth_config,
            scopes=YT_SCOPES,
            state=returned_state,
            redirect_uri=oauth_redirect_uri,
        )
        # The PKCE verifier is carried inside the signed state so it survives
        # Google's redirect even when Streamlit starts a fresh session.
        callback_flow.code_verifier = saved_code_verifier
        callback_flow.fetch_token(code=st.query_params.get("code"))
        st.session_state["youtube_owner_token"] = callback_flow.credentials.to_json()
        try:
            if persist_owner_credentials(callback_flow.credentials):
                st.success("YouTube authorization saved securely. Future app refreshes can restore the channel session.")
            else:
                st.warning("YouTube is connected for this session. Add Supabase URL and Secret Key in Streamlit Secrets to keep the login after refresh.")
        except Exception as persist_error:
            st.warning(f"YouTube connected for this session, but secure session backup failed: {persist_error}")
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
            flow.code_verifier = secrets.token_urlsafe(64)
            signed_state = make_oauth_state(flow.code_verifier)
            auth_url, _ = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
                state=signed_state,
            )
            st.link_button("Googleలో అనుమతి ఇవ్వండి", auth_url)
        except Exception as exc:
            st.error(f"Could not start Google authorization: {exc}")
    st.caption("నీ Google accountలో Macherla Guru channel access ఉన్న accountతోనే అనుమతి ఇవ్వాలి.")
else:
    st.success("YouTube channel connected for upload and analytics.")

    # Verify the scopes actually granted by Google. Do not show a stale,
    # unconditional warning after a successful re-authorization.
    schedule_scope = "https://www.googleapis.com/auth/youtube.force-ssl"
    granted_scopes = set()
    scope_check_error = None
    try:
        token_check = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"access_token": owner_creds.token},
            timeout=15,
        )
        token_check.raise_for_status()
        granted_scopes = set(token_check.json().get("scope", "").split())
    except Exception as exc:
        scope_check_error = exc

    if schedule_scope in granted_scopes:
        st.success("✅ Google Schedule/Publish permission verified. You can schedule approved videos.")
    else:
        if scope_check_error:
            st.warning(f"Google Schedule permission could not be verified right now: {scope_check_error}")
        else:
            st.warning(
                "Schedule/Publish permission ఇంకా Google tokenలో కనిపించడం లేదు. "
                "క్రింది Google Reconnect లింక్ ద్వారా అదే Macherla Guru accountతో మళ్లీ Allow చేయి."
            )
        from google_auth_oauthlib.flow import Flow
        try:
            reauth_flow = Flow.from_client_config(
                oauth_config, scopes=YT_SCOPES, redirect_uri=oauth_redirect_uri
            )
            reauth_flow.code_verifier = secrets.token_urlsafe(64)
            reauth_state = make_oauth_state(reauth_flow.code_verifier)
            reauth_url, _ = reauth_flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
                state=reauth_state,
            )
            st.markdown(f"### [🔄 Google Reconnect — Schedule Permission ఇవ్వు]({reauth_url})")
            st.caption("Googleలో అదే Macherla Guru channel account ఎంచుకుని YouTube permissions Allow చేయి. పూర్తయ్యాక Dashboardకు తిరిగి వస్తుంది.")
        except Exception as exc:
            st.error(f"Could not start YouTube re-authorization: {exc}")
    if not get_supabase_config():
        st.warning("Persistent login is not configured yet. Add [supabase] url and secret_key in Streamlit Secrets; the OAuth token will then be encrypted and stored outside the app session.")
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    youtube_owner = build("youtube", "v3", credentials=owner_creds, cache_discovery=False)
    analytics_owner = build("youtubeAnalytics", "v2", credentials=owner_creds, cache_discovery=False)

    # Safely identify and remove an accidental duplicate of the scheduled video.
    st.subheader("🧹 Duplicate వీడియో గుర్తించి తొలగించు")
    st.caption("షెడ్యూల్ చేసిన yCAeNqEs3Ao వీడియోను ఎప్పటికీ తొలగించదు. అదే Title ఉన్న మరో వీడియోను మాత్రమే చూపిస్తుంది; Deleteకు ముందు నీ confirmation తప్పనిసరి.")
    protected_video_id = "yCAeNqEs3Ao"
    try:
        protected_result = youtube_owner.videos().list(
            part="snippet,status", id=protected_video_id
        ).execute()
        protected_items = protected_result.get("items", [])
        if protected_items:
            protected_title = protected_items[0].get("snippet", {}).get("title", "")
            mine = youtube_owner.channels().list(part="contentDetails", mine=True).execute()
            mine_items = mine.get("items", [])
            uploads_id = (mine_items[0].get("contentDetails", {})
                          .get("relatedPlaylists", {}).get("uploads")) if mine_items else None
            duplicate_candidates = []
            if uploads_id and protected_title:
                playlist = youtube_owner.playlistItems().list(
                    part="contentDetails", playlistId=uploads_id, maxResults=50
                ).execute()
                owned_ids = [
                    x.get("contentDetails", {}).get("videoId")
                    for x in playlist.get("items", [])
                    if x.get("contentDetails", {}).get("videoId")
                ]
                for offset in range(0, len(owned_ids), 50):
                    batch = owned_ids[offset:offset + 50]
                    details = youtube_owner.videos().list(
                        part="snippet,status", id=",".join(batch)
                    ).execute()
                    for video in details.get("items", []):
                        vid = video.get("id")
                        title = video.get("snippet", {}).get("title", "")
                        if vid != protected_video_id and title == protected_title:
                            duplicate_candidates.append({
                                "id": vid,
                                "title": title,
                                "privacy": video.get("status", {}).get("privacyStatus", "unknown"),
                                "publish_at": video.get("status", {}).get("publishAt", ""),
                            })
            if duplicate_candidates:
                st.warning(f"షెడ్యూల్ వీడియో Titleతో సరిపోలిన మరో {len(duplicate_candidates)} వీడియో(లు) దొరికాయి.")
                options = {f'{x["id"]} — {x["privacy"]}': x for x in duplicate_candidates}
                chosen_label = st.selectbox("తొలగించాల్సిన Duplicate Video ID ఎంచుకో", list(options.keys()), key="duplicate_video_choice")
                chosen = options[chosen_label]
                st.write("**ఉంచాల్సిన వీడియో:**", protected_video_id, "—", protected_title)
                st.write("**తొలగించడానికి ఎంచుకున్నది:**", chosen["id"])
                confirm_delete = st.checkbox("అవును, ఎంచుకున్న Duplicate వీడియోను శాశ్వతంగా Delete చేయడానికి అంగీకరిస్తున్నాను", key="confirm_duplicate_delete")
                if st.button("🗑️ Confirm చేసి Duplicate మాత్రమే Delete చేయి", type="secondary", disabled=not confirm_delete):
                    if chosen["id"] == protected_video_id:
                        st.error("భద్రతా కారణంగా షెడ్యూల్ వీడియోను Delete చేయడం నిరోధించబడింది.")
                    else:
                        try:
                            youtube_owner.videos().delete(id=chosen["id"]).execute()
                            st.success(f'Duplicate వీడియో {chosen["id"]} Delete అయింది. షెడ్యూల్ వీడియో {protected_video_id} అలాగే ఉంది.')
                            st.rerun()
                        except Exception as delete_exc:
                            st.error(f"Duplicate Delete కాలేదు: {delete_exc}")
            else:
                st.info("ఇప్పటికి షెడ్యూల్ వీడియోతో అచ్చంగా ఒకే Title ఉన్న మరో Upload కనిపించలేదు. ఏ వీడియోనూ Delete చేయలేదు.")
        else:
            st.warning("రక్షించాల్సిన షెడ్యూల్ వీడియో yCAeNqEs3Ao ఈ Channelలో కనిపించలేదు. భద్రత కోసం Duplicate Delete చర్య నిలిపివేశాం.")
    except Exception as duplicate_exc:
        st.error(f"Duplicate వీడియోలను తనిఖీ చేయలేకపోయాం: {duplicate_exc}")


    st.subheader("🎬 ఒక్క వీడియో ఇవ్వు — మిగతావన్నీ Gemini సిద్ధం చేస్తుంది")
    uploaded_video = st.file_uploader("నీ వీడియో ఎంచుకోండి", type=["mp4", "mov", "avi", "webm"], key="source_video_for_ai")
    if uploaded_video and GEMINI_KEY:
        if st.button("✨ ఈ వీడియో చూసి Title, SEO, Tags, Captions తయారు చేయి", type="primary"):
            try:
                video_bytes = uploaded_video.getvalue()
                mime_type = uploaded_video.type or "video/mp4"
                start = requests.post(
                    "https://generativelanguage.googleapis.com/upload/v1beta/files",
                    headers={
                        "x-goog-api-key": GEMINI_KEY,
                        "X-Goog-Upload-Protocol": "resumable",
                        "X-Goog-Upload-Command": "start",
                        "X-Goog-Upload-Header-Content-Length": str(len(video_bytes)),
                        "X-Goog-Upload-Header-Content-Type": mime_type,
                        "Content-Type": "application/json",
                    },
                    json={"file": {"display_name": uploaded_video.name}},
                    timeout=60,
                )
                start.raise_for_status()
                upload_url = start.headers.get("X-Goog-Upload-URL")
                if not upload_url:
                    raise RuntimeError("Gemini video upload URL రాలేదు.")
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
                finish_data = finish.json()
                if isinstance(finish_data, dict):
                    file_info = finish_data.get("file", finish_data)
                else:
                    raise RuntimeError("Gemini upload response అర్థం కాలేదు. మళ్లీ ప్రయత్నించు.")
                if not isinstance(file_info, dict):
                    raise RuntimeError("Gemini file response సరైన formatలో లేదు.")
                file_uri = file_info.get("uri")
                file_state = file_info.get("state", "PROCESSING")
                if not file_uri:
                    raise RuntimeError("Gemini వీడియో ఫైల్ URI రాలేదు.")
                import time
                for _ in range(30):
                    if file_state == "ACTIVE":
                        break
                    time.sleep(2)
                    check = requests.get(
                        "https://generativelanguage.googleapis.com/v1beta/" + file_info.get("name", ""),
                        headers={"x-goog-api-key": GEMINI_KEY},
                        timeout=30,
                    )
                    check.raise_for_status()
                    file_info = check.json()
                    file_state = file_info.get("state", "")
                if file_state != "ACTIVE":
                    raise RuntimeError("Gemini వీడియోను ఇంకా ప్రాసెస్ చేయలేదు. కొద్దిసేపటి తర్వాత మళ్లీ ప్రయత్నించు.")
                ai_prompt = """Watch the supplied video carefully and create ready-to-use YouTube publishing metadata for Macherla Guru, a Telugu AI entertainment channel. Infer the actual subject, characters, actions, spoken language and mood from the video. Do not invent events, people, dialogue or claims not visible/audible. Return ONLY valid JSON with keys: title (catchy Telugu title, max 100 chars), description (natural Telugu description with a short CTA), tags (array of 12-18 relevant tags), hashtags (array of exactly 5 relevant hashtags), thumbnail_prompt (detailed 9:16 or 16:9 choice based on video, cinematic thumbnail prompt showing only actual video characters, no text), instagram_caption (curiosity hook plus exactly 5 hashtags), youtube_caption (curiosity hook plus exactly 5 hashtags), category (short label), keywords (array). Keep title and descriptions accurate to this video."""
                gen = requests.post(
                    "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent",
                    headers={"x-goog-api-key": GEMINI_KEY, "Content-Type": "application/json"},
                    json={
                        "contents": [{"parts": [
                            {"file_data": {"mime_type": mime_type, "file_uri": file_uri}},
                            {"text": ai_prompt},
                        ]}],
                        "generationConfig": {"temperature": 0.45, "responseMimeType": "application/json"},
                    },
                    timeout=240,
                )
                gen.raise_for_status()
                gen_data = gen.json()
                if not isinstance(gen_data, dict):
                    raise RuntimeError("Gemini response format తప్పుగా వచ్చింది. మళ్లీ Generate చేయి.")
                candidates = gen_data.get("candidates", [])
                text_parts = []
                for candidate in candidates if isinstance(candidates, list) else []:
                    if not isinstance(candidate, dict):
                        continue
                    content_obj = candidate.get("content", {})
                    if not isinstance(content_obj, dict):
                        continue
                    parts = content_obj.get("parts", [])
                    for part in parts if isinstance(parts, list) else []:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            text_parts.append(part["text"])
                generated_text = "\\n".join(text_parts).strip()
                if not generated_text:
                    raise RuntimeError("Gemini నుంచి వివరాలు రాలేదు. API response: " + json.dumps(gen_data, ensure_ascii=False)[:700])
                generated_text = generated_text.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
                # Gemini may occasionally wrap the requested object in a one-item
                # array or a named envelope. Normalize these safe response shapes.
                metadata = json.loads(generated_text)
                if isinstance(metadata, list):
                    metadata = next((item for item in metadata if isinstance(item, dict)), None)
                if isinstance(metadata, dict):
                    for wrapper_key in ("metadata", "result", "data", "output"):
                        wrapped = metadata.get(wrapper_key)
                        if isinstance(wrapped, dict):
                            metadata = wrapped
                            break
                if not isinstance(metadata, dict):
                    raise RuntimeError(
                        "Gemini సమాధానం JSON object రూపంలో రాలేదు. Generate మళ్లీ నొక్కి ప్రయత్నించు. "
                        "వివరాలు ఇంకా రాకపోతే Gemini API response format తనిఖీ చేయాలి."
                    )
                for field in ["title", "description", "tags", "hashtags", "thumbnail_prompt", "instagram_caption", "youtube_caption"]:
                    metadata.setdefault(field, [] if field in ["tags", "hashtags"] else "")
                if not isinstance(metadata.get("tags"), list):
                    metadata["tags"] = [str(metadata["tags"])]
                if not isinstance(metadata.get("hashtags"), list):
                    metadata["hashtags"] = [str(metadata["hashtags"])]
                st.session_state["ai_video_metadata"] = metadata
                st.session_state["ai_video_description"] = str(metadata.get("description", ""))
                st.session_state["ai_video_title"] = str(metadata.get("title", ""))[:100]
                st.session_state["ai_video_tags"] = ", ".join(str(tag) for tag in metadata.get("tags", []))

                # If the owner has not supplied a thumbnail, ask Gemini image
                # generation to create one using the actual uploaded video as context.
                st.session_state["ai_generated_thumbnail_bytes"] = None
                st.session_state["ai_generated_thumbnail_mime"] = "image/png"
                try:
                    thumb_prompt = (
                        "Create one polished YouTube thumbnail image for this exact video. "
                        "Use the supplied video as the only source of truth. "
                        + str(metadata.get("thumbnail_prompt", "")).strip()
                        + " Make the main subject large, expressive and instantly readable on a phone. "
                        "Use a cinematic composition, high contrast and crisp details. "
                        "Do not add text, letters, captions, logos or watermarks. "
                        "Return an image, not a written prompt."
                    )
                    thumb_response = None
                    thumb_data = {}
                    # Retry transient image-model rate limits with exponential backoff.
                    for thumb_attempt in range(3):
                        thumb_response = requests.post(
                            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent",
                            headers={"x-goog-api-key": GEMINI_KEY, "Content-Type": "application/json"},
                            json={
                                "contents": [{"parts": [
                                    {"file_data": {"mime_type": mime_type, "file_uri": file_uri}},
                                    {"text": thumb_prompt},
                                ]}],
                                "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
                            },
                            timeout=240,
                        )
                        if thumb_response.status_code not in (429, 500, 502, 503, 504) or thumb_attempt == 2:
                            break
                        time.sleep(2 ** (thumb_attempt + 1))
                    if not thumb_response.ok:
                        try:
                            thumb_error = thumb_response.json().get("error", {}).get("message", thumb_response.text)
                        except Exception:
                            thumb_error = thumb_response.text
                        raise RuntimeError(f"Gemini Image API ({thumb_response.status_code}): {thumb_error}")
                    thumb_data = thumb_response.json()
                    generated_image = None
                    for thumb_candidate in thumb_data.get("candidates", []):
                        for thumb_part in thumb_candidate.get("content", {}).get("parts", []):
                            inline_data = thumb_part.get("inlineData") or thumb_part.get("inline_data")
                            if isinstance(inline_data, dict) and inline_data.get("data"):
                                import base64
                                generated_image = base64.b64decode(inline_data["data"])
                                st.session_state["ai_generated_thumbnail_mime"] = inline_data.get("mimeType", inline_data.get("mime_type", "image/png"))
                                break
                        if generated_image:
                            break
                    if generated_image:
                        st.session_state["ai_generated_thumbnail_bytes"] = generated_image
                    else:
                        st.warning("Gemini వివరాలు తయారు చేసింది, కానీ ఆటో Thumbnail image రాలేదు. నువ్వు JPG/PNG ఎంచుకుని పెట్టవచ్చు.")
                except Exception as thumb_exc:
                    st.warning(f"Gemini వివరాలు సిద్ధం అయ్యాయి. ఆటో Thumbnail తయారీలో సమస్య: {thumb_exc}. నువ్వు JPG/PNG ఎంచుకుని పెట్టవచ్చు.")
                st.success("వీడియో చూసి Title, SEO, Tags సిద్ధం అయ్యాయి. Thumbnail నువ్వు ఇస్తే అదే; ఇవ్వకపోతే Gemini తయారు చేసినదాన్ని వాడతాం. Upload ముందు Review చేయి.")
            except Exception as exc:
                st.error(f"AI వీడియో విశ్లేషణలో సమస్య: {exc}")
    elif uploaded_video and not GEMINI_KEY:
        st.warning("Gemini API key లేదు. Streamlit Secretsలో GEMINI_API_KEY తనిఖీ చేయి.")

    metadata = st.session_state.get("ai_video_metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
        st.session_state["ai_video_metadata"] = {}
    if metadata:
        st.markdown("#### ✨ Gemini తయారు చేసిన వివరాలు — Review చేయి")
        st.text_input("YouTube Title", key="ai_video_title", max_chars=100)
        st.text_area("Description", key="ai_video_description", height=140)
        st.text_input("Tags (comma separated)", key="ai_video_tags")
        st.write("**Hashtags:** " + " ".join(metadata.get("hashtags", [])))
        generated_thumb = st.session_state.get("ai_generated_thumbnail_bytes")
        if generated_thumb:
            st.write("**Gemini తయారు చేసిన Thumbnail Preview (నువ్వు ఇవ్వనప్పుడు):**")
            st.image(generated_thumb, use_container_width=True)
        st.write("**Instagram Caption:**")
        st.write(metadata.get("instagram_caption", ""))
        st.write("**YouTube Caption:**")
        st.write(metadata.get("youtube_caption", ""))

    with st.form("youtube_private_upload_form"):
        upload_thumbnail = st.file_uploader("Thumbnail image (ఐచ్ఛికం)", type=["jpg", "jpeg", "png"])
        upload_submit = st.form_submit_button("🔒 Review చేసిన వివరాలతో Privateగా Upload చేయి", type="primary")

    if upload_submit:
        upload_title = st.session_state.get("ai_video_title", "").strip()
        upload_description = st.session_state.get("ai_video_description", "")
        upload_tags_text = st.session_state.get("ai_video_tags", "")
        if not uploaded_video or not upload_title:
            st.warning("ముందుగా వీడియో ఎంచుకుని Geminiతో వివరాలు తయారు చేయి.")
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
                # A manually selected thumbnail always takes priority.
                # Otherwise use the Gemini-generated image when available.
                thumbnail_bytes = upload_thumbnail.getvalue() if upload_thumbnail else st.session_state.get("ai_generated_thumbnail_bytes")
                thumbnail_mime = (upload_thumbnail.type or "image/jpeg") if upload_thumbnail else st.session_state.get("ai_generated_thumbnail_mime", "image/png")
                if thumbnail_bytes:
                    thumb_media = MediaIoBaseUpload(
                        io.BytesIO(thumbnail_bytes),
                        mimetype=thumbnail_mime,
                        resumable=False,
                    )
                    youtube_owner.thumbnails().set(videoId=new_video_id, media_body=thumb_media).execute()
                else:
                    st.warning("Thumbnail image అందుబాటులో లేదు. YouTube default thumbnailతో వీడియో Privateగా Upload అయింది.")
                st.success("వీడియో Privateగా Upload అయింది. నీ Approval వచ్చే వరకు Public కాదు.")
                st.video(uploaded_video.getvalue())
                st.markdown(f"[YouTubeలో Private Preview తెరువు](https://youtu.be/{new_video_id})")
            except Exception as exc:
                st.error(f"Upload failed: {exc}")

    pending_id = st.session_state.get("last_uploaded_video_id")
    if not pending_id:
        pending_id = st.text_input(
            "ఇప్పటికే YouTubeలో Privateగా ఉన్న వీడియో ID (మళ్లీ Upload అవసరం లేదు)",
            value="",
            key="manual_pending_video_id",
            help="ఉదా: yCAeNqEs3Ao — Private వీడియోను Review చేసి Schedule చేయడానికి.",
        ).strip()
    if pending_id:
        st.subheader("నీ Approval కోసం")
        st.write(st.session_state.get("last_uploaded_video_title", "Uploaded video"))
        st.markdown(f"[YouTube Preview](https://youtu.be/{pending_id})")
        from datetime import datetime, date, time, timedelta
        from zoneinfo import ZoneInfo
        india_tz = ZoneInfo("Asia/Kolkata")
        scheduled_at = st.session_state.get("last_uploaded_video_scheduled_at")
        if scheduled_at:
            st.info(f"ఈ వీడియో Schedule అయింది: {scheduled_at} (IST). YouTube సమయానికి Public చేస్తుంది.")
        publish_mode = st.radio(
            "ఎప్పుడు Public చేయాలి?",
            ["వెంటనే Public చేయి", "తేదీ, సమయానికి Schedule చేయి"],
            horizontal=True,
            key="youtube_publish_mode",
        )
        if publish_mode == "వెంటనే Public చేయి":
            if st.button("✅ Approve చేసి ఇప్పుడే Public చేయి", type="primary"):
                try:
                    current = youtube_owner.videos().list(part="status", id=pending_id).execute()
                    if not current.get("items"):
                        st.error("ఈ వీడియోను YouTubeలో కనుగొనలేకపోయాం.")
                    else:
                        status = current["items"][0].get("status", {})
                        status.pop("publishAt", None)
                        status["privacyStatus"] = "public"
                        youtube_owner.videos().update(part="status", body={"id": pending_id, "status": status}).execute()
                        st.success("నీ Approvalతో వీడియో Public అయింది!")
                        st.session_state["last_uploaded_video_id"] = None
                        st.session_state["last_uploaded_video_scheduled_at"] = None
                except Exception as exc:
                    st.error(f"Publish failed: {exc}")
        else:
            default_schedule = datetime.now(india_tz) + timedelta(hours=1)
            schedule_col1, schedule_col2 = st.columns(2)
            with schedule_col1:
                schedule_date = st.date_input(
                    "Public అయ్యే తేదీ",
                    value=default_schedule.date(),
                    min_value=date.today(),
                    key="youtube_schedule_date",
                )
            with schedule_col2:
                st.markdown("**Public అయ్యే సమయం (IST)**")
                default_clock = default_schedule.time()
                default_hour_12 = default_clock.hour % 12 or 12
                default_ampm = "PM" if default_clock.hour >= 12 else "AM"
                hour_col, minute_col, ampm_col = st.columns([1, 1, 1])
                with hour_col:
                    schedule_hour_12 = st.selectbox(
                        "Hour",
                        options=list(range(1, 13)),
                        index=default_hour_12 - 1,
                        key="youtube_schedule_hour_12",
                    )
                with minute_col:
                    schedule_minute = st.selectbox(
                        "Minute",
                        options=list(range(60)),
                        index=default_clock.minute,
                        format_func=lambda minute: f"{minute:02d}",
                        key="youtube_schedule_minute",
                    )
                with ampm_col:
                    schedule_ampm = st.selectbox(
                        "AM / PM",
                        options=["AM", "PM"],
                        index=0 if default_ampm == "AM" else 1,
                        key="youtube_schedule_ampm",
                    )
            hour_24 = (schedule_hour_12 % 12) + (12 if schedule_ampm == "PM" else 0)
            schedule_time = time(hour_24, schedule_minute)
            if st.button("🗓️ Approve చేసి Schedule చేయి", type="primary"):
                try:
                    publish_datetime = datetime.combine(schedule_date, schedule_time, tzinfo=india_tz)
                    if publish_datetime <= datetime.now(india_tz) + timedelta(minutes=2):
                        st.error("దయచేసి కనీసం 2 నిమిషాల తర్వాతి సమయాన్ని ఎంచుకో.")
                    else:
                        current = youtube_owner.videos().list(part="status", id=pending_id).execute()
                        if not current.get("items"):
                            st.error("ఈ వీడియోను YouTubeలో కనుగొనలేకపోయాం.")
                        else:
                            status = current["items"][0].get("status", {})
                            # YouTube only accepts publishAt for a video that is
                            # still private and has never been published.
                            if status.get("privacyStatus") == "public":
                                st.error("ఈ వీడియో ఇప్పటికే Public అయింది. Schedule చేయలేం.")
                            elif status.get("uploadStatus") not in (None, "processed"):
                                st.error(f"వీడియో ఇంకా processingలో ఉంది (uploadStatus: {status.get('uploadStatus')}). Processing పూర్తయ్యాక మళ్లీ ప్రయత్నించు.")
                            else:
                                status["privacyStatus"] = "private"
                                status["publishAt"] = publish_datetime.isoformat(timespec="seconds")
                                update_result = youtube_owner.videos().update(
                                    part="status",
                                    body={"id": pending_id, "status": status}
                                ).execute()

                                # Read the video back from YouTube. Never show
                                # success based only on the update request returning.
                                verified = youtube_owner.videos().list(
                                    part="status,snippet",
                                    id=pending_id
                                ).execute()
                                verified_items = verified.get("items", [])
                                verified_status = verified_items[0].get("status", {}) if verified_items else {}
                                verified_publish_at = verified_status.get("publishAt")
                                if (
                                    verified_items
                                    and verified_status.get("privacyStatus") == "private"
                                    and verified_publish_at
                                ):
                                    st.session_state["last_uploaded_video_scheduled_at"] = verified_publish_at
                                    st.success(
                                        "✅ YouTube Schedule నిర్ధారించింది. "
                                        f"Publish time: {verified_publish_at}. "
                                        "YouTube Studioలో Visibility → Scheduledగా కనిపించాలి."
                                    )
                                else:
                                    st.session_state["last_uploaded_video_scheduled_at"] = None
                                    st.error(
                                        "YouTube Scheduleని నిర్ధారించలేదు. వీడియో ఇంకా "
                                        f"{verified_status.get('privacyStatus', 'తెలియని status')}గానే ఉంది. "
                                        f"publishAt: {verified_publish_at or 'లేదు'}. "
                                        "YouTube API update responseలో వచ్చిన statusను మళ్లీ తనిఖీ చేయాలి."
                                    )
                except Exception as exc:
                    st.error(f"Schedule failed: {exc}")
        st.divider()
        if st.button("🔎 YouTubeలో అసలు Schedule Status తనిఖీ చేయి"):
            try:
                live_check = youtube_owner.videos().list(
                    part="status,snippet",
                    id=pending_id
                ).execute()
                live_items = live_check.get("items", [])
                if not live_items:
                    st.error("YouTubeలో ఈ Video ID కనిపించలేదు.")
                else:
                    live_status = live_items[0].get("status", {})
                    live_publish_at = live_status.get("publishAt")
                    st.write("**YouTube Privacy:**", live_status.get("privacyStatus", "తెలియదు"))
                    if live_publish_at:
                        live_dt = datetime.fromisoformat(live_publish_at.replace("Z", "+00:00"))
                        st.write("**YouTube Publish time (IST):**", live_dt.astimezone(india_tz).strftime("%d-%m-%Y %I:%M %p"))
                        st.success("YouTube APIలో publishAt ఉంది. Studioలో Scheduledగా కనిపించకపోతే Studio refresh చేసి సరైన channel/accountలో చూడాలి.")
                    else:
                        st.error("YouTube APIలో publishAt లేదు. కాబట్టి వీడియో నిజంగా Schedule కాలేదు; ప్రస్తుతం Private మాత్రమే.")
            except Exception as exc:
                st.error(f"Status check failed: {exc}")

        if st.button("🔐 Privateగానే ఉంచు"):
            st.info("వీడియో Privateగానే ఉంటుంది. Schedule చేయలేదు.")

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
                        metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,shares,subscribersGained,subscribersLost",
                        dimensions="day",
                        filters=f"video=={analysis_id.strip()}",
                        sort="day",
                    ).execute()
                    headers = [h.get("name") for h in report.get("columnHeaders", [])]
                    data_rows = report.get("rows", [])
                    if data_rows:
                        import pandas as pd
                        st.caption("YouTube Analytics: Views, watch time, average view duration, average view %, likes, comments, shares, subscribers gained/lost. Recent 1–2 days data may be delayed. Thumbnail impressions/CTR are not available through this targeted Analytics query.")
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

st.caption("Privacy: API keys, Supabase Secret Key and Google OAuth client credentials belong only in Streamlit deployment Secrets, never in GitHub. When Supabase credentials are configured, the YouTube OAuth token is encrypted before server-side storage in a table inaccessible to anon/authenticated users. The Supabase Secret Key is used only by this server-side app.")
