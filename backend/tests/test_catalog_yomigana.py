"""Conservative pronunciation enrichment, with no dictionary download or TTS."""

from copy import deepcopy
import csv
import hashlib
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import catalog_yomigana as yomigana
from scripts.generate_vocab_audio_google import load_vocabulary, pronunciation_parts


def dictionary_node(surface="塵", kana="ゴミ", accent="2", **overrides):
    features = {
        "lemma": surface, "lemma_id": 101, "kana": kana, "aType": accent,
        "aConType": "C1", "aModType": "*", "pos1": "名詞",
        "pos2": "普通名詞", "pos3": "一般", "pos4": "*",
        "cType": "*", "cForm": "*",
    }
    features.update(overrides)
    return SimpleNamespace(surface=surface, is_unk=False,
                           feature=SimpleNamespace(**features))


def dictionary_tagger(node=None, *, nodes=None, analyses=None):
    node = node or dictionary_node()
    selected = [node] if nodes is None else nodes
    candidates = [selected] if analyses is None else analyses

    class FixtureTagger:
        def __call__(self, _surface):
            return selected

        def nbestToNodeList(self, _surface, count):
            return candidates[:count]

    return FixtureTagger()


def vocabulary_text(rows, headers=None):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=headers or list(rows[0]),
                            delimiter=";", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def enrichment_config(text, **overrides):
    return {
        "version": 1, "candidate_limit": 64,
        "input_vocabulary_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "dictionary_version": "fixture", "fugashi_version": "fixture",
        "unidic_package_version": "fixture", "dictionary_files_sha256": {},
        **overrides,
    }


class YomiganaEncodingTests(unittest.TestCase):
    def test_known_accent_examples_include_phrase_start_and_final_drop(self):
        for kana, accent, expected in (
            ("はし", 1, "^は!し"), ("はし", 2, "^はし!"),
            ("ごみ", 2, "^ごみ!"), ("ねいろ", 0, "^ねいろ"),
        ):
            with self.subTest(kana=kana, accent=accent):
                self.assertEqual(yomigana.accent_yomigana(kana, accent), expected)

    def test_morae_join_small_vowels_but_count_sokuon_nasal_and_length(self):
        self.assertEqual(yomigana.morae("きゃっとしんふぃー"),
                         ["きゃ", "っ", "と", "し", "ん", "ふぃ", "ー"])
        self.assertEqual(yomigana.accent_yomigana("きょう", 1), "^きょ!う")
        self.assertEqual(yomigana.accent_yomigana("ちょっと", 2), "^ちょっ!と")

    def test_malformed_mora_readings_are_rejected(self):
        for reading in ("", "ゃ", "きゃゃ", "っゃ", "んゅ", "ーぁ", "ゕ", "ゖ",
                        "はし/ばし", "はし、はし", "ハシ", "橋", "^は!し"):
            with self.subTest(reading=reading), self.assertRaises(ValueError):
                yomigana.morae(reading)

    def test_accent_must_be_an_integer_within_mora_count(self):
        for accent in (-1, 3, 1.0, "1", None, True, False):
            with self.subTest(accent=accent), self.assertRaises(ValueError):
                yomigana.accent_yomigana("はし", accent)

    def test_normalization_keeps_suru_and_reading_alternatives(self):
        for source, expected in (
            (" ベンキョウ・する ", "べんきょうする"),
            ("ﾊｼ", "はし"), ("あげる（=やる）", "あげる"),
            ("お（ちゃ）", "おちゃ"), ("はし/ばし", "はし/ばし"),
            ("ええ,はい;うん", "ええ、はい、うん"),
        ):
            with self.subTest(source=source):
                self.assertEqual(yomigana.normalize_kana(source), expected)


