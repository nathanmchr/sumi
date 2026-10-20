"""Lesson completion is activity progress, not an SRS mastery rating."""
import hashlib
import json
import unicodedata
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, load_only
from app.models.lesson import Lesson, LessonProgress
from app.schemas.lesson import LessonCommand, LessonState, LessonSummary
from app.services.lesson_sequence import ordered_steps
from app.services.lesson_choices import lesson_options
from app.services.lesson_readings import reading_aids
from app.services.lesson_recap import build_recap
from app.services.theme_recaps import is_theme_recap, require_completed_theme


def localized(value, locale: str):
    if isinstance(value, dict):
        if set(value) == {"fr", "en"}:
            return value[locale]
        return {key: localized(item, locale) for key, item in value.items()}
    if isinstance(value, list):
        return [localized(item, locale) for item in value]
    return value


def normalize_answer(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().strip()
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in value if not c.isspace())


def summary(lesson: Lesson, progress: LessonProgress | None, locale: str, *, total: int | None = None, recap_count: int | None = None) -> LessonSummary:
    data = localized(lesson.content, locale)
    if not is_theme_recap(lesson):
        recap_count = 0
    elif recap_count is None:
        recap_count = len(progress.recap_steps or []) if progress else 0
    return LessonSummary(
        id=lesson.id, unit_id=data["unit_id"], unit_title=data["unit_title"],
        title=data["title"], goal=data["goal"], position=lesson.position,
        minutes=max(1, recap_count // 2) if is_theme_recap(lesson) and recap_count else data["minutes"],
        total_steps=total if total is not None else max(1, len(data["steps"]) + recap_count),
        completed_steps=progress.cursor if progress else 0,
        completed=bool(progress and progress.completed_at),
        vocabulary_count=len(data["vocabulary_ids"]), grammar_count=len(data["grammar_ids"]),
        kanji_count=len(data["kanji_ids"]),
        is_recap=is_theme_recap(lesson),
    )


def list_lessons(db: Session, user_id: str, level: str, locale: str):
    lessons = list(db.scalars(select(Lesson).where(Lesson.level == level).order_by(Lesson.position)))
    # The course overview only needs counts, not hundreds of saved questions per lesson.
    progress = {p.lesson_id: (p, count) for p, count in db.execute(select(
        LessonProgress, func.coalesce(func.json_array_length(LessonProgress.recap_steps), 0)
    ).options(load_only(LessonProgress.cursor, LessonProgress.completed_at, LessonProgress.version)).where(LessonProgress.user_id == user_id))}
    rows = [summary(lesson, progress.get(lesson.id, (None, 0))[0], locale,
                    recap_count=progress.get(lesson.id, (None, 0))[1]) for lesson in lessons]
    completed_ids = {lesson.id for lesson in lessons if lesson.id in progress
                     and progress[lesson.id][0].completed_at and progress[lesson.id][0].version == lesson.version}
    for lesson, row in zip(lessons, rows):
        row.locked = is_theme_recap(lesson) and not set(lesson.content["prerequisite_ids"]).issubset(completed_ids)
    # Resume a started lesson before recommending the next untouched one.
    recommended = next((row for row in rows if row.completed_steps and not row.completed and not row.locked), None)
    recommended = recommended or next((row for row in rows if not row.completed and not row.locked), None)
    if recommended:
        recommended.recommended = True
    return rows


def require_lesson(db: Session, lesson_id: str, lock: bool = False) -> Lesson:
    lesson = db.scalar(select(Lesson).where(Lesson.id == lesson_id).with_for_update(read=True)) if lock else db.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found")
    return lesson


def previous_kanji_examples(db: Session, lesson: Lesson, user_id: str, character: str, locale: str) -> list[dict]:
    previous = db.scalars(select(Lesson.content).join(LessonProgress, LessonProgress.lesson_id == Lesson.id).where(
        LessonProgress.user_id == user_id,
        LessonProgress.completed_at.is_not(None),
        LessonProgress.version == Lesson.version,
        Lesson.position < lesson.position,
    ).order_by(Lesson.position.desc()))
    examples = []
    seen_ids = set()
    seen_spellings = set()
    for content in previous:
        for word in content["steps"]:
            if word["kind"] != "word":
                continue
            spelling = word["japanese"]
            identity = word["source_id"]
            # Use the spelling actually taught, not an unseen catalog variant.
            if character not in spelling or identity in seen_ids or spelling in seen_spellings:
                continue
            examples.append({"japanese": spelling, "translation": localized(word["meaning"], locale), **reading_aids(word)})
            seen_ids.add(identity)
            seen_spellings.add(spelling)
            if len(examples) == 3:
                return examples
    return examples


def state(db: Session, lesson: Lesson, progress: LessonProgress | None, locale: str, viewing: int | None = None, *, user_id: str) -> LessonState:
    if progress and progress.version != lesson.version:
        raise HTTPException(409, "Lesson version changed; contact support")
    require_completed_theme(db, lesson, user_id)
    cursor = progress.cursor if progress else 0
    recap = (progress.recap_steps if progress and progress.recap_steps is not None else build_recap(db, lesson, user_id)) if is_theme_recap(lesson) else []
    steps = ordered_steps(lesson, progress) + recap
    index = cursor if viewing is None else viewing
    if index > cursor or index < 0 or index > len(steps):
        raise HTTPException(422, "Step is not available yet")
    visible_ids = {item["id"] for item in steps}
    answers = {key: value for key, value in progress.answers.items() if key in visible_ids} if progress else {}
    step = None
    feedback = None
    if index < len(steps):
        raw = steps[index]
        # Whitelist: never serialize future correct answers or acceptance rules.
        public = {key: raw[key] for key in (
            "id", "kind", "title", "body", "japanese", "translation", "segments", "romaji",
            "audio_url", "character", "meaning", "onyomi", "kunyomi", "options", "prompt", "lines",
            "reading_note", "source_id", "review", "kanji_characters",
            "recap", "recap_category", "source_lesson_id", "source_lesson_title",
            "recap_section_index", "recap_section_total",
        ) if key in raw}
        step = localized(public, locale)
        if raw["kind"] == "choice":
            step["options"] = localized(lesson_options(raw), locale)
        if raw["kind"] == "kanji":
            # Resolve at read time so existing lesson versions and cursors stay intact.
            examples = previous_kanji_examples(db, lesson, user_id, raw["character"], locale)
            if examples:
                step["lines"] = examples
                step["body"] = localized({
                    "fr": "Retrouve ce kanji dans des mots vus dans tes leçons précédentes terminées. Les lectures dépendent du mot ; inutile de toutes les mémoriser d'un coup.",
                    "en": "Find this kanji in words from earlier lessons you have completed. Readings depend on the word; there is no need to memorise them all at once.",
                }, locale)
            else:
                step.pop("lines", None)
                step["body"] = localized({
                    "fr": "Tu n'as pas encore rencontré de mot contenant ce kanji dans une leçon précédente terminée. Pour le moment, observe sa forme et ses lectures.",
                    "en": "You have not yet encountered a word containing this kanji in an earlier completed lesson. For now, observe its shape and readings.",
                }, locale)
        word = raw.get("recap_word") or (raw if raw["kind"] == "word" else next((item for item in lesson.content["steps"]
            if item["kind"] == "word" and raw.get("source_id") and item.get("source_id") == raw["source_id"]), None))
        if raw["kind"] in {"word", "choice"} and raw.get("japanese"):
            matching_word = word if word and word.get("japanese") == raw["japanese"] else {}
            step.update(reading_aids({**matching_word, **raw}))
        # Recognition may play the visible word; production must not reveal it before correction.
        if word and word.get("audio_row") and raw["kind"] in {"word", "choice"}:
            from app.services.catalog_audio import canonical_row_audio
            step["audio_url"] = canonical_row_audio(word["audio_row"], db)
        if raw["id"] in answers:
            answer = answers[raw["id"]]
            feedback = {"correct": answer["correct"], "answer": localized(raw["solution"], locale),
                        "explanation": localized(raw.get("explanation", ""), locale)}
            if raw["kind"] == "choice":
                feedback["correct_option_id"] = raw["correct_option"]
                feedback["selected_option_id"] = answer.get("selected_option_id")
            if word:
                feedback["japanese"] = word.get("japanese")
                feedback["meaning"] = localized(word.get("meaning"), locale)
                feedback.update(reading_aids(word))
                if raw["kind"] == "recall" and word.get("audio_row"):
                    from app.services.catalog_audio import canonical_row_audio
                    feedback["audio_url"] = canonical_row_audio(word["audio_row"], db)
            elif raw["kind"] == "choice" and raw.get("source_id") and raw.get("japanese"):
                # Review words may have been introduced in a different lesson.
                feedback.update(japanese=raw["japanese"], meaning=localized(raw["solution"], locale), **reading_aids(raw))
    next_id = db.scalar(select(Lesson.id).where(Lesson.level == lesson.level, Lesson.position > lesson.position).order_by(Lesson.position).limit(1))
    recap_ids = {item["id"] for item in recap if item["kind"] in {"choice", "recall"}}
    recap_answers = [value for key, value in answers.items() if key in recap_ids]
    return LessonState(lesson=summary(lesson, progress, locale, total=len(steps), recap_count=len(recap)), revision=progress.revision if progress else 0,
        cursor=cursor, viewing=index, step=step, feedback=feedback,
        correct=sum(bool(value["correct"]) for value in answers.values()), answered=len(answers), next_lesson_id=next_id,
        recap_total=len(recap_ids), recap_answered=len(recap_answers),
        recap_correct=sum(bool(value["correct"]) for value in recap_answers))


def command(db: Session, user_id: str, lesson_id: str, payload: LessonCommand, locale: str) -> LessonState:
    # Block a concurrent content import until this progress transaction finishes.
    lesson = require_lesson(db, lesson_id, lock=True)
    require_completed_theme(db, lesson, user_id)
    # INSERT ON CONFLICT + row lock serializes first requests and simultaneous tabs.
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif db.bind.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise RuntimeError("Unsupported lesson database dialect")
    db.execute(insert(LessonProgress).values(user_id=user_id, lesson_id=lesson_id, version=lesson.version,
        cursor=0, revision=0, answers={}).on_conflict_do_nothing(index_elements=["user_id", "lesson_id"]))
    progress = db.scalar(select(LessonProgress).where(LessonProgress.user_id == user_id,
        LessonProgress.lesson_id == lesson_id).with_for_update().execution_options(populate_existing=True))
    if progress.version != lesson.version:
        raise HTTPException(409, "Lesson version changed; contact support")
    fingerprint = hashlib.sha256(json.dumps(payload.model_dump(), sort_keys=True).encode()).hexdigest()
    if fingerprint == progress.last_command:
        return state(db, lesson, progress, locale, user_id=user_id)
    if payload.revision != progress.revision:
        raise HTTPException(409, "Progress changed in another tab; reload the lesson")
    if progress.completed_at:
        raise HTTPException(409, "Lesson already completed")
    base_steps = ordered_steps(lesson, progress)
    if is_theme_recap(lesson) and progress.recap_steps is None:
        progress.recap_steps = build_recap(db, lesson, user_id)
    steps = base_steps + (progress.recap_steps or [] if is_theme_recap(lesson) else [])
    if progress.cursor >= len(steps):
        raise HTTPException(409, "Lesson already completed")
    step = steps[progress.cursor]
    if payload.step_id != step["id"]:
        raise HTTPException(409, "This is not the current step")
    if progress.step_order is None:
        progress.step_order = [item["id"] for item in base_steps]
    is_question = step["kind"] in {"choice", "recall"}
    if payload.action == "answer":
        if not is_question or payload.answer is None or not payload.answer.strip():
            raise HTTPException(422, "An answer is required for a question")
        if step["id"] in progress.answers:
            raise HTTPException(409, "Answer already recorded")
        if step["kind"] == "choice":
            if payload.answer not in {option["id"] for option in lesson_options(step)}:
                raise HTTPException(422, "Unknown option")
            correct = payload.answer == step["correct_option"]
        else:
            correct = normalize_answer(payload.answer) in {normalize_answer(v) for v in step["accepted"]}
        recorded = {"correct": correct}
        if step["kind"] == "choice":
            recorded["selected_option_id"] = payload.answer
        progress.answers = {**progress.answers, step["id"]: recorded}
    else:
        if payload.answer is not None:
            raise HTTPException(422, "Continue cannot submit an answer")
        if is_question and step["id"] not in progress.answers:
            raise HTTPException(422, "Answer before continuing")
        progress.cursor += 1
        if progress.cursor == len(steps):
            progress.completed_at = datetime.now(timezone.utc)
    progress.revision += 1
    progress.last_command = fingerprint
    db.flush()
    return state(db, lesson, progress, locale, user_id=user_id)
