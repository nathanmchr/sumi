"""Conservative furigana alignment and validation for explicit dataset segments."""

from functools import lru_cache
from itertools import product
import re
import unicodedata
from typing import Any


KANJI = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af々〆〇"
KANJI_RE = re.compile(f"[{KANJI}]+")
PARTS_RE = re.compile(f"[{KANJI}]+|[^{KANJI}]+")
KANA_RE = re.compile(r"[ぁ-ゖー]+")


def hiragana(text: str) -> str:
    return "".join(
        chr(ord(char) - 0x60) if "ァ" <= char <= "ヶ" else char
        for char in unicodedata.normalize("NFC", text)
    )


def reading_variants(reading: str) -> list[str]:
    return list(dict.fromkeys(hiragana(part.strip()) for part in re.split(r"[/／]", reading)))


def _align(parts: list[str], reading: str) -> tuple[tuple[str, ...], ...]:
    @lru_cache(maxsize=None)
    def visit(index: int, offset: int) -> tuple[tuple[str, ...], ...]:
        if index == len(parts):
            return ((),) if offset == len(reading) else ()
        part = parts[index]
        if not KANJI_RE.fullmatch(part):
            anchor = hiragana(part)
            if not reading.startswith(anchor, offset):
                return ()
            return tuple(("", *tail) for tail in visit(index + 1, offset + len(anchor)))
        results = []
        for end in range(offset + 1, len(reading) + 1):
            for tail in visit(index + 1, end):
                results.append((reading[offset:end], *tail))
                if len(results) == 2:
                    return tuple(results)
        return tuple(results)

    return visit(0, 0)


def build_furigana(surface: str, reading: str) -> tuple[list[dict[str, str]], str]:
    """Annotate only uniquely aligned kanji groups; ambiguous data stays plain."""
    parts = PARTS_RE.findall(surface)
    plain = [{"surface": part} for part in parts]
    if not KANJI_RE.search(surface):
        return plain, "kana_or_plain"
    variants = reading_variants(reading)
    if not reading.strip():
        return plain, "missing_reading"
    if any(not KANA_RE.fullmatch(value) for value in variants):
        return plain, "non_kana_reading"
    aligned = []
    for value in variants:
        candidates = _align(parts, value)
        if len(candidates) != 1:
            return plain, "ambiguous_alignment" if candidates else "reading_mismatch"
        aligned.append(candidates[0])
    segments = [
        {"surface": part, **({"reading": " / ".join(dict.fromkeys(row[index] for row in aligned))}
                               if KANJI_RE.fullmatch(part) else {})}
        for index, part in enumerate(parts)
    ]
    try:
        validate_furigana(surface, reading, segments)
    except ValueError:
        # Several correlated variants cannot safely be represented as independent ruby.
        return plain, "correlated_variants"
    return segments, "aligned"


def validate_furigana(surface: str, reading: str, segments: Any) -> list[dict[str, Any]]:
    """Reject malformed, mixed-kana ruby and readings inconsistent with the source.

    Plain text is permitted for uncertain source entries. This checks structural
    consistency, not whether the source dictionary reading is linguistically true.
    """
    if not isinstance(segments, list) or not segments:
        raise ValueError("Furigana must be a non-empty JSON array")
    for segment in segments:
        if not isinstance(segment, dict) or not isinstance(segment.get("surface"), str) or not segment["surface"]:
            raise ValueError("Each furigana segment requires a non-empty surface")
        if set(segment) - {"surface", "reading", "kanji_ids"}:
            raise ValueError("Unknown furigana segment fields")
        if "reading" in segment and not isinstance(segment["reading"], str):
            raise ValueError("Furigana reading must be a string")
        ids = segment.get("kanji_ids", [])
        if not isinstance(ids, list) or any(not isinstance(value, str) for value in ids):
            raise ValueError("Furigana kanji_ids must be a list of strings")
        if segment.get("reading"):
            if not KANJI_RE.fullmatch(segment["surface"]):
                raise ValueError("Ruby must cover kanji only")
            if any(not KANA_RE.fullmatch(value) for value in reading_variants(segment["reading"])):
                raise ValueError("Furigana readings must contain kana only")
    if "".join(segment["surface"] for segment in segments) != surface:
        raise ValueError("Furigana surfaces do not reconstruct the original word")
    if not any(segment.get("reading") for segment in segments):
        return segments
    # Written alternatives can share one reading (伯父さん/叔父さん → おじさん).
    # Validate each complete spelling, not their concatenated pronunciation.
    if re.search(r"[/／]", surface) and len(reading_variants(reading)) == 1:
        groups = [[]]
        for segment in segments:
            if segment.get("reading"):
                groups[-1].append(segment)
                continue
            for part in re.split(r"([/／])", segment["surface"]):
                if part in {"/", "／"}:
                    groups.append([])
                elif part:
                    groups[-1].append({**segment, "surface": part})
        for group in groups:
            validate_furigana("".join(s["surface"] for s in group), reading, group)
        return segments
    choices = []
    combinations = 1
    for segment in segments:
        if KANJI_RE.search(segment["surface"]) and not segment.get("reading"):
            raise ValueError("Partially annotated kanji cannot reconstruct the reading")
        values = reading_variants(segment["reading"]) if segment.get("reading") else [hiragana(segment["surface"])]
        choices.append(values)
        combinations *= len(values)
        if combinations > 128:
            raise ValueError("Too many furigana reading combinations")
    reconstructed = {"".join(value) for value in product(*choices)}
    if reconstructed != set(reading_variants(reading)):
        raise ValueError("Furigana readings do not reconstruct the source reading variants")
    return segments
