"""Prepare reviewed, order-preserving CSVs. Does not import or modify the database."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path
import re
from uuid import NAMESPACE_URL, uuid5

if __package__:
    from .catalog_corrections import apply_reviewed_corrections
    from .catalog_yomigana import CONFIG_FILE as YOMIGANA_CONFIG_FILE, apply_yomigana
    from .kanji_supplement import append_catalog, load_entries
else:
    from catalog_corrections import apply_reviewed_corrections
    from catalog_yomigana import CONFIG_FILE as YOMIGANA_CONFIG_FILE, apply_yomigana
    from kanji_supplement import append_catalog, load_entries


ROOT = Path(__file__).resolve().parents[2]
CORRECTIONS_FILE = ROOT / "backend/app/data/catalog_corrections.json"
LEVELS = ("N5", "N4", "N3", "N2", "N1")
CATEGORIES = {"vocabulary": "Vocab", "grammar": "Grammar", "kanji": "Kanji"}
HEADERS = {
    "vocabulary": ["Level", "KanjiLevel", "ID", "Kanji", "Kana", "Romaji", "Furigana", "English", "French", "Audio", "Notes"],
    "grammar": ["Level", "ID", "Kanji", "Kana", "Romaji", "English", "French"],
    "kanji": ["Level", "ID", "Kanji", "Pronunciation", "English", "French"],
}
HAN = re.compile(r"[\u3400-\u9fff々]")

# Audio sharing is weaker than lexical identity. Keep these for human review.
KEEP_SEPARATE = {
    ("たとえ", "simile,metaphor,allegory"): "Nom comparaison/métaphore face à une cible mêlant nom et conjonction.",
    ("かける", "to call by phone"): "Usage appeler au téléphone distinct de suspendre/accrocher dans les fiches sources.",
    ("する", "to do"): "Traductions de 為る divergentes entre anglais et français ; vérifier avant fusion.",
    ("せっけん", "economy"): "Anglais Economy contradictoire avec le français savon ; ne pas corriger implicitement.",
    ("しかる", "a particular"): "Anglais a particular contradictoire avec gronder ; ne pas corriger implicitement.",
    ("おかげ", "owing to"): "Construction grâce à face à un nom soutien/aide ; confirmer le regroupement pédagogique.",
    ("めでたい", "happy,simple soul,propitious,joyous"): "Graphie 愛でたい et étendue des sens à confirmer.",
}
# These two source rows put annotations in Hiragana; their explicit kana and
# Japanese/English/French meanings have been checked against the target rows.
EXTRA_EQUIVALENCES = {
    ("じゅうたん", "carpet"): "絨毯",
    ("だいいち", "first,foremost,# 1"): "第一",
}
SAME_SPELLING_VOCAB = {
    ("でも", "でも"): {"but", "but,however"},
    ("その", "その"): {"that", "the,that"},
    ("けれど/けれども", "けれど/けれども"): {"however", "but,however"},
    ("すると", "すると"): {"then", "thereupon,hereupon"},
}
SAME_USAGE_GRAMMAR = {
    ("が早いか", "がはやいか"): {"as soon as / no sooner than", "as soon as"},
    ("ながらも", "ながらも"): {"but;although;despite ~", "although / even while"},
    ("っぱなし", "っぱなし"): {"leaving (something) on;leaving (something) still in use", "left as is / continuously"},
}


def normalized(value: str) -> str:
    return re.sub(r"\s*([,;])\s*", r"\1", " ".join(value.casefold().split()))


def meaning_parts(value: str) -> list[str]:
    """Split only top-level lists, retaining punctuation within parentheses."""
    depth = 0
    start = 0
    parts = []
    for index, char in enumerate(value):
        if char in "([（":
            depth += 1
        elif char in ")]）":
            depth = max(0, depth - 1)
        elif char in ",;" and not depth:
            parts.append(value[start:index].strip())
            start = index + 1
    parts.append(value[start:].strip())
    return [part for part in parts if part]


def combine_meanings(values: list[str]) -> str:
    values = [value for value in values if value]
    if len(set(values)) <= 1:
        return values[0] if values else ""
    parts = {}
    for value in values:
        for part in meaning_parts(value):
            parts.setdefault(normalized(part), part)
    return "; ".join(parts.values())


@dataclass(frozen=True)
class Source:
    category: str
    file: str
    row: int
    order: int
    level: str
    raw: dict[str, str]

    @property
    def word(self) -> str:
        return self.raw.get("Kanji", "").strip() or self.kana

    @property
    def kana(self) -> str:
        written = self.raw.get("Kanji", "").strip()
        if self.category == "vocabulary" and written and not HAN.search(written):
            return written
        return self.raw.get("Hiragana", self.raw.get("Kana", "")).strip()

    @property
    def kanji(self) -> str:
        value = self.raw.get("Kanji", "").strip()
        return value if self.category != "vocabulary" or HAN.search(value) else ""


class Groups:
    def __init__(self, count: int):
        self.parents = list(range(count))

    def root(self, index: int) -> int:
        while self.parents[index] != index:
            self.parents[index] = self.parents[self.parents[index]]
            index = self.parents[index]
        return index

    def merge(self, first: int, second: int) -> None:
        a, b = sorted((self.root(first), self.root(second)))
        self.parents[b] = a  # The first source position always wins.


def read_sources(directory: Path, category: str) -> list[Source]:
    records = []
    for level in LEVELS:
        path = directory / f"JLPT {level} {CATEGORIES[category]}.csv"
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row, raw in enumerate(csv.DictReader(handle, delimiter=";"), 2):
                if None in raw or any(value is None for value in raw.values()):
                    raise ValueError(f"Malformed CSV: {path.name}:{row}")
                records.append(Source(category, path.name, row, len(records) + 1, level, raw))
    if not records:
        raise ValueError(f"No source rows for {category}")
    return records


def read_audio(path: Path) -> dict[tuple[str, str], str]:
    if not path.exists():
        return {}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return {
        (row["japanese"], row["reading"]): f"/audio/{path.parent.name}/{row['audio_file']}"
        for rows in manifest.values() for row in rows
        if row.get("audio_file")
    }


def source_audio(source: Source, audio: dict[tuple[str, str], str]) -> str:
    reading = source.raw.get("Hiragana", "").strip() or source.kana
    return audio.get((source.word, reading), "")


def group_sources(records: list[Source], aliases: dict[tuple[str, str], str]):
    groups = Groups(len(records))
    exact = {}
    spellings = {}
    issues = []
    for index, source in enumerate(records):
        spelling = (source.word, source.kana)
        identity = (*spelling, normalized(source.raw.get("English", "")),
                    normalized(source.raw.get("French", "")) if not source.raw.get("English") else "")
        if identity in exact:
            groups.merge(exact[identity], index)
        else:
            exact[identity] = index
        spellings.setdefault(spelling, []).append(index)

    category = records[0].category
    approved = SAME_SPELLING_VOCAB if category == "vocabulary" else SAME_USAGE_GRAMMAR if category == "grammar" else {}
    for spelling, meanings in approved.items():
        indices = [i for i in spellings.get(spelling, []) if normalized(records[i].raw.get("English", "")) in meanings]
        for index in indices[1:]:
            groups.merge(indices[0], index)

    if category == "vocabulary":
        for index, source in enumerate(records):
            if source.kanji:
                continue
            key = (source.kana, source.raw.get("English", "").strip().casefold())
            target = aliases.get(key)
            if not target:
                continue
            if key in KEEP_SEPARATE:
                issues.append(("fusion suspendue", [index], KEEP_SEPARATE[key]))
                continue
            candidates = spellings.get((target, source.kana), [])
            if len({groups.root(i) for i in candidates}) != 1:
                issues.append(("cible absente ou ambiguë", [index], f"Cible proposée : {target}"))
                continue
            groups.merge(index, candidates[0])

    # Shared spelling is not a uniqueness constraint for senses or grammar uses.
    for spelling, indices in spellings.items():
        if len({groups.root(i) for i in indices}) > 1:
            issues.append(("sens/usages conservés séparément", indices, f"Forme : {spelling[0]} ; lecture : {spelling[1]}"))

    # Do not collapse alternative kanji just because their English gloss matches.
    if category == "vocabulary":
        candidates = {}
        for index, source in enumerate(records):
            if source.kanji:
                candidates.setdefault((source.kana, normalized(source.raw.get("English", ""))), []).append(index)
        for (reading, meaning), indices in candidates.items():
            if meaning and len({records[i].kanji for i in indices}) > 1:
                issues.append(("graphies kanji à examiner", indices, f"Même lecture et anglais : {reading} ; {meaning}"))

    grouped = {}
    for index in range(len(records)):
        grouped.setdefault(groups.root(index), []).append(index)
    return list(grouped.values()), issues


def canonical_row(records: list[Source], indices: list[int], audio: dict[tuple[str, str], str]) -> dict[str, str]:
    sources = [records[index] for index in indices]
    first = sources[0]
    written = [source for source in sources if source.kanji]
    preferred = written[0] if written else first
    identity = json.dumps([first.category, first.raw.get("Kanji", ""), first.kana,
                           normalized(first.raw.get("English", "")),
                           normalized(first.raw.get("French", "")) if not first.raw.get("English") else ""], ensure_ascii=False)
    row = {
        "Level": first.level,
        "ID": str(uuid5(NAMESPACE_URL, "mirai-path:catalog:" + identity)),
        "Kanji": preferred.kanji,
        "Kana": preferred.kana,
        "Romaji": preferred.raw.get("Romaji", ""),
        "English": combine_meanings([source.raw.get("English", "") for source in [preferred, *sources]]),
        "French": combine_meanings([source.raw.get("French", "") for source in [preferred, *sources]]),
    }
    if first.category == "vocabulary":
        notes = []
        for source in sources:
            if source.kana != source.raw.get("Hiragana", ""):
                notes.append(f"Annotation source Hiragana : {source.raw.get('Hiragana', '')}")
        row.update({
            "KanjiLevel": written[0].level if written else "",
            "Furigana": preferred.raw.get("Furigana", ""),
            "Audio": source_audio(preferred, audio) or next((source_audio(s, audio) for s in sources if source_audio(s, audio)), ""),
            "Notes": " ; ".join(dict.fromkeys(notes)),
        })
    elif first.category == "kanji":
        row["Pronunciation"] = preferred.raw.get("pronunciation", preferred.raw.get("Pronounciation", ""))
    return {header: row[header] for header in HEADERS[first.category]}


def csv_text(rows: list[dict], headers: list[str]) -> str:
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=headers, delimiter=";", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue()


def build_catalog(directory: Path, audio_manifest: Path, alias_file: Path, *, reviewed: bool = True,
                  include_yomigana: bool = True):
    fingerprints = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in directory.glob("JLPT * *.csv")}
    with alias_file.open(encoding="utf-8", newline="") as handle:
        aliases = {(row["kana"], row["translation_en"].strip().casefold()): row["audio_kanji"]
                   for row in csv.DictReader(handle, delimiter=";")}
    aliases.update(EXTRA_EQUIVALENCES)
    audio = read_audio(audio_manifest)
    files = {}
    summary = {}
    provenance = []
    reviews = []
    merges = []
    for category in CATEGORIES:
        records = read_sources(directory, category)
        grouped, issues = group_sources(records, aliases)
        rows = []
        source_to_output = {}
        for position, indices in enumerate(grouped, 1):
            row = canonical_row(records, indices, audio)
            rows.append(row)
            for index in indices:
                source_to_output[index] = (position, row["ID"])
            if len(indices) > 1:
                merges.append({"Category": category, "ID": row["ID"], "Position": position,
                               "Word": row["Kanji"] or row.get("Kana", ""), "Level": row["Level"],
                               "KanjiLevel": row.get("KanjiLevel", ""),
                               "Sources": " | ".join(f"{records[i].file}:{records[i].row}" for i in indices)})
        # Validate losslessness of meaning, coverage, ordering and renderable furigana.
        assert len(source_to_output) == len(records)
        assert [indices[0] for indices in grouped] == sorted(indices[0] for indices in grouped)
        assert len({row["ID"] for row in rows}) == len(rows)
        for index, source in enumerate(records):
            position, identity = source_to_output[index]
            canonical = rows[position - 1]
            for language in ("English", "French"):
                expected = {normalized(part) for part in meaning_parts(source.raw.get(language, ""))}
                actual = {normalized(part) for part in meaning_parts(canonical[language])}
                assert expected <= actual, (source.file, source.row, language)
            provenance.append({"Category": category, "SourceFile": source.file, "SourceRow": source.row,
                               "SourceOrder": source.order, "CanonicalID": identity, "CanonicalOrder": position,
                               "OriginalRow": json.dumps(source.raw, ensure_ascii=False, separators=(",", ":"))})
            if not source.raw.get("English") or not source.raw.get("French"):
                issues.append(("traduction source manquante", [index], "Champ vide conservé ; aucune traduction inventée."))
            if category == "vocabulary" and source.kana != source.raw.get("Hiragana", ""):
                issues.append(("annotation déplacée dans Notes", [index], "Kana reprend la graphie kana explicite ; ancienne valeur conservée."))
        if category == "vocabulary":
            for row in rows:
                segments = json.loads(row["Furigana"])
                assert "".join(segment["surface"] for segment in segments) == (row["Kanji"] or row["Kana"]), row["ID"]
                assert bool(row["Kanji"]) == bool(row["KanjiLevel"])
                if row["KanjiLevel"]:
                    assert LEVELS.index(row["Level"]) <= LEVELS.index(row["KanjiLevel"])
        for status, indices, reason in issues:
            reviews.append({"Category": category, "Status": status, "Reason": reason,
                            "Sources": " | ".join(f"{records[i].file}:{records[i].row}" for i in indices),
                            "Forms": " | ".join(records[i].word for i in indices),
                            "English": " | ".join(records[i].raw.get("English", "") for i in indices),
                            "French": " | ".join(records[i].raw.get("French", "") for i in indices)})
        files[f"{category}.csv"] = csv_text(rows, HEADERS[category])
        summary[category] = {"source_rows": len(records), "rows": len(rows), "absorbed_rows": len(records) - len(rows),
                             "merge_groups": sum(len(indices) > 1 for indices in grouped)}
    files["_audit/source-map.csv"] = csv_text(provenance, ["Category", "SourceFile", "SourceRow", "SourceOrder", "CanonicalID", "CanonicalOrder", "OriginalRow"])
    files["_audit/merges.csv"] = csv_text(merges, ["Category", "ID", "Position", "Word", "Level", "KanjiLevel", "Sources"])
    files["_audit/review.csv"] = csv_text(reviews, ["Category", "Status", "Reason", "Sources", "Forms", "English", "French"])
    current_fingerprints = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in directory.glob("JLPT * *.csv")}
    if fingerprints != current_fingerprints:
        raise ValueError("Source CSVs changed during preparation; review and retry.")
    files["_audit/sources.sha256.json"] = json.dumps(fingerprints, ensure_ascii=False, indent=2) + "\n"
    if reviewed:
        recipe = json.loads(CORRECTIONS_FILE.read_text(encoding="utf-8"))
        files, summary, _ = apply_reviewed_corrections(files, recipe)
    yomigana_summary = None
    if reviewed and include_yomigana:
        config = json.loads(YOMIGANA_CONFIG_FILE.read_text(encoding="utf-8"))
        files = apply_yomigana(files, config)
        yomigana_summary = json.loads(files["_audit/yomigana.json"])["summary"]
    files["README.md"] = report(summary, len(reviews), yomigana_summary=yomigana_summary)
    return files, summary


def report(summary: dict, reviews: int, *, yomigana_summary: dict | None = None) -> str:
    counts = "\n".join(f"| {category} | {s['source_rows']} | {s['rows']} | {s['absorbed_rows']} |" for category, s in summary.items())
    vocabulary_columns = "Kana, Yomigana, Romaji" if yomigana_summary else "Kana, Romaji"
    yomigana_section = ""
    if yomigana_summary:
        yomigana_section = f"""
