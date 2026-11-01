"""Instagram Manager for Macherla Guru.
Uses Meta's Unified Login / System User Access Token configured in Streamlit Secrets.
Never stores tokens in GitHub or displays them in the UI.
"""
import time
import requests
import streamlit as st

TIMEOUT = 30

def _ig_config():
    try:
        cfg = st.secrets.get("instagram", {})
        return {
            "token": str(cfg.get("system_user_access_token", "")).strip(),
            "ig_user_id": str(cfg.get("ig_user_id", "")).strip(),
            "api_version": str(cfg.get("api_version", "v25.0")).strip(),
        }
    except Exception:
        return {"token": "", "ig_user_id": "", "api_version": "v25.0"}

def _api(cfg, method, path, params=None, data=None):
    url = f"https://graph.facebook.com/{cfg['api_version']}/{path.lstrip('/')}"
    payload = dict(params or {})
    payload["access_token"] = cfg["token"]
    response = requests.request(
        method, url, params=payload if method.upper() == "GET" else None,
        data={**(data or {}), "access_token": cfg["token"]} if method.upper() != "GET" else None,
        timeout=TIMEOUT,
    )
    try:
        body = response.json()
    except Exception:
        body = {"error": {"message": response.text[:500]}}
    if not response.ok or "error" in body:
        message = body.get("error", {}).get("message", f"Meta API returned HTTP {response.status_code}")
        raise RuntimeError(message)
    return body

def _profile(cfg):
    return _api(cfg, "GET", cfg["ig_user_id"], {
        "fields": "id,username,name,profile_picture_url,biography,followers_count,follows_count,media_count"
    })

def _recent_media(cfg):
    return _api(cfg, "GET", f"{cfg['ig_user_id']}/media", {
        "fields": "id,caption,media_type,media_product_type,permalink,thumbnail_url,media_url,timestamp,like_count,comments_count",
        "limit": 12,
    }).get("data", [])

def _publish_reel(cfg, video_url, caption):
    # Instagram Reels publishing is a create-container -> wait -> publish workflow.
    container = _api(cfg, "POST", f"{cfg['ig_user_id']}/media", data={
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true",
    })
    creation_id = container.get("id")
    if not creation_id:
        raise RuntimeError("Meta did not return a Reel media container ID.")
    for _ in range(24):
        status = _api(cfg, "GET", creation_id, {"fields": "status_code,status"})
        if status.get("status_code") == "FINISHED":
            break
        if status.get("status_code") == "ERROR":
            raise RuntimeError(status.get("status") or "Instagram could not process this video.")
        time.sleep(5)
    else:
        raise RuntimeError("Instagram is still processing the video. Please check again before publishing.")
    result = _api(cfg, "POST", f"{cfg['ig_user_id']}/media_publish", data={
        "creation_id": creation_id,
    })
    return result.get("id")

def render_instagram_manager():
    st.divider()
    st.header("📸 Macherla Guru — Instagram Manager")
    st.caption("Official Meta Graph API • @macherlaguru • Owner approval before publishing")
    cfg = _ig_config()
    if not cfg["token"] or not cfg["ig_user_id"]:
        st.warning(
            "Instagram connection setup is waiting for Meta credentials. "
            "The app is ready to read the official Meta System User Access Token from Streamlit Secrets."
        )
        st.code(
            '[instagram]\n'
            'system_user_access_token = "ADD_META_SYSTEM_USER_TOKEN_IN_STREAMLIT_SECRETS"\n'
            'ig_user_id = "ADD_INSTAGRAM_ACCOUNT_ID"\n'
            'api_version = "v25.0"',
            language="toml",
        )
        st.info(
            "Do not paste the token here or commit it to GitHub. "
            "Add the token and Instagram Account ID privately in Streamlit App settings → Secrets."
        )
        st.markdown(
            "Meta app permissions needed: instagram_basic and instagram_content_publish. "
            "Insights additionally needs instagram_manage_insights if Meta grants it to this app."
        )
        return
    left, right = st.columns([1, 3])
    with left:
        if st.button("Refresh Instagram", key="ig_refresh"):
            st.rerun()
    try:
        profile = _profile(cfg)
        with right:
            st.success(f"Connected to Instagram: @{profile.get('username', 'unknown')}")
        m1, m2, m3 = st.columns(3)
        m1.metric("Followers", f"{int(profile.get('followers_count', 0)):,}")
        m2.metric("Following", f"{int(profile.get('follows_count', 0)):,}")
        m3.metric("Posts", f"{int(profile.get('media_count', 0)):,}")
        if profile.get("biography"):
            st.caption(profile["biography"])
        st.subheader("Recent Instagram posts & Reels")
        media = _recent_media(cfg)
        if media:
            rows = [{
                "Date": (item.get("timestamp") or "")[:10],
                "Type": item.get("media_product_type") or item.get("media_type") or "Media",
                "Likes": item.get("like_count", 0),
                "Comments": item.get("comments_count", 0),
                "Caption": (item.get("caption") or "")[:100],
                "Post URL": item.get("permalink", ""),
            } for item in media]
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("No media items were returned for this Instagram account.")
        with st.expander("Instagram Insights"):
            if st.button("Load account insights", key="ig_load_insights"):
                try:
                    insights = _api(cfg, "GET", f"{cfg['ig_user_id']}/insights", {
                        "metric": "reach,profile_views",
                        "period": "day",
                    })
                    st.json(insights.get("data", []))
                except Exception as exc:
                    st.warning(f"Insights permission/metric is not available for this token yet: {exc}")
        st.subheader("Publish an Instagram Reel")
        st.caption("Use a stable public HTTPS video URL. Publishing happens only after you tick approval and press the button.")
        video_url = st.text_input(
            "Public HTTPS video URL",
            placeholder="https://your-host.example/reel.mp4",
            key="ig_video_url",
        )
        caption = st.text_area("Instagram caption", placeholder="Caption + hashtags", key="ig_caption", height=120)
        approved = st.checkbox(
            "I reviewed this Reel and explicitly approve publishing it to @macherlaguru.",
            key="ig_publish_approval",
        )
        if st.button(
            "Publish approved Reel now",
            type="primary",
            disabled=not (approved and video_url.startswith("https://") and bool(caption.strip())),
            key="ig_publish_reel",
        ):
            try:
                with st.spinner("Instagram is processing the Reel..."):
                    media_id = _publish_reel(cfg, video_url.strip(), caption.strip())
                st.success(f"Instagram Reel published. Media ID: {media_id}")
                st.session_state["ig_publish_approval"] = False
            except Exception as exc:
                st.error(f"Instagram publishing failed: {exc}")
    except Exception as exc:
        st.error(f"Instagram connection/API error: {exc}")
        st.caption(
            "Check that the System User token belongs to the Meta app and has access to this exact "
            "Instagram asset. Do not change or remove any Facebook/Instagram account links to fix this."
        )
