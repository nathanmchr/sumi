import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from scripts.import_kanjivg_n5 import ROOT, REVISION, SOURCE_ROOT, build_assets, n5_characters, parse_svg
from scripts.kanji_supplement import load_entries

ASSETS = ROOT / "frontend/public/kanji-strokes"
CSV = ROOT / "contenu csv/JLPT N5 Kanji.csv"
SIMPLE = b'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:kvg="https://kanjivg.tagaini.net/" viewBox="0 0 109 109">
<g id="kvg:StrokePaths_04e00"><g id="kvg:04e00" kvg:element="&#x4e00;">
<path id="kvg:04e00-s1" d="M10,50L90,50" /></g></g>
<g id="kvg:StrokeNumbers_04e00"><text transform="matrix(1 0 0 1 8 46)">1</text></g></svg>'''


class StrokeImportTests(unittest.TestCase):
    def test_minimal_shape_and_number_are_preserved(self):
        data = parse_svg(SIMPLE, "一")
        self.assertEqual(data["strokes"], [{"path": "M10,50L90,50", "number_transform": [1, 0, 0, 1, 8, 46]}])

    def test_rejects_wrong_identity_or_viewbox(self):
        with self.assertRaises(ValueError):
            parse_svg(SIMPLE, "二")
        with self.assertRaises(ValueError):
            parse_svg(SIMPLE.replace(b'0 0 109 109', b'0 0 100 100'), "一")

    def test_rejects_nonsequential_strokes_and_numbers(self):
        for raw in (SIMPLE.replace(b'-s1', b'-s2'), SIMPLE.replace(b'>1</text>', b'>2</text>')):
            with self.assertRaises(ValueError):
                parse_svg(raw, "一")

    def test_rejects_unhandled_transforms(self):
        with self.assertRaises(ValueError):
            parse_svg(SIMPLE.replace(b'<path ', b'<path transform="translate(10 10)" '), "一")

    def test_rejects_executable_or_external_markup(self):
        for markup in (b'<script />', b'<image href="https://example.com/x"/>', b'<foreignObject/>'):
            with self.subTest(markup=markup), self.assertRaises(ValueError):
                parse_svg(SIMPLE.replace(b'</svg>', markup + b'</svg>'), "一")
        for attribute in (b'onload="alert(1)"', b'style="fill:url(https://example.com)"'):
            with self.assertRaises(ValueError):
                parse_svg(SIMPLE.replace(b'<path ', b'<path ' + attribute + b' '), "一")

    def test_rejects_entities_and_bad_path_or_matrix(self):
        cases = [b'<!ENTITY x "test">' + SIMPLE,
                 SIMPLE.replace(b'M10,50L90,50', b'javascript:alert(1)'),
                 SIMPLE.replace(b'matrix(1 0 0 1 8 46)', b'translate(8 46)'),
                 SIMPLE.replace(b'matrix(1 0 0 1 8 46)', b'matrix(1 0 0 1 1e999 46)')]
        for raw in cases:
            with self.assertRaises(ValueError):
                parse_svg(raw, "一")


class N5CorpusTests(unittest.TestCase):
    def test_coverage_is_exactly_the_n5_catalogue(self):
        characters = set(n5_characters(CSV)) | {row["character"] for row in load_entries() if row["level"] == "N5"}
        manifest = json.loads((ASSETS / "manifest.json").read_text())
        self.assertEqual(set(manifest["levels"]["N5"]), set(characters))
        self.assertEqual(manifest["revision"], REVISION)
        self.assertEqual(len(list((ASSETS / "n5").glob("*.json"))), len(characters))

    def test_every_stroke_matches_the_original_in_order(self):
        for character in n5_characters(CSV):
            with self.subTest(character=character):
                code = f"{ord(character):05x}"
                raw = (ASSETS / f"source/{code}.svg").read_bytes()
                data = json.loads((ASSETS / f"n5/{code}.json").read_text())
                self.assertEqual(parse_svg(raw, character), data)
                self.assertEqual(data["source_sha256"], hashlib.sha256(raw).hexdigest())

    def test_reference_counts(self):
        for character, count in {"一": 1, "人": 2, "山": 3, "日": 4, "先": 6, "学": 8}.items():
            data = json.loads((ASSETS / f"n5/{ord(character):05x}.json").read_text())
            self.assertEqual(len(data["strokes"]), count)

    def test_rebuild_is_byte_identical_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "source.zip"
            with ZipFile(archive, "w") as target:
                target.write(ASSETS / "COPYING.txt", f"{SOURCE_ROOT}/COPYING")
                for path in (ASSETS / "source").glob("*.svg"):
                    target.write(path, f"{SOURCE_ROOT}/kanji/{path.name}")
            result = build_assets(archive, CSV)
            for path, data in result.items():
                if path == "manifest.json":
                    continue
                self.assertEqual((ASSETS / path).read_bytes(), data, path)

    def test_attribution_and_license_are_distributed(self):
        notice = (ASSETS / "NOTICE.md").read_text()
        self.assertIn("Ulrich Apel", notice)
        self.assertIn("https://creativecommons.org/licenses/by-sa/3.0/", notice)
        self.assertIn("CREATIVE COMMONS", (ASSETS / "COPYING.txt").read_text())


if __name__ == "__main__":
    unittest.main()
