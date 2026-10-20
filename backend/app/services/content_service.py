from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.content import GrammarItem, KanjiItem, VocabularyItem
from app.models.learning import GrammarExercise, LearningState
from app.repositories.content_repository import ContentRepository
from app.schemas.content import (
    ExampleSentenceOut,
    GrammarOut,
    KanjiOut,
    LinkedVocabularyOut,
    SearchOut,
    VocabularyLinkOut,
    VocabularyOut,
)
from app.services.fsrs_service import memory_status
from app.services.vocabulary_audio import preferred_audio_url
from app.utils.enums import ContentType, ReviewStatus


def _localized_record(records: list, locale: str):
    requested = next((record for record in records if record.locale == locale), None)
    english = next((record for record in records if record.locale == "en"), None)
    selected = requested or english or next(iter(records), None)
    return selected, selected.locale if selected else "en"


def vocabulary_out(db: Session, item: VocabularyItem, user_id: str | None = None, locale: str = "en") -> VocabularyOut:
    localized, translation_locale = _localized_record(item.translations, locale)
    state = None
    if user_id:
        state = db.query(LearningState).filter(
            LearningState.user_id == user_id,
            LearningState.content_type == ContentType.vocabulary,
            LearningState.content_id == item.id,
        ).first()
    links: list[VocabularyLinkOut] = []
    for link in sorted(item.kanji_links, key=lambda link: (link.kanji_position or float("inf"), link.kanji_item.id)):
        localized_kanji, _ = _localized_record(link.kanji_item.translations, locale)
        links.append(
            VocabularyLinkOut(
                kanji_id=link.kanji_item.id,
                kanji_character=link.kanji_item.character,
                kanji_slug=link.kanji_item.slug,
                jlpt_level_code=link.kanji_item.jlpt_level_code,
                meanings=localized_kanji.meanings if localized_kanji else link.kanji_item.meanings or [],
                position=link.kanji_position,
                is_primary=link.is_primary,
            )
        )
    return VocabularyOut(
        catalog_id=item.catalog_id,
        source_order=item.source_order,
        kanji_level_code=item.kanji_level_code,
        id=item.id,
        slug=item.slug,
        japanese=item.japanese,
        reading=item.reading,
        romaji=item.romaji or "",
        furigana_segments=item.furigana_segments or [],
        translation=localized.translation if localized else item.translation,
        part_of_speech=item.part_of_speech,
        jlpt_level_code=item.jlpt_level_code,
        mastery=state.mastery if state else 0.0,
        status=memory_status(state, datetime.now(timezone.utc)) if state else ReviewStatus.new,
        audio_url=preferred_audio_url(db, item),
        notes=localized.notes if localized else item.notes,
        example_sentences=[_example_out(ex, locale) for ex in item.example_sentences],
        kanji_links=links,
        translation_locale=translation_locale,
    )


def _example_out(example, locale: str) -> ExampleSentenceOut:
    localized, translation_locale = _localized_record(example.translations, locale)
    return ExampleSentenceOut(
        id=example.id,
        text=example.text,
        translation=localized.translation if localized else example.translation,
        furigana_segments=example.furigana_segments or [],
        audio_url=example.audio_url,
        translation_locale=translation_locale,
    )


