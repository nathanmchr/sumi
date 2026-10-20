from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.content import ExampleSentence, GrammarItem, JLPTLevel, KanjiItem, VocabularyItem, VocabularyKanjiLink
from app.repositories.content_repository import ContentRepository
from app.schemas.imports import ImportSummaryOut
from app.utils.enums import ContentType
from app.utils.furigana import build_furigana, validate_furigana


def _parse_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _split_csv_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [chunk.strip() for chunk in value.split(",") if chunk.strip()]


def _furigana_segments_from_row(row: dict[str, str]) -> list[dict[str, Any]]:
    reading = row.get("reading") or row.get("kana") or ""
    japanese = row.get("japanese") or row.get("text") or row.get("character") or ""
    if not japanese:
        return []
    if row.get("furigana_json"):
        return validate_furigana(japanese, reading, json.loads(row["furigana_json"]))
    return build_furigana(japanese, reading)[0]


@dataclass
class ImportSummary:
    item_type: str
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def to_out(self) -> ImportSummaryOut:
        return ImportSummaryOut(**self.__dict__)


def ensure_reference_levels(db: Session) -> None:
    repo = ContentRepository(db)
    levels = [
        ("N5", 5, "JLPT N5", "Foundational vocabulary and grammar."),
        ("N4", 4, "JLPT N4", "Basic everyday language."),
        ("N3", 3, "JLPT N3", "Intermediate bridge level."),
        ("N2", 2, "JLPT N2", "Upper-intermediate."),
        ("N1", 1, "JLPT N1", "Advanced proficiency."),
    ]
    for code, rank, label, description in levels:
        repo.upsert_jlpt_level(code, rank, label, description)
    db.commit()


def import_csv(
    db: Session,
    item_type: ContentType,
    csv_path: Path,
    *,
    delimiter: str = ",",
    transform_row: Callable[[dict[str, str], int], dict[str, str]] | None = None,
) -> ImportSummary:
    # Once adopted, the reviewed repository catalogue is the sole editorial
    # source. A slug-based upload must not silently recreate absorbed records.
    for model in (VocabularyItem, KanjiItem, GrammarItem):
        if db.scalar(select(model.id).where(model.catalog_id.is_not(None)).limit(1)):
            raise ValueError("Le site utilise le catalogue consolidé. Modifiez sa source puis lancez scripts.sync_catalog avec sauvegarde.")
    repo = ContentRepository(db)
    summary = ImportSummary(item_type=item_type.value)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        for index, row in enumerate(reader, start=2):
            try:
                with db.begin_nested():
                    if transform_row:
                        row = transform_row(row, index)
                    if item_type == ContentType.vocabulary:
                        action = _import_vocabulary_row(db, repo, row)
                    elif item_type == ContentType.kanji:
                        action = _import_kanji_row(db, repo, row)
                    else:
                        action = _import_grammar_row(db, repo, row)
                summary.created += 1 if action == "created" else 0
                summary.updated += 1 if action == "updated" else 0
            except Exception as exc:  # pragma: no cover - import safety boundary
                summary.errors.append(f"Line {index}: {exc}")
                summary.skipped += 1
    db.commit()
    return summary


def _import_vocabulary_row(db: Session, repo: ContentRepository, row: dict[str, str]) -> str:
    existing = repo.get_vocabulary_by_slug(row["slug"])
    english_translation = row.get("translation_en")
    canonical_translation = english_translation or row.get("translation_fr") or row["translation"]
    payload = {
        "slug": row["slug"],
        "japanese": row["japanese"],
        "reading": row.get("reading") or row.get("kana"),
        "furigana_segments": _furigana_segments_from_row(row),
        "romaji": row.get("romaji", ""),
        "translation": canonical_translation,
        "part_of_speech": row.get("part_of_speech", "noun"),
        "jlpt_level_code": row.get("jlpt_level", "N5"),
        "audio_url": row.get("audio_url") or None,
        "notes": row.get("notes") or None,
    }
    item = repo.upsert_vocabulary(payload)
    if english_translation or "translation_en" not in row:
        repo.upsert_vocabulary_translation(
            {
                "vocabulary_item_id": item.id,
                "locale": "en",
                "translation": english_translation or row["translation"],
                "notes": row.get("notes_en") or row.get("notes") or None,
            }
        )
    if row.get("translation_fr"):
        repo.upsert_vocabulary_translation(
            {
                "vocabulary_item_id": item.id,
                "locale": "fr",
                "translation": row["translation_fr"],
                "notes": row.get("notes_fr") or None,
            }
        )
    example_text = row.get("example_japanese")
    if example_text:
        example = repo.upsert_example(
            {
                "text": example_text,
                "translation": row.get("example_translation", ""),
                "furigana_segments": _parse_json(row.get("example_furigana_json"), [{"surface": example_text, "reading": row.get("example_reading", ""), "kanji_ids": []}]),
                "audio_url": row.get("example_audio_url") or None,
                "vocabulary_item_id": item.id,
            }
        )
        if not example.vocabulary_item_id:
            example.vocabulary_item_id = item.id
        db.flush()
        repo.upsert_example_translation(
            {"example_sentence_id": example.id, "locale": "en", "translation": row.get("example_translation_en") or row.get("example_translation", "")}
        )
        if row.get("example_translation_fr"):
            repo.upsert_example_translation(
                {"example_sentence_id": example.id, "locale": "fr", "translation": row["example_translation_fr"]}
            )
    repo.replace_vocabulary_links(
        item.id,
        [
            {"kanji_item_id": kanji.id, "kanji_position": position, "is_primary": True}
            for position, kanji_char in enumerate(_split_csv_list(row.get("kanji_links")), start=1)
            if (kanji := db.query(KanjiItem).filter(KanjiItem.character == kanji_char).first())
        ],
    )
    return "updated" if existing else "created"


