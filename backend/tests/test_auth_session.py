"""Refresh rotation and lesson recovery with real cookie authentication."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models
from app.core.database import get_db, engine as configured_engine
from app.core.security import create_token, hash_password, hash_token
from app.models.base import Base
from app.models.content import JLPTLevel
from app.models.lesson import Lesson, LessonProgress
from app.models.user import RefreshToken, User
from app.routers import auth, lessons
from app.services.auth_service import get_user_settings, issue_tokens


class AuthSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = hash_password("session-test-password")

    def make_engine(self):
        return create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    def setUp(self):
        self.engine = self.make_engine()
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.Factory = sessionmaker(self.engine, expire_on_commit=False)
        with self.Factory() as db:
            db.add(JLPTLevel(code="N5", rank=1, label="N5"))
            self.user = User(email="session@example.com", full_name="Session", hashed_password=self.password_hash)
            db.add(self.user)
            db.flush()
            get_user_settings(db, self.user.id)
            self.access, self.refresh = issue_tokens(db, self.user)
            db.add(Lesson(id="auth-lesson", level="N5", position=1, version="v1", content={
                "unit_id": "test", "unit_title": "Test", "title": "Test", "goal": "Test", "minutes": 5,
                "vocabulary_ids": [], "grammar_ids": [], "kanji_ids": [], "steps": [
                    {"id": "read", "kind": "read", "title": "Read"},
                    {"id": "recall", "kind": "recall", "title": "Recall", "accepted": ["ねこ", "neko"], "solution": "ねこ"},
                ],
            }))
            db.commit()
        self.app = FastAPI()
        self.app.include_router(auth.router)
        self.app.include_router(lessons.router)
        def database():
            with self.Factory() as db:
                yield db
        self.app.dependency_overrides[get_db] = database
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.set_cookies(self.access, self.refresh)

    def set_cookies(self, access, refresh):
        self.client.cookies.clear()
        self.client.cookies.set("access_token", access)
        self.client.cookies.set("refresh_token", refresh)

    def test_expired_access_refreshes_and_preserves_lesson(self):
        command = {"action": "continue", "step_id": "read", "revision": 0}
        self.assertEqual(self.client.post("/lessons/auth-lesson/progress", json=command).status_code, 200)
        expired = create_token({"sub": self.user.id}, timedelta(seconds=-1), "access")
        self.set_cookies(expired, self.refresh)
        command = {"action": "answer", "step_id": "recall", "revision": 1, "answer": "ねこ"}
        self.assertEqual(self.client.post("/lessons/auth-lesson/progress", json=command).status_code, 401)
        with self.Factory() as db:
            saved = db.get(LessonProgress, (self.user.id, "auth-lesson"))
            self.assertEqual((saved.cursor, saved.revision, saved.answers), (1, 1, {}))
        renewed = self.client.post("/auth/refresh")
        self.assertEqual(renewed.status_code, 200, renewed.text)
        self.assertEqual(self.client.get("/auth/session").status_code, 200)
        answer = self.client.post("/lessons/auth-lesson/progress", json=command)
        self.assertEqual(answer.status_code, 200, answer.text)
        self.assertTrue(answer.json()["feedback"]["correct"])
        self.assertEqual(self.client.post("/lessons/auth-lesson/progress", json=command).json(), answer.json())
        self.assertEqual(self.client.get("/lessons/auth-lesson").json(), answer.json())
        self.client.cookies.clear()
        login = self.client.post("/auth/login", json={"email": self.user.email, "password": "session-test-password"})
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(self.client.get("/lessons/auth-lesson").json(), answer.json())

    def test_refresh_rotates_once_and_revoked_cookie_cannot_replay(self):
        result = self.client.post("/auth/refresh")
        self.assertEqual(result.status_code, 200, result.text)
        cookies = result.headers.get_list("set-cookie")
        self.assertTrue(all("HttpOnly" in c and "SameSite=lax" in c for c in cookies))
        with self.Factory() as db:
            tokens = list(db.scalars(select(RefreshToken)))
            self.assertEqual(len(tokens), 2)
            self.assertEqual(sum(t.revoked_at is None for t in tokens), 1)
        self.set_cookies(self.access, self.refresh)
        self.assertEqual(self.client.post("/auth/refresh").status_code, 401)

    def test_invalid_expired_wrong_type_and_missing_refresh_are_401(self):
        for value in ("not-a-jwt", create_token({"sub": self.user.id}, timedelta(seconds=-1), "refresh"), self.access):
            self.set_cookies(self.access, value)
            self.assertEqual(self.client.post("/auth/refresh").status_code, 401)
        self.client.cookies.clear()
        self.assertEqual(self.client.post("/auth/refresh").status_code, 401)

    def test_failed_replacement_does_not_consume_refresh(self):
        with patch("app.routers.auth.issue_tokens", side_effect=RuntimeError("database failure")):
            self.assertEqual(self.client.post("/auth/refresh").status_code, 500)
        with self.Factory() as db:
            old = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(self.refresh)))
            self.assertIsNone(old.revoked_at)
        self.assertEqual(self.client.post("/auth/refresh").status_code, 200)

    def test_disabled_account_cannot_refresh(self):
        with self.Factory.begin() as db:
            db.get(User, self.user.id).is_active = False
        self.assertEqual(self.client.post("/auth/refresh").status_code, 401)

    def test_logout_revokes_and_clears_same_cookie_domain(self):
        with patch.object(auth.settings, "cookie_domain", "example.com"):
            result = self.client.post("/auth/logout")
        self.assertEqual(result.status_code, 200)
        self.assertTrue(all("Domain=example.com" in c and "Max-Age=0" in c for c in result.headers.get_list("set-cookie")))
        self.set_cookies(self.access, self.refresh)
        self.assertEqual(self.client.post("/auth/refresh").status_code, 401)


@unittest.skipUnless(os.getenv("AUTH_TEST_POSTGRES") == "1", "Opt-in isolated PostgreSQL tests")
class PostgresAuthSessionTests(AuthSessionTests):
    def make_engine(self):
        schema = "auth_test_" + uuid4().hex
        admin = create_engine(configured_engine.url)
        with admin.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA {schema}"))
        def cleanup():
            with admin.begin() as conn:
                conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            admin.dispose()
        self.addCleanup(cleanup)
        return create_engine(configured_engine.url, connect_args={"options": f"-csearch_path={schema}"})

    def test_concurrent_refresh_cannot_issue_two_successors(self):
        barrier = Barrier(2)
        def refresh(_):
            with TestClient(self.app, raise_server_exceptions=False) as client:
                client.cookies.set("refresh_token", self.refresh)
                barrier.wait(timeout=10)
                return client.post("/auth/refresh").status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(refresh, range(2))), [200, 401])
        with self.Factory() as db:
            tokens = list(db.scalars(select(RefreshToken)))
            self.assertEqual(len(tokens), 2)
            self.assertEqual(sum(t.revoked_at is None for t in tokens), 1)
