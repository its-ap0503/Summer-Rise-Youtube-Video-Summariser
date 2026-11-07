import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session

from app.services.transcript_service import YouTubeIPBlockedError


from app.db.database import (
    engine,
    get_db,
    get_recent_summaries,
    get_summary_from_db,
    init_db,
    save_summary_to_db,
)
from app.schemas.video import VideoRequest, VideoSummaryResponse
from app.services.cache_service import (
    get_cached_summary,
    limiter,
    set_cached_summary,
)
from app.services.llm_service import generate_video_summary
from app.services.transcript_service import (
    extract_video_id,
    fetch_raw_transcript,
    window_transcript,
)

# Configure structured console logging across all modules
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """ASGI Lifespan context manager that runs startup initialization before

    accepting HTTP traffic and cleans up TCP pools on server shutdown.
    """
    logger.info("Starting up YouTube Study Companion backend...")
    # Ensure PostgreSQL tables and B-Tree indexes exist before serving requests
    init_db()
    yield
    # Cleanly close all pooled PostgreSQL sockets when Uvicorn shuts down
    logger.info("Shutting down backend and disposing SQLAlchemy QueuePool...")
    engine.dispose()


app = FastAPI(
    title="YouTube Video Summarizer & Study Companion",
    description="Production 3-Tier Backend (Redis L1 + PostgreSQL L2 + Gemini Structured Outputs L3)",
    version="1.0.0",
    lifespan=lifespan,
)

# 1. Attach slowapi Rate Limiter to app state and register HTTP 429 handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 2. Configure CORS Middleware so the frontend JS can call the API across ports
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.post(
    "/api/summarize",
    response_model=VideoSummaryResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("5/minute")
def summarize_video(
    request: Request,
    payload: VideoRequest,
    db: Session = Depends(get_db),
) -> VideoSummaryResponse:
    """Orchestrates the 3-Tier Summarization Pipeline:

    1. Validate URL & extract 11-char video_id (0ms CPU regex)
    2. Tier 1 Check: Redis L1 Cache (~3ms)
    3. Tier 2 Check: PostgreSQL L2 Storage (~15ms + L1 Cache Warming)
    4. Tier 3 Compute: YouTube Transcript + 60s Windowing + Gemini Structured Output (~6000ms)
    """
    # Step 1: Extract and validate the 11-character YouTube video_id
    try:
        video_id = extract_video_id(payload.url)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Step 2 (Tier 1 - L1 Cache): Check Redis RAM first
    cached_summary = get_cached_summary(video_id)
    if cached_summary is not None:
        return cached_summary

    # Step 3 (Tier 2 - L2 Database): Check PostgreSQL disk storage
    db_summary = get_summary_from_db(db, video_id)
    if db_summary is not None:
        # Self-Heal / Warm L1 Cache for the next 24 hours
        set_cached_summary(video_id, db_summary)
        return db_summary

    # Step 4 (Tier 3 - Cold Compute): Fetch transcript (or fall back to Gemini URI if IP blocked)
    windowed_data = None
    try:
        raw_snippets = fetch_raw_transcript(video_id)
        windowed_data = window_transcript(raw_snippets, window_seconds=60)
    except YouTubeIPBlockedError as e:
        logger.warning(f"YouTube IP block detected ({e}). Falling back to Gemini native URI.")
        windowed_data = None
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected transcript failure for video_id={video_id}: {e}")
        # Fallback to Gemini native URI instead of failing the request
        windowed_data = None

    
    # A transcript that exists but has no usable text -> also use the fallback
    if windowed_data is not None and not windowed_data["chunks"]:
        windowed_data = None

    try:
        summary = generate_video_summary(windowed_data, video_id=video_id)
    except Exception as e:
        # Use 503 instead of 502 so Cloudflare does not replace our JSON with its HTML page
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI generation temporarily unavailable: {str(e)}",
        )
        
    
    # Step 5: Dual Persistence Write (Save permanently to Postgres L2 + Cache in Redis L1)
    save_summary_to_db(db, summary)
    set_cached_summary(video_id, summary)

    return summary


@app.get("/api/history", status_code=status.HTTP_200_OK)
def fetch_revision_history(
    limit: int = 20,
    db: Session = Depends(get_db),
) -> dict:
    """Returns lightweight metadata for recently summarized lectures

    to populate the exam revision sidebar without reading heavy JSONB blobs.
    """
    clamped_limit = max(1, min(limit, 50))
    items = get_recent_summaries(db, limit=clamped_limit)
    return {"items": items}


# Mount the Vanilla HTML/CSS/JS frontend at the root path "/"
# IMPORTANT: Must remain at the very bottom of main.py so it does not shadow /api/* routes
os.makedirs("frontend", exist_ok=True)
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")