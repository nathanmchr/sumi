import copy
import importlib.util
import json
import os
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.base import Base
from app.models.content import JLPTLevel
from app.models.lesson import Lesson, LessonProgress
from app.models.user import User
from app.models.learning import LearningState, ReviewHistory
from app.routers.lessons import router
from app.services.lesson_service import normalize_answer
from app.services.lesson_sequence import gradual_steps, ordered_steps
from app.services.lesson_choices import lesson_options, choice_signature

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from import_n5_lessons import compile_course, import_course, surface, DATA


class CurriculumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lessons, cls.report = compile_course()

    def test_complete_unique_coverage_and_short_lessons(self):
        self.assertEqual([self.report[k] for k in ("units", "lessons", "vocabulary", "grammar", "kanji")], [15, 109, 668, 84, 86])
        for key, count in (("vocabulary_ids", 668), ("grammar_ids", 84), ("kanji_ids", 86)):
            ids = [value for lesson in self.lessons for value in lesson["content"][key]]
            self.assertEqual(len(ids), count)
            self.assertEqual(len(set(ids)), count)
        for lesson in self.lessons:
            self.assertLessEqual(len(lesson["content"]["vocabulary_ids"]), 8)
            self.assertLessEqual(len(lesson["content"]["kanji_ids"]), 3)
            steps = lesson["content"]["steps"]
            self.assertEqual(len({s["id"] for s in steps}), len(steps))
            for step in steps:
                self.assertTrue(step["title"])
                if step["kind"] == "choice":
                    for locale in ("fr", "en"):
                        self.assertEqual(len({o["label"][locale] for o in step["options"]}), 3)
                    self.assertIn(step["correct_option"], {o["id"] for o in step["options"]})

    def test_kana_only_and_writing_level_are_preserved(self):
        self.assertEqual(surface(dict(Kanji="掛ける", Kana="かける", KanjiLevel="N3")), "かける")
        self.assertEqual(surface(dict(Kanji="掃除", Kana="そうじする", KanjiLevel="N5")), "掃除する")
        for lesson in self.lessons:
            for step in lesson["content"]["steps"]:
                if step["kind"] == "word" and all("ぁ" <= c <= "ゖ" for c in step["japanese"]):
                    self.assertFalse(any(segment.get("reading") for segment in step["segments"]))
        examples = [s for l in self.lessons for s in l["content"]["steps"] if s.get("character") == "円"]
        self.assertTrue(any("円い" == line["japanese"] for line in examples[0]["lines"]))

    def test_deterministic_compilation(self):
        self.assertEqual(self.lessons, compile_course()[0])

    def test_four_presented_choices_preserve_versioned_content(self):
        from build_lesson_choices import build_supplements
        self.assertEqual(json.loads((DATA / "n5_choice_supplements.json").read_text()), build_supplements())
        for lesson in self.lessons:
            for step in lesson["content"]["steps"]:
                if step["kind"] != "choice":
                    continue
                original = copy.deepcopy(step)
                options = lesson_options(step)
                self.assertEqual(len(options), 4, step["id"])
                self.assertEqual(len({o["id"] for o in options}), 4)
                for locale in ("fr", "en"):
                    self.assertEqual(len({o["label"][locale].casefold() for o in options}), 4)
                self.assertTrue(all(o in options for o in step["options"]))
                self.assertEqual(step, original)
                changed = {**step, "japanese": "different question"}
                self.assertEqual(lesson_options(changed), step["options"])

    def test_original_cloze_and_bilingual_structure_coverage(self):
        examples = json.loads((DATA / "n5_grammar_examples.json").read_text())["entries"]
        patterns = json.loads((DATA / "n5_grammar_patterns_en.json").read_text())
        self.assertEqual(len(patterns), len(examples))
        for example in examples.values():
            self.assertEqual(example[1].count("____"), 1)
        self.assertIn("まだ", patterns[26])
        self.assertIn("にする", patterns[49])

    def test_every_lesson_checks_small_blocks_before_more_words(self):
        for record in self.lessons:
            with self.subTest(lesson=record["id"]):
                original = copy.deepcopy(record["content"]["steps"])
                ordered = ordered_steps(Lesson(**record), None)
                self.assertEqual({s["id"] for s in ordered}, {s["id"] for s in original})
                self.assertEqual(len(ordered), len(original))
                self.assertEqual(record["content"]["steps"], original)
                pending = []
                seen = set()
                for step in ordered:
                    if step["kind"] == "word":
                        pending.append(step["source_id"])
                        self.assertLessEqual(len(pending), 2)
                        seen.add(step["source_id"])
                    elif step["id"].startswith("recognise-") and step.get("source_id") in pending:
                        pending.remove(step["source_id"])
                    elif step["kind"] == "recall":
                        self.assertIn(step["source_id"], seen)
                    elif step["kind"] == "dialogue":
                        self.assertEqual(seen, set(record["content"]["vocabulary_ids"]))
                self.assertFalse(pending)
                self.assertEqual(ordered[-1]["id"], "reflect")

    def test_legacy_completed_steps_and_current_step_stay_in_place(self):
        lesson = Lesson(**self.lessons[0])
        original = lesson.content["steps"]
        for cursor in range(len(original) + 1):
            progress = LessonProgress(cursor=cursor, revision=cursor + 1, answers={}, step_order=None)
            result = ordered_steps(lesson, progress)
            keep = min(len(original), cursor + 1)
            self.assertEqual(result[:keep], original[:keep])
            self.assertEqual({s["id"] for s in result}, {s["id"] for s in original})
            self.assertIsNone(progress.step_order)

    def test_saved_order_is_stable_and_invalid_orders_are_rejected(self):
        from fastapi import HTTPException
        lesson = Lesson(**self.lessons[0])
        sequence = gradual_steps(lesson.content["steps"])
        progress = LessonProgress(cursor=5, revision=7, answers={}, step_order=[s["id"] for s in sequence])
        self.assertEqual(ordered_steps(lesson, progress), sequence)
        progress.step_order[-1] = progress.step_order[0]
        with self.assertRaises(HTTPException):
            ordered_steps(lesson, progress)


