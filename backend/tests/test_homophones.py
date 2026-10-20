import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.base import Base
from app.models.content import JLPTLevel, VocabularyItem, VocabularyTranslation
from app.routers.content import router
from app.services.homophone_service import list_homophones, normalize_reading


class ReadingTests(unittest.TestCase):
    def test_normalizes_script_and_width_only(self):
        for value in ("はし", "ハシ", " ﾊｼ "):
            self.assertEqual(normalize_reading(value), "はし")
        self.assertEqual(normalize_reading("コーヒー"), "こーひー")
        self.assertNotEqual(normalize_reading("おばさん"), normalize_reading("おばあさん"))
        self.assertNotEqual(normalize_reading("きて"), normalize_reading("きって"))
        self.assertNotEqual(normalize_reading("きよう"), normalize_reading("きょう"))

    def test_rejects_ambiguous_or_invented_readings(self):
        for value in ("", " ", "橋", "hashi", "はし/ばし", "はし・ばし", "(副)", "は し", "ー", "Uӣ[い"):
            with self.subTest(value=value):
                self.assertIsNone(normalize_reading(value))


class HomophoneTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.db.add_all([JLPTLevel(code=f"N{rank}", rank=rank, label=f"N{rank}") for rank in range(1, 6)])
        self.sequence = 0

    def word(self, japanese, reading, meaning, audio="/sample.wav", level="N5", romaji="", french=None):
        self.sequence += 1
        word = VocabularyItem(
            slug=f"word-{self.sequence}", japanese=japanese, reading=reading,
            translation=meaning, audio_url=audio, jlpt_level_code=level,
            part_of_speech="noun", romaji_search=romaji,
        )
        if french is not None:
            word.translations = [VocabularyTranslation(locale="fr", translation=french)]
        self.db.add(word)
        self.db.flush()
        return word

    def bridge_group(self):
        bridge = self.word("橋", "はし", "bridge", "/bridge.wav", romaji="hashi", french="pont")
        chopsticks = self.word("箸", "はし", "chopsticks", "/chopsticks.wav", romaji="hashi", french="baguettes")
        return bridge, chopsticks

    def test_search_returns_whole_group_with_localized_meanings(self):
        bridge, chopsticks = self.bridge_group()
        for query in ("橋", "はし", "ハシ", "ﾊｼ", "HASH I", "pont", "bridge"):
            with self.subTest(query=query):
                result = list_homophones(self.db, query, "fr")
                self.assertEqual(result.total, 1)
                self.assertEqual({word.id for word in result.groups[0].words}, {bridge.id, chopsticks.id})
                self.assertEqual({word.translation for word in result.groups[0].words}, {"pont", "baguettes"})

    def test_empty_query_and_no_match(self):
        self.bridge_group()
        self.assertEqual(list_homophones(self.db, " ").total, 1)
        self.assertEqual(list_homophones(self.db, "nothing-matches").total, 0)

    def test_single_word_and_spelling_variants_alone_are_excluded(self):
        self.word("雨", "あめ", "rain")
        self.word("はし", "はし", "chopsticks")
        self.word("箸", "はし", "Chopsticks ")
        self.assertEqual(list_homophones(self.db).total, 0)

    def test_exact_cross_level_duplicates_are_collapsed_but_senses_survive(self):
        bridge, _ = self.bridge_group()
        self.word("橋", "はし", " Bridge ", level="N2", french="pont")
        self.word("橋", "はし", "bridge of a musical instrument", level="N1")
        words = list_homophones(self.db).groups[0].words
        self.assertEqual(len(words), 3)
        self.assertIn(bridge.id, {word.id for word in words})

    def test_duplicate_with_audio_is_preferred(self):
        self.word("橋", "はし", "bridge", None)
        playable = self.word("橋", "はし", "bridge", "/bridge.wav", "N2")
        self.word("箸", "はし", "chopsticks")
        words = list_homophones(self.db).groups[0].words
        self.assertIn(playable.id, {word.id for word in words})
        self.assertEqual(len(words), 2)

    def test_distinct_translated_senses_are_not_collapsed(self):
        self.word("橋", "はし", "bridge", french="pont")
        self.word("橋", "はし", "bridge", french="chevalet")
        words = list_homophones(self.db, locale="fr").groups[0].words
        self.assertEqual({word.translation for word in words}, {"pont", "chevalet"})

    def test_audio_aliases_and_missing_audio_do_not_merge_distinct_entries(self):
        self.bridge_group()
        self.word("はし", "はし", "chopsticks", "/kana.wav")
        self.word("端", "はし", "edge", None)
        words = {word.japanese: word for word in list_homophones(self.db).groups[0].words}
        self.assertEqual(words["はし"].audio_url, words["箸"].audio_url)
        self.assertNotEqual(words["橋"].audio_url, words["箸"].audio_url)
        self.assertIsNone(words["端"].audio_url)
        self.assertFalse(self.db.dirty)

    def test_fallback_translation_locale_is_honest(self):
        self.word("雨", "あめ", "rain", french="pluie")
        self.word("飴", "あめ", "candy")
        words = {word.japanese: word for word in list_homophones(self.db, locale="fr").groups[0].words}
        self.assertEqual((words["雨"].translation, words["雨"].translation_locale), ("pluie", "fr"))
        self.assertEqual((words["飴"].translation, words["飴"].translation_locale), ("candy", "en"))

    def test_only_valid_matching_readings_are_grouped(self):
        self.bridge_group()
        self.word("端", "ハシ", "edge")
        self.word("嘴", "はし / くちばし", "beak")
        self.word("羽", "はしい", "unrelated")
        result = list_homophones(self.db)
        self.assertEqual(result.total, 1)
        self.assertEqual(len(result.groups[0].words), 3)

    def test_pagination_is_deterministic_and_does_not_split_groups(self):
        self.bridge_group()
        self.word("雨", "あめ", "rain")
        self.word("飴", "あめ", "candy")
        first = list_homophones(self.db, limit=1)
        second = list_homophones(self.db, limit=1, offset=1)
        self.assertEqual(first.total, 2)
        self.assertEqual(len(first.groups[0].words), 2)
        self.assertNotEqual(first.groups[0].reading, second.groups[0].reading)
        self.assertEqual(first, list_homophones(self.db, limit=1))
        self.assertEqual(list_homophones(self.db, offset=10).groups, [])

    def test_exact_romaji_group_is_ranked_first(self):
        self.word("今日", "きょう", "today", romaji="kyou")
        self.word("京", "きょう", "capital", romaji="kyou")
        self.word("共同", "きょうどう", "cooperation", romaji="kyoudou")
        self.word("協同", "きょうどう", "collaboration", romaji="kyoudou")
        self.assertEqual(list_homophones(self.db, "kyou").groups[0].reading, "きょう")

    def test_repository_avoids_per_word_queries(self):
        self.bridge_group()
        self.db.expunge_all()
        queries = []
        def record(*args):
            queries.append(args[2])
        event.listen(self.engine, "before_cursor_execute", record)
        try:
            list_homophones(self.db)
        finally:
            event.remove(self.engine, "before_cursor_execute", record)
        self.assertEqual(len(queries), 2)

    def test_api_authentication_validation_and_contract(self):
        self.bridge_group()
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        app.dependency_overrides[get_db] = lambda: self.db
        client = TestClient(app)
        self.addCleanup(client.close)
        url = "/api/v1/content/homophones"
        self.assertEqual(client.get(url).status_code, 401)
        app.dependency_overrides[get_current_user] = lambda: object()
        for params in ({"limit": 51}, {"limit": 0}, {"offset": -1}, {"locale": "ja"}, {"q": "a" * 101}):
            self.assertEqual(client.get(url, params=params).status_code, 422)
        response = client.get(url, params={"q": "pont", "locale": "fr", "limit": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["groups"][0]["reading"], "はし")
        self.assertEqual(len(response.json()["groups"][0]["words"]), 2)


if __name__ == "__main__":
    unittest.main()