class YomiganaDictionaryDecisionTests(unittest.TestCase):
    def setUp(self):
        self.row = {"ID": "dust", "Kanji": "塵", "Kana": "ごみ"}

    def assert_plain(self, expected_reason, tagger=None, **kwargs):
        before = deepcopy(self.row)
        result = yomigana.annotate_row(self.row, tagger or dictionary_tagger(), **kwargs)
        self.assertEqual(result["decision"], "plain_kana")
        self.assertEqual(result["reason"], expected_reason)
        self.assertEqual(result["yomigana"], yomigana.normalize_kana(self.row["Kana"]))
        self.assertNotIn("^", result["yomigana"])
        self.assertEqual(self.row, before)
        return result

    def test_unique_exact_dictionary_match_is_annotated_without_mutation(self):
        before = deepcopy(self.row)
        result = yomigana.annotate_row(self.row, dictionary_tagger())
        self.assertEqual(result["yomigana"], "^ごみ!")
        self.assertEqual(result["decision"], "dictionary_annotation")
        self.assertEqual(result["reason"], "unique_exact_dictionary_match")
        self.assertEqual(result["mora_count"], 2)
        self.assertEqual(result["dictionary"]["lemma_id"], 101)
        self.assertEqual(self.row, before)

    def test_explicit_zero_accent_is_not_treated_as_unknown(self):
        result = yomigana.annotate_row(self.row, dictionary_tagger(dictionary_node(accent="0")))
        self.assertEqual(result["yomigana"], "^ごみ")
        self.assertEqual(result["decision"], "dictionary_annotation")

    def test_missing_or_multiple_accents_are_not_guessed(self):
        for accent in (None, "", "*", "0,2", "1/2", "-1", "2.0"):
            with self.subTest(accent=accent):
                self.assert_plain("accent_missing_or_multiple",
                                  dictionary_tagger(dictionary_node(accent=accent)))

    def test_reading_mismatch_keeps_catalogue_kana(self):
        result = self.assert_plain("reading_mismatch",
                                   dictionary_tagger(dictionary_node(kana="チリ")))
        self.assertEqual(result["dictionary"]["kana"], "ちり")
        self.assertEqual(result["yomigana"], "ごみ")

    def test_multiple_tokens_and_partial_surface_are_rejected(self):
        for nodes in ([], [dictionary_node(), dictionary_node()],
                      [dictionary_node(surface="塵の")]):
            with self.subTest(nodes=nodes):
                self.assert_plain("multiple_tokens_or_partial_match",
                                  dictionary_tagger(nodes=nodes))

    def test_unknown_tokens_are_not_annotated(self):
        node = dictionary_node()
        node.is_unk = True
        self.assert_plain("unknown_token", dictionary_tagger(node))

    def test_out_of_bounds_dictionary_accent_is_rejected(self):
        self.assert_plain("accent_out_of_bounds", dictionary_tagger(dictionary_node(accent="3")))

    def test_inflection_requiring_an_accent_rule_is_not_guessed(self):
        self.assert_plain("inflection_requires_accent_rule",
                          dictionary_tagger(dictionary_node(aModType="M1@1")))

    def test_non_exhaustive_nbest_search_is_rejected(self):
        node = dictionary_node()
        result = self.assert_plain("candidate_limit_not_exhaustive",
                                   dictionary_tagger(node, analyses=[[node]] * 3),
                                   candidate_limit=3)
        self.assertEqual(result["analyses_examined"], 3)

    def test_competing_lemma_morphology_or_accent_is_rejected(self):
        first = dictionary_node()
        for overrides in ({"lemma_id": 102}, {"lemma": "別語"},
                          {"pos2": "固有名詞"}, {"accent": "0"}):
            with self.subTest(overrides=overrides):
                other = dictionary_node(**overrides)
                result = self.assert_plain("ambiguous_dictionary_entry",
                                           dictionary_tagger(first, analyses=[[first], [other]]))
                self.assertEqual(result["distinct_matching_candidates"], 2)

    def test_absent_first_candidate_is_rejected(self):
        self.assert_plain("ambiguous_dictionary_entry",
                          dictionary_tagger(analyses=[[dictionary_node(kana="チリ")]]))

    def test_other_readings_are_not_confused_with_the_expected_one(self):
        first = dictionary_node()
        result = yomigana.annotate_row(self.row, dictionary_tagger(
            first, analyses=[[first], [dictionary_node(kana="チリ", accent="0")]]))
        self.assertEqual(result["yomigana"], "^ごみ!")

    def test_duplicate_nbest_paths_do_not_create_false_ambiguity(self):
        first = dictionary_node()
        result = yomigana.annotate_row(self.row, dictionary_tagger(
            first, analyses=[[first], [deepcopy(first)]]))
        self.assertEqual(result["yomigana"], "^ごみ!")

    def test_catalogue_homographs_are_not_resolved_by_dictionary_cost(self):
        self.assert_plain("catalogue_homograph", duplicate=True)

    def test_annotations_and_alternatives_remain_plain_kana(self):
        for kana, kanji in (("ごみ/ちり", "塵"), ("べんきょう・する", "勉強・する"),
                            ("ごみ", "塵/ごみ"), ("ごみ（=ちり）", "塵")):
            with self.subTest(kana=kana, kanji=kanji):
                self.row.update(Kana=kana, Kanji=kanji)
                self.assert_plain("annotations_or_alternatives")

    def test_invalid_reading_does_not_reach_dictionary(self):
        self.row["Kana"] = "ご3み"
        self.assert_plain("invalid_or_multiple_reading")


class YomiganaCatalogueTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"Level": "N4", "KanjiLevel": "N3", "ID": "dust", "Kanji": "塵",
             "Kana": "ごみ", "Romaji": "gomi", "French": "déchets ; poussière",
             "Audio": "/audio/existing.wav", "Notes": 'une note; "citée"\nseconde ligne'},
            {"Level": "N2", "KanjiLevel": "N2", "ID": "tone", "Kanji": "音色",
             "Kana": "ねいろ", "Romaji": "neiro", "French": "timbre",
             "Audio": "", "Notes": ""},
        ]
        self.notices = {"BSD": "fixture license\n", "AUTHORS": "Fixture Authors\n"}
        nodes = {"塵": dictionary_node(),
                 "音色": dictionary_node(surface="音色", kana="ネイロ", accent="0", lemma_id=102)}

        class CatalogueTagger:
            def __call__(self, surface):
                return [nodes[surface]]

            def nbestToNodeList(self, surface, _count):
                return [[nodes[surface]]]

        self.tagger = CatalogueTagger()

    def enrich(self, text, **overrides):
        with patch.object(yomigana, "load_dictionary", return_value=(self.tagger, self.notices)):
            return yomigana.enrich_vocabulary(text, enrichment_config(text, **overrides))

    def test_adds_only_yomigana_immediately_after_kana_and_preserves_order(self):
        original = deepcopy(self.rows)
        text = vocabulary_text(self.rows)
        enriched, audit, notices = self.enrich(text)
        reader = csv.DictReader(io.StringIO(enriched), delimiter=";")
        expected_headers = list(self.rows[0])
        expected_headers.insert(expected_headers.index("Kana") + 1, "Yomigana")
        self.assertEqual(reader.fieldnames, expected_headers)
        actual = list(reader)
        self.assertEqual([row.pop("Yomigana") for row in actual], ["^ごみ!", "^ねいろ"])
        self.assertEqual(actual, original)
        self.assertEqual(self.rows, original)
        self.assertEqual(list(audit["entries"]), ["dust", "tone"])
        self.assertEqual(audit["summary"]["rows"], 2)
        self.assertEqual(audit["summary"]["dictionary_annotations"], 2)
        self.assertEqual(audit["summary"]["plain_kana"], 0)
        self.assertEqual(audit["input_vocabulary_sha256"], hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual(audit["output_vocabulary_sha256"], hashlib.sha256(enriched.encode()).hexdigest())
        self.assertEqual(notices, self.notices)

    def test_duplicate_surface_reading_with_distinct_ids_stays_unaccented(self):
        rows = [self.rows[0], {**self.rows[0], "ID": "another-sense", "French": "autre sens"}]
        enriched, audit, _ = self.enrich(vocabulary_text(rows))
        actual = list(csv.DictReader(io.StringIO(enriched), delimiter=";"))
        self.assertEqual([row["Yomigana"] for row in actual], ["ごみ", "ごみ"])
        self.assertEqual([row["ID"] for row in actual], ["dust", "another-sense"])
        self.assertEqual(audit["summary"]["reasons"], {"catalogue_homograph": 2})

    def test_suru_annotation_removes_separator_not_the_verb(self):
        row = {**self.rows[0], "Kanji": "勉強・する", "Kana": "べんきょう・する"}
        enriched, audit, _ = self.enrich(vocabulary_text([row]))
        actual = next(csv.DictReader(io.StringIO(enriched), delimiter=";"))
        self.assertEqual(actual["Kana"], "べんきょう・する")
        self.assertEqual(actual["Yomigana"], "べんきょうする")
        self.assertEqual(audit["summary"]["plain_kana"], 1)

    def test_changed_input_hash_is_refused_before_loading_dictionary(self):
        text = vocabulary_text(self.rows)
        with patch.object(yomigana, "load_dictionary") as loader:
            with self.assertRaisesRegex(ValueError, "fingerprint changed"):
                yomigana.enrich_vocabulary(text, enrichment_config(text, input_vocabulary_sha256="0" * 64))
            loader.assert_not_called()

    def test_invalid_configuration_is_rejected(self):
        text = vocabulary_text(self.rows)
        for overrides in ({"version": 2}, {"candidate_limit": 1}):
            with self.subTest(overrides=overrides), self.assertRaisesRegex(ValueError, "configuration"):
                self.enrich(text, **overrides)

    def test_existing_yomigana_column_or_missing_required_column_is_rejected(self):
        for row in ({**self.rows[0], "Yomigana": "^ごみ!"},
                    {key: value for key, value in self.rows[0].items() if key != "Kana"}):
            with self.subTest(headers=list(row)), self.assertRaisesRegex(ValueError, "schema"):
                self.enrich(vocabulary_text([row]))

    def test_malformed_csv_and_duplicate_ids_are_rejected(self):
        cases = (
            ("ID;Kanji;Kana\nid;塵\n", "Malformed"),
            ("ID;Kanji;Kana\nid;塵;ごみ;extra\n", "Malformed"),
            (vocabulary_text([self.rows[0], self.rows[0]]), "Duplicate"),
        )
        for text, message in cases:
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, message):
                self.enrich(text)

    def test_non_phonetic_reading_fails_instead_of_being_silently_exported(self):
        text = vocabulary_text([{**self.rows[0], "Kana": "ごみ?"}])
        with self.assertRaisesRegex(ValueError, "Unresolved non-phonetic reading: dust"):
            self.enrich(text)

    def test_pipeline_preserves_other_files_and_emits_provenance_and_licenses(self):
        files = {"vocabulary.csv": vocabulary_text(self.rows), "grammar.csv": "unchanged grammar\n",
                 "kanji.csv": "unchanged kanji\n", "_audit/source-map.csv": "unchanged map\n"}
        original = deepcopy(files)
        with patch.object(yomigana, "load_dictionary", return_value=(self.tagger, self.notices)):
            result = yomigana.apply_yomigana(files, enrichment_config(files["vocabulary.csv"]))
        self.assertEqual(files, original)
        for name, content in original.items():
            if name != "vocabulary.csv":
                self.assertEqual(result[name], content)
        self.assertEqual(result["_audit/unidic/BSD"], self.notices["BSD"])
        self.assertEqual(result["_audit/unidic/AUTHORS"], self.notices["AUTHORS"])
        audit = json.loads(result["_audit/yomigana.json"])
        self.assertEqual(audit["source"]["dictionary_version"], "fixture")
        self.assertEqual(audit["summary"]["rows"], 2)

    def bridge_review_fixture(self):
        row = {**self.rows[0], "ID": "bridge", "Kanji": "橋", "Kana": "はし",
               "Romaji": "hashi", "English": "bridge", "French": "pont"}
        first = dictionary_node(surface="橋", kana="ハシ", accent="2", lemma_id=29677)
        other = dictionary_node(surface="橋", kana="ハシ", accent="2", lemma_id=99999)
        self.tagger = dictionary_tagger(first, analyses=[[first], [other]])
        review = {"ID": "bridge", "expect": {key: row[key] for key in ("Kanji", "Kana", "English", "French")},
                  "lemma_id": 29677, "accent": 2, "reason": "The gloss explicitly selects bridge.",
                  "reference": "https://docs.cloud.google.com/text-to-speech/docs/phonemes#japanese_yomigana"}
        return vocabulary_text([row]), review

    def test_reviewed_bridge_sense_has_auditable_final_mora_drop(self):
        text, review = self.bridge_review_fixture()
        original_review = deepcopy(review)
        enriched, audit, _ = self.enrich(text, reviewed_overrides=[review])
        row = next(csv.DictReader(io.StringIO(enriched), delimiter=";"))
        self.assertEqual(row["Yomigana"], "^はし!")
        self.assertEqual({key: value for key, value in row.items() if key != "Yomigana"},
                         next(csv.DictReader(io.StringIO(text), delimiter=";")))
        entry = audit["entries"]["bridge"]
        self.assertEqual(entry["decision"], "reviewed_dictionary_annotation")
        self.assertEqual(entry["reason"], "reviewed_sense_disambiguation")
        self.assertEqual(entry["review"], original_review)
        self.assertEqual(entry["dictionary"]["lemma_id"], 29677)
        self.assertEqual(audit["summary"]["automatic_annotations"], 0)
        self.assertEqual(audit["summary"]["reviewed_annotations"], 1)
        self.assertEqual(audit["summary"]["dictionary_annotations"], 1)
        self.assertEqual(audit["summary"]["plain_kana"], 0)
        self.assertEqual(review, original_review)

    def test_reviewed_override_rejects_changed_expected_field(self):
        text, review = self.bridge_review_fixture()
        for field, replacement in (("Kana", "きょう"), ("Kanji", "箸"),
                                    ("English", "chopsticks"), ("French", "baguettes")):
            candidate = deepcopy(review)
            candidate["expect"][field] = replacement
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "evidence changed: bridge"):
                self.enrich(text, reviewed_overrides=[candidate])

    def test_reviewed_override_rejects_changed_lemma_or_accent(self):
        text, review = self.bridge_review_fixture()
        for field, replacement in (("lemma_id", 99999), ("accent", 0), ("accent", 1)):
            with self.subTest(field=field, replacement=replacement):
                with self.assertRaisesRegex(ValueError, "evidence changed: bridge"):
                    self.enrich(text, reviewed_overrides=[{**review, field: replacement}])

    def test_reviewed_override_requires_reason_and_source(self):
        text, review = self.bridge_review_fixture()
        for field in ("reason", "reference"):
            for replacement in ("", None):
                with self.subTest(field=field, replacement=replacement):
                    with self.assertRaisesRegex(ValueError, "evidence changed: bridge"):
                        self.enrich(text, reviewed_overrides=[{**review, field: replacement}])

    def test_reviewed_override_requires_unique_existing_id(self):
        text, review = self.bridge_review_fixture()
        for reviews in ([review, review], [{**review, "ID": "not-in-catalogue"}]):
            with self.subTest(reviews=reviews):
                with self.assertRaisesRegex(ValueError, "Duplicate or missing reviewed Yomigana ID"):
                    self.enrich(text, reviewed_overrides=reviews)

    def test_reviewed_override_requires_all_lexical_and_sense_expectations(self):
        text, review = self.bridge_review_fixture()
        for missing in ("Kanji", "Kana", "English", "French"):
            candidate = deepcopy(review)
            del candidate["expect"][missing]
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, "evidence changed: bridge"):
                self.enrich(text, reviewed_overrides=[candidate])

    def test_reviewed_override_cannot_bypass_reading_or_inflection_checks(self):
        text, review = self.bridge_review_fixture()
        for features in ({"kana": "キョウ"}, {"aModType": "M1@1"}):
            node = dictionary_node(surface="橋", kana="ハシ", accent="2", lemma_id=29677)
            for field, value in features.items():
                setattr(node.feature, field, value)
            self.tagger = dictionary_tagger(node)
            with self.subTest(features=features), self.assertRaisesRegex(ValueError, "evidence changed: bridge"):
                self.enrich(text, reviewed_overrides=[review])

    def test_reviewed_override_cannot_bypass_non_exhaustive_candidates(self):
        text, review = self.bridge_review_fixture()
        node = dictionary_node(surface="橋", kana="ハシ", accent="2", lemma_id=29677)
        self.tagger = dictionary_tagger(node, analyses=[[node]] * 3)
        with self.assertRaisesRegex(ValueError, "evidence changed: bridge"):
            self.enrich(text, reviewed_overrides=[review], candidate_limit=3)


class YomiganaSavedCatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = load_vocabulary(yomigana.ROOT / "contenu csv" / "consolidated")

    def test_all_saved_yomigana_match_generator_readings_without_google_client(self):
        self.assertEqual(len(self.entries), 8038)
        with patch("scripts.generate_vocab_audio_google.create_google_client",
                   side_effect=AssertionError("Corpus validation must not create a TTS client")):
            for entry in self.entries:
                with self.subTest(identity=entry["id"]):
                    self.assertTrue(entry.get("yomigana"))
                    self.assertTrue(pronunciation_parts(entry))

    def test_saved_examples_have_expected_reading_and_accent(self):
        for surface, reading, expected in (("箸", "はし", "^は!し"),
                                           ("橋", "はし", "^はし!"),
                                           ("塵", "ごみ", "^ごみ!"),
                                           ("音色", "ねいろ", "^ねいろ")):
            with self.subTest(surface=surface, reading=reading):
                matching = [entry for entry in self.entries
                            if entry["japanese"] == surface and entry["reading"] == reading]
                self.assertEqual(len(matching), 1)
                self.assertEqual(matching[0]["yomigana"], expected)
                self.assertEqual(pronunciation_parts(matching[0]), [expected])


if __name__ == "__main__":
    unittest.main()
