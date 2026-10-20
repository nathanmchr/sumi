"""Idempotent, targeted exercise import; never reseeds content or learning states."""

from sqlalchemy import select
from sqlalchemy.orm import Session
import json
from pathlib import Path
from app.data.grammar_exercises import exercise_records
from app.models.content import GrammarItem
from app.models.learning import GrammarExercise


def import_grammar_exercises(db: Session) -> int:
    items = list(db.scalars(select(GrammarItem)))
    catalogue_mode = any(item.catalog_id for item in items)
    catalogue_ids = json.loads((Path(__file__).resolve().parents[1] / "data/grammar_exercise_catalog.json").read_text()) if catalogue_mode else {}
    count = 0
    for source in exercise_records():
        row = dict(source)
        level, key = row.pop("level"), row.pop("key")
        matches = [i for i in items if i.catalog_id and i.catalog_id == catalogue_ids.get(row["code"])] if catalogue_mode else [
            i
            for i in items
            if i.jlpt_level_code == level and key in (i.structure, i.title)
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Expected exactly one grammar point for {level} {key}, found {len(matches)}"
            )
        if (
            len(row["distractors"]) != 3
            or len(set([row["answer"], *row["distractors"]])) != 4
            or row["prompt"].count("___") != 1
        ):
            raise ValueError(f"Invalid exercise {row['code']}")
        item = db.scalar(
            select(GrammarExercise).where(GrammarExercise.code == row["code"])
        )
        if item is None:
            item = GrammarExercise(grammar_item_id=matches[0].id, **row)
            db.add(item)
        else:
            if item.grammar_item_id != matches[0].id:
                raise ValueError(f"Changed grammar mapping: {row['code']}")
            for field, value in row.items():
                setattr(item, field, value)
        count += 1
    db.flush()
    return count


if __name__ == "__main__":
    from app.core.database import SessionLocal

    with SessionLocal() as db:
        count = import_grammar_exercises(db)
        db.commit()
        print(f"Imported {count} bilingual application exercises.")
