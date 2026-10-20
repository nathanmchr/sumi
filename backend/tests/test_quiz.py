import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fsrs import Card, State
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import app.models  # noqa: F401 — register all SQLAlchemy models before schema creation
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.base import Base
from app.models.content import (
    JLPTLevel,
    VocabularyItem,
    VocabularyTranslation,
    KanjiItem,
    KanjiTranslation,
    GrammarItem,
    GrammarTranslation,
    ExampleSentence,
    ExampleSentenceTranslation,
)
from app.models.learning import (
    LearningState,
    ReviewHistory,
    StudyQuestion,
    StudySession,
    GrammarExercise,
)
from app.models.user import User, UserSettings
from app.routers.learning import router
from app.routers.users import router as settings_router
from app.services.learning_service import build_dashboard
from app.services.fsrs_service import SCHEDULER, memory_status, schedule_answer, utc
from app.services.quiz_choices import choose_distractors, conflicts
from app.utils.enums import ContentType, ReviewStatus

NOW = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)


class SchedulerTests(unittest.TestCase):
    def fresh(self):
        return LearningState(id=str(uuid4()), status=ReviewStatus.new)

    def test_first_success_four_hours_then_fsrs(self):
        s = self.fresh()
        first = schedule_answer(s, True, NOW, 5)
        self.assertEqual(s.next_review_at, NOW + timedelta(hours=4))
        self.assertEqual(s.status, ReviewStatus.learning)
        self.assertEqual(first["rating"], 3)
        schedule_answer(s, True, s.next_review_at, 1000)
        self.assertEqual(Card.from_dict(s.fsrs_card).state, State.Review)
        self.assertGreaterEqual(s.interval_days, 1)
        self.assertEqual(len(SCHEDULER.parameters), 21)
        self.assertEqual(SCHEDULER.desired_retention, 0.9)

    def test_error_ten_minutes_then_four_hours(self):
        s = self.fresh()
        schedule_answer(s, False, NOW, 800)
        self.assertEqual(s.next_review_at, NOW + timedelta(minutes=10))
        schedule_answer(s, True, s.next_review_at, 900)
        self.assertEqual(s.next_review_at, NOW + timedelta(minutes=10, hours=4))
        self.assertEqual(Card.from_dict(s.fsrs_card).state, State.Learning)

    def test_established_lapse_relearning_then_review(self):
        s = self.fresh()
        for _ in range(4):
            schedule_answer(s, True, s.next_review_at or NOW, 1000)
        difficulty = s.fsrs_card["difficulty"]
        missed = s.next_review_at
        schedule_answer(s, False, missed, 2000)
        self.assertEqual(s.status, ReviewStatus.relearning)
        self.assertEqual(s.next_review_at, missed + timedelta(minutes=10))
        self.assertGreater(s.fsrs_card["difficulty"], difficulty)
        schedule_answer(s, True, s.next_review_at, 2000)
        self.assertEqual(Card.from_dict(s.fsrs_card).state, State.Review)
        self.assertGreaterEqual(s.interval_days, 1)

    def test_legacy_reads_do_not_migrate(self):
        s = self.fresh()
        s.status = ReviewStatus.known
        s.repetition_count = 3
        s.interval_days = 12
        s.last_review_at = NOW - timedelta(days=12)
        s.next_review_at = NOW
        self.assertEqual(memory_status(s, NOW), ReviewStatus.known)
        self.assertIsNone(s.fsrs_card)
        self.assertEqual(s.next_review_at, NOW)
        out = schedule_answer(s, True, NOW, 100)
        self.assertEqual(out["before"]["stability"], 12)
        self.assertEqual(s.scheduler_version, "fsrs6")

    def test_status_thresholds_and_recent_errors(self):
        s = self.fresh()
        s.fsrs_card = Card(
            state=State.Review,
            stability=100,
            difficulty=5,
            last_review=NOW,
            due=NOW + timedelta(days=100),
        ).to_dict()
        s.consecutive_correct = 5
        s.recent_results = [True] * 5
        self.assertEqual(memory_status(s, NOW), ReviewStatus.master)
        self.assertEqual(
            memory_status(s, NOW + timedelta(days=1000)), ReviewStatus.fragile
        )
        s.recent_results = [False, False, True]
        self.assertEqual(memory_status(s, NOW), ReviewStatus.fragile)
        s.recent_results = [True] * 3
        s.consecutive_correct = 3
        self.assertEqual(memory_status(s, NOW), ReviewStatus.known)


class DistractorTests(unittest.TestCase):
    def item(self, label, canonical=None):
        return dict(
            id=str(uuid4()),
            surface=str(uuid4()),
            label=label,
            canonical=canonical or label,
            locale="fr",
            level="N5",
            pos="other",
        )

    def test_synonyms_aliases_and_canonical_collisions(self):
        for a, b in [("voiture", "automobile"), ("content ; joyeux", "heureux")]:
            self.assertTrue(conflicts(self.item(a), self.item(b)))
        self.assertTrue(
            conflicts(
                self.item("expression différente", "house"),
                self.item("autre texte", "home"),
            )
        )
        self.assertFalse(conflicts(self.item("chien"), self.item("lune")))

    def test_levels_languages_unique_and_no_forced_choices(self):
        target = self.item("voiture")
        candidates = [self.item(x) for x in ["automobile", "chien", "lune", "rivière"]]
        lang = self.item("soleil")
        lang["locale"] = "en"
        far = self.item("chaise")
        far["level"] = "N1"
        self.assertEqual(
            {i["label"] for i in choose_distractors(target, candidates + [lang, far])},
            {"chien", "lune", "rivière"},
        )
        self.assertEqual(choose_distractors(target, [candidates[0]]), [])


