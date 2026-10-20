import unittest
from unittest.mock import patch

from app.services.lesson_readings import reading_aids


class LessonReadingTests(unittest.TestCase):
    def test_reviewed_segments_replace_automatic_grouping(self):
        aids = reading_aids({"source_id": "daa10f9a-525a-5488-a07c-ec5002147686", "japanese": "日曜日",
            "segments": [{"surface": "日曜日", "reading": "にちようび"}]})
        self.assertEqual([s["reading"] for s in aids["segments"]], ["にち", "よう", "び"])

    def test_irregular_group_and_kana_stay_intact(self):
        today = reading_aids({"source_id": "6891196d-d86e-56d7-9df5-323e82e16543", "japanese": "今日"})
        self.assertEqual(today["segments"], [{"surface": "今日", "reading": "きょう"}])
        kana = reading_aids({"source_id": "6891196d-d86e-56d7-9df5-323e82e16543", "japanese": "きょう"})
        self.assertEqual(kana["segments"], [{"surface": "きょう"}])
        self.assertEqual(kana["romaji"], "kyou")

    def test_unknown_spelling_and_hidden_word_are_not_enriched(self):
        self.assertEqual(reading_aids({"source_id": "6891196d-d86e-56d7-9df5-323e82e16543", "japanese": "今日は"}), {})
        self.assertEqual(reading_aids({"source_id": "6891196d-d86e-56d7-9df5-323e82e16543"}), {})

    def test_catalog_unavailable_preserves_authored_readings(self):
        word = {"japanese": "猫", "segments": [{"surface": "猫", "reading": "ねこ"}], "romaji": "neko"}
        with patch("app.services.lesson_readings._rows", side_effect=OSError):
            self.assertEqual(reading_aids(word), {"segments": word["segments"], "romaji": "neko"})
