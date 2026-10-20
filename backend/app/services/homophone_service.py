"""Conservative same-reading groups, not inferred pitch-accent classifications."""
from collections import defaultdict
import re
import unicodedata

import jaconv
from sqlalchemy.orm import Session

from app.models.content import VocabularyItem
from app.repositories.content_repository import ContentRepository
from app.schemas.content import HomophoneGroupOut, HomophonePageOut, HomophoneWordOut
from app.services.content_service import _localized_record
from app.services.vocabulary_audio import preferred_audio_url
from app.utils.romaji import normalize_romaji


def normalize_reading(value: str) -> str | None:
    kana = jaconv.kata2hira(unicodedata.normalize("NFKC", value).strip())
    # Do not guess a pronunciation from multi-reading entries or annotations.
    return kana if re.fullmatch(r"[ぁ-ゖ][ぁ-ゖー]*", kana) else None


def _sense(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _meaning_key(item: VocabularyItem) -> tuple[str, ...]:
    # Equal English glosses can still have distinct senses in the French dataset.
    return (_sense(item.translation), *sorted(
        f"{record.locale}:{_sense(record.translation)}" for record in item.translations
    ))


def list_homophones(
    db: Session, query: str = "", locale: str = "en", offset: int = 0, limit: int = 20,
) -> HomophonePageOut:
    groups: dict[str, dict[tuple[str, ...], VocabularyItem]] = defaultdict(dict)
    for item in ContentRepository(db).list_homophone_candidates():
        reading = normalize_reading(item.reading)
        if not reading:
            continue
        identity = (unicodedata.normalize("NFKC", item.japanese), *_meaning_key(item))
        previous = groups[reading].get(identity)
        # Collapse exact cross-level duplicates; prefer playable, then easier entries.
        rank = (not bool(item.audio_url), -int(item.jlpt_level_code[1:]), item.id)
        if previous is None or rank < (
            not bool(previous.audio_url), -int(previous.jlpt_level_code[1:]), previous.id,
        ):
            groups[reading][identity] = item

    term = _sense(query)
    kana_query = normalize_reading(query) if term else None
    romaji_query = normalize_romaji(query) if term else ""
    matches: list[tuple[str, list[VocabularyItem]]] = []
    for reading, unique in groups.items():
        words = list(unique.values())
        if len(words) < 2:
            continue
        # Different spellings of a single identical sense are not a useful contrast.
        if len({_meaning_key(word) for word in words}) == 1:
            continue
        if term and not (kana_query and kana_query in reading) and not any(
            term in _sense(word.japanese) or term in _sense(word.translation)
            or (romaji_query and romaji_query in word.romaji_search)
            or any(record.locale == locale and term in _sense(record.translation) for record in word.translations)
            for word in words
        ):
            continue
        matches.append((reading, words))

    def order(group: tuple[str, list[VocabularyItem]]):
        reading, words = group
        exact = kana_query == reading or bool(romaji_query and any(
            romaji_query in word.romaji_search.split(" / ") for word in words
        ))
        pair_level = sorted((int(word.jlpt_level_code[1:]) for word in words), reverse=True)[1]
        return (not exact, sum(bool(word.audio_url) for word in words) < 2, -pair_level, len(reading), reading)

    matches.sort(key=order)
    result = []
    for reading, words in matches[offset:offset + limit]:
        rendered = []
        for word in sorted(words, key=lambda item: (-int(item.jlpt_level_code[1:]), item.japanese, item.id)):
            localized, translation_locale = _localized_record(word.translations, locale)
            rendered.append(HomophoneWordOut(
                id=word.id, japanese=word.japanese,
                translation=localized.translation if localized else word.translation,
                translation_locale=translation_locale, jlpt_level_code=word.jlpt_level_code,
                audio_url=preferred_audio_url(db, word),
            ))
        result.append(HomophoneGroupOut(reading=reading, words=rendered))
    return HomophonePageOut(groups=result, total=len(matches), offset=offset, limit=limit)
