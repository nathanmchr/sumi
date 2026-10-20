from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class LessonCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["answer", "continue"]
    step_id: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=0)
    answer: str | None = Field(default=None, max_length=300)


class LessonSummary(BaseModel):
    id: str
    unit_id: str
    unit_title: str
    title: str
    goal: str
    position: int
    minutes: int
    total_steps: int
    completed_steps: int
    completed: bool
    recommended: bool = False
    is_recap: bool = False
    locked: bool = False
    vocabulary_count: int
    grammar_count: int
    kanji_count: int


class LessonState(BaseModel):
    lesson: LessonSummary
    revision: int
    cursor: int
    viewing: int
    step: dict[str, Any] | None
    feedback: dict[str, Any] | None
    correct: int
    answered: int
    next_lesson_id: str | None
    recap_total: int = 0
    recap_answered: int = 0
    recap_correct: int = 0
