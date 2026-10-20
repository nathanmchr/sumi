import copy
import unittest

from sqlalchemy import select

from app.models.lesson import Lesson, LessonProgress
from app.services.lesson_recap import build_recap
from app.services.theme_recaps import publish_theme_recaps
import test_lesson_recap as fixtures


class ThemeRecapTests(unittest.TestCase):
    make_engine = fixtures.RecapTests.make_engine
    setUp = fixtures.RecapTests.setUp
    setUpClass = classmethod(fixtures.RecapTests.setUpClass.__func__)
    install = fixtures.RecapTests.install
    complete = fixtures.RecapTests.complete
    publish = fixtures.RecapTests.publish

    def two_themes(self):
        self.install()
        with self.Factory.begin() as db:
            last = db.get(Lesson, "lesson-2")
            last.content = {**last.content, "unit_id": "next", "unit_title": {"fr": "Suite", "en": "Next"}}

    def test_exactly_one_final_lesson_per_theme_and_no_inline_test(self):
        self.two_themes()
        report = self.publish()
        self.assertEqual(report["created"], 2)
        rows = self.client.get("/lessons").json()
        self.assertEqual([r["id"] for r in rows], ["lesson-0", "lesson-1", "n5-unit-recap", "lesson-2", "n5-next-recap"])
        self.assertEqual([r["position"] for r in rows], [1, 2, 3, 4, 5])
        self.assertEqual(sum(r["is_recap"] for r in rows), 2)
        for row in rows:
            if row["is_recap"]:
                self.assertTrue(row["locked"])
                self.assertEqual(row["vocabulary_count"] + row["grammar_count"] + row["kanji_count"], 0)
            else:
                state = self.client.get(f"/lessons/{row['id']}").json()
                self.assertEqual(state["recap_total"], 0)
                self.assertEqual(state["lesson"]["total_steps"], 6)
        with self.Factory.begin() as db:
            again = publish_theme_recaps(db)
        self.assertEqual(again, dict(created=0, reordered=0, normalized_progress=0))

    def test_unlock_and_next_lesson_navigation(self):
        self.two_themes()
        self.publish()
        url = "/lessons/n5-unit-recap"
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url + "/progress", json=dict(action="continue", step_id="recap-intro", revision=0)).status_code, 403)
        with self.Factory() as db:
            self.assertIsNone(db.get(LessonProgress, (self.user.id, "n5-unit-recap")))
        self.complete(0)
        # Finishing a future lesson must not make it part of this earlier theme's test.
        self.complete(2)
        self.assertEqual(self.client.get(url).status_code, 403)
        with self.Factory.begin() as db:
            db.add(LessonProgress(user_id=self.user.id, lesson_id="lesson-1", version="v1", cursor=5,
                revision=1, step_order=[s["id"] for s in self.course[1]["content"]["steps"]], answers={}))
        finish = self.client.post("/lessons/lesson-1/progress", json=dict(action="continue", step_id="end", revision=1)).json()
        self.assertTrue(finish["lesson"]["completed"])
        self.assertIsNone(finish["step"])
        self.assertEqual(finish["next_lesson_id"], "n5-unit-recap")
        recap = self.client.get(url).json()
        self.assertEqual(recap["recap_total"], 6)
        self.assertEqual(recap["next_lesson_id"], "lesson-2")
        rows = self.client.get("/lessons").json()
        current = next(r for r in rows if r["id"] == "n5-unit-recap")
        self.assertFalse(current["locked"])
        self.assertTrue(current["recommended"])
        with self.Factory() as db:
            questions = build_recap(db, db.get(Lesson, "n5-unit-recap"), self.user.id)
        self.assertEqual({q["source_lesson_id"] for q in questions[1:]}, {"lesson-0", "lesson-1"})

    def test_inline_history_is_preserved_but_removed_from_learning_flow(self):
        self.two_themes()
        base = self.course[0]["content"]["steps"]
        with self.Factory.begin() as db:
            snapshot = build_recap(db, db.get(Lesson, "lesson-0"), self.user.id)
            answers = {"choice": {"correct": True}, snapshot[1]["id"]: {"correct": False}}
            db.add(LessonProgress(user_id=self.user.id, lesson_id="lesson-0", version="v1", cursor=len(base)+1,
                revision=8, step_order=[s["id"] for s in base], recap_steps=copy.deepcopy(snapshot), answers=copy.deepcopy(answers)))
            db.add(LessonProgress(user_id=self.other.id, lesson_id="lesson-0", version="v1", cursor=2,
                revision=3, step_order=[s["id"] for s in base], recap_steps=copy.deepcopy(snapshot), answers={}))
        report = self.publish()
        self.assertEqual(report["normalized_progress"], 1)
        with self.Factory() as db:
            old = db.get(LessonProgress, (self.user.id, "lesson-0"))
            self.assertEqual(old.cursor, len(base))
            self.assertIsNotNone(old.completed_at)
            self.assertEqual(old.revision, 9)
            self.assertEqual(old.answers, answers)
            self.assertEqual(old.recap_steps, snapshot)
            self.assertEqual(old.version, "v1")
            unfinished = db.get(LessonProgress, (self.other.id, "lesson-0"))
            self.assertEqual((unfinished.cursor, unfinished.revision), (2, 3))
            self.assertIsNone(unfinished.completed_at)
        state = self.client.get("/lessons/lesson-0").json()
        self.assertTrue(state["lesson"]["completed"])
        self.assertEqual((state["correct"], state["answered"], state["recap_total"]), (1, 1, 0))
        self.assertIsNone(state["step"])
        with self.Factory.begin() as db:
            self.assertEqual(publish_theme_recaps(db)["normalized_progress"], 0)
        # Reimporting unchanged base content keeps final tests and their ordering.
        with self.Factory.begin() as db:
            from test_lessons import import_course
            self.assertEqual(import_course(db, self.course[:2])["unchanged"], 2)
            self.assertEqual([l.id for l in db.scalars(select(Lesson).order_by(Lesson.position))],
                ["lesson-0", "lesson-1", "n5-unit-recap", "lesson-2", "n5-next-recap"])
