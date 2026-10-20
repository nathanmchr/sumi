import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.consolidate_content_csv import (
    ROOT, HEADERS, LEVELS, Source, build_catalog, canonical_row,
    combine_meanings, group_sources, meaning_parts, normalized,
)


def source(word, kana, english, french="", level="N5", order=1, category="vocabulary"):
    raw = {"Kanji": word, "English": english, "French": french, "Romaji": "test"}
    raw["Hiragana" if category == "vocabulary" else "Kana"] = kana
    raw["Furigana"] = json.dumps([{"surface": word or kana, "reading": kana}], ensure_ascii=False)
    return Source(category, f"JLPT {level} test.csv", order + 1, order, level, raw)


class ConsolidationRulesTests(unittest.TestCase):
    def test_merge_stays_at_first_appearance_and_uses_kanji_audio(self):
        records = [source("", "はし", "chopsticks", "baguettes"),
                   source("犬", "いぬ", "dog", "chien", order=2),
                   source("箸", "はし", "chopsticks", "baguettes", "N2", 3),
                   source("橋", "はし", "bridge", "pont", order=4)]
        groups, _ = group_sources(records, {("はし", "chopsticks"): "箸"})
        self.assertEqual(groups, [[0, 2], [1], [3]])
        row = canonical_row(records, groups[0], {("箸", "はし"): "/kanji.wav", ("はし", "はし"): "/kana.wav"})
        self.assertEqual((row["Level"], row["KanjiLevel"], row["Kanji"], row["Kana"]),
                         ("N5", "N2", "箸", "はし"))
        self.assertEqual(row["Audio"], "/kanji.wav")
        self.assertEqual(json.loads(row["Furigana"])[0]["surface"], "箸")

    def test_same_kana_different_senses_are_not_duplicates(self):
        records = [source("", "あの", "that over there", order=1),
                   source("", "あの", "um...", order=2)]
        groups, issues = group_sources(records, {})
        self.assertEqual(groups, [[0], [1]])
        ids = [canonical_row(records, group, {})["ID"] for group in groups]
        self.assertEqual(len(set(ids)), 2)
        self.assertTrue(issues)

    def test_shared_audio_does_not_authorize_different_uses_or_bad_translations(self):
        records = [source("", "かける", "to call by phone", order=1),
                   source("掛ける", "かける", "to hang something", order=2),
                   source("", "せっけん", "Economy", "savon", order=3),
                   source("石鹸", "せっけん", "soap", "savon", order=4)]
        groups, issues = group_sources(records, {("かける", "to call by phone"): "掛ける", ("せっけん", "economy"): "石鹸"})
        self.assertEqual(len(groups), 4)
        self.assertEqual(sum(issue[0] == "fusion suspendue" for issue in issues), 2)

    def test_missing_or_ambiguous_target_never_merges(self):
        records = [source("", "かな", "meaning", order=1),
                   source("仮名", "かな", "meaning one", order=2),
                   source("仮名", "かな", "meaning two", order=3)]
        for target in ("仮名", "不存在"):
            groups, issues = group_sources(records, {("かな", "meaning"): target})
            self.assertEqual(len(groups), 3)
            self.assertTrue(issues)

    def test_same_english_and_reading_do_not_merge_different_kanji(self):
        records = [source("保証", "ほしょう", "guarantee", order=1),
                   source("保障", "ほしょう", "guarantee", order=2)]
        groups, issues = group_sources(records, {})
        self.assertEqual(groups, [[0], [1]])
        self.assertEqual(issues[0][0], "graphies kanji à examiner")

    def test_new_grammar_sense_does_not_inherit_an_old_merge_approval(self):
        records = [source("", "ながらも", "but; although; despite ~", order=1, category="grammar"),
                   source("", "ながらも", "although / even while", order=2, category="grammar"),
                   source("", "ながらも", "another unreviewed use", order=3, category="grammar")]
        groups, _ = group_sources(records, {})
        self.assertEqual(groups, [[0, 1], [2]])

    def test_meaning_union_retains_parenthetical_commas_and_unique_clauses(self):
        values = ["spring (e.g. coil, leaf), elastic", "elastic; flexible"]
        result = combine_meanings(values)
        self.assertEqual(meaning_parts(result), ["spring (e.g. coil, leaf)", "elastic", "flexible"])

    def test_annotation_is_preserved_and_kana_is_not_invented(self):
        record = source("ノー", "（no）", "", "non")
        row = canonical_row([record], [0], {("ノー", "（no）"): "/original.wav"})
        self.assertEqual((row["Kanji"], row["Kana"], row["KanjiLevel"]), ("", "ノー", ""))
        self.assertIn("（no）", row["Notes"])
        self.assertEqual(row["Audio"], "/original.wav")


class ConsolidationCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files, cls.summary = build_catalog(
            ROOT / "contenu csv", ROOT / "audio/vocabulary/manifest.json",
            ROOT / "backend/app/data/vocabulary_audio_aliases.csv",
        )

    def rows(self, name):
        return list(csv.DictReader(io.StringIO(self.files[name]), delimiter=";"))

    def test_schema_and_counts_cover_all_fifteen_sources(self):
        for category, original_count in (("vocabulary", 8410), ("grammar", 666), ("kanji", 2211)):
            reader = csv.DictReader(io.StringIO(self.files[f"{category}.csv"]), delimiter=";")
            expected_headers = list(HEADERS[category])
            if category == "vocabulary":
                expected_headers.insert(expected_headers.index("Kana") + 1, "Yomigana")
            self.assertEqual(reader.fieldnames, expected_headers)
            self.assertEqual(self.summary[category]["source_rows"], original_count)
            self.assertEqual(len(list(reader)), self.summary[category]["rows"])
        self.assertEqual(HEADERS["vocabulary"][:2], ["Level", "KanjiLevel"])
        self.assertNotIn("KanaLevel", HEADERS["vocabulary"])

    def test_order_is_exactly_first_occurrence_order_not_alphabetic(self):
        provenance = self.rows("_audit/source-map.csv")
        for category in HEADERS:
            seen = []
            mappings = [r for r in provenance if r["Category"] == category]
            self.assertEqual([int(r["SourceOrder"]) for r in mappings], list(range(1, len(mappings) + 1)))
            for mapping in mappings:
                if mapping["CanonicalID"] not in seen:
                    seen.append(mapping["CanonicalID"])
            output = self.rows(f"{category}.csv")
            self.assertEqual([r["ID"] for r in output], seen)
            self.assertEqual([LEVELS.index(r["Level"]) for r in output], sorted(LEVELS.index(r["Level"]) for r in output))

    def test_every_original_row_is_preserved_and_mapped_once(self):
        originals = {}
        for path in (ROOT / "contenu csv").glob("JLPT * *.csv"):
            with path.open(encoding="utf-8-sig", newline="") as handle:
                for index, row in enumerate(csv.DictReader(handle, delimiter=";"), 2):
                    originals[(path.name, index)] = row
        mappings = self.rows("_audit/source-map.csv")
        self.assertEqual(len(mappings), len(originals))
        keys = {(r["SourceFile"], int(r["SourceRow"])) for r in mappings}
        self.assertEqual(keys, set(originals))
        for mapping in mappings:
            key = (mapping["SourceFile"], int(mapping["SourceRow"]))
            self.assertEqual(json.loads(mapping["OriginalRow"]), originals[key])

    def test_examples_levels_audio_and_distinct_grammar_uses(self):
        vocabulary = self.rows("vocabulary.csv")
        for kanji, kana, level in (("箸", "はし", "N2"), ("椅子", "いす", "N3"), ("美味しい", "おいしい", "N1")):
            matches = [r for r in vocabulary if r["Kanji"] == kanji and r["Kana"] == kana]
            self.assertEqual(len(matches), 1)
            self.assertEqual((matches[0]["Level"], matches[0]["KanjiLevel"]), ("N5", level))
            self.assertTrue((ROOT / matches[0]["Audio"].lstrip("/")).is_file())
        grammar = self.rows("grammar.csv")
        for kana in ("そうだ", "のに", "ばかり", "だけ", "にする", "と"):
            self.assertEqual(len([r for r in grammar if r["Kana"] == kana]), 2)

    def test_sources_unchanged_and_output_is_reproducible(self):
        for name, expected in json.loads(self.files["_audit/sources.sha256.json"]).items():
            self.assertEqual(hashlib.sha256((ROOT / "contenu csv" / name).read_bytes()).hexdigest(), expected)
        files, _ = build_catalog(ROOT / "contenu csv", ROOT / "audio/vocabulary/manifest.json",
                                 ROOT / "backend/app/data/vocabulary_audio_aliases.csv")
        self.assertEqual(files, self.files)

    def test_command_refuses_to_overwrite_an_existing_output_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "existing"
            output.mkdir()
            protected = output / "vocabulary.csv"
            protected.write_text("user edits", encoding="utf-8")
            result = subprocess.run([sys.executable, str(ROOT / "backend/scripts/consolidate_content_csv.py"),
                                     "--write", "--output-dir", str(output)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(protected.read_text(encoding="utf-8"), "user edits")
            self.assertEqual(list(output.iterdir()), [protected])


if __name__ == "__main__":
    unittest.main()
