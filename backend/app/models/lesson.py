from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class Lesson(Base, TimestampMixin):
    __tablename__ = "lessons"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    level: Mapped[str] = mapped_column(ForeignKey("jlpt_levels.code"), index=True)
    position: Mapped[int] = mapped_column(Integer, unique=True)
    version: Mapped[str] = mapped_column(String(64))
    content: Mapped[dict[str, Any]] = mapped_column(JSON)


class LessonProgress(Base, TimestampMixin):
    __tablename__ = "lesson_progress"
    __table_args__ = (CheckConstraint("cursor >= 0 AND revision >= 0", name="ck_lesson_progress_nonnegative"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    lesson_id: Mapped[str] = mapped_column(ForeignKey("lessons.id"), primary_key=True)
    version: Mapped[str] = mapped_column(String(64))
    cursor: Mapped[int] = mapped_column(Integer, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    answers: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    step_order: Mapped[list[str] | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    recap_steps: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    last_command: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
