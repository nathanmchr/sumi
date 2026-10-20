import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base
from app.models.content import JLPTLevel, KanjiItem, VocabularyItem
from app.models.learning import LearningState
from app.utils.enums import ContentType, ReviewStatus
from scripts.prepare_catalog_readings import prepare, restore


class ReadingUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.backup = Path(self.temporary.name) / "backup.json"
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.db.add(JLPTLevel(code="N3", rank=3, label="N3"))
        self.db.add(KanjiItem(id="sound", character="音", slug="音", jlpt_level_code="N3"))
        self.word = VocabularyItem(id="old-id", slug="old-slug", japanese="音色", reading="おんいろ", romaji="oniro",
                                   romaji_search="oniro", furigana_segments=[{"surface": "音色", "reading": "おんいろ"}],
                                   translation="timbre", jlpt_level_code="N3", part_of_speech="noun", audio_url="/old.wav")
        self.db.add(self.word)
        self.db.add(LearningState(user_id="user", content_id="old-id", content_type=ContentType.vocabulary,
                                  mastery=0.8, status=ReviewStatus.known))
        self.db.commit()
        self.catalog = {"ID": "new-id", "Kanji": "音色", "Kana": "ねいろ", "Romaji": "neiro",
                        "Furigana": '[{"surface":"音色","reading":"ねいろ"}]'}
        stub = patch("scripts.prepare_catalog_readings.catalog_entry", return_value=self.catalog)
        stub.start()
        self.addCleanup(stub.stop)

    def test_preview_writes_nothing_and_apply_is_reversible_and_idempotent(self):
        changes = prepare(self.db)
        self.assertEqual(len(changes), 1)
        self.assertEqual(self.word.reading, "おんいろ")
        self.assertFalse(self.backup.exists())
        prepare(self.db, self.backup)
        self.db.commit()
        self.db.refresh(self.word)
        self.assertEqual((self.word.reading, self.word.romaji), ("ねいろ", "neiro"))
        self.assertEqual(self.word.furigana_segments[0]["kanji_ids"], ["sound"])
        self.assertEqual((self.word.id, self.word.slug, self.word.audio_url, self.word.jlpt_level_code),
                         ("old-id", "old-slug", "/old.wav", "N3"))
        state = self.db.scalar(select(LearningState))
        self.assertEqual((state.content_id, state.mastery), ("old-id", 0.8))
        self.assertEqual(prepare(self.db), [])
        self.assertEqual(prepare(self.db, self.backup), [])
        self.assertEqual(restore(self.db, self.backup), 1)
        self.db.commit()
        self.db.refresh(self.word)
        self.assertEqual((self.word.reading, self.word.romaji), ("おんいろ", "oniro"))

    def test_stale_backup_is_not_applied_over_later_edits(self):
        prepare(self.db, self.backup)
        self.db.commit()
        self.word.romaji = "user-edit"
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "edited since backup"):
            restore(self.db, self.backup)

    def test_existing_backup_is_never_overwritten(self):
        self.backup.write_text("precious backup")
        with self.assertRaises(FileExistsError):
            prepare(self.db, self.backup)
        self.assertEqual(self.backup.read_text(), "precious backup")
        self.assertEqual(self.word.reading, "おんいろ")