def _import_kanji_row(db: Session, repo: ContentRepository, row: dict[str, str]) -> str:
    existing = repo.get_kanji_by_character(row["character"])
    character = row["character"]
    english_meanings = _split_csv_list(row.get("meanings_en") or row.get("meanings"))
    item = repo.upsert_kanji(
        {
            "character": character,
            "slug": row.get("slug") or character,
            "meanings": english_meanings,
            "onyomi": _split_csv_list(row.get("onyomi")),
            "kunyomi": _split_csv_list(row.get("kunyomi")),
            "radicals": _split_csv_list(row.get("radicals")),
            "mnemonic": row.get("mnemonic") or None,
            "jlpt_level_code": row.get("jlpt_level", "N5"),
        }
    )
    repo.upsert_kanji_translation(
        {
            "kanji_item_id": item.id,
            "locale": "en",
            "meanings": english_meanings,
            "mnemonic": row.get("mnemonic_en") or row.get("mnemonic") or None,
        }
    )
    if row.get("meanings_fr"):
        repo.upsert_kanji_translation(
            {
                "kanji_item_id": item.id,
                "locale": "fr",
                "meanings": _split_csv_list(row.get("meanings_fr")),
                "mnemonic": row.get("mnemonic_fr") or None,
            }
        )
    return "updated" if existing else "created"


def _import_grammar_row(db: Session, repo: ContentRepository, row: dict[str, str]) -> str:
    existing = repo.get_grammar_by_slug(row["slug"])
    english_explanation = row.get("explanation_en") or row["explanation"]
    item = repo.upsert_grammar(
        {
            "slug": row["slug"],
            "title": row["title"],
            "jlpt_level_code": row.get("jlpt_level", "N5"),
            "explanation": english_explanation,
            "structure": row.get("structure", ""),
            "nuances": row.get("nuances", ""),
            "counter_examples": _parse_json(row.get("counter_examples_json"), []),
            "examples": _parse_json(row.get("examples_json"), []),
        }
    )
    repo.upsert_grammar_translation(
        {
            "grammar_item_id": item.id,
            "locale": "en",
            "explanation": english_explanation,
            "nuances": row.get("nuances_en") or row.get("nuances", ""),
        }
    )
    if row.get("explanation_fr"):
        repo.upsert_grammar_translation(
            {
                "grammar_item_id": item.id,
                "locale": "fr",
                "explanation": row["explanation_fr"],
                "nuances": row.get("nuances_fr") or "",
            }
        )
    if row.get("example_japanese"):
        example = repo.upsert_example(
            {
                "text": row["example_japanese"],
                "translation": row.get("example_translation", ""),
                "furigana_segments": _parse_json(row.get("example_furigana_json"), [{"surface": row["example_japanese"], "reading": row.get("example_reading", ""), "kanji_ids": []}]),
                "audio_url": row.get("example_audio_url") or None,
                "grammar_item_id": item.id,
            }
        )
        db.flush()
        repo.upsert_example_translation(
            {"example_sentence_id": example.id, "locale": "en", "translation": row.get("example_translation_en") or row.get("example_translation", "")}
        )
        if row.get("example_translation_fr"):
            repo.upsert_example_translation(
                {"example_sentence_id": example.id, "locale": "fr", "translation": row["example_translation_fr"]}
            )
    return "updated" if existing else "created"
