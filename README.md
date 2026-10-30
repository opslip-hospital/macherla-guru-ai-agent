# Macherla Guru — Free-first YouTube AI Manager

A starter dashboard for the **Macherla Guru** channel (@macherlaguru).

## Current capabilities
- Reads public channel statistics using YouTube Data API v3.
- Lists up to 50 recent uploads and sorts them by public view count.
- Exports a CSV report.
- Keeps API keys outside source control.

## Run locally
1. Install Python 3.11+.
2. Run `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env`.
4. Add your YouTube Data API v3 key to `.env`.
5. Run `streamlit run app.py`.

## Google API setup
In Google Cloud Console, create/select a project, enable **YouTube Data API v3**, create an API key, and restrict it to YouTube Data API v3. Never commit the key or paste it into chat. For deployment, add it as a secret named `YOUTUBE_API_KEY`.

## Important limitations
- This first version uses public YouTube Data API information only.
- Private metrics such as impressions CTR, audience retention, revenue and detailed watch time require the channel owner's separate OAuth consent through YouTube Analytics API. They are not available from a public API key.
- Gemini AI features are optional and need a Gemini API key; the current dashboard remains usable without it.
- GitHub Actions is included as a daily configuration check, not a promise of automatic growth or automatic publishing.

## Deploy
This is a Streamlit app, so deploy it with Streamlit Community Cloud (free tier subject to its current limits) or run locally. GitHub Pages cannot host this Python dashboard.


## YouTube upload and owner analytics
The app supports an owner-authorized workflow: upload a video as **Private**, review it, and explicitly approve it before changing it to **Public**. It can also request per-video YouTube Analytics.

Before using these features:
1. In Google Cloud Console, enable **YouTube Data API v3** and **YouTube Analytics API**.
2. Configure the OAuth consent screen and add the channel owner's Google account as a test user if the app is in Testing.
3. Create an OAuth Client ID of type **Web application**.
4. Add the exact Streamlit app URL shown in the browser as an authorized redirect URI.
5. In Streamlit Community Cloud → App → Settings → Secrets, add:

```toml
[youtube_oauth]
client_id = "YOUR_OAUTH_CLIENT_ID"
client_secret = "YOUR_OAUTH_CLIENT_SECRET"
redirect_uri = "https://YOUR-APP-NAME.streamlit.app"
```

Never commit OAuth client secrets or access/refresh tokens to GitHub. The owner must connect the Google account that manages the Macherla Guru channel. Authorization is held in the active Streamlit session; reconnect may be required after the session resets. Analytics are subject to YouTube's reporting delay and API availability.
