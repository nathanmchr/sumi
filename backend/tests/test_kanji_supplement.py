import copy
import csv
import hashlib
import io
import unittest

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from app.models import Base, JLPTLevel, KanjiItem, KanjiTranslation, VocabularyItem, VocabularyKanjiLink
from scripts.kanji_supplement import (
    AUDIT, CATALOG, FIELDS, PACKAGE, append_catalog, catalog_row,
    integrate_database, load_entries, read_json, validate_entries, validate_levels,
)
from scripts.import_kanjivg_n5 import ROOT, parse_svg


class SupplementDataTests(unittest.TestCase):
    def test_complete_bilingual_coverage_and_spelling_levels(self):
        entries = load_entries()
        validate_entries(entries)
        validate_levels(entries, CATALOG / "vocabulary.csv")
        expected = {row["kanji"]: row["level"] for row in read_json(AUDIT)["consolidated"]["missing"]}
        self.assertEqual({row["character"]: row["level"] for row in entries}, expected)
        self.assertEqual(sum(bool(row["source_meanings"]["fr"]) for row in entries), 35)

    def test_english_changes_are_explicit_and_sourced(self):
        for row in load_entries():
            if row["english"] != row["source_meanings"]["en"]:
                self.assertEqual(row["english"], row["cross_checks"]["english"])
                self.assertTrue(row["cross_checks"]["sources"])
                self.assertTrue(row["cross_checks"]["reason"])
        self.assertIn("by-sa/4.0", read_json(PACKAGE)["license"])

    def test_original_catalogue_bytes_and_ids_are_preserved(self):
        content = (CATALOG / "kanji.csv").read_bytes()
        original = b"".join(content.splitlines(keepends=True)[:2212])
        key = "contenu csv/consolidated/kanji.csv"
        self.assertEqual(hashlib.sha256(original).hexdigest(), read_json(AUDIT)["source_sha256"][key])
        reconstructed, added = append_catalog(original.decode(), load_entries())
        self.assertEqual(added, 323)
        self.assertEqual(reconstructed.encode(), content)
        self.assertEqual(append_catalog(reconstructed, load_entries()), (reconstructed, 0))

    def test_refuses_silent_overwrite(self):
        entry = load_entries()[0]
        output = io.StringIO()
        writer = csv.DictWriter(output, FIELDS, delimiter=";")
        writer.writeheader()
        row = catalog_row(entry)
        row["French"] = "conflict"
        writer.writerow(row)
        with self.assertRaises(ValueError):
            append_catalog(output.getvalue(), [entry])

    def test_readings_are_japanese_not_names_or_chinese(self):
        for row in load_entries():
            for reading in row["onyomi"]:
                self.assertTrue(any("\u30a1" <= char <= "\u30fa" for char in reading), reading)
            for reading in row["kunyomi"]:
                self.assertTrue(any("\u3041" <= char <= "\u3096" for char in reading), reading)

    def test_all_added_strokes_match_pinned_originals(self):
        assets = ROOT / "frontend/public/kanji-strokes"
        manifest = read_json(assets / "manifest.json")
        for row in load_entries():
            char = row["character"]
            info = manifest["levels"][row["level"]][char]
            raw = (assets / f"source/{ord(char):05x}.svg").read_bytes()
            data = read_json(assets / info["file"])
            self.assertEqual(parse_svg(raw, char), data)
            self.assertEqual(info["source_sha256"], hashlib.sha256(raw).hexdigest())


class SupplementDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        event.listen(self.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.entries = load_entries()[:1]
        with Session(self.engine) as db:
            db.add(JLPTLevel(code="N5", rank=5, label="N5"))
            db.flush()
            db.add(VocabularyItem(id="word", slug="word", japanese="大丈夫", reading="だいじょうぶ",
                                  translation="all right", part_of_speech="expression", jlpt_level_code="N5"))
            db.add(KanjiItem(id="old", slug="old", character="大", meanings=["big"], jlpt_level_code="N5"))
            db.flush()
            db.add(VocabularyKanjiLink(vocabulary_item_id="word", kanji_item_id="old", kanji_position=1))
            db.commit()

    def test_insert_then_noop_without_changing_existing_word_or_link(self):
        with Session(self.engine) as db:
            word = db.get(VocabularyItem, "word")
            before = {col.name: copy.deepcopy(getattr(word, col.name)) for col in word.__table__.columns}
            self.assertEqual(integrate_database(db, self.entries), {"kanji": 1, "translations": 2, "links": 1})
            db.commit()
            self.assertEqual(integrate_database(db, self.entries), {"kanji": 0, "translations": 0, "links": 0})
            self.assertEqual({col.name: getattr(word, col.name) for col in word.__table__.columns}, before)
            self.assertEqual(db.get(VocabularyKanjiLink, ("word", "old")).kanji_position, 1)
            self.assertEqual(db.get(VocabularyKanjiLink, ("word", self.entries[0]["id"])).kanji_position, 2)
            for locale, key in (("en", "english"), ("fr", "french")):
                self.assertEqual(db.get(KanjiTranslation, (self.entries[0]["id"], locale)).meanings, self.entries[0][key])

    def test_dry_run_rolls_back_all_three_tables(self):
        with Session(self.engine) as db:
            integrate_database(db, self.entries)
            db.rollback()
            self.assertEqual(db.scalar(select(func.count()).select_from(KanjiItem)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(KanjiTranslation)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(VocabularyKanjiLink)), 1)

    def test_conflicting_existing_character_is_not_overwritten(self):
        with Session(self.engine) as db:
            db.add(KanjiItem(id="conflict", slug="conflict", character=self.entries[0]["character"],
                             meanings=["existing editorial value"], jlpt_level_code="N5"))
            db.commit()
            with self.assertRaises(ValueError):
                integrate_database(db, self.entries)
            db.rollback()
            self.assertEqual(db.get(KanjiItem, "conflict").meanings, ["existing editorial value"])


if __name__ == "__main__":
    unittest.main()
