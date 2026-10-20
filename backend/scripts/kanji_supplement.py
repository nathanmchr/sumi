"""Prepare and append the reviewed kanji supplement, without replacing existing rows.

Run from backend: python -m scripts.kanji_supplement --help
KANJIDIC2-derived data and editorial translations: CC BY-SA 4.0.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import unicodedata
from uuid import NAMESPACE_URL, uuid5
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "backend/app/data"
PACKAGE = DATA / "kanji_supplement.json"
CATALOG = ROOT / "contenu csv/consolidated"
AUDIT = ROOT / "output/kanji-coverage-2026-09-08/audit.json"
LEVELS = ("N5", "N4", "N3", "N2", "N1")
EXPECTED = {"N5": 7, "N4": 5, "N3": 51, "N2": 88, "N1": 172}
FIELDS = ["Level", "ID", "Kanji", "Pronunciation", "English", "French"]
SOURCE = "https://www.edrdg.org/kanjidic/kanjidic2.xml.gz"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def json_text(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def validate_entries(entries: list[dict]) -> None:
    if Counter(row["level"] for row in entries) != EXPECTED:
        raise ValueError("Supplement must retain the reviewed 323-entry distribution")
    if len({row["character"] for row in entries}) != len(entries):
        raise ValueError("Duplicate characters")
    for row in entries:
        char = row["character"]
        if len(char) != 1 or not unicodedata.name(char, "").startswith("CJK UNIFIED IDEOGRAPH"):
            raise ValueError(f"Invalid kanji: {char}")
        if row["id"] != str(uuid5(NAMESPACE_URL, f"mirai-path:kanji-supplement:{char}")):
            raise ValueError(f"Unstable identifier: {char}")
        for field in ("english", "french"):
            if not row[field] or not all(isinstance(value, str) and value.strip() for value in row[field]):
                raise ValueError(f"Missing {field}: {char}")
        if not row["onyomi"] and not row["kunyomi"]:
            raise ValueError(f"Missing Japanese readings: {char}")


def validate_levels(entries: list[dict], vocabulary: Path) -> None:
    targets = {row["character"]: [] for row in entries}
    with vocabulary.open(encoding="utf-8-sig", newline="") as handle:
        for word in csv.DictReader(handle, delimiter=";"):
            for char in set(word["Kanji"]) & targets.keys():
                level = word["KanjiLevel"]
                if level not in LEVELS:
                    raise ValueError(f"Missing KanjiLevel for {word['ID']}")
                targets[char].append(level)
    for row in entries:
        levels = targets[row["character"]]
        if not levels or min(levels, key=LEVELS.index) != row["level"]:
            raise ValueError(f"KanjiLevel changed for {row['character']}; review before importing")


def prepare(archive: Path) -> dict:
    raw = archive.read_bytes()
    xml = gzip.decompress(raw)
    if b"<!ENTITY" in xml.upper():
        raise ValueError("Entity declarations are not accepted")
    root = ET.fromstring(xml)
    characters = {entry.findtext("literal"): entry for entry in root.findall("character")}
    targets = read_json(AUDIT)["consolidated"]["missing"]
    french = read_json(DATA / "kanji_supplement_french.json")
    overrides = read_json(DATA / "kanji_supplement_overrides.json")
    if set(french) != {row["kanji"] for row in targets}:
        raise ValueError("French editorial map must cover exactly the reviewed targets")
    entries = []
    for target in targets:
        char = target["kanji"]
        source = characters[char]
        groups = source.findall("reading_meaning/rmgroup")
        readings = {kind: list(dict.fromkeys(
            value.text for group in groups for value in group.findall(f"reading[@r_type='{kind}']")
            if value.text
        )) for kind in ("ja_on", "ja_kun")}
        meanings = {locale: list(dict.fromkeys(
            value.text for group in groups for value in group.findall("meaning")
            if value.get("m_lang", "en") == locale and value.text
        )) for locale in ("en", "fr")}
        if not meanings["en"]:
            raise ValueError(f"No English source for {char}")
        radical = source.findtext("radical/rad_value[@rad_type='classical']")
        override = overrides.get(char, {})
        entries.append({
            "id": str(uuid5(NAMESPACE_URL, f"mirai-path:kanji-supplement:{char}")),
            "character": char, "level": target["level"],
            "onyomi": readings["ja_on"], "kunyomi": readings["ja_kun"],
            "english": override.get("english", meanings["en"]),
            "french": [value.strip() for value in french[char].split(";") if value.strip()],
            "classical_radical": int(radical) if radical else None,
            "stroke_count": int(source.findtext("misc/stroke_count")),
            "source_meanings": meanings,
            "french_method": "editorial translation/adaptation of sourced senses; not an independently certified dictionary translation",
            "cross_checks": override,
        })
    validate_entries(entries)
    validate_levels(entries, CATALOG / "vocabulary.csv")
    return {
        "source": SOURCE,
        "source_documentation": "https://www.edrdg.org/wiki/KANJIDIC_Project.html",
        "copyright": "Jim Breen and the Electronic Dictionary Research and Development Group",
        "license": "https://creativecommons.org/licenses/by-sa/4.0/",
        "source_version": root.findtext("header/database_version"),
        "source_date": root.findtext("header/date_of_creation"),
        "source_archive_sha256": hashlib.sha256(raw).hexdigest(),
        "source_xml_sha256": hashlib.sha256(xml).hexdigest(),
        "level_basis": "Minimum difficulty KanjiLevel of consolidated vocabulary; pedagogical, not official JLPT levels",
        "entries": entries,
    }


def load_entries() -> list[dict]:
    entries = read_json(PACKAGE)["entries"]
    validate_entries(entries)
    return entries


def catalog_row(entry: dict) -> dict[str, str]:
    return dict(zip(FIELDS, (
        entry["level"], entry["id"], entry["character"],
        "・".join(entry["onyomi"] + entry["kunyomi"]),
        "; ".join(entry["english"]), " ; ".join(entry["french"]),
    )))


def append_catalog(content: str, entries: list[dict]) -> tuple[str, int]:
    reader = csv.DictReader(io.StringIO(content), delimiter=";")
    if reader.fieldnames != FIELDS:
        raise ValueError("Unexpected consolidated kanji schema")
    rows = list(reader)
    by_char = {row["Kanji"]: row for row in rows}
    ids = {row["ID"] for row in rows}
    if len(by_char) != len(rows) or len(ids) != len(rows):
        raise ValueError("Duplicate existing catalogue entries")
    addition = io.StringIO()
    writer = csv.DictWriter(addition, fieldnames=FIELDS, delimiter=";", lineterminator="\n")
    added = 0
    for entry in entries:
        row = catalog_row(entry)
        if row["Kanji"] in by_char:
            if by_char[row["Kanji"]] != row:
                raise ValueError(f"Refusing to overwrite existing {row['Kanji']}")
            continue
        if row["ID"] in ids:
            raise ValueError("Identifier collision")
        writer.writerow(row)
        by_char[row["Kanji"]] = row
        ids.add(row["ID"])
        added += 1
    if not added:
        return content, 0
    # Keep all original bytes/row positions; provenance references remain valid.
    return content + ("" if content.endswith("\n") else "\n") + addition.getvalue(), added


def integrate_database(db, entries: list[dict]) -> dict[str, int]:
    """Stage insert-only changes; caller owns the transaction and commit decision."""
    from sqlalchemy import select
    from app.models.content import KanjiItem, KanjiTranslation, VocabularyItem, VocabularyKanjiLink
    from app.utils.romaji import romaji_search_key

    counts = {"kanji": 0, "translations": 0, "links": 0}
    existing = {item.character: item for item in db.scalars(select(KanjiItem))}
    if any(item.catalog_id for item in existing.values()):
        raise ValueError("Le site utilise le catalogue consolidé ; mettez à jour kanji.csv puis utilisez scripts.sync_catalog.")
    existing_ids = {item.id for item in existing.values()}
    translations = {(item.kanji_item_id, item.locale): item for item in db.scalars(select(KanjiTranslation))}
    for row in entries:
        values = {
            "id": row["id"], "character": row["character"], "slug": row["character"],
            "meanings": row["english"], "onyomi": row["onyomi"], "kunyomi": row["kunyomi"],
            "jlpt_level_code": row["level"],
        }
        item = existing.get(row["character"])
        if item is not None:
            if any(getattr(item, field) != value for field, value in values.items()):
                raise ValueError(f"Existing kanji differs: {row['character']}; nothing committed")
        else:
            if row["id"] in existing_ids:
                raise ValueError("Kanji identifier collision")
            radical = row["classical_radical"]
            db.add(KanjiItem(**values, radicals=[unicodedata.normalize("NFKC", chr(0x2F00 + radical - 1))] if radical else [],
                             romaji_search=romaji_search_key([*row["onyomi"], *row["kunyomi"]])))
            counts["kanji"] += 1
        for locale, field in (("en", "english"), ("fr", "french")):
            current = translations.get((row["id"], locale))
            if current is not None:
                if current.meanings != row[field]:
                    raise ValueError(f"Existing translation differs: {row['character']}/{locale}")
            else:
                db.add(KanjiTranslation(kanji_item_id=row["id"], locale=locale, meanings=row[field]))
                counts["translations"] += 1
    db.flush()
    existing_links = set(db.execute(select(VocabularyKanjiLink.vocabulary_item_id, VocabularyKanjiLink.kanji_item_id)).tuples())
    ids = {row["character"]: row["id"] for row in entries}
    for word_id, japanese in db.execute(select(VocabularyItem.id, VocabularyItem.japanese)):
        for char in set(japanese) & ids.keys():
            pair = (word_id, ids[char])
            if pair not in existing_links:
                db.add(VocabularyKanjiLink(vocabulary_item_id=word_id, kanji_item_id=ids[char], kanji_position=japanese.index(char) + 1))
                existing_links.add(pair)
                counts["links"] += 1
    db.flush()
    return counts


def stroke_assets(archive: Path, output: Path, entries: list[dict]) -> dict[str, bytes]:
    from zipfile import ZipFile
    from scripts.import_kanjivg_n5 import REVISION, SOURCE_ROOT, parse_svg

    manifest = read_json(output / "manifest.json")
    if manifest["revision"] != REVISION:
        raise ValueError("Review KanjiVG revision before mixing sources")
    assets = {}
    with ZipFile(archive) as source:
        for entry in entries:
            char, level = entry["character"], entry["level"]
            code = f"{ord(char):05x}"
            raw = source.read(f"{SOURCE_ROOT}/kanji/{code}.svg")
            data = parse_svg(raw, char)
            filename = f"{level.lower()}/{code}.json"
            assets[f"source/{code}.svg"] = raw
            assets[filename] = (json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
            info = {"file": filename, "strokes": len(data["strokes"]), "source_sha256": data["source_sha256"]}
            for mapping in (manifest["levels"].setdefault(level, {}), manifest["characters"]):
                if char in mapping and mapping[char] != info:
                    raise ValueError(f"Refusing to replace existing stroke manifest entry: {char}")
                mapping[char] = info
    for name, content in assets.items():
        path = output / name
        if path.exists() and path.read_bytes() != content:
            raise ValueError(f"Refusing to replace existing asset: {name}")
    assets["manifest.json"] = json_text(manifest).encode()
    return assets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "catalog", "database", "strokes"))
    parser.add_argument("--archive", type=Path, help="Official KANJIDIC2 gzip for prepare; pinned KanjiVG ZIP for strokes")
    parser.add_argument("--write", action="store_true", help="Commit validated changes; default is dry run")
    args = parser.parse_args()
    if args.action in ("prepare", "strokes") and not args.archive:
        parser.error("--archive is required")
    if args.action == "prepare":
        package = prepare(args.archive)
        if args.write:
            PACKAGE.write_text(json_text(package), encoding="utf-8")
        print(json.dumps({"entries": len(package["entries"]), "source_date": package["source_date"], "written": args.write}))
        return
    entries = load_entries()
    validate_levels(entries, CATALOG / "vocabulary.csv")
    if args.action == "catalog":
        path = CATALOG / "kanji.csv"
        content, added = append_catalog(path.read_bytes().decode("utf-8"), entries)
        if args.write and added:
            path.write_bytes(content.encode("utf-8"))
        print(json.dumps({"added": added, "written": args.write}))
    elif args.action == "database":
        from app.core.database import SessionLocal
        with SessionLocal() as db:
            counts = integrate_database(db, entries)
            if args.write:
                db.commit()
            else:
                db.rollback()
            print(json.dumps({**counts, "committed": args.write}))
    else:
        output = ROOT / "frontend/public/kanji-strokes"
        assets = stroke_assets(args.archive, output, entries)
        changed = 0
        for name, content in assets.items():
            path = output / name
            if path.exists() and path.read_bytes() == content:
                continue
            changed += 1
            if args.write:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        print(json.dumps({"assets_changed": changed, "written": args.write}))


if __name__ == "__main__":
    main()
