"""Import the reviewed catalogue without guessing identities or resetting learning.

Application primary keys are stable surrogate keys. ``catalog_id`` is the unique
editorial identity; provenance is used only to reconcile the first legacy import.
The caller owns the transaction and must provide backup/rollback around writes.
"""
from collections import defaultdict
import csv
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import unicodedata
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, selectinload

from app.models.content import (
    ContentAlias, ExampleSentence, GrammarItem, GrammarTranslation, KanjiItem,
    KanjiTranslation, VocabularyItem, VocabularyKanjiLink, VocabularyTranslation,
)
from app.models.learning import GrammarExercise, LearningState, ReviewHistory, StudyQuestion, StudySession
from app.services.catalog_audio import CATALOG_DIR, canonical_row_audio, catalog_entry
from app.services.content_identity import MODELS
from app.utils.furigana import build_furigana, validate_furigana
from app.utils.romaji import romaji_search_key

LEVELS = {"N5", "N4", "N3", "N2", "N1"}
TRANSLATIONS = {
    "vocabulary": (VocabularyTranslation, "vocabulary_item_id", "translation"),
    "grammar": (GrammarTranslation, "grammar_item_id", "explanation"),
    "kanji": (KanjiTranslation, "kanji_item_id", "meanings"),
}
# Exact, reviewed historical title formats; never match by kana alone.
GRAMMAR_LEGACY = {
    ("～や否や（いなや）", "やいなや", "the instant / as soon as"):
        ("c06f36a1-ce9a-579a-b378-017421c1fe1e", "や否や", "やいなや"),
    ("中（ちゅう）", "chuu / juu", "currently; during; at some point; throughout; before the end of ~"):
        ("c147dcbe-23f9-5811-ab2e-253cd32011db", "中", "ちゅう / じゅう"),
    ("～割りに（は）", "わりに（は）", "despite / although"):
        ("c24e08f9-8b38-57de-89dc-60ec0f6bcdb8", "割に / 割りに / 割りには", "わりに / わりには"),
}


def grammar_key(value: str) -> str:
    return re.sub(r"[\s~〜～]", "", unicodedata.normalize("NFKC", value)).casefold()


def grammar_title(row: dict) -> str:
    return f"{row['Kanji']}（{row['Kana']}）" if row["Kanji"] else row["Kana"]


@dataclass
class Catalog:
    rows: dict[str, list[dict]]
    grammar_index: dict[tuple, set[str]]
    grammar_readings: dict[str, set[str]] = field(default_factory=dict)


def load_catalog(directory: Path = CATALOG_DIR) -> Catalog:
    rows = {}
    for kind in MODELS:
        with (directory / f"{kind}.csv").open(encoding="utf-8-sig", newline="") as handle:
            rows[kind] = list(csv.DictReader(handle, delimiter=";"))
        ids = set()
        for row in rows[kind]:
            identity = str(UUID(row["ID"]))
            if identity != row["ID"] or identity in ids or row["Level"] not in LEVELS:
                raise ValueError(f"Invalid/duplicate catalogue identity: {kind} {identity}")
            if not row["English"] or not row["French"] or not (row["Kanji"] or row.get("Kana")):
                raise ValueError(f"Incomplete catalogue row: {identity}")
            if kind == "vocabulary" and (not row["Kana"] or row["KanjiLevel"] not in LEVELS | {""}):
                raise ValueError(f"Invalid vocabulary reading/level: {identity}")
            ids.add(identity)
        if not rows[kind]:
            raise ValueError(f"Empty catalogue: {kind}")
    index = defaultdict(set)
    readings = defaultdict(set)
    grammar_ids = {r["ID"] for r in rows["grammar"]}

    def add(row, identity):
        if identity not in grammar_ids:
            raise ValueError("Unknown grammar provenance identity")
        for title in {row["Kanji"] or row["Kana"], grammar_title(row)}:
            index[(grammar_key(title), grammar_key(row["English"]))].add(identity)
        readings[identity].update(grammar_key(row[key]) for key in ("Romaji", "Kana") if row[key])

    for row in rows["grammar"]:
        add(row, row["ID"])
    with (directory / "_audit" / "source-map.csv").open(encoding="utf-8-sig", newline="") as handle:
        for source in csv.DictReader(handle, delimiter=";"):
            if source["Category"] == "grammar":
                add(json.loads(source["OriginalRow"]), source["CanonicalID"])
    for (_, legacy_reading, _), (identity, _, _) in GRAMMAR_LEGACY.items():
        readings[identity].add(grammar_key(legacy_reading))
    return Catalog(rows, dict(index), dict(readings))


