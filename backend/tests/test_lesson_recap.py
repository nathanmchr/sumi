import copy
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import unittest

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

from app.models.lesson import Lesson, LessonProgress
from app.services.lesson_recap import build_recap
from app.services.theme_recaps import publish_theme_recaps
import test_lessons as existing_tests


class RecapTests(unittest.TestCase):
    make_engine = existing_tests.LessonApiTests.make_engine
    setUp = existing_tests.LessonApiTests.setUp

    @classmethod
    def setUpClass(cls):
        cls.course = []
        for index, (character, kana, meaning) in enumerate([
            ("日", "ひ", "soleil"), ("月", "つき", "lune"), ("火", "ひ", "feu"),
        ]):
            source = f"word-{index}"
            grammar = f"grammar-{index}"
            options = [{"id": str(i), "label": {"fr": label, "en": label}} for i, label in enumerate([meaning, "eau", "terre", "bois"])]
            steps = [dict(id="goal", kind="read", title="Start"),
                dict(id="word", kind="word", source_id=source, japanese=character, meaning={"fr": meaning, "en": meaning}, segments=[{"surface": character, "reading": kana}]),
                dict(id="kanji", kind="kanji", source_id=f"kanji-{index}", character=character, meaning={"fr": meaning, "en": meaning}),
                dict(id="choice", kind="choice", source_id=source, title="Word", japanese=character, options=options, correct_option="0", solution={"fr": meaning, "en": meaning}),
                dict(id=f"apply-{grammar}", kind="choice", title="Grammar", japanese="____", options=copy.deepcopy(options), correct_option="0", solution={"fr": meaning, "en": meaning}),
                dict(id="end", kind="read", title="End")]
            cls.course.append(dict(id=f"lesson-{index}", level="N5", position=index+1, version="v1", content=dict(
                unit_id="unit", unit_title={"fr": "Unite", "en": "Unit"}, title={"fr": f"Lecon {index}", "en": f"Lesson {index}"},
                goal="Learn", minutes=4, vocabulary_ids=[source], grammar_ids=[grammar], kanji_ids=[f"kanji-{index}"], steps=steps)))

    def install(self, count=3):
        with self.Factory.begin() as db:
            db.get(Lesson, "test").position = 1000
            db.flush()
            for item in self.course[:count]:
                db.add(Lesson(**copy.deepcopy(item)))

    def complete(self, index, user=None):
        record = self.course[index]
        with self.Factory.begin() as db:
            db.add(LessonProgress(user_id=(user or self.user).id, lesson_id=record["id"],
                version=record["version"], cursor=len(record["content"]["steps"]), revision=1,
                answers={}, completed_at=datetime.now(timezone.utc)))

    def publish(self):
        with self.Factory.begin() as db:
            db.delete(db.get(Lesson, "test"))
            db.flush()
            return publish_theme_recaps(db)

    def test_exhaustive_first_and_full_course_coverage(self):
        self.install(len(self.course))
        with self.Factory() as db:
            first = build_recap(db, db.get(Lesson, self.course[0]["id"]), self.user.id)
        self.assertEqual(len(first) - 1, 3)
        for index in range(len(self.course) - 1):
            self.complete(index)
        with self.Factory() as db:
            last = db.get(Lesson, self.course[-1]["id"])
            before = copy.deepcopy(last.content)
            recap = build_recap(db, last, self.user.id)
            self.assertEqual(recap, build_recap(db, last, self.user.id))
            self.assertEqual(last.content, before)
        questions = recap[1:]
        self.assertEqual(len(questions), 9)
        self.assertEqual(len({q["recap_key"] for q in questions}), len(questions))
        self.assertEqual([sum(q["recap_category"] == c for q in questions)
                          for c in ("vocabulary", "grammar", "kanji")], [3, 3, 3])
        for question in questions:
            if question["kind"] == "choice":
                self.assertEqual(len(question["options"]), 4)
                self.assertIn(question["correct_option"], {o["id"] for o in question["options"]})
                for locale in ("fr", "en"):
                    self.assertEqual(len({o["label"][locale] for o in question["options"]}), 4)

    def test_only_own_completed_earlier_lessons(self):
        self.install()
        self.complete(0, self.other)
        self.complete(2)
        with self.Factory() as db:
            current = db.get(Lesson, self.course[1]["id"])
            recap = build_recap(db, current, self.user.id)
            self.assertEqual({q["source_lesson_id"] for q in recap[1:]}, {current.id})
        self.complete(0)
        with self.Factory() as db:
            recap = build_recap(db, db.get(Lesson, self.course[1]["id"]), self.user.id)
            self.assertEqual({q["source_lesson_id"] for q in recap[1:]}, {self.course[0]["id"], self.course[1]["id"]})

    def test_saved_test_completion_replay_and_no_answer_leak(self):
        self.install()
        for index in range(3):
            self.complete(index)
        self.publish()
        identity = "n5-unit-recap"
        base = []
        url = f"/lessons/{identity}"
        before = self.client.get(url).json()
        self.assertEqual(before["recap_total"], 9)
        self.assertEqual(before["step"]["id"], "recap-intro")
        payload = dict(action="continue", step_id=before["step"]["id"], revision=before["revision"])
        response = self.client.post(url + "/progress", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        state = response.json()
        self.assertTrue(state["step"]["recap"])
        self.assertFalse(state["lesson"]["completed"])
        self.assertEqual(state, self.client.post(url + "/progress", json=payload).json())
        with self.Factory() as db:
            snapshot = copy.deepcopy(db.get(LessonProgress, (self.user.id, identity)).recap_steps)
        raw_by_id = {s["id"]: s for s in snapshot}
        while state["step"]:
            step = state["step"]
            for forbidden in ("solution", "accepted", "correct_option", "recap_word", "recap_key"):
                self.assertNotIn(forbidden, step)
            if step["kind"] in {"choice", "recall"} and not state["feedback"]:
                raw = raw_by_id[step["id"]]
                answer = raw["correct_option"] if raw["kind"] == "choice" else raw["accepted"][0]
                payload = dict(action="answer", step_id=step["id"], revision=state["revision"], answer=answer)
            else:
                payload = dict(action="continue", step_id=step["id"], revision=state["revision"])
            response = self.client.post(url + "/progress?locale=fr", json=payload)
            self.assertEqual(response.status_code, 200, response.text)
            state = response.json()
            self.assertEqual(state, self.client.get(url + "?locale=fr").json())
        self.assertTrue(state["lesson"]["completed"])
        self.assertEqual(state["recap_correct"], state["recap_total"])
        self.assertEqual(state["recap_answered"], len(snapshot)-1)
        listing = self.client.get("/lessons?locale=fr")
        self.assertEqual(listing.status_code, 200, listing.text)
        listed = next(item for item in listing.json() if item["id"] == identity)
        self.assertEqual(listed["total_steps"], len(base) + len(snapshot))
        self.assertEqual(listed["completed_steps"], listed["total_steps"])
        with self.Factory() as db:
            progress = db.get(LessonProgress, (self.user.id, identity))
            self.assertEqual(progress.recap_steps, snapshot)
            self.assertEqual(progress.step_order, [s["id"] for s in base])
        self.assertEqual(self.client.post(url + "/progress", json={**payload, "revision": state["revision"]}).status_code, 409)

    def test_completed_legacy_lessons_stay_completed(self):
        self.install()
        self.complete(0)
        state = self.client.get(f"/lessons/{self.course[0]['id']}").json()
        self.assertTrue(state["lesson"]["completed"])
        self.assertIsNone(state["step"])
        self.assertEqual(state["recap_total"], 0)

    def test_snapshot_is_not_expanded_by_another_completed_lesson(self):
        self.install()
        with self.Factory.begin() as db:
            first = db.get(Lesson, self.course[0]["id"])
            first.content = {**first.content, "unit_id": "earlier"}
        self.complete(1)
        self.complete(2)
        self.publish()
        identity = "n5-unit-recap"
        url = f"/lessons/{identity}"
        initial = self.client.get(url).json()
        self.assertEqual(initial["recap_total"], 6)
        response = self.client.post(url + "/progress", json=dict(action="continue", step_id="recap-intro", revision=0))
        self.assertEqual(response.status_code, 200, response.text)
        self.complete(0)
        self.assertEqual(self.client.get(url).json()["recap_total"], 6)

    def test_wrong_recap_answer_is_saved_without_advancing(self):
        self.install()
        for index in range(3):
            self.complete(index)
        self.publish()
        identity = "n5-unit-recap"
        with self.Factory.begin() as db:
            lesson = db.get(Lesson, identity)
            recap = build_recap(db, lesson, self.user.id)
            base = lesson.content["steps"]
            db.add(LessonProgress(user_id=self.user.id, lesson_id=identity, version=lesson.version,
                cursor=len(base)+1, revision=1, step_order=[s["id"] for s in base], recap_steps=recap, answers={}))
        question = recap[1]
        wrong = next(o["id"] for o in question["options"] if o["id"] != question["correct_option"])
        url = f"/lessons/{identity}"
        payload = dict(action="answer", step_id=question["id"], revision=1, answer=wrong)
        state = self.client.post(url + "/progress", json=payload).json()
        self.assertFalse(state["feedback"]["correct"])
        self.assertEqual(state["feedback"]["correct_option_id"], question["correct_option"])
        self.assertEqual(state["recap_correct"], 0)
        self.assertEqual(state["recap_answered"], 1)
        self.assertEqual(state["cursor"], len(base)+1)
        self.assertEqual(self.client.post(url + "/progress", json=payload).json(), state)
        self.assertEqual(self.client.get(url).json(), state)
        self.assertEqual(self.client.post(url + "/progress", json={**payload, "answer": question["correct_option"]}).status_code, 409)


class RecapMigrationTests(unittest.TestCase):
    def test_additive_idempotent_and_protected(self):
        path = Path(__file__).resolve().parents[1] / "alembic/versions/0011_lesson_recap.py"
        spec = importlib.util.spec_from_file_location("recap_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE lesson_progress (cursor INTEGER NOT NULL)"))
            connection.execute(text("INSERT INTO lesson_progress VALUES (42)"))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                migration.upgrade()
                self.assertEqual(connection.execute(text("SELECT cursor, recap_steps FROM lesson_progress")).one(), (42, None))
                connection.execute(text("UPDATE lesson_progress SET recap_steps = '[]'"))
                with self.assertRaises(RuntimeError):
                    migration.downgrade()
                self.assertIn("recap_steps", {c["name"] for c in inspect(connection).get_columns("lesson_progress")})
