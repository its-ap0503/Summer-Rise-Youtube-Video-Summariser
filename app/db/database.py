import logging
from datetime import datetime
from typing import Any, Generator

from sqlalchemy import DateTime, String, Text, create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import settings
from app.schemas.video import VideoSummaryResponse

logger = logging.getLogger(__name__)

# 1. Normalize legacy cloud Postgres URI scheme ("postgres://" -> "postgresql://")
raw_db_url = settings.DATABASE_URL
if raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)

# 2. Initialize the SQLAlchemy Engine & QueuePool
engine = create_engine(
    raw_db_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=1800,
)

# 3. Create the transactional Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# 4. Define the SQLAlchemy 2.0 Declarative Base & Hybrid ORM Model
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


class VideoSummaryModel(Base):
    """ORM model mapping to the 'video_summaries' table in PostgreSQL.

    Combines B-Tree indexed relational columns with binary JSONB columns.
    """

    __tablename__ = "video_summaries"

    # Primary Key (Automatically creates a unique B-Tree index in PostgreSQL)
    video_id: Mapped[str] = mapped_column(String(11), primary_key=True)

    # Relational metadata columns for fast sidebar/history queries
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    overview: Mapped[str] = mapped_column(Text, nullable=False)

    # Decomposed binary JSON (JSONB) columns for zero-JOIN nested reads
    notes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    quiz: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)

    # Server-side UTC timestamp indexed for fast chronological sorting
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )


def init_db() -> None:
    """Creates database tables on startup if they do not already exist."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI Dependency that provides a transactional database session per request

    and guarantees returning the TCP connection to QueuePool upon completion.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_summary_from_db(db: Session, video_id: str) -> VideoSummaryResponse | None:
    """Tier 2 Read: Fetches a saved video summary from PostgreSQL by its Primary Key.

    Runs in O(log N) time via the B-Tree primary key index.
    """
    try:
        record = db.get(VideoSummaryModel, video_id)
        if record is None:
            logger.info(f"Postgres L2 MISS for video_id={video_id}")
            return None

        logger.info(f"Postgres L2 HIT for video_id={video_id}")
        return VideoSummaryResponse(
            video_id=record.video_id,
            title=record.title,
            overview=record.overview,
            notes=record.notes,
            quiz=record.quiz,
        )

    except SQLAlchemyError as e:
        logger.error(f"Postgres error during GET for video_id={video_id}: {e}")
        return None


def save_summary_to_db(db: Session, summary: VideoSummaryResponse) -> bool:
    """Tier 2 Write: Persists a validated VideoSummaryResponse into PostgreSQL.

    Uses db.merge() for idempotent upserts to prevent duplicate-key crashes
    if two concurrent requests summarize the same video simultaneously.
    """
    try:
        db_record = VideoSummaryModel(
            video_id=summary.video_id,
            title=summary.title,
            overview=summary.overview,
            # Convert Pydantic sub-models into native Python dicts for JSONB storage
            notes=[note.model_dump() for note in summary.notes],
            quiz=[q.model_dump() for q in summary.quiz],
        )

        # merge() checks if the Primary Key already exists and updates or inserts safely
        db.merge(db_record)
        db.commit()
        logger.info(f"Saved summary for video_id={summary.video_id} to PostgreSQL")
        return True

    except SQLAlchemyError as e:
        # Mandatory rollback to clear the aborted transaction state on the connection
        db.rollback()
        logger.error(f"Postgres error during SAVE for video_id={summary.video_id}: {e}")
        return False


def get_recent_summaries(db: Session, limit: int = 20) -> list[dict[str, Any]]:
    """Fetches lightweight metadata for the most recently summarized lectures.

    Uses explicit column projection to skip reading heavy JSONB blobs from disk.
    """
    try:
        stmt = (
            select(
                VideoSummaryModel.video_id,
                VideoSummaryModel.title,
                VideoSummaryModel.overview,
                VideoSummaryModel.created_at,
            )
            .order_by(VideoSummaryModel.created_at.desc())
            .limit(limit)
        )

        rows = db.execute(stmt).all()

        return [
            {
                "video_id": row.video_id,
                "title": row.title,
                "overview": row.overview,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]

    except SQLAlchemyError as e:
        logger.error(f"Postgres error fetching recent history: {e}")
        return []