@dataclass
class CatalogPlan:
    catalog: Catalog
    groups: dict[str, dict[str, list]]
    targets: dict[str, dict[str, str]]
    remap: dict[str, dict[str, str]]
    summary: dict


def build_plan(db: Session, catalog: Catalog | None = None) -> CatalogPlan:
    catalog = catalog or load_catalog()
    groups, targets, remap, summary = {}, {}, {}, {}
    learned = {(s.content_type.value, s.content_id) for s in db.scalars(select(LearningState))}
    for kind, model in MODELS.items():
        source = {r["ID"]: r for r in catalog.rows[kind]}
        by_character = {r["Kanji"]: r["ID"] for r in catalog.rows[kind]} if kind == "kanji" else {}
        groups[kind] = {identity: [] for identity in source}
        current = list(db.scalars(select(model).options(selectinload(model.translations))))
        for item in current:
            identity = item.catalog_id
            if not identity and item.id in source:
                identity = item.id
            if not identity and kind == "vocabulary":
                row = catalog_entry(item)
                identity = row["ID"] if row else None
            elif not identity and kind == "kanji":
                identity = by_character.get(item.character)
            elif not identity and kind == "grammar":
                candidates = catalog.grammar_index.get((grammar_key(item.title), grammar_key(item.explanation)), set())
                if len(candidates) == 1:
                    identity = next(iter(candidates))
                elif not candidates and (reviewed := GRAMMAR_LEGACY.get((item.title, item.structure, item.explanation))):
                    identity, written, reading = reviewed
                    if source.get(identity, {}).get("Kanji") != written or source[identity]["Kana"] != reading:
                        raise ValueError("Stale reviewed grammar correspondence")
            if identity not in source:
                raise ValueError(f"Unmapped or ambiguous {kind}: {item.id}")
            groups[kind][identity].append(item)
        targets[kind], remap[kind] = {}, {}
        for identity, items in groups[kind].items():
            # Preserve an already associated record, then a studied legacy record.
            items.sort(key=lambda item: (item.catalog_id != identity,
                                        (kind, item.id) not in learned,
                                        -int(item.jlpt_level_code[1]), item.id))
            target = items[0].id if items else identity
            targets[kind][identity] = target
            remap[kind].update({item.id: target for item in items if item.id != target})
        summary[kind] = {"before": len(current), "after": len(source),
                         "created": sum(not items for items in groups[kind].values()),
                         "absorbed": len(remap[kind])}
    seen = set()
    for state in db.scalars(select(LearningState)):
        kind = state.content_type.value
        key = (state.user_id, kind, remap[kind].get(state.content_id, state.content_id))
        if key in seen:
            raise ValueError("Conflicting learning states: manual FSRS review required; nothing merged")
        seen.add(key)
    return CatalogPlan(catalog, groups, targets, remap, summary)


def _notes(*values) -> str | None:
    """Preserve authored notes from every absorbed record, once each."""
    unique = []
    for value in values:
        for paragraph in (value or "").split("\n\n"):
            if paragraph.strip() and paragraph.strip() not in unique:
                unique.append(paragraph.strip())
    return "\n\n".join(unique) or None


