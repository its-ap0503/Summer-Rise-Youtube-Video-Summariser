import logging

from google import genai
from google.genai import types

from app.core.config import settings
from app.schemas.video import VideoSummaryResponse

logger = logging.getLogger(__name__)

# Lazily initialized Google GenAI client (created on first API call,
# so the module can be imported even before the API key is configured).
_client = None


def _get_client() -> genai.Client:
    """Returns (and lazily creates) the Google GenAI client."""
    global _client
    if _client is None:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set. Please add it to your .env file.")
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


SYSTEM_INSTRUCTION = (
    "You are an expert AI educational assistant and senior software engineer. "
    "Your task is to analyze the provided lecture, extract key conceptual sections "
    "with accurate timestamp anchors, provide clear technical summaries, and generate "
    "high-yield multiple-choice exam revision questions. Always write in English."
)

REQUIREMENTS = """
Requirements:
1. Create a professional, descriptive title for the lecture.
2. Write a high-level 3-sentence overview of the entire video.
3. Group related concepts into chronological timestamped notes. {timestamp_rule}
4. Generate 3 to 5 rigorous multiple-choice quiz questions to test core understanding, each with
   exactly 4 options, a correct_answer that is copied EXACTLY from one of the options, and an explanation.
"""


def _clean_summary(summary: VideoSummaryResponse, video_id: str) -> VideoSummaryResponse:
    """Enforces invariants the LLM may violate (the schema alone can't)."""
    summary.video_id = video_id
    summary.title = summary.title.strip()[:255]
    summary.notes = sorted(summary.notes, key=lambda n: n.start_seconds)

    valid_quiz = []
    for q in summary.quiz:
        if len(q.options) == 4 and q.correct_answer in q.options:
            valid_quiz.append(q)
        else:
            logger.warning(f"Dropping malformed quiz question for {video_id}: {q.question!r}")
    summary.quiz = valid_quiz
    return summary


def generate_video_summary(windowed_data: dict | None, video_id: str) -> VideoSummaryResponse:
    """Generates a structured study guide.

    * windowed_data given  -> summarize the transcript text.
    * windowed_data is None -> fallback: let Gemini read the YouTube URL directly
      (used when YouTube blocks our server's IP for transcript scraping).
    """
    client = _get_client()

    if windowed_data is not None:
        chunks = windowed_data.get("chunks", [])
        if not chunks:
            raise ValueError("Provided transcript chunks are empty. Cannot generate summary.")

        transcript_text = "\n".join(
            f"[{c['timestamp']}] (Seconds: {c['start_seconds']}): {c['text']}" for c in chunks
        )
        prompt = (
            "Analyze the following YouTube lecture transcript chunks and generate a "
            "comprehensive study companion package.\n\nTranscript:\n"
            + transcript_text
            + REQUIREMENTS.format(
                timestamp_rule="Each note MUST use the exact `timestamp` and `start_seconds` "
                "from the transcript chunk where that topic starts."
            )
        )
        contents = prompt
    else:
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        prompt = (
            "Watch this YouTube lecture and generate a comprehensive study companion package."
            + REQUIREMENTS.format(
                timestamp_rule="Each note's `start_seconds` must be where the topic actually starts "
                "in the video and `timestamp` must be the same time formatted MM:SS (or HH:MM:SS)."
            )
        )
        contents = types.Content(
            parts=[
                types.Part(file_data=types.FileData(file_uri=video_url)),
                types.Part(text=prompt),
            ]
        )

    try:
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=VideoSummaryResponse,
                temperature=0.3,
                max_output_tokens=8192,
            ),
        )

        parsed = response.parsed
        if not isinstance(parsed, VideoSummaryResponse):
            # Usually means the JSON was truncated or blocked by safety filters
            raise RuntimeError("Failed to parse structured response from Gemini model.")

        return _clean_summary(parsed, video_id)

    except Exception as e:
        logger.error(f"Error during LLM structured generation for video {video_id}: {e}")
        raise RuntimeError(f"LLM Summarization failed: {e}") from e