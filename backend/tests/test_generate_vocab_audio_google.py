"""Offline contracts for kana-directed Chirp requests and resumable audio files."""

import argparse
from contextlib import redirect_stdout
from copy import deepcopy
import csv
import hashlib
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

from scripts import generate_vocab_audio_google as audio

try:
    from google.cloud import texttospeech as google_tts
except ImportError:
    google_tts = None


def entry(japanese="箸", reading="はし", identity="test-id", **extra):
    return {"id": identity, "japanese": japanese, "reading": reading, "sources": ["N5"],
            "source_rows": ["vocabulary.csv:2"], **extra}


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def wav_fixture(tag="default", amplitude=0.25, seconds=0.2, format="WAV"):
    import numpy as np
    import soundfile as sf

    rate = 24000
    frequency = 200 + sum(map(ord, tag)) % 200
    samples = amplitude * np.sin(2 * np.pi * frequency * np.arange(round(rate * seconds)) / rate)
    stream = io.BytesIO()
    sf.write(stream, samples, rate, format=format)
    return stream.getvalue()


class PronunciationTests(unittest.TestCase):
    def test_listed_readings_and_notation_keep_their_order(self):
        cases = [
            ("毎月", "まいげつ/まいつき", ["まいげつ", "まいつき"]),
            ("四", "し / よん", ["し", "よん"]),
            ("お・金持ち", "かねもち/おかねもち", ["かねもち", "おかねもち"]),
            ("", "キロ/キログラム", ["キロ", "キログラム"]),
            ("", "レポート／リポート", ["レポート", "リポート"]),
            ("経験", "けいけん・する", ["けいけんする"]),
            ("", "チェック・する", ["チェックする"]),
            ("", "より、ほう", ["より", "ほう"]),
            ("", "ｺｰﾋｰ", ["コーヒー"]), ("", "か\u3099", ["が"]),
        ]
        for japanese, reading, expected in cases:
            with self.subTest(reading=reading):
                row = entry(japanese, reading)
                before = deepcopy(row)
                self.assertEqual(audio.reading_parts(row), expected)
                self.assertEqual(audio.pronunciation_parts(row), expected)
                self.assertEqual(row, before)

    def test_single_reading_keeps_written_form_without_inventing_accent(self):
        for japanese, reading in [("太い", "ふとい"), ("箸", "はし"), ("橋", "はし"), ("音色", "ねいろ"),
                                  ("愛憎", "あいぞう"), ("一筋", "ひとすじ")]:
            with self.subTest(japanese=japanese):
                prepared = audio.speech_input(entry(japanese, reading))
                root = ET.fromstring(prepared["ssml"])
                self.assertEqual(root[0].text, japanese)
                self.assertEqual(root[0].get("ph"), reading)
                self.assertEqual(root[0].get("alphabet"), "yomigana")
                self.assertEqual(root[0].tail, "。")
                self.assertNotIn("custom_pronunciations", prepared)

    def test_spelling_alternatives_have_one_spoken_surface_without_changing_the_entry(self):
        cases = [("初め/始め", "はじめ"), ("伯母さん/叔母さん", "おばさん"),
                 ("丸い/円い", "まるい"), ("川/河", "かわ"),
                 ("伯父さん/叔父さん", "おじさん"), ("堅/硬/固い", "かたい"),
                 ("作る/造る", "つくる"), ("伯母さん／叔母さん", "おばさん")]
        for written, reading in cases:
            with self.subTest(written=written):
                row = entry(written, reading, yomigana=reading)
                before = deepcopy(row)
                root = ET.fromstring(audio.speech_input(row)["ssml"])
                self.assertEqual(len(root), 1)
                self.assertEqual(root[0].text, reading)
                self.assertEqual(root[0].get("ph"), reading)
                self.assertEqual(root[0].get("alphabet"), "yomigana")
                self.assertEqual(root[0].tail, "。")
                self.assertEqual(row, before)

    def test_spelling_alternatives_preserve_accent_and_genuine_reading_alternatives(self):
        root = ET.fromstring(audio.speech_input(entry("箸/はし", "はし", yomigana="^は!し"))["ssml"])
        self.assertEqual(root[0].text, "はし")
        self.assertEqual(root[0].get("ph"), "^は!し")
        root = ET.fromstring(audio.speech_input(entry("四/４", "し/よん", yomigana="^し!/^よ!ん"))["ssml"])
        self.assertEqual([node.text for node in root], ["し", "よん"])
        self.assertEqual([node.get("ph") for node in root], ["^し!", "^よ!ん"])
        self.assertEqual([node.tail for node in root], ["、", "。"])

    def test_corrected_spelling_surface_invalidates_old_request_filename(self):
        row = entry("伯母さん/叔母さん", "おばさん", yomigana="おばさん")
        corrected = audio.audio_name(row, "wav")
        original = {"ssml": '<speak><phoneme alphabet="yomigana" ph="おばさん">伯母さん/叔母さん</phoneme>。</speak>'}
        with patch.object(audio, "speech_input", return_value=original):
            self.assertNotEqual(corrected, audio.audio_name(row, "wav"))

    def test_multiple_readings_use_separate_ssml_phonemes(self):
        prepared = audio.speech_input(entry("毎月", "まいげつ/まいつき"))
        self.assertEqual(set(prepared), {"ssml"})
        root = ET.fromstring(prepared["ssml"])
        self.assertEqual(root.tag, "speak")
        self.assertEqual([(node.get("alphabet"), node.get("ph"), node.text) for node in root],
                         [("yomigana", "まいげつ", "まいげつ"), ("yomigana", "まいつき", "まいつき")])
        self.assertEqual([node.tail for node in root], ["、", "。"])

    def test_nan_nani_keeps_both_readings_in_the_supplied_order(self):
        for readings in ("なん/なに", "なに/なん"):
            with self.subTest(readings=readings):
                row = entry("何", readings, yomigana=readings)
                before = deepcopy(row)
                root = ET.fromstring(audio.speech_input(row)["ssml"])
                self.assertEqual([node.text for node in root], readings.split("/"))
                self.assertEqual([node.get("ph") for node in root], readings.split("/"))
                self.assertEqual([node.tail for node in root], ["、", "。"])
                self.assertEqual(row, before)

    def test_explicit_accents_survive_and_blank_yomigana_falls_back(self):
        for raw, expected in [(None, "はし"), ("", "はし"), ("  ", "はし"),
                              ("^はし", "^はし"), ("^は!し", "^は!し"),
                              ("^はし!", "^はし!"), ("^ハ!シ", "^ハ!シ"),
                              ("＾ﾊ！ｼ", "^ハ!シ")]:
            with self.subTest(yomigana=raw):
                row = entry(yomigana=raw)
                self.assertEqual(audio.pronunciation_parts(row), [expected])
                self.assertEqual(ET.fromstring(audio.speech_input(row)["ssml"])[0].get("ph"), expected)
        root = ET.fromstring(audio.speech_input(entry("四", "し/よん", yomigana="^し!/^よ!ん"))["ssml"])
        self.assertEqual([node.get("ph") for node in root], ["^し!", "^よ!ん"])
        self.assertEqual([node.text for node in root], ["し", "よん"])
        self.assertEqual(audio.pronunciation_parts(entry("今日", "きょう", yomigana="^きょ!う")), ["^きょ!う"])

    def test_invalid_kana_or_yomigana_fails_with_source_location(self):
        for reading in ("", " ", "hashi", "箸", "はし/", "/はし", "はし//はし", "(no)",
                        "は し", "1", "<phoneme>", "^は!し"):
            with self.subTest(reading=reading), self.assertRaisesRegex(ValueError, "vocabulary.csv:2"):
                audio.speech_input(entry(reading=reading))
        accents = [("はし", raw) for raw in
                   ("は!し", "^^はし", "^は^し", "^!はし", "^は!!し", "^はし!^", "^はじ")]
        accents += [("きょう", "^き!ょう"), ("し/よん", "^し!"), ("し/よん", "^よん/^し"),
                    ("こう", "^こお"), ("はし", "^箸"), ("はし", "^はし/")]
        for reading, yomigana in accents:
            with self.subTest(yomigana=yomigana), self.assertRaisesRegex(ValueError, "vocabulary.csv:2"):
                audio.speech_input(entry(reading=reading, yomigana=yomigana))

    @unittest.skipIf(google_tts is None, "Google SDK not installed; no network needed")
    def test_requests_are_accepted_by_the_installed_sdk_without_a_client(self):
        for row in (entry(yomigana="^は!し"), entry("四", "し/よん", yomigana="^し!/^よ!ん")):
            for output_format, encoding in (("wav", google_tts.AudioEncoding.LINEAR16),
                                             ("mp3", google_tts.AudioEncoding.MP3)):
                with self.subTest(reading=row["reading"], output_format=output_format):
                    request = google_tts.SynthesizeSpeechRequest(**audio.synthesis_request(
                        row, audio.DEFAULT_VOICE, 0.8, output_format))
                    self.assertEqual(request.voice.language_code, "ja-JP")
                    self.assertEqual(request.voice.name, audio.DEFAULT_VOICE)
                    self.assertEqual(request.audio_config.audio_encoding, encoding)
                    self.assertAlmostEqual(request.audio_config.speaking_rate, 0.8)
                    self.assertFalse(request.input.text)
                    self.assertEqual([node.get("ph") for node in ET.fromstring(request.input.ssml)], audio.pronunciation_parts(row))


