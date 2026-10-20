from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import soundfile as sf
from kokoro import KPipeline


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_DIR = ROOT_DIR / "contenu csv"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "audio" / "vocabulary"
VOCAB_FILES = sorted(DEFAULT_INPUT_DIR.glob("* Vocab.csv"))
JLPT_PRIORITY = {"N5": 0, "N4": 1, "N3": 2, "N2": 3, "N1": 4}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Japanese vocabulary audio with Kokoro.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--voice", default="jf_alpha")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--format", choices=("wav", "mp3"), default="wav")
    parser.add_argument("--bitrate", default="64k", help="MP3 bitrate when --format mp3 is used.")
    parser.add_argument("--limit", type=int, help="Only generate the first N unique entries.")
    return parser.parse_args()


def is_kana_text(text: str) -> bool:
    characters = text.replace("/", "").replace("・", "").replace(" ", "").replace("　", "")
    return bool(characters) and all(
        "ぁ" <= character <= "ゖ" or "ァ" <= character <= "ヺ" or character == "ー"
        for character in characters
    )


def source_priority(path: Path) -> int:
    source = path.stem.removesuffix(" Vocab")
    return JLPT_PRIORITY.get(source.split()[-1], len(JLPT_PRIORITY))


def load_vocabulary(input_dir: Path) -> list[dict[str, str]]:
    entries: dict[tuple[str, str], dict[str, str]] = {}
    files = sorted(input_dir.glob("* Vocab.csv"), key=source_priority)
    if not files:
        raise FileNotFoundError(f"No '* Vocab.csv' files found in {input_dir}")

    for csv_path in files:
        source = csv_path.stem.removesuffix(" Vocab")
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row_number, row in enumerate(csv.DictReader(handle, delimiter=";"), start=2):
                japanese = (row.get("Kanji") or "").strip()
                reading = (row.get("Hiragana") or "").strip()
                if not reading and is_kana_text(japanese):
                    reading = japanese
                    japanese = ""
                if not reading:
                    print(f"Skipping {csv_path.name}:{row_number}: missing Hiragana")
                    continue

                key = (japanese, reading)
                if key not in entries:
                    entries[key] = {
                        "japanese": japanese or reading,
                        "reading": reading,
                        "sources": [source],
                    }
                elif source not in entries[key]["sources"]:
                    entries[key]["sources"].append(source)

    return list(entries.values())


def audio_name(entry: dict[str, object], extension: str) -> str:
    key = f"{entry['japanese']}\t{entry['reading']}".encode("utf-8")
    digest = hashlib.sha256(key).hexdigest()[:16]
    return f"{digest}.{extension}"


def normalize_kana(text: str) -> str:
    return "".join(
        chr(ord(character) - 0x60) if "ァ" <= character <= "ヺ" else character
        for character in text.strip()
    )


def kanji_reading_matches(tagger: Any, japanese: str, reading: str) -> bool:
    if not japanese:
        return False

    detected = "".join(
        token.feature.kana
        for token in tagger(japanese)
        if token.feature.kana and token.feature.kana != "*"
    )
    detected = normalize_kana(detected)
    expected_readings = {normalize_kana(value) for value in reading.split("/") if value.strip()}
    return bool(detected) and detected in expected_readings


def write_mp3(audio, output_path: Path, bitrate: str) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for --format mp3; install it or use --format wav")

    temporary_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    temporary_wav.close()
    try:
        sf.write(temporary_wav.name, audio, 24000, subtype="PCM_16")
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-v",
                "error",
                "-i",
                temporary_wav.name,
                "-codec:a",
                "libmp3lame",
                "-b:a",
                bitrate,
                "-ac",
                "1",
                "-ar",
                "24000",
                str(output_path),
            ],
            check=True,
        )
    finally:
        Path(temporary_wav.name).unlink(missing_ok=True)


def save_manifest(manifest_path: Path, manifest: dict[str, list[dict[str, object]]]) -> None:
    temporary_path = manifest_path.with_suffix(".json.tmp")
    temporary_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(manifest_path)


def print_progress(index: int, total: int, pending: int, entry: dict[str, object], created: int, reused: int) -> None:
    width = 30
    completed = int(width * index / total) if total else width
    bar = "#" * completed + "-" * (width - completed)
    percentage = index / total * 100 if total else 100
    label = str(entry["japanese"] or entry["reading"])
    print(
        f"\r\033[K[{bar}] {percentage:6.2f}% ({index}/{total}) "
        f"generation={created}/{pending} reused={reused} {label}",
        end="",
        flush=True,
    )


def main() -> None:
    args = parse_args()
    if args.speed <= 0:
        raise ValueError("--speed must be greater than 0")

    entries = load_vocabulary(args.input_dir)
    if args.limit is not None:
        entries = entries[: args.limit]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    extension = args.format
    pending_count = sum(not (args.output_dir / audio_name(entry, extension)).exists() for entry in entries)
    print(f"Session: {len(entries)} entries, {pending_count} audios to generate, {len(entries) - pending_count} to reuse")
    manifest: dict[str, list[dict[str, object]]] = {}
    manifest_path = args.output_dir / "manifest.json"
    save_manifest(manifest_path, manifest)
    tagger = importlib.import_module("fugashi").Tagger()
    pipeline = KPipeline(lang_code="j", repo_id="hexgrad/Kokoro-82M")
    started_at = time.time()
    generated_count = 0
    reused_count = 0

    for index, entry in enumerate(entries, start=1):
        filename = audio_name(entry, extension)
        output_path = args.output_dir / filename
        if not output_path.exists():
            tts_text = entry["japanese"] if kanji_reading_matches(tagger, entry["japanese"], entry["reading"]) else entry["reading"]
            generator = pipeline(f"{tts_text}。", voice=args.voice, speed=args.speed, split_pattern=r"\n+")
            _, _, audio = next(generator)
            if args.format == "wav":
                sf.write(output_path, audio, 24000, subtype="PCM_16")
            else:
                write_mp3(audio, output_path, args.bitrate)
            generated_count += 1
        else:
            reused_count += 1

        manifest_entry = {
            "japanese": entry["japanese"],
            "reading": entry["reading"],
            "audio_file": filename,
        }
        manifest.setdefault(entry["sources"][0], []).append(manifest_entry)
        save_manifest(manifest_path, manifest)
        print_progress(index, len(entries), pending_count, entry, generated_count, reused_count)

    print()
    print(f"Generated or reused {len(entries)} files in {args.output_dir}")
    print(f"Manifest: {manifest_path}")
    print(f"Elapsed: {time.time() - started_at:.1f}s")


if __name__ == "__main__":
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    main()
