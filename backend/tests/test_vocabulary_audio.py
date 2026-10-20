import csv
from datetime import datetime, timezone
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

import app.models  # Register all tables referenced by content relationships.
from app.models.base import Base
from app.models.content import JLPTLevel, VocabularyItem
from app.services.content_service import kanji_out, vocabulary_out
from app.services.quiz_service import present_question
from app.services.vocabulary_audio import audio_aliases, preferred_audio_url


class VocabularyAudioTests(unittest.TestCase):
    def setUp(self):
        # Keep historical alias tests independent from live generation progress.
        catalog = patch("app.services.vocabulary_audio.catalog_audio", return_value=(False, None))
        catalog.start()
        self.addCleanup(catalog.stop)
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.db.add_all([
            JLPTLevel(code="N5", rank=5, label="N5"),
            JLPTLevel(code="N2", rank=2, label="N2"),
        ])

    def word(self, japanese, reading, meaning, audio, level="N5"):
        item = VocabularyItem(
            slug=f"{japanese}-{reading}-{meaning}", japanese=japanese,
            reading=reading, translation=meaning, audio_url=audio,
            part_of_speech="other", jlpt_level_code=level,
        )
        self.db.add(item)
        self.db.flush()
        return item

    def chopsticks(self):
        source = self.word("はし", "はし", "chopsticks", "/kana.wav")
        target = self.word("箸", "はし", "chopsticks", "/chopsticks.wav", "N2")
        bridge = self.word("橋", "はし", "bridge", "/bridge.wav")
        return source, target, bridge

    def test_same_word_shares_kanji_audio_without_changing_display_or_level(self):
        source, target, bridge = self.chopsticks()
        for word in (source, target):
            self.assertEqual(preferred_audio_url(self.db, word), "/chopsticks.wav")
        self.assertEqual(preferred_audio_url(self.db, bridge), "/bridge.wav")
        rendered = vocabulary_out(self.db, source, locale="fr")
        self.assertEqual(rendered.audio_url, "/chopsticks.wav")
        self.assertEqual((rendered.japanese, rendered.reading, rendered.jlpt_level_code),
                         ("はし", "はし", "N5"))
        self.assertEqual(source.audio_url, "/kana.wav")
        self.assertFalse(self.db.dirty)

    def test_meaning_distinguishes_identical_kana(self):
        bottom = self.word("底", "そこ", "bottom,sole", "/bottom.wav")
        there = self.word("其処", "そこ", "that place, there", "/there.wav")
        for meaning, target in (("bottom,sole", bottom), ("that place", there)):
            source = self.word("そこ", "そこ", meaning, "/kana.wav")
            self.assertEqual(preferred_audio_url(self.db, source), target.audio_url)
        filler = self.word("あの", "あの", "um...", "/filler.wav")
        self.word("彼の", "あの", "that over there", "/that.wav")
        self.assertEqual(preferred_audio_url(self.db, filler), "/filler.wav")

    def test_unknown_sense_and_missing_target_keep_original_audio(self):
        missing = self.word("はし", "はし", "chopsticks", "/kana.wav")
        self.word("橋", "はし", "bridge", "/bridge.wav")
        unknown = self.word("はし", "はし", "unreviewed meaning", "/unknown.wav")
        self.assertEqual(preferred_audio_url(self.db, missing), "/kana.wav")
        self.assertEqual(preferred_audio_url(self.db, unknown), "/unknown.wav")

    def test_missing_target_audio_keeps_original(self):
        source = self.word("はし", "はし", "chopsticks", "/kana.wav")
        self.word("箸", "はし", "chopsticks", None)
        self.assertEqual(preferred_audio_url(self.db, source), "/kana.wav")

    def test_missing_source_audio_can_use_target(self):
        source = self.word("はし", "はし", "chopsticks", None)
        self.word("箸", "はし", "chopsticks", "/chopsticks.wav")
        self.assertEqual(preferred_audio_url(self.db, source), "/chopsticks.wav")

    def test_target_must_have_the_same_reading(self):
        source = self.word("ある", "ある", "to be,to have (used for inanimate objects)", "/aru.wav")
        self.word("有る", "ゆう", "to be,to have", "/yuu.wav")
        self.assertEqual(preferred_audio_url(self.db, source), "/aru.wav")

    def test_linked_vocabulary_and_existing_quiz_use_same_audio(self):
        source, _, _ = self.chopsticks()
        kanji = SimpleNamespace(
            catalog_id=None, source_order=None,
            id="test-kanji", character="箸", slug="箸", meanings=["chopsticks"],
            translations=[], onyomi=[], kunyomi=[], radicals=[], mnemonic=None,
            jlpt_level_code="N2", vocabulary_links=[SimpleNamespace(vocabulary_item=source)],
        )
        self.assertEqual(kanji_out(self.db, kanji).linked_vocabulary[0].audio_url,
                         "/chopsticks.wav")
        question = SimpleNamespace(
            id="old-question", content_type="vocabulary", content_id=source.id,
            locale="en", answered_at=None, expires_at=datetime.now(timezone.utc), result=None,
            choices=[], feedback={}, prompt={
                "kind": "meaning", "title": "はし", "reading": "はし",
                "instruction": "Choose", "jlpt_level_code": "N5",
                "audio_url": "/kana.wav",
            },
        )
        result = present_question(self.db, question)
        self.assertEqual(result.audio_url, "/chopsticks.wav")
        self.assertEqual(result.title, "はし")
        self.assertEqual(question.prompt["audio_url"], "/kana.wav")

    def test_target_lookup_is_batched_once_per_session(self):
        source, _, _ = self.chopsticks()
        queries = []
        def count_query(*args):
            queries.append(args[2])
        event.listen(self.engine, "before_cursor_execute", count_query)
        try:
            for _ in range(10):
                self.assertEqual(preferred_audio_url(self.db, source), "/chopsticks.wav")
        finally:
            event.remove(self.engine, "before_cursor_execute", count_query)
        self.assertEqual(len(queries), 1)


class AudioAliasCorpusTests(unittest.TestCase):
    def test_every_current_candidate_is_reviewed_and_targets_exist(self):
        root = Path(__file__).resolve().parents[2]
        rows = []
        for path in sorted((root / "contenu csv").glob("* Vocab.csv")):
            with path.open(encoding="utf-8-sig", newline="") as handle:
                rows.extend(csv.DictReader(handle, delimiter=";"))
        self.assertTrue(rows)
        has_kanji = re.compile(r"[\u3400-\u9fff々]").search
        targets = {}
        for row in rows:
            if has_kanji(row["Kanji"]):
                targets.setdefault(row["Hiragana"], set()).add(row["Kanji"])
        candidates = set()
        for row in rows:
            reading = row["Hiragana"] or row["Kanji"]
            if not has_kanji(row["Kanji"]) and reading in targets:
                candidates.add((reading, row["English"].strip().casefold()))
        aliases = audio_aliases()
        self.assertEqual(candidates, set(aliases), "Review new or changed kana/kanji pairs")
        for (reading, meaning), target in aliases.items():
            if target:
                with self.subTest(reading=reading, meaning=meaning):
                    self.assertIn(target, targets[reading])
        self.assertEqual(aliases[("はし", "chopsticks")], "箸")
        self.assertEqual(aliases[("つける", "to turn on")], "点ける")
        self.assertEqual(aliases[("せっけん", "economy")], "石鹸")  # French source confirms savon.
        self.assertEqual(aliases[("いっぱい", "full")], "")  # Not 一敗 (defeat).


if __name__ == "__main__":
    unittest.main()
