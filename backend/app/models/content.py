from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.utils.enums import ContentType


class JLPTLevel(Base, TimestampMixin):
    __tablename__ = "jlpt_levels"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    rank: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(32), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class VocabularyItem(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "vocabulary_items"

    catalog_id: Mapped[str | None] = mapped_column(String(36), unique=True, index=True, nullable=True)
    source_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kanji_level_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    japanese: Mapped[str] = mapped_column(String(255), index=True)
    reading: Mapped[str] = mapped_column(String(255))
    romaji: Mapped[str] = mapped_column(Text, default="", server_default="")
    romaji_search: Mapped[str] = mapped_column(Text, default="", server_default="")
    furigana_segments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    translation: Mapped[str] = mapped_column(String(255))
    part_of_speech: Mapped[str] = mapped_column(String(64))
    jlpt_level_code: Mapped[str] = mapped_column(ForeignKey("jlpt_levels.code"), index=True)
    audio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    jlpt_level = relationship("JLPTLevel")
    example_sentences = relationship("ExampleSentence", back_populates="vocabulary_item")
    kanji_links = relationship("VocabularyKanjiLink", back_populates="vocabulary_item", cascade="all, delete-orphan")
    translations = relationship("VocabularyTranslation", back_populates="vocabulary_item", cascade="all, delete-orphan")


class VocabularyTranslation(Base, TimestampMixin):
    __tablename__ = "vocabulary_translations"

    vocabulary_item_id: Mapped[str] = mapped_column(ForeignKey("vocabulary_items.id"), primary_key=True)
    locale: Mapped[str] = mapped_column(String(5), primary_key=True)
    translation: Mapped[str] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    vocabulary_item = relationship("VocabularyItem", back_populates="translations")


class KanjiItem(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "kanji_items"

    catalog_id: Mapped[str | None] = mapped_column(String(36), unique=True, index=True, nullable=True)
    source_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    character: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    meanings: Mapped[list[str]] = mapped_column(JSON, default=list)
    onyomi: Mapped[list[str]] = mapped_column(JSON, default=list)
    kunyomi: Mapped[list[str]] = mapped_column(JSON, default=list)
    romaji_search: Mapped[str] = mapped_column(Text, default="", server_default="")
    radicals: Mapped[list[str]] = mapped_column(JSON, default=list)
    mnemonic: Mapped[str | None] = mapped_column(Text, nullable=True)
    jlpt_level_code: Mapped[str] = mapped_column(ForeignKey("jlpt_levels.code"), index=True)

    jlpt_level = relationship("JLPTLevel")
    vocabulary_links = relationship("VocabularyKanjiLink", back_populates="kanji_item", cascade="all, delete-orphan")
    translations = relationship("KanjiTranslation", back_populates="kanji_item", cascade="all, delete-orphan")


class KanjiTranslation(Base, TimestampMixin):
    __tablename__ = "kanji_translations"

    kanji_item_id: Mapped[str] = mapped_column(ForeignKey("kanji_items.id"), primary_key=True)
    locale: Mapped[str] = mapped_column(String(5), primary_key=True)
    meanings: Mapped[list[str]] = mapped_column(JSON, default=list)
    mnemonic: Mapped[str | None] = mapped_column(Text, nullable=True)

    kanji_item = relationship("KanjiItem", back_populates="translations")


class GrammarItem(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "grammar_items"
    __table_args__ = (UniqueConstraint("slug", name="uq_grammar_slug"),)

    catalog_id: Mapped[str | None] = mapped_column(String(36), unique=True, index=True, nullable=True)
    source_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slug: Mapped[str] = mapped_column(String(160), index=True)
    title: Mapped[str] = mapped_column(String(255))
    jlpt_level_code: Mapped[str] = mapped_column(ForeignKey("jlpt_levels.code"), index=True)
    explanation: Mapped[str] = mapped_column(Text)
    structure: Mapped[str] = mapped_column(Text)
    romaji_search: Mapped[str] = mapped_column(Text, default="", server_default="")
    nuances: Mapped[str] = mapped_column(Text)
    counter_examples: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    examples: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    jlpt_level = relationship("JLPTLevel")
    example_sentences = relationship("ExampleSentence", back_populates="grammar_item")
    translations = relationship("GrammarTranslation", back_populates="grammar_item", cascade="all, delete-orphan")


class ContentAlias(Base):
    """Old IDs/slugs of absorbed entries; resolved only within their category."""
    __tablename__ = "content_aliases"

    content_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    alias: Mapped[str] = mapped_column(String(160), primary_key=True)
    content_id: Mapped[str] = mapped_column(String(64))


class GrammarTranslation(Base, TimestampMixin):
    __tablename__ = "grammar_translations"

    grammar_item_id: Mapped[str] = mapped_column(ForeignKey("grammar_items.id"), primary_key=True)
    locale: Mapped[str] = mapped_column(String(5), primary_key=True)
    explanation: Mapped[str] = mapped_column(Text)
    nuances: Mapped[str] = mapped_column(Text, default="")

    grammar_item = relationship("GrammarItem", back_populates="translations")


class ExampleSentence(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "example_sentences"

    text: Mapped[str] = mapped_column(Text)
    translation: Mapped[str] = mapped_column(Text)
    furigana_segments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    audio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    vocabulary_item_id: Mapped[str | None] = mapped_column(ForeignKey("vocabulary_items.id"), nullable=True, index=True)
    grammar_item_id: Mapped[str | None] = mapped_column(ForeignKey("grammar_items.id"), nullable=True, index=True)

    vocabulary_item = relationship("VocabularyItem", back_populates="example_sentences")
    grammar_item = relationship("GrammarItem", back_populates="example_sentences")
    translations = relationship("ExampleSentenceTranslation", back_populates="example_sentence", cascade="all, delete-orphan")


class ExampleSentenceTranslation(Base, TimestampMixin):
    __tablename__ = "example_sentence_translations"

    example_sentence_id: Mapped[str] = mapped_column(ForeignKey("example_sentences.id"), primary_key=True)
    locale: Mapped[str] = mapped_column(String(5), primary_key=True)
    translation: Mapped[str] = mapped_column(Text)

    example_sentence = relationship("ExampleSentence", back_populates="translations")


class VocabularyKanjiLink(Base):
    __tablename__ = "vocabulary_kanji_links"
    __table_args__ = (UniqueConstraint("vocabulary_item_id", "kanji_item_id", name="uq_vocab_kanji_link"),)

    vocabulary_item_id: Mapped[str] = mapped_column(ForeignKey("vocabulary_items.id"), primary_key=True)
    kanji_item_id: Mapped[str] = mapped_column(ForeignKey("kanji_items.id"), primary_key=True)
    kanji_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)

    vocabulary_item = relationship("VocabularyItem", back_populates="kanji_links")
    kanji_item = relationship("KanjiItem", back_populates="vocabulary_links")