## Yomigana — 8 septembre 2026

La colonne Yomigana, après Kana, est directement utilisable par le générateur Google.
Elle contient {yomigana_summary['dictionary_annotations']} annotations d’accent provenant
de correspondances strictes UniDic et {yomigana_summary['plain_kana']} lectures sans accent
imposé. Ces dernières ne sont pas des accents plats : un accent plat connu porte ^,
par exemple ^ねいろ ; une lecture sans accent renseigné ne porte ni ^ ni !.

`_audit/yomigana.json` conserve les décisions par ID, les motifs de repli, la version
du dictionnaire et les empreintes avant/après. Les notices UniDic sont conservées dans
`_audit/unidic/BSD` et `AUTHORS`. Ces annotations de dictionnaire ne constituent ni une
validation humaine de tous les sens, ni une validation des audios à l’écoute.

Seule cette colonne est ajoutée ; toutes les anciennes valeurs, les ID, les niveaux et
l’ordre restent identiques. Aucun audio ni manifeste audio n’a été généré, remplacé ou
raccordé au site. La reproduction par `backend/scripts/consolidate_content_csv.py`
inclut cette étape après les corrections ; le dictionnaire local épinglé est requis.
Les contrôles des corrections précédentes restent historiques ; les tests
`test_catalog_yomigana.py` et `test_generate_vocab_audio_google.py` couvrent cette étape.
"""
    return f"""# Catalogue consolidé corrigé — migration à valider

