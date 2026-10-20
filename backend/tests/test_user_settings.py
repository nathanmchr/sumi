"""Preference persistence and session serialization in an isolated PostgreSQL schema."""
import os
import unittest
from uuid import uuid4

from pydantic import ValidationError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.database import engine as configured_engine, get_db
from app.core.dependencies import get_current_user
from app.models.base import Base
from app.models.content import JLPTLevel
from app.models.user import User
from app.routers import auth, users
from app.schemas.user import UserSettingsUpdate


class SettingsContractTests(unittest.TestCase):
    def test_helper_is_opt_in_for_existing_clients(self):
        payload = UserSettingsUpdate(vocabulary_level_code='N5', grammar_level_code='N5', kanji_level_code='N5')
        self.assertFalse(payload.furigana_helper_enabled)
        self.assertFalse(payload.romaji_enabled)


    def test_legacy_single_level_payload_resolves_both_bounds(self):
        payload = UserSettingsUpdate(vocabulary_level_code='N2', grammar_level_code='N3', kanji_level_code='N1')
        self.assertEqual(payload.vocabulary_min_level_code, 'N2')
        self.assertEqual(payload.grammar_min_level_code, 'N3')
        self.assertEqual(payload.kanji_min_level_code, 'N1')

    def test_all_ordered_ranges_and_invalid_bounds(self):
        base = dict(vocabulary_level_code='N5', grammar_level_code='N5', kanji_level_code='N5')
        for category in ('vocabulary', 'grammar', 'kanji'):
            for lower in range(1, 6):
                for upper in range(1, 6):
                    fields = {**base, f'{category}_min_level_code': f'N{lower}', f'{category}_level_code': f'N{upper}'}
                    if lower >= upper:
                        UserSettingsUpdate(**fields)
                    else:
                        with self.assertRaises(ValidationError):
                            UserSettingsUpdate(**fields)
            for invalid in ('N0', 'N6', 'bad', ''):
                with self.assertRaises(ValidationError):
                    UserSettingsUpdate(**{**base, f'{category}_min_level_code': invalid})


@unittest.skipUnless(os.getenv('SETTINGS_TEST_POSTGRES') == '1', 'Opt-in isolated PostgreSQL tests')
class SettingsPersistenceTests(unittest.TestCase):
    def setUp(self):
        schema = 'settings_test_' + uuid4().hex
        admin = create_engine(configured_engine.url)
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA {schema}'))

        def cleanup():
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
            admin.dispose()

        self.addCleanup(cleanup)
        engine = create_engine(configured_engine.url, connect_args={'options': f'-csearch_path={schema}'})
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add_all(JLPTLevel(code=f'N{n}', rank=6-n, label=f'N{n}') for n in range(1, 6))
            user = User(email='settings@example.com', full_name='Settings test', hashed_password='unused')
            db.add(user)
            db.commit()
            user_id = user.id

        def test_db():
            with Session(engine) as db:
                yield db

        def test_user():
            with Session(engine) as db:
                return db.get(User, user_id)

        application = FastAPI()
        application.include_router(users.router)
        application.include_router(auth.router)
        application.dependency_overrides[get_db] = test_db
        application.dependency_overrides[get_current_user] = test_user
        self.client = TestClient(application)
        self.addCleanup(self.client.close)

    def test_helper_and_languages_round_trip_through_settings_and_session(self):
        original = self.client.get('/users/me/settings').json()
        self.assertFalse(original['furigana_helper_enabled'])
        for enabled, language, mode in [(True, 'fr', 'hover'), (False, 'en', 'hidden')]:
            payload = {**original, 'furigana_helper_enabled': enabled, 'interface_locale': language,
                       'content_locale': language, 'furigana_display_mode': mode}
            result = self.client.put('/users/me/settings', json=payload)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json(), payload)
            self.assertEqual(self.client.get('/users/me/settings').json(), payload)
            self.assertEqual(self.client.get('/auth/session').json()['settings'], payload)

    def test_invalid_update_does_not_change_saved_preferences(self):
        original = self.client.get('/users/me/settings').json()
        result = self.client.put('/users/me/settings', json={**original, 'interface_locale': 'invalid', 'furigana_helper_enabled': True})
        self.assertEqual(result.status_code, 422)
        self.assertEqual(self.client.get('/users/me/settings').json(), original)

    def test_romaji_round_trip_is_independent_and_legacy_clients_preserve_it(self):
        original = self.client.get('/users/me/settings').json()
        self.assertFalse(original['romaji_enabled'])
        payload = {**original, 'romaji_enabled': True, 'furigana_display_mode': 'hidden'}
        result = self.client.put('/users/me/settings', json=payload)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.client.get('/auth/session').json()['settings'], payload)
        legacy = {key: value for key, value in payload.items() if key != 'romaji_enabled'}
        self.assertTrue(self.client.put('/users/me/settings', json=legacy).json()['romaji_enabled'])
        payload['romaji_enabled'] = False
        self.assertFalse(self.client.put('/users/me/settings', json=payload).json()['romaji_enabled'])

    def test_hidden_furigana_cannot_enable_colour_helper(self):
        original = self.client.get('/users/me/settings').json()
        result = self.client.put('/users/me/settings', json={**original, 'furigana_display_mode': 'hidden', 'furigana_helper_enabled': True})
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.json()['furigana_helper_enabled'])
        self.assertFalse(self.client.get('/auth/session').json()['settings']['furigana_helper_enabled'])

    def test_independent_level_ranges_round_trip_and_reject_crossed_bounds(self):
        original = self.client.get('/users/me/settings').json()
        self.assertEqual(original['vocabulary_min_level_code'], original['vocabulary_level_code'])
        payload = {**original, 'vocabulary_min_level_code': 'N4', 'vocabulary_level_code': 'N2',
                   'grammar_min_level_code': 'N5', 'grammar_level_code': 'N1',
                   'kanji_min_level_code': 'N3', 'kanji_level_code': 'N3'}
        result = self.client.put('/users/me/settings', json=payload)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.client.get('/auth/session').json()['settings'], payload)
        invalid = self.client.put('/users/me/settings', json={**payload, 'vocabulary_min_level_code': 'N1'})
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(self.client.get('/users/me/settings').json(), payload)


