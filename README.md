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
