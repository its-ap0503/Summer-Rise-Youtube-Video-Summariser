from pydantic import BaseModel, Field


class VideoRequest(BaseModel):
    """Request payload containing the YouTube video URL."""

    url: str = Field(
        # ... refers to the  mandatory field
        ...,
        description="Valid YouTube URL (standard, shortened, embed, etc.)",
        example="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    )


class TimestampedNote(BaseModel):
    """A single timestamped revision note anchored to a transcript window."""

    timestamp: str = Field(
        ...,
        description="Formatted MM:SS timestamp for UI display",
        example="05:20",
    )
    start_seconds: int = Field(
        ...,
        description="Integer timestamp in seconds for YouTube IFrame seekTo()",
        example=320,
    )
    heading: str = Field(
        ...,
        description="Concise sub-topic title",
        example="Introduction to B-Tree Indexing",
    )
    summary: str = Field(
        ...,
        description="2-3 sentence technical summary of the concept",
        example="B-Trees maintain sorted data and allow searches, sequential access, insertions, and deletions in logarithmic time.",
    )


class QuizQuestion(BaseModel):
    """Self-assessment multiple-choice quiz question for exam revision."""

    question: str = Field(
        ...,
        description="Conceptual question testing understanding of the lecture segment",
        example="What is the time complexity of search operations in a balanced B-Tree?",
    )
    options: list[str] = Field(
        ...,
        description="Exactly 4 multiple choice options",
        example=["O(1)", "O(log n)", "O(n)", "O(n log n)"],
    )
    correct_answer: str = Field(
        ...,
        description="The exact string matching the correct option",
        example="O(log n)",
    )
    explanation: str = Field(
        ...,
        description="Detailed explanation of why the correct answer is right",
        example="Balanced B-Trees keep keys sorted and maintain a height of log_b(n), resulting in logarithmic search times.",
    )


class VideoSummaryResponse(BaseModel):
    """Root response schema containing the complete structured study companion package."""

    video_id: str = Field(
        ...,
        description="11-character unique YouTube video identifier",
        example="dQw4w9WgXcQ",
    )
    title: str = Field(
        ...,
        description="Inferred professional title of the lecture",
        example="Advanced Database Indexing & B-Trees",
    )
    overview: str = Field(
        ...,
        description="High-level 3-sentence summary of the entire video content",
        example="This lecture explores underlying database indexing strategies, contrasting hash indexes with balanced B-Trees and analyzing disk I/O performance characteristics.",
    )
    notes: list[TimestampedNote] = Field(
        ...,
        description="Chronological list of timestamped revision notes",
    )
    quiz: list[QuizQuestion] = Field(
        ...,
        description="List of self-test quiz questions generated from lecture content",
    )