class LessonApiTests(unittest.TestCase):
    def make_engine(self):
        return create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    def setUp(self):
        self.engine = self.make_engine()
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.Factory = sessionmaker(self.engine, expire_on_commit=False)
        self.content = dict(unit_id="unit", unit_title={"fr": "Unité", "en": "Unit"}, title={"fr":"Leçon", "en":"Lesson"},
            goal={"fr":"Apprendre", "en":"Learn"}, minutes=4, vocabulary_ids=[], grammar_ids=[], kanji_ids=[], steps=[
                dict(id="read", kind="read", title={"fr":"Bonjour", "en":"Hello"}),
                dict(id="choice", kind="choice", title="Quiz", options=[dict(id="yes", label={"fr":"chat", "en":"cat"}),dict(id="no",label={"fr":"chien", "en":"dog"})], correct_option="yes", solution={"fr":"chat", "en":"cat"}),
                dict(id="recall", kind="recall", title="Recall", accepted=["ねこ","neko"], solution={"fr":"ねこ", "en":"ねこ"})])
        with self.Factory.begin() as db:
            db.add(JLPTLevel(code="N5", label="N5", rank=1))
            self.user = User(email="lesson-a@example.com", full_name="A", hashed_password="unused")
            self.other = User(email="lesson-b@example.com", full_name="B", hashed_password="unused")
            db.add_all([self.user, self.other])
            db.add(Lesson(id="test", level="N5", position=1, version="v1", content=self.content))
        def database():
            with self.Factory() as db:
                yield db
        self.application = FastAPI()
        self.application.include_router(router)
        self.application.dependency_overrides[get_db] = database
        self.application.dependency_overrides[get_current_user] = lambda: self.user
        self.client = TestClient(self.application)
        self.addCleanup(self.client.close)

    def post(self, step, revision, action="continue", **kwargs):
        return self.client.post("/lessons/test/progress?locale=fr", json=dict(step_id=step, revision=revision, action=action, **kwargs))

    def test_authentication_and_contract(self):
        del self.application.dependency_overrides[get_current_user]
        self.assertEqual(self.client.get("/lessons").status_code, 401)
        self.assertEqual(self.post("read", 0).status_code, 401)

    def test_read_is_side_effect_free_localized_and_bounded(self):
        self.assertEqual(self.client.get("/lessons/test?locale=fr").json()["step"]["title"], "Bonjour")
        self.assertEqual(self.client.get("/lessons/test?locale=en").json()["lesson"]["title"], "Lesson")
        self.assertEqual(self.client.get("/lessons/test?step=1").status_code, 422)
        self.assertEqual(self.client.get("/lessons/test?step=-1").status_code, 422)
        self.assertEqual(self.client.get("/lessons/missing").status_code, 404)
        with self.Factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(LessonProgress)), 0)

    def test_wrong_answer_feedback_replay_and_stale_revision(self):
        first = self.post("read", 0)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(self.post("read", 0).json(), first.json())
        self.assertNotIn("correct_option", first.json()["step"])
        self.assertNotIn("solution", first.json()["step"])
        self.assertIsNone(first.json()["feedback"])
        self.assertEqual(self.post("choice", 0, "answer", answer="no").status_code, 409)
        self.assertEqual(self.post("choice", 1).status_code, 422)
        self.assertEqual(self.post("choice", 1, "answer", answer="forged").status_code, 422)
        wrong = self.post("choice", 1, "answer", answer="no")
        self.assertFalse(wrong.json()["feedback"]["correct"])
        self.assertEqual(wrong.json()["feedback"]["answer"], "chat")
        self.assertEqual(wrong.json()["feedback"]["explanation"], "")
        self.assertEqual(wrong.json()["feedback"]["selected_option_id"], "no")
        self.assertEqual(wrong.json()["feedback"]["correct_option_id"], "yes")
        self.assertEqual(self.post("choice", 1, "answer", answer="no").json(), wrong.json())
        self.assertEqual(self.post("choice", 2, "answer", answer="yes").status_code, 409)
        self.assertEqual(self.client.get("/lessons/test?locale=fr").json(), wrong.json())

    def test_feedback_preserves_explicit_localized_explanations(self):
        with self.Factory.begin() as db:
            lesson = db.get(Lesson, "test")
            content = copy.deepcopy(lesson.content)
            content["steps"][1]["explanation"] = {"fr": "La particule marque le sujet.", "en": "The particle marks the subject."}
            lesson.content = content
        self.post("read", 0)
        response = self.post("choice", 1, "answer", answer="yes")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["feedback"]["explanation"], "La particule marque le sujet.")
        self.assertEqual(self.client.get("/lessons/test?locale=en").json()["feedback"]["explanation"], "The particle marks the subject.")

    def test_legacy_feedback_has_no_invented_selection(self):
        with self.Factory.begin() as db:
            db.add(LessonProgress(user_id=self.user.id, lesson_id="test", version="v1", cursor=1,
                revision=2, answers={"choice": {"correct": False}}))
        feedback = self.client.get("/lessons/test?locale=fr").json()["feedback"]
        self.assertIsNone(feedback["selected_option_id"])
        self.assertEqual(feedback["correct_option_id"], "yes")

    def test_added_fourth_choice_is_accepted_persisted_and_idempotent(self):
        content = copy.deepcopy(self.content)
        step = content["steps"][1]
        step["options"].append({"id": "bird", "label": {"fr": "oiseau", "en": "bird"}})
        extra = {"id": "fish", "label": {"fr": "poisson", "en": "fish"}}
        with self.Factory.begin() as db:
            db.get(Lesson, "test").content = content
        with patch("app.services.lesson_choices.supplements", return_value={choice_signature(step): extra}):
            view = self.post("read", 0).json()
            self.assertEqual(len(view["step"]["options"]), 4)
            self.assertIsNone(view["feedback"])
            result = self.post("choice", 1, "answer", answer="fish")
            self.assertEqual(result.status_code, 200)
            self.assertFalse(result.json()["feedback"]["correct"])
            self.assertEqual(result.json()["feedback"]["selected_option_id"], "fish")
            self.assertEqual(result.json()["feedback"]["correct_option_id"], "yes")
            self.assertEqual(result.json(), self.post("choice", 1, "answer", answer="fish").json())
            self.assertEqual(result.json(), self.client.get("/lessons/test?locale=fr").json())
            with self.Factory() as db:
                self.assertEqual(db.get(Lesson, "test").content, content)
                self.assertEqual(db.get(Lesson, "test").version, "v1")

    def test_word_audio_and_meaning_do_not_leak_production_answer(self):
        content = copy.deepcopy(self.content)
        content["steps"][0] = dict(id="read", kind="word", title="Cat", source_id="cat", japanese="猫",
            meaning={"fr": "chat", "en": "cat"}, audio_row={"Kana": "ねこ"},
            segments=[{"surface": "猫", "reading": "ねこ"}], romaji="neko")
        content["steps"][1]["japanese"] = "猫"
        for step in content["steps"][1:]:
            step["source_id"] = "cat"
        with self.Factory.begin() as db:
            db.get(Lesson, "test").content = content
        with patch("app.services.catalog_audio.canonical_row_audio", return_value="/audio/cat.mp3"):
            self.assertEqual(self.client.get("/lessons/test").json()["step"]["audio_url"], "/audio/cat.mp3")
            choice = self.post("read", 0).json()
            self.assertEqual(choice["step"]["audio_url"], "/audio/cat.mp3")
            self.assertEqual(choice["step"]["segments"], [{"surface": "猫", "reading": "ねこ"}])
            self.assertEqual(choice["step"]["romaji"], "neko")
            self.assertNotIn("meaning", choice["step"])
            correct = self.post("choice", 1, "answer", answer="yes").json()["feedback"]
            self.assertEqual(correct["selected_option_id"], "yes")
            self.assertEqual(correct["meaning"], "chat")
            self.assertEqual(correct["japanese"], "猫")
            recall = self.post("choice", 2).json()
            self.assertNotIn("audio_url", recall["step"])
            self.assertNotIn("japanese", recall["step"])
            self.assertNotIn("segments", recall["step"])
            self.assertNotIn("romaji", recall["step"])
            self.assertIsNone(recall["feedback"])
            feedback = self.post("recall", 3, "answer", answer="incorrect").json()["feedback"]
            self.assertEqual(feedback["audio_url"], "/audio/cat.mp3")
            self.assertEqual(feedback["meaning"], "chat")
            self.assertEqual(feedback["segments"], [{"surface": "猫", "reading": "ねこ"}])
            self.assertEqual(feedback["romaji"], "neko")
            self.assertNotIn("selected_option_id", feedback)
            self.assertEqual(self.client.get("/lessons/test?locale=en").json()["feedback"]["meaning"], "cat")

    def test_own_progress_only_and_no_srs_side_effect(self):
        self.post("read", 0)
        self.application.dependency_overrides[get_current_user] = lambda: self.other
        self.assertEqual(self.client.get("/lessons/test").json()["cursor"], 0)
        self.assertEqual(self.client.get("/lessons").json()[0]["completed_steps"], 0)
        self.assertEqual(self.client.get("/lessons/test?step=1").status_code, 422)
        self.assertEqual(self.post("read", 0).status_code, 200)
        with self.Factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(LessonProgress)), 2)
            self.assertEqual(db.scalar(select(func.count()).select_from(LearningState)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(ReviewHistory)), 0)

    def test_completion_and_past_review(self):
        self.post("read", 0)
        self.post("choice", 1, "answer", answer="yes")
        self.post("choice", 2)
        hidden = self.client.get("/lessons/test").json()["step"]
        self.assertNotIn("accepted", hidden)
        self.assertTrue(self.post("recall", 3, "answer", answer=" ＮｅＫｏ ").json()["feedback"]["correct"])
        final = self.post("recall", 4).json()
        self.assertTrue(final["lesson"]["completed"])
        self.assertIsNone(final["step"])
        self.assertEqual(final["correct"], 2)
        self.assertTrue(self.client.get("/lessons/test?step=1").json()["feedback"]["correct"])
        self.assertEqual(self.post("recall", 5).status_code, 409)
        self.assertEqual(normalize_answer("ネコ"), "ねこ")

    def test_import_rejects_revision_with_progress(self):
        record = dict(id="test", level="N5", position=1, version="v1", content=self.content)
        with self.Factory.begin() as db:
            self.assertEqual(import_course(db, [record])["unchanged"], 1)
        self.post("read", 0)
        with self.assertRaises(ValueError):
            with self.Factory.begin() as db:
                import_course(db, [{**record, "version":"v2"}])
        with self.Factory() as db:
            self.assertEqual(db.get(Lesson, "test").version, "v1")

    def test_full_course_import_is_idempotent(self):
        records, _ = compile_course()
        with self.Factory.begin() as db:
            db.delete(db.get(Lesson, "test"))
            db.flush()
            self.assertEqual(import_course(db, records)["created"], 109)
        with self.Factory.begin() as db:
            self.assertEqual(import_course(db, records)["unchanged"], 109)

    def prepare_kanji_examples(self):
        from datetime import datetime, timezone
        def word(identity, spelling):
            return dict(id=f"word-{identity}", kind="word", title="Word", source_id=identity,
                japanese=spelling, meaning={"fr": f"fr-{identity}", "en": f"en-{identity}"})
        with self.Factory.begin() as db:
            current = db.get(Lesson, "test")
            current.position = 50
            current.content = {**self.content, "steps": [
                dict(id="kanji", kind="kanji", title="Kanji", character="学",
                    lines=[dict(japanese="未学習", translation={"fr":"futur", "en":"future"})]),
                word("current", "学ぶ"),
            ]}
            rows = [
                ("old", 10, [word("university", "大学"), word("extra", "学問")], self.user.id, True, "v1"),
                ("outdated", 15, [word("outdated", "見学")], self.user.id, True, "old-version"),
                ("near", 20, [word("school", "学校"), word("student", "学生"), word("duplicate", "学校"),
                    word("school", "学校内"), word("kana", "がくしゅう"), word("unrelated", "本")], self.user.id, True, "v1"),
                ("unfinished", 30, [word("unfinished", "学者")], self.user.id, False, "v1"),
                ("other", 40, [word("other", "数学")], self.other.id, True, "v1"),
                ("future", 60, [word("future", "科学")], self.user.id, True, "v1"),
            ]
            for identity, position, words, user_id, completed, version in rows:
                db.add(Lesson(id=identity, level="N5", position=position, version="v1", content={**self.content, "steps":words}))
                db.flush()
                db.add(LessonProgress(user_id=user_id, lesson_id=identity, version=version, cursor=len(words) if completed else 0,
                    revision=1, answers={}, completed_at=datetime.now(timezone.utc) if completed else None))

    def test_kanji_examples_use_only_own_completed_earlier_lessons(self):
        self.prepare_kanji_examples()
        expected = ["学校", "学生", "大学"]
        for locale in ("fr", "en"):
            result = self.client.get(f"/lessons/test?locale={locale}")
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual([line["japanese"] for line in result.json()["step"]["lines"]], expected)
            self.assertEqual(result.json()["step"]["lines"][0]["translation"], f"{locale}-school")
        # Merely opening a kanji step does not record progress or rewrite its stored examples.
        with self.Factory() as db:
            self.assertIsNone(db.get(LessonProgress, (self.user.id,"test")))
            self.assertEqual(db.get(Lesson,"test").content["steps"][0]["lines"][0]["japanese"], "未学習")
        self.assertEqual(self.post("kanji", 0).status_code, 200)
        self.assertTrue(self.post("word-current", 1).json()["lesson"]["completed"])
        replay = self.client.get("/lessons/test?locale=fr&step=0").json()
        self.assertEqual([line["japanese"] for line in replay["step"]["lines"]], expected)
        self.application.dependency_overrides[get_current_user] = lambda: self.other
        self.assertEqual(self.client.get("/lessons/test").json()["step"]["lines"], [{"japanese":"数学", "translation":"en-other"}])

    def test_first_kanji_has_no_unknown_word_fallback(self):
        self.prepare_kanji_examples()
        with self.Factory.begin() as db:
            db.get(Lesson,"test").position = 1
        for locale, message in (("fr", "Tu n'as pas encore"), ("en", "You have not yet")):
            result = self.client.get(f"/lessons/test?locale={locale}").json()
            self.assertNotIn("lines", result["step"])
            self.assertTrue(result["step"]["body"].startswith(message))
            self.assertNotIn("未学習", json.dumps(result,ensure_ascii=False))

    def test_previous_kanji_examples_keep_reading_aids(self):
        self.prepare_kanji_examples()
        segments = [{"surface": "学", "reading": "がっ"}, {"surface": "校", "reading": "こう"}]
        with self.Factory.begin() as db:
            lesson = db.get(Lesson, "near")
            content = copy.deepcopy(lesson.content)
            content["steps"][0].update(segments=segments, romaji="gakkou")
            lesson.content = content
        example = self.client.get("/lessons/test?locale=fr").json()["step"]["lines"][0]
        self.assertEqual(example["segments"], segments)
        self.assertEqual(example["romaji"], "gakkou")

    def test_review_word_uses_catalog_aids_without_rewriting_content(self):
        content = copy.deepcopy(self.content)
        content["steps"][1].update(japanese="日曜日", source_id="daa10f9a-525a-5488-a07c-ec5002147686", review=True)
        with self.Factory.begin() as db:
            db.get(Lesson, "test").content = content
        choice = self.post("read", 0).json()["step"]
        self.assertEqual([segment["reading"] for segment in choice["segments"]], ["にち", "よう", "び"])
        self.assertEqual(choice["romaji"], "nichiyoubi")
        feedback = self.post("choice", 1, "answer", answer="no").json()["feedback"]
        self.assertEqual(feedback["segments"], choice["segments"])
        self.assertEqual(feedback["romaji"], choice["romaji"])
        with self.Factory() as db:
            lesson = db.get(Lesson, "test")
            self.assertEqual(lesson.content, content)
            self.assertEqual(lesson.version, "v1")

    def test_gradual_order_is_frozen_on_first_command_and_resumes(self):
        content = compile_course()[0][0]["content"]
        with self.Factory.begin() as db:
            db.get(Lesson,"test").content = content
        first = self.client.get("/lessons/test?locale=fr").json()
        result = self.post(first["step"]["id"], 0)
        self.assertEqual(result.status_code, 200, result.text)
        expected = [s["id"] for s in gradual_steps(content["steps"])]
        with self.Factory() as db:
            progress = db.get(LessonProgress,(self.user.id,"test"))
            self.assertEqual(progress.step_order, expected)
            self.assertEqual(progress.cursor, 1)
        self.assertEqual(self.client.get("/lessons/test?locale=fr").json(), result.json())
        self.assertEqual(self.post(first["step"]["id"], 0).json(), result.json())

    def test_old_answer_and_cursor_survive_sequence_adoption(self):
        content = compile_course()[0][0]["content"]
        current = next((i,s) for i,s in enumerate(content["steps"]) if s["kind"] == "choice")
        cursor, question = current
        answers = {question["id"]: {"correct":False}}
        with self.Factory.begin() as db:
            db.get(Lesson,"test").content = content
            db.add(LessonProgress(user_id=self.user.id, lesson_id="test", version="v1",
                cursor=cursor, revision=30, answers=answers))
        before = self.client.get("/lessons/test?locale=fr").json()
        self.assertEqual(before["step"]["id"], question["id"])
        self.assertFalse(before["feedback"]["correct"])
        result = self.post(question["id"],30)
        self.assertEqual(result.status_code,200,result.text)
        with self.Factory() as db:
            progress = db.get(LessonProgress,(self.user.id,"test"))
            self.assertEqual(progress.step_order[:cursor+1], [s["id"] for s in content["steps"][:cursor+1]])
            self.assertEqual(progress.cursor,cursor+1)
            self.assertEqual(progress.answers,answers)
            self.assertEqual(progress.version,"v1")
        replay = self.client.get(f"/lessons/test?step={cursor}").json()
        self.assertEqual(replay["step"]["id"],question["id"])
        self.assertFalse(replay["feedback"]["correct"])