L’application utilise encore les quinze CSV d’origine. Aucune base, progression,
configuration d’import ou ressource audio n’a été modifiée.

| Catégorie | Lignes source | Entrées consolidées | Occurrences absorbées |
|---|---:|---:|---:|
{counts}

## Colonnes et niveaux

- Vocabulaire : Level, KanjiLevel, ID, Kanji, {vocabulary_columns}, Furigana, English, French, Audio, Notes.
- Grammaire : Level, ID, Kanji, Kana, Romaji, English, French.
- Kanji : Level, ID, Kanji, Pronunciation, English, French.

Level est le premier niveau d’introduction. KanjiLevel est le premier niveau de
la graphie kanji du mot, pas celui des caractères pris séparément. Si le mot est
introduit directement en kanji, les deux niveaux sont identiques. Sans graphie
kanji associée, KanjiLevel reste vide. Il n’y a pas de KanaLevel.

## Ordre préservé

Les fichiers sont parcourus N5 → N4 → N3 → N2 → N1, dans leur ordre de lignes
d’origine. Chaque entrée fusionnée reste à la place de sa première occurrence.
Seules les occurrences ultérieures absorbées disparaissent. Aucun tri
alphabétique, par graphie ou par ID n’est effectué.

## Fusions prudentes

Les variantes kana/kanji examinées sont regroupées sauf lorsque leurs sens,
usages ou traductions sont incertains. Des mots partageant une lecture ne sont
jamais fusionnés sur ce seul critère. Les graphies kanji différentes ne sont pas
automatiquement fusionnées, même avec un anglais identique : ce critère confond
notamment des termes comme 保証 et 保障.

