from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.utils.enums import ContentType, ReviewStatus


class QuizStartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: ContentType | None = None
    content_id: UUID | None = None
    only_due: bool = False
    planned_items: int = Field(default=12, ge=1, le=30)

    @model_validator(mode="after")
    def target_requires_category(self):
        if self.content_id and not self.category:
            raise ValueError("category is required with content_id")
        return self


class ChoiceOut(BaseModel):
    id: str
    label: str


class AnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    option_id: UUID


class FeedbackExample(BaseModel):
    text: str
    translation: str
    reading: str = ""


class IntroductionOut(BaseModel):
    meaning: str
    example: FeedbackExample | None = None


class MemoryProgressOut(BaseModel):
    phase: Literal["acquisition", "consolidation"]
    value: float = Field(ge=0, le=1)
    successes: int | None = None
    required_successes: int | None = None


class AnswerOut(BaseModel):
    memory: MemoryProgressOut | None = None
    planned_items: int | None = None
    question_id: str
    selected_option_id: str
    correct_option_id: str
    correct: bool
    title: str
    reading: str
    meaning: str
    explanation: str = ""
    example: FeedbackExample | None = None
    status: ReviewStatus
    next_review_at: datetime | None
    difficulty: float | None
    stability: float | None
    retrievability: float | None


class QuestionOut(BaseModel):
    phase: Literal["introduction", "question"] = "question"
    introduction: IntroductionOut | None = None
    id: str
    content_type: ContentType
    content_id: str
    kind: Literal["meaning", "cloze"]
    title: str
    reading: str
    furigana_segments: list[dict[str, Any]] = Field(default_factory=list)
    instruction: str
    context: str = ""
    jlpt_level_code: str
    locale: Literal["en", "fr"]
    audio_url: str | None = None
    choices: list[ChoiceOut]
    expires_at: datetime
    result: AnswerOut | None = None


class QuizTurnOut(BaseModel):
    acquired_items: int = 0
    acquiring_items: int = 0
    session_id: str
    completed_items: int
    planned_items: int
    correct_answers: int
    ended: bool
    question: QuestionOut | None = None
    next_due_at: datetime | None = None
    grammar_points_available: int = 0
    unavailable_items: int = 0
