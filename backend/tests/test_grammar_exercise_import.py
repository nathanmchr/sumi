import unittest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
import app.models
from app.models.base import Base
from app.models.content import GrammarItem, JLPTLevel
from app.models.learning import GrammarExercise
from app.data.grammar_exercises import exercise_records
from app.services.grammar_exercise_import import import_grammar_exercises


class GrammarImportTests(unittest.TestCase):
    def test_bank_coverage_validation_and_idempotent_import(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        records = list(exercise_records())
        self.assertEqual(len(records), 25)
        with Session(engine) as db:
            for n in range(1, 6):
                level = f"N{n}"
                self.assertEqual(sum(r["level"] == level for r in records), 5)
                db.add(JLPTLevel(code=level, rank=n, label=level))
            for row in records:
                self.assertEqual(
                    row["completed_sentence"],
                    row["prompt"].replace("___", row["answer"]),
                )
                self.assertEqual(set(row["translations"]), {"fr", "en"})
                db.add(
                    GrammarItem(
                        slug=row["code"],
                        title=row["key"],
                        structure=row["key"],
                        explanation="test",
                        nuances="",
                        jlpt_level_code=row["level"],
                    )
                )
            db.commit()
            self.assertEqual(import_grammar_exercises(db), 25)
            db.commit()
            ids = set(db.scalars(select(GrammarExercise.id)))
            self.assertEqual(import_grammar_exercises(db), 25)
            db.commit()
            self.assertEqual(set(db.scalars(select(GrammarExercise.id))), ids)
        engine.dispose()