@unittest.skipUnless(os.getenv('SETTINGS_TEST_POSTGRES') == '1', 'Opt-in isolated PostgreSQL migration test')
class SettingsRangeMigrationTests(unittest.TestCase):
    def test_migration_preserves_existing_preferences_and_adds_valid_bounds(self):
        import importlib.util
        from pathlib import Path
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from sqlalchemy.exc import IntegrityError
        from test_quiz_postgres import PostgresQuizTests

        engine = PostgresQuizTests.make_engine(self)
        self.addCleanup(engine.dispose)
        path = Path(__file__).resolve().parents[1] / 'alembic/versions/0007_jlpt_level_ranges.py'
        spec = importlib.util.spec_from_file_location('range_migration', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE jlpt_levels (code VARCHAR(8) PRIMARY KEY)'))
            conn.execute(text("INSERT INTO jlpt_levels VALUES ('N1'),('N2'),('N3'),('N4'),('N5')"))
            conn.execute(text('CREATE TABLE user_settings (id TEXT PRIMARY KEY, vocabulary_level_code VARCHAR(8), grammar_level_code VARCHAR(8), kanji_level_code VARCHAR(8), updated_at TIMESTAMPTZ, content_locale TEXT)'))
            conn.execute(text("INSERT INTO user_settings VALUES ('one','N2','N3','N4','2026-09-01T12:00:00Z','fr'), ('two','N5','N1','N5','2026-09-02T12:00:00Z','en')"))
            original_columns = 'id,vocabulary_level_code,grammar_level_code,kanji_level_code,updated_at,content_locale'
            before = conn.execute(text(f'SELECT {original_columns} FROM user_settings ORDER BY id')).all()
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
            self.assertEqual(before, conn.execute(text(f'SELECT {original_columns} FROM user_settings ORDER BY id')).all())
            for category in ('vocabulary', 'grammar', 'kanji'):
                self.assertEqual(conn.execute(text(f'SELECT count(*) FROM user_settings WHERE {category}_min_level_code = {category}_level_code')).scalar(), 2)
            savepoint = conn.begin_nested()
            with self.assertRaises(IntegrityError):
                conn.execute(text("UPDATE user_settings SET vocabulary_min_level_code='N1' WHERE id='one'"))
            savepoint.rollback()
            with Operations.context(MigrationContext.configure(conn)):
                migration.downgrade()
            self.assertEqual(before, conn.execute(text(f'SELECT {original_columns} FROM user_settings ORDER BY id')).all())
