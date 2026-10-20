"""CONTENT_TEST_POSTGRES=1 runs read-only searches in a disposable schema."""
import os
import unittest
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.database import engine as configured_engine
from app.models.base import Base
from app.models.content import GrammarItem, JLPTLevel, KanjiItem, VocabularyItem, VocabularyTranslation
from app.repositories.content_repository import ContentRepository
from app.services.content_service import search_content
from app.utils.romaji import normalize_romaji, romaji_search_key


class SearchNormalizationTests(unittest.TestCase):
    def test_romaji_normalization_and_explicit_source_priority(self):
        self.assertEqual(normalize_romaji("　ＫＹＯＵ　"), 'kyou')
        self.assertEqual(normalize_romaji("shin'you"), 'shinyou')
        self.assertEqual(normalize_romaji('nakereba naranai'), 'nakerebanaranai')
        self.assertEqual(romaji_search_key(['きょう']), 'kyou')
        self.assertEqual(romaji_search_key(['こんにちは'], 'konnichiwa'), 'konnichiwa')
        self.assertEqual(romaji_search_key(['コーヒー']), 'koohii')
        self.assertEqual(romaji_search_key(['ガク', 'まな.ぶ']), 'gaku / manabu')
        self.assertEqual(romaji_search_key(['garbled', '今日']), '')
        self.assertEqual(romaji_search_key(['ー']), '')


