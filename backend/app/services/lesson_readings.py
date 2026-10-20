"""Presentation-only reading aids; never rewrite versioned lesson content."""

import csv
import json
from functools import lru_cache
from pathlib import Path

from app.utils.furigana import validate_furigana

CATALOG = Path(__file__).resolve().parents[3] / "contenu csv/consolidated/vocabulary.csv"


@lru_cache(maxsize=1)
def _rows(path: Path, stamp: tuple[int, int]) -> dict[str, dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["ID"]: row for row in csv.DictReader(handle, delimiter=";")}


def reading_aids(word: dict) -> dict:
    surface = word.get("japanese")
    if not surface:
        return {}
    aids = {key: word[key] for key in ("segments", "romaji") if word.get(key)}
    try:
        stat = CATALOG.stat()
        row = _rows(CATALOG, (stat.st_mtime_ns, stat.st_size)).get(word.get("source_id"))
        if not row:
            return aids
        # Only enrich the spelling actually taught, not another catalog variant.
        if surface == (row["Kanji"] or row["Kana"]):
            aids["segments"] = validate_furigana(surface, row["Kana"], json.loads(row["Furigana"]))
            aids["romaji"] = row["Romaji"]
        elif surface == row["Kana"].split("/")[0].strip():
            aids = {"segments": [{"surface": surface}], "romaji": row["Romaji"].split("/")[0].strip()}
    except (OSError, ValueError, KeyError, TypeError):
        # Existing authored aids remain usable if the optional catalog is absent.
        pass
    return aids
