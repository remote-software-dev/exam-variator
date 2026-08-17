"""SQLAlchemy database models for job persistence."""

import enum
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine, Column, String, Integer, Float, Text, DateTime,
    Enum, JSON, Boolean,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import settings


class Base(DeclarativeBase):
    pass


class JobPhase(str, enum.Enum):
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    SOLVING = "solving"
    SOLVED = "solved"
    VARYING = "varying"
    COMPLETED = "completed"
    FAILED = "failed"


class JobRecord(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True)
    filename = Column(String(512), nullable=False)
    pdf_path = Column(String(1024), nullable=False)
    docx_path = Column(String(1024), nullable=True)
    phase = Column(Enum(JobPhase), nullable=False, default=JobPhase.UPLOADED)
    progress = Column(Float, nullable=False, default=0.0)
    total_pages = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    questions_json = Column(JSON, nullable=True, default=list)
    selected_indices = Column(JSON, nullable=True, default=list)
    variations_json = Column(JSON, nullable=True, default=list)
    custom_instruction = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


_engine = None
_SessionLocal = None
_in_memory = False


def configure_engine(url: str, in_memory: bool = False):
    """Configure a custom engine (for tests)."""
    global _engine, _SessionLocal, _in_memory
    _in_memory = in_memory
    if in_memory:
        _engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        _engine = create_engine(url, connect_args={"check_same_thread": False})
    _SessionLocal = sessionmaker(bind=_engine)


def _get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        configure_engine(settings.database_url)
    return _engine


def _get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _get_engine()
    return _SessionLocal


def init_db():
    engine = _get_engine()
    Base.metadata.create_all(bind=engine)


def get_db():
    sf = _get_session_factory()
    db = sf()
    try:
        yield db
    finally:
        db.close()


def drop_all():
    engine = _get_engine()
    Base.metadata.drop_all(bind=engine)


def SessionLocal():
    """Return a new session (convenience alias)."""
    sf = _get_session_factory()
    return sf()
