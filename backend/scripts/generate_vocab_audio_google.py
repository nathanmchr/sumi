from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import random
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape, quoteattr


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_DIR = ROOT_DIR / "contenu csv" / "consolidated"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "audio" / "vocabulary-chirp3-yomigana"
GENERATION_VERSION = "chirp3-yomigana-v1"
YOMIGANA = "PHONETIC_ENCODING_JAPANESE_YOMIGANA"
JLPT_PRIORITY = {"N5": 0, "N4": 1, "N3": 2, "N2": 3, "N1": 4}
DEFAULT_VOICE = "ja-JP-Chirp3-HD-Aoede"
CHIRP_PRICE_PER_CHARACTER_USD = 30 / 1_000_000


class AudioQualityError(RuntimeError):
    """Unusable synthesis output, not a linguistic pronunciation assessment."""


def validate_audio_signal(content: bytes) -> dict[str, float]:
    """Reject broken/near-silent WAV or MP3 output, including cached files.

    -35 dBFS is a conservative peak screen: the two reproduced failed outputs
    peak at -40/-37 dBFS; all other 8,036 corpus files peak above -15 dBFS.
    There is deliberately no minimum word duration or guessed accent check.
    """
    import numpy as np
    import soundfile as sf

    if not content:
        raise AudioQualityError("Google returned empty audio; no file will be saved")
    try:
        samples, rate = sf.read(io.BytesIO(content), dtype="float32", always_2d=True)
    except (sf.LibsndfileError, ValueError) as exc:
        raise AudioQualityError("Google returned undecodable audio; no file will be saved") from exc
    if not samples.size or rate <= 0 or not np.isfinite(samples).all():
        raise AudioQualityError("Google returned empty or non-finite samples; no file will be saved")
    peak = float(np.max(np.abs(samples)))
    peak_dbfs = 20 * math.log10(max(peak, 1e-10))
    if peak_dbfs < -35:
        raise AudioQualityError(f"Google returned near-silent audio (peak {peak_dbfs:.1f} dBFS); no file will be saved")
    return {"duration_seconds": len(samples) / rate, "peak_dbfs": peak_dbfs}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate audio for the complete Japanese vocabulary with Google Chirp 3 HD.",
        epilog="Authentication: GOOGLE_TTS_API_KEY environment variable, or Google ADC if unset/empty.",
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--format", choices=("wav", "mp3"), default="wav")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Generate at most N entries (default: all vocabulary).",
    )
    selection.add_argument(
        "--all",
        action="store_true",
        help="Generate the complete vocabulary (already the default).",
    )
    selection.add_argument("--ids", nargs="+", help="Generate only these consolidated catalog IDs, in catalog order.")
    parser.add_argument(
        "--shuffle",
        action="store_true",
        help="Shuffle deterministically before applying the optional limit.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Seed used with --shuffle.")
    parser.add_argument(
        "--requests-per-minute",
        type=int,
        default=180,
        help="Client-side rate limit; Chirp 3 currently allows 200 requests/minute.",
    )
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate files that already exist in the output directory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the selected entries and estimated usage without calling Google.",
    )
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


def load_vocabulary(input_dir: Path) -> list[dict[str, Any]]:
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    consolidated = input_dir / "vocabulary.csv"
    files = [consolidated] if consolidated.is_file() else sorted(
        input_dir.glob("* Vocab.csv"), key=source_priority
    )
    if not files:
        raise FileNotFoundError(f"No vocabulary.csv or '* Vocab.csv' files found in {input_dir}")

    for csv_path in files:
        source = csv_path.stem.removesuffix(" Vocab")
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row_number, row in enumerate(csv.DictReader(handle, delimiter=";"), start=2):
                location = f"{csv_path.name}:{row_number}"
                is_consolidated = csv_path == consolidated
                japanese = (row.get("Kanji") or "").strip()
                reading = (row.get("Kana" if is_consolidated else "Hiragana") or "").strip()
                if not reading and is_kana_text(japanese):
                    reading = japanese
                    japanese = ""
                if not reading:
                    raise ValueError(f"{location}: missing kana reading")

                identity = (row.get("ID") or "").strip()
                level = (row.get("Level") or "").strip() if is_consolidated else source
                if is_consolidated and (not identity or level not in JLPT_PRIORITY):
                    raise ValueError(f"{location}: missing ID or invalid Level")
                key = ("id", identity) if is_consolidated else (japanese, reading)
                if is_consolidated and key in entries:
                    raise ValueError(f"{location}: duplicate ID {identity}")
                if key not in entries:
                    entries[key] = {
                        "japanese": japanese or reading,
                        "reading": reading,
                        "sources": [level],
                        "source_rows": [location],
                    }
                    if is_consolidated:
                        entries[key]["id"] = identity
                    if row.get("Yomigana"):
                        entries[key]["yomigana"] = row["Yomigana"].strip()
                else:
                    if entries[key].get("yomigana", "") != (row.get("Yomigana") or "").strip():
                        raise ValueError(f"{location}: conflicting Yomigana for duplicate {japanese!r}; review source annotations")
                    entries[key]["source_rows"].append(location)
                    if level not in entries[key]["sources"]:
                        entries[key]["sources"].append(level)

    return list(entries.values())