En grammaire, les répétitions équivalentes de が早いか, ながらも,
っぱなし, 割に et だけまし sont regroupées. Les différents usages de そうだ, のに, でも, ばかり,
だけ, にする, こと, も et と restent distincts avec leurs niveaux respectifs.

Les sens valides sont conservés ; les erreurs certaines de lecture et de
traduction sont corrigées suivant le manifeste explicite
`backend/app/data/catalog_corrections.json`. Treize anglais vides, trois erreurs
de tableur et une note de travail ont été remplacés par leurs définitions.
Les furigana et l’audio sont alignés sur les corrections vérifiées.
Les annotations présentes à la place d’une lecture sont conservées dans Notes,
et la graphie kana explicite est utilisée comme Kana. Aucun nouvel audio n’est généré.
Trois références audio incorrectes (音色, 愛憎, 一筋) restent vides et sont
signalées dans Notes et dans le journal : les anciens WAV sont conservés,
mais ne doivent plus accompagner les lectures corrigées. Les autres références
existent ; lorsqu’un enregistrement approprié était disponible, il a été réutilisé.

## Contrôles et traçabilité

- `_audit/source-map.csv` relie chaque ligne d’origine à l’ID et à la position de
  sa destination ; OriginalRow conserve toutes ses colonnes d’origine et
  OriginalCanonicalID conserve l’ID de la première consolidation.
