import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4
from unittest.mock import patch

from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session

from app.models import Base
from app.models.content import (ExampleSentence, GrammarItem, GrammarTranslation, JLPTLevel, KanjiItem,
                                VocabularyItem, VocabularyTranslation)
from app.models.learning import GrammarExercise, LearningState, ReviewHistory, StudyQuestion, StudySession
from app.models.user import User
from app.repositories.content_repository import ContentRepository
from app.services.consolidated_catalog import Catalog, apply_plan, build_plan, grammar_key, load_catalog
from app.services.content_identity import resolve_content_id
from app.services.import_service import import_csv
from app.utils.enums import ContentType
from scripts.sync_catalog import MUTABLE, digest, restore, snapshot, synchronize


class ConsolidatedCatalogTests(unittest.TestCase):
    def make_engine(self):
        return create_engine("sqlite://")

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.backup = Path(self.tmp.name) / "before.json"
        self.engine = self.make_engine()
        if self.engine.dialect.name == "sqlite":
            event.listen(self.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.db.add_all([JLPTLevel(code=f"N{n}", rank=n, label=f"N{n}") for n in range(1, 6)])
        self.db.add(User(id="learner", email="catalog-test@example.test", full_name="Test", hashed_password="unused"))
        self.db.flush()
        self.word = VocabularyItem(id="word-kanji", slug="kanji-slug", japanese="事", reading="こと", romaji="koto",
                                   translation="thing", part_of_speech="noun", jlpt_level_code="N3", notes="Note A")
        self.other = VocabularyItem(id="word-kana", slug="kana-slug", japanese="こと", reading="こと", romaji="koto",
                                    translation="thing; fact", part_of_speech="noun", jlpt_level_code="N4", notes="Note B")
        self.word.translations = [VocabularyTranslation(locale="fr", translation="chose", notes="Note française A")]
        self.other.translations = [VocabularyTranslation(locale="fr", translation="fait", notes="Note française B")]
        self.grammar = GrammarItem(id="grammar-old", slug="grammar-old-slug", title="も", structure="mo", explanation="also",
                                   jlpt_level_code="N5", nuances="keep nuance", examples=[{"text": "例"}])
        self.grammar.translations = [GrammarTranslation(locale="fr", explanation="aussi", nuances="Nuance")]
        self.db.add_all([self.word, self.other, self.grammar,
                        KanjiItem(id="kanji-old", character="事", slug="事", jlpt_level_code="N3", mnemonic="keep mnemonic")])
        self.db.flush()
        self.db.add(ExampleSentence(id="example", vocabulary_item_id=self.other.id, text="例", translation="example"))
        self.db.add(GrammarExercise(id="exercise", code="sample", grammar_item_id=self.grammar.id, prompt="___", answer="も",
                                   distractors=["は", "を", "に"], completed_sentence="も", translations={}))
        now = datetime.now(timezone.utc)
        self.db.add(StudySession(id="session", user_id="learner", started_at=now,
                                 snapshot={"categories": ["vocabulary"], "content_id": self.other.id}))
        self.db.flush()
        self.db.add(LearningState(id="state", user_id="learner", content_type=ContentType.vocabulary, content_id=self.word.id,
                                  mastery=0.73, review_revision=12, next_review_at=now, fsrs_card={"stability": 7.7}))
        self.db.add(ReviewHistory(id="review", user_id="learner", content_type=ContentType.vocabulary, content_id=self.other.id,
                                  rating=3, payload={"historical_id": self.other.id}, session_id="session"))
        self.db.add(StudyQuestion(id="question", user_id="learner", session_id="session", content_type="vocabulary",
                                  content_id=self.other.id, locale="fr", prompt={"title": "こと"}, choices=[{"id": "answer", "label": "chose"}],
                                  correct_option_id="answer", feedback={}, baseline_revision=12, expires_at=now))
        self.db.commit()
        self.row = {"ID": "canonical-word", "Level": "N4", "KanjiLevel": "N3", "Kanji": "事", "Kana": "こと", "Romaji": "koto",
                    "Furigana": '[{"surface":"事","reading":"こと"}]', "English": "thing; fact", "French": "chose ; fait", "Notes": "Catalogue note"}
        homonym = {**self.row, "ID": "canonical-other-sense", "Kanji": "", "English": "different sense", "French": "autre sens", "Furigana": '[{"surface":"こと"}]'}
        grammar = {"ID": "canonical-grammar", "Level": "N5", "Kanji": "", "Kana": "も", "Romaji": "mo", "English": "also", "French": "aussi"}
        grammar2 = {**grammar, "ID": "canonical-distinct-grammar", "Level": "N4", "English": "as many as", "French": "pas moins de"}
        kanji = {"ID": "canonical-kanji", "Level": "N3", "Kanji": "事", "Pronunciation": "ジ・こと", "English": "thing; matter", "French": "chose ; affaire"}
        self.catalog = Catalog({"vocabulary": [homonym, self.row], "grammar": [grammar, grammar2], "kanji": [kanji]},
                               {(grammar_key("も"), grammar_key("also")): {grammar["ID"]}})
        for mocked in (patch("app.services.consolidated_catalog.load_catalog", return_value=self.catalog),
                       patch("app.services.consolidated_catalog.catalog_entry", side_effect=lambda item: self.row if item.id in {"word-kanji", "word-kana"} else None),
                       patch("app.services.consolidated_catalog.canonical_row_audio", return_value="/audio/approved.wav?v=verified"),
                       patch("scripts.sync_catalog.source_hashes", return_value={"catalogue": "fixture"})):
            mocked.start()
            self.addCleanup(mocked.stop)

    def test_sync_preserves_progress_extras_urls_order_and_distinct_senses(self):
        result = synchronize(self.db, self.backup)
        self.db.commit()
        self.assertTrue(result["changed"])
        self.assertEqual(result["vocabulary"], {"before": 2, "after": 2, "created": 1, "absorbed": 1})
        repo = ContentRepository(self.db)
        word = repo.get_vocabulary("canonical-word")
        self.assertEqual(word.id, "word-kanji")
        self.assertEqual(repo.get_vocabulary("word-kana").id, word.id)
        self.assertEqual(repo.get_vocabulary_by_slug("kana-slug").id, word.id)
        self.assertEqual(word.jlpt_level_code, "N4")
        self.assertEqual(word.kanji_level_code, "N3")
        self.assertEqual(word.audio_url, "/audio/approved.wav?v=verified")
        self.assertEqual(word.kanji_links[0].kanji_position, 1)
        self.assertEqual(word.notes, "Note A\n\nNote B")
        self.assertEqual(next(t for t in word.translations if t.locale == "fr").notes,
                         "Catalogue note\n\nNote française A\n\nNote française B")
        self.assertEqual(self.db.get(ExampleSentence, "example").vocabulary_item_id, word.id)
        self.assertEqual(self.db.get(LearningState, "state").review_revision, 12)
        self.assertEqual(self.db.get(StudyQuestion, "question").content_id, word.id)
        self.assertEqual(self.db.get(StudyQuestion, "question").correct_option_id, "answer")
        self.assertEqual(self.db.get(ReviewHistory, "review").payload, {"historical_id": "word-kana"})
        self.assertEqual(self.db.get(StudySession, "session").snapshot["content_id"], word.id)
        self.assertEqual([w.catalog_id for w in repo.list_vocabulary()], ["canonical-other-sense", "canonical-word"])
        self.assertEqual(len(repo.list_grammar()), 2)
        self.assertEqual(repo.get_grammar("canonical-grammar").nuances, "keep nuance")
        self.assertEqual(repo.get_kanji("canonical-kanji").mnemonic, "keep mnemonic")
        self.assertEqual(resolve_content_id(self.db, "grammar", "word-kana"), "word-kana")
        self.assertEqual(self.backup.stat().st_mode & 0o777, 0o600)
        self.assertFalse(synchronize(self.db)["changed"])
        with self.assertRaisesRegex(ValueError, "catalogue consolidé"):
            import_csv(self.db, ContentType.vocabulary, Path("never-read.csv"))
        from scripts.kanji_supplement import integrate_database
        with self.assertRaisesRegex(ValueError, "catalogue consolidé"):
            integrate_database(self.db, [])

    def test_restore_is_exact_and_refuses_subsequent_progress(self):
        before = digest(snapshot(self.db, MUTABLE))
        synchronize(self.db, self.backup)
        self.db.commit()
        self.db.get(LearningState, "state").mastery = 0.91
        self.db.flush()
        with self.assertRaisesRegex(ValueError, "changed since"):
            restore(self.db, self.backup)
        self.db.rollback()
        restore(self.db, self.backup)
        self.db.commit()
        self.assertEqual(digest(snapshot(self.db, MUTABLE)), before)

    def test_collision_aborts_before_any_merge(self):
        self.db.add(LearningState(user_id="learner", content_type=ContentType.vocabulary, content_id=self.other.id))
        self.db.commit()
        before = digest(snapshot(self.db, MUTABLE))
        with self.assertRaisesRegex(ValueError, "Conflicting learning states"):
            build_plan(self.db)
        self.assertEqual(digest(snapshot(self.db, MUTABLE)), before)

    def test_ambiguous_grammar_and_unmapped_words_fail_closed(self):
        ambiguous = copy.deepcopy(self.catalog)
        ambiguous.grammar_index[(grammar_key("も"), grammar_key("also"))].add("canonical-distinct-grammar")
        with self.assertRaisesRegex(ValueError, "ambiguous grammar"):
            build_plan(self.db, ambiguous)
        with patch("app.services.consolidated_catalog.catalog_entry", return_value=None):
            with self.assertRaisesRegex(ValueError, "Unmapped"):
                build_plan(self.db)

    def test_existing_backup_is_not_overwritten(self):
        self.backup.write_text("keep")
        with self.assertRaises(FileExistsError):
            synchronize(self.db, self.backup)
        self.assertEqual(self.backup.read_text(), "keep")


class RealCatalogTests(unittest.TestCase):
    def test_reviewed_catalogue_and_family_readings_are_distinct(self):
        catalog = load_catalog()
        self.assertEqual({kind: len(rows) for kind, rows in catalog.rows.items()}, {"vocabulary": 8038, "grammar": 661, "kanji": 2534})
        words = {r["ID"]: r for r in catalog.rows["vocabulary"]}
        self.assertEqual(words["01f26f27-01ff-5506-b08c-5caafc5bed98"]["Kanji"], "お祖父さん")
        self.assertEqual(words["01f26f27-01ff-5506-b08c-5caafc5bed98"]["Kana"], "おじいさん")
        self.assertEqual(words["4e3ab6b5-c9c1-5755-ab3a-93f76d026f77"]["Kana"], "おじさん")
        self.assertTrue(any(r["Kanji"] == "何" and "なん" in r["Kana"] and "なに" in r["Kana"] for r in words.values()))


@unittest.skipUnless(os.getenv("CATALOG_TEST_POSTGRES") == "1", "Opt-in isolated PostgreSQL migration tests")
class PostgresCatalogTests(ConsolidatedCatalogTests):
    def make_engine(self):
        from app.core.database import engine
        schema = "catalog_test_" + uuid4().hex
        admin = create_engine(engine.url)
        with admin.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA {schema}"))

        def cleanup():
            with admin.begin() as connection:
                connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            admin.dispose()

        self.addCleanup(cleanup)
        return create_engine(engine.url, connect_args={"options": f"-csearch_path={schema}"})
