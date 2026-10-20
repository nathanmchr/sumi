"""Check every dataset row against its source and independent UniDic readings.

Dictionary agreement is evidence, not a manual linguistic certification.
"""

import argparse
from collections import Counter
import csv
import gzip
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import fugashi

from app.utils.furigana import KANJI_RE, hiragana, reading_variants, validate_furigana
from scripts.prepare_vocab_furigana import load_reference, reference_segments


ROOT = Path(__file__).resolve().parents[2]


def dictionary_entries(path: Path, wanted: set[str]) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {}
    with gzip.open(path, "rb") as handle:
        for _, entry in ET.iterparse(handle, events=("end",)):
            if entry.tag != "entry":
                continue
            for spelling in entry.findall("k_ele"):
                word = spelling.findtext("keb")
                if word not in wanted:
                    continue
                for reading in entry.findall("r_ele"):
                    restrictions = {value.text for value in reading.findall("re_restr")}
                    if reading.find("re_nokanji") is not None or (restrictions and word not in restrictions):
                        continue
                    tags = [value.text for value in spelling.findall("ke_inf") + reading.findall("re_inf")]
                    found.setdefault(word, []).append({"reading": hiragana(reading.findtext("reb")), "id": entry.findtext("ent_seq"), "tags": tags})
            entry.clear()
    return found


def kanji_readings(path: Path) -> dict[str, set[str]]:
    found = {}
    with gzip.open(path, "rb") as handle:
        for _, entry in ET.iterparse(handle, events=("end",)):
            if entry.tag != "character":
                continue
            found[entry.findtext("literal")] = {
                hiragana(value.text.strip("-")) for value in entry.findall(".//reading")
                if value.get("r_type") in {"ja_on", "ja_kun"} and "." not in value.text
            }
            entry.clear()
    return found


def audit(jmdict_path: Path, kanjidic_path: Path, reference_path: Path) -> None:
    tagger = fugashi.Tagger()
    rows = []
    counts = Counter()
    wanted = set()
    for path in (ROOT / "contenu csv").glob("* Vocab.csv"):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            wanted.update((row["Kanji"] or row["Hiragana"]).strip() for row in csv.DictReader(handle, delimiter=";"))
    jmdict = dictionary_entries(jmdict_path, wanted)
    kanjidic = kanji_readings(kanjidic_path)
    reference = load_reference(reference_path)
    manual = {(row["japanese"], row["reading"]): row for row in json.loads((ROOT / "docs" / "vocabulary-furigana-manual-review.json").read_text(encoding="utf-8"))}
    for path in sorted((ROOT / "contenu csv").glob("* Vocab.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for line, row in enumerate(csv.DictReader(handle, delimiter=";"), start=2):
                surface = (row["Kanji"] or row["Hiragana"]).strip()
                reading = row["Hiragana"].strip()
                parts = validate_furigana(surface, reading, json.loads(row["Furigana"]))
                lexical_parts = reference_segments(surface, reading, reference)
                annotated = any(part.get("reading") for part in parts)
                if annotated and lexical_parts is not None and parts != lexical_parts:
                    raise ValueError(f"{path.name}:{line}: segmentation differs from the lexical reference")
                segmentation_check = "lexical_match" if annotated and lexical_parts == parts else "conservative_fallback" if annotated else "no_ruby"
                readings = []
                for nodes in tagger.nbestToNodeList(surface, 32):
                    if any(node.is_unk or not node.feature.kana or node.feature.kana == "*" for node in nodes):
                        continue
                    value = hiragana("".join(node.feature.kana for node in nodes))
                    if value not in readings:
                        readings.append(value)
                expected = set(reading_variants(reading))
                matches = jmdict.get(surface, [])
                accepted = {value["reading"] for value in matches if not any("search-only" in tag or "irregular kana" in tag for tag in value["tags"])}
                search_only = {value["reading"] for value in matches} - accepted
                decision = manual.get((surface, reading), {})
                if not any(part.get("reading") for part in parts):
                    status = "review_unannotated" if KANJI_RE.search(surface) else "no_ruby_needed"
                elif decision.get("decision") == "confirmed":
                    status = "manual_reference_match"
                elif decision.get("decision") == "withheld":
                    status = "review_source_error"
                elif expected <= accepted:
                    status = "jmdict_match"
                elif expected & search_only:
                    status = "review_nonstandard_form"
                elif expected <= kanjidic.get(surface, set()):
                    status = "kanjidic_match"
                elif expected <= set(readings):
                    status = "unidic_match"
                else:
                    status = "review_unconfirmed"
                counts[status] += 1
                rows.append({
                    "file": path.name, "line": line, "japanese": surface,
                    "reading": reading, "furigana": row["Furigana"], "status": status,
                    "dictionary_readings": " / ".join(readings[:8]),
                    "unconfirmed_readings": " / ".join(sorted(expected - set(readings))),
                    "jmdict_evidence": json.dumps(matches, ensure_ascii=False, separators=(",", ":")),
                    "kanjidic_readings": " / ".join(sorted(kanjidic.get(surface, set()))),
                    "manual_source": decision.get("source", ""),
                    "manual_note": decision.get("note", ""),
                    "segmentation_check": segmentation_check,
                })
    output = ROOT / "docs" / "vocabulary-furigana-audit.csv"
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Audited {len(rows)} rows: {dict(counts)}")
    print(f"Dictionary: {tagger.dictionary_info}")
    print(f"Report: {output}")
    metadata = {
        "method": "Structural validation of every row, 32 UniDic analyses, exact JMdict spelling/reading restrictions and KANJIDIC2 for isolated kanji. Not a manual linguistic certification.",
        "counts": dict(counts), "unidic": tagger.dictionary_info,
        "references": [
            {"url": "https://www.edrdg.org/pub/Nihongo/JMdict_e.gz", "sha256": hashlib.sha256(jmdict_path.read_bytes()).hexdigest()},
            {"url": "https://www.edrdg.org/kanjidic/kanjidic2.xml.gz", "sha256": hashlib.sha256(kanjidic_path.read_bytes()).hexdigest()},
            {"url": "https://github.com/Doublevil/JmdictFurigana/releases/tag/2.3.1%2B2026-08-25", "sha256": hashlib.sha256(reference_path.read_bytes()).hexdigest()},
        ],
        "dataset_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((ROOT / "contenu csv").glob("* Vocab.csv"))},
    }
    output.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jmdict", type=Path, required=True)
    parser.add_argument("--kanjidic", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    args = parser.parse_args()
    audit(args.jmdict, args.kanjidic, args.reference)