- `_audit/merges.csv` détaille chaque groupe fusionné.
- `_audit/review.csv` conserve les {reviews} signalements du premier audit :
  ce n’est plus une liste d’erreurs toutes ouvertes. Consulter le journal des corrections.
- `_audit/corrections.json` conserve les valeurs avant/après, les ID absorbés
  et leurs destinations, les références, les audios à régénérer et les cas non tranchés.
- `_audit/sources.sha256.json` permet de vérifier que les quinze sources n’ont
  pas changé pendant ou après la préparation.

Les IDs sont reproductibles pour cette préparation, puis doivent être conservés
lors des corrections éditoriales. L’import futur devra utiliser cette colonne,
sans recalculer l’identité depuis une graphie ou une traduction modifiée.

Validation attendue avant migration de l’application et de la progression.
Les fichiers anciens et les rapports de transition restent conservés jusque-là.

## Validation des corrections — 6 septembre 2026

Les modifications validées portent sur 61 fiches avant regroupement, puis
19 occurrences de vocabulaire et 2 de grammaire sont absorbées dans leurs
premières occurrences. Aucun ID survivant n’est recalculé. Pour お祖父さん,
Level reste N5 mais KanjiLevel devient N1 : seule la graphie correcte attestée
est utilisée, pas l’ancienne graphie d’oncle erronée.

