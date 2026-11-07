import os
import re
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
)
from youtube_transcript_api.proxies import GenericProxyConfig

VIDEO_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{11}$")
PREFERRED_LANGUAGES = ["en", "en-IN", "en-US", "en-GB", "hi"]

# Optional proxy support if PROXY_URL is set (e.g. in Render env vars)
_proxy_url = os.getenv("PROXY_URL", "").strip()
_proxy_config = (
    GenericProxyConfig(http_url=_proxy_url, https_url=_proxy_url)
    if _proxy_url
    else None
)

# Single module-level client (the proxy config is now actually used for fetching)
ytt_client = YouTubeTranscriptApi(proxy_config=_proxy_config)


class YouTubeIPBlockedError(Exception):
    """Raised when YouTube blocks the cloud server's IP from scraping transcripts."""


def extract_video_id(url: str) -> str:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().split(":")[0]

    candidate_id = None
    if host in ("www.youtu.be", "youtu.be"):
        candidate_id = parsed.path.lstrip("/").split("/")[0]
    elif host == "youtube.com" or host.endswith(".youtube.com"):
        if parsed.path == "/watch":
            candidate_id = parse_qs(parsed.query).get("v", [None])[0]
        elif parsed.path.startswith(("/embed/", "/shorts/", "/live/", "/v/")):
            parts = parsed.path.strip("/").split("/")
            if len(parts) >= 2:
                candidate_id = parts[1]

    if not candidate_id or not VIDEO_ID_REGEX.match(candidate_id):
        raise ValueError(f"Invalid YouTube URL or could not extract 11-char video ID: {url}")

    return candidate_id


def fetch_raw_transcript(video_id: str) -> list[dict]:
    try:
        try:
            fetched = ytt_client.fetch(video_id, languages=PREFERRED_LANGUAGES)
        except NoTranscriptFound:
            # Preferred languages not available: use whatever transcript exists
            transcript_list = ytt_client.list(video_id)
            available = list(transcript_list)
            if not available:
                raise
            fetched = available[0].fetch()
        return fetched.to_raw_data()

    except (RequestBlocked, IpBlocked) as e:
        raise YouTubeIPBlockedError(
            f"YouTube blocked transcript fetch from this server IP for {video_id}."
        ) from e
    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as e:
        raise ValueError(
            f"No usable transcript available for video {video_id}: {str(e)}"
        ) from e
    except Exception as e:
        if "blocking requests from your IP" in str(e) or "RequestBlocked" in str(e):
            raise YouTubeIPBlockedError(str(e)) from e
        raise RuntimeError(
            f"Unexpected error fetching transcript for {video_id}: {str(e)}"
        ) from e


def format_timestamp(seconds: float) -> str:
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def window_transcript(raw_snippets: list[dict], window_seconds: int = 60) -> dict:
    if not raw_snippets:
        return {"chunks": [], "formatted_text": ""}

    chunks = []
    bucket_start = None
    bucket_texts: list[str] = []

    for snippet in raw_snippets:
        clean_text = snippet["text"].replace("\n", " ").strip()
        if not clean_text:
            continue

        snippet_start = snippet["start"]
        if bucket_start is None:
            bucket_start = snippet_start

        if (snippet_start - bucket_start) >= window_seconds and bucket_texts:
            chunks.append({
                "start_seconds": int(bucket_start),
                "timestamp": format_timestamp(bucket_start),
                "text": " ".join(bucket_texts),
            })
            bucket_start = snippet_start
            bucket_texts = []

        bucket_texts.append(clean_text)

    if bucket_texts:
        chunks.append({
            "start_seconds": int(bucket_start),
            "timestamp": format_timestamp(bucket_start),
            "text": " ".join(bucket_texts),
        })

    formatted_lines = [f"[{c['timestamp']}] {c['text']}" for c in chunks]
    return {"chunks": chunks, "formatted_text": "\n".join(formatted_lines)}