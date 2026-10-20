"""Align historical vocabulary readings with reviewed audio data; preserve IDs and progress."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.models.content import KanjiItem, VocabularyItem
from app.services.catalog_audio import catalog_entry
from app.utils.romaji import romaji_search_key

FIELDS = ("reading", "romaji", "romaji_search", "furigana_segments")
ROOT = Path(__file__).resolve().parents[2]


def prepare(db, backup_path: Path | None = None):
    table = VocabularyItem.__table__
    statement = select(VocabularyItem)
    if backup_path is not None:
        statement = statement.with_for_update()
    words = list(db.scalars(statement))
    kanji_ids = dict(db.execute(select(KanjiItem.character, KanjiItem.id)).all())
    changes = []
    for word in words:
        row = catalog_entry(word)
        if row is None or word.reading == row["Kana"]:
            continue
        if word.japanese == (row["Kanji"] or row["Kana"]):
            segments = json.loads(row["Furigana"])
            for segment in segments:
                segment["kanji_ids"] = [kanji_ids[char] for char in segment["surface"] if char in kanji_ids]
        else:
            # Preserve lower-level kana display when its canonical spelling is kanji.
            segments = [{"surface": word.japanese, "kanji_ids": []}]
        after = {
            "reading": row["Kana"], "romaji": row["Romaji"],
            "romaji_search": romaji_search_key([row["Kana"], word.japanese], row["Romaji"]),
            "furigana_segments": segments,
        }
        changes.append({"id": word.id, "japanese": word.japanese, "catalog_id": row["ID"],
                        "before": {field: getattr(word, field) for field in FIELDS}, "after": after})
    if backup_path is not None and changes:
        # Exclusive creation: never overwrite a previous rollback record.
        with backup_path.open("x", encoding="utf-8") as handle:
            json.dump({"created_at": datetime.now(timezone.utc).isoformat(), "changes": changes}, handle, ensure_ascii=False, indent=2)
        backup_path.chmod(0o600)
        originals = {word.id: {column.name: getattr(word, column.name) for column in table.columns} for word in words}
        for change in changes:
            db.execute(update(table).where(table.c.id == change["id"]).values(
                **change["after"], updated_at=originals[change["id"]]["updated_at"],
            ))
            originals[change["id"]].update(change["after"])
        actual = {row["id"]: dict(row) for row in db.execute(select(table)).mappings()}
        if actual != originals:
            raise ValueError("Unexpected vocabulary mutation; rollback required")
    return changes


def restore(db, path: Path):
    table = VocabularyItem.__table__
    changes = json.loads(path.read_text(encoding="utf-8"))["changes"]
    for change in changes:
        row = db.execute(select(table).where(table.c.id == change["id"]).with_for_update()).mappings().one()
        if any(row[field] != change["after"][field] for field in FIELDS):
            raise ValueError(f"Vocabulary edited since backup: {change['id']}")
        db.execute(update(table).where(table.c.id == change["id"]).values(
            **change["before"], updated_at=row["updated_at"],
        ))
    return len(changes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--restore", type=Path)
    parser.add_argument("--backup", type=Path, default=ROOT / ".local" / "audio-jobs" / "readings-before-yomigana.json")
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.restore:
            count = restore(db, args.restore)
            db.commit()
            print(json.dumps({"restored": count}))
            return
        changes = prepare(db, args.backup if args.write else None)
        if args.write:
            db.commit()
        print(json.dumps({"changed": len(changes), "applied": args.write,
                          "backup": str(args.backup) if args.write else None,
                          "readings": [{"japanese": row["japanese"], "before": row["before"]["reading"],
                                        "after": row["after"]["reading"]} for row in changes]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
