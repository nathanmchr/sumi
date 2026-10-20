from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.utils.enums import ContentType, ReviewStatus


class DueItemOut(BaseModel):
    content_type: ContentType
    content_id: str
    title: str
    subtitle: str
    jlpt_level_code: str
    next_review_at: datetime | None = None
    status: ReviewStatus


class SessionRecommendationOut(BaseModel):
    minutes: int
    target_items: int
    focus: list[ContentType]
    rationale: str


