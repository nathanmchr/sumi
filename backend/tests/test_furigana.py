import json
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from app.services.import_service import _furigana_segments_from_row
from app.utils.furigana import build_furigana, validate_furigana
from scripts.prepare_vocab_furigana import prepare, reference_segments


class FuriganaTests(TestCase):
    def test_written_alternatives_share_one_reading_without_concatenation(self):
        parts = [{"surface": "伯父", "reading": "おじ"}, {"surface": "さん/"},
                 {"surface": "叔父", "reading": "おじ"}, {"surface": "さん"}]
        self.assertEqual(validate_furigana("伯父さん/叔父さん", "おじさん", parts), parts)
        with self.assertRaises(ValueError):
            validate_furigana("伯父さん/叔父さん", "おじさん", [*parts[:2], {"surface": "叔父", "reading": "おじい"}, parts[3]])
        self.assertEqual(validate_furigana("何", "なん/なに", [{"surface": "何", "reading": "なん / なに"}]),
                         [{"surface": "何", "reading": "なん / なに"}])

    def test_kana_prefix_and_suffix_are_not_annotated(self):
        self.assertEqual(build_furigana("お母さん", "おかあさん"), ([
            {"surface": "お"}, {"surface": "母", "reading": "かあ"}, {"surface": "さん"},
        ], "aligned"))

    def test_okurigana_and_several_kanji_groups(self):
        self.assertEqual(build_furigana("取り扱う", "とりあつかう")[0], [
            {"surface": "取", "reading": "と"}, {"surface": "り"},
            {"surface": "扱", "reading": "あつか"}, {"surface": "う"},
        ])

    def test_indivisible_readings_and_variants_remain_grouped(self):
        self.assertEqual(build_furigana("今日", "きょう")[0], [{"surface": "今日", "reading": "きょう"}])
        self.assertEqual(build_furigana("毎月", "まいげつ/まいつき")[0], [{"surface": "毎月", "reading": "まいげつ / まいつき"}])
        self.assertEqual(build_furigana("大きい", "オオキイ")[0], [{"surface": "大", "reading": "おお"}, {"surface": "きい"}])

    def test_kana_and_punctuation_stay_plain(self):
        self.assertEqual(build_furigana("ありがとう！", "ありがとう")[0], [{"surface": "ありがとう！"}])
        self.assertEqual(build_furigana("コーヒー", "こーひー")[0], [{"surface": "コーヒー"}])

    def test_ambiguity_and_bad_readings_are_not_guessed(self):
        for word, reading, reason in [
            ("甲あ乙", "かあきあく", "ambiguous_alignment"),
            ("お母さん", "はは", "reading_mismatch"),
            ("賛成", "さんせい (annotation)", "non_kana_reading"),
            ("母", "", "missing_reading"),
        ]:
            with self.subTest(word=word):
                parts, status = build_furigana(word, reading)
                self.assertEqual(status, reason)
                self.assertFalse(any(part.get("reading") for part in parts))
                self.assertEqual("".join(part["surface"] for part in parts), word)

    def test_correlated_variants_do_not_invent_combinations(self):
        parts, status = build_furigana("甲の乙", "かのき/くのけ")
        self.assertEqual(status, "correlated_variants")
        self.assertFalse(any(part.get("reading") for part in parts))

    def test_manual_unambiguous_segments_are_preserved(self):
        parts = [{"surface": "甲", "reading": "か"}, {"surface": "あ"}, {"surface": "乙", "reading": "きあく"}]
        self.assertEqual(validate_furigana("甲あ乙", "かあきあく", parts), parts)

    def test_import_rejects_invalid_explicit_data(self):
        invalid = [[], {}, [{"surface": "母", "reading": "はは"}],
                   [{"surface": "お母さん", "reading": "おかあさん"}],
                   [{"surface": "お母さん", "reading": 123}]]
        for parts in invalid:
            with self.subTest(parts=parts), self.assertRaises(ValueError):
                _furigana_segments_from_row({"japanese": "お母さん", "reading": "おかあさん", "furigana_json": json.dumps(parts)})
        with self.assertRaises(ValueError):
            _furigana_segments_from_row({"japanese": "母", "reading": "はは", "furigana_json": "not-json"})

    def test_legacy_import_is_segmented_and_ids_are_preserved(self):
        expected = [{"surface": "会", "reading": "あ", "kanji_ids": ["kanji-a"]}, {"surface": "う"}]
        row = {"japanese": "会う", "reading": "あう", "furigana_json": json.dumps(expected)}
        self.assertEqual(_furigana_segments_from_row(row), expected)
        row.pop("furigana_json")
        self.assertEqual(_furigana_segments_from_row(row), [{"surface": "会", "reading": "あ"}, {"surface": "う"}])

    def test_extended_kanji_and_iteration_mark(self):
        self.assertEqual(build_furigana("𠮷田さん", "よしださん")[0], [{"surface": "𠮷田", "reading": "よしだ"}, {"surface": "さん"}])
        self.assertEqual(build_furigana("人々", "ひとびと")[0], [{"surface": "人々", "reading": "ひとびと"}])

    def test_reference_splits_regular_kanji_but_keeps_jukujikun(self):
        cases = [
            ("日曜日", "にちようび", [{"surface": "日", "reading": "にち"}, {"surface": "曜", "reading": "よう"}, {"surface": "日", "reading": "び"}]),
            ("今日", "きょう", [{"surface": "今日", "reading": "きょう"}]),
            ("学校", "がっこう", [{"surface": "学", "reading": "がっ"}, {"surface": "校", "reading": "こう"}]),
        ]
        reference = {(surface, reading): [parts] for surface, reading, parts in cases}
        for surface, reading, parts in cases:
            with self.subTest(surface=surface):
                self.assertEqual(reference_segments(surface, reading, reference), parts)

    def test_reference_rejects_inconsistent_or_conflicting_entries(self):
        self.assertIsNone(reference_segments("母", "はは", {("母", "はは"): [[{"surface": "母", "reading": "かあ"}]]}))
        self.assertIsNone(reference_segments("母", "はは", {("母", "はは"): [[{"surface": "母", "reading": "はは"}], [{"surface": "母"}]]}))

    def test_variants_keep_shared_boundaries_only(self):
        reference = {
            ("今日", "きょう"): [[{"surface": "今日", "reading": "きょう"}]],
            ("今日", "こんにち"): [[{"surface": "今", "reading": "こん"}, {"surface": "日", "reading": "にち"}]],
        }
        self.assertEqual(reference_segments("今日", "きょう/こんにち", reference), [{"surface": "今日", "reading": "きょう / こんにち"}])

    def test_dataset_writer_preserves_other_fields_and_is_idempotent(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "JLPT N5 Vocab.csv"
            path.write_text('Kanji;Hiragana;English\nお母さん;おかあさん;"mother; mum"\n', encoding="utf-8")
            prepare(root, write=True, report=root / "report.csv")
            first = path.read_bytes()
            prepare(root, write=True, report=root / "report.csv")
            self.assertEqual(first, path.read_bytes())
            with path.open(newline="") as handle:
                row = next(csv.DictReader(handle, delimiter=";"))
            self.assertEqual(row["English"], "mother; mum")
            self.assertEqual(json.loads(row["Furigana"]), build_furigana("お母さん", "おかあさん")[0])

    def test_seed_transform_preserves_explicit_furigana(self):
        from scripts.seed_db import _transform_row
        from app.utils.enums import ContentType
        parts = [{"surface": "お"}, {"surface": "母", "reading": "かあ"}, {"surface": "さん"}]
        row = {"Kanji": "お母さん", "Hiragana": "おかあさん", "English": "mother", "Furigana": json.dumps(parts)}
        imported = _transform_row(ContentType.vocabulary, "N5")(row, 2)
        self.assertEqual(_furigana_segments_from_row(imported), parts)