class LessonMigrationTests(unittest.TestCase):
    def test_step_order_migration_preserves_progress_and_protects_downgrade(self):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from sqlalchemy import text
        path = Path(__file__).resolve().parents[1] / "alembic/versions/0010_lesson_step_order.py"
        spec = importlib.util.spec_from_file_location("step_order_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE lesson_progress (user_id TEXT PRIMARY KEY, cursor INTEGER, answers JSON)"))
            connection.execute(text("INSERT INTO lesson_progress VALUES ('one',3,:answers)"), {"answers":json.dumps({"word":{"correct":False}})})
            before = connection.execute(text("SELECT user_id,cursor,answers FROM lesson_progress")).all()
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                migration.upgrade()
                self.assertIsNone(connection.execute(text("SELECT step_order FROM lesson_progress")).scalar())
                self.assertEqual(before,connection.execute(text("SELECT user_id,cursor,answers FROM lesson_progress")).all())
                connection.execute(text("UPDATE lesson_progress SET step_order=:steps"),{"steps":json.dumps(["word"])})
                with self.assertRaisesRegex(RuntimeError,"Cannot drop"):
                    migration.downgrade()
                connection.execute(text("UPDATE lesson_progress SET step_order=NULL"))
                migration.downgrade()
                self.assertEqual(before,connection.execute(text("SELECT user_id,cursor,answers FROM lesson_progress")).all())

    def test_fresh_migration_adoption_and_downgrade(self):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        path = Path(__file__).resolve().parents[1] / "alembic/versions/0009_lessons.py"
        spec = importlib.util.spec_from_file_location("lesson_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        with engine.begin() as connection:
            Base.metadata.create_all(connection, tables=[User.__table__, JLPTLevel.__table__])
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                migration.upgrade()
                self.assertEqual(len(inspect(connection).get_columns("lesson_progress")), 10)
                migration.downgrade()
                self.assertFalse(inspect(connection).has_table("lessons"))
                Lesson.__table__.create(connection)
                LessonProgress.__table__.create(connection)
                migration.upgrade()

    def test_incompatible_existing_schema_is_not_adopted(self):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from sqlalchemy import text
        path = Path(__file__).resolve().parents[1] / "alembic/versions/0009_lessons.py"
        spec = importlib.util.spec_from_file_location("lesson_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE lessons (id TEXT PRIMARY KEY)"))
            with Operations.context(MigrationContext.configure(connection)):
                with self.assertRaisesRegex(RuntimeError, "unexpected columns"):
                    migration.upgrade()


