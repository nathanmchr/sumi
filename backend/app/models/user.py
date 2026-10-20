from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.utils.enums import FuriganaDisplayMode


class User(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    settings = relationship("UserSettings", uselist=False, back_populates="user", cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")


class UserSettings(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "user_settings"
    __table_args__ = tuple(
        CheckConstraint(f"{category}_min_level_code >= {category}_level_code", name=f"ck_settings_{category}_range")
        for category in ("vocabulary", "grammar", "kanji")
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    vocabulary_level_code: Mapped[str] = mapped_column(ForeignKey("jlpt_levels.code"))
    vocabulary_min_level_code: Mapped[str] = mapped_column(ForeignKey("jlpt_levels.code"), default=lambda context: context.get_current_parameters()["vocabulary_level_code"])
    grammar_level_code: Mapped[str] = mapped_column(ForeignKey("jlpt_levels.code"))
    grammar_min_level_code: Mapped[str] = mapped_column(ForeignKey("jlpt_levels.code"), default=lambda context: context.get_current_parameters()["grammar_level_code"])
    kanji_level_code: Mapped[str] = mapped_column(ForeignKey("jlpt_levels.code"))
    kanji_min_level_code: Mapped[str] = mapped_column(ForeignKey("jlpt_levels.code"), default=lambda context: context.get_current_parameters()["kanji_level_code"])
    furigana_display_mode: Mapped[FuriganaDisplayMode] = mapped_column(String(16), default=FuriganaDisplayMode.always.value)
    furigana_helper_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    romaji_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    daily_goal_minutes: Mapped[int] = mapped_column(Integer, default=20)
    interface_locale: Mapped[str] = mapped_column(String(5), default="en")
    content_locale: Mapped[str] = mapped_column(String(5), default="en")

    user = relationship("User", back_populates="settings")


class RefreshToken(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="refresh_tokens")
