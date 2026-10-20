"""Reviewed corrections preserve identities, source evidence and explicit scope."""

from copy import deepcopy
import csv
import hashlib
import json
import unittest

from scripts.catalog_corrections import apply_reviewed_corrections, csv_text, rows_from
from scripts.consolidate_content_csv import CORRECTIONS_FILE, HEADERS, ROOT, build_catalog


def synthetic_catalog():
    tables = {
        "vocabulary": [
            {**dict.fromkeys(HEADERS["vocabulary"], ""), "ID": "v-first", "Level": "N5",
             "KanjiLevel": "N5", "Kanji": "猫", "Kana": "ねこ", "Romaji": "neko",
             "Furigana": '[{"surface":"猫","reading":"ねこ"}]',
             "English": "cat", "French": "chat"},
        ],
        "grammar": [
            {"Level": level, "ID": identity, "Kanji": "", "Kana": "かな",
             "Romaji": "kana", "English": english, "French": french}
            for identity, level, english, french in (
                ("g-first", "N5", "first sense", "premier sens"),
                ("g-middle", "N4", "different sense", "autre sens"),
                ("g-last", "N2", "first sense", "premier sens"),
            )
        ],
        "kanji": [
            {"Level": "N5", "ID": "k-first", "Kanji": "猫",
             "Pronunciation": "ビョウ、ねこ", "English": "cat", "French": "chat"},
        ],
    }
    files = {f"{category}.csv": csv_text(rows, HEADERS[category])
             for category, rows in tables.items()}
    provenance = []
    for category, rows in tables.items():
        for position, row in enumerate(rows, 1):
            provenance.append({
                "Category": category, "SourceFile": f"{category}-source.csv",
                "SourceRow": str(position + 1), "SourceOrder": str(position),
                "CanonicalID": row["ID"], "CanonicalOrder": str(position),
                "OriginalRow": json.dumps(row, ensure_ascii=False, separators=(",", ":")),
            })
    files["_audit/source-map.csv"] = csv_text(provenance, list(provenance[0]))
    files["unrelated.txt"] = "keep this artifact unchanged\n"
    recipe = {
        "version": 1,
        "baseline_sha256": {name: hashlib.sha256(text.encode()).hexdigest()
                            for name, text in files.items() if name.endswith(".csv")},
        "updates": [], "merges": [], "pending_audio": [], "unresolved": [],
    }
    return files, recipe


def grammar_update(**changes):
    return {"category": "grammar", "id": "g-first", "expect": {"French": "premier sens"},
            "set": changes, "reason": "Explicit test correction", "reference": "test fixture"}


def grammar_merge(keep="g-first", absorb=None, **changes):
    return {"category": "grammar", "keep": keep,
            "absorb": ["g-last"] if absorb is None else absorb, "set": changes,
            "reason": "Explicit test merge", "reference": "test fixture"}


