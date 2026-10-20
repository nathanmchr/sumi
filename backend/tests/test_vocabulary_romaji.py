import csv
import tempfile
from pathlib import Path
from unittest import TestCase

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.content import VocabularyItem
from app.repositories.content_repository import ContentRepository
from scripts.prepare_vocabulary_romaji import prepare


class DisplayRomajiTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.engine = create_engine('sqlite://')
        self.addCleanup(self.engine.dispose)
        VocabularyItem.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)
        self.word = VocabularyItem(slug='bookshop', japanese='本屋', reading='ほんや',
                                   romaji_search='honya', translation='bookshop',
                                   part_of_speech='noun', jlpt_level_code='N5')
        self.db.add(self.word)
        self.db.commit()
        self.write_csv([['本屋', 'ほんや', "hon'ya"]])

    def write_csv(self, rows):
        with (self.path / 'JLPT N5 Vocab.csv').open('w', encoding='utf-8', newline='') as handle:
            writer = csv.writer(handle, delimiter=';')
            writer.writerow(['Kanji', 'Hiragana', 'Romaji'])
            writer.writerows(rows)

    def snapshot(self):
        return dict(self.db.execute(select(VocabularyItem.__table__)).mappings().one())

    def test_exact_source_format_dry_run_and_idempotency(self):
        before = self.snapshot()
        self.assertEqual(prepare(self.db, self.path)['changed'], 1)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(prepare(self.db, self.path, write=True)['changed'], 1)
        self.db.commit()
        self.assertEqual(self.snapshot(), {**before, 'romaji': "hon'ya"})
        self.assertEqual(prepare(self.db, self.path, write=True)['changed'], 0)

    def test_reading_mismatch_does_not_guess(self):
        self.write_csv([['本屋', 'べつ', 'betsu']])
        self.assertEqual(prepare(self.db, self.path, write=True)['missing'], 1)
        self.assertEqual(self.snapshot()['romaji'], '')

    def test_conflicting_sources_abort_before_any_write(self):
        self.write_csv([['本屋', 'ほんや', "hon'ya"], ['本屋', 'ほんや', 'honya']])
        with self.assertRaises(ValueError):
            prepare(self.db, self.path, write=True)
        self.assertEqual(self.snapshot()['romaji'], '')

    def test_import_keeps_display_romaji_separate_from_search(self):
        payload = {key: value for key, value in self.snapshot().items()
                   if key not in ('id', 'created_at', 'updated_at')}
        payload['romaji'] = "hon'ya"
        ContentRepository(self.db).upsert_vocabulary(payload)
        self.db.commit()
        self.assertEqual(self.snapshot()['romaji'], "hon'ya")
        self.assertEqual(self.snapshot()['romaji_search'], 'honya')
        payload.pop('romaji')
        ContentRepository(self.db).upsert_vocabulary(payload)
        self.db.commit()
        self.assertEqual(self.snapshot()['romaji'], "hon'ya")
