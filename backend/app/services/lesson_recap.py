"""Cumulative tests drawn only from the current and previously completed lessons."""
from copy import deepcopy
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.lesson import Lesson, LessonProgress
from app.services.lesson_choices import lesson_options


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def build_recap(db: Session, lesson: Lesson, user_id: str) -> list[dict]:
    previous = list(db.scalars(select(Lesson).join(
        LessonProgress, LessonProgress.lesson_id == Lesson.id
    ).where(
        LessonProgress.user_id == user_id, LessonProgress.completed_at.is_not(None),
        LessonProgress.version == Lesson.version,
        Lesson.position < lesson.position,
    ).order_by(Lesson.position)))
    sources = previous + [lesson]
    candidates = {}
    kanjis = {}
    expected = set()
    known_characters = set()
    for source in sources:
        words = {s["source_id"]: s for s in source.content["steps"] if s["kind"] == "word"}
        vocabulary = set(source.content.get("vocabulary_ids", []))
        grammar = set(source.content.get("grammar_ids", []))
        expected.update(f"vocabulary:{identity}" for identity in vocabulary)
        expected.update(f"grammar:{identity}" for identity in grammar)
        for raw in source.content["steps"]:
            if raw["kind"] == "word":
                known_characters.update(c for c in raw["japanese"] if "\u3400" <= c <= "\u9fff")
            if raw["kind"] == "kanji" and raw.get("source_id") in source.content.get("kanji_ids", []):
                kanjis.setdefault(raw["character"], (source, raw))
                known_characters.add(raw["character"])
            identity = raw.get("source_id") or (raw["id"].removeprefix("apply-") if raw["id"].startswith("apply-") else None)
            if raw["kind"] not in {"choice", "recall"} or not identity or raw.get("review"):
                continue
            category = "vocabulary" if identity in vocabulary and identity in words else "grammar" if identity in grammar else None
            if category is None:
                continue
            step = deepcopy(raw)
            if step["kind"] == "choice":
                step["options"] = deepcopy(lesson_options(raw))
                if len(step["options"]) != 4:
                    continue
            key = f"{category}:{identity}"
            # One question for each taught concept; prefer the existing recognition quiz.
            priority = (raw["kind"] != "choice", source.position, raw["id"])
            if key in candidates and priority >= candidates[key][0]:
                continue
            if identity in words:
                step["recap_word"] = deepcopy(words[identity])
            candidates[key] = (priority, source, category, step)

    # Test meanings against written forms already encountered, not future kanji.
    for character, (source, raw) in kanjis.items():
        distractors = sorted(known_characters - {character}, key=lambda c: _hash(f"{lesson.id}:{character}:{c}"))[:3]
        meaning = raw["meaning"]
        step = dict(solution={"fr": character, "en": character},
                    prompt={"fr": f"Quel kanji correspond à : {meaning['fr']} ?", "en": f"Which kanji means: {meaning['en']}?"},
                    explanation={"fr": f"{character} : {meaning['fr']}", "en": f"{character}: {meaning['en']}"})
        if len(distractors) == 3:
            options = [{"id": _hash(c), "label": {"fr": c, "en": c}} for c in [character, *distractors]]
            step.update(kind="choice", options=options, correct_option=options[0]["id"])
        else:
            step.update(kind="recall", accepted=[character])
        candidates[f"kanji:{character}"] = ((), source, "kanji", step)
    expected.update(f"kanji:{character}" for character in kanjis)
    if expected - candidates.keys():
        raise HTTPException(409, "Some taught items have no valid recap exercise; contact support")
    categories = ("vocabulary", "grammar", "kanji")
    selected = sorted(candidates, key=lambda key: (categories.index(candidates[key][2]), candidates[key][1].position, key))
    if not selected:
        return []
    result = [dict(id="recap-intro", kind="read", recap=True,
                   title={"fr": "Faisons le point", "en": "Bring it all together"},
                   body={"fr": f"{len(selected)} questions : un exercice pour chaque mot, point de grammaire et kanji de ce thème et des leçons précédentes terminées. Le bilan est exhaustif, sans limite de questions. Ta progression est sauvegardée après chaque réponse : tu peux quitter et reprendre plus tard.",
                         "en": f"{len(selected)} questions: one exercise for every word, grammar point and kanji from this theme and earlier completed lessons. This is a full test, with no question limit. Progress is saved after every answer: leave and resume whenever you need."})]
    totals = {category: sum(candidates[k][2] == category for k in selected) for category in categories}
    counts = dict.fromkeys(categories, 0)
    for index, key in enumerate(selected, 1):
        _, source, category, step = candidates[key]
        counts[category] += 1
        step.update(id=f"recap-{_hash(key)}", recap=True, recap_key=key, recap_category=category,
                    recap_section_index=counts[category], recap_section_total=totals[category],
                    source_lesson_id=source.id, source_lesson_title=deepcopy(source.content["title"]),
                    title={"fr": f"Bilan cumulatif · {index} / {len(selected)}", "en": f"Cumulative test · {index} / {len(selected)}"})
        if step["kind"] == "choice":
            step["options"].sort(key=lambda o: _hash(f"{user_id}:{lesson.id}:{key}:{o['id']}"))
        result.append(step)
    return result