`_audit/quality-report.html`, `quality-artifact.json`, `quality-results.json` et
`quality-checks.ipynb` décrivent l’état historique AVANT ces corrections.
Le contrôle de cette étape est `_audit/correction-checks.ipynb`, avec ses sorties exécutées.
Les variantes anciennes de 復旧 et 真実, l’entrée mal identifiée 伊井,
les autres cas éditoriaux non confirmés et les paires nom / nom + する
restent inchangés. Les lectures rares attestées, comme 何々[どれどれ], sont préservées.
{yomigana_section}
""".rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=ROOT / "contenu csv")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "contenu csv" / "consolidated")
    parser.add_argument("--audio-manifest", type=Path, default=ROOT / "audio" / "vocabulary" / "manifest.json")
    parser.add_argument("--aliases", type=Path, default=ROOT / "backend" / "app" / "data" / "vocabulary_audio_aliases.csv")
    parser.add_argument("--write", action="store_true", help="Write a new proposal; never overwrite an existing directory.")
    args = parser.parse_args()
    files, summary = build_catalog(args.input_dir, args.audio_manifest, args.aliases)
    files["kanji.csv"], added = append_catalog(files["kanji.csv"], load_entries())
    summary["kanji"]["rows"] += added
    summary["kanji"]["supplement_rows"] = added
    files["README.md"] += "\n## Supplement kanji\n\n323 fiches EN/FR KANJIDIC2 ajoutees en fin de catalogue (total 2534).\nVoir backend/app/data/kanji_supplement.json et docs/kanji-supplement.md pour les sources et licences.\n"
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.write:
        print("Preview only: no files or database changes.")
        return
    # Refuse to replace either source files or a proposal already being edited.
    args.output_dir.mkdir(parents=True, exist_ok=False)
    for name, content in files.items():
        path = args.output_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")
    print(f"Proposal: {args.output_dir}")


if __name__ == "__main__":
    main()
