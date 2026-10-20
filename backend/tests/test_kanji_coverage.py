from unittest import TestCase

from scripts.audit_vocabulary_kanji import audit, is_kanji


def word(value, level, **extra):
    return {'word': value, 'level': level, 'spelling_level': level, 'reading': '', 'source': 'test', **extra}


class KanjiCoverageTests(TestCase):
    def test_uses_easiest_spelling_level_and_deduplicates_characters(self):
        result = audit([word('分身', 'N1'), word('半分', 'N5'), word('分分', 'N3')], {'半', '身'})
        self.assertEqual(result['missing_count'], 1)
        self.assertEqual(result['missing'][0]['kanji'], '分')
        self.assertEqual(result['missing'][0]['level'], 'N5')
        self.assertEqual(len(result['missing'][0]['occurrences']), 3)

    def test_catalogue_membership_is_not_restricted_to_word_level(self):
        self.assertEqual(audit([word('漢字', 'N5')], {'漢', '字'})['missing'], [])

    def test_uses_spelling_level_not_word_level(self):
        self.assertEqual(audit([word('箸', 'N5', spelling_level='N2')], set())['missing'][0]['level'], 'N2')

    def test_compares_spelling_levels_across_words(self):
        result = audit([word('分身', 'N5', spelling_level='N2'), word('半分', 'N4', spelling_level='N3')], {'身', '半'})
        self.assertEqual(result['missing'][0]['level'], 'N3')
        self.assertEqual(result['missing'][0]['occurrences'][0]['word'], '半分')

    def test_missing_spelling_level_does_not_fall_back_to_word_level(self):
        for level in ('', None, 'N6'):
            with self.assertRaises(ValueError):
                audit([word('箸', 'N5', spelling_level=level)], set())
        self.assertEqual(audit([word('はし', 'N5', spelling_level='')], set())['missing'], [])

    def test_kana_punctuation_and_iteration_marks_are_not_kanji(self):
        result = audit([word('ひらがな・カタカナ/々ヶ〇〆', 'N5')], set())
        self.assertEqual(result['missing'], [])
        self.assertEqual(result['rows_with_kanji'], 0)

    def test_supplementary_and_compatibility_ideographs_are_not_lost(self):
        for character in ('𠮷', '﨑', '龍'):
            self.assertTrue(is_kanji(character))
            self.assertEqual(audit([word(character, 'N2')], {'竜'})['missing'][0]['kanji'], character)

    def test_invalid_level_is_not_silently_ignored(self):
        with self.assertRaises(ValueError):
            audit([word('分', 'N6')], set())
