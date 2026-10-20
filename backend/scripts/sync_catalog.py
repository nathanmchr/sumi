"""Synchronize the site's content from the consolidated catalogue.

python -m scripts.sync_catalog                           # simulate, then roll back
python -m scripts.sync_catalog --apply --backup PATH     # private, exclusive backup
python -m scripts.sync_catalog --restore PATH            # refuses subsequent edits
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from sqlalchemy import DateTime, delete, select, text

from app.core.database import SessionLocal
from app.models import Base
from app.services.catalog_audio import CATALOG_DIR, MANIFEST_PATH
from app.services.consolidated_catalog import apply_plan, build_plan
from app.services.content_identity import MODELS

MUTABLE = {
    "vocabulary_items", "vocabulary_translations", "kanji_items", "kanji_translations",
    "grammar_items", "grammar_translations", "vocabulary_kanji_links", "content_aliases",
    "example_sentences", "example_sentence_translations", "grammar_exercises",
    "learning_states", "review_history", "study_questions", "study_sessions",
}
REFERENCE_COLUMNS = {
    "learning_states": "content_id", "review_history": "content_id", "study_questions": "content_id",
    "example_sentences": None, "grammar_exercises": "grammar_item_id",
}


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()).hexdigest()


def snapshot(db, names: set[str]) -> dict:
    return {table.name: [dict(row) for row in db.execute(select(table).order_by(*table.primary_key)).mappings()]
            for table in Base.metadata.sorted_tables if table.name in names}


def lock_tables(db):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SET LOCAL lock_timeout = '5s'"))
        db.execute(text("LOCK TABLE " + ", ".join(sorted(MUTABLE)) + " IN SHARE ROW EXCLUSIVE MODE"))


def source_hashes():
    paths = [CATALOG_DIR / f"{kind}.csv" for kind in MODELS]
    paths += [CATALOG_DIR / "_audit/source-map.csv", MANIFEST_PATH]
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def verify(db, plan, before, protected):
    after = snapshot(db, MUTABLE)
    for kind, model in MODELS.items():
        rows = list(db.scalars(select(model).order_by(model.source_order)))
        expected = plan.catalog.rows[kind]
        if [r.catalog_id for r in rows] != [r["ID"] for r in expected]:
            raise ValueError(f"Catalogue identities/order mismatch: {kind}")
        if [r.jlpt_level_code for r in rows] != [r["Level"] for r in expected]:
            raise ValueError(f"Catalogue levels mismatch: {kind}")
    for name, column in REFERENCE_COLUMNS.items():
        expected = []
        for old in before[name]:
            row = dict(old)
            if name == "example_sentences":
                for kind in ("vocabulary", "grammar"):
                    field = f"{kind}_item_id"
                    row[field] = plan.remap[kind].get(row[field], row[field])
            else:
                kind = "grammar" if name == "grammar_exercises" else getattr(row["content_type"], "value", row["content_type"])
                row[column] = plan.remap[kind].get(row[column], row[column])
            expected.append(row)
        if digest(expected) != digest(after[name]):
            raise ValueError(f"Protected learning/pedagogical values changed: {name}")
    sessions = []
    for old in before["study_sessions"]:
        row = dict(old)
        scope = row["snapshot"] or {}
        categories = scope.get("categories", [])
        if len(categories) == 1 and (target := plan.remap.get(categories[0], {}).get(scope.get("content_id"))):
            row["snapshot"] = {**scope, "content_id": target}
        sessions.append(row)
    if digest(sessions) != digest(after["study_sessions"]):
        raise ValueError("Session data changed beyond identity remapping")
    if digest(before["example_sentence_translations"]) != digest(after["example_sentence_translations"]):
        raise ValueError("Example translations changed")
    if digest(snapshot(db, set(protected))) != digest(protected):
        raise ValueError("Lessons or lesson progress changed")
    identities = {kind: {r["id"] for r in after[model.__tablename__]} for kind, model in MODELS.items()}
    for name in ("learning_states", "review_history", "study_questions"):
        for row in after[name]:
            if row["content_id"] not in identities[getattr(row["content_type"], "value", row["content_type"])]:
                raise ValueError(f"Orphan learning reference: {name}")
    for alias in after["content_aliases"]:
        if alias["content_id"] not in identities[alias["content_type"]]:
            raise ValueError("Orphan content alias")
    aliases = {(a["content_type"], a["alias"]): a["content_id"] for a in after["content_aliases"]}
    for kind, model in MODELS.items():
        for item in before[model.__tablename__]:
            target = plan.remap[kind].get(item["id"], item["id"])
            if target not in identities[kind]:
                raise ValueError("Lost historical content identity")
            if item["id"] != target and any(aliases.get((kind, key)) != target for key in (item["id"], item["slug"])):
                raise ValueError("Lost historical ID/slug alias")
    return after


def synchronize(db, backup: Path | None = None):
    lock_tables(db)
    sources = source_hashes()
    plan = build_plan(db)
    before = snapshot(db, MUTABLE)
    protected = snapshot(db, {"lessons", "lesson_progress"})
    document = {"kind": "consolidated-site-v1", "created_at": datetime.now(timezone.utc).isoformat(),
                "sources": sources, "before": before, "remap": plan.remap, "summary": plan.summary}
    if backup:
        with backup.open("x", encoding="utf-8") as handle:
            backup.chmod(0o600)
            json.dump(document, handle, ensure_ascii=False, default=str)
    apply_plan(db, plan)
    after = verify(db, plan, before, protected)
    if source_hashes() != sources:
        raise ValueError("Catalogue or audio manifest changed during synchronization")
    document["after_sha256"] = digest(after)
    document["changed"] = digest(before) != digest(after)
    if backup:
        with backup.open("w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, default=str)
            handle.flush()
            import os
            os.fsync(handle.fileno())
    return {**plan.summary, "changed": document["changed"], "protected_values": "verified"}


def restore(db, path: Path):
    lock_tables(db)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("kind") != "consolidated-site-v1" or set(data.get("before", {})) != MUTABLE:
        raise ValueError("Invalid catalogue backup")
    if digest(snapshot(db, MUTABLE)) != data.get("after_sha256"):
        raise ValueError("Data changed since migration; restore refused to protect later progress")
    tables = [t for t in Base.metadata.sorted_tables if t.name in MUTABLE]
    for table in reversed(tables):
        db.execute(delete(table))
    for table in tables:
        rows = data["before"][table.name]
        for row in rows:
            for column in table.columns:
                if isinstance(column.type, DateTime) and row[column.name] is not None:
                    row[column.name] = datetime.fromisoformat(row[column.name])
        if rows:
            db.execute(table.insert(), rows)
    db.expire_all()
    if digest(snapshot(db, MUTABLE)) != digest(data["before"]):
        raise ValueError("Restored snapshot does not match backup")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--restore", type=Path)
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    if args.apply and not args.backup:
        parser.error("--apply requires an unused --backup path")
    if args.backup and not args.apply:
        parser.error("--backup is only used with --apply")
    with SessionLocal() as db:
        try:
            if args.restore:
                restore(db, args.restore)
                db.commit()
                print("Restored; subsequent progress guard passed")
            else:
                result = synchronize(db, args.backup)
                if args.apply:
                    db.commit()
                else:
                    db.rollback()
                print(json.dumps({"mode": "applied" if args.apply else "simulation rolled back", **result}, indent=2))
        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    main()
