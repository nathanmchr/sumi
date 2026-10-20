"""Share audio between explicitly reviewed kana/kanji spellings of the same word."""

import csv
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.models.content import VocabularyItem
from app.services.catalog_audio import catalog_audio


@lru_cache(maxsize=1)
def audio_aliases() -> dict[tuple[str, str], str]:
    path = Path(__file__).resolve().parents[1] / "data" / "vocabulary_audio_aliases.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return {
            (row["kana"], row["translation_en"].strip().casefold()): row["audio_kanji"]
            for row in csv.DictReader(handle, delimiter=";")
        }


def preferred_audio_url(db: Session, item: VocabularyItem) -> str | None:
    matched, url = catalog_audio(item, db)
    if matched:
        return url
    # A shared reading alone is not enough: はし can mean chopsticks or bridge.
    if item.japanese != item.reading:
        return item.audio_url
    aliases = audio_aliases()
    target = aliases.get((item.reading, item.translation.strip().casefold()))
    if not target:
        return item.audio_url

    # One batched lookup per request/session, including linked vocabulary cards.
    cache_key = "vocabulary_audio_alias_urls"
    if cache_key not in db.info:
        targets = {(kanji, kana) for (kana, _), kanji in aliases.items() if kanji}
        db.info[cache_key] = {
            (japanese, reading): url
            for japanese, reading, url in db.execute(
                select(VocabularyItem.japanese, VocabularyItem.reading, VocabularyItem.audio_url)
                .where(tuple_(VocabularyItem.japanese, VocabularyItem.reading).in_(targets))
                .where(VocabularyItem.audio_url.is_not(None), VocabularyItem.audio_url != "")
            )
        }
    return db.info[cache_key].get((target, item.reading)) or item.audio_url