class LoadingAndCacheTests(unittest.TestCase):
    def test_targeted_selection_preserves_catalog_order_and_rejects_unknown_ids(self):
        rows = [entry(identity="one"), entry(identity="two"), entry(identity="three")]
        args = argparse.Namespace(limit=None, ids=["three", "one"], shuffle=False)
        self.assertEqual([row["id"] for row in audio.select_entries(rows, args)], ["one", "three"])
        args.ids = ["missing"]
        with self.assertRaisesRegex(ValueError, "Unknown catalog IDs"):
            audio.select_entries(rows, args)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def test_consolidated_has_priority_keeps_ids_order_and_yomigana(self):
        rows = [{"Level": "N5", "ID": "z-first", "Kanji": "箸", "Kana": "はし", "Yomigana": "^は!し"},
                {"Level": "N2", "ID": "a-second", "Kanji": "箸", "Kana": "はし", "Yomigana": ""}]
        write_csv(self.directory / "vocabulary.csv", rows)
        write_csv(self.directory / "JLPT N5 Vocab.csv", [{"Kanji": "無効", "Hiragana": ""}])
        loaded = audio.load_vocabulary(self.directory)
        self.assertEqual([row["id"] for row in loaded], ["z-first", "a-second"])
        self.assertEqual(loaded[0]["yomigana"], "^は!し")
        self.assertEqual(loaded[1].get("yomigana", ""), "")
        self.assertEqual([row["source_rows"] for row in loaded], [["vocabulary.csv:2"], ["vocabulary.csv:3"]])
        self.assertNotEqual(audio.entry_identity(loaded[0]), audio.entry_identity(loaded[1]))

    def test_legacy_files_remain_explicit_and_merge_source_references(self):
        for level in ("N2", "N5"):
            write_csv(self.directory / f"JLPT {level} Vocab.csv", [{"Kanji": "箸", "Hiragana": "はし"}])
        loaded = audio.load_vocabulary(self.directory)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["sources"], ["JLPT N5", "JLPT N2"])
        self.assertEqual(loaded[0]["source_rows"], ["JLPT N5 Vocab.csv:2", "JLPT N2 Vocab.csv:2"])
        self.assertEqual(audio.entry_identity(loaded[0]), ("word", "箸", "はし"))

    def test_legacy_conflicting_yomigana_is_not_silently_dropped(self):
        for second in ("^はし!", ""):
            with self.subTest(second=second):
                for level, pronunciation in (("N5", "^は!し"), ("N2", second)):
                    write_csv(self.directory / f"JLPT {level} Vocab.csv", [{
                        "Kanji": "箸", "Hiragana": "はし", "Yomigana": pronunciation,
                    }])
                with self.assertRaisesRegex(ValueError, "conflicting Yomigana"):
                    audio.load_vocabulary(self.directory)

    def test_missing_kana_bad_level_and_duplicate_id_are_not_silently_skipped(self):
        valid = {"Level": "N5", "ID": "one", "Kanji": "箸", "Kana": "はし"}
        for rows in ([{**valid, "Kana": ""}], [{**valid, "ID": ""}],
                     [{**valid, "Level": "N9"}], [valid, valid]):
            with self.subTest(rows=rows):
                write_csv(self.directory / "vocabulary.csv", rows)
                with self.assertRaisesRegex(ValueError, "vocabulary.csv:"):
                    audio.load_vocabulary(self.directory)

    def test_cache_signature_covers_request_identity_and_generation_version(self):
        row = entry()
        original = audio.audio_name(row, "wav")
        changes = [audio.audio_name(row, "mp3"), audio.audio_name(row, "wav", speed=0.8),
                   audio.audio_name(row, "wav", voice_name="ja-JP-Chirp3-HD-Kore"),
                   audio.audio_name(entry(yomigana="^は!し"), "wav"),
                   audio.audio_name(entry(reading="ばし"), "wav"),
                   audio.audio_name(entry(identity="different-id"), "wav")]
        with patch.object(audio, "GENERATION_VERSION", "different-version"):
            changes.append(audio.audio_name(row, "wav"))
        self.assertTrue(all(changed != original for changed in changes))
        self.assertEqual(audio.audio_name(row, "wav", speed=1), original)
        self.assertNotEqual(audio.audio_name(entry("四", "し/よん"), "wav"),
                            audio.audio_name(entry("四", "よん/し"), "wav"))
        legacy = hashlib.sha256("箸\tはし".encode()).hexdigest()[:16] + ".wav"
        self.assertNotEqual(original, legacy)

    def test_manifest_round_trip_checksum_and_request_control_reuse(self):
        row = entry(yomigana="^は!し")
        request = audio.synthesis_request(row, audio.DEFAULT_VOICE, 1.0, "wav")
        path = self.directory / audio.audio_name(row, "wav")
        path.write_bytes(wav_fixture())
        record = {**row, "generation_version": audio.GENERATION_VERSION, "audio_file": path.name,
                  "request": request, "audio_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        manifest = {"N5": [record]}
        manifest_path = self.directory / "manifest.json"
        audio.save_manifest(manifest_path, manifest)
        self.assertEqual(audio.load_manifest(manifest_path), manifest)
        self.assertFalse(manifest_path.with_suffix(".json.tmp").exists())
        self.assertTrue(audio.reusable_audio(path, record, request))
        for invalid in (None, {**record, "generation_version": "old"}, {**record, "audio_sha256": "wrong"},
                        {**record, "audio_file": "other.wav"}, {**record, "request": {}}):
            with self.subTest(record=invalid):
                self.assertFalse(audio.reusable_audio(path, invalid, request))
        path.write_bytes(b"")
        self.assertFalse(audio.reusable_audio(path, record, request))
        self.assertFalse(audio.reusable_audio(self.directory / "missing.wav", record, request))
        other = {**record, "id": "another-id"}
        audio.update_manifest(manifest, "N2", other)
        audio.update_manifest(manifest, "N5", {**record, "reading": "updated"})
        self.assertEqual(len(manifest["N5"]), 1)
        self.assertEqual(manifest["N5"][0]["reading"], "updated")
        self.assertEqual(manifest["N2"], [other])

    def test_actual_consolidated_corpus_prepares_without_dropping_any_reading(self):
        loaded = audio.load_vocabulary(audio.DEFAULT_INPUT_DIR)
        self.assertEqual(len(loaded), 8038)
        for row in loaded:
            parts = audio.pronunciation_parts(row)
            prepared = audio.speech_input(row)
            self.assertEqual(len(parts), len(audio.reading_parts(row)))
            if "ssml" in prepared:
                self.assertEqual([node.get("ph") for node in ET.fromstring(prepared["ssml"])], parts)
            else:
                self.assertEqual(prepared["custom_pronunciations"]["pronunciations"][0]["pronunciation"], parts[0])


class OfflineMainTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.output = self.directory / "separate-output"
        self.rows = [{"Level": "N5", "ID": f"item-{index}", "Kanji": japanese, "Kana": reading,
                      "Yomigana": yomigana} for index, (japanese, reading, yomigana) in enumerate(
                          [("箸", "はし", "^は!し"), ("四", "し/よん", "^し!/^よ!ん"), ("音色", "ねいろ", "")])]
        write_csv(self.directory / "vocabulary.csv", self.rows)
        self.args = argparse.Namespace(input_dir=self.directory, output_dir=self.output, voice=audio.DEFAULT_VOICE,
                                       speed=1.0, format="wav", limit=None, all=False, shuffle=False, seed=42,
                                       requests_per_minute=180, max_retries=0, force=False, dry_run=False)
        self.factory = Mock(return_value=(object(), object(), ()))
        self.synthesis = Mock(return_value=wav_fixture())

    def run_main(self):
        with patch.object(audio, "parse_args", return_value=self.args), \
             patch.object(audio, "create_google_client", self.factory), \
             patch.object(audio, "synthesize", self.synthesis), patch.object(audio.time, "sleep"), \
             redirect_stdout(io.StringIO()) as output:
            audio.main()
        return output.getvalue()

    def test_dry_run_or_invalid_selected_reading_has_no_side_effects(self):
        self.args.dry_run = True
        output = self.run_main()
        self.assertIn('^は!し', output)
        self.assertIn("ssml", output)
        self.factory.assert_not_called()
        self.synthesis.assert_not_called()
        self.assertFalse(self.output.exists())
        self.args.dry_run = False
        self.rows[1]["Yomigana"] = "^よん/^し"
        write_csv(self.directory / "vocabulary.csv", self.rows)
        with self.assertRaisesRegex(ValueError, "does not match Kana"):
            self.run_main()
        self.factory.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_old_manifest_is_refused_without_overwrite_or_api(self):
        self.output.mkdir()
        path = self.output / "manifest.json"
        path.write_text('{"JLPT N5": [{"japanese": "箸", "reading": "はし", "audio_file": "old.wav"}]}')
        (self.output / "old.wav").write_bytes(b"precious old audio")
        before = {item.name: item.read_bytes() for item in self.output.iterdir()}
        with self.assertRaisesRegex(ValueError, "Incompatible audio manifest"):
            self.run_main()
        self.assertEqual({item.name: item.read_bytes() for item in self.output.iterdir()}, before)
        self.factory.assert_not_called()

    def test_interruption_resume_and_limited_force_keep_prior_manifest_entries(self):
        self.synthesis.side_effect = [wav_fixture("first"), RuntimeError("simulated interruption")]
        with self.assertRaisesRegex(RuntimeError, "simulated interruption"):
            self.run_main()
        path = self.output / "manifest.json"
        first = audio.load_manifest(path)["N5"]
        self.assertEqual([record["id"] for record in first], ["item-0"])
        self.assertEqual((self.output / first[0]["audio_file"]).read_bytes(), wav_fixture("first"))
        self.synthesis = Mock(return_value=wav_fixture("resumed"))
        self.run_main()
        self.assertEqual(self.synthesis.call_count, 2)
        complete = audio.load_manifest(path)["N5"]
        self.assertEqual([record["id"] for record in complete], ["item-0", "item-1", "item-2"])
        self.assertTrue(all(record["pronunciation_verified"] is False for record in complete))
        self.assertTrue(all(record["generated_at"] and record["source_rows"] for record in complete))
        before = path.read_bytes()
        self.args.limit = 1
        self.factory.reset_mock()
        self.synthesis.reset_mock()
        self.run_main()
        self.factory.assert_not_called()
        self.synthesis.assert_not_called()
        self.assertEqual(path.read_bytes(), before)
        self.args.force = True
        self.synthesis.return_value = wav_fixture("forced")
        self.run_main()
        self.assertEqual(self.synthesis.call_count, 1)
        final = audio.load_manifest(path)["N5"]
        self.assertEqual(final[1:], complete[1:])
        self.assertEqual(final[0]["yomigana"], "^は!し")
        self.assertFalse(list(self.output.glob("*.tmp")))

    def test_orphan_cache_and_failed_force_do_not_erase_existing_content(self):
        self.args.limit = 1
        self.output.mkdir()
        row = audio.load_vocabulary(self.directory)[0]
        target = self.output / audio.audio_name(row, "wav")
        target.write_bytes(b"unverified orphan")
        self.run_main()
        self.synthesis.assert_called_once()
        self.assertEqual(target.read_bytes(), wav_fixture())
        manifest = (self.output / "manifest.json").read_bytes()
        self.args.force = True
        self.synthesis.side_effect = RuntimeError("simulated failure")
        with self.assertRaisesRegex(RuntimeError, "simulated failure"):
            self.run_main()
        self.assertEqual(target.read_bytes(), wav_fixture())
        self.assertEqual((self.output / "manifest.json").read_bytes(), manifest)

    def test_synthesize_retries_only_retryable_errors_and_rejects_empty_audio(self):
        class TemporaryFailure(Exception):
            pass

        sdk = SimpleNamespace(SynthesizeSpeechRequest=lambda **request: request)
        request = audio.synthesis_request(entry(), audio.DEFAULT_VOICE, 1.0, "wav")
        client = Mock()
        client.synthesize_speech.side_effect = [TemporaryFailure(), SimpleNamespace(audio_content=wav_fixture("done"))]
        with patch.object(audio.time, "sleep") as sleep, redirect_stdout(io.StringIO()):
            result = audio.synthesize(client, sdk, (TemporaryFailure,), request, max_retries=1)
        self.assertEqual(result, wav_fixture("done"))
        self.assertEqual(client.synthesize_speech.call_count, 2)
        sleep.assert_called_once_with(1)
        client.synthesize_speech.reset_mock()
        client.synthesize_speech.side_effect = [SimpleNamespace(audio_content=b"")]
        with self.assertRaisesRegex(RuntimeError, "empty audio"):
            audio.synthesize(client, sdk, (TemporaryFailure,), request, max_retries=0)
        self.assertEqual(client.synthesize_speech.call_count, 1)

    def test_failed_quality_check_preserves_existing_audio_and_manifest(self):
        self.args.limit = 1
        self.run_main()
        before = {path.name: path.read_bytes() for path in self.output.iterdir()}
        self.args.force = True
        client = Mock()
        client.synthesize_speech.return_value = SimpleNamespace(audio_content=wav_fixture(amplitude=0.009))
        sdk = SimpleNamespace(SynthesizeSpeechRequest=lambda **request: request)
        with patch.object(audio, "parse_args", return_value=self.args), \
             patch.object(audio, "create_google_client", return_value=(client, sdk, ())), \
             redirect_stdout(io.StringIO()), self.assertRaises(audio.AudioQualityError):
            audio.main()
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.output.iterdir()})
        self.assertEqual(client.synthesize_speech.call_count, 1)