def audio_name(
    entry: dict[str, Any], extension: str, voice_name: str = DEFAULT_VOICE, speed: float = 1.0
) -> str:
    key = {
        "version": GENERATION_VERSION,
        "identity": entry_identity(entry),
        "request": synthesis_request(entry, voice_name, speed, extension),
    }
    digest = hashlib.sha256(json.dumps(key, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]
    return f"{digest}.{extension}"


def reading_parts(entry: dict[str, Any]) -> list[str]:
    """Keep listed alternatives/pauses in order; never infer a reading or accent."""
    reading = unicodedata.normalize("NFKC", str(entry["reading"]))
    parts = [part.strip().replace("・", "") for part in re.split(r"[/、]", reading)]
    for part in parts:
        if not part or not all(
            "ぁ" <= char <= "ゖ" or "ァ" <= char <= "ヺ" or char == "ー"
            for char in part
        ):
            location = ", ".join(entry.get("source_rows", [])) or str(entry.get("id", entry["japanese"]))
            raise ValueError(f"{location}: unsupported kana reading {entry['reading']!r}; review it before synthesis")
    return parts


def pronunciation_parts(entry: dict[str, Any]) -> list[str]:
    readings = reading_parts(entry)
    raw = str(entry.get("yomigana") or "").strip()
    if not raw:
        return readings
    parts = [part.strip() for part in re.split(r"[/、]", unicodedata.normalize("NFKC", raw))]
    location = ", ".join(entry.get("source_rows", [])) or str(entry.get("id", entry["japanese"]))

    def comparable(text: str) -> str:
        return "".join(chr(ord(char) - 0x60) if "ァ" <= char <= "ヶ" else char for char in text)

    if len(parts) != len(readings):
        raise ValueError(f"{location}: Yomigana must keep every Kana reading in the same order")
    for part, reading in zip(parts, readings, strict=True):
        plain = part.replace("^", "").replace("!", "")
        if comparable(plain) != comparable(reading):
            raise ValueError(f"{location}: Yomigana {part!r} does not match Kana {reading!r}")
        invalid = part.count("^") > 1 or ("^" in part and not part.startswith("^"))
        invalid |= part.count("!") > 1 or ("!" in part and not part.startswith("^"))
        if "!" in part:
            before, after = part.split("!", 1)
            invalid |= before == "^" or (bool(after) and after[0] in "ゃゅょぁぃぅぇぉゎャュョァィゥェォヮ")
        if invalid:
            raise ValueError(f"{location}: invalid Yomigana accent markers in {part!r}")
    return parts


def speech_input(entry: dict[str, Any]) -> dict[str, Any]:
    parts = pronunciation_parts(entry)
    japanese = str(entry["japanese"]).strip() or reading_parts(entry)[0]
    if len(parts) == 1:
        if "/" in unicodedata.normalize("NFKC", japanese):
            # Alternative spellings are display text, not successive words.
            # Use the known kana once; the first fragment may be incomplete
            # (e.g. 堅/硬/固い). The explicit Yomigana accent stays unchanged.
            japanese = reading_parts(entry)[0]
        # Inline scope avoids Google's custom-pronunciation phrase matcher,
        # which rejects some valid Japanese words (e.g. 太い / ふとい).
        return {"ssml": f'<speak><phoneme alphabet="yomigana" ph={quoteattr(parts[0])}>{escape(japanese)}</phoneme>。</speak>'}
    # One override per occurrence avoids contradictory global replacements of 四 etc.
    phonemes = [
        f'<phoneme alphabet="yomigana" ph={quoteattr(part)}>{escape(part.replace("^", "").replace("!", ""))}</phoneme>'
        for part in parts
    ]
    return {"ssml": "<speak>" + "、".join(phonemes) + "。</speak>"}


def synthesis_request(
    entry: dict[str, Any], voice_name: str, speed: float, audio_format: str
) -> dict[str, Any]:
    return {
        "input": speech_input(entry),
        "voice": {"language_code": "ja-JP", "name": voice_name},
        "audio_config": {
            "audio_encoding": "LINEAR16" if audio_format == "wav" else "MP3",
            "speaking_rate": float(speed),
        },
    }


def entry_identity(entry: dict[str, Any]) -> tuple[str, ...]:
    return ("id", entry["id"]) if entry.get("id") else ("word", entry["japanese"], entry["reading"])


def select_entries(entries: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit must be greater than 0")
    selected = entries.copy()
    if identities := getattr(args, "ids", None):
        missing = set(identities) - {entry.get("id") for entry in entries}
        if missing:
            raise ValueError(f"Unknown catalog IDs: {', '.join(sorted(missing))}")
        selected = [entry for entry in selected if entry.get("id") in identities]
    if args.shuffle:
        random.Random(args.seed).shuffle(selected)
    return selected[: args.limit]


def save_manifest(manifest_path: Path, manifest: dict[str, list[dict[str, Any]]]) -> None:
    temporary_path = manifest_path.with_suffix(".json.tmp")
    temporary_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(manifest_path)


def load_manifest(manifest_path: Path) -> dict[str, list[dict[str, Any]]]:
    if not manifest_path.exists():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or any(
        not isinstance(rows, list) or any(
            not isinstance(row, dict)
            or row.get("generation_version") != GENERATION_VERSION
            or not all(key in row for key in ("japanese", "reading", "audio_file", "request", "audio_sha256"))
            for row in rows
        ) for rows in manifest.values()
    ):
        raise ValueError("Incompatible audio manifest: choose a separate --output-dir; existing files were not changed")
    return manifest


def reusable_audio(path: Path, record: dict[str, Any] | None, request: dict[str, Any]) -> bool:
    if not (
        record and record.get("generation_version") == GENERATION_VERSION
        and record.get("audio_file") == path.name and record.get("request") == request
    ):
        return False
    try:
        if not path.is_file():
            return False
        content = path.read_bytes()
        if record.get("audio_sha256") != hashlib.sha256(content).hexdigest():
            return False
        validate_audio_signal(content)
    except (OSError, AudioQualityError):
        return False
    return True


def update_manifest(manifest: dict[str, list[dict[str, Any]]], source: str, record: dict[str, Any]) -> None:
    for rows in manifest.values():
        for index, previous in enumerate(rows):
            if entry_identity(previous) == entry_identity(record):
                rows[index] = record
                return
    manifest.setdefault(source, []).append(record)


def print_progress(
    index: int,
    total: int,
    pending: int,
    entry: dict[str, Any],
    created: int,
    reused: int,
) -> None:
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


def create_google_client() -> tuple[Any, Any, tuple[type[Exception], ...]]:
    try:
        from google.api_core import exceptions as google_exceptions
        from google.auth.exceptions import DefaultCredentialsError
        from google.cloud import texttospeech
    except ImportError as exc:
        raise RuntimeError(
            "Missing Google Cloud client. From the project root, run 'uv sync --project backend'."
        ) from exc

    retryable_errors = (
        google_exceptions.DeadlineExceeded,
        google_exceptions.InternalServerError,
        google_exceptions.ResourceExhausted,
        google_exceptions.ServiceUnavailable,
        google_exceptions.TooManyRequests,
    )
    api_key = os.environ.get("GOOGLE_TTS_API_KEY", "").strip()
    try:
        client = (
            texttospeech.TextToSpeechClient(client_options={"api_key": api_key})
            if api_key
            else texttospeech.TextToSpeechClient()
        )
    except DefaultCredentialsError as exc:
        raise RuntimeError(
            "Google credentials are missing. Set GOOGLE_TTS_API_KEY or run "
            "'gcloud auth application-default login'."
        ) from exc
    return client, texttospeech, retryable_errors


def synthesize(
    client: Any,
    texttospeech: Any,
    retryable_errors: tuple[type[Exception], ...],
    request: dict[str, Any],
    max_retries: int,
) -> bytes:
    google_request = texttospeech.SynthesizeSpeechRequest(**request)
    recoverable_errors = (AudioQualityError,) + retryable_errors

    for attempt in range(max_retries + 1):
        try:
            response = client.synthesize_speech(request=google_request)
            validate_audio_signal(response.audio_content)
            return response.audio_content
        except recoverable_errors as exc:
            if attempt == max_retries:
                raise
            delay = min(2**attempt, 30)
            reason = "Unusable audio" if isinstance(exc, AudioQualityError) else "Temporary Google API error"
            print(f"\n{reason}; retrying the same request in {delay}s...", flush=True)
            time.sleep(delay)

    raise RuntimeError("Unreachable synthesis retry state")


def validate_args(args: argparse.Namespace) -> None:
    if not 0.25 <= args.speed <= 2.0:
        raise ValueError("--speed must be between 0.25 and 2.0 for Chirp 3 HD")
    if not 1 <= args.requests_per_minute <= 200:
        raise ValueError("--requests-per-minute must be between 1 and 200")
    if args.max_retries < 0:
        raise ValueError("--max-retries must be zero or greater")
    if not args.voice.startswith("ja-JP-Chirp3-HD-"):
        raise ValueError("--voice must be a Japanese Chirp 3 HD voice")


def main() -> None:
    args = parse_args()
    validate_args(args)
    entries = select_entries(load_vocabulary(args.input_dir), args)
    prepared = [(entry, synthesis_request(entry, args.voice, args.speed, args.format)) for entry in entries]
    character_count = sum(len(request["input"].get("text", request["input"].get("ssml", ""))) for _, request in prepared)
    estimated_cost = character_count * CHIRP_PRICE_PER_CHARACTER_USD

    print(f"Selection: {len(prepared)} unique entries")
    print(f"Input characters (including SSML): {character_count}")
    print(f"Indicative text cost before free tier: US${estimated_cost:.4f}; pronunciation billing not verified")
    print(f"Voice: {args.voice}; speed: {args.speed}; format: {args.format}")

    if args.dry_run:
        for entry, request in prepared:
            print(f"- {entry['japanese']} [{entry['reading']}] -> {json.dumps(request['input'], ensure_ascii=False)}")
        print("Dry run: no API request and no file created.")
        return

    manifest_path = args.output_dir / "manifest.json"
    manifest = load_manifest(manifest_path)
    previous_records = {entry_identity(row): row for rows in manifest.values() for row in rows}
    extension = args.format
    pending_count = sum(
        args.force or not reusable_audio(
            args.output_dir / audio_name(entry, extension, args.voice, args.speed),
            previous_records.get(entry_identity(entry)), request,
        ) for entry, request in prepared
    )
    print(
        f"Session: {len(prepared)} entries, {pending_count} audios to generate, "
        f"{len(prepared) - pending_count} to reuse"
    )

    if not pending_count:
        print("All selected audios have matching requests, checksums, and usable signal; no API request needed.")
        return
    client, texttospeech, retryable_errors = create_google_client()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    minimum_interval = 60 / args.requests_per_minute
    previous_request_at: float | None = None
    started_at = time.monotonic()
    generated_count = 0
    reused_count = 0

    for index, (entry, request) in enumerate(prepared, start=1):
        filename = audio_name(entry, extension, args.voice, args.speed)
        output_path = args.output_dir / filename
        previous = previous_records.get(entry_identity(entry))
        if args.force or not reusable_audio(output_path, previous, request):
            if previous_request_at is not None:
                elapsed = time.monotonic() - previous_request_at
                if elapsed < minimum_interval:
                    time.sleep(minimum_interval - elapsed)

            previous_request_at = time.monotonic()
            audio = synthesize(
                client=client,
                texttospeech=texttospeech,
                retryable_errors=retryable_errors,
                request=request,
                max_retries=args.max_retries,
            )
            temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
            temporary_path.write_bytes(audio)
            temporary_path.replace(output_path)
            generated_count += 1
            manifest_entry = {
                **entry,
                "audio_file": filename,
                "generation_version": GENERATION_VERSION,
                "request": request,
                "audio_sha256": hashlib.sha256(audio).hexdigest(),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "pronunciation_verified": False,
            }
        else:
            reused_count += 1
            manifest_entry = {**previous, **entry}
        update_manifest(manifest, entry["sources"][0], manifest_entry)
        save_manifest(manifest_path, manifest)
        print_progress(
            index,
            len(prepared),
            pending_count,
            entry,
            generated_count,
            reused_count,
        )

    print()
    print(f"Generated or reused {len(prepared)} files in {args.output_dir}")
    print(f"Manifest: {manifest_path}")
    print(f"Elapsed: {time.monotonic() - started_at:.1f}s")


if __name__ == "__main__":
    main()
