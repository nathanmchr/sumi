import csv
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base
from app.models.content import JLPTLevel, VocabularyItem, VocabularyTranslation
from app.models.learning import LearningState
from app.services.content_service import vocabulary_out
from app.utils.enums import ContentType, ReviewStatus
from scripts.prepare_spelling_notes import CATALOG_IDS, prepare, restore


class SpellingNotesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.backup = Path(self.temporary.name) / "notes.json"
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.db.add(JLPTLevel(code="N5", rank=5, label="N5"))
        self.word = VocabularyItem(id="legacy", slug="legacy", japanese="伯父/叔父", reading="おじさん",
                                   translation="uncle", part_of_speech="noun", jlpt_level_code="N5",
                                   audio_url="/unchanged.wav", notes="base note")
        self.word.translations = [
            VocabularyTranslation(locale="fr", translation="oncle"),
            VocabularyTranslation(locale="en", translation="uncle", notes="English note"),
        ]
        self.db.add(self.word)
        self.db.add(LearningState(user_id="learner", content_id="legacy", content_type=ContentType.vocabulary,
                                  mastery=0.7, status=ReviewStatus.known))
        self.db.commit()
        self.source = {"ID": "canonical", "Notes": "伯父さん : côté aîné. 叔父さん : côté cadet."}
        for stub in [patch("scripts.prepare_spelling_notes.CATALOG_IDS", {"canonical"}),
                     patch("scripts.prepare_spelling_notes.catalog_entry", return_value=self.source)]:
            stub.start()
            self.addCleanup(stub.stop)

    def snapshot(self):
        return {table.name: [dict(row) for row in self.db.execute(select(table)).mappings()]
                for table in Base.metadata.sorted_tables}

    def test_preview_apply_idempotence_localization_and_restore(self):
        original = self.snapshot()
        self.assertEqual(len(prepare(self.db)), 1)
        self.assertEqual(self.snapshot(), original)
        self.assertFalse(self.backup.exists())
        prepare(self.db, self.backup)
        self.db.commit()
        self.assertEqual(self.backup.stat().st_mode & 0o777, 0o600)
        expected = self.snapshot()
        expected["vocabulary_translations"] = original["vocabulary_translations"]
        self.assertEqual(expected, original)  # Includes learning state and all item fields.
        self.db.expire_all()
        with patch("app.services.content_service.preferred_audio_url", return_value="/unchanged.wav"):
            self.assertEqual(vocabulary_out(self.db, self.word, locale="fr").notes, self.source["Notes"])
            self.assertEqual(vocabulary_out(self.db, self.word, locale="en").notes, "English note")
        self.assertEqual(prepare(self.db, self.backup), [])
        self.assertEqual(restore(self.db, self.backup), 1)
        self.db.commit()
        self.assertEqual(self.snapshot(), original)

    def test_missing_or_ambiguous_identity_blocks_all_writes(self):
        original = self.snapshot()
        with patch("scripts.prepare_spelling_notes.catalog_entry", return_value=None):
            with self.assertRaisesRegex(ValueError, "Missing reviewed"):
                prepare(self.db, self.backup)
        self.assertEqual(self.snapshot(), original)
        self.db.add(VocabularyItem(id="duplicate", slug="duplicate", japanese="別", reading="べつ",
                                   translation="other", part_of_speech="noun", jlpt_level_code="N5"))
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            prepare(self.db, self.backup)
        self.assertFalse(self.backup.exists())

    def test_existing_note_and_backup_are_preserved(self):
        self.backup.write_text("keep me")
        with self.assertRaises(FileExistsError):
            prepare(self.db, self.backup)
        self.assertEqual(self.backup.read_text(), "keep me")
        french = self.db.get(VocabularyTranslation, ("legacy", "fr"))
        french.notes = "User note"
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "Existing note"):
            prepare(self.db)
        self.assertEqual(french.notes, "User note")

    def test_blank_source_note_and_missing_translation_are_rejected(self):
        self.source["Notes"] = " "
        with self.assertRaisesRegex(ValueError, "Missing reviewed note"):
            prepare(self.db, self.backup)
        self.source["Notes"] = "Reviewed"
        self.db.delete(self.db.get(VocabularyTranslation, ("legacy", "fr")))
        self.db.commit()
        from sqlalchemy.exc import NoResultFound
        with self.assertRaises(NoResultFound):
            prepare(self.db, self.backup)
        self.assertFalse(self.backup.exists())

    def test_restore_refuses_later_changes(self):
        prepare(self.db, self.backup)
        self.db.commit()
        french = self.db.get(VocabularyTranslation, ("legacy", "fr"))
        french.translation = "User correction"
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "edited since backup"):
            restore(self.db, self.backup)
        self.db.rollback()
        self.assertEqual(french.translation, "User correction")


class ReviewedSpellingNoteContentTests(unittest.TestCase):
    def test_lesson_content_and_versions_stay_identical_to_pre_note_catalogue(self):
        from scripts import import_n5_lessons as compiler

        current, current_report = compiler.compile_course()
        plan = json.loads((compiler.DATA / "n5_units.json").read_text())
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for category in ("grammar", "kanji"):
                shutil.copyfile(compiler.CATALOG / f"{category}.csv", root / f"{category}.csv")
            # Reconstruct the exact pre-note bytes, without keeping another full catalogue.
            lines = (compiler.CATALOG / "vocabulary.csv").read_text().splitlines(keepends=True)
            original = "".join(line.rsplit(";", 1)[0] + ";\n" if line.split(";")[2] in CATALOG_IDS else line
                               for line in lines)
            self.assertEqual(hashlib.sha256(original.encode()).hexdigest(), plan["source_sha256"]["vocabulary"])
            (root / "vocabulary.csv").write_text(original)
            with patch.object(compiler, "CATALOG", root):
                before, before_report = compiler.compile_course()
                self.assertEqual(current, before)
                self.assertEqual(current_report, before_report)
                # No broad exemption: an unreviewed catalogue change still blocks import.
                (root / "vocabulary.csv").write_text(original.replace("毎月", "毎年", 1))
                with self.assertRaisesRegex(ValueError, "source changed"):
                    compiler.compile_course()

    def test_seven_source_notes_have_their_readings_and_nuances(self):
        path = Path(__file__).resolve().parents[2] / "contenu csv/consolidated/vocabulary.csv"
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = {row["ID"]: row for row in csv.DictReader(handle, delimiter=";") if row["ID"] in CATALOG_IDS}
        self.assertEqual(set(rows), CATALOG_IDS)
        for row in rows.values():
            self.assertIn(row["Kana"], row["Notes"])
            self.assertTrue(row["Notes"].strip())
        by_reading = {row["Kana"]: row["Notes"] for row in rows.values()}
        self.assertIn("conjoint", by_reading["おばさん"])
        self.assertIn("épouse", by_reading["おじさん"])
        self.assertIn("小父さん", by_reading["おじさん"])
        self.assertIn("dans la mer", by_reading["かわ"])
        for spelling in ("堅い", "硬い", "固い"):
            self.assertIn(spelling, by_reading["かたい"])
        self.assertIn("saké", by_reading["つくる"])
        self.assertIn("préférence", by_reading["まるい"])
