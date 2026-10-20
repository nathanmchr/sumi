from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.utils.enums import ContentType


class JLPTLevelOut(BaseModel):
    code: str
    rank: int
    label: str
    description: str | None = None


class ExampleSentenceOut(BaseModel):
    id: str
    text: str
    translation: str
    furigana_segments: list[dict[str, Any]] = Field(default_factory=list)
    audio_url: str | None = None
    translation_locale: str = "en"


class VocabularyLinkOut(BaseModel):
    kanji_id: str
    kanji_character: str
    kanji_slug: str
    jlpt_level_code: str
    meanings: list[str] = Field(default_factory=list)
    position: int | None = None
    is_primary: bool = True


class VocabularyOut(BaseModel):
    catalog_id: str | None = None
    source_order: int | None = None
    kanji_level_code: str | None = None
    id: str
    slug: str
    japanese: str
    reading: str
    romaji: str = ""
    furigana_segments: list[dict[str, Any]] = Field(default_factory=list)
    translation: str
    part_of_speech: str
    jlpt_level_code: str
    mastery: float = 0.0
    status: str = "new"
    audio_url: str | None = None
    notes: str | None = None
    example_sentences: list[ExampleSentenceOut] = Field(default_factory=list)
    kanji_links: list[VocabularyLinkOut] = Field(default_factory=list)
    translation_locale: str = "en"


class HomophoneWordOut(BaseModel):
    id: str
    japanese: str
    translation: str
    translation_locale: str
    jlpt_level_code: str
    audio_url: str | None = None


class HomophoneGroupOut(BaseModel):
    reading: str
    words: list[HomophoneWordOut]


class HomophonePageOut(BaseModel):
    groups: list[HomophoneGroupOut]
    total: int
    offset: int
    limit: int


class LinkedVocabularyOut(BaseModel):
    vocabulary_id: str
    vocabulary_japanese: str
    vocabulary_reading: str
    jlpt_level_code: str
    furigana_segments: list[dict[str, Any]] = Field(default_factory=list)
    translation: str
    audio_url: str | None = None


class KanjiOut(BaseModel):
    catalog_id: str | None = None
    source_order: int | None = None
    id: str
    character: str
    slug: str
    meanings: list[str] = Field(default_factory=list)
    onyomi: list[str] = Field(default_factory=list)
    kunyomi: list[str] = Field(default_factory=list)
    radicals: list[str] = Field(default_factory=list)
    mnemonic: str | None = None
    jlpt_level_code: str
    mastery: float = 0.0
    status: str = "new"
    linked_vocabulary: list[LinkedVocabularyOut] = Field(default_factory=list)
    translation_locale: str = "en"


class GrammarOut(BaseModel):
    catalog_id: str | None = None
    source_order: int | None = None
    exercisable: bool = False
    id: str
    slug: str
    title: str
    jlpt_level_code: str
    explanation: str
    structure: str
    nuances: str
    counter_examples: list[dict[str, Any]] = Field(default_factory=list)
    examples: list[dict[str, Any]] = Field(default_factory=list)
    mastery: float = 0.0
    status: str = "new"
    translation_locale: str = "en"


class DashboardStatsOut(BaseModel):
    learned_items: int
    due_reviews: int
    streak_days: int
    estimated_session_minutes: int
    progression_by_category: dict[str, float]
    recommendation: str


class SearchOut(BaseModel):
    content_type: ContentType
    id: str
    title: str
    subtitle: str
    jlpt_level_code: str
    url: str
