"""Run with QUIZ_TEST_POSTGRES=1. Only temporary schemas are created/dropped."""

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import create_engine, select, func, text
from app.core.database import engine as configured_engine
from app.models.learning import StudyQuestion, ReviewHistory, LearningState
from app.schemas.quiz import QuizStartIn
from app.services.quiz_service import answer_question, begin_question, start_session
import test_quiz


@unittest.skipUnless(
    os.getenv("QUIZ_TEST_POSTGRES") == "1",
    "Opt-in isolated PostgreSQL integration tests",
)
class PostgresQuizTests(test_quiz.QuizAPITests):
    def make_engine(self):
        schema = "quiz_test_" + uuid4().hex
        admin = create_engine(configured_engine.url)
        with admin.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA {schema}"))

        def cleanup():
            with admin.begin() as conn:
                conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            admin.dispose()

        self.addCleanup(cleanup)
        return create_engine(
            configured_engine.url, connect_args={"options": f"-csearch_path={schema}"}
        )

    def test_concurrent_identical_answers_count_once(self):
        turn = self.start(category="vocabulary")
        with self.Factory() as db:
            q = db.get(StudyQuestion, turn["question"]["id"])
            choice = q.correct_option_id
        barrier = Barrier(2)

        def worker():
            with self.Factory() as db:
                barrier.wait(timeout=10)
                return answer_question(db, self.user.id, q.id, choice).model_dump(
                    mode="json"
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
        self.assertEqual(results[0], results[1])
        with self.Factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(ReviewHistory)), 1
            )
            self.assertEqual(db.scalar(select(LearningState)).review_revision, 1)

    def test_concurrent_fifth_answer_graduates_exactly_once(self):
        from datetime import timedelta
        from app.models.learning import StudySession
        from app.utils.enums import ContentType, ReviewStatus

        turn = self.start(category="vocabulary")
        with self.Factory() as db:
            question = db.get(StudyQuestion, turn["question"]["id"])
            question.baseline_revision = 4
            db.add(
                LearningState(
                    user_id=self.user.id,
                    content_type=ContentType.vocabulary,
                    content_id=question.content_id,
                    status=ReviewStatus.learning,
                    acquisition={"successes": 4, "position": 4},
                    review_revision=4,
                    last_session_id=turn["session_id"],
                    last_review_at=test_quiz.NOW - timedelta(seconds=60),
                    consecutive_correct=4,
                    repetition_count=4,
                )
            )
            db.get(StudySession, turn["session_id"]).completed_items = 4
            db.commit()
            choice = question.correct_option_id
        barrier = Barrier(2)

        def worker():
            with self.Factory() as db:
                barrier.wait(timeout=10)
                return answer_question(
                    db, self.user.id, question.id, choice
                ).model_dump(mode="json")

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0]["memory"]["value"], 1)
        with self.Factory() as db:
            state = db.scalar(select(LearningState))
            self.assertEqual(state.acquisition["successes"], 5)
            self.assertEqual(state.review_revision, 5)
            self.assertEqual(
                db.scalar(select(func.count()).select_from(ReviewHistory)), 1
            )

    def test_concurrent_different_answers_first_wins(self):
        turn = self.start(category="vocabulary")
        with self.Factory() as db:
            q = db.get(StudyQuestion, turn["question"]["id"])
            choices = [o["id"] for o in q.choices[:2]]
        barrier = Barrier(2)

        def worker(choice):
            with self.Factory() as db:
                barrier.wait(timeout=10)
                try:
                    answer_question(db, self.user.id, q.id, choice)
                    return 200
                except HTTPException as exc:
                    return exc.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, choices))
        self.assertEqual(sorted(results), [200, 409])
        with self.Factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(ReviewHistory)), 1
            )

    def test_concurrent_begin_preserves_question_and_does_not_review(self):
        turn = self.start(show_introduction=True, category="vocabulary")
        barrier = Barrier(2)

        def worker():
            with self.Factory() as db:
                barrier.wait(timeout=10)
                return begin_question(
                    db, self.user.id, turn["question"]["id"]
                ).model_dump(mode="json")

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0]["phase"], "question")
        with self.Factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(ReviewHistory)), 0
            )
            self.assertEqual(
                db.scalar(select(func.count()).select_from(LearningState)), 0
            )

    def test_concurrent_start_resumes_one_question(self):
        barrier = Barrier(2)

        def worker():
            with self.Factory() as db:
                barrier.wait(timeout=10)
                return start_session(
                    db, self.user.id, QuizStartIn(category="vocabulary")
                ).session_id

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
        self.assertEqual(results[0], results[1])
        with self.Factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(StudyQuestion)), 1
            )


@unittest.skipUnless(
    os.getenv("QUIZ_TEST_POSTGRES") == "1", "Opt-in isolated PostgreSQL migration test"
)
class PostgresMigrationTests(unittest.TestCase):
    def test_acquisition_migration_preserves_legacy_dates(self):
        import importlib.util
        from pathlib import Path
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        engine = PostgresQuizTests.make_engine(self)
        self.addCleanup(engine.dispose)
        path = (
            Path(__file__).resolve().parents[1]
            / "alembic/versions/0004_initial_acquisition.py"
        )
        spec = importlib.util.spec_from_file_location("acquisition_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE learning_states (id VARCHAR PRIMARY KEY, next_review_at TIMESTAMPTZ, last_review_at TIMESTAMPTZ)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO learning_states VALUES ('legacy','2026-09-10T12:00:00Z','2026-09-03T12:00:00Z')"
                )
            )
            before = conn.execute(
                text("SELECT id,next_review_at,last_review_at FROM learning_states")
            ).all()
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
            self.assertEqual(
                conn.execute(
                    text("SELECT id,next_review_at,last_review_at FROM learning_states")
                ).all(),
                before,
            )
            self.assertIsNone(
                conn.scalar(text("SELECT acquisition FROM learning_states"))
            )

    def test_additive_migration_preserves_legacy_schedule(self):
        import importlib.util
        from pathlib import Path
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        engine = PostgresQuizTests.make_engine(self)
        self.addCleanup(engine.dispose)
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "alembic/versions/0003_fsrs_questions.py"
        )
        spec = importlib.util.spec_from_file_location("fsrs_migration", migration_path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with engine.begin() as conn:
            conn.execute(
                text("CREATE TYPE review_status AS ENUM ('new', 'learning', 'known')")
            )
            for table in ("users", "study_sessions", "grammar_items"):
                conn.execute(text(f"CREATE TABLE {table} (id VARCHAR PRIMARY KEY)"))
            conn.execute(
                text(
                    "CREATE TABLE learning_states (id VARCHAR PRIMARY KEY, status review_status, next_review_at TIMESTAMPTZ, last_review_at TIMESTAMPTZ, interval_days INTEGER)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO learning_states VALUES ('legacy','known','2026-09-10T12:00:00Z','2026-09-03T12:00:00Z',7)"
                )
            )
            columns = "id,status::text,next_review_at,last_review_at,interval_days"
            before = conn.execute(text(f"SELECT {columns} FROM learning_states")).all()
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
            self.assertEqual(
                conn.execute(text(f"SELECT {columns} FROM learning_states")).all(),
                before,
            )
            row = conn.execute(
                text(
                    "SELECT scheduler_version,fsrs_card,review_revision,recent_results FROM learning_states"
                )
            ).one()
            self.assertEqual(tuple(row), (None, None, 0, []))
        # New enum values become usable only after the migration transaction commits.
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE learning_states SET status='relearning' WHERE id='legacy'")
            )