class QuizAPITests(unittest.TestCase):
    def test_catalogue_and_absorbed_ids_resolve_to_same_review(self):
        from app.models.content import ContentAlias
        canonical, old = str(uuid4()), str(uuid4())
        with self.Factory() as db:
            item = db.get(VocabularyItem, self.vocab[0].id)
            item.catalog_id = canonical
            db.add(ContentAlias(content_type="vocabulary", alias=old, content_id=item.id))
            db.commit()
        for identity in (canonical, old):
            turn = self.start(category="vocabulary", content_id=identity)
            self.assertEqual(turn["question"]["content_id"], self.vocab[0].id)

    def make_engine(self):
        return create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )

    def setUp(self):
        self.engine = self.make_engine()
        Base.metadata.create_all(self.engine)
        self.Factory = sessionmaker(
            self.engine, expire_on_commit=False, autoflush=False
        )
        with self.Factory() as db:
            for n in range(1, 6):
                db.add(JLPTLevel(code=f"N{n}", rank=n, label=f"N{n}"))
            self.user = User(
                email="quiz@example.test", full_name="Quiz", hashed_password="test"
            )
            self.user.settings = UserSettings(
                vocabulary_level_code="N5",
                kanji_level_code="N5",
                grammar_level_code="N5",
                content_locale="fr",
                interface_locale="fr",
            )
            self.other = User(
                email="other@example.test", full_name="Other", hashed_password="test"
            )
            db.add_all([self.user, self.other])
            self.vocab = []
            for jp, en, fr in [
                ("犬", "dog", "chien"),
                ("月", "moon", "lune"),
                ("川", "river", "rivière"),
                ("椅", "chair", "chaise"),
                ("花", "flower", "fleur"),
                ("雨", "rain", "pluie"),
            ]:
                v = VocabularyItem(
                    slug=en,
                    japanese=jp,
                    reading=jp,
                    translation=en,
                    part_of_speech="noun",
                    jlpt_level_code="N5",
                    translations=[VocabularyTranslation(locale="fr", translation=fr)],
                )
                k = KanjiItem(
                    slug=en,
                    character=jp,
                    meanings=[en],
                    onyomi=["オン"],
                    kunyomi=["くん"],
                    jlpt_level_code="N5",
                    translations=[KanjiTranslation(locale="fr", meanings=[fr])],
                )
                db.add_all([v, k])
                self.vocab.append(v)
            self.grammar = GrammarItem(
                slug="question",
                title="か",
                structure="ka",
                explanation="question",
                nuances="",
                jlpt_level_code="N5",
                translations=[
                    GrammarTranslation(locale="fr", explanation="question polie")
                ],
            )
            self.unavailable = GrammarItem(
                slug="no-exercise",
                title="だけ",
                structure="dake",
                explanation="only",
                nuances="",
                jlpt_level_code="N5",
            )
            db.add_all([self.grammar, self.unavailable])
            db.flush()
            db.add(
                GrammarExercise(
                    code="test-ka",
                    grammar_item_id=self.grammar.id,
                    prompt="これは本です___。",
                    answer="か",
                    distractors=["を", "に", "で"],
                    completed_sentence="これは本ですか。",
                    translations={
                        lang: {"context": hint, "translation": hint, "explanation": exp}
                        for lang, hint, exp in [
                            ("fr", "Est-ce un livre ?", "か marque une question."),
                            ("en", "Is this a book?", "か marks a question."),
                        ]
                    },
                )
            )
            db.add(
                ExampleSentence(
                    vocabulary_item_id=self.vocab[0].id,
                    text="犬がいます。",
                    translation="There is a dog.",
                    translations=[
                        ExampleSentenceTranslation(
                            locale="fr", translation="Il y a un chien."
                        )
                    ],
                )
            )
            db.commit()
        self.auth_id = self.user.id
        app = FastAPI()
        app.include_router(router)
        app.include_router(settings_router)

        def database():
            with self.Factory() as db:
                yield db

        def current():
            with self.Factory() as db:
                return db.get(User, self.auth_id)

        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_user] = current
        self.client = TestClient(app)
        self.clock = patch("app.services.quiz_service.now_utc", return_value=NOW)
        self.mock_clock = self.clock.start()

    def tearDown(self):
        self.clock.stop()
        self.client.close()
        self.engine.dispose()

    def start(self, show_introduction=False, **payload):
        r = self.client.post("/learning/sessions", json=payload)
        self.assertEqual(r.status_code, 200, r.text)
        turn = r.json()
        if (
            not show_introduction
            and turn.get("question")
            and turn["question"]["phase"] == "introduction"
        ):
            ready = self.client.post(
                "/learning/questions/" + turn["question"]["id"] + "/begin"
            )
            self.assertEqual(ready.status_code, 200, ready.text)
            turn["question"] = ready.json()
        return turn

    def answer(self, turn, correct=True):
        with self.Factory() as db:
            q = db.get(StudyQuestion, turn["question"]["id"])
            choice = (
                q.correct_option_id
                if correct
                else next(o["id"] for o in q.choices if o["id"] != q.correct_option_id)
            )
        r = self.client.post(
            "/learning/questions/" + q.id + "/answer", json={"option_id": choice}
        )
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def next_turn(self, turn, seconds=1):
        self.mock_clock.return_value += timedelta(seconds=seconds)
        response = self.client.post(
            "/learning/sessions/" + turn["session_id"] + "/next"
        )
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        if result.get("question") and result["question"]["phase"] == "introduction":
            ready = self.client.post(
                "/learning/questions/" + result["question"]["id"] + "/begin"
            )
            self.assertEqual(ready.status_code, 200, ready.text)
            result["question"] = ready.json()
        return result

    def add_range_grammar(self):
        with self.Factory() as db:
            for n in range(1, 6):
                item = GrammarItem(id=f"0000000{n}-0000-4000-8000-000000000001", slug=f"range-{n}",
                                   title=f"point {n}", structure="test", explanation="test", nuances="", jlpt_level_code=f"N{n}")
                db.add(item)
                db.flush()
                db.add(GrammarExercise(code=f"range-{n}", grammar_item_id=item.id, prompt="本です___。", answer="か",
                                       distractors=["を", "に", "で"], completed_sentence="本ですか。",
                                       translations={lang: {"context": "Question", "translation": "Question", "explanation": "Question"}
                                                     for lang in ("en", "fr")}))
            db.commit()

    def set_range(self, category, minimum, maximum):
        with self.Factory() as db:
            settings = db.get(User, self.user.id).settings
            setattr(settings, f"{category}_min_level_code", minimum)
            setattr(settings, f"{category}_level_code", maximum)
            db.commit()

    def test_grammar_range_issues_every_level_in_order_and_excludes_outside(self):
        self.add_range_grammar()
        self.set_range("grammar", "N4", "N2")
        turn = self.start(category="grammar", planned_items=6)
        levels = []
        for _ in range(6):
            if turn["ended"]:
                break
            levels.append(turn["question"]["jlpt_level_code"])
            self.answer(turn)
            turn = self.next_turn(turn)
        self.assertEqual(levels, ["N4", "N3", "N2"])
        self.assertTrue(turn["ended"])

    def test_vocabulary_and_kanji_discovery_follow_ranges_across_recalls(self):
        with self.Factory() as db:
            for model in (VocabularyItem, KanjiItem):
                for item, level in zip(db.scalars(select(model).order_by(model.slug)), ["N4", "N4", "N3", "N3", "N2", "N2"]):
                    item.jlpt_level_code = level
            db.commit()
        for kind in ("vocabulary", "kanji"):
            self.set_range(kind, "N4", "N3")
            turn = self.start(category=kind, planned_items=30)
            seen, discoveries = set(), []
            for _ in range(30):
                if turn["ended"]:
                    break
                question = turn["question"]
                self.assertIn(question["jlpt_level_code"], ["N4", "N3"])
                if question["content_id"] not in seen:
                    seen.add(question["content_id"])
                    discoveries.append(question["jlpt_level_code"])
                self.answer(turn)
                turn = self.next_turn(turn)
            self.assertEqual(discoveries, ["N4", "N4", "N3", "N3"], kind)
            self.assertTrue(turn["ended"])

    def test_mixed_discovery_prefers_easier_level_over_category_rotation(self):
        with self.Factory() as db:
            for item in db.scalars(select(VocabularyItem)):
                item.jlpt_level_code = "N4"
            db.commit()
        self.set_range("vocabulary", "N4", "N4")
        turn = self.start()
        self.assertEqual(turn["question"]["jlpt_level_code"], "N5")
        self.assertNotEqual(turn["question"]["content_type"], "vocabulary")

    def test_changed_minimum_starts_new_scope_but_legacy_single_scope_resumes(self):
        turn = self.start(category="grammar")
        with self.Factory() as db:
            session = db.get(StudySession, turn["session_id"])
            session.snapshot = {k: v for k, v in session.snapshot.items() if k != "min_levels"}
            db.commit()
        self.assertEqual(self.start(category="grammar")["session_id"], turn["session_id"])
        self.add_range_grammar()
        self.set_range("grammar", "N3", "N3")
        single = self.start(category="grammar")
        self.assertEqual(single["question"]["jlpt_level_code"], "N3")
        self.set_range("grammar", "N4", "N3")
        wider = self.start(category="grammar")
        self.assertNotEqual(single["session_id"], wider["session_id"])
        self.assertEqual(wider["question"]["jlpt_level_code"], "N4")
        with self.Factory() as db:
            self.assertIsNotNone(db.get(StudySession, single["session_id"]).ended_at)

    def test_unreviewed_placeholder_states_obey_discovery_range_and_order(self):
        self.add_range_grammar()
        self.set_range("grammar", "N4", "N2")
        with self.Factory() as db:
            for level in ("N3", "N1"):
                item = db.scalar(select(GrammarItem).where(GrammarItem.jlpt_level_code == level))
                db.add(LearningState(user_id=self.user.id, content_type=ContentType.grammar, content_id=item.id))
            db.commit()
        turn = self.start(category="grammar", planned_items=6)
        levels = []
        for _ in range(6):
            if turn["ended"]:
                break
            levels.append(turn["question"]["jlpt_level_code"])
            self.answer(turn)
            turn = self.next_turn(turn)
        self.assertEqual(levels, ["N4", "N3", "N2"])
        self.assertTrue(self.start(category="grammar", only_due=True)["ended"])

    def save_settings(self, **changes):
        payload = self.client.get("/users/me/settings").json()
        response = self.client.put("/users/me/settings", json={**payload, **changes})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def memory_snapshot(self):
        # Include every persisted field, JSON payload and timestamp, not just a
        # score: changing a range must not silently mutate the scheduler.
        with self.Factory() as db:
            return {
                model.__tablename__: [dict(row) for row in db.execute(
                    select(model.__table__).order_by(model.id)
                ).mappings()]
                for model in (LearningState, ReviewHistory)
            }

    def test_due_reviews_and_explicit_practice_exclude_suspended_levels(self):
        self.add_range_grammar()
        self.set_range("grammar", "N4", "N2")
        with self.Factory() as db:
            for level in ("N1", "N3"):
                item = db.scalar(select(GrammarItem).where(GrammarItem.jlpt_level_code == level))
                db.add(LearningState(user_id=self.user.id, content_type=ContentType.grammar, content_id=item.id,
                                     status=ReviewStatus.review, repetition_count=3, interval_days=12,
                                     last_review_at=NOW-timedelta(days=12), next_review_at=NOW))
            db.commit()
        turn = self.start(category="grammar")
        self.assertEqual(turn["question"]["jlpt_level_code"], "N3")
        self.answer(turn)
        self.assertEqual(self.next_turn(turn)["question"]["jlpt_level_code"], "N4")
        targeted = self.start(category="grammar", content_id=self.grammar.id)
        self.assertTrue(targeted["ended"])
        self.assertIsNone(targeted["question"])
        due = self.client.get("/learning/due").json()
        self.assertNotIn("N1", [item["jlpt_level_code"] for item in due])

    def test_removing_and_restoring_levels_preserves_memory_and_resumes_acquisition(self):
        self.add_range_grammar()
        with self.Factory() as db:
            kanji_id = db.scalar(select(KanjiItem).order_by(KanjiItem.id)).id
        for kind, target in (("vocabulary", self.vocab[0].id), ("kanji", kanji_id), ("grammar", self.grammar.id)):
            with self.subTest(kind=kind):
                self.save_settings(**{f"{kind}_min_level_code": "N5", f"{kind}_level_code": "N4"})
                turn = self.start(category=kind, content_id=target)
                self.answer(turn)
                # Grammar uses FSRS immediately, unlike the two acquisition tracks.
                turn = self.next_turn(turn, seconds=4*3600 if kind == "grammar" else 0)
                if kind == "grammar":
                    turn = self.start(category=kind, content_id=target)
                self.assertIsNotNone(turn["question"])
                pending = turn["question"]
                before = self.memory_snapshot()
                self.save_settings(**{f"{kind}_min_level_code": "N4", f"{kind}_level_code": "N4"})
                self.assertEqual(before, self.memory_snapshot())
                old = self.client.get("/learning/sessions/" + turn["session_id"]).json()
                self.assertTrue(old["ended"])
                self.assertIsNone(old["question"])
                self.assertEqual(old["completed_items"], 0 if kind == "grammar" else 1)
                self.assertIsNone(old["next_due_at"])
                self.assertEqual(old["acquiring_items"], 0)
                self.assertEqual(self.client.post("/learning/questions/" + pending["id"] + "/begin").status_code, 409)
                rejected = self.client.post("/learning/questions/" + pending["id"] + "/answer",
                                            json={"option_id": pending["choices"][0]["id"]})
                self.assertEqual(rejected.status_code, 409)
                self.assertTrue(self.next_turn(turn)["ended"])
                self.assertTrue(self.start(category=kind, content_id=target)["ended"])
                due = self.client.get("/learning/due").json()
                self.assertNotIn(target, [item["content_id"] for item in due])
                with self.Factory() as db:
                    self.assertEqual(build_dashboard(db, self.user.id)["due_reviews"], len(due))
                self.assertEqual(before, self.memory_snapshot())
                self.save_settings(**{f"{kind}_min_level_code": "N5", f"{kind}_level_code": "N4"})
                self.assertIn(target, [item["content_id"] for item in self.client.get("/learning/due").json()])
                restored = self.start(category=kind, content_id=target, show_introduction=True)
                self.assertEqual(restored["question"]["phase"], "question")
                self.assertEqual(restored["question"]["content_id"], target)
                self.assertEqual(before, self.memory_snapshot())
                answer = self.answer(restored)
                if kind != "grammar":
                    self.assertEqual(answer["memory"]["successes"], 2)
                with self.Factory() as db:
                    state = db.scalar(select(LearningState).where(LearningState.content_type == kind, LearningState.content_id == target))
                    self.assertEqual(state.review_revision, 2)

    def test_range_save_preserves_established_and_retained_progress_and_future_due_dates(self):
        with self.Factory() as db:
            db.get(VocabularyItem, self.vocab[1].id).jlpt_level_code = "N4"
            for item in self.vocab[:2]:
                state = LearningState(id=str(uuid4()), user_id=self.user.id, content_type=ContentType.vocabulary, content_id=item.id, status=ReviewStatus.new)
                for _ in range(4):
                    schedule_answer(state, True, state.next_review_at or NOW, 1000)
                db.add(state)
            db.commit()
        self.save_settings(vocabulary_min_level_code="N5", vocabulary_level_code="N4")
        before = self.memory_snapshot()
        with self.Factory() as db:
            learned = build_dashboard(db, self.user.id)["learned_items"]
        self.save_settings(vocabulary_min_level_code="N4", vocabulary_level_code="N4")
        self.assertEqual(before, self.memory_snapshot())
        self.save_settings(vocabulary_min_level_code="N5", vocabulary_level_code="N4")
        self.assertEqual(before, self.memory_snapshot())
        with self.Factory() as db:
            self.assertEqual(build_dashboard(db, self.user.id)["learned_items"], learned)
        turn = self.start(category="vocabulary", content_id=self.vocab[0].id)
        self.assertTrue(turn["ended"])
        self.assertIsNotNone(turn["next_due_at"])
        self.assertEqual(before, self.memory_snapshot())

    def test_unrelated_preferences_do_not_end_a_running_course(self):
        turn = self.start(category="vocabulary")
        self.save_settings(furigana_helper_enabled=True)
        self.save_settings(kanji_min_level_code="N4", kanji_level_code="N4")
        current = self.client.get("/learning/sessions/" + turn["session_id"]).json()
        self.assertFalse(current["ended"])
        self.assertEqual(current["question"]["id"], turn["question"]["id"])
        self.answer(turn)

    def test_legacy_pending_question_outside_scope_is_replaced_without_a_review(self):
        self.add_range_grammar()
        turn = self.start(category="grammar", content_id=self.grammar.id)
        old = turn["question"]
        # A question persisted by the former scheduler may be outside its own
        # snapshot, because due reviews used to bypass the level bounds.
        self.set_range("grammar", "N4", "N2")
        with self.Factory() as db:
            course = db.get(StudySession, turn["session_id"])
            course.snapshot = {**course.snapshot, "content_id": None,
                               "levels": {**course.snapshot["levels"], "grammar": "N2"},
                               "min_levels": {**course.snapshot["min_levels"], "grammar": "N4"}}
            db.commit()
        self.assertEqual(self.client.post("/learning/questions/" + old["id"] + "/begin").status_code, 409)
        self.assertEqual(self.client.post("/learning/questions/" + old["id"] + "/answer",
                                         json={"option_id": old["choices"][0]["id"]}).status_code, 409)
        refreshed = self.client.get("/learning/sessions/" + turn["session_id"]).json()
        self.assertEqual(refreshed["question"]["jlpt_level_code"], "N4")
        self.assertNotEqual(refreshed["question"]["id"], old["id"])
        self.assertEqual(self.memory_snapshot(), {"learning_states": [], "review_history": []})

    def test_five_recalls_then_fsrs_with_no_early_graduation(self):
        turn = self.start(category="vocabulary", content_id=self.vocab[0].id)
        self.assertEqual(turn["planned_items"], 5)
        for count in range(1, 6):
            answer = self.answer(turn)
            self.assertEqual(answer["memory"]["phase"], "acquisition")
            self.assertEqual(answer["memory"]["successes"], count)
            self.assertEqual(answer["memory"]["required_successes"], 5)
            self.assertAlmostEqual(answer["memory"]["value"], count / 5)
            with self.Factory() as db:
                state = db.scalar(select(LearningState))
                self.assertEqual(state.acquisition["successes"], count)
                if count < 5:
                    self.assertIsNone(state.fsrs_card)
                    self.assertIsNone(answer["stability"])
            if count < 5:
                turn = self.next_turn(turn, seconds=0)
                self.assertFalse(turn["ended"])
                self.assertNotIn("retry_at", turn)
                self.assertIsNone(turn["question"]["introduction"])
        expected = self.mock_clock.return_value + timedelta(hours=4)
        self.assertEqual(
            datetime.fromisoformat(answer["next_review_at"].replace("Z", "+00:00")),
            expected,
        )
        ended = self.next_turn(turn, seconds=0)
        self.assertTrue(ended["ended"])
        self.assertEqual(ended["acquired_items"], 1)
        self.assertEqual(ended["acquiring_items"], 0)
        self.assertTrue(
            self.start(category="vocabulary", content_id=self.vocab[0].id)["ended"]
        )
        with self.Factory() as db:
            histories = list(
                db.scalars(select(ReviewHistory).order_by(ReviewHistory.created_at))
            )
            self.assertEqual(len(histories), 5)
            self.assertEqual(
                sum(h.payload["scheduler"] == "fsrs6" for h in histories), 1
            )
            self.assertEqual(
                Card.from_dict(db.scalar(select(LearningState)).fsrs_card).state,
                State.Learning,
            )
        self.mock_clock.return_value = expected
        review = self.start(category="vocabulary", content_id=self.vocab[0].id)
        answer = self.answer(review)
        self.assertEqual(answer["memory"]["phase"], "consolidation")
        self.assertTrue(self.next_turn(review)["ended"])

    def test_cohort_repeats_with_two_intervening_answers(self):
        turn = self.start(category="vocabulary")
        seen = []
        for index in range(15):
            self.assertFalse(turn["ended"])
            self.assertNotIn("retry_at", turn)
            item_id = turn["question"]["content_id"]
            if item_id in seen:
                previous = max(i for i, value in enumerate(seen) if value == item_id)
                self.assertGreaterEqual(index - previous, 3)
            seen.append(item_id)
            self.answer(turn)
            turn = self.next_turn(turn, seconds=0)
        self.assertTrue(turn["ended"])
        self.assertEqual(len(set(seen)), 3)
        self.assertEqual({seen.count(item) for item in set(seen)}, {5})
        self.assertEqual(turn["acquired_items"], 3)
        with self.Factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(LearningState)), 3
            )

    def test_initial_error_resets_progress_and_reserves_more_questions(self):
        turn = self.start(category="vocabulary", content_id=self.vocab[0].id)
        self.answer(turn)
        turn = self.next_turn(turn, seconds=0)
        self.assertEqual(self.answer(turn)["memory"]["successes"], 2)
        turn = self.next_turn(turn, seconds=0)
        answer = self.answer(turn, False)
        self.assertEqual(answer["memory"]["value"], 0)
        self.assertEqual(answer["planned_items"], 8)
        with self.Factory() as db:
            state = db.scalar(select(LearningState))
            self.assertEqual(state.acquisition["successes"], 0)
            self.assertIsNone(state.fsrs_card)
        for count in range(1, 6):
            turn = self.next_turn(turn, seconds=0)
            self.assertEqual(self.answer(turn)["memory"]["successes"], count)
        self.assertTrue(self.next_turn(turn)["ended"])

    def test_initial_progress_survives_a_different_session(self):
        first = self.start(category="vocabulary", content_id=self.vocab[0].id)
        self.answer(first)
        self.start(category="grammar")
        resumed = self.start(category="vocabulary", content_id=self.vocab[0].id)
        self.assertNotEqual(first["session_id"], resumed["session_id"])
        self.assertEqual(resumed["planned_items"], 4)
        self.assertEqual(resumed["question"]["phase"], "question")
        self.assertEqual(self.answer(resumed)["memory"]["successes"], 2)

    def test_existing_active_initial_word_resumes_without_changing_its_due_date(self):
        from app.models.learning import StudySession
        from app.schemas.quiz import AnswerOut

        turn = self.start(category="vocabulary", content_id=self.vocab[0].id)
        with self.Factory() as db:
            question = db.get(StudyQuestion, turn["question"]["id"])
            state = LearningState(
                user_id=self.user.id,
                content_type=ContentType.vocabulary,
                content_id=self.vocab[0].id,
            )
            db.add(state)
            db.flush()
            scheduled = schedule_answer(state, True, NOW, 1000)
            state.last_session_id = turn["session_id"]
            due = state.next_review_at
            old_session = db.get(StudySession, turn["session_id"])
            old_session.completed_items = old_session.planned_items = 1
            question.answered_at = NOW
            question.selected_option_id = question.correct_option_id
            question.result = AnswerOut(
                question_id=question.id,
                selected_option_id=question.correct_option_id,
                correct_option_id=question.correct_option_id,
                correct=True,
                **question.feedback,
                status=state.status,
                next_review_at=due,
                difficulty=scheduled["difficulty"],
                stability=scheduled["stability"],
                retrievability=scheduled["retrievability"],
            ).model_dump(mode="json")
            db.commit()
        resumed = self.client.get("/learning/sessions/" + turn["session_id"]).json()
        self.assertEqual(resumed["planned_items"], 5)
        self.assertEqual(resumed["question"]["result"]["memory"]["successes"], 1)
        with self.Factory() as db:
            self.assertEqual(utc(db.scalar(select(LearningState)).next_review_at), due)
        repeated = self.next_turn(turn, seconds=0)
        self.assertEqual(repeated["question"]["content_id"], self.vocab[0].id)
        answer = self.answer(repeated)
        self.assertEqual(answer["memory"]["successes"], 2)
        self.assertIsNone(answer["stability"])

    def test_kanji_uses_initial_recall_and_grammar_keeps_application_review(self):
        kanji = self.start(category="kanji")
        result = self.answer(kanji)
        self.assertEqual(result["memory"]["phase"], "acquisition")
        self.assertEqual(result["memory"]["required_successes"], 5)
        grammar = self.start(category="grammar")
        result = self.answer(grammar)
        self.assertEqual(result["memory"]["phase"], "consolidation")
        self.assertEqual(
            datetime.fromisoformat(result["next_review_at"].replace("Z", "+00:00")),
            NOW + timedelta(hours=4),
        )

    def test_mixed_session_still_includes_grammar_and_finishes_initial_words(self):
        turn = self.start()
        kinds = []
        for index in range(15):
            self.assertIsNotNone(turn["question"])
            kinds.append(turn["question"]["content_type"])
            self.answer(turn)
            turn = self.next_turn(turn)
            if turn["ended"]:
                break
            self.assertNotIn("retry_at", turn)
        self.assertTrue(turn["ended"])
        self.assertEqual(set(kinds), {"grammar", "kanji", "vocabulary"})
        self.assertEqual(turn["acquiring_items"], 0)

    def test_introduction_before_quiz_persists_without_scheduling(self):
        turn = self.start(
            show_introduction=True, category="vocabulary", content_id=self.vocab[0].id
        )
        question = turn["question"]
        self.assertEqual(question["phase"], "introduction")
        self.assertEqual(question["introduction"]["meaning"], "chien")
        self.assertEqual(
            question["introduction"]["example"]["translation"], "Il y a un chien."
        )
        self.assertEqual(question["choices"], [])
        self.assertNotIn("correct_option_id", question)
        self.assertEqual(turn["completed_items"], 0)
        self.assertEqual(
            turn, self.client.get("/learning/sessions/" + turn["session_id"]).json()
        )
        with self.Factory() as db:
            choice = db.get(StudyQuestion, question["id"]).correct_option_id
        blocked = self.client.post(
            "/learning/questions/" + question["id"] + "/answer",
            json={"option_id": choice},
        )
        self.assertEqual(blocked.status_code, 409)
        with self.Factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(LearningState)), 0
            )
            self.assertEqual(
                db.scalar(select(func.count()).select_from(ReviewHistory)), 0
            )

    def test_begin_is_idempotent_and_reading_time_is_excluded(self):
        turn = self.start(
            show_introduction=True, category="vocabulary", content_id=self.vocab[0].id
        )
        url = "/learning/questions/" + turn["question"]["id"] + "/begin"
        self.mock_clock.return_value = NOW + timedelta(minutes=5)
        ready = self.client.post(url).json()
        self.assertEqual(ready["phase"], "question")
        self.assertIsNone(ready["introduction"])
        self.assertEqual(len(ready["choices"]), 4)
        self.mock_clock.return_value += timedelta(seconds=2)
        self.assertEqual(ready, self.client.post(url).json())
        resumed = self.client.get("/learning/sessions/" + turn["session_id"]).json()
        self.assertEqual(resumed["question"], ready)
        self.assertEqual(resumed["completed_items"], 0)
        with self.Factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(LearningState)), 0
            )
        self.answer(resumed)
        with self.Factory() as db:
            self.assertEqual(db.scalar(select(ReviewHistory)).response_time_ms, 2000)
        self.mock_clock.return_value += timedelta(hours=4)
        reviewed = self.start(
            show_introduction=True, category="vocabulary", content_id=self.vocab[0].id
        )
        # Advance the saved feedback before resuming the next recall.
        if reviewed["question"] and reviewed["question"].get("result"):
            self.client.post("/learning/sessions/" + reviewed["session_id"] + "/next")
            reviewed = self.start(
                show_introduction=True,
                category="vocabulary",
                content_id=self.vocab[0].id,
            )
        self.assertEqual(reviewed["question"]["phase"], "question")
        self.assertIsNone(reviewed["question"]["introduction"])

    def test_preexisting_unanswered_new_word_gets_introduction(self):
        turn = self.start(show_introduction=True, category="vocabulary")
        with self.Factory() as db:
            question = db.get(StudyQuestion, turn["question"]["id"])
            question.prompt = {
                key: value
                for key, value in question.prompt.items()
                if key != "requires_introduction"
            }
            db.commit()
        resumed = self.client.get("/learning/sessions/" + turn["session_id"]).json()
        self.assertEqual(resumed["question"]["phase"], "introduction")
        self.assertEqual(resumed["question"]["choices"], [])

    def test_begin_checks_owner_and_expiration(self):
        turn = self.start(show_introduction=True, category="vocabulary")
        url = "/learning/questions/" + turn["question"]["id"] + "/begin"
        self.auth_id = self.other.id
        self.assertEqual(self.client.post(url).status_code, 404)
        self.auth_id = self.user.id
        self.mock_clock.return_value = NOW + timedelta(days=1)
        self.assertEqual(self.client.post(url).status_code, 409)

    def test_question_private_stable_start_idempotent(self):
        turn = self.start(category="vocabulary")
        q = turn["question"]
        self.assertEqual(len(q["choices"]), 4)
        self.assertEqual(q["locale"], "fr")
        self.assertNotIn("correct_option_id", q)
        self.assertNotIn("feedback", q)
        self.assertEqual(turn, self.start(category="vocabulary"))
        self.assertEqual(
            turn, self.client.get("/learning/sessions/" + turn["session_id"]).json()
        )
        self.assertEqual(
            turn,
            self.client.post(
                "/learning/sessions/" + turn["session_id"] + "/next"
            ).json(),
        )
        with self.Factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(LearningState)), 0
            )
            self.assertEqual(
                db.scalar(select(func.count()).select_from(StudyQuestion)), 1
            )

    def test_first_choice_final_retries_idempotent(self):
        turn = self.start(category="vocabulary", content_id=self.vocab[0].id)
        result = self.answer(turn, False)
        self.assertFalse(result["correct"])
        self.assertEqual(
            datetime.fromisoformat(result["next_review_at"].replace("Z", "+00:00")),
            NOW,
        )
        self.assertEqual(result["example"]["translation"], "Il y a un chien.")
        url = "/learning/questions/" + turn["question"]["id"] + "/answer"
        self.assertEqual(
            self.client.post(
                url, json={"option_id": result["selected_option_id"]}
            ).json(),
            result,
        )
        self.assertEqual(
            self.client.post(
                url, json={"option_id": result["correct_option_id"]}
            ).status_code,
            409,
        )
        loaded = self.client.get("/learning/sessions/" + turn["session_id"]).json()
        self.assertEqual(loaded["question"]["result"], result)
        self.assertEqual(loaded["completed_items"], 1)
        with self.Factory() as db:
            history = db.scalar(select(ReviewHistory))
            self.assertEqual(history.rating, 1)
            self.assertEqual(history.payload["option_id"], result["selected_option_id"])
            self.assertEqual(
                db.scalar(select(func.count()).select_from(ReviewHistory)), 1
            )
            self.assertEqual(db.scalar(select(LearningState)).review_revision, 1)

    def test_single_item_continues_immediately_after_error_and_reload(self):
        turn = self.start(category="vocabulary", content_id=self.vocab[0].id)
        self.answer(turn, False)
        repeated = self.next_turn(turn, seconds=0)
        self.assertFalse(repeated["ended"])
        self.assertNotIn("retry_at", repeated)
        self.assertEqual(
            repeated, self.client.get("/learning/sessions/" + turn["session_id"]).json()
        )
        self.assertEqual(
            repeated, self.start(category="vocabulary", content_id=self.vocab[0].id)
        )
        self.assertEqual(repeated["question"]["content_id"], self.vocab[0].id)
        self.assertNotEqual(repeated["question"]["id"], turn["question"]["id"])
        self.assertEqual(repeated["question"]["phase"], "question")
        self.assertEqual(self.answer(repeated)["memory"]["successes"], 1)

    def test_two_pending_items_alternate_without_waiting_or_new_items(self):
        with self.Factory() as db:
            for item in self.vocab[:2]:
                db.add(
                    LearningState(
                        user_id=self.user.id,
                        content_type=ContentType.vocabulary,
                        content_id=item.id,
                        status=ReviewStatus.learning,
                        acquisition={"successes": 0, "position": 0},
                        last_review_at=NOW,
                        next_review_at=NOW,
                    )
                )
            db.commit()
        turn = self.start(category="vocabulary", only_due=True)
        seen = []
        for _ in range(10):
            self.assertFalse(turn["ended"])
            self.assertIsNotNone(turn["question"])
            self.assertNotIn("retry_at", turn)
            item = turn["question"]["content_id"]
            if seen:
                self.assertNotEqual(seen[-1], item)
            seen.append(item)
            self.answer(turn)
            turn = self.next_turn(turn, seconds=0)
        self.assertTrue(turn["ended"])
        self.assertEqual(set(seen), {item.id for item in self.vocab[:2]})
        self.assertEqual({seen.count(item) for item in seen}, {5})
        self.assertEqual(turn["acquired_items"], 2)

    def test_error_on_last_word_finishes_without_pause_or_extra_new_words(self):
        turn = self.start(category="vocabulary")
        seen = []
        for index in range(20):
            self.assertFalse(turn["ended"])
            self.assertIsNotNone(turn["question"])
            self.assertNotIn("retry_at", turn)
            seen.append(turn["question"]["content_id"])
            self.answer(turn, correct=index != 14)
            turn = self.next_turn(turn, seconds=0)
        self.assertTrue(turn["ended"])
        self.assertEqual(len(set(seen)), 3)
        self.assertEqual(turn["acquired_items"], 3)
        self.assertEqual(turn["acquiring_items"], 0)
        self.assertEqual(turn["planned_items"], 20)

    def test_previously_paused_session_resumes_without_waiting_or_double_review(self):
        turn = self.start(category="vocabulary", content_id=self.vocab[0].id)
        for index, method in enumerate(("get", "start"), start=1):
            with self.subTest(method=method):
                self.answer(turn)
                previous_question = turn["question"]["id"]
                with self.Factory() as db:
                    saved = db.get(StudySession, turn["session_id"])
                    saved.snapshot = {
                        **saved.snapshot,
                        "retry_at": (NOW + timedelta(seconds=60)).isoformat(),
                    }
                    db.commit()
                turn = (
                    self.client.get("/learning/sessions/" + turn["session_id"]).json()
                    if method == "get"
                    else self.start(category="vocabulary", content_id=self.vocab[0].id)
                )
                self.assertFalse(turn["ended"])
                self.assertNotIn("retry_at", turn)
                self.assertEqual(turn["question"]["content_id"], self.vocab[0].id)
                self.assertNotEqual(turn["question"]["id"], previous_question)
                self.assertEqual(turn["question"]["phase"], "question")
                self.assertEqual(
                    turn,
                    self.client.get("/learning/sessions/" + turn["session_id"]).json(),
                )
                with self.Factory() as db:
                    self.assertNotIn(
                        "retry_at", db.get(StudySession, turn["session_id"]).snapshot
                    )
                    self.assertEqual(
                        db.scalar(select(LearningState)).review_revision, index
                    )
                    self.assertEqual(
                        db.scalar(select(func.count()).select_from(ReviewHistory)),
                        index,
                    )

    def test_next_new_card_is_different(self):
        turn = self.start(category="vocabulary")
        self.answer(turn)
        self.mock_clock.return_value = NOW + timedelta(seconds=5)
        next_turn = self.client.post(
            "/learning/sessions/" + turn["session_id"] + "/next"
        ).json()
        self.assertNotEqual(
            next_turn["question"]["content_id"], turn["question"]["content_id"]
        )
        self.assertEqual(next_turn["completed_items"], 1)

    def test_reject_browser_ratings_unknown_options_and_legacy(self):
        turn = self.start(category="kanji")
        url = "/learning/questions/" + turn["question"]["id"] + "/answer"
        self.assertEqual(
            self.client.post(
                url,
                json={
                    "option_id": turn["question"]["choices"][0]["id"],
                    "correct": True,
                },
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.post(url, json={"option_id": str(uuid4())}).status_code, 422
        )
        self.assertEqual(
            self.client.post(
                "/learning/reviews", json={"correct": True, "rating": 5}
            ).status_code,
            410,
        )
        self.assertEqual(
            self.client.post("/learning/sessions", json={"snapshot": {}}).status_code,
            422,
        )
        self.assertEqual(
            self.client.post(
                "/learning/sessions", json={"content_id": self.vocab[0].id}
            ).status_code,
            422,
        )

    def test_owner_checks(self):
        turn = self.start(category="vocabulary")
        self.auth_id = self.other.id
        self.assertEqual(
            self.client.get("/learning/sessions/" + turn["session_id"]).status_code, 404
        )
        self.assertEqual(
            self.client.post(
                "/learning/sessions/" + turn["session_id"] + "/next"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/learning/questions/" + turn["question"]["id"] + "/answer",
                json={"option_id": turn["question"]["choices"][0]["id"]},
            ).status_code,
            404,
        )

    def test_expiration_replacement(self):
        turn = self.start(category="vocabulary")
        self.mock_clock.return_value = NOW + timedelta(days=1)
        self.assertEqual(
            self.client.post(
                "/learning/questions/" + turn["question"]["id"] + "/answer",
                json={"option_id": turn["question"]["choices"][0]["id"]},
            ).status_code,
            409,
        )
        replacement = self.client.post(
            "/learning/sessions/" + turn["session_id"] + "/next"
        ).json()
        self.assertNotEqual(replacement["question"]["id"], turn["question"]["id"])
        self.assertEqual(replacement["completed_items"], 0)

    def test_cross_session_stale_answer(self):
        turn = self.start(category="vocabulary")
        self.start(category="kanji")
        self.assertEqual(
            self.client.post(
                "/learning/questions/" + turn["question"]["id"] + "/answer",
                json={"option_id": turn["question"]["choices"][0]["id"]},
            ).status_code,
            409,
        )

    def test_revision_conflict(self):
        turn = self.start(category="vocabulary")
        with self.Factory() as db:
            db.add(
                LearningState(
                    user_id=self.user.id,
                    content_type=ContentType.vocabulary,
                    content_id=turn["question"]["content_id"],
                    review_revision=1,
                    next_review_at=NOW + timedelta(days=1),
                )
            )
            db.commit()
        self.assertEqual(
            self.client.post(
                "/learning/questions/" + turn["question"]["id"] + "/answer",
                json={"option_id": turn["question"]["choices"][0]["id"]},
            ).status_code,
            409,
        )
        with self.Factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(ReviewHistory)), 0
            )

    def test_grammar_application_unavailable_content(self):
        turn = self.start(category="grammar")
        q = turn["question"]
        self.assertEqual(q["kind"], "cloze")
        self.assertIn("___", q["title"])
        self.assertNotEqual(q["title"], self.grammar.title)
        self.assertEqual(q["context"], "Est-ce un livre ?")
        self.assertEqual(turn["grammar_points_available"], 1)
        self.assertEqual(self.answer(turn)["example"]["text"], "これは本ですか。")
        empty = self.start(category="grammar", content_id=self.unavailable.id)
        self.assertTrue(empty["ended"])
        self.assertIsNone(empty["question"])
        with self.Factory() as db:
            self.assertIsNone(
                db.scalar(
                    select(LearningState).where(
                        LearningState.content_id == self.unavailable.id
                    )
                )
            )

    def test_english_choices_feedback(self):
        with self.Factory() as db:
            db.get(User, self.user.id).settings.content_locale = "en"
            db.commit()
        turn = self.start(category="vocabulary", content_id=self.vocab[0].id)
        self.assertIn("dog", {c["label"] for c in turn["question"]["choices"]})
        self.assertEqual(self.answer(turn)["example"]["translation"], "There is a dog.")

    def test_due_only_legacy_dates_preserved(self):
        with self.Factory() as db:
            s = LearningState(
                user_id=self.user.id,
                content_type=ContentType.vocabulary,
                content_id=self.vocab[0].id,
                status=ReviewStatus.known,
                next_review_at=NOW - timedelta(days=1),
                last_review_at=NOW - timedelta(days=8),
                interval_days=7,
                repetition_count=3,
            )
            db.add(s)
            db.commit()
        turn = self.start(only_due=True)
        self.assertEqual(turn["question"]["content_id"], self.vocab[0].id)
        with self.Factory() as db:
            state = db.get(LearningState, s.id)
            self.assertIsNone(state.fsrs_card)
            self.assertEqual(utc(state.next_review_at), NOW - timedelta(days=1))
        self.answer(turn)
        with self.Factory() as db:
            self.assertEqual(db.get(LearningState, s.id).scheduler_version, "fsrs6")

    def test_missing_translation_no_english_fallback(self):
        with self.Factory() as db:
            item = db.get(VocabularyItem, self.vocab[0].id)
            item.translations.clear()
            db.commit()
        turn = self.start(category="vocabulary", content_id=self.vocab[0].id)
        self.assertTrue(turn["ended"])
        self.assertIsNone(turn["question"])


if __name__ == "__main__":
    unittest.main()
