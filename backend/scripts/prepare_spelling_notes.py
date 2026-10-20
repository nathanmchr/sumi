"""Add the seven reviewed French spelling notes, without replacing existing content.

Preview: python -m scripts.prepare_spelling_notes
Apply:   python -m scripts.prepare_spelling_notes --apply --backup /absolute/backup.json
Undo:    python -m scripts.prepare_spelling_notes --restore /absolute/backup.json
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.content import VocabularyItem, VocabularyTranslation
from app.services.catalog_audio import catalog_entry

CATALOG_IDS = frozenset({
    "404379cf-1c98-5d44-bc90-b32f1cbc6eea",
    "6b899840-f7c7-572a-853d-e432a78339f0",
    "dbf1f16e-3200-5c35-8585-ec50f66379bb",
    "8fce087b-86d9-5a5a-93c6-6053a576b146",
    "4e3ab6b5-c9c1-5755-ab3a-93f76d026f77",
    "678fb344-01f2-5c24-bbaa-4e32b73e3b37",
    "8752c929-6393-5f51-af7d-f8d1e1fff6bb",
})


def _snapshot(row) -> dict:
    return {key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in row.items()}


def _translation(db: Session, word_id: str):
    table = VocabularyTranslation.__table__
    return db.execute(select(table).where(
        table.c.vocabulary_item_id == word_id, table.c.locale == "fr",
    ).with_for_update()).mappings().one()


def prepare(db: Session, backup_path: Path | None = None) -> list[dict]:
    """Fail closed on missing/ambiguous matches or existing different notes."""
    matches = {}
    for word in db.scalars(select(VocabularyItem)):
        source = catalog_entry(word)
        if source is None or source["ID"] not in CATALOG_IDS:
            continue
        identity = source["ID"]
        if identity in matches:
            raise ValueError(f"Ambiguous catalogue match: {identity}")
        matches[identity] = (word, source)
    if set(matches) != CATALOG_IDS:
        raise ValueError("Missing reviewed catalogue matches")

    changes = []
    for identity, (word, source) in matches.items():
        note = source.get("Notes", "").strip()
        if not note:
            raise ValueError(f"Missing reviewed note: {identity}")
        before = _snapshot(_translation(db, word.id))
        if before["notes"] == note:
            continue
        if before["notes"] not in (None, ""):
            raise ValueError(f"Existing note must be reviewed: {word.id}")
        changes.append({"catalog_id": identity, "japanese": word.japanese,
                        "before": before, "after": {**before, "notes": note}})

    if backup_path is not None and changes:
        # Save all original values before any update; never clobber a backup.
        with backup_path.open("x", encoding="utf-8") as handle:
            backup_path.chmod(0o600)
            json.dump({"kind": "spelling-notes-fr-v1", "created_at": datetime.now(timezone.utc).isoformat(),
                       "changes": changes}, handle, ensure_ascii=False, indent=2)
        _apply_changes(db, changes)
    return changes


def _apply_changes(db: Session, changes: list[dict], reverse: bool = False) -> None:
    table = VocabularyTranslation.__table__
    for change in changes:
        expected, desired = (change["after"], change["before"]) if reverse else (change["before"], change["after"])
        row = _translation(db, expected["vocabulary_item_id"])
        if _snapshot(row) != expected:
            raise ValueError(f"Translation edited since backup: {expected['vocabulary_item_id']}")
        db.execute(update(table).where(
            table.c.vocabulary_item_id == row["vocabulary_item_id"], table.c.locale == "fr",
        ).values(notes=desired["notes"], updated_at=row["updated_at"]))
        if _snapshot(_translation(db, row["vocabulary_item_id"])) != desired:
            raise ValueError("Unexpected translation mutation; rollback required")


def restore(db: Session, backup_path: Path) -> int:
    backup = json.loads(backup_path.read_text(encoding="utf-8"))
    if backup.get("kind") != "spelling-notes-fr-v1":
        raise ValueError("Not a spelling notes backup")
    changes = backup["changes"]
    if any(change["catalog_id"] not in CATALOG_IDS for change in changes):
        raise ValueError("Unexpected catalogue entry in backup")
    _apply_changes(db, changes, reverse=True)
    return len(changes)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--restore", type=Path)
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    if args.apply != bool(args.backup):
        parser.error("--apply and --backup must be supplied together")
    with SessionLocal.begin() as db:
        if args.restore:
            print(json.dumps({"restored": restore(db, args.restore)}))
        else:
            changes = prepare(db, args.backup)
            print(json.dumps({"mode": "apply" if args.apply else "preview", "count": len(changes),
                              "words": [change["japanese"] for change in changes]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
