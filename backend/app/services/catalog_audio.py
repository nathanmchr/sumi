"""Resolve consolidated audio for current or historical vocabulary, without DB writes."""

import csv
from functools import lru_cache
import hashlib
import json
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CATALOG_DIR = ROOT / "contenu csv" / "consolidated"
MANIFEST_PATH = ROOT / "audio" / "vocabulary-chirp3-yomigana" / "manifest.json"
OVERRIDES_PATH = Path(__file__).resolve().parents[1] / "data" / "vocabulary_audio_legacy_overrides.json"
logger = logging.getLogger(__name__)


def _stamp(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


def _key(japanese: str, reading: str, meaning: str) -> tuple[str, str, str]:
    return japanese.strip(), reading.strip(), meaning.strip().casefold()


@lru_cache(maxsize=1)
def _catalog(directory: Path, overrides_path: Path, stamps: tuple) -> tuple[dict, dict]:
    with (directory / "vocabulary.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))
    by_id = {row["ID"]: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError("Duplicate vocabulary catalog ID")
    candidates: dict[tuple, set[str]] = {}

    def add(key, identity):
        if identity not in by_id:
            raise ValueError("Audio source mapping references an unknown catalog ID")
        candidates.setdefault(key, set()).add(identity)

    for row in rows:
        add(_key(row["Kanji"] or row["Kana"], row["Kana"], row["English"]), row["ID"])
    with (directory / "_audit" / "source-map.csv").open(encoding="utf-8-sig", newline="") as handle:
        for source in csv.DictReader(handle, delimiter=";"):
            if source["Category"] != "vocabulary":
                continue
            row = json.loads(source["OriginalRow"])
            reading = row["Hiragana"].strip()
            add(_key(row.get("Kanji", "").strip() or reading, reading,
                     row.get("English") or row.get("French") or ""), source["CanonicalID"])
            # Retain the audited identity after a targeted reading correction,
            # even while the old display spelling/translation stays in the DB.
            add(_key(row.get("Kanji", "").strip() or reading, by_id[source["CanonicalID"]]["Kana"],
                     row.get("English") or row.get("French") or ""), source["CanonicalID"])
    for override in json.loads(overrides_path.read_text(encoding="utf-8")):
        target = by_id[override["catalog_id"]]
        if any(target[field] != value for field, value in override["expect_catalog"].items()):
            raise ValueError("Stale reviewed legacy audio override")
        add(_key(*override["legacy"]), override["catalog_id"])
        add(_key(override["legacy"][0], target["Kana"], override["legacy"][2]), override["catalog_id"])
    # An ambiguous sense is never resolved by choosing the first result.
    return by_id, {key: next(iter(ids)) for key, ids in candidates.items() if len(ids) == 1}


def catalog_entry(item) -> dict | None:
    paths = (CATALOG_DIR / "vocabulary.csv", CATALOG_DIR / "_audit" / "source-map.csv", OVERRIDES_PATH)
    try:
        by_id, by_word = _catalog(CATALOG_DIR, OVERRIDES_PATH, tuple(_stamp(path) for path in paths))
        key = _key(item.japanese, item.reading, item.translation)
        identity = by_word.get(key)
        # Even a stable ID must still agree with an audited lexical identity.
        stable_id = getattr(item, "catalog_id", None) or (item.id if getattr(item, "id", None) in by_id else None)
        if stable_id and identity != stable_id:
            return None
        return by_id.get(identity)
    except (OSError, ValueError, KeyError, TypeError):
        logger.warning("Consolidated audio catalog unavailable or invalid", exc_info=True)
        return None


@lru_cache(maxsize=1)
def _manifest(path: Path, stamp: tuple) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    result = {}
    for group in manifest.values():
        for record in group:
            identity = record["id"]
            if identity in result:
                raise ValueError("Duplicate ID in audio manifest")
            result[identity] = record
    return result


@lru_cache(maxsize=8192)
def _checksum_matches(path: Path, expected: str, stamp: tuple) -> bool:
    return stamp[1] > 44 and hashlib.sha256(path.read_bytes()).hexdigest() == expected


def generated_audio_url(row: dict, manifest: dict) -> str | None:
    record = manifest.get(row["ID"])
    if not record or any((
        record.get("japanese") != (row["Kanji"] or row["Kana"]),
        record.get("reading") != row["Kana"],
        record.get("yomigana", "") != row["Yomigana"],
        record.get("generation_version") != "chirp3-yomigana-v1",
    )):
        return None
    filename = record.get("audio_file", "")
    if not isinstance(filename, str) or not filename or Path(filename).name != filename or Path(filename).suffix not in {".wav", ".mp3"}:
        return None
    path = MANIFEST_PATH.parent / filename
    try:
        if path.is_symlink() or not _checksum_matches(path, record.get("audio_sha256", ""), _stamp(path)):
            return None
        # The same synthesis request can yield different bytes on a retry.
        # Version the URL by the verified content, not just the request filename.
        return f"/audio/{MANIFEST_PATH.parent.name}/{filename}?v={record['audio_sha256'][:16]}"
    except OSError:
        return None


def catalog_audio(item, db=None) -> tuple[bool, str | None]:
    row = catalog_entry(item)
    if row is None:
        return False, None
    return True, canonical_row_audio(row, db)


def canonical_row_audio(row: dict, db=None) -> str | None:
    """Resolve an already identified, reviewed catalog row (including lesson content)."""
    # One consistent manifest snapshot per API request/DB session. Atomic writer
    # replacement lets the next request discover newly completed files.
    key = "consolidated_audio_manifest"
    info = db.info if db is not None else {}
    if key not in info:
        try:
            info[key] = _manifest(MANIFEST_PATH, _stamp(MANIFEST_PATH))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            info[key] = {}
    audio = generated_audio_url(row, info[key])
    if audio:
        return audio
    # The reviewed catalog deliberately clears audio for some corrected readings.
    # Do not bring those known wrong files back through the historical DB record.
    return row.get("Audio") or None
