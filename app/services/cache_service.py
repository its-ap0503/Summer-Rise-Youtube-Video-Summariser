import logging
import redis
from redis.exceptions import RedisError
from pydantic import ValidationError

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings
from app.schemas.video import VideoSummaryResponse

logger = logging.getLogger(__name__)

# Namespace prefixes to prevent key collisions in shared Redis instances
SUMMARY_KEY_PREFIX = "YouTube_video_summariser:summary:"
RATELIMIT_KEY_PREFIX = "YouTube_video_summariser:ratelimit:"
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def get_real_client_ip(request: Request) -> str:
    """Extracts the true user IP behind Cloudflare and Render reverse proxies."""
    # 1. Cloudflare header (summer-rise.techwithap.site)
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()

    # 2. Standard Render / AWS ALB proxy header (first IP in comma-separated list)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    # 3. Localhost fallback
    return get_remote_address(request)

# Initialize slowapi Limiter backed by our Redis URL
# in_memory_fallback_enabled=True ensures fail-open resiliency if Redis is down

limiter = Limiter(
    key_func=get_real_client_ip,
    storage_uri=settings.REDIS_URL,
    in_memory_fallback_enabled=True,
    swallow_errors=True,
)

# Initialize a module-level Redis client backed by an internal TCP Connection Pool
redis_client = redis.from_url(
    url=settings.REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=1.0,
    socket_timeout=1.0,
    health_check_interval=30,
)


def get_cached_summary(video_id: str) -> VideoSummaryResponse | None:
    """Retrieves a cached video summary from Redis in O(1) time.

    Fails open (returns None) if Redis is unreachable or if cached schema is stale.
    """
    cache_key = f"{SUMMARY_KEY_PREFIX}{video_id}"

    try:
        raw_json = redis_client.get(cache_key)
        if raw_json is None:
            logger.info(f"Cache MISS for video_id={video_id}")
            return None

        logger.info(f"Cache HIT for video_id={video_id}")
        # Fast-path Rust deserialization directly from JSON string to Pydantic model
        return VideoSummaryResponse.model_validate_json(raw_json)

    except ValidationError as e:
        # Poison-Pill Self-Healing: Our Python Pydantic schema changed after this video was cached
        logger.warning(f"Stale schema in Redis for key={cache_key}. Evicting key and regenerating. Details: {e}")
        try:
            redis_client.delete(cache_key)
        except RedisError:
            pass
        return None

    except RedisError as e:
        # Fail-Open: If Redis is down or times out after 1.0s, log and fall back to Gemini
        logger.warning(f"Redis unavailable during GET for key={cache_key}: {e}")
        return None


def set_cached_summary(
    video_id: str,
    summary: VideoSummaryResponse,
    ttl_seconds: int = settings.CACHE_TTL_SECONDS,) -> bool:
    """Serializes a validated VideoSummaryResponse to JSON and stores it in Redis

    with an atomic TTL expiration timer (SETEX).
    """
    cache_key = f"{SUMMARY_KEY_PREFIX}{video_id}"

    try:
        # Fast-path Rust serialization from Pydantic model to UTF-8 JSON string
        json_payload = summary.model_dump_json()

        # Atomic Set + Expire in a single network round-trip
        redis_client.setex(
            name=cache_key,
            time=ttl_seconds,
            value=json_payload,
        )
        logger.info(f"Cached summary for video_id={video_id} with TTL={ttl_seconds}s")
        return True

    except RedisError as e:
        # Fail-Open: Even if caching fails, we still return the generated summary to the user
        logger.warning(f"Redis unavailable during SETEX for key={cache_key}: {e}")
        return False
    