@unittest.skipUnless(os.getenv("LESSONS_TEST_POSTGRES") == "1", "Opt-in isolated PostgreSQL lesson tests")
class PostgresLessonTests(LessonApiTests):
    def make_engine(self):
        from test_quiz_postgres import PostgresQuizTests
        return PostgresQuizTests.make_engine(self)

    def test_concurrent_first_step_is_idempotent(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from app.schemas.lesson import LessonCommand
        from app.services.lesson_service import command
        barrier = Barrier(2)
        def advance():
            with self.Factory.begin() as db:
                barrier.wait(timeout=5)
                return command(db, self.user.id, "test", LessonCommand(action="continue", step_id="read", revision=0), "fr")
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(advance), pool.submit(advance)
            self.assertEqual(a.result(timeout=10), b.result(timeout=10))
        with self.Factory() as db:
            self.assertEqual(db.get(LessonProgress, (self.user.id,"test")).revision, 1)

    def test_concurrent_different_answers_only_one_wins(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from fastapi import HTTPException
        from app.schemas.lesson import LessonCommand
        from app.services.lesson_service import command
        self.post("read", 0)
        barrier = Barrier(2)
        def answer(value):
            try:
                with self.Factory.begin() as db:
                    barrier.wait(timeout=5)
                    command(db, self.user.id, "test", LessonCommand(action="answer", step_id="choice", revision=1, answer=value), "fr")
                return 200
            except HTTPException as error:
                return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(answer,"yes"), pool.submit(answer,"no")
            self.assertEqual(sorted([a.result(timeout=10),b.result(timeout=10)]), [200,409])
        with self.Factory() as db:
            progress = db.get(LessonProgress, (self.user.id,"test"))
            self.assertEqual(progress.revision, 2)
            self.assertEqual(len(progress.answers), 1)


if __name__ == "__main__":
    unittest.main()