class CatalogCorrectionRulesTests(unittest.TestCase):
    def setUp(self):
        self.files, self.recipe = synthetic_catalog()

    def assert_rejected_without_mutation(self, message):
        files_before, recipe_before = deepcopy(self.files), deepcopy(self.recipe)
        with self.assertRaisesRegex(ValueError, message):
            apply_reviewed_corrections(self.files, self.recipe)
        self.assertEqual(self.files, files_before)
        self.assertEqual(self.recipe, recipe_before)

    def test_refuses_changed_baseline(self):
        self.files["grammar.csv"] += "\n"
        self.assert_rejected_without_mutation("Reviewed baseline changed")

    def test_refuses_incorrect_before_value(self):
        operation = grammar_update(French="correction")
        operation["expect"]["French"] = "stale value"
        self.recipe["updates"] = [operation]
        self.assert_rejected_without_mutation("Correction precondition failed")

    def test_refuses_a_merge_keeping_a_later_id(self):
        self.recipe["merges"] = [grammar_merge(keep="g-last", absorb=["g-first"])]
        self.assert_rejected_without_mutation("keep the first occurrence")

    def test_refuses_overlapping_merges(self):
        self.recipe["merges"] = [grammar_merge(), grammar_merge(absorb=["g-middle"])]
        self.assert_rejected_without_mutation("Overlapping reviewed merges")

    def test_refuses_duplicate_or_empty_merge_members(self):
        for members in ([], ["g-first"], ["g-last", "g-last"]):
            with self.subTest(members=members):
                self.recipe["merges"] = [grammar_merge(absorb=members)]
                self.assert_rejected_without_mutation("distinct, explicit member IDs")

    def test_refuses_stable_id_and_introduction_level_changes(self):
        for field, value, message in (("ID", "replacement-id", "replace a stable ID"),
                                      ("Level", "N1", "first introduction level")):
            for operation_kind in ("updates", "merges"):
                with self.subTest(field=field, operation=operation_kind):
                    self.files, self.recipe = synthetic_catalog()
                    operation = (grammar_update if operation_kind == "updates" else grammar_merge)
                    self.recipe[operation_kind] = [operation(**{field: value})]
                    self.assert_rejected_without_mutation(message)

    def test_refuses_unknown_or_non_string_fields(self):
        for changes in ({"KanaLevel": "N5"}, {"French": None}, {"English": 12}):
            with self.subTest(changes=changes):
                self.recipe["updates"] = [grammar_update(**changes)]
                self.assert_rejected_without_mutation("Invalid correction fields")

    def test_refuses_repeated_updates(self):
        operation = grammar_update(French="premier sens")
        self.recipe["updates"] = [operation, deepcopy(operation)]
        self.assert_rejected_without_mutation("Repeated update")

    def test_failure_after_an_earlier_edit_does_not_mutate_inputs(self):
        self.recipe["updates"] = [grammar_update(French="correction")]
        self.recipe["merges"] = [grammar_merge(keep="g-last", absorb=["g-first"])]
        self.assert_rejected_without_mutation("keep the first occurrence")

    def test_identical_spellings_are_not_merged_without_explicit_ids(self):
        result, summary, ledger = apply_reviewed_corrections(self.files, self.recipe)
        self.assertEqual(rows_from(result["grammar.csv"]), rows_from(self.files["grammar.csv"]))
        self.assertEqual(summary["grammar"]["rows"], 3)
        self.assertEqual(ledger["redirects"], [])

    def test_success_keeps_inputs_order_provenance_and_reversible_ledger(self):
        self.recipe["updates"] = [grammar_update(French="premier sens clarifié")]
        self.recipe["merges"] = [grammar_merge()]
        files_before, recipe_before = deepcopy(self.files), deepcopy(self.recipe)

        result, summary, ledger = apply_reviewed_corrections(self.files, self.recipe)

        self.assertEqual(self.files, files_before)
        self.assertEqual(self.recipe, recipe_before)
        self.assertEqual(result["unrelated.txt"], self.files["unrelated.txt"])
        rows = rows_from(result["grammar.csv"])
        self.assertEqual([row["ID"] for row in rows], ["g-first", "g-middle"])
        self.assertEqual(rows[0]["French"], "premier sens clarifié")
        self.assertEqual(rows[0]["Level"], "N5")
        self.assertEqual(summary["grammar"]["source_rows"], 3)
        self.assertEqual(summary["grammar"]["absorbed_rows"], 1)
        self.assertEqual(ledger["redirects"],
                         [{"category": "grammar", "from": "g-last", "to": "g-first"}])
        self.assertEqual(ledger["updates"][0]["before"]["French"], "premier sens")
        self.assertEqual(ledger["merges"][0]["after"], rows[0])
        for before, after in zip(rows_from(self.files["_audit/source-map.csv"]),
                                 rows_from(result["_audit/source-map.csv"]), strict=True):
            self.assertEqual(after["OriginalRow"], before["OriginalRow"])
            self.assertEqual(after["OriginalCanonicalID"], before["CanonicalID"])
        self.assertEqual(json.loads(result["_audit/corrections.json"]), ledger)


class CatalogCorrectionCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        arguments = (ROOT / "contenu csv", ROOT / "audio/vocabulary/manifest.json",
                     ROOT / "backend/app/data/vocabulary_audio_aliases.csv")
        cls.baseline, cls.baseline_summary = build_catalog(*arguments, reviewed=False)
        cls.corrected, cls.summary = build_catalog(*arguments, reviewed=True, include_yomigana=False)
        cls.recipe = json.loads(CORRECTIONS_FILE.read_text(encoding="utf-8"))
        cls.ledger = json.loads(cls.corrected["_audit/corrections.json"])
        cls.before = {category: rows_from(cls.baseline[f"{category}.csv"]) for category in HEADERS}
        cls.after = {category: rows_from(cls.corrected[f"{category}.csv"]) for category in HEADERS}

    def test_surviving_ids_levels_and_original_order_are_unchanged(self):
        absorbed = {(merge["category"], identity) for merge in self.recipe["merges"]
                    for identity in merge["absorb"]}
        for category in HEADERS:
            with self.subTest(category=category):
                expected = [row for row in self.before[category] if (category, row["ID"]) not in absorbed]
                self.assertEqual([row["ID"] for row in self.after[category]],
                                 [row["ID"] for row in expected])
                self.assertEqual([row["Level"] for row in self.after[category]],
                                 [row["Level"] for row in expected])
                self.assertEqual(len({row["ID"] for row in self.after[category]}), len(expected))
                self.assertEqual(self.summary[category]["source_rows"],
                                 self.baseline_summary[category]["source_rows"])

    def test_only_declared_fields_and_explicit_merge_ids_change(self):
        expected = {category: {row["ID"]: dict(row) for row in rows}
                    for category, rows in self.before.items()}
        expected_redirects = []
        for operation in self.recipe["updates"]:
            row = expected[operation["category"]][operation["id"]]
            for field, value in operation["expect"].items():
                self.assertEqual(row[field], value)
            row.update(operation["set"])
        for operation in self.recipe["merges"]:
            self.assertTrue(operation["reason"].strip())
            self.assertTrue(operation["reference"].strip())
            category, keep = operation["category"], operation["keep"]
            expected[category][keep].update(operation.get("set", {}))
            for identity in operation["absorb"]:
                del expected[category][identity]
                expected_redirects.append({"category": category, "from": identity, "to": keep})
        for category, rows in self.after.items():
            self.assertEqual(rows, list(expected[category].values()))
        self.assertEqual(self.ledger["redirects"], expected_redirects)
        self.assertEqual(len(self.ledger["merges"]), len(self.recipe["merges"]))

    def test_all_11287_source_rows_and_original_ids_remain_exactly_traceable(self):
        original_mapping = rows_from(self.baseline["_audit/source-map.csv"])
        corrected_mapping = rows_from(self.corrected["_audit/source-map.csv"])
        self.assertEqual(len(original_mapping), 11287)
        self.assertEqual(len(corrected_mapping), 11287)
        positions = {category: {row["ID"]: str(position) for position, row in enumerate(rows, 1)}
                     for category, rows in self.after.items()}
        redirects = {(row["category"], row["from"]): row["to"] for row in self.ledger["redirects"]}
        source_rows = {}
        for path in (ROOT / "contenu csv").glob("JLPT * *.csv"):
            with path.open(encoding="utf-8-sig", newline="") as handle:
                for line, row in enumerate(csv.DictReader(handle, delimiter=";"), 2):
                    source_rows[(path.name, str(line))] = row
        seen = set()
        for before, after in zip(original_mapping, corrected_mapping, strict=True):
            category, original_id = before["Category"], before["CanonicalID"]
            key = (after["SourceFile"], after["SourceRow"])
            self.assertNotIn(key, seen)
            seen.add(key)
            for field in ("Category", "SourceFile", "SourceRow", "SourceOrder", "OriginalRow"):
                self.assertEqual(after[field], before[field])
            self.assertEqual(json.loads(after["OriginalRow"]), source_rows[key])
            self.assertEqual(after["OriginalCanonicalID"], original_id)
            self.assertEqual(after["CanonicalID"], redirects.get((category, original_id), original_id))
            self.assertEqual(after["CanonicalOrder"], positions[category][after["CanonicalID"]])
        self.assertEqual(seen, set(source_rows))

    def test_distinct_grammar_uses_remain_separate_after_metadata_cleanup(self):
        grammar = self.after["grammar"]
        for kana in ("そうだ", "のに", "ばかり", "だけ", "にする", "と", "も", "こと", "でも", "より"):
            with self.subTest(kana=kana):
                matches = [row for row in grammar if row["Kana"] == kana]
                self.assertEqual(len(matches), 2)
                self.assertEqual(len({row["ID"] for row in matches}), 2)
                self.assertEqual(len({row["English"] for row in matches}), 2)
        by_id = {row["ID"]: row for row in grammar}
        self.assertEqual(by_id["85142ab7-f2c6-5fb3-83f0-e1e9e7e65da2"]["Level"], "N5")
        self.assertEqual(by_id["2dd4f2d6-8e5b-5e17-815e-b3b8cfa60a4d"]["Level"], "N3")
        self.assertNotIn("autant", by_id["85142ab7-f2c6-5fb3-83f0-e1e9e7e65da2"]["French"])
        self.assertIn("autant", by_id["2dd4f2d6-8e5b-5e17-815e-b3b8cfa60a4d"]["French"])
        yori = by_id["61944476-4047-5afa-8264-4c61027cee3d"]
        self.assertEqual((yori["Kana"], yori["Level"]), ("より", "N2"))
        self.assertIn("from", yori["English"])

    def test_grammar_corrections_remove_crossed_senses_and_hybrid_readings(self):
        rows = {row["ID"]: row for row in self.after["grammar"]}
        self.assertNotIn("transformer", rows["36fc564e-88d7-5f62-8294-1420867cdae5"]["French"])
        self.assertNotIn("choisir", rows["0eb1219d-886b-5ba5-b887-2079368e5b0e"]["French"])
        self.assertEqual(rows["03fa1f5b-79c4-5994-bcd0-ed18dd7954df"]["French"], "il arrive que ~ ; parfois ~")
        self.assertNotIn("at most", rows["cf7b89f8-27ab-508a-9f6a-8a9e292cc7af"]["English"])
        self.assertEqual(rows["e128d2d3-bf71-5e16-8f64-b7421d508712"]["French"].count("sans interruption"), 1)
        for identity, kanji, kana, romaji in (
            ("72f26491-b705-53b1-bf6a-db95005aa5dc", "イ形容詞", "いけいようし", "i keiyoushi"),
            ("4b8996de-ecc0-5de0-8e3d-8504a02ba11c", "ナ形容詞", "なけいようし", "na keiyoushi"),
        ):
            self.assertEqual(tuple(rows[identity][field] for field in ("Kanji", "Kana", "Romaji")),
                             (kanji, kana, romaji))

    def test_three_spreadsheet_error_values_are_corrected_not_lost(self):
        errors = [(category, row["ID"], field) for category, rows in self.before.items()
                  for row in rows for field, value in row.items() if "#NAME?" in value]
        self.assertEqual(len(errors), 3)
        after = {category: {row["ID"]: row for row in rows} for category, rows in self.after.items()}
        redirects = {(row["category"], row["from"]): row["to"] for row in self.ledger["redirects"]}
        for category, identity, field in errors:
            destination = redirects.get((category, identity), identity)
            self.assertTrue(after[category][destination][field].strip())
        for rows in self.after.values():
            for row in rows:
                self.assertFalse(any("#NAME?" in value for value in row.values()), row["ID"])

    def test_only_three_documented_audio_files_are_pending(self):
        expected = {
            "e90f8804-8005-5a65-b1cc-319c5ff0582e": ("音色", "ねいろ"),
            "2a098313-5693-5d03-88f2-5881023ca697": ("愛憎", "あいぞう"),
            "797947e4-7105-5cc6-ab23-89a1ef735116": ("一筋", "ひとすじ"),
        }
        pending = self.ledger["pending_audio"]
        self.assertEqual(len(pending), 3)
        self.assertEqual({row["id"] for row in pending}, set(expected))
        for item in pending:
            self.assertEqual(item["category"], "vocabulary")
            self.assertEqual((item["kanji"], item["kana"]), expected[item["id"]])
            self.assertTrue(item["previous_audio"])
            self.assertTrue(item["reason"].strip())
        vocabulary = self.after["vocabulary"]
        self.assertEqual({row["ID"] for row in vocabulary if not row["Audio"]}, set(expected))
        for row in vocabulary:
            if row["ID"] in expected:
                self.assertEqual((row["Kanji"], row["Kana"]), expected[row["ID"]])
            else:
                self.assertTrue((ROOT / row["Audio"].lstrip("/")).is_file(), row["ID"])

    def test_sources_stay_unchanged_and_reviewed_build_replays_exactly(self):
        fingerprints = json.loads(self.baseline["_audit/sources.sha256.json"])
        for filename, expected in fingerprints.items():
            self.assertEqual(hashlib.sha256((ROOT / "contenu csv" / filename).read_bytes()).hexdigest(), expected)
        rebuilt, summary = build_catalog(
            ROOT / "contenu csv", ROOT / "audio/vocabulary/manifest.json",
            ROOT / "backend/app/data/vocabulary_audio_aliases.csv", reviewed=True, include_yomigana=False,
        )
        self.assertEqual(rebuilt, self.corrected)
        self.assertEqual(summary, self.summary)
        for filename, expected in self.ledger["result_sha256"].items():
            self.assertEqual(hashlib.sha256(self.corrected[filename].encode()).hexdigest(), expected)


if __name__ == "__main__":
    unittest.main()
