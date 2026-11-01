"""Instagram Manager for Macherla Guru.
Uses a Meta Instagram-compatible access token configured privately in Streamlit Secrets.
Never stores tokens in GitHub or displays them in the UI.
"""
import time
import requests
import streamlit as st

TIMEOUT = 30

# Facebook Login for Business (Instagram API Unified Login) OAuth settings.
META_APP_ID = "1681552070258441"
META_LOGIN_CONFIG_ID = "4141386829497142"
DEFAULT_REDIRECT_URI = "https://macherla-guru-ai-agent-utaxv6fgkyc4salfken7wv.streamlit.app"
GRAPH_VERSION = "v25.0"

def _oauth_settings():
    try:
        cfg = st.secrets.get("instagram_oauth", {})
        secret = str(cfg.get("app_secret", "")).strip()
        redirect_uri = str(cfg.get("redirect_uri", DEFAULT_REDIRECT_URI)).strip()
        return secret, redirect_uri
    except Exception:
        return "", DEFAULT_REDIRECT_URI

def _signed_state(secret):
    import hashlib, hmac, secrets
    nonce = secrets.token_urlsafe(24)
    signature = hmac.new(secret.encode(), nonce.encode(), hashlib.sha256).hexdigest()
    st.session_state["ig_oauth_state"] = nonce + "." + signature
    return st.session_state["ig_oauth_state"]

def _valid_state(secret, received):
    import hashlib, hmac
    expected = st.session_state.get("ig_oauth_state", "")
    if not expected or not received:
        return False
    try:
        nonce, signature = received.rsplit(".", 1)
        expected_signature = hmac.new(secret.encode(), nonce.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, received) and hmac.compare_digest(signature, expected_signature)
    except Exception:
        return False

def _complete_meta_login(secret, redirect_uri):
    code = st.query_params.get("code")
    if not code:
        return
    state = st.query_params.get("state", "")
    if not _valid_state(secret, state):
        raise RuntimeError("Meta login state check failed. Please start Connect Instagram again.")
    token_response = requests.get(
        f"https://graph.facebook.com/{GRAPH_VERSION}/oauth/access_token",
        params={
            "client_id": META_APP_ID,
            "client_secret": secret,
            "redirect_uri": redirect_uri,
            "code": code,
        },
        timeout=TIMEOUT,
    )
    token_body = token_response.json()
    if not token_response.ok or "access_token" not in token_body:
        raise RuntimeError(token_body.get("error", {}).get("message", "Meta token exchange failed."))
    user_token = token_body["access_token"]

    # Exchange for a long-lived user token before discovering the selected Page/Instagram asset.
    long_response = requests.get(
        f"https://graph.facebook.com/{GRAPH_VERSION}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": META_APP_ID,
            "client_secret": secret,
            "fb_exchange_token": user_token,
        },
        timeout=TIMEOUT,
    )
    long_body = long_response.json()
    if long_response.ok and long_body.get("access_token"):
        user_token = long_body["access_token"]

    pages_response = requests.get(
        f"https://graph.facebook.com/{GRAPH_VERSION}/me/accounts",
        params={
            "fields": "id,name,access_token,instagram_business_account",
            "access_token": user_token,
        },
        timeout=TIMEOUT,
    )
    pages_body = pages_response.json()
    if not pages_response.ok:
        raise RuntimeError(pages_body.get("error", {}).get("message", "Could not read Facebook Pages."))
    connected = [
        p for p in pages_body.get("data", [])
        if p.get("instagram_business_account", {}).get("id") and p.get("access_token")
    ]
    if not connected:
        raise RuntimeError(
            "Meta login completed, but no Page with a connected Instagram professional account was returned. "
            "Check that the Facebook Login for Business configuration includes the Page and Instagram assets, "
            "and grants pages_show_list, pages_read_engagement and instagram_basic."
        )
    # Keep the connected Page token and Instagram account ID only in this Streamlit session.
    st.session_state["ig_oauth_pages"] = connected
    st.session_state["ig_oauth_user_token"] = user_token
    st.session_state.pop("ig_oauth_state", None)
    st.query_params.clear()
    st.rerun()


def _ig_config():
    try:
        cfg = st.secrets.get("instagram", {})
        return {
            "token": str(cfg.get("access_token", cfg.get("user_access_token", cfg.get("system_user_access_token", "")))).strip(),
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
    oauth_secret, oauth_redirect_uri = _oauth_settings()
    # A token obtained through the current Meta OAuth session takes precedence over old manual secrets.
    selected = st.session_state.get("ig_oauth_selected")
    if selected:
        cfg["token"] = selected.get("access_token", "")
        cfg["ig_user_id"] = selected.get("instagram_business_account", {}).get("id", "")
    if oauth_secret:
        try:
            _complete_meta_login(oauth_secret, oauth_redirect_uri)
        except Exception as oauth_error:
            st.error(f"Meta Instagram login failed: {oauth_error}")
            st.query_params.clear()
        state = st.session_state.get("ig_oauth_state") or _signed_state(oauth_secret)
        from urllib.parse import urlencode
        login_url = "https://www.facebook.com/v25.0/dialog/oauth?" + urlencode({
            "client_id": META_APP_ID,
            "redirect_uri": oauth_redirect_uri,
            "config_id": META_LOGIN_CONFIG_ID,
            "response_type": "code",
            "state": state,
        })
        st.link_button("🔐 Connect Instagram with Meta", login_url, type="primary")
        pages = st.session_state.get("ig_oauth_pages", [])
        if pages:
            page_labels = [f'{p.get("name", "Facebook Page")} — Instagram ID {p["instagram_business_account"]["id"]}' for p in pages]
            chosen_index = st.selectbox(
                "Choose the Facebook Page connected to @macherlaguru",
                range(len(pages)),
                format_func=lambda i: page_labels[i],
                key="ig_oauth_page_choice",
            )
            if st.button("Use this Instagram account", key="ig_use_selected_page"):
                st.session_state["ig_oauth_selected"] = pages[chosen_index]
                st.rerun()
    else:
        st.info("To enable secure Meta login, add [instagram_oauth] with app_secret in Streamlit Secrets. Never share the App Secret in chat or GitHub.")
        st.code('[instagram_oauth]\\napp_secret = "YOUR_META_APP_SECRET"\\nredirect_uri = "' + DEFAULT_REDIRECT_URI + '"', language="toml")
    if not cfg["token"] or not cfg["ig_user_id"]:
        st.warning(
            "Instagram connection setup is waiting for Meta credentials. "
            "Add your Instagram-compatible Meta access token and Instagram account ID in Streamlit Secrets."
        )
        st.code(
            '[instagram]\n'
            'access_token = "ADD_META_ACCESS_TOKEN_IN_STREAMLIT_SECRETS"\n'
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
            "Check that the access token belongs to the correct Meta app, has the required permissions, and can access this exact "
            "Instagram asset. User tokens may expire; if this token is expired or lacks access, generate a fresh supported token. Do not change or remove any Facebook/Instagram account links to fix this."
        )
