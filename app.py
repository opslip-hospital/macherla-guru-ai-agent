import os
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
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
    st.info("Setup needed: add your YouTube Data API key in the sidebar or GitHub/hosting Secrets.")
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
        uploads = yt_get("playlistItems", {"part":"snippet,contentDetails", "playlistId":playlist_id, "maxResults":50})
        ids = [x.get("contentDetails",{}).get("videoId") for x in uploads.get("items",[]) if x.get("contentDetails",{}).get("videoId")]
        if ids:
            videos = yt_get("videos", {"part":"snippet,statistics,contentDetails", "id":",".join(ids)})
            rows = []
            for v in videos.get("items", []):
                s = v.get("statistics", {})
                rows.append({"Title":v.get("snippet",{}).get("title",""),"Published":v.get("snippet",{}).get("publishedAt","")[:10],"Views":int(s.get("viewCount",0)),"Likes":int(s.get("likeCount",0)),"Comments":int(s.get("commentCount",0)),"URL":"https://youtu.be/"+v["id"]})
            rows.sort(key=lambda r:r["Views"], reverse=True)
            st.subheader("Recent uploads — sorted by views")
            st.dataframe(rows, use_container_width=True, hide_index=True)
            st.download_button("Download video report CSV", data=__import__("pandas").DataFrame(rows).to_csv(index=False), file_name="macherla-guru-videos.csv", mime="text/csv")
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