class AudioSignalTests(unittest.TestCase):
    def test_wav_and_mp3_with_signal_are_accepted_without_a_minimum_word_duration(self):
        for format in ("WAV", "MP3"):
            with self.subTest(format=format):
                metrics = audio.validate_audio_signal(wav_fixture(seconds=0.1, format=format))
                self.assertGreater(metrics["peak_dbfs"], -35)
                self.assertGreater(metrics["duration_seconds"], 0)
                self.assertLess(metrics["duration_seconds"], 0.4)

    def test_rejects_silence_near_silence_empty_and_broken_files(self):
        for content in (b"", b"not an audio", wav_fixture(seconds=0),
                        wav_fixture(amplitude=0), wav_fixture(amplitude=0.009)):
            with self.subTest(length=len(content)), self.assertRaises(audio.AudioQualityError):
                audio.validate_audio_signal(content)
        # A quiet but usable signal is not normalized or forced to a new duration.
        audio.validate_audio_signal(wav_fixture(amplitude=0.025))

    def test_non_finite_samples_are_rejected(self):
        import numpy as np
        import soundfile as sf

        for value in (np.nan, np.inf):
            stream = io.BytesIO()
            sf.write(stream, np.full(2400, value), 24000, format="WAV", subtype="FLOAT")
            with self.subTest(value=value), self.assertRaises(audio.AudioQualityError):
                audio.validate_audio_signal(stream.getvalue())

    def test_quiet_cache_is_rejected_despite_matching_request_and_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            request = audio.synthesis_request(entry(), audio.DEFAULT_VOICE, 1.0, "wav")
            path = Path(directory) / audio.audio_name(entry(), "wav")
            content = wav_fixture(amplitude=0.009)
            path.write_bytes(content)
            record = {"generation_version": audio.GENERATION_VERSION, "audio_file": path.name,
                      "request": request, "audio_sha256": hashlib.sha256(content).hexdigest()}
            self.assertFalse(audio.reusable_audio(path, record, request))
            self.assertEqual(path.read_bytes(), content)

    def test_retries_the_exact_request_after_a_quiet_output(self):
        sdk = SimpleNamespace(SynthesizeSpeechRequest=lambda **request: request)
        request = audio.synthesis_request(entry(yomigana="^は!し"), audio.DEFAULT_VOICE, 1.0, "wav")
        before = deepcopy(request)
        good = wav_fixture()
        client = Mock()
        client.synthesize_speech.side_effect = [SimpleNamespace(audio_content=wav_fixture(amplitude=0.009)),
                                               SimpleNamespace(audio_content=good)]
        with patch.object(audio.time, "sleep") as sleep, redirect_stdout(io.StringIO()):
            self.assertEqual(audio.synthesize(client, sdk, (), request, 1), good)
        self.assertEqual(request, before)
        self.assertEqual(client.synthesize_speech.call_count, 2)
        self.assertTrue(all(call.kwargs["request"] == before for call in client.synthesize_speech.call_args_list))
        sleep.assert_called_once_with(1)

    def test_exhausted_quality_retries_raise_without_silent_fallback(self):
        sdk = SimpleNamespace(SynthesizeSpeechRequest=lambda **request: request)
        client = Mock()
        client.synthesize_speech.return_value = SimpleNamespace(audio_content=wav_fixture(amplitude=0.009))
        request = audio.synthesis_request(entry(), audio.DEFAULT_VOICE, 1.0, "wav")
        with patch.object(audio.time, "sleep"), redirect_stdout(io.StringIO()), \
             self.assertRaisesRegex(audio.AudioQualityError, "near-silent"):
            audio.synthesize(client, sdk, (), request, 2)
        self.assertEqual(client.synthesize_speech.call_count, 3)


if __name__ == "__main__":
    unittest.main()
