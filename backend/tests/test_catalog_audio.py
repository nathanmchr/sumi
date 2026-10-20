import csv
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.services import catalog_audio as audio
from app.services.vocabulary_audio import preferred_audio_url


class CatalogAudioTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "_audit").mkdir()
        (self.root / "generated").mkdir()
        self.manifest_path = self.root / "generated" / "manifest.json"
        self.overrides_path = self.root / "overrides.json"
        self.overrides_path.write_text("[]")
        self.rows = [
            {"ID": "chopsticks", "Kanji": "箸", "Kana": "はし", "Yomigana": "^は!し", "English": "chopsticks", "Audio": "/old-chopsticks.wav"},
            {"ID": "bridge", "Kanji": "橋", "Kana": "はし", "Yomigana": "^はし!", "English": "bridge", "Audio": "/old-bridge.wav"},
            {"ID": "tone", "Kanji": "音色", "Kana": "ねいろ", "Yomigana": "^ねいろ", "English": "timbre", "Audio": ""},
        ]
        self.sources = [
            {"Category": "vocabulary", "CanonicalID": "chopsticks", "OriginalRow": json.dumps({"Kanji": "", "Hiragana": "はし", "English": "chopsticks"})},
            {"Category": "vocabulary", "CanonicalID": "tone", "OriginalRow": json.dumps({"Kanji": "音色", "Hiragana": "おんいろ", "English": "old timbre gloss"})},
        ]
        self.write_catalog()
        for name, value in (("CATALOG_DIR", self.root), ("MANIFEST_PATH", self.manifest_path), ("OVERRIDES_PATH", self.overrides_path)):
            patcher = patch.object(audio, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        audio._catalog.cache_clear()
        audio._manifest.cache_clear()
        audio._checksum_matches.cache_clear()
        self.item = SimpleNamespace(id="historical-id", japanese="はし", reading="はし", translation="chopsticks", audio_url="/old-kana.wav")
        self.generated_url = "/audio/generated/word.wav?v=" + hashlib.sha256(b"RIFF" + b"sample audio" * 8).hexdigest()[:16]

    def write_catalog(self):
        for path, rows in ((self.root / "vocabulary.csv", self.rows), (self.root / "_audit/source-map.csv", self.sources)):
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter=";")
                writer.writeheader()
                writer.writerows(rows)

    def write_audio(self, **changes):
        data = b"RIFF" + b"sample audio" * 8
        path = self.manifest_path.parent / "word.wav"
        path.write_bytes(data)
        record = {"id": "chopsticks", "japanese": "箸", "reading": "はし", "yomigana": "^は!し",
                  "generation_version": "chirp3-yomigana-v1", "audio_file": path.name,
                  "audio_sha256": hashlib.sha256(data).hexdigest(), **changes}
        self.manifest_path.write_text(json.dumps({"N5": [record]}))
        return path

    def test_new_audio_is_shared_by_audited_variant_but_not_homophone(self):
        self.write_audio()
        self.assertEqual(preferred_audio_url(None, self.item), self.generated_url)
        self.item.japanese = "箸"
        self.assertEqual(preferred_audio_url(None, self.item), self.generated_url)
        self.item.japanese, self.item.translation = "橋", "bridge"
        self.assertEqual(preferred_audio_url(None, self.item), "/old-bridge.wav")

    def test_new_manifest_is_discovered_on_next_session_without_db_mutation(self):
        first = SimpleNamespace(info={})
        self.assertEqual(preferred_audio_url(first, self.item), "/old-chopsticks.wav")
        before = vars(self.item).copy()
        self.write_audio()
        self.assertEqual(preferred_audio_url(first, self.item), "/old-chopsticks.wav")
        self.assertEqual(preferred_audio_url(SimpleNamespace(info={}), self.item), self.generated_url)
        self.assertEqual(vars(self.item), before)

    def test_missing_bad_checksum_or_mismatched_reading_keeps_reviewed_fallback(self):
        for changes in ({"reading": "ばし"}, {"yomigana": "^はし!"}, {"audio_file": "../secret.wav"},
                        {"audio_file": 42}, {"audio_sha256": "bad"}, {"generation_version": "old"}):
            with self.subTest(changes=changes):
                self.write_audio(**changes)
                self.assertEqual(preferred_audio_url(None, self.item), "/old-chopsticks.wav")
        path = self.write_audio()
        self.assertEqual(preferred_audio_url(None, self.item), self.generated_url)
        path.write_bytes(b"corrupted audio")
        self.assertEqual(preferred_audio_url(None, self.item), "/old-chopsticks.wav")
        path.unlink()
        self.assertEqual(preferred_audio_url(None, self.item), "/old-chopsticks.wav")

    def test_ambiguous_identity_is_not_guessed_and_id_alone_is_not_enough(self):
        self.sources.append({**self.sources[0], "CanonicalID": "bridge"})
        self.write_catalog()
        self.assertIsNone(audio.catalog_entry(self.item))
        self.item.id, self.item.japanese, self.item.translation = "bridge", "箸", "chopsticks"
        self.assertIsNone(audio.catalog_entry(self.item))

    def test_replaced_audio_changes_url_but_unchanged_content_keeps_it_stable(self):
        path = self.write_audio()
        original_url = preferred_audio_url(None, self.item)
        self.assertEqual(original_url, preferred_audio_url(None, self.item))
        content = json.loads(self.manifest_path.read_text())
        replacement = b"RIFF" + b"approved replacement" * 8
        path.write_bytes(replacement)
        # Until the new checksum is committed, do not serve unverified bytes.
        self.assertEqual(preferred_audio_url(None, self.item), "/old-chopsticks.wav")
        content["N5"][0]["audio_sha256"] = hashlib.sha256(replacement).hexdigest()
        self.manifest_path.write_text(json.dumps(content))
        new_url = preferred_audio_url(None, self.item)
        self.assertNotEqual(new_url, original_url)
        self.assertEqual(new_url.split("?v=")[0], original_url.split("?v=")[0])
        self.assertTrue(new_url.endswith(hashlib.sha256(replacement).hexdigest()[:16]))

    def test_corrected_reading_can_never_restore_known_wrong_audio(self):
        self.item.japanese, self.item.reading, self.item.translation = "音色", "おんいろ", "old timbre gloss"
        self.assertEqual(preferred_audio_url(None, self.item), None)
        self.item.reading = "ねいろ"
        self.assertEqual(audio.catalog_entry(self.item)["ID"], "tone")
        self.assertEqual(preferred_audio_url(None, self.item), None)

    def test_invalid_manifest_falls_back_and_never_breaks_the_page(self):
        self.manifest_path.write_text("{partial")
        self.assertEqual(preferred_audio_url(None, self.item), "/old-chopsticks.wav")
        self.write_audio()
        content = json.loads(self.manifest_path.read_text())
        content["N2"] = content["N5"]
        self.manifest_path.write_text(json.dumps(content))
        self.assertEqual(preferred_audio_url(None, self.item), "/old-chopsticks.wav")
