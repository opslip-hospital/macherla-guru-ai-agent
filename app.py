import os
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
st.caption("Privacy: API keys must be stored as deployment secrets, never committed to GitHub. This starter dashboard reads public channel/video data only; private YouTube Analytics requires a separate OAuth authorization.")
