"""Compile the authored N5 curriculum; dry-run by default, --import-db to upsert."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import func, select
from app.models.lesson import Lesson, LessonProgress
from app.utils.furigana import build_furigana

DATA = ROOT / "backend/app/data"
CATALOG = ROOT / "contenu csv/consolidated"


def bilingual(fr: str, en: str) -> dict:
    return {"fr": fr, "en": en}


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def first(value: str) -> str:
    return re.split(r"\s*/\s*|\s+", value.strip())[0]


def surface(row: dict) -> str:
    spelling = first(row["Kanji"] or row["Kana"]) if row["KanjiLevel"] == "N5" else first(row["Kana"])
    # Some catalog verbs store only their noun stem in Kanji, but include する in Kana.
    if row["KanjiLevel"] == "N5" and first(row["Kana"]).endswith("する") and not spelling.endswith("する"):
        spelling += "する"
    return spelling


def writings(row: dict) -> list[str]:
    return re.split(r"\s*/\s*|\s+", row["Kanji"] or row["Kana"]) if row["KanjiLevel"] == "N5" else [first(row["Kana"])]


def meanings(row: dict) -> dict:
    return bilingual(row["French"], row["English"])


def partitions(values: list, count: int) -> list[list]:
    # Contiguous balanced groups preserve the author's teaching order.
    return [values[i * len(values) // count:(i + 1) * len(values) // count] for i in range(count)]


def choice(step_id: str, prompt: dict, answer: dict, distractors: list[dict], **extra) -> dict:
    options = [{"id": digest([step_id, label])[:16], "label": label} for label in [answer, *distractors]]
    correct = options[0]["id"]
    options.sort(key=lambda option: digest([step_id, option["id"]]))
    return dict(id=step_id, kind="choice", title=bilingual("À toi de jouer", "Your turn"),
        prompt=prompt, options=options, correct_option=correct, solution=answer, **extra)


def distractors_for(row: dict, rows: list[dict], count: int = 2) -> list[dict]:
    def tokens(value):
        return {v.strip().casefold() for v in re.split(r"[;,/]", value)}
    candidates = sorted(rows, key=lambda candidate: digest([row["ID"], candidate["ID"]]))
    chosen = [row]
    for candidate in candidates:
        if any(candidate["Kana"] == other["Kana"] or surface(candidate) == surface(other)
               or any(tokens(candidate[key]) & tokens(other[key]) for key in ("French", "English"))
               for other in chosen):
            continue
        chosen.append(candidate)
        if len(chosen) == count + 1:
            return [meanings(item) for item in chosen[1:]]
    raise ValueError(f"Not enough distinct distractors: {row['ID']}")


def compile_course() -> tuple[list[dict], dict]:
    plan = json.loads((DATA / "n5_units.json").read_text())
    examples = json.loads((DATA / "n5_grammar_examples.json").read_text())["entries"]
    foundations = json.loads((DATA / "n5_foundations.json").read_text())
    english_patterns = json.loads((DATA / "n5_grammar_patterns_en.json").read_text())
    tables = {}
    for category, expected in plan["source_sha256"].items():
        path = CATALOG / f"{category}.csv"
        # Reviewed metadata-only edits can keep the authored lesson versions stable.
        compatible = plan.get("compatible_source_sha256", {}).get(category, [])
        if hashlib.sha256(path.read_bytes()).hexdigest() not in {expected, *compatible}:
            raise ValueError(f"{category}: source changed; reconcile authored indices before importing")
        with path.open(encoding="utf-8-sig", newline="") as handle:
            tables[category] = [row for row in csv.DictReader(handle, delimiter=";") if row["Level"] == "N5"]
    for category in ("vocabulary", "grammar"):
        counts = Counter(index for unit in plan["units"] for index in unit[category])
        if set(counts) != set(range(len(tables[category]))) or any(n != 1 for n in counts.values()):
            raise ValueError(f"Incomplete or duplicate {category} assignments")
    if set(examples) != {str(i) for i in range(len(tables["grammar"]))}:
        raise ValueError("Each grammar point needs an original exercise")

    vocabulary, grammar, kanji = (tables[key] for key in ("vocabulary", "grammar", "kanji"))
    kanji_by_unit = [[] for _ in plan["units"]]
    for character in kanji:
        match = next((i for i, unit in enumerate(plan["units"])
            if any(any(character["Kanji"] in spelling for spelling in writings(vocabulary[index])) for index in unit["vocabulary"])), None)
        if match is None:
            raise ValueError(f"No N5 writing example for {character['Kanji']}")
        kanji_by_unit[match].append(character)

    lessons = []
    seen_vocabulary = set()
    for unit_index, unit in enumerate(plan["units"]):
        count = max(len(unit["grammar"]), math.ceil(len(unit["vocabulary"]) / 8), math.ceil(len(kanji_by_unit[unit_index]) / 3))
        word_groups = partitions(unit["vocabulary"], count)
        kanji_groups = partitions(kanji_by_unit[unit_index], count)
        review_indices = [index for index in unit["review_vocabulary"] if index in seen_vocabulary]
        review_groups = partitions(review_indices, count)
        for part in range(count):
            lesson_id = f"n5-{unit['id']}-{part + 1:02d}"
            words = [vocabulary[index] for index in word_groups[part]]
            grammar_index = unit["grammar"][part] if part < len(unit["grammar"]) else None
            point = grammar[grammar_index] if grammar_index is not None else None
            steps = [{"id": "goal", "kind": "read", "title": unit["title"], "body": unit["goal"]}]
            if part == 0:
                if unit["id"] in foundations:
                    steps.append(dict(id="foundation", kind="read", title=bilingual("Les repères utiles", "Useful foundations"), body=foundations[unit["id"]]))
                steps.append(dict(id="scene", kind="dialogue", title=bilingual("Une situation à observer", "A scene to observe"),
                    body=bilingual("Lis avec la traduction. Les expressions nouvelles seront travaillées progressivement.", "Read with the translation. New expressions will be practised progressively."),
                    lines=[dict(speaker=a, japanese=b, translation=bilingual(c, d)) for a,b,c,d in unit["scene"]]))
            for row in words:
                jp = surface(row)
                segments, _ = build_furigana(jp, first(row["Kana"]))
                steps.append(dict(id=f"word-{row['ID']}", kind="word", title=bilingual("Un nouveau mot", "A new word"),
                    source_id=row["ID"], japanese=jp, segments=segments, romaji=row["Romaji"].split("/")[0].strip(),
                    meaning=meanings(row), audio_row={key: row[key] for key in ("ID", "Kanji", "Kana", "Yomigana", "Audio")},
                    reading_note=bilingual("Observe la lecture, puis essaie de retrouver le sens sans regarder.", "Notice the reading, then try recalling the meaning without looking.")))
            if point is not None:
                pattern, sentence, answer, wrong, fr, en = examples[str(grammar_index)]
                if sentence.count("____") != 1 or len(set([answer, *wrong])) != 3:
                    raise ValueError(f"Invalid grammar exercise {grammar_index}")
                steps.append(dict(id=f"grammar-{point['ID']}", kind="grammar", source_id=point["ID"],
                    title=point["Kanji"] or point["Kana"], body=bilingual(point["French"] + "\n\n" + pattern, point["English"] + "\n\n" + english_patterns[grammar_index]),
                    japanese=sentence.replace("____", answer), translation=bilingual(fr,en)))
            for row in kanji_groups[part]:
                readings = row["Pronunciation"].split("・")
                related = [(word, next(spelling for spelling in writings(word) if row["Kanji"] in spelling))
                    for word in vocabulary if any(row["Kanji"] in spelling for spelling in writings(word))][:3]
                steps.append(dict(id=f"kanji-{row['ID']}", kind="kanji", title=bilingual("Un kanji à reconnaître", "A kanji to recognise"),
                    source_id=row["ID"], character=row["Kanji"], meaning=meanings(row),
                    onyomi=[r for r in readings if re.search(r"[ァ-ヶ]", r)], kunyomi=[r for r in readings if not re.search(r"[ァ-ヶ]", r)],
                    lines=[dict(japanese=spelling, translation=meanings(word)) for word, spelling in related],
                    body=bilingual("Les lectures dépendent du mot. Observe les exemples ; il n'est pas nécessaire de mémoriser toutes les lectures d'un coup.", "Readings depend on the word. Observe the examples; you do not need to memorise every reading at once.")))
            for row in words + [vocabulary[index] for index in review_groups[part]]:
                steps.append(choice(f"recognise-{row['ID']}", bilingual("Quel est le sens de ce mot ?", "What does this word mean?"),
                    meanings(row), distractors_for(row, vocabulary), japanese=surface(row), source_id=row["ID"], review=row not in words))
            if point is not None:
                steps.append(choice(f"apply-{point['ID']}", bilingual("Complète pour obtenir ce sens : " + fr, "Complete to express: " + en),
                    bilingual(answer, answer), [bilingual(v,v) for v in wrong], japanese=sentence,
                    explanation=bilingual(sentence.replace("____",answer) + "\n" + fr, sentence.replace("____",answer) + "\n" + en)))
            for row in words[:2]:
                accepted = [v.strip() for v in row["Kana"].split("/") + row["Romaji"].split("/")]
                accepted.append(surface(row))
                steps.append(dict(id=f"recall-{row['ID']}", kind="recall", title=bilingual("Sans regarder", "Without looking"),
                    prompt=bilingual("Écris ce mot en kana ou en romaji.", "Write this word in kana or romaji."), meaning=meanings(row),
                    accepted=accepted, solution=bilingual(first(row["Kana"]), first(row["Kana"])), source_id=row["ID"]))
            steps.append(dict(id="reflect", kind="read", title=bilingual("Un dernier geste", "One last step"),
                body=bilingual("Reprends un mot ou une structure de cette leçon et dis une phrase personnelle à voix haute. Les erreurs vues ici sont des repères pour réviser, pas un jugement de maîtrise.", "Use a word or structure from this lesson in a personal sentence aloud. Mistakes here guide your revision; they are not a mastery judgement.")))
            content = dict(unit_id=unit["id"], unit_title=unit["title"],
                title=bilingual(f"{unit['title']['fr']} · {part+1}", f"{unit['title']['en']} · {part+1}"),
                goal=unit["goal"], minutes=max(4, math.ceil(len(steps)*0.35)), steps=steps,
                vocabulary_ids=[word["ID"] for word in words], grammar_ids=[point["ID"]] if point else [],
                kanji_ids=[k["ID"] for k in kanji_groups[part]], source_sha256=plan["source_sha256"],
                prerequisites=[lessons[-1]["id"]] if lessons else [])
            lessons.append(dict(id=lesson_id, level="N5", position=len(lessons)+1, version=digest(content), content=content))
        seen_vocabulary.update(unit["vocabulary"])
    report = dict(units=len(plan["units"]), lessons=len(lessons), vocabulary=len(vocabulary), grammar=len(grammar), kanji=len(kanji),
        steps=sum(len(item["content"]["steps"]) for item in lessons), source_sha256=plan["source_sha256"])
    return lessons, report


def import_course(db, lessons: list[dict]) -> dict:
    result = dict(created=0, updated=0, unchanged=0)
    next_position = db.scalar(select(func.max(Lesson.position))) or 0
    # One transaction: never discard existing user progress or silently change its meaning.
    for item in lessons:
        existing = db.scalar(select(Lesson).where(Lesson.id == item["id"]).with_for_update())
        if existing and existing.version == item["version"]:
            result["unchanged"] += 1
            continue
        if existing and db.scalar(select(LessonProgress.user_id).where(LessonProgress.lesson_id == existing.id).limit(1)):
            raise ValueError(f"{existing.id} has learner progress; publish a new versioned lesson instead")
        if existing:
            for key, value in item.items():
                if key != "position":
                    setattr(existing, key, value)
            result["updated"] += 1
        else:
            # Published recap rows now occupy positions between the source lessons.
            next_position += 1
            db.add(Lesson(**{**item, "position": next_position}))
            result["created"] += 1
    db.flush()
    from app.services.theme_recaps import publish_theme_recaps
    result["theme_recaps"] = publish_theme_recaps(db)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--import-db", action="store_true")
    args = parser.parse_args()
    lessons, report = compile_course()
    if args.import_db:
        from app.core.database import SessionLocal
        with SessionLocal.begin() as db:
            report["import"] = import_course(db, lessons)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
