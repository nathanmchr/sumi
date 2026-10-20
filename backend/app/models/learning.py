from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.utils.enums import ContentType, ReviewStatus


class LearningState(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "learning_states"
    __table_args__ = (UniqueConstraint("user_id", "content_type", "content_id", name="uq_learning_state_item"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    content_type: Mapped[ContentType] = mapped_column(Enum(ContentType, name="content_type"), index=True)
    content_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus, name="review_status"), default=ReviewStatus.new)
    mastery: Mapped[float] = mapped_column(Float, default=0.0)
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    repetition_count: Mapped[int] = mapped_column(Integer, default=0)
    lapses_count: Mapped[int] = mapped_column(Integer, default=0)
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_session_id: Mapped[str | None] = mapped_column(ForeignKey("study_sessions.id"), nullable=True)
    acquisition: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scheduler_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    fsrs_card: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    consecutive_correct: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    recent_results: Mapped[list[bool]] = mapped_column(JSON, default=list, server_default="[]")
    review_revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class ReviewHistory(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "review_history"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    content_type: Mapped[ContentType] = mapped_column(Enum(ContentType, name="review_content_type"), index=True)
    content_id: Mapped[str] = mapped_column(String(64), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    correct: Mapped[bool] = mapped_column(default=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_window: Mapped[str] = mapped_column(String(16), default="short")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("study_sessions.id"), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class StudySession(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "study_sessions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    mode: Mapped[str] = mapped_column(String(32), default="mixed")
    planned_items: Mapped[int] = mapped_column(Integer, default=0)
    completed_items: Mapped[int] = mapped_column(Integer, default=0)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=10)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)


class StudyQuestion(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "study_questions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("study_sessions.id"), index=True)
    content_type: Mapped[str] = mapped_column(String(16))
    content_id: Mapped[str] = mapped_column(String(64))
    locale: Mapped[str] = mapped_column(String(5))
    prompt: Mapped[dict] = mapped_column(JSON)
    choices: Mapped[list[dict]] = mapped_column(JSON)
    correct_option_id: Mapped[str] = mapped_column(String(64))
    feedback: Mapped[dict] = mapped_column(JSON)
    baseline_revision: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    selected_option_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class GrammarExercise(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "grammar_exercises"

    code: Mapped[str] = mapped_column(String(80), unique=True)
    grammar_item_id: Mapped[str] = mapped_column(ForeignKey("grammar_items.id"), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(String(255))
    distractors: Mapped[list[str]] = mapped_column(JSON)
    completed_sentence: Mapped[str] = mapped_column(Text)
    translations: Mapped[dict] = mapped_column(JSON)