def _meanings(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[;,]", value) if part.strip()]


def _assign_changed(item, values: dict) -> None:
    for field, value in values.items():
        if getattr(item, field) != value:
            setattr(item, field, value)


def _copy_extras(target, items, kind):
    fields = {"vocabulary": ["notes"], "grammar": ["nuances"], "kanji": ["mnemonic"]}[kind]
    for field in fields:
        setattr(target, field, _notes(*(getattr(item, field) for item in items)) or ("" if kind == "grammar" else None))
    if kind == "grammar":
        for field in ("examples", "counter_examples"):
            combined = []
            for item in items:
                for example in getattr(item, field) or []:
                    if example not in combined:
                        combined.append(example)
            setattr(target, field, combined)


def _sync_translations(db, target, items, row, kind):
    model, fk, field = TRANSLATIONS[kind]
    locales = {"en", "fr"} | {t.locale for item in items for t in item.translations}
    for locale in locales:
        records = [t for item in items for t in item.translations if t.locale == locale]
        value = _meanings(row["French" if locale == "fr" else "English"]) if kind == "kanji" else row["French" if locale == "fr" else "English"]
        if locale not in {"en", "fr"}:
            values = {json.dumps(getattr(t, field), ensure_ascii=False) for t in records}
            if len(values) != 1:
                raise ValueError(f"Conflicting supplementary translation: {row['ID']} {locale}")
            value = getattr(records[0], field)
        record = next((t for t in target.translations if t.locale == locale), None)
        if record is None:
            record = model(**{fk: target.id, "locale": locale, field: value})
            db.add(record)
        else:
            _assign_changed(record, {field: value})
        extra = {"vocabulary": "notes", "grammar": "nuances", "kanji": "mnemonic"}[kind]
        notes = _notes(row.get("Notes") if kind == "vocabulary" and locale == "fr" else None,
                       *(getattr(t, extra) for t in records))
        _assign_changed(record, {extra: notes or ("" if kind == "grammar" else None)})


def _remap_references(db, plan):
    for kind, mapping in plan.remap.items():
        for old, target in mapping.items():
            for model in (LearningState, ReviewHistory, StudyQuestion):
                table = model.__table__
                db.execute(update(table).where(table.c.content_type == kind, table.c.content_id == old)
                           .values(content_id=target, updated_at=table.c.updated_at))
            for model, fk in ((ExampleSentence, f"{kind}_item_id"), (GrammarExercise, "grammar_item_id")):
                if model == ExampleSentence and kind not in {"vocabulary", "grammar"}:
                    continue
                if model == GrammarExercise and kind != "grammar":
                    continue
                table = model.__table__
                db.execute(update(table).where(table.c[fk] == old).values({fk: target, "updated_at": table.c.updated_at}))
            db.execute(update(ContentAlias).where(ContentAlias.content_type == kind, ContentAlias.content_id == old).values(content_id=target))
    for session in db.scalars(select(StudySession)):
        scope = session.snapshot or {}
        categories = scope.get("categories", [])
        if len(categories) == 1 and (target := plan.remap.get(categories[0], {}).get(scope.get("content_id"))):
            # Historical questions/answers remain immutable; only the scope key moves.
            table = StudySession.__table__
            db.execute(update(table).where(table.c.id == session.id)
                       .values(snapshot={**scope, "content_id": target}, updated_at=table.c.updated_at))


def apply_plan(db: Session, plan: CatalogPlan) -> dict:
    """Caller commits only after independent invariant checks; exceptions roll back."""
    for kind in ("kanji", "vocabulary", "grammar"):
        model = MODELS[kind]
        for order, row in enumerate(plan.catalog.rows[kind], 1):
            items = plan.groups[kind][row["ID"]]
            target = items[0] if items else model(id=plan.targets[kind][row["ID"]],
                                                 slug=row["Kanji"] if kind == "kanji" else f"{kind}-{row['ID']}")
            if not items:
                if kind == "vocabulary":
                    target.part_of_speech = "other"
                db.add(target)
            _copy_extras(target, items, kind)
            values = {"catalog_id": row["ID"], "source_order": order, "jlpt_level_code": row["Level"]}
            if kind == "vocabulary":
                japanese, reading = row["Kanji"] or row["Kana"], row["Kana"]
                furigana = validate_furigana(japanese, reading, json.loads(row["Furigana"])) if row["Furigana"] else build_furigana(japanese, reading)[0]
                values.update(japanese=japanese, reading=reading, romaji=row["Romaji"],
                              romaji_search=romaji_search_key([reading], row["Romaji"]),
                              furigana_segments=furigana, translation=row["English"],
                              kanji_level_code=row["KanjiLevel"] or None,
                              audio_url=canonical_row_audio(row, db))
            elif kind == "grammar":
                values.update(title=grammar_title(row), explanation=row["English"],
                              romaji_search=romaji_search_key([row["Kana"]], row["Romaji"]))
                # Legacy structure is the import's reading field. Keep authored syntax
                # if it is not a reading; always use source romaji for new records.
                structure = target.structure or ""
                if not structure or grammar_key(structure) in plan.catalog.grammar_readings.get(row["ID"], set()):
                    values["structure"] = row["Romaji"]
            else:
                readings = [p.strip() for p in re.split(r"[・,;/]", row["Pronunciation"]) if p.strip()]
                onyomi = [p for p in readings if any("ァ" <= c <= "ヶ" for c in p)]
                kunyomi = [p for p in readings if p not in onyomi]
                values.update(character=row["Kanji"], meanings=_meanings(row["English"]),
                              onyomi=onyomi, kunyomi=kunyomi, romaji_search=romaji_search_key(readings))
            _assign_changed(target, values)
            _sync_translations(db, target, items, row, kind)
        db.flush()
    _remap_references(db, plan)
    # Rebuild only derived links; the catalogue supplies the written forms.
    link_table = VocabularyKanjiLink.__table__
    expected = {}
    kanji_ids = {r["Kanji"]: plan.targets["kanji"][r["ID"]] for r in plan.catalog.rows["kanji"]}
    for row in plan.catalog.rows["vocabulary"]:
        word_id = plan.targets["vocabulary"][row["ID"]]
        for position, char in enumerate(row["Kanji"] or row["Kana"], start=1):
            if char in kanji_ids:
                expected.setdefault((word_id, kanji_ids[char]), {"kanji_position": position, "is_primary": True})
    existing = {(r.vocabulary_item_id, r.kanji_item_id): r for r in db.execute(select(link_table))}
    for pair, link in existing.items():
        where = (link_table.c.vocabulary_item_id == pair[0], link_table.c.kanji_item_id == pair[1])
        if pair not in expected:
            db.execute(delete(link_table).where(*where))
        elif any(getattr(link, field) != value for field, value in expected[pair].items()):
            db.execute(update(link_table).where(*where).values(**expected[pair]))
    additions = [{"vocabulary_item_id": pair[0], "kanji_item_id": pair[1], **values}
                 for pair, values in expected.items() if pair not in existing]
    if additions:
        db.execute(link_table.insert(), additions)
    for kind, groups in plan.groups.items():
        translation, fk, _ = TRANSLATIONS[kind]
        for items in groups.values():
            for old in items[1:]:
                target = plan.remap[kind][old.id]
                for alias in (old.id, old.slug):
                    prior = db.get(ContentAlias, (kind, alias))
                    if prior and prior.content_id != target:
                        raise ValueError("Conflicting legacy URL alias")
                    if not prior:
                        db.add(ContentAlias(content_type=kind, alias=alias, content_id=target))
                db.execute(delete(translation.__table__).where(translation.__table__.c[fk] == old.id))
                db.execute(delete(MODELS[kind].__table__).where(MODELS[kind].id == old.id))
    db.flush()
    db.expire_all()
    return plan.summary
