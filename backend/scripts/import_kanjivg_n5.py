"""Build local JLPT stroke assets from a pinned KanjiVG source archive."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
REVISION = "55b5ba92a7cad78a62ef04db4be6f9562d949b7f"
SOURCE_ROOT = f"kanjivg-{REVISION}"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/3.0/"
SVG = "{http://www.w3.org/2000/svg}"
NUMBER = r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?"


def level_characters(csv_path: Path) -> list[str]:
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        characters = [row["Kanji"].strip() for row in csv.DictReader(handle, delimiter=";")]
    if not characters or len(set(characters)) != len(characters):
        raise ValueError("Empty or duplicate JLPT characters")
    if any(len(character) != 1 for character in characters):
        raise ValueError("Each JLPT entry must contain one character")
    return characters


n5_characters = level_characters


def parse_svg(raw: bytes, character: str) -> dict:
    if len(raw) > 100_000 or b"<!ENTITY" in raw.upper():
        raise ValueError("Unexpected SVG size or entity declaration")
    root = ET.fromstring(raw)
    code = f"{ord(character):05x}"
    if root.tag != f"{SVG}svg" or root.get("viewBox") != "0 0 109 109":
        raise ValueError("Unexpected coordinate system")
    for element in root.iter():
        if element.tag not in {f"{SVG}{name}" for name in ("svg", "g", "path", "text")}:
            raise ValueError("Unexpected SVG element")
        for key, value in element.attrib.items():
            local_key = key.rsplit("}", 1)[-1].lower()
            if local_key.startswith("on") or local_key == "href" or "url(" in value.lower():
                raise ValueError("External or executable SVG attribute")
    paths_group = root.find(f"{SVG}g[@id='kvg:StrokePaths_{code}']")
    numbers_group = root.find(f"{SVG}g[@id='kvg:StrokeNumbers_{code}']")
    if paths_group is None or numbers_group is None:
        raise ValueError("Stroke paths/numbers missing")
    identity = paths_group.find(f"{SVG}g[@id='kvg:{code}']")
    if identity is None or character not in [v for k, v in identity.attrib.items() if k.endswith("}element")]:
        raise ValueError("Character identity mismatch")
    if any("transform" in element.attrib for element in paths_group.iter()):
        raise ValueError("Transformed paths need an explicit coordinate conversion")
    paths = list(paths_group.iter(f"{SVG}path"))
    labels = list(numbers_group.iter(f"{SVG}text"))
    if not 1 <= len(paths) <= 40 or len(paths) != len(labels):
        raise ValueError("Invalid stroke/number count")
    strokes = []
    for index, (path, label) in enumerate(zip(paths, labels), 1):
        if path.get("id") != f"kvg:{code}-s{index}" or label.text != str(index):
            raise ValueError("Non-sequential stroke order")
        d = path.get("d", "")
        if not re.fullmatch(r"[Mm][\s,0-9.eE+\-MmZzLlHhVvCcSsQqTtAa]+", d):
            raise ValueError("Invalid stroke path")
        transform = label.get("transform", "")
        if not re.fullmatch(rf"matrix\(\s*{NUMBER}(?:[\s,]+{NUMBER}){{5}}\s*\)", transform):
            raise ValueError("Unexpected number transform")
        matrix = [float(value) for value in re.findall(NUMBER, transform)]
        if not all(math.isfinite(value) for value in matrix):
            raise ValueError("Non-finite number transform")
        strokes.append({"path": d, "number_transform": matrix})
    return {
        "character": character, "view_box": [0, 0, 109, 109], "strokes": strokes,
        "source": f"https://github.com/KanjiVG/kanjivg/blob/{REVISION}/kanji/{code}.svg",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "license": LICENSE_URL,
    }


def build_assets(archive: Path, csv_path: Path, level: str = "N5") -> dict[str, bytes]:
    if level not in {"N1", "N2", "N3", "N4", "N5"}:
        raise ValueError("Unsupported JLPT level")
    assets: dict[str, bytes] = {}
    manifest = {"revision": REVISION, "license": LICENSE_URL, "characters": {}}
    with ZipFile(archive) as source:
        for character in level_characters(csv_path):
            code = f"{ord(character):05x}"
            raw = source.read(f"{SOURCE_ROOT}/kanji/{code}.svg")
            data = parse_svg(raw, character)
            assets[f"source/{code}.svg"] = raw
            assets[f"{level.lower()}/{code}.json"] = (json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
            manifest["characters"][character] = {
                "file": f"{level.lower()}/{code}.json", "strokes": len(data["strokes"]),
                "source_sha256": data["source_sha256"],
            }
        assets["COPYING.txt"] = source.read(f"{SOURCE_ROOT}/COPYING")
    assets["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    return assets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--level", choices=("N1", "N2", "N3", "N4", "N5"), required=True)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "frontend/public/kanji-strokes")
    args = parser.parse_args()
    csv_path = args.csv or ROOT / f"contenu csv/JLPT {args.level} Kanji.csv"
    # Validate the entire set before changing any published asset.
    assets = build_assets(args.archive, csv_path, args.level)
    manifest_path = args.output / "manifest.json"
    current_manifest = json.loads(assets["manifest.json"])
    if manifest_path.exists():
        merged_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        merged_manifest = {"revision": REVISION, "license": LICENSE_URL, "levels": {}}
    levels = merged_manifest.setdefault("levels", {})
    if not levels and merged_manifest.get("characters"):
        levels["N5"] = merged_manifest["characters"]
    levels[args.level] = current_manifest["characters"]
    merged_manifest["revision"] = REVISION
    merged_manifest["license"] = LICENSE_URL
    selected_characters = {}
    for level in ("N5", "N4", "N3", "N2", "N1"):
        for character, entry in levels.get(level, {}).items():
            selected_characters.setdefault(character, entry)
    merged_manifest["characters"] = selected_characters
    assets["manifest.json"] = (json.dumps(merged_manifest, ensure_ascii=False, indent=2) + "\n").encode()
    changed = 0
    for name, content in assets.items():
        target = args.output / name
        if target.exists() and target.read_bytes() == content:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        changed += 1
    print(f"Validated {(len(assets) - 2) // 2} {args.level} kanji; {changed} assets updated.")


if __name__ == "__main__":
    main()
