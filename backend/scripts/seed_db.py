from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from app.utils.enums import ContentType


ROOT_DIR = Path(__file__).resolve().parents[2]
KANJI_PATTERN = re.compile(r"[\u3400-\u9fff々]")
AUDIO_MANIFEST_PATH = ROOT_DIR / "audio" / "vocabulary" / "manifest.json"


def _load_vocabulary_audio_urls() -> dict[tuple[str, str], str]:
    if not AUDIO_MANIFEST_PATH.exists():
        return {}
    manifest = json.loads(AUDIO_MANIFEST_PATH.read_text(encoding="utf-8"))
    return {
        (entry["japanese"], entry["reading"]): f"/audio/vocabulary/{entry['audio_file']}"
        for entries in manifest.values()
        for entry in entries
        if entry.get("japanese") and entry.get("reading") and entry.get("audio_file")
    }


def _stable_slug(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"


def _translation(row: dict[str, str], locale: str = "en") -> str:
    column = "French" if locale == "fr" else "English"
    return (row.get(column) or "").strip()


def _split_readings(value: str) -> tuple[str, str]:
    readings = [part.strip() for part in re.split(r"[・,;/]", value) if part.strip()]
    onyomi = [reading for reading in readings if any("ァ" <= char <= "ヶ" for char in reading)]
    kunyomi = [reading for reading in readings if reading not in onyomi]
    return ",".join(onyomi), ",".join(kunyomi)


def _transform_row(item_type: ContentType, level: str, audio_urls: dict[tuple[str, str], str] | None = None):
    vocabulary_audio_urls = audio_urls or {}

    def transform(row: dict[str, str], line: int) -> dict[str, str]:
        if item_type == ContentType.vocabulary:
            written_form = (row.get("Kanji") or "").strip()
            reading = (row.get("Hiragana") or "").strip()
            japanese = written_form or reading
            if not japanese or not (_translation(row, "en") or _translation(row, "fr")):
                raise ValueError("missing vocabulary term, reading, or translation")
            return {
                "slug": _stable_slug("vocab", written_form, reading),
                "japanese": japanese,
                "reading": reading,
                "furigana_json": row.get("Furigana", ""),
                "romaji": row.get("Romaji", ""),
                "translation": _translation(row, "en") or _translation(row, "fr"),
                "translation_en": _translation(row, "en"),
                "translation_fr": _translation(row, "fr"),
                "part_of_speech": "other",
                "jlpt_level": level,
                "kanji_links": ",".join(dict.fromkeys(KANJI_PATTERN.findall(japanese))),
                "audio_url": vocabulary_audio_urls.get((japanese, reading), ""),
            }
        if item_type == ContentType.kanji:
            character = (row.get("Kanji") or "").strip()
            pronunciation = (row.get("pronunciation") or row.get("Pronounciation") or "").strip()
            if not character or not pronunciation or not _translation(row, "en"):
                raise ValueError("missing kanji, pronunciation, or translation")
            onyomi, kunyomi = _split_readings(pronunciation)
            return {
                "character": character,
                "slug": character,
                "meanings": ",".join(part.strip() for part in _translation(row, "en").split(";") if part.strip()),
                "meanings_en": ",".join(part.strip() for part in _translation(row, "en").split(";") if part.strip()),
                "meanings_fr": ",".join(part.strip() for part in _translation(row, "fr").split(";") if part.strip()),
                "onyomi": onyomi,
                "kunyomi": kunyomi,
                "jlpt_level": level,
            }

        title = (row.get("Japanese") or row.get("Grammar Point") or "").strip()
        source_structure = (row.get("Romaji") or row.get("Hiragana") or "").strip()
        structure = source_structure or title
        if not title or not _translation(row, "en"):
            raise ValueError("missing grammar point, reading, or explanation")
        return {
            "slug": _stable_slug("grammar", title, source_structure),
            "title": title,
            "jlpt_level": level,
            "explanation": _translation(row, "en"),
            "explanation_en": _translation(row, "en"),
            "explanation_fr": _translation(row, "fr"),
            "structure": structure,
            "nuances": "",
        }

    return transform


def main() -> None:
    # Compatibility entry point. Historical transforms remain available to audit
    # tools, but seeding must never reintroduce the per-level CSV duplicates.
    from scripts.sync_catalog import main as sync_main
    sync_main()


if __name__ == "__main__":
    main()