def kanji_out(db: Session, item: KanjiItem, user_id: str | None = None, locale: str = "en") -> KanjiOut:
    localized, translation_locale = _localized_record(item.translations, locale)
    state = None
    if user_id:
        state = db.query(LearningState).filter(
            LearningState.user_id == user_id,
            LearningState.content_type == ContentType.kanji,
            LearningState.content_id == item.id,
        ).first()
    linked: list[LinkedVocabularyOut] = []
    for link in sorted(item.vocabulary_links, key=lambda link: (link.vocabulary_item.source_order or float("inf"), link.vocabulary_item.id)):
        localized_vocabulary, _ = _localized_record(link.vocabulary_item.translations, locale)
        linked.append(
            LinkedVocabularyOut(
                vocabulary_id=link.vocabulary_item.id,
                vocabulary_japanese=link.vocabulary_item.japanese,
                vocabulary_reading=link.vocabulary_item.reading,
                jlpt_level_code=link.vocabulary_item.jlpt_level_code,
                furigana_segments=link.vocabulary_item.furigana_segments or [],
                translation=localized_vocabulary.translation if localized_vocabulary else link.vocabulary_item.translation,
                audio_url=preferred_audio_url(db, link.vocabulary_item),
            )
        )
    return KanjiOut(
        catalog_id=item.catalog_id,
        source_order=item.source_order,
        id=item.id,
        character=item.character,
        slug=item.slug,
        meanings=localized.meanings if localized else item.meanings or [],
        onyomi=item.onyomi or [],
        kunyomi=item.kunyomi or [],
        radicals=item.radicals or [],
        mnemonic=localized.mnemonic if localized else item.mnemonic,
        jlpt_level_code=item.jlpt_level_code,
        mastery=state.mastery if state else 0.0,
        status=memory_status(state, datetime.now(timezone.utc)) if state else ReviewStatus.new,
        linked_vocabulary=linked,
        translation_locale=translation_locale,
    )


def grammar_out(db: Session, item: GrammarItem, user_id: str | None = None, locale: str = "en") -> GrammarOut:
    localized, translation_locale = _localized_record(item.translations, locale)
    state = None
    if user_id:
        state = db.query(LearningState).filter(
            LearningState.user_id == user_id,
            LearningState.content_type == ContentType.grammar,
            LearningState.content_id == item.id,
        ).first()
    return GrammarOut(
        catalog_id=item.catalog_id,
        source_order=item.source_order,
        exercisable=db.scalar(select(GrammarExercise.id).where(GrammarExercise.grammar_item_id == item.id).limit(1)) is not None,
        id=item.id,
        slug=item.slug,
        title=item.title,
        jlpt_level_code=item.jlpt_level_code,
        explanation=localized.explanation if localized else item.explanation,
        structure=item.structure,
        nuances=localized.nuances if localized else item.nuances,
        counter_examples=item.counter_examples or [],
        examples=item.examples or [],
        mastery=state.mastery if state else 0.0,
        status=memory_status(state, datetime.now(timezone.utc)) if state else ReviewStatus.new,
        translation_locale=translation_locale,
    )


def search_content(db: Session, term: str, locale: str = "en") -> list[SearchOut]:
    repo = ContentRepository(db)
    results: list[SearchOut] = []
    for item in repo.list_vocabulary(search=term, locale=locale, limit=8):
        localized, _ = _localized_record(item.translations, locale)
        results.append(
            SearchOut(
                content_type=ContentType.vocabulary,
                id=item.id,
                title=item.japanese,
                subtitle=localized.translation if localized else item.translation,
                jlpt_level_code=item.jlpt_level_code,
                url=f"/study/vocabulary/{item.id}",
            )
        )
    for item in repo.list_kanji(search=term, locale=locale, limit=8):
        localized, _ = _localized_record(item.translations, locale)
        results.append(
            SearchOut(
                content_type=ContentType.kanji,
                id=item.id,
                title=item.character,
                subtitle=", ".join((localized.meanings if localized else item.meanings)[:3]),
                jlpt_level_code=item.jlpt_level_code,
                url=f"/study/kanji/{item.id}",
            )
        )
    for item in repo.list_grammar(search=term, locale=locale, limit=8):
        localized, _ = _localized_record(item.translations, locale)
        results.append(
            SearchOut(
                content_type=ContentType.grammar,
                id=item.id,
                title=item.title,
                subtitle=localized.explanation if localized else item.explanation,
                jlpt_level_code=item.jlpt_level_code,
                url=f"/study/grammar/{item.id}",
            )
        )
    return results
