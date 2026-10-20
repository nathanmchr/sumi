from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.learning import LearningState
from app.services.content_service import kanji_out, vocabulary_out
from app.utils.enums import ContentType, ReviewStatus


class VocabularyMasteryTests(TestCase):
    def setUp(self) -> None:
        self.audio = patch("app.services.vocabulary_audio.catalog_audio", return_value=(False, None))
        self.audio.start()
        self.addCleanup(self.audio.stop)
        self.item = SimpleNamespace(
            catalog_id=None, source_order=None, kanji_level_code=None,
            id="vocabulary-会う", slug="会う", japanese="会う", reading="あう", romaji="au",
            furigana_segments=[], translation="to meet", part_of_speech="verb",
            jlpt_level_code="N5", audio_url=None, notes=None, translations=[],
            example_sentences=[], kanji_links=[],
        )
        # An isolated, in-memory table verifies the actual user/category/item filters.
        self.engine = create_engine("sqlite://")
        LearningState.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def add_state(self, user_id="user-a", content_type=ContentType.vocabulary, content_id="vocabulary-会う", mastery=0.64):
        state = LearningState(
            user_id=user_id, content_type=content_type, content_id=content_id,
            mastery=mastery, status=ReviewStatus.known,
        )
        self.db.add(state)
        self.db.commit()
        return state

    def test_detail_exposes_the_current_users_mastery_and_computed_status(self) -> None:
        self.add_state(user_id="user-b", mastery=0.99)
        self.add_state(content_type=ContentType.kanji, mastery=0.1)
        self.add_state(content_id="another-word", mastery=0.2)
        state = self.add_state()
        with patch("app.services.content_service.memory_status", return_value=ReviewStatus.fragile) as status:
            result = vocabulary_out(self.db, self.item, user_id="user-a")

        self.assertEqual(result.mastery, 0.64)
        self.assertEqual(result.status, "fragile")
        self.assertIs(status.call_args.args[0], state)

    def test_unlearned_word_does_not_reuse_another_users_progress(self) -> None:
        self.add_state(user_id="user-b", mastery=0.99)
        result = vocabulary_out(self.db, self.item, user_id="user-a")
        self.assertEqual(result.mastery, 0.0)
        self.assertEqual(result.status, "new")

    def test_public_catalog_does_not_query_personal_progress(self) -> None:
        db = Mock()
        result = vocabulary_out(db, self.item)
        db.query.assert_not_called()
        self.assertEqual(result.mastery, 0.0)
        self.assertEqual(result.status, "new")

    def test_display_romaji_preserves_source_format_and_missing_values(self) -> None:
        self.item.romaji_search = "honya"
        for value in ["hon'ya", "ohayou gozaimasu", "", None]:
            self.item.romaji = value
            self.assertEqual(vocabulary_out(Mock(), self.item).romaji, value or "")


class RelatedContentMeaningTests(TestCase):
    def setUp(self) -> None:
        self.audio = patch("app.services.vocabulary_audio.catalog_audio", return_value=(False, None))
        self.audio.start()
        self.addCleanup(self.audio.stop)

    def test_vocabulary_links_expose_localized_kanji_meanings(self) -> None:
        kanji = SimpleNamespace(
            id="kanji-会",
            character="会",
            slug="会",
            meanings=["meeting"],
            translations=[SimpleNamespace(locale="fr", meanings=["rencontre"])],
            jlpt_level_code="N4",
        )
        item = SimpleNamespace(
            catalog_id=None, source_order=None, kanji_level_code=None,
            id="vocabulary-会う",
            slug="会う",
            japanese="会う",
            reading="あう",
            romaji="au",
            furigana_segments=[],
            translation="to meet",
            part_of_speech="verb",
            jlpt_level_code="N5",
            audio_url=None,
            notes=None,
            translations=[SimpleNamespace(locale="fr", translation="rencontrer", notes=None)],
            example_sentences=[],
            kanji_links=[SimpleNamespace(kanji_item=kanji, kanji_position=1, is_primary=True)],
        )

        result = vocabulary_out(None, item, locale="fr")

        self.assertEqual(result.kanji_links[0].meanings, ["rencontre"])
        self.assertEqual(result.kanji_links[0].jlpt_level_code, "N4")
        self.assertEqual(result.jlpt_level_code, "N5")

    def test_kanji_links_expose_localized_vocabulary_translation(self) -> None:
        vocabulary = SimpleNamespace(
            source_order=None,
            id="vocabulary-会う",
            japanese="会う",
            reading="あう",
            furigana_segments=[
                {"surface": "会", "reading": "あ", "kanji_ids": ["kanji-会"]},
                {"surface": "う", "reading": "", "kanji_ids": []},
            ],
            translation="to meet",
            audio_url="/audio/vocabulary/meet.wav",
            jlpt_level_code="N4",
            translations=[SimpleNamespace(locale="fr", translation="rencontrer")],
        )
        item = SimpleNamespace(
            id="kanji-会",
            catalog_id=None, source_order=None,
            character="会",
            slug="会",
            meanings=["meeting"],
            onyomi=["カイ"],
            kunyomi=["あ.う"],
            radicals=[],
            mnemonic=None,
            jlpt_level_code="N5",
            translations=[SimpleNamespace(locale="fr", meanings=["rencontre"], mnemonic=None)],
            vocabulary_links=[SimpleNamespace(vocabulary_item=vocabulary)],
        )

        result = kanji_out(None, item, locale="fr")

        self.assertEqual(result.linked_vocabulary[0].translation, "rencontrer")
        self.assertEqual(result.linked_vocabulary[0].jlpt_level_code, "N4")
        self.assertEqual(result.jlpt_level_code, "N5")
        self.assertEqual(result.linked_vocabulary[0].furigana_segments, vocabulary.furigana_segments)
        self.assertEqual(result.linked_vocabulary[0].audio_url, "/audio/vocabulary/meet.wav")
