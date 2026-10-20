"""Populate missing display romaji from exact CSV matches, without reimporting words."""
import argparse
import json
from pathlib import Path

from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.models.content import VocabularyItem
from scripts.prepare_content_search import source_romaji


def prepare(db, directory: Path, *, write: bool = False) -> dict:
    source = source_romaji(directory)
    table = VocabularyItem.__table__
    statement = select(table)
    if write:
        statement = statement.with_for_update()
    rows = [dict(row) for row in db.execute(statement).mappings()]
    summary = {"matched": 0, "missing": 0, "changed": 0, "preserved": 0}
    for row in rows:
        value = source.get((row["japanese"], row["reading"]))
        if not value:
            summary["missing"] += 1
            continue
        summary["matched"] += 1
        if row["romaji"]:
            summary["preserved"] += 1
            continue
        summary["changed"] += 1
        if write:
            db.execute(update(table).where(table.c.id == row["id"]).values(
                romaji=value, updated_at=row["updated_at"],
            ))
    if write:
        originals = {row["id"]: row for row in rows}
        for row in db.execute(select(table)).mappings():
            if any(value != originals[row["id"]][key] for key, value in row.items() if key != "romaji"):
                raise ValueError("Unexpected vocabulary change; transaction must be rolled back")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content-dir", type=Path, default=Path(__file__).resolve().parents[2] / "contenu csv")
    parser.add_argument("--write", action="store_true", help="Apply missing values; default is a dry run")
    args = parser.parse_args()
    if not args.content_dir.is_dir() or not list(args.content_dir.glob("* Vocab.csv")):
        parser.error("Content directory must contain * Vocab.csv files")
    with SessionLocal() as db:
        result = prepare(db, args.content_dir, write=args.write)
        if args.write:
            db.commit()
        print(json.dumps(result))


if __name__ == "__main__":
    main()
