"""Add conservative, sourced UniDic annotations without changing catalogue identity.

This is a separate stage AFTER reviewed corrections. A plain kana value means
the accent is not established here; only an explicit ^ means an accent phrase
was annotated. No TTS, download, audio mutation or database access is performed.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import re
from typing import Any
import unicodedata


ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = ROOT / "backend/app/data/catalog_yomigana.json"
SMALL_JOINERS = frozenset("ぁぃぅぇぉゃゅょゎ")
ANNOTATION = re.compile(r"[()（）/／・、,;；]")
KANA_WORD = re.compile(r"[ぁ-ゖー]+\Z")
UNIDIC_URL = "https://clrd.ninjal.ac.jp/unidic/"
ACCENT_MANUAL = "https://clrd.ninjal.ac.jp/unidic/UNIDIC_manual.pdf"
GOOGLE_ENCODING = "https://docs.cloud.google.com/text-to-speech/docs/reference/rest/Shared.Types/PhoneticEncoding"


def normalize_kana(value: str) -> str:
    """Normalize phonetic text only; never strip the lexical suffix する.

    Alternative readings stay separated by /, pauses by 、. Parentheses around
    kana preserve those kana; editorial text such as (=やる) is not pronounced.
    The original Kana/Notes fields remain untouched and are retained in audit.
    """
    value = unicodedata.normalize("NFKC", value)
    value = "".join(chr(ord(char) - 0x60) if "ァ" <= char <= "ヶ" else char for char in value)
    value = re.sub(r"\(([^()]*)\)",
                   lambda match: match[1] if KANA_WORD.fullmatch(match[1]) else "", value)
    value = value.replace("・する", "する")
    value = re.sub(r"[,;；・]", "、", value)
    return re.sub(r"\s+", "", value)


def morae(reading: str) -> list[str]:
    """Split hiragana into morae: きょ is one; っ, ん and ー each count as one."""
    if not KANA_WORD.fullmatch(reading):
        raise ValueError("A single kana reading is required")
    result: list[str] = []
    for char in reading:
        if char in SMALL_JOINERS:
            if not result or result[-1][-1] in SMALL_JOINERS | frozenset("っんー"):
                raise ValueError("Unattached or repeated small kana")
            result[-1] += char
        elif char in "ゕゖ":
            raise ValueError("Ambiguous small ka/ke")
        else:
            result.append(char)
    return result


def accent_yomigana(reading: str, accent: int) -> str:
    """Google ^ starts the phrase; ! follows the accented mora, including final."""
    units = morae(reading)
    if isinstance(accent, bool) or not isinstance(accent, int) or not 0 <= accent <= len(units):
        raise ValueError("Accent is outside mora bounds")
    if accent:
        units[accent - 1] += "!"
    return "^" + "".join(units)


def _feature(node: Any) -> dict[str, Any]:
    feature = node.feature
    return {
        "lemma": feature.lemma,
        "lemma_id": feature.lemma_id,
        "kana": normalize_kana(feature.kana or ""),
        "aType": feature.aType,
        "aConType": feature.aConType,
        "aModType": feature.aModType,
        "morphology": [feature.pos1, feature.pos2, feature.pos3, feature.pos4,
                       feature.cType, feature.cForm],
    }


def annotate_row(row: dict[str, str], tagger: Any, *, duplicate: bool = False,
                 candidate_limit: int = 64) -> dict[str, Any]:
    """Keep kana unaccented unless all lexical/mora checks succeed.

    N-best must be exhausted below the bound. Competing complete tokens with
    the same expected reading must agree on lemma, morphology and accent.
    This is dictionary evidence, not a human validation of all word senses.
    """
    reading = normalize_kana(row["Kana"])
    surface = unicodedata.normalize("NFKC", row["Kanji"] or row["Kana"])
    evidence: dict[str, Any] = {"yomigana": reading, "decision": "plain_kana"}

    def plain(reason: str) -> dict[str, Any]:
        return {**evidence, "reason": reason}

    # Multiple spellings/readings and editorial annotations are not accent cues.
    if ANNOTATION.search(row["Kana"] + row["Kanji"]):
        return plain("annotations_or_alternatives")
    if duplicate:
        return plain("catalogue_homograph")
    try:
        units = morae(reading)
    except ValueError:
        return plain("invalid_or_multiple_reading")
    nodes = tagger(surface)
    if len(nodes) != 1 or nodes[0].surface != surface:
        return plain("multiple_tokens_or_partial_match")
    node = nodes[0]
    if node.is_unk:
        return plain("unknown_token")
    first = _feature(node)
    evidence["dictionary"] = first
    if first["kana"] != reading:
        return plain("reading_mismatch")
    accent_text = first["aType"] or ""
    if not re.fullmatch(r"[0-9]+", accent_text):
        return plain("accent_missing_or_multiple")
    accent = int(accent_text)
    if not 0 <= accent <= len(units):
        return plain("accent_out_of_bounds")
    if first["aModType"] not in ("", "*"):
        return plain("inflection_requires_accent_rule")
    analyses = tagger.nbestToNodeList(surface, candidate_limit)
    evidence["analyses_examined"] = len(analyses)
    if len(analyses) >= candidate_limit:
        return plain("candidate_limit_not_exhaustive")
    candidates = {}
    for analysis in analyses:
        if len(analysis) != 1 or analysis[0].is_unk or analysis[0].surface != surface:
            continue
        candidate = _feature(analysis[0])
        if candidate["kana"] == reading:
            candidates[json.dumps(candidate, sort_keys=True, ensure_ascii=False)] = candidate
    if len(candidates) != 1 or first not in candidates.values():
        evidence["distinct_matching_candidates"] = len(candidates)
        evidence["candidate_examples"] = list(candidates.values())[:3]
        return plain("ambiguous_dictionary_entry")
    return {**evidence, "yomigana": accent_yomigana(reading, accent),
            "decision": "dictionary_annotation", "reason": "unique_exact_dictionary_match",
            "mora_count": len(units)}


def _sha256_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def load_dictionary(config: dict[str, Any]) -> tuple[Any, dict[str, str]]:
    """Require the pinned local dictionary; never install or silently substitute it."""
    import fugashi
    import unidic

    for package, key in (("fugashi", "fugashi_version"), ("unidic", "unidic_package_version")):
        if importlib.metadata.version(package) != config[key]:
            raise ValueError(f"Yomigana package version changed: {package}")
    directory = Path(unidic.DICDIR)
    if (directory / "version").read_text(encoding="utf-8").strip() != config["dictionary_version"]:
        raise ValueError("Yomigana UniDic data version changed")
    for name, expected in config["dictionary_files_sha256"].items():
        if _sha256_file(directory / name) != expected:
            raise ValueError(f"Yomigana dictionary fingerprint changed: {name}")
    tagger = fugashi.Tagger(f'-r "{directory / "mecabrc"}" -d "{directory}"')
    if len(tagger.dictionary_info) != 1 or Path(tagger.dictionary_info[0]["filename"]) != directory / "sys.dic":
        raise ValueError("Unexpected dictionary or user dictionary selected")
    notices = {name: (directory / "licenses" / name).read_text(encoding="utf-8")
               for name in ("BSD", "AUTHORS")}
    return tagger, notices


def enrich_vocabulary(text: str, config: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, str]]:
    """Add only Yomigana, in input order, after the existing Kana column."""
    if config["version"] != 1 or config["candidate_limit"] < 2:
        raise ValueError("Unsupported Yomigana configuration")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if digest != config["input_vocabulary_sha256"]:
        raise ValueError("Yomigana reviewed vocabulary fingerprint changed")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    headers = list(reader.fieldnames or [])
    if "Yomigana" in headers or not {"ID", "Kanji", "Kana"} <= set(headers):
        raise ValueError("Yomigana requires the pre-enrichment vocabulary schema")
    rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError("Malformed vocabulary CSV")
    if len({row["ID"] for row in rows}) != len(rows):
        raise ValueError("Duplicate vocabulary IDs")
    reviews = config.get("reviewed_overrides", [])
    overrides = {item["ID"]: item for item in reviews}
    if len(overrides) != len(reviews) or not set(overrides) <= {row["ID"] for row in rows}:
        raise ValueError("Duplicate or missing reviewed Yomigana ID")
    tagger, notices = load_dictionary(config)
    pairs = Counter((unicodedata.normalize("NFKC", row["Kanji"] or row["Kana"]),
                     normalize_kana(row["Kana"])) for row in rows)
    entries = {}
    reasons: Counter[str] = Counter()
    for row in rows:
        pair = (unicodedata.normalize("NFKC", row["Kanji"] or row["Kana"]), normalize_kana(row["Kana"]))
        result = annotate_row(row, tagger, duplicate=pairs[pair] > 1,
                              candidate_limit=config["candidate_limit"])
        if row["ID"] in overrides:
            review = overrides[row["ID"]]
            dictionary = result.get("dictionary", {})
            if (not {"Kanji", "Kana", "English", "French"} <= set(review["expect"])
                    or any(row.get(field) != value for field, value in review["expect"].items())
                    or result["reason"] not in ("ambiguous_dictionary_entry", "unique_exact_dictionary_match")
                    or dictionary.get("kana") != normalize_kana(row["Kana"])
                    or dictionary.get("lemma_id") != review["lemma_id"]
                    or dictionary.get("aType") != str(review["accent"])
                    or not review.get("reason") or not review.get("reference")):
                raise ValueError(f"Reviewed Yomigana evidence changed: {row['ID']}")
            result = {**result,
                      "yomigana": accent_yomigana(normalize_kana(row["Kana"]), review["accent"]),
                      "decision": "reviewed_dictionary_annotation",
                      "reason": "reviewed_sense_disambiguation", "review": review}
        if not re.fullmatch(r"[ぁ-ゖー/、^!]+", result["yomigana"]):
            raise ValueError(f"Unresolved non-phonetic reading: {row['ID']}")
        row["Yomigana"] = result["yomigana"]
        entries[row["ID"]] = result
        reasons[result["reason"]] += 1
    output_headers = list(headers)
    output_headers.insert(output_headers.index("Kana") + 1, "Yomigana")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=output_headers, delimiter=";", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    automatic = sum(entry["decision"] == "dictionary_annotation" for entry in entries.values())
    reviewed = sum(entry["decision"] == "reviewed_dictionary_annotation" for entry in entries.values())
    annotated = automatic + reviewed
    audit = {
        "version": 1,
        "scope": "Vocabulary only. Dictionary annotations, not human validation or audio validation.",
        "source": {"name": "UniDic", "url": UNIDIC_URL,
                   "dictionary_version": config["dictionary_version"],
                   "fugashi_version": config["fugashi_version"],
                   "unidic_package_version": config["unidic_package_version"],
                   "dictionary_files_sha256": config["dictionary_files_sha256"],
                   "license": "BSD-3-Clause (selected from GPL/LGPL/BSD triple license)",
                   "authors": notices["AUTHORS"].strip(),
                   "license_notice": "Preserve _audit/unidic/BSD and AUTHORS with redistributed data.",
                   "license_url": "https://clrd.ninjal.ac.jp/unidic/copying/BSD"},
        "conventions": {"encoding": "PHONETIC_ENCODING_JAPANESE_YOMIGANA",
                        "phrase_start": "^", "down_pitch_after_mora": "!",
                        "plain_kana": "Accent unknown here, NOT accent type 0.",
                        "alternatives": "/", "pause": "、",
                        "suru_annotation": "Remove only ・; preserve the lexical suffix する.",
                        "accent_reference": ACCENT_MANUAL, "encoding_reference": GOOGLE_ENCODING},
        "policy": {"candidate_limit": config["candidate_limit"],
                   "exact_surface_and_reading": True, "single_known_token": True,
                   "unique_lemma_morphology_and_accent": True,
                   "require_exhaustive_candidates_below_limit": True,
                   "do_not_apply_inflection_accent_rules": True},
        "input_vocabulary_sha256": digest,
        "output_vocabulary_sha256": hashlib.sha256(output.getvalue().encode("utf-8")).hexdigest(),
        "previous_stage": "_audit/corrections.json and correction-checks.ipynb describe the stage BEFORE Yomigana; their historical vocabulary hashes are preserved.",
        "summary": {"rows": len(rows), "dictionary_annotations": annotated,
                    "automatic_annotations": automatic, "reviewed_annotations": reviewed,
                    "plain_kana": len(rows) - annotated, "reasons": dict(sorted(reasons.items()))},
        "entries": entries,
    }
    return output.getvalue(), audit, notices


def apply_yomigana(files: dict[str, str], config: dict[str, Any]) -> dict[str, str]:
    result = dict(files)
    vocabulary, audit, notices = enrich_vocabulary(files["vocabulary.csv"], config)
    result["vocabulary.csv"] = vocabulary
    # Compact per-ID records; no raw N-best analyses are distributed.
    result["_audit/yomigana.json"] = json.dumps(audit, ensure_ascii=False, separators=(",", ":")) + "\n"
    for name, content in notices.items():
        result[f"_audit/unidic/{name}"] = content
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", type=Path, default=ROOT / "contenu csv/consolidated/vocabulary.csv")
    parser.add_argument("--config", type=Path, default=CONFIG_FILE)
    parser.add_argument("--write", action="store_true", help="Add the column only to the fingerprint-verified vocabulary and write its audit/notices.")
    args = parser.parse_args()
    original = args.input_csv.read_text(encoding="utf-8")
    result = apply_yomigana({"vocabulary.csv": original}, json.loads(args.config.read_text(encoding="utf-8")))
    print(json.dumps(json.loads(result["_audit/yomigana.json"])["summary"], ensure_ascii=False, indent=2))
    if args.write:
        if args.input_csv.read_text(encoding="utf-8") != original:
            raise ValueError("Vocabulary changed during preparation")
        # This explicit bulk transformation changes only one column and its audit.
        for name, content in result.items():
            destination = args.input_csv if name == "vocabulary.csv" else args.input_csv.parent / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8", newline="")


if __name__ == "__main__":
    main()