@unittest.skipUnless(os.getenv('CONTENT_TEST_POSTGRES') == '1', 'Opt-in isolated PostgreSQL tests')
class ContentSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schema = 'content_search_test_' + uuid4().hex
        admin = create_engine(configured_engine.url)
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA {schema}'))

        def cleanup():
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
            admin.dispose()

        cls.addClassCleanup(cleanup)
        cls.engine = create_engine(configured_engine.url, connect_args={'options': f'-csearch_path={schema}'})
        cls.addClassCleanup(cls.engine.dispose)
        Base.metadata.create_all(cls.engine)
        with Session(cls.engine) as db:
            db.add_all([JLPTLevel(code='N5', rank=5, label='N5'), JLPTLevel(code='N4', rank=4, label='N4')])
            db.flush()
            rows = [
                ('今日', 'きょう', 'today', 'N5'),
                ('不味い', 'まずい', 'unappetizing', 'N5'),
                ('お母さん', 'おかあさん', 'mother', 'N5'),
                ('日曜日', 'にちようび', 'Sunday', 'N5'),
                ('学校', 'がっこう', 'school', 'N5'),
                ('猫', 'ねこ', 'cat', 'N4'),
                ('テレビ', 'テレビ', 'television', 'N5'),
            ]
            for word, reading, translation, level in rows:
                db.add(VocabularyItem(slug=word, japanese=word, reading=reading, translation=translation,
                                      part_of_speech='other', jlpt_level_code=level, furigana_segments=[],
                                      romaji_search=romaji_search_key([reading])))
            db.flush()
            mother = db.query(VocabularyItem).filter_by(japanese='お母さん').one()
            db.add(VocabularyTranslation(vocabulary_item_id=mother.id, locale='fr', translation='mère'))
            db.add_all([
                KanjiItem(character='学', slug='学', meanings=['study'], onyomi=['ガク'], kunyomi=['まな.ぶ'], romaji_search='gaku / manabu', jlpt_level_code='N5'),
                KanjiItem(character='会', slug='会', meanings=['meet'], onyomi=['カイ'], kunyomi=['あ.う'], romaji_search='kai / au', jlpt_level_code='N4'),
                KanjiItem(character='火', slug='火', meanings=['fire'], onyomi=['カ'], kunyomi=['ひ', '-び'], romaji_search='ka / hi / bi', jlpt_level_code='N5'),
            ])
            db.add(GrammarItem(slug='obligation', title='なければならない', structure='nakereba naranai',
                               romaji_search='nakerebanaranai', explanation='must', nuances='', jlpt_level_code='N4'))
            db.commit()

    def setUp(self):
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)
        self.repo = ContentRepository(self.db)

    def test_full_partial_romaji_and_existing_kana(self):
        for word, queries in {
            '今日': ['きょう', 'kyou', 'KYOU', 'ｋｙｏｕ', ' kyou '],
            '不味い': ['mazu', 'mazui', 'MAZUI'],
            'お母さん': ['okaasan', 'kaasan'],
            '日曜日': ['nichiyoubi', 'youbi'],
            '学校': ['gakkou', 'gakk'],
            'テレビ': ['terebi'],
        }.items():
            for query in queries:
                with self.subTest(query=query):
                    self.assertIn(word, [item.japanese for item in self.repo.list_vocabulary(search=query)])

    def test_kanji_romaji_readings(self):
        for query, word in [('gaku', '学'), ('GAKU', '学'), ('manabu', '学'), ('mana', '学'), ('au', '会'), ('hi', '火'), ('bi', '火')]:
            with self.subTest(query=query):
                self.assertIn(word, [item.character for item in self.repo.list_kanji(search=query)])
        self.assertEqual(self.repo.list_kanji(search='gakumanabu'), [])

    def test_grammar_romaji_and_spacing(self):
        for query in ['nakereba', 'nakerebanaranai', 'nakereba naranai', 'NAKEREBA NARANAI', 'なければ']:
            self.assertEqual([item.title for item in self.repo.list_grammar(search=query)], ['なければならない'])
        self.assertEqual(self.repo.list_grammar('N5', 'nakereba'), [])

    def test_existing_spelling_translation_and_level_filters(self):
        self.assertEqual([v.japanese for v in self.repo.list_vocabulary(search='mère', locale='fr')], ['お母さん'])
        self.assertEqual([v.japanese for v in self.repo.list_vocabulary(search='SCHOOL')], ['学校'])
        self.assertEqual([v.japanese for v in self.repo.list_vocabulary(search='不味')], ['不味い'])
        self.assertEqual(self.repo.list_vocabulary('N5', 'ねこ'), [])
        self.assertEqual([v.japanese for v in self.repo.list_vocabulary('N4', 'NEKO')], ['猫'])
        self.assertEqual(self.repo.list_kanji('N5', 'au'), [])
        self.assertEqual([k.character for k in self.repo.list_kanji(search='meet')], ['会'])
        self.assertEqual(len(self.repo.list_vocabulary(limit=2)), 2)

    def test_literal_wildcards_empty_and_unmatched_queries(self):
        for query in ['%', '_', '.', 'zzzzzz']:
            self.assertEqual(self.repo.list_vocabulary(search=query), [])
            self.assertEqual(self.repo.list_kanji(search=query), [])
        self.assertEqual(len(self.repo.list_vocabulary(search='　 ')), 7)

    def test_global_search_uses_the_same_readings(self):
        self.assertIn('今日', [item.title for item in search_content(self.db, 'kyou')])
        self.assertIn('学', [item.title for item in search_content(self.db, 'gaku')])
        self.assertIn('火', [item.title for item in search_content(self.db, 'hi')])

    def test_upsert_refreshes_romaji_search_keys(self):
        word = self.db.query(VocabularyItem).filter_by(japanese='学校').one()
        payload = dict(slug=word.slug, japanese=word.japanese, reading=word.reading, translation=word.translation,
                       jlpt_level_code='N5', part_of_speech='other')
        self.repo.upsert_vocabulary({**payload, 'romaji': 'gakkou-source'})
        self.assertIn('学校', [item.japanese for item in self.repo.list_vocabulary(search='gakkousource')])
        self.repo.upsert_vocabulary(payload)
        self.db.expire_all()
        self.assertEqual(self.repo.list_vocabulary(search='gakkousource'), [])
        self.assertIn('学校', [item.japanese for item in self.repo.list_vocabulary(search='gakkou')])

    def test_exact_readings_rank_before_partial_matches_and_global_limit(self):
        for index in range(10):
            self.db.add(VocabularyItem(slug=f'partial-{index}', japanese=f'共学{index}', reading='きょうがく',
                                       translation='coeducation', part_of_speech='other', jlpt_level_code='N4',
                                       romaji_search='kyougaku'))
        self.db.flush()
        self.assertEqual(self.repo.list_vocabulary(search='kyou', limit=1)[0].japanese, '今日')
        self.assertIn('今日', [item.title for item in search_content(self.db, 'kyou')])
        self.db.add(VocabularyItem(slug='tomorrow', japanese='明日', reading='あす / あした',
                                   translation='tomorrow', part_of_speech='other', jlpt_level_code='N5',
                                   romaji_search='asu / ashita'))
        self.db.flush()
        self.assertEqual(self.repo.list_vocabulary(search='asu', limit=1)[0].japanese, '明日')
