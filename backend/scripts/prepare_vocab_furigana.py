"""Prepare or validate the explicit Furigana column without changing source words."""

import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
import shutil
import tempfile

from app.utils.furigana import KANJI_RE, build_furigana, hiragana, reading_variants, validate_furigana


ROOT = Path(__file__).resolve().parents[2]


def reference_segments(surface: str, reading: str, reference: dict) -> list[dict] | None:
    variants = []
    for value in reading_variants(reading):
        candidates = reference.get((surface, value), [])
        if len(candidates) != 1:
            return None
        parts = candidates[0]
        try:
            validate_furigana(surface, value, parts)
        except ValueError:
            return None
        variants.append(parts)
    # Keep boundaries shared by every reading, never split a jukujikun merely
    # because another reading of the same word is compositional.
    common = None
    for parts in variants:
        position = 0
        boundaries = {0}
        for part in parts:
            position += len(part["surface"])
            boundaries.add(position)
        common = boundaries if common is None else common & boundaries
    boundaries = sorted(common or [])
    merged = []
    for start, end in zip(boundaries, boundaries[1:]):
        written = surface[start:end]
        readings = []
        for parts in variants:
            position = 0
            value = ""
            for part in parts:
                next_position = position + len(part["surface"])
                if start <= position and next_position <= end:
                    value += part.get("reading") or hiragana(part["surface"])
                position = next_position
            readings.append(value)
        merged.append({"surface": written, **({"reading": " / ".join(dict.fromkeys(readings))} if KANJI_RE.fullmatch(written) else {})})
    try:
        return validate_furigana(surface, reading, merged)
    except ValueError:
        return None


def load_reference(path: Path) -> dict:
    reference = {}
    for row in json.loads(path.read_text(encoding="utf-8-sig")):
        parts = [{"surface": part["ruby"], **({"reading": hiragana(part["rt"])} if part.get("rt") else {})} for part in row["furigana"]]
        candidates = reference.setdefault((row["text"], hiragana(row["reading"])), [])
        if parts not in candidates:
            candidates.append(parts)
    return reference


def prepare(input_dir: Path, *, write: bool, report: Path, reference_path: Path | None = None) -> dict[str, int]:
    reference = load_reference(reference_path) if reference_path else {}
    paths = sorted(input_dir.glob("* Vocab.csv"))
    if not paths:
        raise ValueError("No vocabulary CSV files found")
    counts: Counter[str] = Counter()
    pending = []
    review = []
    duplicate_segments = {}
    for path in paths:
        original = path.read_bytes()
        reader = csv.DictReader(io.StringIO(original.decode("utf-8-sig"), newline=""), delimiter=";")
        fields = list(reader.fieldnames or [])
        if "Furigana" not in fields:
            if not write:
                raise ValueError(f"{path.name}: missing Furigana column")
            fields.insert(fields.index("Hiragana") + 1, "Furigana")
        rows = list(reader)
        for line, row in enumerate(rows, start=2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{path.name}:{line}: malformed CSV row")
            surface = (row.get("Kanji") or row.get("Hiragana") or "").strip()
            reading = (row.get("Hiragana") or "").strip()
            if not surface:
                raise ValueError(f"{path.name}:{line}: missing written form")
            generated, status = build_furigana(surface, reading)
            original_generated = generated
            refined = reference_segments(surface, reading, reference) if reference else None
            if refined is not None:
                generated, status = refined, "lexical_reference"
            if row.get("Furigana", "").strip():
                segments = validate_furigana(surface, reading, json.loads(row["Furigana"]))
                if write and refined is not None and segments == original_generated:
                    segments = refined
                if segments != generated:
                    status = "explicit" if any(part.get("reading") for part in segments) else "unannotated"
            elif write:
                segments = generated
            else:
                raise ValueError(f"{path.name}:{line}: empty Furigana column")
            validate_furigana(surface, reading, segments)
            key = (surface, reading)
            if key in duplicate_segments and duplicate_segments[key] != segments:
                raise ValueError(f"{path.name}:{line}: conflicting furigana for {surface}")
            duplicate_segments[key] = segments
            row["Furigana"] = json.dumps(segments, ensure_ascii=False, separators=(",", ":"))
            counts[status] += 1
            if KANJI_RE.search(surface) and not any(part.get("reading") for part in segments):
                review.append({"file": path.name, "line": line, "japanese": surface, "reading": reading, "reason": status})
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=fields, delimiter=";", lineterminator="\r\n" if b"\r\n" in original else "\n")
        writer.writeheader()
        writer.writerows(rows)
        encoded = output.getvalue().encode("utf-8-sig" if original.startswith(b"\xef\xbb\xbf") else "utf-8")
        pending.append((path, original, encoded))

    if write:
        backup = Path(tempfile.mkdtemp(prefix="vocab-furigana-backup-"))
        for path, original, encoded in pending:
            if path.read_bytes() != original:
                raise RuntimeError(f"{path.name} changed during preparation; retry")
            shutil.copy2(path, backup / path.name)
        for path, _, encoded in pending:
            temporary = path.with_suffix(".csv.tmp")
            temporary.write_bytes(encoded)
            temporary.replace(path)
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["file", "line", "japanese", "reading", "reason"])
            writer.writeheader()
            writer.writerows(review)
        print(f"Backup: {backup}")
        print(f"Review report: {report} ({len(review)} rows)")
    print(f"Validated: {sum(counts.values())} rows, {len(duplicate_segments)} unique words")
    print(json.dumps(dict(counts), ensure_ascii=False, sort_keys=True))
    return dict(counts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=ROOT / "contenu csv")
    parser.add_argument("--write", action="store_true", help="Add missing segments and write the review report; default: validate only")
    parser.add_argument("--report", type=Path, default=ROOT / "docs" / "vocabulary-furigana-review.csv")
    parser.add_argument("--reference", type=Path, help="Local JmdictFurigana.json to refine automatically generated groups; explicit corrections are preserved")
    args = parser.parse_args()
    prepare(args.input_dir, write=args.write, report=args.report, reference_path=args.reference)
